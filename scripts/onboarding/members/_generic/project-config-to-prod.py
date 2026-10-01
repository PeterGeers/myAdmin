#!/usr/bin/env python3
"""project-config-to-prod.py — one-command runner: seed a tenant's members CONFIG
into MySQL, then project the governance subset to DynamoDB, with three safeties.

This is the single safe runner for the two-step rollout "author members-config →
run the governance projection" (the scripted form of the h-dcn one-off we validated,
t54_project_hdcn_to_real.py). It calls ``seed()`` from ``seed-hdcn-members-config.py``
to upsert the ``members.*`` config params, then drives the REAL
``ProjectionSync`` (the sole writer of the projection table).

CROSS-ENVIRONMENT PATH (confirmed intent — do not "fix"):

    READ side  = Railway prod MySQL (via RAILWAY_DB_* → DB_*);
    WRITE side = prod DynamoDB governance_projection (nonprofit-deploy 506221081911,
                 eu-west-1).

This cross-environment path mirrors the one-off we validated; the in-account
alternative is the Tenant-Admin UI / deployed backend enqueue_sync path. We take
it here because the governance SoR lives in Railway prod MySQL while the module
plane reads the prod DynamoDB projection in the data account — there is no
in-account MySQL to project from. Hence ``--db railway`` is the DEFAULT.

────────────────────────────────────────────────────────────────────────────
THE THREE BAKED-IN SAFETIES (why each exists)
────────────────────────────────────────────────────────────────────────────

1. ``_restrip_aws_env(profile, region)`` — the load_dotenv credential-clobber fix.
   ``backend/src/database.py`` calls ``load_dotenv()`` at IMPORT time, which
   re-injects the repo ``.env`` STATIC personal-account ``AWS_ACCESS_KEY_ID`` /
   ``AWS_SECRET_ACCESS_KEY`` plus ``AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000``.
   boto3's credential chain ranks static ENV keys ABOVE ``AWS_PROFILE``, so without
   this fix a DynamoDB client silently resolves the WRONG account (personal
   344561557829) or the LOCAL emulator → ``ResourceNotFoundException`` on prod
   tables that only exist in nonprofit-deploy. The helper POPS
   ``AWS_ENDPOINT_URL_DYNAMODB`` / ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``
   / ``AWS_SESSION_TOKEN`` and RE-SETS ``AWS_PROFILE`` + ``AWS_REGION``. It MUST be
   called AFTER importing any database-dependent module (so that module's
   ``load_dotenv`` has already run and injected the keys) and BEFORE constructing
   any boto3 client. Strict apply order: map Railway DB_* → import
   database-dependent modules → ``_restrip_aws_env`` → STS account guard →
   build/run sync.

2. Version-guard tenant bump. ``ProjectionSync`` writes a ``config#*`` row only
   when its version STRICTLY supersedes the stored one; ``_scope_config_version``
   derives the version from the TENANT ROW's ``updated_at``/``version``/``revision``,
   NOT from the parameter. So merely re-authoring the param is a no-op projection.
   After seeding, this runner bumps the tenant row on the SAME DB before syncing:
   a parameterized ``UPDATE tenants SET updated_at = CURRENT_TIMESTAMP WHERE
   administration = %s`` (steering 31 — ``%s`` placeholders, never f-string). This
   subtlety is documented in ``.kiro/specs/myBacklog/backlog.md``.

3. Account guard. Before ANY DynamoDB write, resolve
   ``boto3.client("sts").get_caller_identity()["Account"]`` and REQUIRE it equals
   ``--expected-account`` (default 506221081911) — else ``SystemExit`` naming the
   resolved vs expected account. Belt-and-suspenders over safety #1: even if the
   env strip somehow failed, we refuse to write to the wrong account.

DRY-RUN is the DEFAULT and touches NO AWS at all (no boto3, no account guard), so
it runs anywhere; ``--apply`` performs the writes.

Usage:
  # Dry-run (DEFAULT — reads Railway read-only to show the param diff, no writes):
  python scripts/onboarding/members/_generic/project-config-to-prod.py --tenant h-dcn

  # Apply (seed → bump tenant → account guard → sync → read-back verify):
  python scripts/onboarding/members/_generic/project-config-to-prod.py --tenant h-dcn --apply
"""

from __future__ import annotations

import argparse
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# Bootstrap: find the repo root by walking up to a marker (NOT by counting dirname levels —
# Tenant-Onboarding Tooling R4), put it on sys.path, then hand off to the shared onboarding
# `_lib` for repo-root + backend/src setup.
_r = os.path.abspath(__file__)
while _r != os.path.dirname(_r):
    _r = os.path.dirname(_r)
    if os.path.isdir(os.path.join(_r, ".git")) or os.path.isdir(os.path.join(_r, ".kiro")):
        break
if _r not in sys.path:
    sys.path.insert(0, _r)
from scripts.onboarding._lib.paths import (  # noqa: E402
    ensure_backend_src_on_path,
    import_by_path,
    repo_root,
)

ensure_backend_src_on_path()
_REPO_ROOT = repo_root()

#: Repo-root .env — parsed by hand for RAILWAY_DB_* only (never re-sourced whole,
#: so we don't re-inject the personal-account AWS keys; _restrip_aws_env also
#: covers that).
_ENV_PATH = os.path.join(_REPO_ROOT, ".env")

#: DynamoDB endpoint / static-credential env vars that the repo .env injects and
#: that must be stripped so AWS_PROFILE resolves (safety #1).
_AWS_CLOBBER_VARS = (
    "AWS_ENDPOINT_URL_DYNAMODB",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)


def _load_seed_module(tenant: str = "h-dcn"):
    """Import the tenant's seed-*-members-config.py by path (dashed filename).

    This generic runner reuses the TENANT's seed step rather than re-implementing param
    authoring. The seed script lives in the tenant's config dir
    (``../<tenant>/seed-hdcn-members-config.py``) — the generic runners sit under ``_generic/``;
    each tenant's committed config + seed tool sits under ``<tenant>/``. Loaded by file path via
    the shared `_lib` ``import_by_path`` (dashes make the filename a non-importable module name).
    """
    path = os.path.join(
        _THIS_DIR, os.pardir, tenant, "seed-hdcn-members-config.py"
    )
    return import_by_path("seed_hdcn_members_config", os.path.abspath(path))


def _parse_env_file(path: str) -> dict[str, str]:
    """Parse a ``.env`` file into a dict (no shell, no re-injection of other vars).

    Reads lines, skips blank / ``#`` comment lines, splits on the FIRST ``=`` and
    strips a single layer of surrounding single/double quotes. We parse it
    ourselves (rather than ``load_dotenv``) so we can lift ONLY the ``RAILWAY_DB_*``
    keys without re-injecting the personal-account AWS keys the file also carries.
    """
    values: dict[str, str] = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key:
                values[key] = value
    return values


def _map_railway_db_env() -> None:
    """Point DB_* at Railway prod MySQL from the repo-root .env RAILWAY_DB_* keys.

    Parses only the ``RAILWAY_DB_*`` keys (never re-sources the whole .env — that
    would re-inject the personal-account AWS keys) and maps them onto the ``DB_*``
    vars ``DatabaseManager`` reads. MUST run BEFORE importing ``database`` so its
    import-time config picks these up. Never prints ``DB_PASSWORD``.

    Mapping (with safe defaults mirroring the railway-db.sh wrapper):
        DB_HOST     ← RAILWAY_DB_HOST
        DB_PORT     ← RAILWAY_DB_PORT      (default "3306")
        DB_USER     ← RAILWAY_DB_USER      (default "root")
        DB_PASSWORD ← RAILWAY_DB_PASSWORD
        DB_NAME     ← RAILWAY_DB_NAME      (default "finance")
        TEST_MODE   = "false"
    """
    env = _parse_env_file(_ENV_PATH)
    host = env.get("RAILWAY_DB_HOST")
    if not host:
        raise SystemExit(
            "RAILWAY_DB_HOST not found in repo-root .env — cannot target Railway "
            "prod MySQL. (Railway can rotate the proxy host/port; refresh RAILWAY_DB_* "
            "in .env.) Use --db local to target local Docker instead."
        )
    os.environ["DB_HOST"] = host
    os.environ["DB_PORT"] = env.get("RAILWAY_DB_PORT", "3306")
    os.environ["DB_USER"] = env.get("RAILWAY_DB_USER", "root")
    os.environ["DB_PASSWORD"] = env.get("RAILWAY_DB_PASSWORD", "")
    os.environ["DB_NAME"] = env.get("RAILWAY_DB_NAME", "finance")
    os.environ["TEST_MODE"] = "false"
    # NB: DB_PASSWORD deliberately NOT printed.
    print(
        f"[db] Railway prod MySQL → host={host} port={os.environ['DB_PORT']} "
        f"user={os.environ['DB_USER']} db={os.environ['DB_NAME']}"
    )


def _restrip_aws_env(profile: str, region: str) -> None:
    """SAFETY #1 — undo the load_dotenv AWS credential clobber before any boto3 call.

    A database-dependent import (``database``) runs ``load_dotenv()`` at import
    time, re-injecting the repo .env static personal-account keys +
    ``AWS_ENDPOINT_URL_DYNAMODB``. boto3 ranks those ENV creds ABOVE ``AWS_PROFILE``,
    so left in place a client resolves the WRONG account / the local emulator. Pop
    them and pin ``AWS_PROFILE`` + ``AWS_REGION`` so the profile resolves cleanly.

    MUST be called AFTER importing the database-dependent modules (so their
    load_dotenv already ran) and BEFORE constructing any boto3 client.
    """
    for var in _AWS_CLOBBER_VARS:
        os.environ.pop(var, None)
    os.environ["AWS_PROFILE"] = profile
    os.environ["AWS_REGION"] = region
    print(
        f"[aws] stripped static-cred/endpoint env; pinned AWS_PROFILE={profile} "
        f"AWS_REGION={region}"
    )


def _assert_account(expected_account: str, region: str) -> None:
    """SAFETY #3 — refuse to write unless STS resolves the expected account.

    Resolve ``get_caller_identity().Account`` and require it equals
    ``expected_account`` (default the data account 506221081911), else SystemExit
    naming resolved vs expected. Called AFTER _restrip_aws_env, BEFORE any write.
    """
    import boto3  # local import: dry-run must not touch boto3 at all

    identity = boto3.client("sts", region_name=region).get_caller_identity()
    resolved = identity["Account"]
    print(f"[aws] STS account = {resolved}  arn={identity.get('Arn')}")
    if resolved != expected_account:
        raise SystemExit(
            f"ACCOUNT GUARD: refusing to write — resolved account {resolved} is NOT "
            f"the expected account {expected_account}. (Check AWS_PROFILE / that the "
            f"personal-account env keys were stripped.)"
        )


def _bump_tenant_updated_at(db, tenant: str) -> None:
    """SAFETY #2 — bump the tenant row so the config#* version strictly supersedes.

    ``ProjectionSync`` derives the ``config#*`` row version from the TENANT ROW's
    ``updated_at``/``version``/``revision`` (``_scope_config_version``), NOT from
    the param — so without this bump a re-authored param projects as a no-op.
    Parameterized ``%s`` (steering 31), on the SAME db used for seed + source read.
    """
    sql = "UPDATE tenants SET updated_at = CURRENT_TIMESTAMP WHERE administration = %s"
    db.execute_query(sql, (tenant,), fetch=False, commit=True)
    print(f"[bump] tenants.updated_at bumped for administration={tenant!r} "
          f"(version-guard so config#* supersedes the stored row)")


def _run_dry_run(args) -> int:
    """DRY-RUN (default): show the param diff + what WOULD happen. Touch NO AWS.

    For --db railway this still connects to Railway read-only to show the diff
    (read-only is fine). No boto3, no account guard — so dry-run runs anywhere.
    """
    if args.db == "railway":
        _map_railway_db_env()
    else:
        print("[db] local Docker MySQL (DB_* from .env, unchanged)")

    # Imported lazily, AFTER the Railway env mapping, so module-top stays
    # DB/AWS-free (so --help is side-effect-free).
    from database import DatabaseManager
    from services.parameter_service import ParameterService

    seed_module = _load_seed_module(args.tenant)
    db = DatabaseManager(test_mode=args.test_mode)
    svc = ParameterService(db)

    print("=" * 68)
    print(f"DRY-RUN — tenant={args.tenant!r}  db={args.db}  test_mode={args.test_mode}")
    print(f"projection table (would be): {args.projection_table}")
    print("=" * 68)

    rc = seed_module.seed(
        args.tenant, apply=False, config_path=args.config, svc=svc
    )
    if rc != 0:
        return rc

    print("-" * 68)
    print("DRY-RUN: no writes made. On --apply this runner WOULD:")
    print(f"  1. seed() the members.* config params for {args.tenant!r}")
    print("  2. bump tenants.updated_at (version-guard so config#* supersedes)")
    print(f"  3. strip personal AWS env + guard STS == {args.expected_account}")
    print(f"  4. run ProjectionSync → DynamoDB table {args.projection_table!r}")
    print("  5. read back config#fields and print version + field keys")
    print("Re-run with --apply to perform the writes.")
    return 0


def _run_apply(args) -> int:
    """APPLY: seed → bump → strip+guard → sync → read-back verify. Fail loudly."""
    # (a) point DB_* at the chosen source BEFORE importing database.
    if args.db == "railway":
        _map_railway_db_env()
    else:
        print("[db] local Docker MySQL (DB_* from .env, unchanged)")

    # Set the projection table target BEFORE resolving it. The schema module reads
    # GOVERNANCE_PROJECTION_TABLE (fail-fast) at resolve time.
    os.environ["GOVERNANCE_PROJECTION_TABLE"] = args.projection_table

    # Import database-dependent modules (their load_dotenv runs here) lazily, AFTER
    # the Railway env mapping and BEFORE _restrip_aws_env.
    from database import DatabaseManager
    from services.parameter_service import ParameterService
    from services.projection_sync import DatabaseSourceProvider, ProjectionSync
    from services import projection_schema as pschema

    seed_module = _load_seed_module(args.tenant)

    # ONE DatabaseManager / ONE connection target for seed + bump + source read.
    db = DatabaseManager(test_mode=args.test_mode)
    svc = ParameterService(db)

    print("=" * 68)
    print(f"APPLY — tenant={args.tenant!r}  db={args.db}  test_mode={args.test_mode}")
    print("=" * 68)

    # (a) seed the config params.
    rc = seed_module.seed(args.tenant, apply=True, config_path=args.config, svc=svc)
    if rc != 0:
        raise SystemExit(f"seed() failed (rc={rc}) — aborting before bump/sync.")

    # (b) version-guard bump (SAFETY #2) on the SAME db.
    _bump_tenant_updated_at(db, args.tenant)

    # (c) strip personal AWS env (SAFETY #1) then STS account guard (SAFETY #3).
    _restrip_aws_env(args.aws_profile, args.region)
    _assert_account(args.expected_account, args.region)

    # (d) run the sync via the REAL ProjectionSync (sole writer), reusing db.
    table_name = pschema.resolve_projection_table_name()
    print(f"[sync] projection target table = {table_name}")
    sync = ProjectionSync(
        DatabaseSourceProvider(db), parameter_service=ParameterService(db)
    )
    result = sync.sync_administration(args.tenant)
    print(
        f"[sync] sync_administration({args.tenant!r}) -> written={result.written} "
        f"skipped={result.skipped} deleted={result.deleted} "
        f"administrations={result.administrations}"
    )
    if result.written == 0:
        if result.skipped > 0:
            print(
                "!!! WARNING: written==0 with skipped>0 — the version bump may NOT "
                "have taken (config#* did not supersede the stored row). Verify "
                "tenants.updated_at advanced for this tenant and re-run.",
                file=sys.stderr,
            )
        raise SystemExit(
            "sync wrote ZERO rows — refusing to report success. See the warning above."
        )

    # (e) read-back verify: config#fields version + field count + sorted field keys.
    table = pschema.get_projection_table_resource()
    key = pschema.build_key(args.tenant, "config#fields")
    item = table.get_item(Key=key).get("Item")
    print("-" * 68)
    if not item:
        print(
            f"[verify] WARNING: no config#fields row read back for {args.tenant!r} "
            f"at {key!r}.",
            file=sys.stderr,
        )
    else:
        version = item.get("version")
        fields = item.get("fields") or {}
        field_keys = sorted(fields.keys()) if isinstance(fields, dict) else []
        print(f"[verify] config#fields version = {version}")
        print(f"[verify] config#fields field count = {len(field_keys)}")
        print(f"[verify] config#fields field keys = {field_keys}")
    print("APPLIED: seed + version bump + projection sync complete.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-command runner: seed a tenant's members config into MySQL, "
        "then project the governance subset to DynamoDB. READS Railway prod MySQL, "
        "WRITES prod DynamoDB governance_projection (nonprofit-deploy 506221081911). "
        "Dry-run by default; --apply to perform writes.",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="The administration (tenant) to seed + project (e.g. 'h-dcn'). "
        "REQUIRED — no hardcoded/default tenant (steering 31).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the members-config JSON (default: seed() falls back to "
        "scripts/onboarding/members/h-dcn/members_config.json).",
    )
    parser.add_argument(
        "--db",
        choices=("railway", "local"),
        default="railway",
        help="Which MySQL to READ from. 'railway' (DEFAULT) maps RAILWAY_DB_* → DB_* "
        "(Railway prod MySQL); 'local' leaves DB_* as the .env local Docker config.",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Use TEST_MODE/testfinance and default the projection table to "
        "test_governance_projection.",
    )
    parser.add_argument(
        "--expected-account",
        default="506221081911",
        help="The AWS account the STS account guard must resolve before any write "
        "(default: data account 506221081911).",
    )
    parser.add_argument(
        "--region",
        default="eu-west-1",
        help="AWS region for the projection table / STS (default: eu-west-1).",
    )
    parser.add_argument(
        "--aws-profile",
        default="nonprofit-deploy",
        help="AWS profile pinned after stripping the personal-account env keys "
        "(default: nonprofit-deploy).",
    )
    parser.add_argument(
        "--projection-table",
        default=None,
        help="DynamoDB projection table name (default: governance_projection, or "
        "test_governance_projection with --test-mode). Set into "
        "GOVERNANCE_PROJECTION_TABLE before the table is resolved.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the writes (seed + bump + sync). Without this the "
        "script runs a dry-run (the default for safety) and touches NO AWS.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly request a dry-run (this is already the default). Ignored "
        "when --apply is given.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Default the projection table per --test-mode when not explicitly given.
    if args.projection_table is None:
        args.projection_table = (
            "test_governance_projection" if args.test_mode else "governance_projection"
        )

    try:
        if args.apply:
            return _run_apply(args)
        return _run_dry_run(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
