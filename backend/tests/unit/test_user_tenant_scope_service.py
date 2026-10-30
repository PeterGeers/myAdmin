"""
Unit tests for UserTenantScopeService (s5d task 5.1).

Covers the SERVICE layer for ``user_tenant_scope`` (read/write/validate/enqueue):
- set -> get round-trip (set reflects exactly what was passed, canonical spelling)
- per-tenant + per-module isolation (a write scopes its query to (email, admin, module))
- atomic overwrite (second set replaces, not merges)
- clear -> delete -> get returns empty
- unknown dimension rejected; unknown value rejected; ["*"] accepted
- enqueue_sync fired on write AND on delete; enqueue failure never breaks the write
- user_tenant_roles never touched (no query mentions it)
- canonical-equality validation (case/diacritic/separator variant stored as canonical)

Uses a lightweight in-memory ``DatabaseManager`` fake modelling the table's UNIQUE
(email, administration, module) key — NO real DB, NO mysql.connector, NO os.environ,
NO load_dotenv, NO sys.path manipulation (steering 34).
"""

import json

import pytest

from services.user_tenant_scope_service import (
    WILDCARD_VALUE,
    ScopeValidationError,
    UserTenantScopeService,
)

MODULE = "MEMBERS"
TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
EMAIL = "member-test@example.com"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDB:
    """In-memory ``DatabaseManager`` stand-in for ``user_tenant_scope``.

    Models just enough SQL to exercise the service: SELECT / INSERT ... ON
    DUPLICATE KEY UPDATE / DELETE keyed on (email, administration, module). Records
    every executed query so tests can assert tenant isolation and that
    ``user_tenant_roles`` is never touched.
    """

    def __init__(self):
        # key: (email, administration, module) -> scopes-json (str)
        self.rows: dict[tuple[str, str, str], str] = {}
        self.queries: list[str] = []

    def execute_query(self, query, params=None, fetch=False, commit=False):
        self.queries.append(query)
        params = params or ()
        q = " ".join(query.split()).upper()

        if q.startswith("SELECT"):
            email, admin, module = params
            key = (email, admin, module)
            if key in self.rows:
                return [{"scopes": self.rows[key]}]
            return []

        if q.startswith("INSERT INTO USER_TENANT_SCOPE"):
            email, admin, module, scopes_json, _created_by = params
            self.rows[(email, admin, module)] = scopes_json
            return None

        if q.startswith("DELETE FROM USER_TENANT_SCOPE"):
            email, admin, module = params
            self.rows.pop((email, admin, module), None)
            return None

        raise AssertionError(f"Unexpected query: {query}")


class FakeParameterService:
    """Read-only ``members.scope_dimensions`` provider for validation."""

    def __init__(self, dimensions_by_tenant):
        # tenant -> list[dimension dicts]
        self._dims = dimensions_by_tenant

    def get_param(self, namespace, key, tenant=None, role=None, user=None):
        assert namespace == "members"
        assert key == "scope_dimensions"
        return self._dims.get(tenant)


class SpyEnqueue:
    """Records the administrations enqueue_sync was called with."""

    def __init__(self, raises=False):
        self.calls: list[str] = []
        self.raises = raises

    def __call__(self, administration):
        self.calls.append(administration)
        if self.raises:
            raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REGION_DIMENSION = {
    "key": "region",
    "enabled": True,
    "values": ["Noord-Holland", "Oost", "Friesland"],
}
_AGE_DIMENSION = {
    "key": "age_group",
    "enabled": True,
    "values": ["U15", "U17"],
}


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def params():
    return FakeParameterService(
        {
            TENANT_A: [dict(_REGION_DIMENSION), dict(_AGE_DIMENSION)],
            TENANT_B: [dict(_REGION_DIMENSION)],
        }
    )


@pytest.fixture
def enqueue():
    return SpyEnqueue()


@pytest.fixture
def service(db, params, enqueue):
    return UserTenantScopeService(db, params, enqueue_sync=enqueue)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_set_then_get_returns_the_scopes(service):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {"region": ["Oost"]}


def test_get_absent_record_returns_empty_dict(service):
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {}


def test_set_multi_value_grant_round_trips(service):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost", "Friesland"]})
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {
        "region": ["Oost", "Friesland"]
    }


def test_set_multi_dimension_grant_round_trips(service):
    service.set_scope(
        EMAIL, TENANT_A, MODULE, {"region": ["Oost"], "age_group": ["U15"]}
    )
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {
        "region": ["Oost"],
        "age_group": ["U15"],
    }


# ---------------------------------------------------------------------------
# Atomic overwrite
# ---------------------------------------------------------------------------


def test_second_set_replaces_not_merges(service):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Friesland"]})
    # Overwrite, not merge: Oost is gone.
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {"region": ["Friesland"]}


def test_overwrite_drops_a_dimension_that_is_no_longer_present(service):
    service.set_scope(
        EMAIL, TENANT_A, MODULE, {"region": ["Oost"], "age_group": ["U15"]}
    )
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {"region": ["Oost"]}


# ---------------------------------------------------------------------------
# Clear -> delete
# ---------------------------------------------------------------------------


def test_clear_all_deletes_row_and_get_returns_empty(service, db):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    assert db.rows  # row exists
    service.set_scope(EMAIL, TENANT_A, MODULE, {})
    assert not db.rows  # row deleted
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {}


def test_grant_with_only_empty_lists_deletes_row(service, db):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    result = service.set_scope(EMAIL, TENANT_A, MODULE, {"region": []})
    assert result == {}
    assert not db.rows


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_dimension_rejected(service):
    with pytest.raises(ScopeValidationError):
        service.set_scope(EMAIL, TENANT_A, MODULE, {"nope": ["Oost"]})


def test_unknown_value_rejected(service):
    with pytest.raises(ScopeValidationError):
        service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Atlantis"]})


def test_wildcard_accepted(service):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": [WILDCARD_VALUE]})
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {"region": [WILDCARD_VALUE]}


def test_disabled_dimension_is_unknown(db, enqueue):
    params = FakeParameterService(
        {TENANT_A: [{"key": "region", "enabled": False, "values": ["Oost"]}]}
    )
    svc = UserTenantScopeService(db, params, enqueue_sync=enqueue)
    with pytest.raises(ScopeValidationError):
        svc.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})


def test_validation_failure_writes_nothing(service, db, enqueue):
    with pytest.raises(ScopeValidationError):
        service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Atlantis"]})
    assert not db.rows
    assert enqueue.calls == []  # no enqueue on a rejected write


# ---------------------------------------------------------------------------
# Canonical-equality validation
# ---------------------------------------------------------------------------


def test_case_variant_accepted_and_stored_canonical(service):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["oost"]})
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {"region": ["Oost"]}


def test_separator_variant_accepted_and_stored_canonical(service):
    # "noord holland" (space) canonically equals "Noord-Holland" (hyphen).
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["noord holland"]})
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {"region": ["Noord-Holland"]}


def test_values_emitted_in_declared_order_deduplicated(service):
    # Input out of order + a duplicate variant -> declared order, de-duplicated.
    service.set_scope(
        EMAIL, TENANT_A, MODULE, {"region": ["friesland", "Oost", "OOST"]}
    )
    assert service.get_scope(EMAIL, TENANT_A, MODULE) == {
        "region": ["Oost", "Friesland"]
    }


# ---------------------------------------------------------------------------
# enqueue_sync
# ---------------------------------------------------------------------------


def test_enqueue_sync_fired_on_write(service, enqueue):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    assert enqueue.calls == [TENANT_A]


def test_enqueue_sync_fired_on_delete(service, enqueue):
    service.set_scope(EMAIL, TENANT_A, MODULE, {})
    assert enqueue.calls == [TENANT_A]


def test_enqueue_sync_failure_does_not_break_write(db, params):
    enqueue = SpyEnqueue(raises=True)
    svc = UserTenantScopeService(db, params, enqueue_sync=enqueue)
    # Must not raise even though enqueue_sync blows up.
    result = svc.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    assert result == {"region": ["Oost"]}
    assert svc.get_scope(EMAIL, TENANT_A, MODULE) == {"region": ["Oost"]}
    # Bug 1 fix (R2.2): a FAILING drain is now bounded-retried, so it may fire more than
    # once — but only ever for THIS tenant, and the write still commits and never raises.
    assert enqueue.calls  # the drain was attempted
    assert set(enqueue.calls) == {TENANT_A}


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_per_tenant_isolation(service):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    # tenant B has no grant for this user.
    assert service.get_scope(EMAIL, TENANT_B, MODULE) == {}


def test_per_module_isolation(service):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    assert service.get_scope(EMAIL, TENANT_A, "EVENTS") == {}


def test_write_query_is_tenant_and_module_scoped(service, db):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    # The stored key carries the exact (email, admin, module) triple.
    assert (EMAIL, TENANT_A, MODULE) in db.rows


def test_never_touches_user_tenant_roles(service, db):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["Oost"]})
    service.get_scope(EMAIL, TENANT_A, MODULE)
    service.set_scope(EMAIL, TENANT_A, MODULE, {})
    assert all("USER_TENANT_ROLES" not in q.upper() for q in db.queries)


def test_blank_tenant_rejected(service):
    with pytest.raises(ValueError):
        service.set_scope(EMAIL, "", MODULE, {"region": ["Oost"]})


# ---------------------------------------------------------------------------
# Stored shape
# ---------------------------------------------------------------------------


def test_stored_scopes_is_valid_json_of_the_normalized_grant(service, db):
    service.set_scope(EMAIL, TENANT_A, MODULE, {"region": ["oost"]})
    stored = db.rows[(EMAIL, TENANT_A, MODULE)]
    assert json.loads(stored) == {"region": ["Oost"]}


# ───────────────────────────────────────────────────────────────────────────────────────
# Bug 1 PRESERVATION property tests (spec member-scope-stale-projection-and-pagination-
# undercount, task 3 / Property 2). Observation-first: these encode behaviour OBSERVED on the
# UNFIXED code so a later fix cannot regress it. They MUST PASS on unfixed code.
#
# Property 2 (Preservation) facet owned here: a COMMITTED MySQL scope write stays committed
# even when the on-change projection drain (enqueue_sync) fails — the write is decoupled from
# propagation and NEVER rolled back for a propagation error (R3.1). The service swallows the
# drain failure (today's _fire_enqueue_sync logs-and-returns) and the write is unaffected.
#
# Validates: Requirements 3.1
# ───────────────────────────────────────────────────────────────────────────────────────

from hypothesis import given, settings
from hypothesis import strategies as st

# A grant over the TENANT_A dimensions the `params` fixture declares (region / age_group),
# so every generated grant is VALID and lands in MySQL. We draw non-empty subsets of the
# declared canonical values (plus the ["*"] wildcard) so the write always persists a row.
_REGION_VALUES = ["Noord-Holland", "Oost", "Friesland"]
_AGE_VALUES = ["U15", "U17"]


@st.composite
def _valid_grant(draw):
    """A non-empty, VALID grant for TENANT_A (so set_scope always writes a row)."""
    grant: dict[str, list[str]] = {}
    region = draw(
        st.one_of(
            st.just(["*"]),
            st.lists(
                st.sampled_from(_REGION_VALUES), min_size=1, max_size=3, unique=True
            ),
        )
    )
    grant["region"] = region
    if draw(st.booleans()):
        grant["age_group"] = draw(
            st.one_of(
                st.just(["*"]),
                st.lists(
                    st.sampled_from(_AGE_VALUES), min_size=1, max_size=2, unique=True
                ),
            )
        )
    return grant


def _params_for_tenant_a():
    return FakeParameterService(
        {
            TENANT_A: [dict(_REGION_DIMENSION), dict(_AGE_DIMENSION)],
            TENANT_B: [dict(_REGION_DIMENSION)],
        }
    )


@settings(max_examples=100)
@given(grant=_valid_grant())
def test_property_committed_write_survives_a_drain_failure(grant):
    """Preservation (R3.1): a drain failure never breaks or rolls back the MySQL write.

    For ANY valid grant, with the on-change ``enqueue_sync`` forced to blow up, ``set_scope``
    still returns the normalized grant AND the row stays readable from MySQL — the write is
    decoupled from propagation and committed regardless. This is the UNFIXED behaviour (the
    failure is swallowed); the Bug-1 fix must keep the write committed while it makes the
    drain failure observable/retried.
    """
    db = FakeDB()
    svc = UserTenantScopeService(
        db, _params_for_tenant_a(), enqueue_sync=SpyEnqueue(raises=True)
    )

    result = svc.set_scope(EMAIL, TENANT_A, MODULE, grant)

    # The committed write is unaffected by the drain failure: the returned grant round-trips.
    assert svc.get_scope(EMAIL, TENANT_A, MODULE) == result
    # And the underlying row is actually present in MySQL (the write landed + committed).
    assert (EMAIL, TENANT_A, MODULE) in db.rows


@settings(max_examples=100)
@given(grant=_valid_grant())
def test_property_drain_failure_still_fires_enqueue_and_never_raises(grant):
    """Preservation (R3.1): the drain IS attempted (enqueue fired) and its failure is swallowed.

    The preservation guarantee owned here (R3.1) is that the write is DECOUPLED: the trigger
    is fired for the tenant and the exception NEVER propagates into the write path, across
    random valid grants. The Bug-1 fix (R2.2) now bounded-RETRIES a failing drain, so the
    trigger may fire more than once — but only ever for THIS tenant — and still never raises.
    """
    enqueue = SpyEnqueue(raises=True)
    svc = UserTenantScopeService(FakeDB(), _params_for_tenant_a(), enqueue_sync=enqueue)

    # Must not raise even though the drain blows up.
    svc.set_scope(EMAIL, TENANT_A, MODULE, grant)

    # The drain was attempted (fired at least once) and only ever for this tenant. The exact
    # count is not pinned: the fix retries a failing drain (R2.2), so >1 attempt is expected.
    assert enqueue.calls
    assert set(enqueue.calls) == {TENANT_A}


@settings(max_examples=100)
@given(grant=_valid_grant())
def test_property_clear_after_write_deletes_and_survives_drain_failure(grant):
    """Preservation (R3.1): clearing a grant deletes the row and survives a drain failure too.

    A clear (empty grant) is the delete path; it must also commit regardless of the drain
    outcome. For any prior valid grant, clearing with a failing drain removes the row and
    returns ``{}`` without raising.
    """
    db = FakeDB()
    svc = UserTenantScopeService(
        db, _params_for_tenant_a(), enqueue_sync=SpyEnqueue(raises=True)
    )
    svc.set_scope(EMAIL, TENANT_A, MODULE, grant)
    assert (EMAIL, TENANT_A, MODULE) in db.rows

    cleared = svc.set_scope(EMAIL, TENANT_A, MODULE, {})

    assert cleared == {}
    assert (EMAIL, TENANT_A, MODULE) not in db.rows


# ═══════════════════════════════════════════════════════════════════════════════════════
# BUG 1 EXPLORATION TEST — on-change drain failure is silently swallowed (propagation miss).
#
# Spec: .kiro/specs/member-scope-stale-projection-and-pagination-undercount
# Task 1 — Property 1 (Bug Condition), drain-swallow half. Requirements 1.1, 1.2, 1.3.
#
# CRITICAL: this test MUST FAIL on the UNFIXED code — the failure CONFIRMS the bug.
# DO NOT "fix" the test or the code to make it pass; the fix lands in spec task 4 and flips
# this test green (it encodes the expected post-fix behaviour).
#
# Companion to test_projection_sync.py::test_bug1_stale_scope_projection_not_propagated_*.
# That test reproduces the stale-PROJECTION symptom on the SAM plane; THIS test observes the
# upstream CAUSE on the Flask/MySQL plane: UserTenantScopeService._fire_enqueue_sync currently
# wraps the on-change drain in a broad `except Exception` that logs a warning and RETURNS —
# the failure is swallowed with NO surfaced/retried signal (bugfix.md 1.1, R2.2). So a lost
# on-change propagation is invisible in production and nothing retries it.
#
# Scoped-PBT approach (reproducibility): the concrete confirmed case — widening
# peter@pgeers.nl / region to ["*"] for h-dcn / MEMBERS while the enqueue_sync drain fails.
# ═══════════════════════════════════════════════════════════════════════════════════════

_BUG1_TENANT = "h-dcn"
_BUG1_USER = "peter@pgeers.nl"


class _ObservableEnqueue:
    """An enqueue_sync spy that ALWAYS fails, and exposes whether the failure was SURFACED or
    RETRIED by the service.

    On UNFIXED code the service calls this exactly once and swallows the raised error, so:
      - ``calls`` == 1 (fired once, no retry), and
      - no observability signal is recorded anywhere the service can reach.

    The post-fix behaviour (R2.2) makes a drain failure observable/retried rather than silently
    swallowed. This spy models the simplest observable contract the fix can satisfy: the service
    notifies a failure sink (``on_failure``) and/or retries (``calls`` > 1). The test asserts at
    least one of those is true — which is FALSE today, so the test FAILS (confirming the bug).
    """

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, administration):
        self.calls.append(administration)
        raise RuntimeError(
            "simulated on-change projection drain failure (bugfix.md 1.1)"
        )


def test_bug1_enqueue_drain_failure_is_observable_or_retried():
    """Bug 1 (cause): a failed on-change drain SHALL be surfaced/retried, not silently swallowed.

    EXPECTED OUTCOME ON UNFIXED CODE: **FAIL** — ``_fire_enqueue_sync`` catches the raised drain
    error, logs a warning, and returns with NO surfaced/retried signal the service exposes. The
    scope write still commits (that part is correct and must be preserved, R3.1), but the
    propagation miss is invisible: there is no failure sink the service notified and no retry.

    This test encodes the expected post-fix behaviour (R2.2): the service makes the drain
    failure observable (a failure-signal hook the caller/metrics can see) and/or retries it.
    On today's code neither happens → the observability assertion FAILS, confirming the bug.

    Validates: Requirements 1.1, 1.2, 1.3
    """
    db = FakeDB()
    params = FakeParameterService({TENANT_A: [dict(_REGION_DIMENSION)]})
    # Reuse TENANT_A's declared region dimension so the ["*"] grant validates; the confirmed
    # production coordinates (h-dcn / peter@pgeers.nl) are mirrored in the assertion message.
    enqueue = _ObservableEnqueue()

    # A post-fix service is expected to accept an observability sink so a failed drain is
    # SURFACED. On the unfixed service this kwarg does not exist, which is itself part of the
    # missing-observability bug — so we probe for it defensively and treat "no sink wired" as
    # "not observable".
    surfaced: list[dict] = []

    svc = UserTenantScopeService(db, params, enqueue_sync=enqueue)
    # If the fix adds an on-failure hook, wire it; absent today, this attribute won't exist.
    if hasattr(svc, "on_enqueue_failure"):
        svc.on_enqueue_failure = lambda **info: surfaced.append(info)

    # The scope write MUST still succeed (write decoupled from propagation — R3.1 preserved).
    result = svc.set_scope(EMAIL, TENANT_A, MODULE, {"region": [WILDCARD_VALUE]})
    assert result == {"region": [WILDCARD_VALUE]}
    assert svc.get_scope(EMAIL, TENANT_A, MODULE) == {"region": [WILDCARD_VALUE]}

    # The drain WAS attempted (and failed).
    assert enqueue.calls, "expected the on-change drain to be fired after the write"

    # EXPECTED POST-FIX: the failure is OBSERVABLE (a sink was notified) and/or RETRIED
    # (fired more than once). On UNFIXED code it is swallowed with neither → THIS FAILS,
    # confirming the silent propagation miss for h-dcn / peter@pgeers.nl / region → ["*"].
    was_retried = len(enqueue.calls) > 1
    was_surfaced = bool(surfaced)
    assert was_surfaced or was_retried, (
        "Bug 1 reproduced: the on-change enqueue_sync drain failure was silently swallowed "
        "by _fire_enqueue_sync (logged-and-return) with no surfaced/retried signal — so the "
        f"propagation miss (e.g. {_BUG1_USER} / region → ['*'] for {_BUG1_TENANT}) is "
        "invisible. Expected the failure to be observable (a notified failure sink) and/or "
        "retried. This FAILURE confirms the swallowed-drain cause of the stale projection."
    )
