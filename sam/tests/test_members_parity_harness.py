"""
S5 Task 6.0 — tests that RUN the Members parity/walkthrough harness and assert on the report.

These are the pytest-driven, CI-runnable form of the hands-on walkthrough R7.1 mandates
BEFORE any human review (task 6.2): they exercise the migrated module end-to-end for the
pilot tenant ``h-dcn`` / region across the four parity dimensions (authz incl. scope, data,
API contract, workflow) and assert the harness's :class:`ParityReport` comes back green with
a full route-by-route checklist.

This is a **test-pool/local walkthrough**, NOT a live-traffic soak and NOT a comparison
against the external h-dcn app — h-dcn Members is demo-only (real data in a Google Sheet)
and the existing app is a separate codebase. The module is exercised over the in-memory
``FakeDynamoTable`` + ``DynamoDbMembersRepository`` with h-dcn's config/hooks/seeded catalog
wired as data, so there is no live AWS / Google / external-app dependency.

Validates: Requirements R7.1, R7.2
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.tests.members_parity_harness import (
    Dimension,
    MembersParityHarness,
    Outcome,
    ParityReport,
    run_parity_walkthrough,
)
from sam.members.handler.routes import route_names


# ── The full walkthrough (the report the Go/No-Go consumes) ────────────────────────────


@pytest.fixture(scope="module")
def report() -> ParityReport:
    """Run the whole parity walkthrough once for the pilot tenant/region."""
    return run_parity_walkthrough(tenant_id="h-dcn", region="Noord")


def test_parity_walkthrough_all_asserted_checks_pass(report):
    # Every automated (PASS/FAIL) check must pass; MANUAL items are checklist flags, not
    # assertions. A failure here is a parity gap the module must close before the Go/No-Go.
    failures = report.failures()
    assert failures == [], "parity failures:\n" + "\n".join(
        f"  [{c.dimension.value}] {c.hdcn_behaviour} → {c.migrated_route}: {c.observed}"
        for c in failures
    )
    assert report.all_passed


def test_report_covers_all_four_dimensions(report):
    for dimension in Dimension:
        assert report.by_dimension(dimension), f"no checks recorded for {dimension.value}"


def test_report_has_manual_walkthrough_items_for_ux(report):
    # The harness must FLAG (not assert) the look & feel / UX behaviours for task 6.2.
    manual = report.manual_items()
    assert manual, "expected at least one MANUAL walkthrough item (look & feel / UX)"
    assert any("look & feel" in c.hdcn_behaviour.lower() for c in manual)


# ── Dimension 3: the route-by-route parity checklist ───────────────────────────────────


def test_api_contract_exercises_every_declared_route(report):
    # The route map is the union of h-dcn's ~18 handler behaviours + the catalog group; the
    # checklist must exercise every declared route (a missing route is a parity gap).
    declared = set(route_names())
    covered = report.routes_covered()
    missing = declared - covered
    assert not missing, f"routes never exercised by the harness: {sorted(missing)}"


def test_api_contract_covers_the_hdcn_behaviour_groups(report):
    # Spot-check that each h-dcn behaviour group is represented among the exercised routes.
    covered = report.routes_covered()
    # Member CRUD
    assert {"create_member", "list_members", "get_member", "update_member",
            "delete_member", "export_members"} <= covered
    # Membership lifecycle
    assert {"create_membership", "list_memberships", "get_membership",
            "update_membership", "delete_membership", "transition_membership",
            "bulk_transition_memberships"} <= covered
    # Delegates
    assert {"manage_delegates", "send_delegate_invitation"} <= covered
    # Payments
    assert {"get_member_payments"} <= covered
    # Catalog (Lidmaatschap Beheer)
    assert {"list_membership_types", "get_membership_type", "create_membership_type",
            "update_membership_type", "deactivate_membership_type"} <= covered


# ── Focused per-dimension assertions (each dimension is truly exercised) ───────────────


def test_authz_dimension_covers_401_403_and_scope(report):
    authz = report.by_dimension(Dimension.AUTHZ)
    behaviours = {c.hdcn_behaviour for c in authz}
    assert "reject unauthenticated caller" in behaviours
    assert "forbid caller lacking members:read" in behaviours
    assert "region-scoped caller sees only their region" in behaviours
    assert "admin/Regio_All sees tenant-wide" in behaviours
    assert any("verify-before-trust" in b for b in behaviours)
    assert all(c.outcome is Outcome.PASS for c in authz)


def test_data_dimension_covers_config_dropdown_and_backfill(report):
    data_checks = report.by_dimension(Dimension.DATA)
    behaviours = {c.hdcn_behaviour for c in data_checks}
    assert any("field config" in b for b in behaviours)
    assert any("only ACTIVE" in b for b in behaviours)
    assert any("backfilled member" in b for b in behaviours)
    # S5d D1: scope is a plain `overlay.region` field now (no `scope_values` bucket).
    assert any("overlay.region" in b for b in behaviours)
    assert all(c.outcome is Outcome.PASS for c in data_checks)


def test_workflow_dimension_walks_full_lifecycle(report):
    wf = report.by_dimension(Dimension.WORKFLOW)
    behaviours = {c.hdcn_behaviour for c in wf}
    # The full happy-path chain plus the two guard/denial checks.
    assert any("application→pending (approved)" in b for b in behaviours)
    assert any("pending→active" in b for b in behaviours)
    assert any("lapsed→left" in b for b in behaviours)
    assert any("denied without approval flag" in b for b in behaviours)
    assert any("undeclared transition edge is denied" in b for b in behaviours)
    assert all(c.outcome is Outcome.PASS for c in wf)


# ── The report renders to a human-readable walkthrough artifact (task 6.2 evidence) ────


def test_report_renders_walkthrough_artifact(report):
    text = report.render()
    assert "parity/walkthrough report" in text
    assert "NOT a live-traffic soak" in text
    for dimension in Dimension:
        assert dimension.value in text


def test_report_to_dict_is_json_serializable(report):
    import json

    payload = report.to_dict()
    # Round-trips through json without error and preserves the checks.
    restored = json.loads(json.dumps(payload))
    assert restored["tenant_id"] == "h-dcn"
    assert restored["region"] == "Noord"
    assert len(restored["checks"]) == len(report.checks)


# ── The harness is reusable / re-runnable in isolation (no shared state leakage) ───────


def test_harness_is_repeatable():
    # Two independent runs each produce a green report over their own in-memory table.
    r1 = MembersParityHarness().run()
    r2 = MembersParityHarness().run()
    assert r1.all_passed and r2.all_passed
    assert r1.routes_covered() == r2.routes_covered()
