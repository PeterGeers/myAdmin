#!/usr/bin/env python3
"""cleanup-membernum-guard-rows.py — delete the retired ``membernum#`` guard rows (s5k task 4.3).

s5k removed the member-number **uniqueness guard**: ``save_member`` no longer writes a second
``membernum#<member_number>`` item per member, and nothing reads it anymore. The guard rows that
were written under the OLD code are now **inert** — deleting them is pure cleanup, not a
correctness fix. This script removes them for one tenant, dry-run-first and idempotent.

What it does
------------
1. Queries the tenant partition of ``sam-members`` for items whose sort key begins with the
   retired ``membernum#`` token (``PK = <tenant> AND begins_with(sk, "membernum#")``). The query
   is structurally tenant-scoped (the partition key is fixed) and record-type-scoped (the SK
   prefix), so it can never address another tenant or another record type (member#, membership#,
   payment#, delegates#, membershiptype#).
2. In **dry-run (the default)** prints how many guard rows were found + a small sample of their
   sort keys, and writes NOTHING.
3. With ``--apply`` (and only then) deletes exactly those items via ``BatchWriteItem`` (chunks of
   25). Every key is RE-CHECKED to still carry the ``membernum#`` SK prefix immediately before it
   is queued for deletion — a defense-in-depth guard so a query anomaly can never delete a real
   ``member#`` / ``membershiptype#`` row.

Safety guards (aws-accounts.md guardrails, R5.2)
------------------------------------------------
- **Dry-run is the default.** Nothing is deleted unless you pass ``--apply``.
- **Tenant-scoped, no default tenant.** ``--tenant`` is REQUIRED (R8, steering 31) so nothing can
  be deleted from the wrong partition by omission.
- **Record-type-scoped + re-checked.** Only ``membernum#`` items are ever queued; each key's SK
  prefix is verified again before deletion. No ``member#`` / ``membershiptype#`` row is touched.
- **Idempotent.** A re-run simply finds nothing left to delete (returns 0 deleted).
- **Fail-fast table name.** Resolved from ``MEMBERS_TABLE`` via
  ``table_design.resolve_members_table_name()`` (a missing/blank var raises rather than guessing).
- **Reuses the T0 client.** ``services.dynamodb_client.get_dynamodb_resource`` (local-vs-cloud
  switch via ``AWS_ENDPOINT_URL_DYNAMODB`` + fail-fast) lives in ONE place.

⚠ Account/credentials (steering 41 — `nonprofit-deploy`)
--------------------------------------------------------
``sam-members`` lives in the nonprofit/data account (506221081911, eu-west-1). The repo-root
``.env`` exports STATIC ``personal``-account keys + a local DynamoDB endpoint that boto3 ranks
ABOVE ``AWS_PROFILE`` — so you MUST strip them (and the endpoint) or this silently runs against
the wrong account / the local emulator. Sanity-check identity prints 506221081911 first.

Usage (from repo root, WSL)
---------------------------
  # Dry run (default — deletes nothing) against real AWS (nonprofit data account).
  # Strip the .env personal keys + endpoint so AWS_PROFILE resolves to nonprofit-deploy:
  env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ENDPOINT_URL \
      -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
      MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/cleanup-membernum-guard-rows.py --tenant h-dcn

  # Actually delete (only after a clean dry run):
  env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ENDPOINT_URL \
      -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
      MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/cleanup-membernum-guard-rows.py --tenant h-dcn --apply

  # Local emulator (endpoint set → local DynamoDB, no real AWS):
  MEMBERS_TABLE=sam-members-local AWS_REGION=eu-west-1 \
      AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 \
      backend/.venv/bin/python scripts/aws/cleanup-membernum-guard-rows.py --tenant h-dcn --apply
"""

from __future__ import annotations

import argparse
import os
import sys

# repo root + backend/src on sys.path so `sam.members...` and its `services.dynamodb_client`
# dependency both import (mirrors provision-members-tables.py + sam/tests path setup).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from boto3.dynamodb.conditions import Key

from sam.members.repository import table_design as td
from services.dynamodb_client import get_dynamodb_resource, get_endpoint_url

DEFAULT_REGION = "eu-west-1"

#: The RETIRED sort-key prefix of the member-number uniqueness guard (s5k removed the token from
#: table_design, so it is spelled literally here — this script is the one place that still knows
#: about it, purely to clean up the historical rows).
_MEMBERNUM_SK_PREFIX = "membernum#"

#: How many sample sort keys to show in the dry-run report.
_SAMPLE_COUNT = 5

#: DynamoDB BatchWriteItem hard limit (items per request).
_BATCH_SIZE = 25


def _find_guard_rows(table, tenant_id: str) -> list[str]:
    """Return the sort keys of every ``membernum#`` guard row in the tenant partition.

    Tenant-scoped (PK fixed) + record-type-scoped (SK ``begins_with`` the retired prefix), with
    pagination. Projects only the key attributes — we never need the guard payload to delete it.
    """
    sort_keys: list[str] = []
    kwargs = {
        "KeyConditionExpression": Key(td.PARTITION_KEY_ATTR).eq(tenant_id)
        & Key(td.SORT_KEY_ATTR).begins_with(_MEMBERNUM_SK_PREFIX),
        "ProjectionExpression": "#pk, #sk",
        "ExpressionAttributeNames": {
            "#pk": td.PARTITION_KEY_ATTR,
            "#sk": td.SORT_KEY_ATTR,
        },
    }
    while True:
        resp = table.query(**kwargs)
        for item in resp.get("Items", []):
            sk = item.get(td.SORT_KEY_ATTR)
            # Defense in depth: only ever collect a real membernum# key.
            if isinstance(sk, str) and sk.startswith(_MEMBERNUM_SK_PREFIX):
                sort_keys.append(sk)
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return sort_keys


def _delete_guard_rows(table, tenant_id: str, sort_keys: list[str]) -> int:
    """Delete the given guard rows via BatchWriteItem (chunks of 25). Returns the count deleted.

    Each key is RE-CHECKED to still carry the ``membernum#`` prefix before it is queued — a real
    ``member#`` / ``membershiptype#`` row can never be deleted even if the caller passed a bad key.
    """
    deleted = 0
    with table.batch_writer() as batch:
        for sk in sort_keys:
            if not sk.startswith(_MEMBERNUM_SK_PREFIX):
                # Should be impossible (the query is prefix-scoped) — skip rather than delete.
                continue
            batch.delete_item(Key={td.PARTITION_KEY_ATTR: tenant_id, td.SORT_KEY_ATTR: sk})
            deleted += 1
    return deleted


def _print_report(
    tenant_id: str,
    table_name: str,
    region: str,
    sort_keys: list[str],
    *,
    apply: bool,
    local: bool,
) -> None:
    print("=" * 68)
    print("s5k membernum# guard-row cleanup")
    print("=" * 68)
    print(f"  tenant       : {tenant_id}")
    print(f"  target table : {table_name}")
    print(f"  region       : {region}")
    print(f"  endpoint     : {'local emulator' if local else 'real AWS'}")
    print(f"  mode         : {'APPLY (deletes the rows)' if apply else 'DRY-RUN (deletes nothing)'}")
    print("-" * 68)
    print(f"  guard rows found (sk begins_with {_MEMBERNUM_SK_PREFIX!r}): {len(sort_keys)}")
    if sort_keys:
        print(f"  sample sort keys (first {_SAMPLE_COUNT}):")
        for sk in sort_keys[:_SAMPLE_COUNT]:
            print(f"    {sk}")
    print("=" * 68)


def cleanup(
    tenant_id: str,
    *,
    region: str,
    apply: bool,
    table=None,
) -> int:
    """Delete (or dry-run) the tenant's ``membernum#`` guard rows. Returns a process exit code.

    The table name is resolved from ``MEMBERS_TABLE`` (fail-fast) — never hardcoded. ``table`` may
    be injected for tests; in production it is resolved lazily.
    """
    table_name = td.resolve_members_table_name()
    local = get_endpoint_url() is not None

    if table is None:
        table = get_dynamodb_resource(region=region).Table(table_name)

    sort_keys = _find_guard_rows(table, tenant_id)
    _print_report(tenant_id, table_name, region, sort_keys, apply=apply, local=local)

    if not apply:
        print(
            "\nDRY-RUN: no rows deleted. Review the count above, then re-run with --apply "
            "to delete. (Re-running after an apply is safe — it will find 0.)"
        )
        return 0

    if not sort_keys:
        print("\nNothing to delete (0 guard rows) — idempotent no-op.")
        return 0

    deleted = _delete_guard_rows(table, tenant_id, sort_keys)

    # Verify none remain (idempotency + confirmation).
    remaining = _find_guard_rows(table, tenant_id)

    print("\n" + "=" * 68)
    print("Cleanup apply summary")
    print("=" * 68)
    print(f"  tenant    : {tenant_id}")
    print(f"  table     : {table_name}")
    print(f"  deleted   : {deleted}")
    print(f"  remaining : {len(remaining)} (must be 0)")
    print("=" * 68)
    return 0 if not remaining else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete the retired s5k membernum# uniqueness-guard rows for a tenant. "
        "Dry-run by default; pass --apply to delete. Tenant-scoped + idempotent.",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="The administration (tenant) whose guard rows to delete (e.g. 'h-dcn'). REQUIRED — "
        "there is no default (R8, steering 31): the script fails if it is missing so nothing can "
        "be deleted from the wrong partition by omission.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: env AWS_REGION or {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the guard rows. Without this, the script only prints the count "
        "(dry-run is the default for safety).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return cleanup(args.tenant, region=args.region, apply=args.apply)
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
