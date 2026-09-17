#!/usr/bin/env python3
"""seed-dynamodb-local.py — create + seed the S3 governance projection table
in local DynamoDB (the `dynamodb-local` container from docker-compose.yml).

Part of the S3 spec (`s3-claims-and-projection`) Phase 0 / T0. It makes the
one-directional MySQL->DynamoDB projection (design.md D3) testable fully offline
against a local table instead of the cloud `test_`/-Test tables.

What it does:
  - Connects to local DynamoDB (default http://localhost:8000) using dummy
    credentials so it works offline against the emulator, never real AWS.
  - Creates the projection table (PAY_PER_REQUEST, matching prod conventions)
    with the design's key schema:
        PK  tenant_id      (S)   == administration (the tenancy boundary)
        SK  record_type#id (S)   e.g. "tenant", "module#members", "role#a@b#R"
    Skips creation if it already exists, unless --reset (delete + recreate).
  - Optionally inserts a handful of small SYNTHETIC items (--with-fixtures)
    using obviously-fake tenant/module/role values so a read-side smoke test has
    something to read. No prod copy, no PII.

The table NAME is taken from --table or the GOVERNANCE_PROJECTION_TABLE env var
(default: test_governance_projection) — the same var the projection's DynamoDB
client resolves (fail-fast) in backend/src/services/dynamodb_client.py.

Usage (from repo root, WSL):
  backend/.venv/bin/python scripts/local/seed-dynamodb-local.py [--reset]
      [--with-fixtures] [--endpoint-url http://localhost:8000]
      [--region eu-west-1] [--table test_governance_projection]
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError

DEFAULT_TABLE = "test_governance_projection"

# Key schema from design.md D3 (R5.4): tenant_id partition key = tenancy
# boundary; record_type#id sort key distinguishes tenant/module/role rows.
PK_ATTR = "tenant_id"
SK_ATTR = "sk"  # holds the "record_type#id" composite value


def _synthetic_items() -> list[dict[str, Any]]:
    """Small, obviously-fake projection items for a read-side smoke test.

    Two tenants so tenant-isolation reads (design Property 3) have something to
    distinguish. Values are synthetic (TEST-*, *@example.invalid) — never real
    tenant/user data.
    """
    return [
        # Tenant A: a SAM-backed-module tenant with two modules + one role grant.
        {"tenant_id": "TEST-TENANT-A", "sk": "tenant", "version": 1},
        {
            "tenant_id": "TEST-TENANT-A",
            "sk": "module#members",
            "is_active": True,
            "version": 1,
        },
        {
            "tenant_id": "TEST-TENANT-A",
            "sk": "module#events",
            "is_active": True,
            "version": 1,
        },
        {
            "tenant_id": "TEST-TENANT-A",
            "sk": "role#testa@example.invalid#Members_CRUD",
            "role": "Members_CRUD",
            "version": 1,
        },
        # Tenant B: a separate tenant, to prove cross-tenant reads are unaddressable.
        {"tenant_id": "TEST-TENANT-B", "sk": "tenant", "version": 1},
        {
            "tenant_id": "TEST-TENANT-B",
            "sk": "module#webshop",
            "is_active": True,
            "version": 1,
        },
    ]


def _dynamodb_resource(endpoint_url: str, region: str):
    """Build a boto3 DynamoDB resource pointing at local DynamoDB.

    Dummy credentials are supplied so botocore can sign requests; local DynamoDB
    ignores the signature. This never reaches real AWS.
    """
    return boto3.resource(
        "dynamodb",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id="local",
        aws_secret_access_key="local",
        aws_session_token="local",
    )


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
        KeySchema=[
            {"AttributeName": PK_ATTR, "KeyType": "HASH"},
            {"AttributeName": SK_ATTR, "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": PK_ATTR, "AttributeType": "S"},
            {"AttributeName": SK_ATTR, "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",  # on-demand, matching prod conventions
    )
    client.get_waiter("table_exists").wait(TableName=name)


def seed(
    endpoint_url: str,
    region: str,
    table_name: str,
    reset: bool,
    with_fixtures: bool,
) -> int:
    dynamodb = _dynamodb_resource(endpoint_url, region)
    client = dynamodb.meta.client

    print(f"Seeding local DynamoDB at {endpoint_url} (region {region})")
    print(f"  table   = {table_name}")
    print(f"  reset   = {reset}")
    print(f"  fixtures= {with_fixtures}\n")

    exists = _table_exists(client, table_name)

    if exists and reset:
        print(f"[{table_name}] exists — deleting (reset)...")
        dynamodb.Table(table_name).delete()
        client.get_waiter("table_not_exists").wait(TableName=table_name)
        exists = False

    if not exists:
        print(f"[{table_name}] creating (PK={PK_ATTR}, SK={SK_ATTR}, on-demand)...")
        _create_table(dynamodb, client, table_name)
        status = "created"
    else:
        print(f"[{table_name}] already exists — skipping create.")
        status = "existed"

    inserted = 0
    if with_fixtures:
        table = dynamodb.Table(table_name)
        for item in _synthetic_items():
            table.put_item(Item=item)
            inserted += 1

    print("\n" + "=" * 52)
    print("Seed summary")
    print("=" * 52)
    print(f"  table   : {table_name} ({status})")
    print(f"  items   : {inserted} synthetic item(s) inserted")
    print("=" * 52)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create + seed the S3 governance projection table in local DynamoDB."
    )
    parser.add_argument(
        "--endpoint-url",
        default=os.environ.get("AWS_ENDPOINT_URL_DYNAMODB", "http://localhost:8000"),
        help="Local DynamoDB endpoint (default: env AWS_ENDPOINT_URL_DYNAMODB "
        "or http://localhost:8000)",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "eu-west-1"),
        help="AWS region name (default: env AWS_REGION or eu-west-1)",
    )
    parser.add_argument(
        "--table",
        default=os.environ.get("GOVERNANCE_PROJECTION_TABLE", DEFAULT_TABLE),
        help=f"Projection table name (default: env GOVERNANCE_PROJECTION_TABLE "
        f"or {DEFAULT_TABLE})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the table if it already exists.",
    )
    parser.add_argument(
        "--with-fixtures",
        action="store_true",
        help="Insert a handful of synthetic items for a read-side smoke test.",
    )
    args = parser.parse_args(argv)

    try:
        return seed(
            args.endpoint_url,
            args.region,
            args.table,
            args.reset,
            args.with_fixtures,
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
