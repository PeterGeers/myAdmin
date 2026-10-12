"""Unit tests for RoutePresetService — CRUD operations and auto-learning.

Covers: Requirement 3 (Route Presets / Favoriete Routes)
Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.3

Tests:
- Usage tracking (increment_usage upserts correctly)
- Suggestion ordering by frequency (highest use_count first)
- Manual preset CRUD (create, update, delete)
- 6-month window filter (only suggestions from last 6 months)
- Limit parameter respected (max_route_presets from parameter system)
- Tenant isolation (presets scoped to administration)
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from services.zzp_route_preset_service import RoutePresetService


TENANT = "test_admin"
OTHER_TENANT = "other_admin"


def _make_service(db=None, parameter_service=None):
    """Create a RoutePresetService with mocked dependencies."""
    db = db or Mock()
    return RoutePresetService(db=db, parameter_service=parameter_service)


def _preset_row(overrides=None):
    """Generate a realistic route preset row dict as returned by the DB."""
    row = {
        "id": 1,
        "administration": TENANT,
        "from_address": "Thuiskantoor, Amsterdam",
        "to_address": "Klant A, Rotterdam",
        "default_category": "Zakelijk",
        "default_purpose": "Klantbezoek",
        "contact_id": 42,
        "typical_distance_km": 75,
        "use_count": 10,
        "last_used_at": datetime(2026, 3, 15, 9, 0, 0),
        "is_manual": True,
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 1, 10, 0, 0),
    }
    if overrides:
        row.update(overrides)
    return row


# ── get_suggestions ─────────────────────────────────────────


class TestGetSuggestions:
    """Tests for RoutePresetService.get_suggestions."""

    def test_returns_manual_and_auto_presets_merged(self):
        """Returns manual presets plus auto-learned presets, deduplicated."""
        db = Mock()
        auto_row = _preset_row({"id": 2, "is_manual": False, "from_address": "Office", "to_address": "Warehouse"})
        manual_row = _preset_row({"id": 1, "is_manual": True})
        db.execute_query = Mock(side_effect=[
            [auto_row],     # auto-learned query
            [manual_row],   # manual presets query
        ])
        svc = _make_service(db=db)

        result = svc.get_suggestions(TENANT, limit=5)

        assert len(result) == 2
        # Manual presets appear first (priority in deduplication)
        assert result[0]["id"] == 1
        assert result[0]["is_manual"] is True
        assert result[1]["id"] == 2
        assert result[1]["is_manual"] is False

    def test_deduplication_manual_takes_priority(self):
        """When the same preset ID appears in both sets, manual wins."""
        db = Mock()
        # Same id=1 in both auto and manual results
        auto_row = _preset_row({"id": 1, "is_manual": False})
        manual_row = _preset_row({"id": 1, "is_manual": True})
        db.execute_query = Mock(side_effect=[
            [auto_row],     # auto-learned query
            [manual_row],   # manual presets query
        ])
        svc = _make_service(db=db)

        result = svc.get_suggestions(TENANT, limit=5)

        # Only one entry — manual wins
        assert len(result) == 1
        assert result[0]["is_manual"] is True

    def test_uses_parameter_service_for_max_presets(self):
        """Uses max_route_presets from parameter service when no limit given."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value="8")
        svc = _make_service(db=db, parameter_service=param_svc)

        svc.get_suggestions(TENANT)

        # Verify the auto-learned query used limit=8
        auto_call = db.execute_query.call_args_list[0]
        assert auto_call[0][1] == (TENANT, 8)

    def test_limit_override_takes_precedence(self):
        """Explicit limit parameter overrides the parameter service value."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value="8")
        svc = _make_service(db=db, parameter_service=param_svc)

        svc.get_suggestions(TENANT, limit=3)

        # Verify the auto-learned query used limit=3 (not 8 from param service)
        auto_call = db.execute_query.call_args_list[0]
        assert auto_call[0][1] == (TENANT, 3)

    def test_empty_results_returns_empty_list(self):
        """No presets returns empty list."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        svc = _make_service(db=db)

        result = svc.get_suggestions(TENANT, limit=5)
        assert result == []


# ── create_preset ───────────────────────────────────────────


class TestCreatePreset:
    """Tests for RoutePresetService.create_preset."""

    def test_happy_path(self):
        """Create preset with all fields returns formatted preset dict."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            1,                      # INSERT returns preset_id
            [_preset_row()],        # get_preset SELECT
        ])
        svc = _make_service(db=db)

        data = {
            "from_address": "Thuiskantoor, Amsterdam",
            "to_address": "Klant A, Rotterdam",
            "default_category": "Zakelijk",
            "default_purpose": "Klantbezoek",
            "contact_id": 42,
            "typical_distance_km": 75,
        }
        result = svc.create_preset(TENANT, data)

        assert result["id"] == 1
        assert result["from_address"] == "Thuiskantoor, Amsterdam"
        assert result["is_manual"] is True
        # Verify INSERT was called with fetch=False, commit=True
        insert_call = db.execute_query.call_args_list[0]
        assert insert_call[1]["fetch"] is False
        assert insert_call[1]["commit"] is True

    def test_missing_from_address_raises_value_error(self):
        """Missing from_address raises ValueError."""
        svc = _make_service()
        data = {"to_address": "Klant A, Rotterdam"}

        with pytest.raises(ValueError, match="from_address"):
            svc.create_preset(TENANT, data)

    def test_missing_to_address_raises_value_error(self):
        """Missing to_address raises ValueError."""
        svc = _make_service()
        data = {"from_address": "Thuiskantoor, Amsterdam"}

        with pytest.raises(ValueError, match="to_address"):
            svc.create_preset(TENANT, data)


# ── update_preset ───────────────────────────────────────────


class TestUpdatePreset:
    """Tests for RoutePresetService.update_preset."""

    def test_happy_path_updates_fields(self):
        """Update preset fields succeeds and returns updated preset."""
        db = Mock()
        updated_row = _preset_row({"default_category": "Privé", "typical_distance_km": 80})
        db.execute_query = Mock(side_effect=[
            [_preset_row()],    # get_preset (existing check)
            None,               # UPDATE query
            [updated_row],      # get_preset (return updated)
        ])
        svc = _make_service(db=db)

        result = svc.update_preset(TENANT, 1, {
            "default_category": "Privé",
            "typical_distance_km": 80,
        })

        assert result["default_category"] == "Privé"
        assert result["typical_distance_km"] == 80

    def test_preset_not_found_raises_value_error(self):
        """Updating non-existent preset raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="not found"):
            svc.update_preset(TENANT, 999, {"default_category": "Privé"})

    def test_empty_update_returns_existing(self):
        """Empty update dict returns existing preset unchanged."""
        db = Mock()
        db.execute_query = Mock(return_value=[_preset_row()])
        svc = _make_service(db=db)

        result = svc.update_preset(TENANT, 1, {})

        assert result["id"] == 1
        # Only one DB call (get_preset), no UPDATE executed
        assert db.execute_query.call_count == 1


# ── delete_preset ───────────────────────────────────────────


class TestDeletePreset:
    """Tests for RoutePresetService.delete_preset."""

    def test_happy_path_returns_true(self):
        """Deleting an existing preset returns True."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [_preset_row()],    # get_preset (existing check)
            None,               # DELETE query
        ])
        svc = _make_service(db=db)

        result = svc.delete_preset(TENANT, 1)

        assert result is True
        # Verify DELETE was called with fetch=False, commit=True
        delete_call = db.execute_query.call_args_list[1]
        assert delete_call[1]["fetch"] is False
        assert delete_call[1]["commit"] is True

    def test_preset_not_found_raises_value_error(self):
        """Deleting non-existent preset raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="not found"):
            svc.delete_preset(TENANT, 999)


# ── increment_usage ─────────────────────────────────────────


class TestIncrementUsage:
    """Tests for RoutePresetService.increment_usage."""

    def test_existing_route_increments_use_count(self):
        """Existing route: increments use_count and updates last_used_at."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"id": 1, "use_count": 5}],    # SELECT finds existing route
            None,                            # UPDATE increments
        ])
        svc = _make_service(db=db)

        svc.increment_usage(TENANT, "Amsterdam", "Rotterdam")

        # Verify UPDATE was called (second call)
        update_call = db.execute_query.call_args_list[1]
        assert "use_count = use_count + 1" in update_call[0][0]
        assert update_call[1]["fetch"] is False
        assert update_call[1]["commit"] is True

    def test_new_route_creates_with_count_one(self):
        """New route: creates preset with use_count=1 and is_manual=False."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [],     # SELECT finds no existing route
            None,   # INSERT creates new
        ])
        svc = _make_service(db=db)

        svc.increment_usage(TENANT, "Amsterdam", "Utrecht")

        # Verify INSERT was called (second call)
        insert_call = db.execute_query.call_args_list[1]
        query = insert_call[0][0]
        params = insert_call[0][1]
        assert "INSERT INTO zzp_route_presets" in query
        # Params: (tenant, from_addr, to_addr, use_count=1, is_manual=False)
        assert params[0] == TENANT
        assert params[1] == "Amsterdam"
        assert params[2] == "Utrecht"
        assert params[3] == 1       # use_count
        assert params[4] is False   # is_manual
        assert insert_call[1]["fetch"] is False
        assert insert_call[1]["commit"] is True

    def test_strips_whitespace_from_addresses(self):
        """Addresses are stripped before lookup/insert."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], None])
        svc = _make_service(db=db)

        svc.increment_usage(TENANT, "  Amsterdam  ", "  Rotterdam  ")

        # Verify the SELECT used stripped addresses
        select_call = db.execute_query.call_args_list[0]
        params = select_call[0][1]
        assert params[1] == "Amsterdam"
        assert params[2] == "Rotterdam"


# ── 6-month window filter ──────────────────────────────────


class TestSixMonthWindowFilter:
    """Tests that get_suggestions only includes auto-learned presets from last 6 months."""

    def test_auto_query_uses_date_filter(self):
        """The auto-learned query filters by last_used_at >= 6 months ago."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        svc = _make_service(db=db)

        svc.get_suggestions(TENANT, limit=5)

        # First call is the auto-learned query with date filter
        auto_query = db.execute_query.call_args_list[0][0][0]
        assert "last_used_at >=" in auto_query
        # Should reference a date subtraction (6 months)
        assert "6" in auto_query or "MONTH" in auto_query

    def test_manual_presets_not_filtered_by_date(self):
        """Manual presets are returned regardless of last_used_at."""
        db = Mock()
        # Manual preset with no recent usage (old last_used_at)
        old_manual = _preset_row({
            "id": 1,
            "is_manual": True,
            "last_used_at": datetime(2020, 1, 1, 0, 0, 0),
        })
        db.execute_query = Mock(side_effect=[
            [],             # No auto-learned presets
            [old_manual],   # Manual presets (no date filter)
        ])
        svc = _make_service(db=db)

        result = svc.get_suggestions(TENANT, limit=5)

        # Manual preset appears even though last_used_at is very old
        assert len(result) == 1
        assert result[0]["is_manual"] is True
        # Second query (manual) doesn't have date filter
        manual_query = db.execute_query.call_args_list[1][0][0]
        assert "last_used_at" not in manual_query

    def test_auto_query_filters_by_is_manual_false(self):
        """Auto-learned query only selects is_manual = FALSE."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        svc = _make_service(db=db)

        svc.get_suggestions(TENANT, limit=5)

        auto_query = db.execute_query.call_args_list[0][0][0]
        assert "is_manual = FALSE" in auto_query


# ── Suggestion ordering by frequency ───────────────────────


class TestSuggestionOrdering:
    """Tests that suggestions are ordered by use_count DESC (highest frequency first)."""

    def test_auto_query_orders_by_use_count_desc(self):
        """Auto-learned presets are queried ORDER BY use_count DESC."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        svc = _make_service(db=db)

        svc.get_suggestions(TENANT, limit=5)

        auto_query = db.execute_query.call_args_list[0][0][0]
        assert "ORDER BY use_count DESC" in auto_query

    def test_high_frequency_routes_appear_before_low(self):
        """Routes with higher use_count appear before those with lower use_count."""
        db = Mock()
        high_usage = _preset_row({"id": 2, "is_manual": False, "use_count": 50,
                                   "from_address": "A", "to_address": "B"})
        low_usage = _preset_row({"id": 3, "is_manual": False, "use_count": 5,
                                  "from_address": "C", "to_address": "D"})
        # DB returns them in order (ORDER BY use_count DESC)
        db.execute_query = Mock(side_effect=[
            [high_usage, low_usage],    # auto-learned (already sorted by DB)
            [],                          # no manual presets
        ])
        svc = _make_service(db=db)

        result = svc.get_suggestions(TENANT, limit=5)

        assert len(result) == 2
        assert result[0]["use_count"] == 50
        assert result[1]["use_count"] == 5

    def test_manual_presets_appear_before_auto_learned(self):
        """Manual presets always appear first in results (priority in merge)."""
        db = Mock()
        auto_row = _preset_row({"id": 2, "is_manual": False, "use_count": 100})
        manual_row = _preset_row({"id": 1, "is_manual": True, "use_count": 0})
        db.execute_query = Mock(side_effect=[
            [auto_row],     # auto-learned (high usage)
            [manual_row],   # manual (low usage)
        ])
        svc = _make_service(db=db)

        result = svc.get_suggestions(TENANT, limit=5)

        # Manual presets always come first regardless of use_count
        assert result[0]["is_manual"] is True
        assert result[1]["is_manual"] is False


# ── Limit parameter respected ──────────────────────────────


class TestLimitParameter:
    """Tests that max_route_presets limit is respected from parameter system."""

    def test_default_limit_is_5_without_parameter_service(self):
        """Without parameter service, limit falls back to 5 (from MODULE_REGISTRY or hardcoded)."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        svc = _make_service(db=db, parameter_service=None)

        with patch("services.module_registry.MODULE_REGISTRY", {
            "ZZP": {"required_params": {"zzp_ritten.max_route_presets": {"default": 5}}}
        }):
            svc.get_suggestions(TENANT)

        auto_call = db.execute_query.call_args_list[0]
        # LIMIT should be 5
        assert auto_call[0][1] == (TENANT, 5)

    def test_parameter_service_returns_none_uses_fallback(self):
        """When parameter_service returns None, uses MODULE_REGISTRY fallback."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        with patch("services.module_registry.MODULE_REGISTRY", {
            "ZZP": {"required_params": {"zzp_ritten.max_route_presets": {"default": 10}}}
        }):
            svc.get_suggestions(TENANT)

        auto_call = db.execute_query.call_args_list[0]
        assert auto_call[0][1] == (TENANT, 10)

    def test_parameter_service_value_converted_to_int(self):
        """Parameter service string value is converted to integer for LIMIT."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value="7")
        svc = _make_service(db=db, parameter_service=param_svc)

        svc.get_suggestions(TENANT)

        auto_call = db.execute_query.call_args_list[0]
        # Limit param should be int 7, not string "7"
        assert auto_call[0][1][1] == 7
        assert isinstance(auto_call[0][1][1], int)


# ── Tenant isolation ───────────────────────────────────────


class TestTenantIsolation:
    """Tests that all queries are properly scoped to the tenant (administration)."""

    def test_get_suggestions_scoped_to_tenant(self):
        """Both auto and manual queries include administration filter."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], []])
        svc = _make_service(db=db)

        svc.get_suggestions(TENANT, limit=5)

        # Both queries must include administration = %s
        auto_query = db.execute_query.call_args_list[0][0][0]
        manual_query = db.execute_query.call_args_list[1][0][0]
        assert "administration = %s" in auto_query
        assert "administration = %s" in manual_query
        # Tenant passed as param
        assert db.execute_query.call_args_list[0][0][1][0] == TENANT
        assert db.execute_query.call_args_list[1][0][1][0] == TENANT

    def test_create_preset_scoped_to_tenant(self):
        """Create preset stores the tenant in administration column."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            1,                      # INSERT returns id
            [_preset_row()],        # get_preset
        ])
        svc = _make_service(db=db)

        svc.create_preset(TENANT, {
            "from_address": "A",
            "to_address": "B",
        })

        insert_call = db.execute_query.call_args_list[0]
        params = insert_call[0][1]
        # First param is the tenant
        assert params[0] == TENANT

    def test_update_preset_scoped_to_tenant(self):
        """Update query includes administration in WHERE clause."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [_preset_row()],    # get_preset (existing check)
            None,               # UPDATE
            [_preset_row()],    # get_preset (return updated)
        ])
        svc = _make_service(db=db)

        svc.update_preset(TENANT, 1, {"default_category": "Privé"})

        update_call = db.execute_query.call_args_list[1]
        query = update_call[0][0]
        params = update_call[0][1]
        assert "administration = %s" in query
        # Last param is the tenant
        assert params[-1] == TENANT

    def test_delete_preset_scoped_to_tenant(self):
        """Delete query includes administration in WHERE clause."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [_preset_row()],    # get_preset (existing check)
            None,               # DELETE
        ])
        svc = _make_service(db=db)

        svc.delete_preset(TENANT, 1)

        delete_call = db.execute_query.call_args_list[1]
        query = delete_call[0][0]
        params = delete_call[0][1]
        assert "administration = %s" in query
        assert TENANT in params

    def test_increment_usage_scoped_to_tenant(self):
        """Increment usage SELECT and INSERT/UPDATE are scoped to tenant."""
        db = Mock()
        db.execute_query = Mock(side_effect=[[], None])
        svc = _make_service(db=db)

        svc.increment_usage(TENANT, "From", "To")

        # SELECT includes tenant
        select_call = db.execute_query.call_args_list[0]
        assert "administration = %s" in select_call[0][0]
        assert select_call[0][1][0] == TENANT
        # INSERT includes tenant
        insert_call = db.execute_query.call_args_list[1]
        assert insert_call[0][1][0] == TENANT

    def test_get_preset_scoped_to_tenant(self):
        """get_preset helper always includes administration filter."""
        db = Mock()
        db.execute_query = Mock(return_value=[_preset_row()])
        svc = _make_service(db=db)

        svc.get_preset(TENANT, 1)

        call_args = db.execute_query.call_args[0]
        assert "administration = %s" in call_args[0]
        assert TENANT in call_args[1]


# ===========================================================================
# Property-based tests — preset learning from import (task 6.2)
#
# Feature: rittenregistratie-tax-log-redesign
# These exercise the import → preset-learning seam added in task 6.1
# (TripImportService.commit_import → _seed_route_presets →
# RoutePresetService.increment_usage). Properties 10 and 12 live here (rather
# than in test_zzp_trip_import_service.py / test_zzp_trip_import_commit.py,
# which are owned by task 5.2) so the commit seam is exercised without touching
# those files.
# ===========================================================================

from hypothesis import given, strategies as st, settings

from services.zzp_trip_import_service import TripImportService


# ── Shared helpers for the import → preset seam ────────────────────────────


def _commit_db():
    """A MagicMock DB whose transaction() context manager yields a cursor.

    Mirrors the fixture pattern in test_zzp_trip_import_commit.py: the per-row
    INSERT + audit writes go through cursor.execute, and lastrowid is stable.
    execute_query returns [] so validate-time lookups (if ever hit) are empty.
    """
    db = Mock()
    db.execute_query = Mock(return_value=[])
    cursor = Mock()
    cursor.lastrowid = 1
    conn = Mock()
    ctx = Mock()
    ctx.__enter__ = Mock(return_value=(cursor, conn))
    ctx.__exit__ = Mock(return_value=False)
    db.transaction = Mock(return_value=ctx)
    return db


def _import_row(idx, from_addr, to_addr, status="ok", start_km=1000, end_km=1050):
    """Build a validated import row as commit_import expects to receive it."""
    return {
        "trip_date": "2026-01-15",
        "start_time": None,
        "end_time": None,
        "start_address": from_addr,
        "end_address": to_addr,
        "start_odometer": start_km,
        "end_odometer": end_km,
        "trip_category": "Zakelijk",
        "trip_purpose": "Klantbezoek",
        "client_name": None,
        "project_name": None,
        "notes": None,
        "route_description": None,
        "_status": status,
        "_messages": [],
        "_row_number": idx + 1,
    }


# Addresses kept short and distinct so pair identity is easy to reason about.
_addr = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ ", min_size=1, max_size=8
).map(lambda s: s.strip() or "X")

# A row spec: (from, to, is_error)
_row_spec = st.tuples(_addr, _addr, st.booleans())


# ── Property 10 ────────────────────────────────────────────────────────────


class TestPropertyPresetLearningRunsPerCommittedRow:
    """Property 10: Preset learning runs once per committed non-error row."""

    # Feature: rittenregistratie-tax-log-redesign, Property 10: increment_usage
    # is invoked exactly once per committed non-error row and zero times per
    # error row.
    @settings(max_examples=150)
    @given(specs=st.lists(_row_spec, min_size=0, max_size=12))
    def test_increment_usage_called_once_per_committed_non_error_row(self, specs):
        """Validates: Requirements 6.1"""
        rows = [
            _import_row(i, frm, to, status="error" if is_err else "ok")
            for i, (frm, to, is_err) in enumerate(specs)
        ]
        expected_non_error = sum(1 for (_f, _t, is_err) in specs if not is_err)

        db = _commit_db()
        service = TripImportService(db=db)

        fake_preset = Mock()
        fake_preset.increment_usage = Mock(return_value=1)
        with patch(
            "services.zzp_route_preset_service.RoutePresetService",
            return_value=fake_preset,
        ):
            result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        # Learning invoked exactly once per committed non-error row...
        assert fake_preset.increment_usage.call_count == expected_non_error
        # ...and the imported count matches the committed non-error rows.
        assert result["imported"] == expected_non_error

        # Every error row is skipped: none of its (from, to) pair was learned.
        learned_pairs = [
            (c.args[1], c.args[2])
            for c in fake_preset.increment_usage.call_args_list
        ]
        committed_pairs = [
            (frm, to) for (frm, to, is_err) in specs if not is_err
        ]
        assert sorted(learned_pairs) == sorted(committed_pairs)


# ── Property 11 ────────────────────────────────────────────────────────────


class _FakePresetDB:
    """Stateful in-memory stand-in for DatabaseManager, scoped to presets.

    Models the normalized matching contract of auto-learned presets: a from/to
    pair is matched case-insensitively after trimming (Req 6.2, 6.3). This lets
    the REAL RoutePresetService.increment_usage upsert against it so use_count
    reflects the true occurrence count of each normalized pair.
    """

    def __init__(self):
        # key = (tenant, from_norm, to_norm) -> stored row dict
        self._by_key = {}
        self._next_id = 1

    @staticmethod
    def _norm(addr):
        return (addr or "").strip().casefold()

    def execute_query(self, query, params=None, fetch=True, commit=False):
        params = params or ()
        q = " ".join(query.split())  # collapse whitespace for simple matching

        if q.startswith("SELECT id, use_count FROM zzp_route_presets"):
            tenant, from_addr, to_addr = params[0], params[1], params[2]
            key = (tenant, self._norm(from_addr), self._norm(to_addr))
            row = self._by_key.get(key)
            return [{"id": row["id"], "use_count": row["use_count"]}] if row else []

        if q.startswith("UPDATE zzp_route_presets"):
            # params tail: (..., id, tenant) — increment the stored row.
            preset_id = params[-2]
            for row in self._by_key.values():
                if row["id"] == preset_id:
                    row["use_count"] += 1
                    break
            return None

        if q.startswith("INSERT INTO zzp_route_presets"):
            tenant, from_addr, to_addr = params[0], params[1], params[2]
            key = (tenant, self._norm(from_addr), self._norm(to_addr))
            self._by_key[key] = {
                "id": self._next_id,
                "tenant": tenant,
                "from_address": from_addr,
                "to_address": to_addr,
                "use_count": 1,
            }
            self._next_id += 1
            return None

        return []

    def presets_for(self, tenant):
        return [r for r in self._by_key.values() if r["tenant"] == tenant]


# A pair drawn from a small address pool so collisions (repeat pairs) and
# case/whitespace variants of the same pair occur naturally.
_pair_pool = st.sampled_from(
    ["AMS", "RTM", "UTR", "DH ", " ams", "rtm", "Utr"]
)
_pair = st.tuples(_pair_pool, _pair_pool)


class TestPropertyPresetUseCountEqualsOccurrences:
    """Property 11: Preset use_count equals occurrence count."""

    # Feature: rittenregistratie-tax-log-redesign, Property 11: each auto-learned
    # preset's use_count equals the number of committed rows carrying that
    # normalized (case-insensitive, trimmed) from/to pair; distinct pairs yield
    # distinct presets.
    @settings(max_examples=150)
    @given(pairs=st.lists(_pair, min_size=1, max_size=20))
    def test_use_count_matches_normalized_pair_occurrences(self, pairs):
        """Validates: Requirements 6.2, 6.3"""
        tenant = "tenant1"
        db = _FakePresetDB()
        service = TripImportService(db=db)

        committed_rows = [
            _import_row(i, frm, to) for i, (frm, to) in enumerate(pairs)
        ]
        # Drive the real learning path (real RoutePresetService, fake DB).
        service._seed_route_presets(tenant, committed_rows)

        # Expected: count of each normalized (trim + casefold) pair.
        def norm(a):
            return a.strip().casefold()

        expected = {}
        for frm, to in pairs:
            key = (norm(frm), norm(to))
            expected[key] = expected.get(key, 0) + 1

        presets = db.presets_for(tenant)

        # Distinct normalized pairs → distinct presets (one row each).
        assert len(presets) == len(expected)

        # Each preset's use_count equals its normalized pair's occurrence count.
        by_norm = {
            (norm(p["from_address"]), norm(p["to_address"])): p["use_count"]
            for p in presets
        }
        assert by_norm == expected
        # A first occurrence yields use_count == 1.
        assert all(count >= 1 for count in by_norm.values())


# ── Property 12 ────────────────────────────────────────────────────────────


class TestPropertyPresetLearningFailureNonFatal:
    """Property 12: Preset learning failure is non-fatal."""

    # Feature: rittenregistratie-tax-log-redesign, Property 12: when learning
    # raises for a row, the trip and import stay committed and a non-fatal note
    # is recorded for that row.
    @settings(max_examples=150)
    @given(
        specs=st.lists(_row_spec, min_size=1, max_size=10),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    def test_learning_failure_leaves_import_committed_with_note(self, specs, seed):
        """Validates: Requirements 6.4"""
        rows = [
            _import_row(i, frm, to, status="error" if is_err else "ok")
            for i, (frm, to, is_err) in enumerate(specs)
        ]
        committed_rows = [r for r in rows if r["_status"] != "error"]

        # Nothing to assert about learning if no row commits; still must succeed.
        db = _commit_db()
        service = TripImportService(db=db)

        if not committed_rows:
            fake_preset = Mock()
            fake_preset.increment_usage = Mock(return_value=1)
            with patch(
                "services.zzp_route_preset_service.RoutePresetService",
                return_value=fake_preset,
            ):
                result = service.commit_import("tenant1", 1, rows, "user@test.com")
            assert result["success"] is True
            assert result["imported"] == 0
            return

        # Pick exactly one committed row whose learning will raise.
        failing_index = seed % len(committed_rows)
        failing_row = committed_rows[failing_index]

        call_state = {"n": 0}

        def flaky_increment(*_args, **_kwargs):
            # Raise only on the call corresponding to the chosen failing row.
            current = call_state["n"]
            call_state["n"] += 1
            if current == failing_index:
                raise RuntimeError("preset backend unavailable")
            return 1

        fake_preset = Mock()
        fake_preset.increment_usage = Mock(side_effect=flaky_increment)
        with patch(
            "services.zzp_route_preset_service.RoutePresetService",
            return_value=fake_preset,
        ):
            result = service.commit_import("tenant1", 1, rows, "user@test.com")

        # Import stays committed; the committed trips are still counted.
        assert result["success"] is True
        assert result["imported"] == len(committed_rows)

        # The failing row carries a non-fatal note; the import did not roll back.
        notes = failing_row.get("_messages", [])
        assert any("routesuggestie" in m for m in notes), (
            f"expected a non-fatal preset note on the failing row, got {notes!r}"
        )
