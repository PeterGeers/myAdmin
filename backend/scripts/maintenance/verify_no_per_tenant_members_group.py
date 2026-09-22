#!/usr/bin/env python3
"""
Verify no PER-TENANT ``Members_*`` Cognito group exists on the identity pools.

s5c task 0.5 / requirement R6.4 (component C-UNWIND).

Why this check exists
---------------------
s5b baked tenant identity into a Cognito group name (e.g. ``Members_CRUD_hdcn``) and
derived Members *capability* from ``cognito:groups`` — the exact bypass s5c unwinds.
Under the settled model:

  * capability comes SOLELY from the verified ``custom:entitlements`` claim
    (stamped by the PreTokenGen Lambda), never from ``cognito:groups``; and
  * tenant/scope context comes from the verified entitlement + the projected
    ``scopegrant#`` row — NOT from a group whose name encodes a tenant.

So a per-tenant ``Members_*`` group must never (re)appear on any pool.

What is LEGITIMATE (and MUST NOT be flagged)
-------------------------------------------
The THREE GLOBAL Members roles are expected on every pool and mirror the other
modules' global roles (``Finance_*``, ``STR_*``, ``ZZP_*``, ``Tenant_Admin``,
``SysAdmin``). Tenant context is NOT encoded in these names — it comes from the
verified entitlement/scope. The three globals are:

    Members_CRUD
    Members_Read
    Members_Export

What FAILS this check
---------------------
Any Cognito group whose name matches ``Members`` (case-insensitive) but is NOT
exactly one of the three globals above — i.e. any per-tenant variant such as
``Members_CRUD_hdcn``, ``hdcn_Members_CRUD``, ``Members_h-dcn``, or
``Members_CRUD_<tenantId>``. Finding one exits non-zero (CI-failing).

Pools checked (steering 23-aws-accounts.md: Cognito/identity = profile ``personal``,
account 344561557829, region eu-west-1)
    test pool  : eu-west-1_xyrlzfqbl  (myAdmin-test)
    prod Pool A: eu-west-1_Hdp40eWmu  (myAdmin)   [--prod]

Usage
-----
    # test pool only (default):
    python backend/scripts/maintenance/verify_no_per_tenant_members_group.py

    # test pool + prod Pool A:
    python backend/scripts/maintenance/verify_no_per_tenant_members_group.py --prod

    # override / add pools explicitly:
    python backend/scripts/maintenance/verify_no_per_tenant_members_group.py \
        --pool eu-west-1_xyrlzfqbl --pool eu-west-1_Hdp40eWmu

Read-only: this script only calls ``cognito-idp:ListGroups`` — it NEVER creates or
deletes a group. Deleting the three global role groups would break scope gating and
MUST NOT be done (see design C-UNWIND).

Exit code: 0 = clean (no per-tenant Members group), 1 = a per-tenant group was found,
2 = a pool could not be inspected (AWS creds / access error).
"""
import argparse
import re
import sys

import boto3

REGION = "eu-west-1"

# The three LEGITIMATE global Members roles (exact names). Anything else that looks
# like a Members group is a per-tenant variant and fails R6.4.
GLOBAL_MEMBERS_ROLES = {"Members_CRUD", "Members_Read", "Members_Export"}

# Case-insensitive "looks like a Members group" detector.
MEMBERS_TOKEN = re.compile(r"members", re.IGNORECASE)

# Known pools (steering 23-aws-accounts.md).
TEST_POOL = "eu-west-1_xyrlzfqbl"   # myAdmin-test
PROD_POOL_A = "eu-west-1_Hdp40eWmu"  # myAdmin (Pool A)


def _list_group_names(client, pool_id):
    """Return every group name in a pool (handles pagination). Read-only."""
    names = []
    kwargs = {"UserPoolId": pool_id, "Limit": 60}
    while True:
        resp = client.list_groups(**kwargs)
        names.extend(g["GroupName"] for g in resp.get("Groups", []))
        token = resp.get("NextToken")
        if not token:
            break
        kwargs["NextToken"] = token
    return names


def check_pool(client, pool_id):
    """
    Inspect one pool. Returns (offenders, globals_present, error).

    offenders       : list of per-tenant Members_* group names (R6.4 violations)
    globals_present : list of the three globals that were found (informational)
    error           : str if the pool could not be inspected, else None
    """
    print("=" * 60)
    print(f"POOL {pool_id}")
    print("=" * 60)
    try:
        names = _list_group_names(client, pool_id)
    except Exception as e:  # noqa: BLE001 - surface any boto/creds error as a soft failure
        print(f"  ⚠️  could not inspect pool: {e}")
        return [], [], str(e)

    members_like = [n for n in names if MEMBERS_TOKEN.search(n)]
    offenders = [n for n in members_like if n not in GLOBAL_MEMBERS_ROLES]
    globals_present = [n for n in members_like if n in GLOBAL_MEMBERS_ROLES]

    for name in sorted(globals_present):
        print(f"  ✅ OK: global role present  — {name}")
    for role in sorted(GLOBAL_MEMBERS_ROLES - set(globals_present)):
        print(f"  ℹ️  global role not present — {role} (allowed; roles are optional per pool)")
    for name in sorted(offenders):
        print(f"  ❌ PER-TENANT Members group — {name}  (R6.4 violation)")

    if not members_like:
        print("  ℹ️  no Members_* groups at all")
    print()
    return offenders, globals_present, None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify no per-tenant Members_* Cognito group exists (R6.4).",
    )
    parser.add_argument(
        "--pool", action="append", default=None,
        help="Explicit pool id (repeatable). Overrides the default test pool.",
    )
    parser.add_argument(
        "--prod", action="store_true",
        help=f"Also check prod Pool A ({PROD_POOL_A}).",
    )
    parser.add_argument(
        "--profile", default=None,
        help="AWS profile (steering 23: identity = 'personal').",
    )
    parser.add_argument("--region", default=REGION)
    args = parser.parse_args(argv)

    # Resolve pool list: explicit --pool wins; otherwise test pool (+ prod if --prod).
    if args.pool:
        pools = list(dict.fromkeys(args.pool))
    else:
        pools = [TEST_POOL]
        if args.prod:
            pools.append(PROD_POOL_A)

    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    client = session.client("cognito-idp", region_name=args.region)

    print("=" * 60)
    print("VERIFY: NO PER-TENANT Members_* COGNITO GROUP (R6.4)")
    print("=" * 60)
    print(f"Region : {args.region}")
    print(f"Profile: {args.profile or '(default)'}")
    print(f"Pools  : {', '.join(pools)}")
    print(f"Allowed global roles: {', '.join(sorted(GLOBAL_MEMBERS_ROLES))}")
    print()

    all_offenders = {}
    inspect_errors = {}
    for pool_id in pools:
        offenders, _globals, error = check_pool(client, pool_id)
        if error:
            inspect_errors[pool_id] = error
        if offenders:
            all_offenders[pool_id] = offenders

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if inspect_errors:
        for pool_id, error in inspect_errors.items():
            print(f"⚠️  {pool_id}: not inspected ({error})")
    if all_offenders:
        for pool_id, offenders in all_offenders.items():
            print(f"❌ {pool_id}: per-tenant Members group(s): {', '.join(offenders)}")
        print()
        print("FAIL — a per-tenant Members_* group exists (R6.4). Capability/tenant must")
        print("come from custom:entitlements + scopegrant#, not a tenant-named group.")
        return 1
    if inspect_errors:
        print()
        print("INCONCLUSIVE — no violations seen, but at least one pool could not be")
        print("inspected. Re-run with valid credentials (steering 23: profile 'personal').")
        return 2

    print("✅ PASS — no per-tenant Members_* group on any checked pool.")
    print("   (Only the global Members_CRUD / Members_Read / Members_Export roles are")
    print("    allowed; tenant context comes from custom:entitlements + scopegrant#.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
