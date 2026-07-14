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
