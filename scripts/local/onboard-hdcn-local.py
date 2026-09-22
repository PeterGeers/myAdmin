#!/usr/bin/env python3
"""onboard-hdcn-local.py — LOCAL DATA-TRACK FIXTURE ONLY. NOT a governance path.

============================================================================
DATA-TRACK FIXTURE — NOT THE GOVERNANCE ONBOARDING FLOW (R6.5, C-UNWIND)
============================================================================
This script is a **local dev/test DATA fixture**. It seeds enough local data to
make h-dcn *renderable* against dynamodb-local + a local MySQL — nothing more.
It is on the **data/migration track**, never the governance track.

It DOES NOT and MUST NOT substitute for the real SPA governance onboarding flow.
Real tenant onboarding + entitlement + role/scope assignment happens through the
SPA governance endpoints (Phase 6 / R8.1):
  - SysAdmin  (`/api/sysadmin/*`)     — create tenant, grant the MEMBERS
                                        entitlement, define roles.
  - Tenant-Admin (`/api/tenant-admin/*`) — assign user roles (-> user_tenant_roles)
                                        and author the members.* parameters,
                                        each of which fires enqueue_sync -> projection.

Only that governance path genuinely exercises MySQL -> enqueue_sync -> projection.
This fixture writes MySQL rows / DynamoDB items directly and runs ProjectionSync
in-process purely so a developer has *data on screen* locally; the writes here are
NOT a stand-in for, and prove nothing about, the governance channel. When you need
to validate onboarding, drive the SPA endpoints — do not run this script.

Scope of what it seeds (local-only, idempotent; does NOT touch AWS or prod):
  1. h-dcn tenant-scope params in MySQL: members.scope_dimensions (region:
     Noord/Zuid/Oost/West, required_for=[Members_CRUD])
     + members.field_overlay (a small variable field).
  2. webmaster@h-dcn.nl's all-access scope authored in user_tenant_scope
     (module=MEMBERS, scopes={"region":["*"]}), so the projected scopegrant is
     ["*"] and the general-admin path renders locally. s5d clean break (R2.2/R8.1):
     scope is sourced from user_tenant_scope, NOT a Regio_* role name.
  3. The local governance projection table + a ProjectionSync run for h-dcn against
     dynamodb-local -> module#members / config#scope / config#fields / scopegrant#.
  4. sam-members-local + h-dcn's membership-type catalog + a few members
     (Noord/Zuid) so Leden Overzicht shows data.

Run (local fixture only): backend/.venv/bin/python scripts/local/onboard-hdcn-local.py
"""
from __future__ import annotations
import os, sys, json

# --- Local env: point every fail-fast client at dynamodb-local -------------
os.environ.setdefault("AWS_ENDPOINT_URL_DYNAMODB", "http://localhost:8000")
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
os.environ.setdefault("AWS_SESSION_TOKEN", "local")
os.environ["GOVERNANCE_PROJECTION_TABLE"] = "test_governance_projection"
os.environ["MEMBERS_TABLE"] = "sam-members-local"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # repo root for sam.*

TENANT = "h-dcn"
ADMIN = "webmaster@h-dcn.nl"


def step1_params(db):
    from services.parameter_service import ParameterService
    svc = ParameterService(db)
    scope_dimensions = [{
        "key": "region",
        "label": {"nl": "Regio", "en": "Region"},
        "enabled": True,
        "values": ["Noord", "Zuid", "Oost", "West"],
        # S5d clean break (R2.2/R8.1): no Regio_* all_wildcard role — scope is authored in
        # user_tenant_scope (see step2), and the all-access sentinel is the ["*"] GRANT value.
        "required_for": ["Members_CRUD"],
    }]
    field_overlay = {
        "fields": {
            "motor_type": {"type": "string", "required": False,
                           "label": {"nl": "Motor", "en": "Motorcycle"}, "order": 10},
        },
        "overrides": {},
    }
    svc.set_param("tenant", TENANT, "members", "scope_dimensions", scope_dimensions,
                  value_type="json", created_by="onboard-hdcn-local")
    svc.set_param("tenant", TENANT, "members", "field_overlay", field_overlay,
                  value_type="json", created_by="onboard-hdcn-local")
    print("  [1] seeded members.scope_dimensions + members.field_overlay for", TENANT)


def step2_scope(db):
    # S5d clean break (R2.2/R8.1): the member-user's scope is AUTHORED in
    # user_tenant_scope (per user-per-tenant-per-module, JSON values-only), NOT
    # encoded in a Regio_* role name. All-access is the ["*"] sentinel in the
    # scopes JSON — build_scopegrant_rows projects it to scopegrant#...=["*"].
    scopes = json.dumps({"region": ["*"]})
    existing = db.execute_query(
        "SELECT id FROM user_tenant_scope WHERE email=%s AND administration=%s AND module=%s",
        (ADMIN, TENANT, "MEMBERS"), fetch=True)
    if existing:
        db.execute_query(
            "UPDATE user_tenant_scope SET scopes=%s WHERE email=%s AND administration=%s AND module=%s",
            (scopes, ADMIN, TENANT, "MEMBERS"), fetch=False, commit=True)
        print("  [2] refreshed user_tenant_scope (region=[*]) for", ADMIN)
        return
    db.execute_query(
        "INSERT INTO user_tenant_scope (email, administration, module, scopes, created_by) "
        "VALUES (%s,%s,%s,%s,%s)",
        (ADMIN, TENANT, "MEMBERS", scopes, "onboard-hdcn-local"), fetch=False, commit=True)
    print("  [2] authored all-access scope (region=[*]) in user_tenant_scope for", ADMIN)


def step3_project(db):
    from services import projection_schema as pschema
    from services.parameter_service import ParameterService
    from services.projection_sync import ProjectionSync, DatabaseSourceProvider
    # Ensure the projection table exists (create if missing).
    resource = pschema.get_dynamodb_resource() if hasattr(pschema, "get_dynamodb_resource") else None
    from services.dynamodb_client import get_dynamodb_resource
    ddb = get_dynamodb_resource()
    name = pschema.resolve_projection_table_name()
    client = ddb.meta.client
    try:
        client.describe_table(TableName=name)
        print(f"  [3] projection table {name} exists")
    except client.exceptions.ResourceNotFoundException:
        ddb.create_table(
            TableName=name,
            KeySchema=[{"AttributeName": "tenant_id", "KeyType": "HASH"},
                       {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "tenant_id", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST")
        client.get_waiter("table_exists").wait(TableName=name)
        print(f"  [3] created projection table {name}")
    sync = ProjectionSync(DatabaseSourceProvider(db), parameter_service=ParameterService(db))
    result = sync.sync_administration(TENANT)
    print(f"  [3] sync_administration({TENANT}) -> written={result.written} skipped={result.skipped}")
    # Show what landed
    from boto3.dynamodb.conditions import Key
    tbl = ddb.Table(name)
    items = tbl.query(KeyConditionExpression=Key("tenant_id").eq(TENANT)).get("Items", [])
    print(f"  [3] {TENANT} partition now has {len(items)} projected rows:")
    for it in sorted(items, key=lambda x: x["sk"]):
        print("       -", it["sk"])


def step4_members(db):
    from services.dynamodb_client import get_dynamodb_resource
    from sam.members.repository import table_design as td
    ddb = get_dynamodb_resource()
    client = ddb.meta.client
    name = td.resolve_members_table_name()
    try:
        client.describe_table(TableName=name)
        print(f"  [4] members table {name} exists")
    except client.exceptions.ResourceNotFoundException:
        ddb.create_table(
            TableName=name,
            KeySchema=[{"AttributeName": td.PARTITION_KEY_ATTR, "KeyType": "HASH"},
                       {"AttributeName": td.SORT_KEY_ATTR, "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": td.PARTITION_KEY_ATTR, "AttributeType": "S"},
                                  {"AttributeName": td.SORT_KEY_ATTR, "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST")
        client.get_waiter("table_exists").wait(TableName=name)
        print(f"  [4] created members table {name}")
    tbl = ddb.Table(name)
    # Catalog (active membership types)
    for code, nl in (("regulier", "Regulier lid"), ("erelid", "Erelid"), ("jeugd", "Jeugdlid")):
        tbl.put_item(Item=td.build_membership_type_item(TENANT, code, {
            "label": {"nl": nl, "en": code.title()}, "active": True, "order": 1}))
    # A few members across regions
    members = [
        ("M-1", "Noord", "Jan Jansen", "regulier"),
        ("M-2", "Zuid", "Piet Pietersen", "erelid"),
        ("M-3", "Noord", "Klaas Klaassen", "jeugd"),
        ("M-4", "West", "Marie de Vries", "regulier"),
    ]
    for mid, region, name_, mtype in members:
        # S5d D1/R3.4: scope is a PLAIN member field now — the retired `scope_values` bucket is
        # gone. h-dcn's `region` dimension binds to the tenant-added `overlay.region` field, a
        # SCALAR (single-valued per scope field). The seed values are already the dimension's
        # canonical spelling (Noord/Zuid/Oost/West).
        member = {
            "personal": {"name": name_, "contact": f"{mid.lower()}@h-dcn.example"},
            "membership": {"member_number": mid.replace("M-", "100"),
                           "status": "active", "membership_type": mtype},
            "overlay": {"region": region},
        }
        tbl.put_item(Item=td.build_member_item(TENANT, mid, member))
    print(f"  [4] seeded 3 membership types + {len(members)} members into {name}")


def main():
    from database import DatabaseManager
    db = DatabaseManager(test_mode=False)
    print("Onboarding h-dcn locally (MySQL + dynamodb-local)...")
    step1_params(db)
    step2_scope(db)
    step3_project(db)
    step4_members(db)
    print("DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
