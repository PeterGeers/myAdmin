"""
Smoke test for the Phase-1 E2E harness fixture (spec 03, task 1.1).

Proves two things about `conftest.py`'s scaffold WITHOUT requiring the container:

1. The committed real-data fixture loads and has the expected top-level shape — a pure file
   read that runs even on an ordinary unit run (no local DynamoDB).
2. The container-backed fixtures SKIP cleanly when `AWS_ENDPOINT_URL_DYNAMODB` is unset / the
   endpoint is unreachable, rather than erroring. `test_seeded_table_available_or_skips`
   depends on `seeded_config_fields_table`; with no container that dependency chains up to
   `local_dynamodb_endpoint`'s `pytest.skip`, so this test reports SKIPPED — exactly the
   behavior the task requires (unit runs unaffected).

The authoritative invariant engine + round-trip cases arrive in tasks 1.2–1.4 and are
EXPECTED red until Phase 2.
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_real_fixture_loads_with_expected_shape(real_hdcn_overlay):
    # Pure file read — no container needed. Sanity-pin the real h-dcn shape the harness seeds.
    assert real_hdcn_overlay["tenant_id"] == "h-dcn"
    for key in ("fields", "overrides", "functional_groups"):
        assert key in real_hdcn_overlay, f"real overlay must carry '{key}'"
    assert real_hdcn_overlay["functional_groups"], "catalog must be non-empty (truncation guard)"


@pytest.mark.e2e
def test_seeded_table_available_or_skips(seeded_config_fields_table):
    # When the container is up this asserts the seeded row is readable; when it is absent the
    # fixture chain SKIPS (via local_dynamodb_endpoint) so the unit run is unaffected.
    table = seeded_config_fields_table["table"]
    tenant_id = seeded_config_fields_table["tenant_id"]
    from services import projection_schema as schema

    resp = table.get_item(
        Key=schema.build_key(
            tenant_id, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS)
        )
    )
    item = resp.get("Item")
    assert item is not None, "seeded h-dcn config#fields row must be readable from local DynamoDB"
    assert item["functional_groups"], "seeded catalog must survive the round-trip (non-empty)"
