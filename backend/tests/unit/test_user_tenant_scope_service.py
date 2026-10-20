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
    ScopeChangeReconciliation,
    ScopeReconciliationBlocked,
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

        if q.startswith(
            "SELECT EMAIL, SCOPES FROM USER_TENANT_SCOPE WHERE ADMINISTRATION"
        ):
            # list_grants (Task 3.9): all rows for (administration, module).
            admin, module = params
            return [
                {"email": e, "scopes": sj}
                for (e, a, m), sj in self.rows.items()
                if a == admin and m == module
            ]

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
    assert enqueue.calls == [TENANT_A]


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
# Task 3.9/3.10 — cross-plane scope-grant RECONCILIATION (Requirement 23, Property 10 +
# the cross-plane invariant). A PROPOSED scope-dimension change is classified against the
# tenant's existing user_tenant_scope grants BEFORE it is applied: ROUTINE (nothing orphaned
# → auto-mirror + reminder) vs ORPHANING (would strand a grant → BLOCK, contact-SysAdmin).
# The no-silent-stale-grant invariant: no APPLIED change leaves a grant referencing a removed
# or renamed dimension/value.
# Validates: Requirements 22, 23
# ───────────────────────────────────────────────────────────────────────────────────────


def _dim(key, values, *, enabled=True):
    """A proposed config#scope dimension (the shape members.scope_dimensions / the overlay
    derivation carries: key + declared values + enabled)."""
    return {"key": key, "field": key, "enabled": enabled, "values": list(values)}


def _svc_with_grants(grants_by_email):
    """A service over a FakeDB pre-seeded with the given {email: scopes-dict} grants for
    TENANT_A / MEMBERS. The parameter service is irrelevant to reconciliation (it reads the
    PROPOSED set, not the stored param), so an empty one suffices."""
    db = FakeDB()
    for email, scopes in grants_by_email.items():
        db.rows[(email, TENANT_A, MODULE)] = json.dumps(scopes)
    return UserTenantScopeService(
        db, FakeParameterService({}), enqueue_sync=lambda *_: None
    )


def test_reconcile_new_tenant_no_grants_is_routine():
    """A tenant with NO grants → any proposed set is ROUTINE (nothing to orphan, R23.1)."""
    svc = _svc_with_grants({})
    result = svc.reconcile_scope_change(
        TENANT_A, MODULE, [_dim("region", ["Noord", "Zuid"])]
    )
    assert isinstance(result, ScopeChangeReconciliation)
    assert result.is_routine
    assert result.orphaned == []
    result.assert_appliable()  # routine never raises


def test_reconcile_adding_a_value_is_routine():
    """Adding a value to a dimension strands no existing grant → ROUTINE (R23.2)."""
    svc = _svc_with_grants({EMAIL: {"region": ["Noord"]}})
    # region grows Noord -> Noord/Zuid/Oost: the existing Noord grant is still declared.
    result = svc.reconcile_scope_change(
        TENANT_A, MODULE, [_dim("region", ["Noord", "Zuid", "Oost"])]
    )
    assert result.is_routine
    assert result.orphaned == []


def test_reconcile_adding_a_new_dimension_is_routine():
    """Adding a whole new dimension never orphans an existing grant → ROUTINE (R23.2)."""
    svc = _svc_with_grants({EMAIL: {"region": ["Noord"]}})
    result = svc.reconcile_scope_change(
        TENANT_A, MODULE, [_dim("region", ["Noord"]), _dim("team", ["A", "B"])]
    )
    assert result.is_routine


def test_reconcile_wildcard_grant_survives_a_value_change():
    """A ["*"] (whole-dimension) grant is NOT stranded by adding/removing values — it means
    'the whole dimension', so only removing the dimension itself orphans it (R23)."""
    svc = _svc_with_grants({EMAIL: {"region": [WILDCARD_VALUE]}})
    result = svc.reconcile_scope_change(
        TENANT_A, MODULE, [_dim("region", ["totally", "different", "values"])]
    )
    assert result.is_routine


def test_reconcile_removing_a_dimension_orphans_its_grants():
    """Removing a dimension strands every grant on it (incl. wildcard) → ORPHANING (R23.3)."""
    svc = _svc_with_grants(
        {EMAIL: {"region": ["Noord"]}, "two@x.example": {"region": [WILDCARD_VALUE]}}
    )
    # Proposed set drops 'region' entirely (only 'team' remains).
    result = svc.reconcile_scope_change(TENANT_A, MODULE, [_dim("team", ["A"])])
    assert result.is_orphaning
    orphaned_emails = {o["email"] for o in result.orphaned}
    assert orphaned_emails == {EMAIL, "two@x.example"}


def test_reconcile_renaming_a_dimension_orphans_grants():
    """A rename is a remove+add from the detector's view: the OLD key is gone → ORPHANING."""
    svc = _svc_with_grants({EMAIL: {"region": ["Noord"]}})
    # 'region' renamed to 'area' — the stored grant still names 'region'.
    result = svc.reconcile_scope_change(TENANT_A, MODULE, [_dim("area", ["Noord"])])
    assert result.is_orphaning
    assert result.orphaned[0]["dimension"] == "region"


def test_reconcile_dropping_a_granted_value_orphans_that_grant():
    """Dropping a value an existing grant references → ORPHANING, naming the stranded value."""
    svc = _svc_with_grants({EMAIL: {"region": ["Noord", "Zuid"]}})
    # 'Zuid' removed from the declared set; the grant still references it.
    result = svc.reconcile_scope_change(TENANT_A, MODULE, [_dim("region", ["Noord"])])
    assert result.is_orphaning
    assert result.orphaned == [
        {"email": EMAIL, "dimension": "region", "values": ["Zuid"]}
    ]


def test_reconcile_disabled_dimension_is_treated_as_removed():
    """A dimension flipped to disabled is absent for validation → its grants are orphaned."""
    svc = _svc_with_grants({EMAIL: {"region": ["Noord"]}})
    result = svc.reconcile_scope_change(
        TENANT_A, MODULE, [_dim("region", ["Noord"], enabled=False)]
    )
    assert result.is_orphaning


def test_reconcile_canonical_equality_value_respelling_is_not_an_orphan():
    """A declared-spelling change that is canonically the SAME value does not orphan (R9.6)."""
    svc = _svc_with_grants({EMAIL: {"region": ["Noord"]}})
    # Re-spelled (case/space variant) but canonically equal → not stranded.
    result = svc.reconcile_scope_change(TENANT_A, MODULE, [_dim("region", [" noord "])])
    assert result.is_routine


def test_reconcile_assert_appliable_blocks_an_orphaning_change():
    """The no-silent-stale-grant invariant: an orphaning change raises
    ScopeReconciliationBlocked (never applied silently), carrying the orphaned refs (R23)."""
    svc = _svc_with_grants({EMAIL: {"region": ["Noord", "Zuid"]}})
    result = svc.reconcile_scope_change(TENANT_A, MODULE, [_dim("region", ["Noord"])])
    with pytest.raises(ScopeReconciliationBlocked) as exc:
        result.assert_appliable()
    assert exc.value.orphaned == [
        {"email": EMAIL, "dimension": "region", "values": ["Zuid"]}
    ]


def test_reconcile_list_grants_is_tenant_isolated():
    """list_grants returns ONLY the queried tenant's grants (steering 31 tenant isolation)."""
    db = FakeDB()
    db.rows[(EMAIL, TENANT_A, MODULE)] = json.dumps({"region": ["Noord"]})
    db.rows[("other@x.example", TENANT_B, MODULE)] = json.dumps({"region": ["Zuid"]})
    svc = UserTenantScopeService(
        db, FakeParameterService({}), enqueue_sync=lambda *_: None
    )

    grants = svc.list_grants(TENANT_A, MODULE)

    assert [g["email"] for g in grants] == [EMAIL]
    # The other tenant's grant never appears (no cross-tenant leak).
    assert all(g["email"] != "other@x.example" for g in grants)


def test_reconcile_never_touches_user_tenant_roles():
    """Axis independence (R1.3/Property 5): reconciliation reads user_tenant_scope ONLY."""
    svc = _svc_with_grants({EMAIL: {"region": ["Noord"]}})
    svc.reconcile_scope_change(TENANT_A, MODULE, [_dim("region", ["Noord"])])
    assert all("USER_TENANT_ROLES" not in q.upper() for q in svc.db.queries)
