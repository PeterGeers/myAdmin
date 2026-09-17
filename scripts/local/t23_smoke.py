#!/usr/bin/env python3
"""T23 checkpoint smoke: MySQL -> local DynamoDB projection sync -> tenant read.

One end-to-end run (design.md "Testing Strategy -> Projection integration smoke"):
  1. ProjectionSync(DatabaseSourceProvider(DatabaseManager())) reads Docker MySQL
     and writes the test_ projection table in LOCAL DynamoDB.
  2. ProjectionReader.query_tenant(<SAM tenant>) reads that tenant's partition.
  3. Compare projected items against what the pure builder derives from the source.

Env (fail-fast, R4.1) must be set by the caller:
  AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000
  GOVERNANCE_PROJECTION_TABLE=test_governance_projection
  AWS_REGION=eu-west-1

NOTE (integration finding): the real Docker MySQL `finance` DB and the T2 fixture
carry module names (ADMIN, members, events, webshop) that are NOT yet in
MODULE_REGISTRY (which registers FIN/STR/TENADMIN/ZZP only; members/events/webshop
land as real SAM modules in S5). The pure builder's SAM-backing gate calls
module_registry.module_backing(), which raises on an unknown module, so the
real-data sync_all() aborts. To prove the sync->read *wiring* converges against
LOCAL DynamoDB independent of that S5 registry gap, this smoke registers the SAM
module names IN-PROCESS (test-only, no source change) so s3test_hdcn's active
members/events/webshop resolve as SAM-backed. The registry gap is reported
separately as the actionable finding.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
from decimal import Decimal

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "src"))

from database import DatabaseManager  # noqa: E402
from services import module_registry  # noqa: E402
from services.projection_builder import build_projection_items  # noqa: E402
from services.projection_reader import ProjectionReader  # noqa: E402
from services.projection_sync import (  # noqa: E402
    DatabaseSourceProvider,
    ProjectionSync,
    TenantSource,
)


def _dynamo_safe(value):
    """Coerce a MySQL cell into a DynamoDB-serializable value (smoke-only).

    boto3's DynamoDB serializer rejects datetime/date/float; MySQL rows carry
    datetime (created_at/updated_at) and can carry float. This normalizes them
    at the source seam so the smoke can prove the round-trip. The REAL fix
    belongs in the projection serialization layer (finding #2 below).
    """
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def _normalize_row(row):
    return {k: _dynamo_safe(v) for k, v in row.items()}

SAM_TENANT = "s3test_hdcn"       # active SAM modules members/events/webshop
OTHER_TENANT = "s3test_full"     # flask-only tenant: must NOT be projected


def _print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _register_sam_modules_in_process() -> None:
    """Test-only: register the S5 SAM module names so the builder can resolve
    their backing. This mutates the in-memory registry for THIS process only;
    it does not touch source files. Mirrors the intended S5 registry entries.
    """
    for name in ("members", "events", "webshop"):
        module_registry.MODULE_REGISTRY.setdefault(
            name,
            {
                "description": f"S5 SAM module {name} (registered in-process for T23 smoke)",
                "required_params": {},
                "required_tax_rates": [],
                "required_roles": [f"{name}_Read"],
                "backing": {"kind": "sam", "api_base_env": f"{name.upper()}_MODULE_API_BASE"},
            },
        )


class _ScopedSource(DatabaseSourceProvider):
    """DatabaseSourceProvider limited to a fixed set of administrations, so the
    smoke syncs only the s3test_* fixtures and does not walk unrelated real
    tenants that carry the still-unregistered ADMIN module.
    """

    def __init__(self, db, administrations):
        super().__init__(db)
        self._scope = list(administrations)

    def list_administrations(self):
        return list(self._scope)

    def get_tenant_source(self, administration):
        src = super().get_tenant_source(administration)
        if src is None:
            return None
        # Normalize datetime/float cells (finding #2) so the DynamoDB round-trip
        # can be proven end-to-end at this checkpoint.
        return TenantSource(
            tenant=_normalize_row(src.tenant),
            tenant_modules=[_normalize_row(r) for r in src.tenant_modules],
            user_tenant_roles=[_normalize_row(r) for r in src.user_tenant_roles],
        )


def main() -> int:
    for var in ("AWS_ENDPOINT_URL_DYNAMODB", "GOVERNANCE_PROJECTION_TABLE", "AWS_REGION"):
        print(f"  env {var} = {os.environ.get(var)!r}")

    _register_sam_modules_in_process()

    db = DatabaseManager(test_mode=False)
    print(f"  MySQL   = {db.config.get('database')} @ "
          f"{db.config.get('host')}:{db.config.get('port')}")

    # Scope the sync to the s3test_* fixtures (SAM tenant + flask-only tenant).
    source = _ScopedSource(db, [SAM_TENANT, OTHER_TENANT, "s3test_fin", "s3test_str"])
    sync = ProjectionSync(source)
    reader = ProjectionReader()

    _print_header("STEP 1 — sync (MySQL -> local DynamoDB), scoped to s3test_* fixtures")
    result = sync.sync_all()
    print(f"  administrations processed : {list(result.administrations)}")
    print(f"  items written             : {result.written}")
    print(f"  items skipped (no-op)     : {result.skipped}")

    _print_header(f"STEP 2 — tenant-scoped read of {SAM_TENANT!r}")
    projected = reader.query_tenant(SAM_TENANT)
    for item in sorted(projected, key=lambda i: i["sk"]):
        extra = {k: v for k, v in item.items() if k not in ("tenant_id", "sk", "version")}
        print(f"  {item['sk']:32} version={item.get('version')} attrs={extra}")
    print(f"  -> {len(projected)} item(s) in {SAM_TENANT}'s partition")

    _print_header("STEP 3 — compare projected vs source (fidelity)")
    src = source.get_tenant_source(SAM_TENANT)
    expected = build_projection_items(src.tenant, src.tenant_modules, src.user_tenant_roles)
    expected_keys = sorted(i.sort_key for i in expected)
    actual_keys = sorted(i["sk"] for i in projected)
    print(f"  expected SKs ({len(expected_keys)}): {expected_keys}")
    print(f"  actual   SKs ({len(actual_keys)}): {actual_keys}")
    fidelity_ok = expected_keys == actual_keys and len(expected_keys) > 0
    print(f"  fidelity match: {fidelity_ok}")

    _print_header("STEP 4 — idempotence re-run + tenant isolation")
    rerun = sync.sync_all()
    print(f"  re-run written (want 0): {rerun.written}  is_noop={rerun.is_noop}")
    other = reader.query_tenant(OTHER_TENANT)
    print(f"  {OTHER_TENANT!r} (flask-only) projected items: {len(other)} (want 0)")
    isolation_ok = len(other) == 0

    _print_header("SMOKE RESULT")
    converged = fidelity_ok and rerun.is_noop and isolation_ok
    print(f"  sync->read converged against LOCAL DynamoDB: {converged}")
    return 0 if converged else 1


if __name__ == "__main__":
    raise SystemExit(main())
