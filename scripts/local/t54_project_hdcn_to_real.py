#!/usr/bin/env python3
"""t54_project_hdcn_to_real.py — ONE-OFF (s5c task 5.4). NOT a permanent fixture.

Drives the REAL governance code path (dev MySQL SoR -> ProjectionSync) but points
the projection WRITE at the REAL data-account table `governance_projection`
(account 506221081911, eu-west-1) instead of dynamodb-local.

- READ side: local dev MySQL `finance` (DB_* from backend/.env) — the governance
  SoR facts for tenant h-dcn (tenant_modules: MEMBERS active; user_tenant_roles:
  webmaster@h-dcn.nl -> Members_CRUD) are already present, seeded via the
  governance/fixture path. This script writes ZERO MySQL rows.
- WRITE side: real table via ProjectionSync (the sole writer). We set
  GOVERNANCE_PROJECTION_TABLE=governance_projection, UNSET AWS_ENDPOINT_URL_DYNAMODB
  (so boto3 hits real AWS, not dynamodb-local), and force the data-account profile
  by clearing the identity-account keys that backend/.env injects.

Run:
  AWS_PROFILE=nonprofit-deploy backend/.venv/bin/python \
    scripts/local/t54_project_hdcn_to_real.py h-dcn
"""
from __future__ import annotations
import os, sys

TENANT = sys.argv[1] if len(sys.argv) > 1 else "h-dcn"

# backend/src on path (DatabaseManager, services.*)
_here = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_here, "..", "..", "backend", "src"))

# --- Load dev .env for DB_* (MySQL SoR), THEN scrub the AWS identity-account
#     keys it injects so the data-account profile (AWS_PROFILE) is used for the
#     DynamoDB write. -------------------------------------------------------
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_here, "..", "..", "backend", ".env"))

# Force the projection WRITE at the REAL data-account table + real AWS endpoint.
os.environ["GOVERNANCE_PROJECTION_TABLE"] = "governance_projection"
os.environ.pop("AWS_ENDPOINT_URL_DYNAMODB", None)  # unset => real AWS
os.environ["AWS_REGION"] = "eu-west-1"
# Clear the identity-account static keys from .env so boto3 resolves AWS_PROFILE
# (nonprofit-deploy) from ~/.aws instead. Fail loudly if no profile was given.
os.environ.pop("AWS_ACCESS_KEY_ID", None)
os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
os.environ.pop("AWS_SESSION_TOKEN", None)
if not os.environ.get("AWS_PROFILE"):
    raise SystemExit("AWS_PROFILE must be set (expected nonprofit-deploy) — refusing "
                     "to write the real projection without an explicit data-account profile.")

# Sanity: confirm which account boto3 resolves BEFORE writing.
import boto3  # noqa: E402
ident = boto3.client("sts", region_name="eu-west-1").get_caller_identity()
print(f"[t54] boto3 STS account = {ident['Account']} arn={ident['Arn']}")
if ident["Account"] != "506221081911":
    raise SystemExit(f"[t54] Refusing: resolved account {ident['Account']} is NOT the "
                     f"data account 506221081911.")

from database import DatabaseManager  # noqa: E402
from services.parameter_service import ParameterService  # noqa: E402
from services.projection_sync import ProjectionSync, DatabaseSourceProvider  # noqa: E402
from services import projection_schema as pschema  # noqa: E402

db = DatabaseManager(test_mode=False)
print(f"[t54] projection target table = {pschema.resolve_projection_table_name()}")

sync = ProjectionSync(DatabaseSourceProvider(db), parameter_service=ParameterService(db))
result = sync.sync_administration(TENANT)
print(f"[t54] sync_administration({TENANT}) -> written={result.written} "
      f"skipped={result.skipped} administrations={result.administrations}")

# Read back what landed in the REAL table for this tenant.
from boto3.dynamodb.conditions import Key  # noqa: E402
tbl = pschema.get_projection_table_resource()
items = tbl.query(KeyConditionExpression=Key("tenant_id").eq(TENANT)).get("Items", [])
print(f"[t54] REAL table now has {len(items)} rows for {TENANT}:")
for it in sorted(items, key=lambda x: x["sk"]):
    extra = ""
    if it["sk"].startswith("module#"):
        extra = f"  is_active={it.get('is_active')}"
    print("   -", it["sk"], extra)
print("[t54] DONE")
