#!/usr/bin/env python3
"""provision-members-tables.py — create the SAM-plane Members table (S5 task 4.0).

Idempotent, dry-run-first provisioner for the **single** ``sam-members`` DynamoDB table
the Members module owns (design C6 / R5.1 / Property 1). Mirrors the structure of
``scripts/local/seed-dynamodb-local.py`` (argparse → describe-then-create → waiter →
dry-run/reset flags), but for the SAM module plane instead of the S3 projection.

Why ONE table (not several)
---------------------------
The Members module uses a **single-table design** (``sam/members/repository/table_design.py``):
members, memberships, delegates, member-payments, per-tenant counters, the member-number
uniqueness guard, and the Lidmaatschap Beheer catalog all live in ONE physical table,
partitioned by ``tenant_id`` and disambiguated by a ``record_type#id`` composite sort key.
So there is nothing to provision but this one table — "counters" and "member-payments" are
not separate tables, they are ``counter#…`` / ``member#…#payment#…`` items in the same
partition. Key schema is taken verbatim from ``table_design`` constants so the script and the
repository can never diverge on the key shape.

Naming (SAM-plane convention — see ``23-aws-accounts.md`` / ``35-sam-module-architecture-sam.md``)
-------------------------------------------------------------------------------------------------
SAM-plane tables use a ``sam-`` name prefix with the environment as a **suffix**:
``sam-members`` (prod) / ``sam-members-test`` (test/dev). The ``sam-`` prefix stays at the
front so module-plane IAM can scope to ``arn:aws:dynamodb:*:*:table/sam-*`` (defense in depth
over the ``tenant_id`` LeadingKeys). The table NAME is **not** hardcoded here — it is resolved
from ``MEMBERS_TABLE`` via ``table_design.resolve_members_table_name()`` (fail-fast; a
missing/blank var raises rather than guessing). This script never synthesizes a name.

Safety guards (aws-accounts.md guardrails)
------------------------------------------
- **Dry-run is the default.** Nothing is created unless you pass ``--apply``. A dry run prints
  the plan (table name, key schema, billing) and exits without touching AWS.
- **Idempotent.** ``describe_table`` first; if the table already exists, creation is skipped.
- **``--reset`` (delete + recreate) is refused against real AWS.** It is allowed ONLY when an
  endpoint override (``AWS_ENDPOINT_URL_DYNAMODB``) is set — i.e. a local emulator. This script
  will never delete a real AWS data table (aws-accounts.md: never ``--delete`` a data store).
- **Additive / reversible (Property 7).** It does NOT touch the legacy per-app tables
  (``Members`` / ``Counters`` / ``Payments`` / ``Memberships`` / …). Dropping ``sam-members``
  reverts the change with no data loss to those tables.

Client
------
Reuses ``services.dynamodb_client.get_dynamodb_resource`` so the local-vs-cloud switch
(``AWS_ENDPOINT_URL_DYNAMODB``) and the fail-fast on region/credentials live in ONE place.
Region defaults to ``eu-west-1`` (aws-accounts.md).

IAM
---
Binding a principal to ``sam-*`` / the tenant partition (``dynamodb:LeadingKeys``) is a
**separate IAM step** — see ``table_design.LEADING_KEYS_IAM_POLICY_PLAN``. This script only
creates the table; it prints a reminder to apply that policy plan out of band.

Usage (from repo root, WSL)
---------------------------
  # Dry run (default — creates nothing), prod name:
  MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 \
      backend/.venv/bin/python scripts/aws/provision-members-tables.py

  # Actually create against real AWS (nonprofit data account):
  MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
      backend/.venv/bin/python scripts/aws/provision-members-tables.py --apply

  # Local emulator create / reset (endpoint set → --reset allowed):
  MEMBERS_TABLE=sam-members-test AWS_REGION=eu-west-1 \
      AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 \
      backend/.venv/bin/python scripts/aws/provision-members-tables.py --apply --reset
"""

from __future__ import annotations

import argparse
import os
import sys

# repo root + backend/src on sys.path so `sam.members...` and its `services.dynamodb_client`
# dependency both import (mirrors sam/conftest.py + sam/tests path setup).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from botocore.exceptions import ClientError

from sam.members.repository import table_design as td
from services.dynamodb_client import get_dynamodb_resource, get_endpoint_url

DEFAULT_REGION = "eu-west-1"


class ResetRefusedError(RuntimeError):
    """``--reset`` was requested against real AWS (no local endpoint override).

    Raised instead of deleting, so this script can never drop a real AWS data table
    (aws-accounts.md guardrail: never ``--delete`` a data store).
    """


def _key_schema() -> list[dict]:
    """Key schema for ``sam-members``, taken verbatim from ``table_design`` constants."""
    return [
        {"AttributeName": td.PARTITION_KEY_ATTR, "KeyType": "HASH"},
        {"AttributeName": td.SORT_KEY_ATTR, "KeyType": "RANGE"},
    ]


def _attribute_definitions() -> list[dict]:
    """Attribute definitions — PK ``tenant_id`` (S), SK ``sk`` (S). From ``table_design``."""
    return [
        {"AttributeName": td.PARTITION_KEY_ATTR, "AttributeType": "S"},
        {"AttributeName": td.SORT_KEY_ATTR, "AttributeType": "S"},
    ]


def _table_exists(client, name: str) -> bool:
    try:
        client.describe_table(TableName=name)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def _create_table(dynamodb, client, name: str) -> None:
    dynamodb.create_table(
        TableName=name,
        KeySchema=_key_schema(),
        AttributeDefinitions=_attribute_definitions(),
        BillingMode="PAY_PER_REQUEST",  # on-demand (aws-accounts.md)
    )
    client.get_waiter("table_exists").wait(TableName=name)


def _delete_table(dynamodb, client, name: str) -> None:
    dynamodb.Table(name).delete()
    client.get_waiter("table_not_exists").wait(TableName=name)


def _print_plan(table_name: str, region: str, *, apply: bool, reset: bool, local: bool) -> None:
    print("=" * 60)
    print("Provision plan — SAM-plane Members table (single-table design)")
    print("=" * 60)
    print(f"  table       : {table_name}")
    print(f"  region      : {region}")
    print(f"  endpoint    : {'local emulator' if local else 'real AWS'}")
    print(f"  billing     : PAY_PER_REQUEST (on-demand)")
    print(f"  key schema  : PK {td.PARTITION_KEY_ATTR} (S), SK {td.SORT_KEY_ATTR} (S)")
    print(f"  mode        : {'APPLY' if apply else 'DRY-RUN (creates nothing)'}")
    print(f"  reset       : {reset}")
    print("  scope       : ONE table (members/memberships/delegates/payments/counters/")
    print("                uniqueness-guard/catalog fold into it via the SK composite)")
    print("  additive    : legacy Members/Counters/Payments/Memberships tables untouched")
    print("  IAM         : bind principal to sam-* / tenant partition separately —")
    print("                see table_design.LEADING_KEYS_IAM_POLICY_PLAN")
    print("=" * 60)


def provision(
    region: str,
    *,
    apply: bool,
    reset: bool,
) -> int:
    """Create (or dry-run) the ``sam-members`` table. Returns a process exit code.

    The table name is resolved from ``MEMBERS_TABLE`` (fail-fast) — never hardcoded.
    """
    # Fail-fast table-name resolution (reuses services.dynamodb_client.require_env via
    # table_design). A missing/blank MEMBERS_TABLE raises here rather than guessing a name.
    table_name = td.resolve_members_table_name()
    local = get_endpoint_url() is not None

    # Guard: --reset may only ever run against a local emulator. Never delete real AWS data.
    if reset and not local:
        raise ResetRefusedError(
            "--reset (delete + recreate) is refused against real AWS: no "
            "AWS_ENDPOINT_URL_DYNAMODB endpoint override is set, so this would target a real "
            "data table. Reset is only permitted against a local DynamoDB emulator "
            "(aws-accounts.md: never --delete a data store)."
        )

    _print_plan(table_name, region, apply=apply, reset=reset, local=local)

    if not apply:
        print("\nDRY-RUN: no AWS calls made. Re-run with --apply to create the table.")
        return 0

    dynamodb = get_dynamodb_resource(region=region)
    client = dynamodb.meta.client

    exists = _table_exists(client, table_name)

    if exists and reset:
        # Only reachable when local (guarded above).
        print(f"[{table_name}] exists — deleting (reset, local emulator only)...")
        _delete_table(dynamodb, client, table_name)
        exists = False

    if not exists:
        print(f"[{table_name}] creating (PK={td.PARTITION_KEY_ATTR}, "
              f"SK={td.SORT_KEY_ATTR}, on-demand)...")
        _create_table(dynamodb, client, table_name)
        status = "created"
    else:
        print(f"[{table_name}] already exists — skipping create (idempotent).")
        status = "existed"

    print("\n" + "=" * 60)
    print("Provision summary")
    print("=" * 60)
    print(f"  table : {table_name} ({status})")
    print("  next  : bind IAM to sam-* / tenant partition "
          "(table_design.LEADING_KEYS_IAM_POLICY_PLAN)")
    print("=" * 60)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision the SAM-plane Members table (sam-members). "
        "Dry-run by default; pass --apply to create.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: env AWS_REGION or {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create the table. Without this, the script only prints the plan "
        "(dry-run is the default for safety).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the table. REFUSED against real AWS — only allowed when "
        "AWS_ENDPOINT_URL_DYNAMODB is set (a local emulator).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return provision(args.region, apply=args.apply, reset=args.reset)
    except ResetRefusedError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
