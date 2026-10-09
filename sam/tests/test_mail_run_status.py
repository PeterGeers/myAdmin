"""
Mail-spec task 3.2 — unit tests for the SEND-RUN STATUS read SERVICE
(:class:`~sam.members.domain.mail_run_status.MailRunStatusService`; R9.2/R9.3).

These pin the R9.3 role-scoped filtering in ISOLATION over an in-memory fake store (no edge, no
AWS): a plain user sees only runs they triggered (``triggered_by == sub``); an admin sees all the
tenant's runs; drill-down applies the same scope (an out-of-scope run reads as absent, no probe).
The route-level wiring (gating, 401/403/404 mapping, JSON shaping) is covered by
``test_mail_run_status_routes.py``.

Validates: Requirements 9.2, 9.3.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.mail_run_status import MailRunStatusService

TENANT = "tenant-a"
SUB_A = "sub-a"
SUB_B = "sub-b"


class _FakeStore:
    """Tenant-pinned in-memory store satisfying the MailRunStore seam."""

    def __init__(self):
        self.runs = {}
        self.failures = {}

    def add_run(self, run_id, *, triggered_by, created_at, **tally):
        self.runs[(TENANT, run_id)] = {
            "run_id": run_id, "triggered_by": triggered_by, "created_at": created_at, **tally
        }

    def add_failure(self, run_id, **entry):
        self.failures.setdefault((TENANT, run_id), []).append(dict(entry))

    def list_mail_runs(self, tenant_id):
        runs = [dict(v) for (t, _r), v in self.runs.items() if t == tenant_id]
        runs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return runs

    def get_mail_run(self, tenant_id, run_id):
        item = self.runs.get((tenant_id, run_id))
        return dict(item) if item is not None else None

    def list_mail_run_failures(self, tenant_id, run_id):
        return [dict(f) for f in self.failures.get((tenant_id, run_id), [])]

    def delete_mail_run(self, tenant_id, run_id):
        self.runs.pop((tenant_id, run_id), None)
        self.failures.pop((tenant_id, run_id), None)


@pytest.fixture()
def service():
    store = _FakeStore()
    store.add_run("own-1", triggered_by=SUB_A, created_at="2026-01-01T00:00:00Z", sent=1, failed=0)
    store.add_run("own-2", triggered_by=SUB_A, created_at="2026-01-02T00:00:00Z", sent=2, failed=1)
    store.add_run("other", triggered_by=SUB_B, created_at="2026-01-03T00:00:00Z", sent=5, failed=0)
    store.add_failure("own-2", address="x@y.z", status="failed", reason="MessageRejected")
    return MailRunStatusService(store)


# ── list scoping ────────────────────────────────────────────────────────────────────────


def test_list_runs_plain_user_sees_only_own(service):
    runs = service.list_runs(TENANT, requester_sub=SUB_A, admin=False)
    assert {r["run_id"] for r in runs} == {"own-1", "own-2"}


def test_list_runs_admin_sees_all(service):
    runs = service.list_runs(TENANT, requester_sub=SUB_A, admin=True)
    assert {r["run_id"] for r in runs} == {"own-1", "own-2", "other"}


def test_list_runs_no_sub_plain_user_sees_nothing(service):
    # Fail-closed: a caller with no verified sub owns nothing, so a non-admin sees no runs.
    assert service.list_runs(TENANT, requester_sub=None, admin=False) == []


# ── drill-down scoping ────────────────────────────────────────────────────────────────


def test_get_run_own_returns_tally_and_failures(service):
    view = service.get_run(TENANT, "own-2", requester_sub=SUB_A, admin=False)
    assert view is not None
    assert view.run["run_id"] == "own-2"
    assert [f["address"] for f in view.failures] == ["x@y.z"]


def test_get_run_other_users_run_is_none_for_plain_user(service):
    # Exists in the tenant but triggered by SUB_B → None (no probe) for a non-admin SUB_A.
    assert service.get_run(TENANT, "other", requester_sub=SUB_A, admin=False) is None


def test_get_run_other_users_run_visible_to_admin(service):
    view = service.get_run(TENANT, "other", requester_sub=SUB_A, admin=True)
    assert view is not None and view.run["run_id"] == "other"


def test_get_run_absent_is_none_for_everyone(service):
    assert service.get_run(TENANT, "nope", requester_sub=SUB_A, admin=False) is None
    assert service.get_run(TENANT, "nope", requester_sub=SUB_A, admin=True) is None


def test_get_run_with_no_failures_returns_empty_tuple(service):
    view = service.get_run(TENANT, "own-1", requester_sub=SUB_A, admin=False)
    assert view is not None
    assert view.failures == ()


# ── delete scoping (R9.6 retention — same scope as get_run) ───────────────────────────


def test_delete_run_own_deletes_and_returns_true(service):
    # A plain user may delete their OWN run — the tally AND its failures are purged.
    assert service.delete_run(TENANT, "own-2", requester_sub=SUB_A, admin=False) is True
    # Gone: a subsequent read reports absent (and the failure sub-record is cleaned up).
    assert service.get_run(TENANT, "own-2", requester_sub=SUB_A, admin=False) is None


def test_delete_run_other_users_run_is_not_deleted_for_plain_user(service):
    # Exists in the tenant but triggered by SUB_B → not visible to non-admin SUB_A: returns the
    # not-visible signal (False, → 404 at the edge, no probe) and leaves the run intact.
    assert service.delete_run(TENANT, "other", requester_sub=SUB_A, admin=False) is False
    assert service.get_run(TENANT, "other", requester_sub=SUB_A, admin=True) is not None


def test_delete_run_other_users_run_deletable_by_admin(service):
    assert service.delete_run(TENANT, "other", requester_sub=SUB_A, admin=True) is True
    assert service.get_run(TENANT, "other", requester_sub=SUB_A, admin=True) is None


def test_delete_run_absent_returns_false_for_everyone(service):
    assert service.delete_run(TENANT, "nope", requester_sub=SUB_A, admin=False) is False
    assert service.delete_run(TENANT, "nope", requester_sub=SUB_A, admin=True) is False


def test_delete_run_no_sub_plain_user_cannot_delete(service):
    # Fail-closed: a caller with no verified sub owns nothing, so a non-admin cannot delete.
    assert service.delete_run(TENANT, "own-1", requester_sub=None, admin=False) is False
    assert service.get_run(TENANT, "own-1", requester_sub=SUB_A, admin=True) is not None
