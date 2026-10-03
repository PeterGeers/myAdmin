#!/usr/bin/env python3
"""provision-test-account.py — Test_Account provisioning (test-environment spec, Req 17).

A documented, repeatable replacement for one-off AWS CLI commands when creating and
seeding a TEST user. It targets the Identity_Account's TEST Cognito pool
(`myAdmin-test`, `eu-west-1_xyrlzfqbl`, personal account 344561557829 — Req 17.5)
and:

  * creates the user in the test pool if absent (Req 17.1);
  * sets a PERMANENT password so there is NO forced-change trap on first sign-in
    (`admin_set_user_password(..., Permanent=True)`, which clears the
    `FORCE_CHANGE_PASSWORD` status — Req 17.2);
  * seeds `custom:tenants` / `custom:role` to a SPECIFIED realistic shape chosen
    for the test — which MAY be any valid tenant/role configuration, including one
    that does not exist in production (Req 17.3).

Prod-mirror is a SEPARATE, opt-in capability (Req 17.4): to make a Test_Account
mirror a production reference account's attributes, use the Copy_Utility
(`copy-prod-to-test.py cognito --email ...`) as an explicit, human-initiated step.
This provisioner does NOT read production by default — it seeds the shape you give
it. (`--mirror-prod EMAIL` is a convenience that simply tells you to run the
Copy_Utility; it never silently reaches into prod here.)

Folder standard (scripts/onboarding/README.md): lives under scripts/test-environment/,
bootstraps via the shared `_lib.paths` marker walk, is dry-run-first, and is
documented in the folder README.

Safety (Req 17.6 / 19.1): PUBLIC pool id only; NO real credentials or secrets in
the repo. The `--password` supplied on `--apply` is a throwaway TEST password; the
script NEVER generates, prints, or stores a password (no clear-text secret handling).

Usage (from repo root, WSL) — dry-run is the default, prints the plan only:

  # Preview provisioning a test user with a chosen tenant/role shape:
  backend/.venv/bin/python scripts/test-environment/provision-test-account.py \\
      --email tester@example.org --tenants TenantA --role Admin

  # Actually provision into the TEST pool (identity account):
  AWS_PROFILE=personal AWS_REGION=eu-west-1 \\
      backend/.venv/bin/python scripts/test-environment/provision-test-account.py \\
      --email tester@example.org --tenants TenantA,TenantB --role Member --apply

  # Mirror a prod reference account's attributes (explicit, via the Copy_Utility):
  backend/.venv/bin/python scripts/test-environment/provision-test-account.py \\
      --email tester@example.org --mirror-prod reference.user@example.org
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

# Bootstrap: find the repo root by walking up to a marker, then hand off to the
# shared onboarding `_lib` for repo-root + backend/src setup (scripts/onboarding/
# README.md "Robust paths (R4)").
_r = os.path.abspath(__file__)
while _r != os.path.dirname(_r):
    _r = os.path.dirname(_r)
    if os.path.isdir(os.path.join(_r, ".git")) or os.path.isdir(os.path.join(_r, ".kiro")):
        break
if _r not in sys.path:
    sys.path.insert(0, _r)
from scripts.onboarding._lib.paths import ensure_backend_src_on_path  # noqa: E402

ensure_backend_src_on_path()

#: PUBLIC, non-secret TEST pool id in the Identity_Account (23-aws-accounts.md,
#: Req 17.5). This provisioner writes the TEST pool ONLY — there is no prod pool
#: reference here (prod-mirror goes through the Copy_Utility).
TEST_POOL_ID = "eu-west-1_xyrlzfqbl"  # myAdmin-test (personal account 344561557829)

DEFAULT_REGION = "eu-west-1"


class ProvisioningError(ValueError):
    """The requested Test_Account shape is invalid (bad email / empty tenants / …)."""


class NotTestPoolError(RuntimeError):
    """The target pool is not the TEST pool.

    Defense in depth: this provisioner writes the TEST pool ONLY (Req 17.5). A
    target that is not the test pool aborts before any write.
    """


# ---------------------------------------------------------------------------
# The desired account shape (pure data) + rendering to Cognito attributes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountShape:
    """The realistic `custom:tenants`/`custom:role` shape to seed (Req 17.3).

    MAY be any valid configuration, including one with no production counterpart.
    """

    email: str
    tenants: list[str]
    role: str
    scope: str = "*"  # "*" = all; otherwise a specific scope value for the test

    def tenants_claim(self) -> str:
        """Render `custom:tenants` per the PreTokenGen reader's shape rules.

        A single tenant is a scalar string (read as ONE tenant); many tenants are
        a JSON array string `["A","B"]` (read as MANY). Mirrors
        `auth.cognito_utils._normalize_tenants_claim` and the load-cognito-users
        runner so the TEST user's claim parses identically to a real one.
        """
        if len(self.tenants) == 1:
            return self.tenants[0]
        return json.dumps(self.tenants, ensure_ascii=False)

    def cognito_attributes(self) -> list[dict[str, str]]:
        """The non-secret user attributes to set on the TEST user."""
        return [
            {"Name": "email", "Value": self.email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "custom:tenants", "Value": self.tenants_claim()},
            {"Name": "custom:role", "Value": self.role},
            {"Name": "custom:scope", "Value": self.scope},
        ]


def build_account_shape(
    email: str, tenants: list[str], role: str, scope: str = "*"
) -> AccountShape:
    """Validate + build an :class:`AccountShape` (loud on bad input)."""
    email = (email or "").strip()
    if not email or "@" not in email:
        raise ProvisioningError(f"a valid --email is required, got {email!r}")
    tenants = [t.strip() for t in tenants if t and t.strip()]
    if not tenants:
        raise ProvisioningError("at least one --tenants value is required")
    role = (role or "").strip()
    if not role:
        raise ProvisioningError("a --role is required")
    return AccountShape(email=email, tenants=tenants, role=role, scope=(scope or "*").strip())


# ---------------------------------------------------------------------------
# Cognito admin client (the single Cognito touch-point) — injectable for tests
# ---------------------------------------------------------------------------


class CognitoAdminClient:
    """Thin wrapper over boto3 ``cognito-idp`` for TEST-pool provisioning.

    Mirrors the onboarding ``load-cognito-users`` client. Injected in tests with an
    in-memory fake so no live pool is touched.
    """

    def __init__(self, *, region: str, pool_id: str, client=None):
        # Defense in depth: refuse any pool that is not the TEST pool.
        if pool_id != TEST_POOL_ID:
            raise NotTestPoolError(
                f"target pool {pool_id!r} is not the TEST pool ({TEST_POOL_ID}); this "
                "provisioner writes the TEST pool ONLY (Req 17.5)."
            )
        self._pool_id = pool_id
        if client is not None:
            self._client = client
        else:
            import boto3  # lazy — only when actually applying

            self._client = boto3.client("cognito-idp", region_name=region)

    def user_exists(self, email: str) -> bool:
        try:
            self._client.admin_get_user(UserPoolId=self._pool_id, Username=email)
            return True
        except self._client.exceptions.UserNotFoundException:
            return False

    def create_user(self, shape: AccountShape) -> None:
        """``admin_create_user`` with the shape's attributes, no invite email."""
        self._client.admin_create_user(
            UserPoolId=self._pool_id,
            Username=shape.email,
            UserAttributes=shape.cognito_attributes(),
            MessageAction="SUPPRESS",  # throwaway TEST user — no invite email
        )

    def update_attributes(self, shape: AccountShape) -> None:
        """``admin_update_user_attributes`` to (re)seed the shape on an existing user."""
        self._client.admin_update_user_attributes(
            UserPoolId=self._pool_id,
            Username=shape.email,
            UserAttributes=shape.cognito_attributes(),
        )

    def set_permanent_password(self, email: str, password: str) -> None:
        """Set a PERMANENT password — clears FORCE_CHANGE_PASSWORD (no forced-change trap)."""
        self._client.admin_set_user_password(
            UserPoolId=self._pool_id, Username=email, Password=password, Permanent=True
        )


@dataclass
class ProvisionResult:
    email: str
    shape: AccountShape
    created: bool = False
    applied: bool = False
    notes: list[str] = field(default_factory=list)


def provision_test_account(
    shape: AccountShape,
    *,
    region: str,
    apply: bool,
    password: str | None = None,
    pool_id: str = TEST_POOL_ID,
    client: CognitoAdminClient | None = None,
) -> ProvisionResult:
    """Create (if absent) + seed + set a permanent password for a TEST account.

    Dry-run (default) prints the plan and writes nothing. ``apply`` creates/updates
    the user in the TEST pool and sets a permanent password (no forced-change trap).
    Idempotent: an existing user is updated in place, not recreated.
    """
    cognito = client or CognitoAdminClient(region=region, pool_id=pool_id)
    already = cognito.user_exists(shape.email)
    result = ProvisionResult(email=shape.email, shape=shape, created=not already)

    _print_plan(result, apply=apply, pool_id=pool_id)

    if not apply:
        return result

    # A password is REQUIRED on apply. We deliberately do NOT generate one: a
    # generated secret would be useless unless surfaced, and surfacing it (stdout,
    # a file) is clear-text secret handling. The operator supplies a known throwaway
    # TEST password via --password; this script NEVER logs, prints, or stores it.
    if not password:
        raise ProvisioningError(
            "--password is required with --apply. Supply a known throwaway TEST password "
            "(this script never generates, prints, or stores a password)."
        )

    if result.created:
        cognito.create_user(shape)
    else:
        cognito.update_attributes(shape)

    cognito.set_permanent_password(shape.email, password)
    result.applied = True

    print("\n" + "=" * 64)
    print("Provision summary")
    print("=" * 64)
    print(f"  pool    : {pool_id}")
    print(f"  user    : {shape.email} ({'created' if result.created else 'updated'})")
    print("  password: PERMANENT set from --password (no forced-change trap; not echoed)")
    print("=" * 64)
    return result


def _print_plan(result: ProvisionResult, *, apply: bool, pool_id: str) -> None:
    shape = result.shape
    print("=" * 64)
    print("Test_Account provisioning — plan")
    print("=" * 64)
    print(f"  pool          : {pool_id} (myAdmin-test, identity account)")
    print(f"  email         : {shape.email}")
    print(f"  user          : {'CREATE (absent)' if result.created else 'UPDATE (exists)'}")
    print(f"  custom:tenants: {shape.tenants_claim()}")
    print(f"  custom:role   : {shape.role}")
    print(f"  custom:scope  : {shape.scope}")
    print("  password      : PERMANENT (clears FORCE_CHANGE_PASSWORD — no forced-change trap)")
    print(f"  mode          : {'APPLY' if apply else 'DRY-RUN (writes nothing)'}")
    print("=" * 64)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _mirror_prod_instructions(mirror_email: str, test_email: str) -> str:
    """The explicit, human-initiated Copy_Utility command for prod-mirror (Req 17.4).

    Prod-mirror is NOT done here by default: it is an opt-in Copy_Utility step so
    reaching into production is always a deliberate, separate action.
    """
    return (
        "Prod-mirror is a separate, explicit Copy_Utility step (Req 17.4). To mirror the "
        f"production reference account {mirror_email!r} onto the TEST account {test_email!r}, "
        "run:\n\n"
        "  AWS_PROFILE=personal AWS_REGION=eu-west-1 \\\n"
        "    backend/.venv/bin/python scripts/test-environment/copy-prod-to-test.py cognito \\\n"
        f"      --email {mirror_email} --apply --i-understand-this-writes-test\n\n"
        "then re-run this provisioner (without --mirror-prod) if you also need a permanent "
        "password set on the TEST account."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision a TEST Cognito account (test pool, identity account): create if "
        "absent, set a PERMANENT password (no forced-change trap), seed custom:tenants/role to a "
        "chosen shape. Dry-run by default; pass --apply to write. Prod-mirror is a separate "
        "Copy_Utility step.",
    )
    parser.add_argument(
        "--email", required=True, help="The TEST account email (username) to provision."
    )
    parser.add_argument(
        "--tenants",
        default="",
        help="Comma-separated tenant name(s) for custom:tenants (a single value is written as a "
        "scalar; many as a JSON array). Required unless --mirror-prod is used.",
    )
    parser.add_argument(
        "--role", default="", help="custom:role value to seed. Required unless --mirror-prod."
    )
    parser.add_argument(
        "--scope",
        default="*",
        help="custom:scope value ('*' = all, the default; or a specific scope for the test).",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Permanent password for the TEST user (a throwaway TEST value). REQUIRED with "
        "--apply. The script never generates/prints/stores it.",
    )
    parser.add_argument(
        "--mirror-prod",
        default=None,
        metavar="PROD_EMAIL",
        help="Print the explicit Copy_Utility command to mirror a production reference account's "
        "attributes onto this TEST account (Req 17.4). Does NOT read production itself.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: env AWS_REGION or {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create/update the user + set the permanent password. Without this the "
        "script only prints the plan (dry-run is the default for safety).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Prod-mirror is informational + explicit: print the Copy_Utility command and exit
    # (never reach into prod from here — Req 17.4).
    if args.mirror_prod:
        print(_mirror_prod_instructions(args.mirror_prod, args.email))
        return 0

    try:
        shape = build_account_shape(
            args.email,
            [t for t in args.tenants.split(",")] if args.tenants else [],
            args.role,
            args.scope,
        )
        provision_test_account(
            shape,
            region=args.region,
            apply=args.apply,
            password=args.password,
        )
    except ProvisioningError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    except NotTestPoolError as exc:
        print(f"REFUSED (not the TEST pool): {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
