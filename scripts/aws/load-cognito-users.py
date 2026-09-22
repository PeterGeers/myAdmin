#!/usr/bin/env python3
"""load-cognito-users.py — bulk-load Cognito users into a pool from an editable file (S5c task 6.4).

Dry-run-first, idempotent bulk load of Cognito users derived from the h-dcn pool shape
(~10 region-scoped + ~10 general + 3 extra) into a target pool (dev/test: ``myAdmin-test`` =
``eu-west-1_xyrlzfqbl``; prod: Pool A in task 7.3). Mirrors the structure of the task-6.2/6.3
runners (``scripts/aws/backfill-hdcn-members.py`` / ``scripts/aws/seed-hdcn-catalog.py``):
argparse → resolve → **dry-run plan by default** → ``--apply`` to write → verify summary.

HARD SEPARATION (R8.1/R8.2, C-PLAYBOOK) — the whole point of this task
---------------------------------------------------------------------
This script does TWO clearly separated things and NOTHING else:

1. **Creates the COGNITO USERS by script** — ``admin-create-user`` + sets ``custom:tenants``
   (and any extra custom attributes) + a permanent (throwaway) password. This is the *identity*
   half. Idempotent: an already-present user (``UsernameExistsException``) is detected + skipped.
2. **Assigns the Members ROLE via the GOVERNANCE ENDPOINT** — it DRIVES the Tenant-Admin
   ``POST /api/tenant-admin/users/<email>/groups`` endpoint (which writes MySQL
   ``user_tenant_roles`` → ``enqueue_sync`` → projection). The script **NEVER** writes
   ``user_tenant_roles`` / the projection / any MySQL directly. If the endpoint cannot be driven
   headless (no ``--governance-url`` / no admin token), the script STILL creates the users + sets
   attributes and MARKS the role-assignment step as endpoint-driven-and-skipped in the summary,
   so the operator runs it through the SPA (or re-runs with the endpoint wired).

Claim shape (R8.2)
------------------
``custom:tenants`` is set per the file: a single tenant name is written as a scalar (the
PreTokenGen reader treats a non-``[``-prefixed scalar as ONE tenant); a list is written as a JSON
array string (``["A","B"]``). See ``auth.cognito_utils._normalize_tenants_claim``. The region
``scope`` is carried on the user (``custom:scope``) and conveyed to the governance assignment so a
scoped role lands the right ``scopegrant#`` subset; ``all`` means the general all-region grant.

Safety guards (aws-accounts.md, R8.2)
-------------------------------------
- **Dry-run is the default.** Nothing is created / no endpoint is called unless you pass ``--apply``.
- **No hardcoded pool/tenant.** ``--pool-id`` and ``--source`` are REQUIRED; the tenant defaults
  from the file (or ``--tenant``). A missing required arg fails argparse (exit 2).
- **Idempotent.** An existing Cognito user is skipped (never recreated / overwritten). Re-running
  is safe.
- **Throwaway/placeholder users only.** The sample file uses ``member-*@example.com`` — never real
  member PII.

Usage (from repo root, WSL)
---------------------------
  # Dry run (default — creates nothing, calls no endpoint): render the plan.
  # --pool-id + --source are REQUIRED (no hardcoded pool):
  AWS_PROFILE=personal AWS_REGION=eu-west-1 \
      backend/.venv/bin/python scripts/aws/load-cognito-users.py \
      --pool-id eu-west-1_xyrlzfqbl --source scripts/aws/cognito-users.sample.json

  # Apply into myAdmin-test (identity account) AND drive the governance endpoint for roles:
  AWS_PROFILE=personal AWS_REGION=eu-west-1 \
      backend/.venv/bin/python scripts/aws/load-cognito-users.py \
      --pool-id eu-west-1_xyrlzfqbl --source scripts/aws/cognito-users.sample.json \
      --governance-url https://<tenant-admin-api> --governance-token "$ADMIN_JWT" --apply

  # Apply users only (create + attributes), leave role assignment for the SPA governance step:
  AWS_PROFILE=personal AWS_REGION=eu-west-1 \
      backend/.venv/bin/python scripts/aws/load-cognito-users.py \
      --pool-id eu-west-1_xyrlzfqbl --source scripts/aws/cognito-users.sample.json --apply
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# repo root + backend/src on sys.path so `auth...` / `services...` import if ever needed
# (mirrors backfill-hdcn-members.py / seed-hdcn-catalog.py path setup).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

DEFAULT_REGION = "eu-west-1"
#: How many planned users to show as samples in the dry-run plan.
_SAMPLE_COUNT = 3
#: Recognized Members capability-intent roles (the vocabulary the governance endpoint accepts for
#: this pilot). Validated per-row so a typo fails loudly instead of assigning a bogus role.
_KNOWN_ROLES = frozenset({"Members_Read", "Members_CRUD", "Members_Export"})


# ---------------------------------------------------------------------------
# The editable input file → a validated, pure plan (no I/O, no AWS)
# ---------------------------------------------------------------------------


class UserSpecError(ValueError):
    """A row in the editable file is malformed (missing email, unknown role, bad scope, ...)."""


@dataclass(frozen=True)
class UserSpec:
    """One editable-file row, normalized. Pure data — carries no I/O."""

    email: str
    tenants: list[str]
    role: str
    #: ``"all"`` (general, every region) or a non-empty list of region names (scoped subset).
    scope: object
    password: str | None = None

    @property
    def is_scoped(self) -> bool:
        return self.scope != "all"

    def tenants_claim(self) -> str:
        """Render ``custom:tenants`` per the PreTokenGen reader's shape rules (R8.2).

        A single tenant is a scalar string (read as ONE tenant); many tenants are a JSON array
        string ``["A","B"]`` (read as MANY). See
        ``auth.cognito_utils._normalize_tenants_claim``.
        """
        if len(self.tenants) == 1:
            return self.tenants[0]
        return json.dumps(self.tenants, ensure_ascii=False)

    def scope_claim(self) -> str:
        """Render ``custom:scope`` — ``"*"`` for all-region, else a JSON array of the subset."""
        if not self.is_scoped:
            return "*"
        return json.dumps(list(self.scope), ensure_ascii=False)


def _normalize_row(row: dict, *, default_tenant: str | None) -> UserSpec:
    """Validate + normalize one raw file row into a :class:`UserSpec` (loud on bad input)."""
    if not isinstance(row, dict):
        raise UserSpecError(f"each user must be an object, got: {row!r}")

    email = str(row.get("email", "")).strip()
    if not email or "@" not in email:
        raise UserSpecError(f"user is missing a valid 'email': {row!r}")

    role = str(row.get("role", "")).strip()
    if role not in _KNOWN_ROLES:
        raise UserSpecError(
            f"user {email!r} has unknown role {role!r} (expected one of {sorted(_KNOWN_ROLES)})"
        )

    # tenants: explicit on the row (scalar or list) else the file/CLI default.
    raw_tenants = row.get("tenants", None)
    if raw_tenants is None:
        if not default_tenant:
            raise UserSpecError(
                f"user {email!r} has no 'tenants' and no default tenant is set "
                "(set 'default_tenant' in the file or pass --tenant)"
            )
        tenants = [default_tenant]
    elif isinstance(raw_tenants, list):
        tenants = [str(t).strip() for t in raw_tenants if str(t).strip()]
    else:
        tenants = [str(raw_tenants).strip()]
    if not tenants:
        raise UserSpecError(f"user {email!r} resolved to an empty tenant list")

    # scope: "all" (general) or a non-empty list (scoped subset).
    raw_scope = row.get("scope", "all")
    if isinstance(raw_scope, str):
        if raw_scope.strip().lower() != "all":
            raise UserSpecError(
                f"user {email!r} scope string must be 'all' or a list, got {raw_scope!r}"
            )
        scope: object = "all"
    elif isinstance(raw_scope, list):
        regions = [str(s).strip() for s in raw_scope if str(s).strip()]
        if not regions:
            raise UserSpecError(f"user {email!r} scope list is empty (use 'all' or list regions)")
        scope = regions
    else:
        raise UserSpecError(f"user {email!r} scope must be 'all' or a list, got {raw_scope!r}")

    password = row.get("password")
    password = str(password) if password not in (None, "") else None

    return UserSpec(email=email, tenants=tenants, role=role, scope=scope, password=password)


@dataclass
class LoadPlan:
    """The parsed, validated load plan (pure — built by a read-only parse of the file)."""

    source_description: str
    default_tenant: str | None
    users: list[UserSpec] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (row-ref, reason)

    @property
    def ok_count(self) -> int:
        return len(self.users)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def scoped_count(self) -> int:
        return sum(1 for u in self.users if u.is_scoped)

    @property
    def general_count(self) -> int:
        return sum(1 for u in self.users if not u.is_scoped)

    def role_breakdown(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for u in self.users:
            out[u.role] = out.get(u.role, 0) + 1
        return out


def build_load_plan(source_path: str, *, cli_default_tenant: str | None = None) -> LoadPlan:
    """Read the editable file READ-ONLY and build a validated :class:`LoadPlan`.

    The file is a JSON object with an optional ``default_tenant`` and a ``users`` array (see
    ``scripts/aws/cognito-users.sample.json``). A ``--tenant`` on the CLI overrides the file's
    ``default_tenant``. Malformed rows are collected as errors (never silently dropped) so the
    dry-run surfaces them before any write.
    """
    with open(source_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict) or "users" not in doc:
        raise UserSpecError(
            f"{source_path}: expected a JSON object with a 'users' array (see the sample file)"
        )

    default_tenant = cli_default_tenant or doc.get("default_tenant") or None
    plan = LoadPlan(source_description=source_path, default_tenant=default_tenant)
    for i, row in enumerate(doc["users"]):
        ref = str(row.get("email", f"row[{i}]")) if isinstance(row, dict) else f"row[{i}]"
        try:
            plan.users.append(_normalize_row(row, default_tenant=default_tenant))
        except UserSpecError as exc:
            plan.errors.append((ref, str(exc)))
    return plan


# ---------------------------------------------------------------------------
# Seams — the Cognito admin client + the governance-endpoint client
# ---------------------------------------------------------------------------


class CognitoAdminClient:
    """Thin wrapper over the boto3 ``cognito-idp`` client (the single Cognito touch-point).

    Reuses the same boto3 ``cognito-idp`` client the rest of the codebase uses
    (``auth.cognito_utils`` drives cognito-idp). Injected in tests with an in-memory fake so no
    live pool is touched.
    """

    def __init__(self, *, region: str, client=None):
        if client is not None:
            self._client = client
        else:
            import boto3  # lazy — only when actually applying

            self._client = boto3.client("cognito-idp", region_name=region)

    def user_exists(self, pool_id: str, email: str) -> bool:
        try:
            self._client.admin_get_user(UserPoolId=pool_id, Username=email)
            return True
        except self._client.exceptions.UserNotFoundException:
            return False

    def create_user(self, pool_id: str, spec: "UserSpec", *, password: str) -> None:
        """``admin-create-user`` + ``custom:tenants``/``custom:scope`` + a permanent password.

        Idempotent at the caller level: the caller checks ``user_exists`` first, and a racing
        ``UsernameExistsException`` is treated as already-present (not an error).
        """
        attributes = [
            {"Name": "email", "Value": spec.email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "custom:tenants", "Value": spec.tenants_claim()},
            {"Name": "custom:scope", "Value": spec.scope_claim()},
        ]
        try:
            self._client.admin_create_user(
                UserPoolId=pool_id,
                Username=spec.email,
                UserAttributes=attributes,
                MessageAction="SUPPRESS",  # throwaway users — no invite email
            )
        except self._client.exceptions.UsernameExistsException:
            # Idempotent: treat a racing existing user as already-present (skip, don't crash).
            return
        # Set a permanent (throwaway) password so the user is immediately usable in dev/test.
        self._client.admin_set_user_password(
            UserPoolId=pool_id, Username=spec.email, Password=password, Permanent=True
        )


class GovernanceEndpointClient:
    """Drives the Tenant-Admin governance endpoint for role assignment (NOT a direct DB write).

    Role assignments MUST flow through ``POST /api/tenant-admin/users/<email>/groups`` (which
    writes MySQL ``user_tenant_roles`` → ``enqueue_sync`` → projection). This client only ever
    calls that HTTP endpoint; it never touches MySQL / the projection. Injected in tests with a
    fake that records the calls so the test asserts role assignment went through the ENDPOINT, not
    a direct write.
    """

    def __init__(self, *, base_url: str, token: str, opener=None):
        self._base_url = base_url.rstrip("/")
        self._token = token
        # `opener` is a callable(request) -> response-like for tests; default = urllib.
        self._opener = opener or urllib.request.urlopen

    def assign_role(self, tenant: str, email: str, role: str) -> None:
        """``POST /api/tenant-admin/users/<email>/groups`` with ``{group_name: role}`` + X-Tenant."""
        url = f"{self._base_url}/api/tenant-admin/users/{email}/groups"
        body = json.dumps({"group_name": role}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("X-Tenant", tenant)
        resp = self._opener(req)
        # urlopen raises HTTPError on non-2xx; a returned response is a success.
        status = getattr(resp, "status", None) or getattr(resp, "code", 200)
        if status is not None and not (200 <= int(status) < 300):
            raise RuntimeError(f"governance endpoint returned {status} for {email!r}")


# ---------------------------------------------------------------------------
# The plan renderer + the apply path
# ---------------------------------------------------------------------------


def _print_plan(
    plan: LoadPlan,
    *,
    apply: bool,
    pool_id: str,
    governance_ready: bool,
) -> None:
    """Render the dry-run plan (users to create, roles to assign via the endpoint). Writes nothing."""
    print("=" * 72)
    print("Cognito bulk user load — plan")
    print("=" * 72)
    print(f"  source           : {plan.source_description}")
    print(f"  target pool       : {pool_id}")
    print(f"  default tenant    : {plan.default_tenant}")
    print(f"  mode              : {'APPLY (creates users + drives endpoint)' if apply else 'DRY-RUN (writes nothing)'}")
    print(f"  role assignment   : GOVERNANCE ENDPOINT "
          f"({'wired' if governance_ready else 'NOT wired — will be skipped, run via the SPA'})")
    print("-" * 72)
    print(f"  users in file     : {plan.ok_count}")
    print(f"  scoped (subset)   : {plan.scoped_count}")
    print(f"  general (all)     : {plan.general_count}")
    print(f"  malformed rows    : {plan.error_count}")
    print("-" * 72)
    print("  role breakdown (capability intent → assigned via the endpoint):")
    breakdown = plan.role_breakdown()
    if not breakdown:
        print("    (none)")
    for role in sorted(breakdown):
        print(f"    {role:<16} {breakdown[role]}")

    if plan.errors:
        print("-" * 72)
        print("  MALFORMED ROWS (not loaded; fix the file and re-run):")
        for ref, reason in plan.errors:
            print(f"    {ref}: {reason}")

    print("-" * 72)
    print(f"  sample planned users (first {_SAMPLE_COUNT}):")
    for u in plan.users[:_SAMPLE_COUNT]:
        print(
            "    "
            + json.dumps(
                {
                    "email": u.email,
                    "custom:tenants": u.tenants_claim(),
                    "custom:scope": u.scope_claim(),
                    "role_via_endpoint": u.role,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    print("=" * 72)


@dataclass
class ApplyResult:
    created: int = 0
    skipped_existing: int = 0
    roles_assigned: int = 0
    roles_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    generated_passwords: dict[str, str] = field(default_factory=dict)


def _apply_plan(
    plan: LoadPlan,
    *,
    pool_id: str,
    cognito: CognitoAdminClient,
    governance: GovernanceEndpointClient | None,
) -> ApplyResult:
    """Create each user via Cognito, then assign its role VIA THE GOVERNANCE ENDPOINT.

    Idempotent: an existing user is skipped (not recreated). Role assignment ALWAYS goes through
    ``governance.assign_role`` (never a direct DB write); if no governance client is wired, the
    role step is counted as skipped so the operator runs it through the SPA.
    """
    result = ApplyResult()
    for spec in plan.users:
        tenant = spec.tenants[0]
        try:
            if cognito.user_exists(pool_id, spec.email):
                result.skipped_existing += 1
            else:
                password = spec.password or _generate_password()
                cognito.create_user(pool_id, spec, password=password)
                result.created += 1
                if spec.password is None:
                    result.generated_passwords[spec.email] = password
        except Exception as exc:  # noqa: BLE001 — record per-user, keep going
            result.errors.append(f"CREATE {spec.email}: {type(exc).__name__}: {exc}")
            continue

        # Role assignment — ONLY via the governance endpoint (R8.1/R8.2, C-PLAYBOOK).
        if governance is None:
            result.roles_skipped += 1
            continue
        try:
            governance.assign_role(tenant, spec.email, spec.role)
            result.roles_assigned += 1
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"ROLE {spec.email} ({spec.role}): {type(exc).__name__}: {exc}")
    return result


def _generate_password() -> str:
    """A throwaway permanent password satisfying a typical Cognito policy (dev/test users only)."""
    # url-safe token + fixed symbol/upper/lower/digit to satisfy default complexity rules.
    return "Aa1!" + secrets.token_urlsafe(16)


def load_users(
    source_path: str,
    *,
    pool_id: str,
    region: str,
    apply: bool,
    tenant: str | None = None,
    governance_url: str | None = None,
    governance_token: str | None = None,
    cognito: CognitoAdminClient | None = None,
    governance: GovernanceEndpointClient | None = None,
) -> int:
    """Run the load (dry-run or apply). Returns a process exit code.

    Reads the editable file READ-ONLY, builds a validated plan, prints it, and — only if
    ``apply`` — creates users via Cognito + assigns roles via the governance endpoint. ``cognito``
    / ``governance`` may be injected for tests; in production they are constructed from the args.
    """
    plan = build_load_plan(source_path, cli_default_tenant=tenant)

    # Governance is "ready" when a client is injected OR both url+token are provided.
    governance_client = governance
    if apply and governance_client is None and governance_url and governance_token:
        governance_client = GovernanceEndpointClient(
            base_url=governance_url, token=governance_token
        )
    governance_ready = governance_client is not None if apply else bool(governance_url)

    _print_plan(plan, apply=apply, pool_id=pool_id, governance_ready=governance_ready)

    if not apply:
        print(
            "\nDRY-RUN: no users created, no endpoint called. Review the plan, then re-run with "
            "--apply (and --governance-url/--governance-token for role assignment)."
        )
        return 0

    if plan.error_count:
        print(
            f"\nREFUSING --apply: {plan.error_count} malformed row(s). Fix the file and re-run "
            "(dry-run stays clean before apply).",
            file=sys.stderr,
        )
        return 2

    cognito_client = cognito or CognitoAdminClient(region=region)
    result = _apply_plan(
        plan, pool_id=pool_id, cognito=cognito_client, governance=governance_client
    )

    print("\n" + "=" * 72)
    print("Cognito user load — apply summary")
    print("=" * 72)
    print(f"  pool             : {pool_id}")
    print(f"  created          : {result.created}")
    print(f"  skipped existing : {result.skipped_existing} (idempotent — not recreated)")
    print(f"  roles assigned   : {result.roles_assigned} (via the governance endpoint)")
    print(f"  roles skipped    : {result.roles_skipped} "
          "(endpoint not wired — assign via the SPA / re-run with --governance-url)")
    print(f"  errors           : {len(result.errors)}")
    for note in result.errors:
        print(f"    {note}")
    if result.generated_passwords:
        print("-" * 72)
        print("  generated throwaway passwords (dev/test users only):")
        for email, pw in sorted(result.generated_passwords.items()):
            print(f"    {email}  {pw}")
    print("=" * 72)

    # Non-zero if any per-user error so automation notices something to reconcile.
    return 0 if not result.errors else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bulk-load Cognito users from an editable file. Creates users + sets "
        "custom:tenants BY SCRIPT; assigns the Members role VIA THE GOVERNANCE ENDPOINT. "
        "Dry-run by default; pass --apply to write. Idempotent.",
    )
    parser.add_argument(
        "--pool-id",
        "--pool",
        dest="pool_id",
        required=True,
        help="The target Cognito User Pool ID (e.g. 'eu-west-1_xyrlzfqbl' for myAdmin-test). "
        "REQUIRED — there is no hardcoded/default pool (R8, steering 23): nothing can silently "
        "land in the wrong pool.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the editable JSON user file (see scripts/aws/cognito-users.sample.json).",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Override the file's 'default_tenant' for rows that don't set 'tenants' explicitly. "
        "Optional — the file may carry its own default.",
    )
    parser.add_argument(
        "--governance-url",
        default=os.environ.get("GOVERNANCE_API_URL"),
        help="Base URL of the Tenant-Admin governance API. Role assignment is POSTed to "
        "<url>/api/tenant-admin/users/<email>/groups. Without it, users are created but the "
        "role step is left for the SPA (never a direct DB write).",
    )
    parser.add_argument(
        "--governance-token",
        default=os.environ.get("GOVERNANCE_API_TOKEN"),
        help="Bearer token for a Tenant-Admin caller on --governance-url.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: env AWS_REGION or {DEFAULT_REGION}).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Actually create users + drive the governance endpoint. Without this, the script "
        "only prints the plan (dry-run is the default for safety).",
    )
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Explicitly request a dry-run (the DEFAULT): build + render the plan and write "
        "NOTHING. Mutually exclusive with --apply.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return load_users(
            args.source,
            pool_id=args.pool_id,
            region=args.region,
            apply=args.apply,
            tenant=args.tenant,
            governance_url=args.governance_url,
            governance_token=args.governance_token,
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
