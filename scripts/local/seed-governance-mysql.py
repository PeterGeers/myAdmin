#!/usr/bin/env python3
"""seed-governance-mysql.py — seed throwaway tenant-governance fixtures into
Docker MySQL (the `finance` DB from docker-compose.yml) for S3 test-first work.

Part of the S3 spec (`s3-claims-and-projection`) Phase 1 / T2. It gives the
claim-contract validation, system-of-record checks, and the MySQL->DynamoDB
projection something reproducible to resolve against on the test environment —
Docker MySQL + the test Cognito pool + local DynamoDB — before any production
Pool A change.

What it seeds (all idempotent, all obviously-synthetic, all throwaway):

  1. `tenants` — a small set of fake tenants keyed `s3test_*`, including a
     SAM-backed-module tenant (`s3test_hdcn`) that will later enable
     members/events/webshop. These are NEVER real tenants.

  2. `tenant_modules` — one row per (tenant, module) with `is_active`, covering:
       - a Flask-module tenant (`s3test_fin` -> FIN),
       - a SAM-backed-module tenant (`s3test_hdcn` -> members/events/webshop),
       - an all-four-modules tenant (`s3test_full` -> FIN/STR/TENADMIN/ZZP).

  3. `user_tenant_roles` — one row per role/claim shape so role_cache.py
     resolution can be exercised across every capability class. This also
     includes an S4 **multi-tenant "size-budget" user** (`s4test-multi@example.com`)
     holding many role grants across several s3test_* tenants, so the S4 spec's
     resolver produces a realistically LARGE per-tenant entitlement map for the
     claim size-budget tests (S4 T5 / T10). All its grants reference existing
     s3test_* tenants (FK-safe) and it is removed by `--reset` along with them.

  4. A **GoodwinSolutions test user** `test-goodwin@example.com` with
     `user_tenant_roles` for `administration='GoodwinSolutions'` covering all
     four enabled modules — full-access set (Finance_CRUD, STR_CRUD, ZZP_CRUD,
     Tenant_Admin), mirroring the real full-access grant peter@pgeers.nl — plus
     read-only variants (Finance_Read, STR_Read, ZZP_Read) so allow/deny can be
     tested (e.g. a *_Read user can view but a create -> 403).

     This user is seeded under the EXISTING `GoodwinSolutions` tenant so the
     `user_tenant_roles.administration` FK to `tenants(administration)` is
     satisfied without inventing a tenant. No `GoodwinSolutions` tenant/module
     rows are created or modified — only this synthetic user's role rows.

Guardrails (workspace database-patterns + S3 R4.1):
  - All access via DatabaseManager; parameterized %s queries only.
  - Idempotent: re-running inserts nothing new (ON DUPLICATE KEY / existence
    checks). `--reset` removes ONLY this script's own synthetic rows first.
  - Throwaway: `--reset` and the seeded set are scoped to the `s3test_*`
    tenants and the `test-goodwin@example.com` user. It NEVER deletes or edits
    any other tenant, module, role, or user — no live governance data is
    touched.
  - Seeds the `finance` DB (test_mode=False -> DB_NAME=finance, the Docker
    MySQL default). Config comes from env (backend/.env), never hardcoded.

Usage (from repo root, WSL):
  backend/.venv/bin/python scripts/local/seed-governance-mysql.py [--reset]
      [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys

# Make the backend `src` importable so `from database import DatabaseManager`
# resolves the workspace DatabaseManager (database-patterns rule).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "src"))

from database import DatabaseManager  # noqa: E402

# --- Synthetic fixture definitions -----------------------------------------
# Every tenant name is prefixed `s3test_` so it is unmistakably throwaway and
# can be safely reset without risk to real data.

SEED_CREATED_BY = "s3-t2-seed"

# 1) Tenants (must exist before their tenant_modules / user_tenant_roles rows;
#    user_tenant_roles.administration has an FK to tenants.administration).
SEED_TENANTS = [
    # (administration, display_name)
    ("s3test_fin", "S3 Test — Finance-only tenant"),
    ("s3test_str", "S3 Test — Short-term rental tenant"),
    ("s3test_full", "S3 Test — All-four-modules tenant"),
    ("s3test_hdcn", "S3 Test — SAM-backed-module tenant (members/events/webshop)"),
]

# 2) Tenant modules — one row per (tenant, module). Covers a Flask-module
#    tenant, an all-four tenant, and a SAM-backed-module tenant. `is_active`
#    lets a disabled-module (module_required -> 403) case be exercised too.
SEED_TENANT_MODULES = [
    # (administration, module_name, is_active)
    ("s3test_fin", "FIN", True),
    ("s3test_str", "STR", True),
    ("s3test_full", "FIN", True),
    ("s3test_full", "STR", True),
    ("s3test_full", "TENADMIN", True),
    ("s3test_full", "ZZP", True),
    # SAM-backed-module tenant (e.g. h-dcn -> members/events/webshop). These
    # module names land as real modules in S5; seeded here so the projection's
    # SAM-backed-tenant path has data now.
    ("s3test_hdcn", "members", True),
    ("s3test_hdcn", "events", True),
    ("s3test_hdcn", "webshop", True),
    # A deliberately INACTIVE module, so an allow/deny (module disabled -> 403)
    # test has a target without touching an active one.
    ("s3test_hdcn", "FIN", False),
]

# 3) user_tenant_roles — one row per role/claim shape, so role_cache.py
#    resolution is exercised across every capability class. Synthetic users
#    at @example.com; synthetic tenants only.
SEED_TENANT_ROLES = [
    # (email, administration, role)
    # Full-CRUD shapes, one per module family:
    ("s3test-crud@example.com", "s3test_full", "Finance_CRUD"),
    ("s3test-crud@example.com", "s3test_full", "STR_CRUD"),
    ("s3test-crud@example.com", "s3test_full", "ZZP_CRUD"),
    ("s3test-crud@example.com", "s3test_full", "Tenant_Admin"),
    # Read-only shapes:
    ("s3test-read@example.com", "s3test_full", "Finance_Read"),
    ("s3test-read@example.com", "s3test_full", "STR_Read"),
    ("s3test-read@example.com", "s3test_full", "ZZP_Read"),
    # Export-only shapes:
    ("s3test-export@example.com", "s3test_full", "Finance_Export"),
    ("s3test-export@example.com", "s3test_full", "STR_Export"),
    ("s3test-export@example.com", "s3test_full", "ZZP_Export"),
    # A single-module tenant grant (FIN-only tenant):
    ("s3test-fin@example.com", "s3test_fin", "Finance_CRUD"),
]

# 3b) S4 multi-tenant "size-budget" user — a single synthetic user holding role
#    grants across SEVERAL of the s3test_* tenants and MANY capabilities, so the
#    S4 resolver (D1) produces a realistically LARGE per-tenant entitlement map.
#    This gives the D3 claim size-budget tests (S4 T5 / T10) a big, realistic
#    input to encode. FK-safe: every `administration` here is an EXISTING
#    s3test_* tenant seeded above; the email is obviously-synthetic (@example.com).
#    Roles are chosen to span active modules across tenants:
#      - s3test_full : all four modules (FIN/STR/ZZP/TENADMIN), CRUD+Read+Export
#      - s3test_fin  : FIN (the only active module there)
#      - s3test_str  : STR (the only active module there)
#      - s3test_hdcn : an active-module role (members) PLUS a role for the
#                      INACTIVE FIN module, so the resolver must exclude it.
S4_MULTITENANT_USER = "s4test-multi@example.com"
SEED_TENANT_ROLES_S4 = [
    # (email, administration, role)
    # Wide grant on the all-four-modules tenant:
    (S4_MULTITENANT_USER, "s3test_full", "Finance_CRUD"),
    (S4_MULTITENANT_USER, "s3test_full", "Finance_Read"),
    (S4_MULTITENANT_USER, "s3test_full", "Finance_Export"),
    (S4_MULTITENANT_USER, "s3test_full", "STR_CRUD"),
    (S4_MULTITENANT_USER, "s3test_full", "STR_Read"),
    (S4_MULTITENANT_USER, "s3test_full", "STR_Export"),
    (S4_MULTITENANT_USER, "s3test_full", "ZZP_CRUD"),
    (S4_MULTITENANT_USER, "s3test_full", "ZZP_Read"),
    (S4_MULTITENANT_USER, "s3test_full", "ZZP_Export"),
    (S4_MULTITENANT_USER, "s3test_full", "Tenant_Admin"),
    # Second tenant (FIN-only active):
    (S4_MULTITENANT_USER, "s3test_fin", "Finance_CRUD"),
    (S4_MULTITENANT_USER, "s3test_fin", "Finance_Read"),
    (S4_MULTITENANT_USER, "s3test_fin", "Finance_Export"),
    # Third tenant (STR-only active):
    (S4_MULTITENANT_USER, "s3test_str", "STR_CRUD"),
    (S4_MULTITENANT_USER, "s3test_str", "STR_Read"),
    # Fourth tenant (SAM-backed modules active; FIN INACTIVE there):
    # A role for the ACTIVE members module...
    (S4_MULTITENANT_USER, "s3test_hdcn", "Tenant_Admin"),
    # ...and a role for the INACTIVE FIN module — the resolver MUST exclude it,
    # exercising the "roles for inactive modules do not grant access" rule.
    (S4_MULTITENANT_USER, "s3test_hdcn", "Finance_CRUD"),
]


def seed_tenant_roles_s4(db: DatabaseManager, dry_run: bool) -> int:
    """Seed the S4 multi-tenant size-budget user's per-tenant role grants.

    All `administration` values reference EXISTING s3test_* tenants (seeded by
    seed_tenants above), so the FK to tenants(administration) holds. Idempotent
    via the shared _seed_role existence check.
    """
    inserted = 0
    for email, administration, role in SEED_TENANT_ROLES_S4:
        if _seed_role(db, email, administration, role, dry_run):
            inserted += 1
    return inserted


# 4) GoodwinSolutions test user — seeded under the EXISTING GoodwinSolutions
#    tenant (its FIN/STR/TENADMIN/ZZP modules are already active). Only this
#    synthetic user's role rows are added; no GoodwinSolutions tenant/module
#    row is created or modified.
GOODWIN_TENANT = "GoodwinSolutions"
GOODWIN_TEST_USER = "test-goodwin@example.com"
# Full-access set (mirrors the real full-access grant peter@pgeers.nl):
GOODWIN_FULL_ACCESS_ROLES = [
    "Finance_CRUD",
    "STR_CRUD",
    "ZZP_CRUD",
    "Tenant_Admin",
]
# Optional read-only variants to test allow/deny (view OK, create -> 403):
GOODWIN_READONLY_ROLES = [
    "Finance_Read",
    "STR_Read",
    "ZZP_Read",
]

# The set of tenants this script owns (for a safe, scoped --reset).
_OWNED_TENANTS = [t[0] for t in SEED_TENANTS]


def _tenant_exists(db: DatabaseManager, administration: str) -> bool:
    rows = db.execute_query(
        "SELECT 1 FROM tenants WHERE administration = %s",
        (administration,),
        fetch=True,
    )
    return bool(rows)


def seed_tenants(db: DatabaseManager, dry_run: bool) -> int:
    inserted = 0
    for administration, display_name in SEED_TENANTS:
        if _tenant_exists(db, administration):
            print(f"  SKIP tenant  {administration} (exists)")
            continue
        print(f"  INSERT tenant {administration}")
        if not dry_run:
            db.execute_query(
                """INSERT INTO tenants
                       (administration, display_name, status, country, created_by)
                   VALUES (%s, %s, 'active', 'Netherlands', %s)""",
                (administration, display_name, SEED_CREATED_BY),
                fetch=False,
                commit=True,
            )
        inserted += 1
    return inserted


def seed_tenant_modules(db: DatabaseManager, dry_run: bool) -> int:
    inserted = 0
    for administration, module_name, is_active in SEED_TENANT_MODULES:
        print(
            f"  UPSERT module {administration} / {module_name} "
            f"(is_active={is_active})"
        )
        if not dry_run:
            # ON DUPLICATE KEY UPDATE keeps this idempotent on the
            # (administration, module_name) unique key.
            db.execute_query(
                """INSERT INTO tenant_modules
                       (administration, module_name, is_active, created_by)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       is_active = VALUES(is_active),
                       updated_at = CURRENT_TIMESTAMP""",
                (administration, module_name, is_active, SEED_CREATED_BY),
                fetch=False,
                commit=True,
            )
        inserted += 1
    return inserted


def _role_exists(db: DatabaseManager, email: str, administration: str, role: str) -> bool:
    rows = db.execute_query(
        """SELECT 1 FROM user_tenant_roles
           WHERE email = %s AND administration = %s AND role = %s""",
        (email, administration, role),
        fetch=True,
    )
    return bool(rows)


def _seed_role(
    db: DatabaseManager, email: str, administration: str, role: str, dry_run: bool
) -> bool:
    if _role_exists(db, email, administration, role):
        print(f"  SKIP role    {email} @ {administration} :: {role} (exists)")
        return False
    print(f"  INSERT role   {email} @ {administration} :: {role}")
    if not dry_run:
        db.execute_query(
            """INSERT INTO user_tenant_roles
                   (email, administration, role, created_by)
               VALUES (%s, %s, %s, %s)""",
            (email, administration, role, SEED_CREATED_BY),
            fetch=False,
            commit=True,
        )
    return True


def seed_tenant_roles(db: DatabaseManager, dry_run: bool) -> int:
    inserted = 0
    for email, administration, role in SEED_TENANT_ROLES:
        if _seed_role(db, email, administration, role, dry_run):
            inserted += 1
    return inserted


def seed_goodwin_test_user(db: DatabaseManager, dry_run: bool) -> int:
    """Seed the GoodwinSolutions test user's per-tenant roles.

    Requires the existing GoodwinSolutions tenant (FK target). If it is absent
    (e.g. an empty dev DB), the roles are skipped with a clear warning rather
    than inventing the tenant — we must not fabricate live governance data.
    """
    if not _tenant_exists(db, GOODWIN_TENANT):
        print(
            f"  WARN: tenant '{GOODWIN_TENANT}' not present — skipping the "
            f"GoodwinSolutions test user roles (won't fabricate the tenant)."
        )
        return 0

    inserted = 0
    for role in GOODWIN_FULL_ACCESS_ROLES + GOODWIN_READONLY_ROLES:
        if _seed_role(db, GOODWIN_TEST_USER, GOODWIN_TENANT, role, dry_run):
            inserted += 1
    return inserted


def reset_seed(db: DatabaseManager, dry_run: bool) -> None:
    """Remove ONLY this script's own synthetic rows.

    Scoped to the `s3test_*` tenants and the `test-goodwin@example.com` user.
    Never deletes any other tenant/module/role — no live data is touched.
    Deletes child rows (user_tenant_roles, tenant_modules) before parent rows
    (tenants) to respect the FK.
    """
    print("Reset: removing this script's synthetic rows only...")

    # GoodwinSolutions test user's roles (the tenant itself is left untouched).
    print(f"  DELETE user_tenant_roles WHERE email = {GOODWIN_TEST_USER}")
    if not dry_run:
        db.execute_query(
            "DELETE FROM user_tenant_roles WHERE email = %s",
            (GOODWIN_TEST_USER,),
            fetch=False,
            commit=True,
        )

    for administration in _OWNED_TENANTS:
        print(f"  DELETE user_tenant_roles WHERE administration = {administration}")
        if not dry_run:
            db.execute_query(
                "DELETE FROM user_tenant_roles WHERE administration = %s",
                (administration,),
                fetch=False,
                commit=True,
            )
        print(f"  DELETE tenant_modules   WHERE administration = {administration}")
        if not dry_run:
            db.execute_query(
                "DELETE FROM tenant_modules WHERE administration = %s",
                (administration,),
                fetch=False,
                commit=True,
            )
        print(f"  DELETE tenants          WHERE administration = {administration}")
        if not dry_run:
            db.execute_query(
                "DELETE FROM tenants WHERE administration = %s",
                (administration,),
                fetch=False,
                commit=True,
            )


def summarize(db: DatabaseManager) -> None:
    print("\n" + "=" * 60)
    print("Seed verification (synthetic fixtures only)")
    print("=" * 60)

    placeholders = ", ".join(["%s"] * len(_OWNED_TENANTS))

    tenants = db.execute_query(
        f"SELECT administration, status FROM tenants "
        f"WHERE administration IN ({placeholders}) ORDER BY administration",
        tuple(_OWNED_TENANTS),
        fetch=True,
    )
    print(f"tenants ({len(tenants or [])}):")
    for r in tenants or []:
        print(f"  {r['administration']:16} status={r['status']}")

    modules = db.execute_query(
        f"SELECT administration, module_name, is_active FROM tenant_modules "
        f"WHERE administration IN ({placeholders}) "
        f"ORDER BY administration, module_name",
        tuple(_OWNED_TENANTS),
        fetch=True,
    )
    print(f"\ntenant_modules ({len(modules or [])}):")
    for r in modules or []:
        print(
            f"  {r['administration']:16} {r['module_name']:10} "
            f"active={r['is_active']}"
        )

    roles = db.execute_query(
        f"SELECT email, administration, role FROM user_tenant_roles "
        f"WHERE administration IN ({placeholders}) "
        f"ORDER BY administration, email, role",
        tuple(_OWNED_TENANTS),
        fetch=True,
    )
    print(f"\nuser_tenant_roles for synthetic tenants ({len(roles or [])}):")
    for r in roles or []:
        print(f"  {r['email']:28} @ {r['administration']:12} :: {r['role']}")

    s4_multi = db.execute_query(
        "SELECT email, administration, role FROM user_tenant_roles "
        "WHERE email = %s ORDER BY administration, role",
        (S4_MULTITENANT_USER,),
        fetch=True,
    )
    s4_tenants = sorted({r["administration"] for r in (s4_multi or [])})
    print(
        f"\nS4 multi-tenant size-budget user ({len(s4_multi or [])} grants "
        f"across {len(s4_tenants)} tenants: {', '.join(s4_tenants)}):"
    )
    for r in s4_multi or []:
        print(f"  {r['email']} @ {r['administration']:12} :: {r['role']}")

    goodwin = db.execute_query(
        "SELECT email, administration, role FROM user_tenant_roles "
        "WHERE email = %s ORDER BY role",
        (GOODWIN_TEST_USER,),
        fetch=True,
    )
    print(f"\nGoodwinSolutions test user roles ({len(goodwin or [])}):")
    for r in goodwin or []:
        print(f"  {r['email']} @ {r['administration']} :: {r['role']}")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed throwaway S3 governance fixtures into Docker MySQL."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove this script's own synthetic rows before seeding.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing.",
    )
    args = parser.parse_args(argv)

    # test_mode=False -> DB_NAME=finance (the Docker MySQL default). Config from
    # env (backend/.env), never hardcoded.
    db = DatabaseManager(test_mode=False)

    print(f"Target DB: {db.config.get('database')} @ "
          f"{db.config.get('host')}:{db.config.get('port')}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'WRITE'}"
          f"{' + RESET' if args.reset else ''}\n")

    if args.reset:
        reset_seed(db, args.dry_run)
        print()

    print("Seeding tenants...")
    n_t = seed_tenants(db, args.dry_run)
    print("\nSeeding tenant_modules...")
    n_m = seed_tenant_modules(db, args.dry_run)
    print("\nSeeding user_tenant_roles (synthetic tenants)...")
    n_r = seed_tenant_roles(db, args.dry_run)
    print("\nSeeding S4 multi-tenant size-budget user roles...")
    n_s4 = seed_tenant_roles_s4(db, args.dry_run)
    print("\nSeeding GoodwinSolutions test user roles...")
    n_g = seed_goodwin_test_user(db, args.dry_run)

    print(
        f"\nDone. tenants +{n_t}, tenant_modules ~{n_m}, "
        f"synthetic roles +{n_r}, S4 multi-tenant roles +{n_s4}, "
        f"GoodwinSolutions test-user roles +{n_g}."
    )

    if not args.dry_run:
        summarize(db)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
