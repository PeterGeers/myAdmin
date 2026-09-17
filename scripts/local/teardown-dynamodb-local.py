#!/usr/bin/env python3
"""teardown-dynamodb-local.py — drop the S3 governance projection table from
local DynamoDB (the `dynamodb-local` container).

Part of the S3 spec (`s3-claims-and-projection`) Phase 0 / T0. It deletes only
the projection *table*, leaving the container itself running — bringing the
whole container down is `docker compose down` (or `docker compose stop
dynamodb-local`). Use this to get a clean table between test runs without
restarting the stack.

Idempotent: no error if the table is already absent.

Usage (from repo root, WSL):
  backend/.venv/bin/python scripts/local/teardown-dynamodb-local.py
      [--endpoint-url http://localhost:8000] [--region eu-west-1]
      [--table test_governance_projection]
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from botocore.exceptions import ClientError

DEFAULT_TABLE = "test_governance_projection"


def _dynamodb_resource(endpoint_url: str, region: str):
    """Build a boto3 DynamoDB resource pointing at local DynamoDB (dummy creds)."""
    return boto3.resource(
        "dynamodb",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id="local",
        aws_secret_access_key="local",
        aws_session_token="local",
    )


def teardown(endpoint_url: str, region: str, table_name: str) -> int:
    dynamodb = _dynamodb_resource(endpoint_url, region)
    client = dynamodb.meta.client

    print(f"Tearing down local DynamoDB table at {endpoint_url} (region {region})")
    print(f"  table = {table_name}\n")

    try:
        dynamodb.Table(table_name).delete()
        client.get_waiter("table_not_exists").wait(TableName=table_name)
        print(f"[{table_name}] deleted.")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"[{table_name}] not present — nothing to tear down.")
        else:
            raise
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drop the S3 governance projection table from local DynamoDB."
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
    args = parser.parse_args(argv)

    try:
        return teardown(args.endpoint_url, args.region, args.table)
    except Exception as exc:  # noqa: BLE001 — surface any failure to the CLI
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
