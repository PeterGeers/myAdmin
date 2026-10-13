"""Unit tests for TripService — CRUD, filtering, enrichment, summary, bijtelling.

Covers: Requirements 2, 5, 6 (Trip CRUD, bijtelling tracking, summaries)
Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.2
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date, datetime
from decimal import Decimal

from hypothesis import given, settings, strategies as st

from services.zzp_trip_service import TripService


TENANT = "test_admin"


def _make_service(db=None, parameter_service=None):
    """Create a TripService with mocked dependencies."""
    db = db or Mock()
    return TripService(db=db, parameter_service=parameter_service)


def _trip_row(overrides=None):
    """Generate a realistic trip row dict as returned by the DB."""
    row = {
        "id": 1,
        "administration": TENANT,
        "vehicle_id": 1,
        "trip_date": date(2026, 7, 13),
        "start_time": "08:30",
        "end_time": "09:15",
        "start_address": "Keizersgracht 100, Amsterdam",
        "end_address": "Stationsplein 1, Utrecht",
        "start_odometer": 45230,
        "end_odometer": 45275,
        "distance_km": 45,
        "trip_category": "Zakelijk",
        "trip_purpose": "Klantbezoek",
        "route_description": None,
        "client_name": "Acme BV",
        "project_name": "Project Alpha",
        "notes": None,
        "is_gap_fill": 0,
        "is_cancelled": 0,
        "cancel_reason": None,
        "version": 1,
        "created_at": datetime(2026, 7, 13, 8, 30, 0),
        "updated_at": datetime(2026, 7, 13, 8, 30, 0),
        "created_by": "user@example.com",
    }
    if overrides:
        row.update(overrides)
    return row


def _valid_trip_data(overrides=None):
    """Generate valid trip creation data."""
    data = {
        "vehicle_id": 1,
        "trip_date": "2026-07-13",
        "start_address": "Keizersgracht 100, Amsterdam",
        "end_address": "Stationsplein 1, Utrecht",
        "start_odometer": 45230,
        "end_odometer": 45275,
        "trip_category": "Zakelijk",
        "trip_purpose": "Klantbezoek",
        "start_time": "08:30",
        "end_time": "09:15",
        "client_name": "Acme BV",
        "project_name": "Project Alpha",
    }
    if overrides:
        data.update(overrides)
    return data


# ── create_trip ─────────────────────────────────────────────


class TestCreateTrip:
    """Tests for TripService.create_trip."""

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_happy_path_no_gap(self, mock_validate):
        """Create trip with valid data, no gap, returns success response."""
        db = Mock()
        created_row = _trip_row()
        # Side effects: validate_vehicle, detect_gap (prev trip), INSERT, audit INSERT, get_trip, contacts
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            [{"end_odometer": 45230}],  # detect_gap: prev trip matches start_odometer
            1,                   # INSERT returns trip_id
            None,                # _write_audit_entry INSERT
            [created_row],       # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        result = svc.create_trip(TENANT, _valid_trip_data(), "user@example.com")

        assert result["success"] is True
        assert result["data"]["id"] == 1
        assert result["data"]["trip_category"] == "Zakelijk"
        assert result["data"]["distance_km"] == 45
        # Trips are billing-free post-redesign: no is_billable/is_billed surfaced (Req 4.5, 4.6).
        assert "is_billable" not in result["data"]
        assert "is_billed" not in result["data"]
        assert "warnings" not in result
        assert "gap_fill_offer" not in result

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_happy_path_with_gap(self, mock_validate):
        """Create trip with gap detected returns warnings and gap_fill_offer."""
        db = Mock()
        created_row = _trip_row()
        # Side effects: validate_vehicle, detect_gap (prev trip with gap), INSERT, audit INSERT, get_trip, contacts
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            [{"end_odometer": 45218}],  # detect_gap: prev trip end=45218, start=45230 → gap=12
            1,                   # INSERT returns trip_id
            None,                # _write_audit_entry INSERT
            [created_row],       # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        result = svc.create_trip(TENANT, _valid_trip_data(), "user@example.com")

        assert result["success"] is True
        assert result["data"]["id"] == 1
        # Verify warnings
        assert "warnings" in result
        assert len(result["warnings"]) == 1
        warning = result["warnings"][0]
        assert warning["type"] == "odometer_gap"
        assert warning["gap_km"] == 12
        assert warning["previous_end_odometer"] == 45218
        assert warning["current_start_odometer"] == 45230
        assert "Gap of 12 km detected" in warning["message"]
        # Verify gap_fill_offer
        assert "gap_fill_offer" in result
        offer = result["gap_fill_offer"]
        assert offer["start_odometer"] == 45218
        assert offer["end_odometer"] == 45230
        assert offer["suggested_category"] == "Privé"
        assert offer["suggested_purpose"] == "Niet geregistreerd"

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_missing_required_fields_raises_value_error(self, mock_validate):
        """Missing required fields raises ValueError via validate_fields."""
        mock_validate.side_effect = ValueError(
            "Required fields missing: trip_date, start_address"
        )
        svc = _make_service()

        with pytest.raises(ValueError, match="Required fields missing"):
            svc.create_trip(TENANT, {"vehicle_id": 1}, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_end_odometer_less_than_start_raises_value_error(self, mock_validate):
        """end_odometer <= start_odometer raises ValueError."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        data = _valid_trip_data({"start_odometer": 50000, "end_odometer": 49000})
        with pytest.raises(ValueError, match="end_odometer must be greater"):
            svc.create_trip(TENANT, data, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_end_odometer_equal_start_raises_value_error(self, mock_validate):
        """end_odometer == start_odometer raises ValueError."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        data = _valid_trip_data({"start_odometer": 50000, "end_odometer": 50000})
        with pytest.raises(ValueError, match="end_odometer must be greater"):
            svc.create_trip(TENANT, data, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_invalid_date_format_raises_value_error(self, mock_validate):
        """Invalid trip_date format raises ValueError."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        data = _valid_trip_data({"trip_date": "13-07-2026"})
        with pytest.raises(ValueError, match="Invalid trip_date"):
            svc.create_trip(TENANT, data, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_invalid_category_raises_value_error(self, mock_validate):
        """Invalid trip_category raises ValueError."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        data = _valid_trip_data({"trip_category": "Vakantie"})
        with pytest.raises(ValueError, match="Invalid trip_category"):
            svc.create_trip(TENANT, data, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_invalid_purpose_raises_value_error(self, mock_validate):
        """Invalid trip_purpose raises ValueError."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        data = _valid_trip_data({"trip_purpose": "Strandbezoek"})
        with pytest.raises(ValueError, match="Invalid trip_purpose"):
            svc.create_trip(TENANT, data, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_vehicle_not_found_raises_value_error(self, mock_validate):
        """Non-existent vehicle raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])  # _validate_vehicle finds nothing
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        data = _valid_trip_data({"vehicle_id": 999})
        with pytest.raises(ValueError, match="Vehicle 999 not found"):
            svc.create_trip(TENANT, data, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_writes_audit_entry_on_creation(self, mock_validate):
        """create_trip writes a 'created' audit entry after INSERT."""
        db = Mock()
        created_row = _trip_row()
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            [{"end_odometer": 45230}],  # detect_gap: no gap
            1,                   # INSERT returns trip_id=1
            None,                # _write_audit_entry INSERT
            [created_row],       # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        result = svc.create_trip(TENANT, _valid_trip_data(), "user@example.com")

        assert result["success"] is True
        # The 4th call (index 3) should be the audit entry INSERT
        audit_call = db.execute_query.call_args_list[3]
        query = audit_call[0][0]
        params = audit_call[0][1]
        assert "INSERT INTO zzp_trip_audit" in query
        assert params[0] == TENANT       # administration
        assert params[1] == 1            # trip_id
        assert params[2] == 1            # version
        assert params[3] == "created"    # action
        assert params[4] is None         # changed_fields
        assert params[5] is None         # correction_reason
        assert params[6] == "user@example.com"  # changed_by


# ── large distance warning ──────────────────────────────────


class TestLargeDistanceWarning:
    """Tests for large distance warning in create_trip (Requirement 4.6)."""

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_warning_triggered_when_distance_exceeds_threshold(self, mock_validate):
        """Large distance warning fires when distance > threshold (default 300 km)."""
        db = Mock()
        # Trip with 450 km distance (start=10000, end=10450)
        created_row = _trip_row({
            "start_odometer": 10000,
            "end_odometer": 10450,
            "distance_km": 450,
        })
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],              # _validate_vehicle
            [{"end_odometer": 10000}], # detect_gap: no gap (matches start)
            1,                         # INSERT returns trip_id
            None,                      # _write_audit_entry INSERT
            [created_row],             # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)  # Falls back to default 300
        svc = _make_service(db=db, parameter_service=param_svc)

        data = _valid_trip_data({"start_odometer": 10000, "end_odometer": 10450})
        result = svc.create_trip(TENANT, data, "user@example.com")

        assert result["success"] is True
        assert "warnings" in result
        # Find the large_distance warning
        large_warnings = [w for w in result["warnings"] if w["type"] == "large_distance"]
        assert len(large_warnings) == 1
        warning = large_warnings[0]
        assert warning["type"] == "large_distance"
        assert warning["distance_km"] == 450
        assert warning["threshold_km"] == 300
        assert "450 km" in warning["message"]
        assert "300 km" in warning["message"]

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_no_warning_when_distance_below_threshold(self, mock_validate):
        """No large distance warning when distance <= threshold."""
        db = Mock()
        created_row = _trip_row()  # 45 km distance (default fixture)
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],              # _validate_vehicle
            [{"end_odometer": 45230}], # detect_gap: no gap
            1,                         # INSERT returns trip_id
            None,                      # _write_audit_entry INSERT
            [created_row],             # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        result = svc.create_trip(TENANT, _valid_trip_data(), "user@example.com")

        assert result["success"] is True
        # No warnings key (no gap, no large distance)
        assert "warnings" not in result

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_no_warning_when_distance_equals_threshold(self, mock_validate):
        """No warning when distance == threshold (must exceed, not equal)."""
        db = Mock()
        created_row = _trip_row({
            "start_odometer": 10000,
            "end_odometer": 10300,
            "distance_km": 300,
        })
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],              # _validate_vehicle
            [{"end_odometer": 10000}], # detect_gap: no gap
            1,                         # INSERT returns trip_id
            None,                      # _write_audit_entry INSERT
            [created_row],             # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        data = _valid_trip_data({"start_odometer": 10000, "end_odometer": 10300})
        result = svc.create_trip(TENANT, data, "user@example.com")

        assert result["success"] is True
        assert "warnings" not in result

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_custom_threshold_from_parameter_service(self, mock_validate):
        """Custom threshold from parameter service is respected."""
        db = Mock()
        # Trip with 200 km distance — below default 300 but above custom 150
        created_row = _trip_row({
            "start_odometer": 10000,
            "end_odometer": 10200,
            "distance_km": 200,
        })
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],              # _validate_vehicle
            [{"end_odometer": 10000}], # detect_gap: no gap
            1,                         # INSERT returns trip_id
            None,                      # _write_audit_entry INSERT
            [created_row],             # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        param_svc = Mock()

        def get_param_side_effect(namespace, key, tenant=None):
            if namespace == "zzp_ritten" and key == "large_distance_warning":
                return 150  # Custom threshold: 150 km
            return None

        param_svc.get_param = Mock(side_effect=get_param_side_effect)
        svc = _make_service(db=db, parameter_service=param_svc)

        data = _valid_trip_data({"start_odometer": 10000, "end_odometer": 10200})
        result = svc.create_trip(TENANT, data, "user@example.com")

        assert result["success"] is True
        assert "warnings" in result
        large_warnings = [w for w in result["warnings"] if w["type"] == "large_distance"]
        assert len(large_warnings) == 1
        assert large_warnings[0]["distance_km"] == 200
        assert large_warnings[0]["threshold_km"] == 150

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_large_distance_and_gap_warning_coexist(self, mock_validate):
        """Both gap and large distance warnings can appear together."""
        db = Mock()
        # Trip with gap AND large distance (400 km, threshold default 300)
        created_row = _trip_row({
            "start_odometer": 10100,
            "end_odometer": 10500,
            "distance_km": 400,
        })
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],              # _validate_vehicle
            [{"end_odometer": 10000}], # detect_gap: gap of 100 km (10000→10100)
            1,                         # INSERT returns trip_id
            None,                      # _write_audit_entry INSERT
            [created_row],             # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        data = _valid_trip_data({"start_odometer": 10100, "end_odometer": 10500})
        result = svc.create_trip(TENANT, data, "user@example.com")

        assert result["success"] is True
        assert "warnings" in result
        assert len(result["warnings"]) == 2
        warning_types = [w["type"] for w in result["warnings"]]
        assert "odometer_gap" in warning_types
        assert "large_distance" in warning_types
        # gap_fill_offer still present
        assert "gap_fill_offer" in result


# ── get_trip ────────────────────────────────────────────────


class TestGetTrip:
    """Tests for TripService.get_trip."""

    def test_existing_trip_returns_data(self):
        """Getting an existing trip returns the free-text client_name directly.

        Post-redesign the SELECT carries ``client_name`` and performs no
        contacts JOIN, so the result has no nested ``contact`` object and no
        ``contact_id`` field (Req 4.5).
        """
        db = Mock()
        row = _trip_row({"client_name": "Acme BV"})
        # The redesigned read path issues a single SELECT (no contacts JOIN).
        db.execute_query = Mock(return_value=[row])
        svc = _make_service(db=db)

        result = svc.get_trip(TENANT, 1)

        assert result is not None
        assert result["id"] == 1
        assert result["trip_date"] == "2026-07-13"
        assert result["client_name"] == "Acme BV"
        assert "contact" not in result

    def test_non_existent_trip_returns_none(self):
        """Getting a non-existent trip returns None."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        result = svc.get_trip(TENANT, 999)
        assert result is None

    def test_tenant_scoping_in_query(self):
        """Query includes tenant (administration) parameter for isolation."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_trip(TENANT, 1)

        call_args = db.execute_query.call_args[0]
        assert "administration = %s" in call_args[0]
        assert TENANT in call_args[1]


# ── list_trips ──────────────────────────────────────────────


class TestListTrips:
    """Tests for TripService.list_trips."""

    def test_no_filters_returns_all_non_cancelled(self):
        """No filters returns paginated non-cancelled trips."""
        db = Mock()
        rows = [_trip_row({"id": 1}), _trip_row({"id": 2, "contact_id": None})]
        db.execute_query = Mock(side_effect=[
            [{"total": 2}],      # COUNT query
            rows,                # SELECT data
            [{"id": 5, "company_name": "Acme BV"}],  # enrich contacts
        ])
        svc = _make_service(db=db)

        result = svc.list_trips(TENANT)

        assert result["total"] == 2
        assert len(result["data"]) == 2

    def test_filter_by_vehicle_id(self):
        """Filter by vehicle_id adds WHERE clause."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 1}],
            [_trip_row()],
            [{"id": 5, "company_name": "Acme BV"}],
        ])
        svc = _make_service(db=db)

        svc.list_trips(TENANT, filters={"vehicle_id": 1})

        # Verify the COUNT query includes vehicle_id
        count_query = db.execute_query.call_args_list[0][0][0]
        assert "vehicle_id = %s" in count_query

    def test_filter_by_date_range(self):
        """Filter by date_from and date_to adds WHERE clauses."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 1}],
            [_trip_row()],
            [{"id": 5, "company_name": "Acme BV"}],
        ])
        svc = _make_service(db=db)

        svc.list_trips(TENANT, filters={
            "date_from": "2026-07-01", "date_to": "2026-07-31"
        })

        count_query = db.execute_query.call_args_list[0][0][0]
        assert "trip_date >= %s" in count_query
        assert "trip_date <= %s" in count_query

    def test_filter_by_category(self):
        """Filter by trip_category adds WHERE clause."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 0}],
            [],
        ])
        svc = _make_service(db=db)

        svc.list_trips(TENANT, filters={"trip_category": "Privé"})

        count_query = db.execute_query.call_args_list[0][0][0]
        assert "trip_category = %s" in count_query

    def test_filter_by_contact_id_is_ignored(self):
        """A ``contact_id`` filter is silently ignored, not wired to WHERE.

        Post-redesign the billing/contact-link filter is dropped from the
        WHERE builder, so the query is identical to one without it and raises
        no error (Req 4.3).
        """
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 0}],
            [],
        ])
        svc = _make_service(db=db)

        svc.list_trips(TENANT, filters={"contact_id": 5})

        count_query = db.execute_query.call_args_list[0][0][0]
        assert "contact_id" not in count_query
        # 5 was passed as a filter value but must not reach the params.
        count_params = db.execute_query.call_args_list[0][0][1]
        assert 5 not in count_params

    def test_filter_by_is_billed_is_ignored(self):
        """An ``is_billed`` filter is silently ignored, not wired to WHERE.

        Post-redesign the billing filter is dropped from the WHERE builder,
        so the query is identical to one without it and raises no error
        (Req 4.3).
        """
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 0}],
            [],
        ])
        svc = _make_service(db=db)

        svc.list_trips(TENANT, filters={"is_billed": True})

        count_query = db.execute_query.call_args_list[0][0][0]
        assert "is_billed" not in count_query

    def test_filter_by_is_gap_fill(self):
        """Filter by is_gap_fill adds WHERE clause."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 0}],
            [],
        ])
        svc = _make_service(db=db)

        svc.list_trips(TENANT, filters={"is_gap_fill": True})

        count_query = db.execute_query.call_args_list[0][0][0]
        assert "is_gap_fill = %s" in count_query

    def test_pagination_limit_offset(self):
        """Custom limit and offset are applied to the data query."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 100}],
            [_trip_row()],
            [{"id": 5, "company_name": "Acme BV"}],
        ])
        svc = _make_service(db=db)

        result = svc.list_trips(TENANT, filters={"limit": 10, "offset": 20})

        assert result["total"] == 100
        # Verify LIMIT and OFFSET in data query
        data_call = db.execute_query.call_args_list[1]
        data_params = data_call[0][1]
        # Last two params should be limit and offset
        assert data_params[-2] == 10
        assert data_params[-1] == 20

    def test_empty_results(self):
        """No matching trips returns empty data list with total=0."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 0}],
            [],
        ])
        svc = _make_service(db=db)

        result = svc.list_trips(TENANT, filters={"vehicle_id": 999})

        assert result["total"] == 0
        assert result["data"] == []


# ── enrich_with_contacts (REMOVED — task 9.1) ───────────────
#
# TestEnrichWithContacts was deleted: the redesign dropped
# ``TripService.enrich_with_contacts`` entirely. Trips now carry a free-text
# ``client_name`` directly, with no contacts JOIN and no nested contact object
# on any read path (Req 4.5). The billing-free read invariant is covered by
# Property 8 (query side) in TestQueryPropertiesTaxLog below.


# ── get_summary ─────────────────────────────────────────────


class TestGetSummary:
    """Tests for TripService.get_summary."""

    def _setup_summary_service(self, vehicle_row=None, category_rows=None,
                                monthly_rows=None):
        """Helper to set up mocks for get_summary tests."""
        db = Mock()
        if vehicle_row is None:
            vehicle_row = [{"id": 1, "vehicle_type": "business", "odometer_unit": "km"}]
        if category_rows is None:
            category_rows = [
                {"trip_category": "Zakelijk", "total_km": 8000},
                {"trip_category": "Privé", "total_km": 300},
                {"trip_category": "Woon-werk", "total_km": 150},
            ]
        if monthly_rows is None:
            monthly_rows = [
                {"month": "2026-01", "trip_category": "Zakelijk", "total_km": 800},
                {"month": "2026-01", "trip_category": "Privé", "total_km": 50},
            ]
        db.execute_query = Mock(side_effect=[
            vehicle_row,      # _get_vehicle_info
            category_rows,    # category totals
            monthly_rows,     # monthly breakdown
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)
        return svc

    def test_yearly_totals_per_category(self):
        """Summary returns correct km totals per category."""
        svc = self._setup_summary_service()

        result = svc.get_summary(TENANT, 1, 2026)

        assert result["zakelijk_km"] == 8000
        assert result["prive_km"] == 300
        assert result["woonwerk_km"] == 150
        assert result["total_km"] == 8450

    def test_bijtelling_km_calculation(self):
        """bijtelling_km = Privé + Woon-werk."""
        svc = self._setup_summary_service()

        result = svc.get_summary(TENANT, 1, 2026)

        assert result["bijtelling_km"] == 450  # 300 + 150

    def test_bijtelling_warning_flag_when_exceeded(self):
        """bijtelling_warning is True when bijtelling_km >= threshold (400)."""
        category_rows = [
            {"trip_category": "Zakelijk", "total_km": 5000},
            {"trip_category": "Privé", "total_km": 350},
            {"trip_category": "Woon-werk", "total_km": 100},
        ]
        svc = self._setup_summary_service(category_rows=category_rows)

        result = svc.get_summary(TENANT, 1, 2026)

        # 350 + 100 = 450 >= 400 threshold
        assert result["bijtelling_warning"] is True

    def test_bijtelling_warning_false_when_below_threshold(self):
        """bijtelling_warning is False when bijtelling_km < threshold."""
        category_rows = [
            {"trip_category": "Zakelijk", "total_km": 5000},
            {"trip_category": "Privé", "total_km": 100},
            {"trip_category": "Woon-werk", "total_km": 50},
        ]
        svc = self._setup_summary_service(category_rows=category_rows)

        result = svc.get_summary(TENANT, 1, 2026)

        # 100 + 50 = 150 < 400 threshold
        assert result["bijtelling_warning"] is False

    def test_tax_deduction_for_private_for_business(self):
        """Private-for-business vehicles get tax_deduction = zakelijk_km × rate."""
        vehicle_row = [{"id": 1, "vehicle_type": "private_for_business", "odometer_unit": "km"}]
        category_rows = [
            {"trip_category": "Zakelijk", "total_km": 10000},
            {"trip_category": "Privé", "total_km": 200},
            {"trip_category": "Woon-werk", "total_km": 100},
        ]
        svc = self._setup_summary_service(
            vehicle_row=vehicle_row, category_rows=category_rows
        )

        result = svc.get_summary(TENANT, 1, 2026)

        # 10000 × 0.23 = 2300.0
        assert result["tax_deduction"] == 2300.0

    def test_monthly_breakdown(self):
        """Monthly breakdown groups by month and category."""
        monthly_rows = [
            {"month": "2026-01", "trip_category": "Zakelijk", "total_km": 800},
            {"month": "2026-01", "trip_category": "Privé", "total_km": 50},
            {"month": "2026-02", "trip_category": "Zakelijk", "total_km": 900},
        ]
        svc = self._setup_summary_service(monthly_rows=monthly_rows)

        result = svc.get_summary(TENANT, 1, 2026)

        assert len(result["monthly_breakdown"]) == 2
        jan = result["monthly_breakdown"][0]
        assert jan["month"] == "2026-01"
        assert jan["zakelijk"] == 800
        assert jan["prive"] == 50

    def test_miles_to_km_conversion(self):
        """Vehicle with odometer_unit='miles' converts to km."""
        vehicle_row = [{"id": 1, "vehicle_type": "business", "odometer_unit": "miles"}]
        category_rows = [
            {"trip_category": "Zakelijk", "total_km": 1000},  # in miles
        ]
        monthly_rows = []
        svc = self._setup_summary_service(
            vehicle_row=vehicle_row,
            category_rows=category_rows,
            monthly_rows=monthly_rows,
        )

        result = svc.get_summary(TENANT, 1, 2026)

        # 1000 miles × 1.60934 = 1609 km (rounded)
        assert result["zakelijk_km"] == 1609
        assert result["total_km"] == 1609

    def test_no_trips_returns_zeros(self):
        """No trips for the year returns all zeros."""
        svc = self._setup_summary_service(category_rows=[], monthly_rows=[])

        result = svc.get_summary(TENANT, 1, 2026)

        assert result["total_km"] == 0
        assert result["zakelijk_km"] == 0
        assert result["prive_km"] == 0
        assert result["woonwerk_km"] == 0
        assert result["bijtelling_km"] == 0
        assert result["bijtelling_warning"] is False
        assert result["monthly_breakdown"] == []

    def test_vehicle_not_found_raises_value_error(self):
        """Non-existent vehicle raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])  # No vehicle
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="Vehicle .* not found"):
            svc.get_summary(TENANT, 999, 2026)


# ── get_bijtelling_status ───────────────────────────────────


class TestGetBijtellingStatus:
    """Tests for TripService.get_bijtelling_status."""

    def test_lightweight_bijtelling_check(self):
        """Returns bijtelling km, limit, warning, exceeded, remaining."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"id": 1, "vehicle_type": "business", "odometer_unit": "km"}],
            [{"total_km": 350}],
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        result = svc.get_bijtelling_status(TENANT, 1, 2026)

        assert result["bijtelling_km"] == 350
        assert result["bijtelling_limit"] == 500
        assert result["remaining_km"] == 150
        assert result["bijtelling_exceeded"] is False

    def test_exceeded_flag_when_over_limit(self):
        """bijtelling_exceeded is True when km > limit."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"id": 1, "vehicle_type": "business", "odometer_unit": "km"}],
            [{"total_km": 600}],
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        result = svc.get_bijtelling_status(TENANT, 1, 2026)

        assert result["bijtelling_exceeded"] is True
        assert result["remaining_km"] == 0

    def test_remaining_km_calculation(self):
        """remaining_km = max(0, limit - bijtelling_km)."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"id": 1, "vehicle_type": "business", "odometer_unit": "km"}],
            [{"total_km": 200}],
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        result = svc.get_bijtelling_status(TENANT, 1, 2026)

        assert result["remaining_km"] == 300  # 500 - 200

    def test_vehicle_not_found_raises_value_error(self):
        """Non-existent vehicle raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="Vehicle .* not found"):
            svc.get_bijtelling_status(TENANT, 999, 2026)

    def test_no_trips_returns_zero_bijtelling(self):
        """No trips means bijtelling_km = 0."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"id": 1, "vehicle_type": "business", "odometer_unit": "km"}],
            [{"total_km": None}],  # SUM returns None when no rows
        ])
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(db=db, parameter_service=param_svc)

        result = svc.get_bijtelling_status(TENANT, 1, 2026)

        assert result["bijtelling_km"] == 0
        assert result["remaining_km"] == 500


# ── _validate_category_and_purpose ──────────────────────────


class TestValidateCategoryAndPurpose:
    """Tests for TripService._validate_category_and_purpose."""

    def test_valid_values_pass(self):
        """Valid category and purpose do not raise."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        # Should not raise
        svc._validate_category_and_purpose(TENANT, "Zakelijk", "Klantbezoek")

    def test_invalid_category_raises_value_error(self):
        """Invalid category raises ValueError."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        with pytest.raises(ValueError, match="Invalid trip_category 'Vakantie'"):
            svc._validate_category_and_purpose(TENANT, "Vakantie", "Klantbezoek")

    def test_invalid_purpose_raises_value_error(self):
        """Invalid purpose raises ValueError."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        with pytest.raises(ValueError, match="Invalid trip_purpose 'Strandbezoek'"):
            svc._validate_category_and_purpose(TENANT, "Zakelijk", "Strandbezoek")

    def test_parameter_fallback_to_defaults(self):
        """When ParameterService returns None, falls back to MODULE_REGISTRY."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_service(parameter_service=param_svc)

        # "Woon-werk" is in defaults, should pass
        svc._validate_category_and_purpose(TENANT, "Woon-werk", "Overig")

    def test_custom_parameter_values_used(self):
        """When ParameterService returns custom list, uses those values."""
        param_svc = Mock()

        def get_param_side_effect(namespace, key, tenant=None):
            if key == "trip_categories":
                return ["Custom1", "Custom2"]
            if key == "trip_purposes":
                return ["Purpose1", "Purpose2"]
            return None

        param_svc.get_param = Mock(side_effect=get_param_side_effect)
        svc = _make_service(parameter_service=param_svc)

        # Default categories no longer valid
        with pytest.raises(ValueError, match="Invalid trip_category"):
            svc._validate_category_and_purpose(TENANT, "Zakelijk", "Purpose1")

        # Custom categories are valid
        svc._validate_category_and_purpose(TENANT, "Custom1", "Purpose1")


# ── detect_gap ──────────────────────────────────────────────


class TestDetectGap:
    """Tests for TripService.detect_gap.

    Covers: Requirement 4 (Odometer Gap Detection)
    """

    def test_gap_detected_returns_gap_info(self):
        """When start_odometer > previous end_odometer, return gap info dict."""
        db = Mock()
        # Previous trip's end_odometer is 45218
        db.execute_query = Mock(return_value=[{"end_odometer": 45218}])
        svc = _make_service(db=db)

        result = svc.detect_gap(TENANT, vehicle_id=1, start_odometer=45230)

        assert result is not None
        assert result["gap_km"] == 12
        assert result["previous_end_odometer"] == 45218
        assert result["current_start_odometer"] == 45230

    def test_no_gap_returns_none(self):
        """When start_odometer == previous end_odometer, return None."""
        db = Mock()
        db.execute_query = Mock(return_value=[{"end_odometer": 45230}])
        svc = _make_service(db=db)

        result = svc.detect_gap(TENANT, vehicle_id=1, start_odometer=45230)

        assert result is None

    def test_start_odometer_less_than_previous_end_returns_none(self):
        """When start_odometer < previous end_odometer (overlap), return None."""
        db = Mock()
        db.execute_query = Mock(return_value=[{"end_odometer": 45300}])
        svc = _make_service(db=db)

        result = svc.detect_gap(TENANT, vehicle_id=1, start_odometer=45230)

        assert result is None

    def test_first_trip_compares_against_vehicle_start_odometer(self):
        """When no previous trips exist, compare against vehicle's start_odometer."""
        db = Mock()
        # First call: no trips found; second call: vehicle start_odometer
        db.execute_query = Mock(side_effect=[
            [],                              # No previous trips
            [{"start_odometer": 45000}],     # Vehicle start_odometer
        ])
        svc = _make_service(db=db)

        result = svc.detect_gap(TENANT, vehicle_id=1, start_odometer=45050)

        assert result is not None
        assert result["gap_km"] == 50
        assert result["previous_end_odometer"] == 45000
        assert result["current_start_odometer"] == 45050

    def test_first_trip_no_gap(self):
        """First trip with start_odometer matching vehicle's start_odometer."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [],                              # No previous trips
            [{"start_odometer": 45000}],     # Vehicle start_odometer
        ])
        svc = _make_service(db=db)

        result = svc.detect_gap(TENANT, vehicle_id=1, start_odometer=45000)

        assert result is None

    def test_vehicle_not_found_returns_none(self):
        """When vehicle doesn't exist (no trips, no vehicle row), return None."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [],  # No previous trips
            [],  # Vehicle not found
        ])
        svc = _make_service(db=db)

        result = svc.detect_gap(TENANT, vehicle_id=999, start_odometer=50000)

        assert result is None

    def test_ignores_cancelled_trips(self):
        """Query includes is_cancelled = FALSE to ignore cancelled trips."""
        db = Mock()
        db.execute_query = Mock(return_value=[{"end_odometer": 45218}])
        svc = _make_service(db=db)

        svc.detect_gap(TENANT, vehicle_id=1, start_odometer=45230)

        # Verify the query includes is_cancelled = FALSE
        query = db.execute_query.call_args[0][0]
        assert "is_cancelled = FALSE" in query

    def test_tenant_scoping_in_trip_query(self):
        """Trip query is scoped by administration (tenant)."""
        db = Mock()
        db.execute_query = Mock(return_value=[{"end_odometer": 45218}])
        svc = _make_service(db=db)

        svc.detect_gap(TENANT, vehicle_id=1, start_odometer=45230)

        query = db.execute_query.call_args[0][0]
        params = db.execute_query.call_args[0][1]
        assert "administration = %s" in query
        assert TENANT in params

    def test_orders_by_end_odometer_desc(self):
        """Query orders by end_odometer DESC to find the highest reading."""
        db = Mock()
        db.execute_query = Mock(return_value=[{"end_odometer": 45218}])
        svc = _make_service(db=db)

        svc.detect_gap(TENANT, vehicle_id=1, start_odometer=45230)

        query = db.execute_query.call_args[0][0]
        assert "ORDER BY end_odometer DESC" in query
        assert "LIMIT 1" in query


# ── create_gap_fill ─────────────────────────────────────────


class TestCreateGapFill:
    """Tests for TripService.create_gap_fill."""

    def _gap_fill_data(self, overrides=None):
        """Generate valid gap-fill creation data."""
        data = {
            "vehicle_id": 1,
            "trip_date": "2026-07-12",
            "start_odometer": 45218,
            "end_odometer": 45230,
            "start_address": "Onbekend",
            "end_address": "Onbekend",
            "trip_category": "Privé",
            "trip_purpose": "Niet geregistreerd",
        }
        if overrides:
            data.update(overrides)
        return data

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_happy_path_creates_gap_fill_trip(self, mock_validate):
        """Gap-fill creates trip with is_gap_fill=True and writes audit."""
        db = Mock()
        gap_row = _trip_row({
            "id": 10,
            "trip_date": date(2026, 7, 12),
            "start_address": "Onbekend",
            "end_address": "Onbekend",
            "start_odometer": 45218,
            "end_odometer": 45230,
            "distance_km": 12,
            "trip_category": "Privé",
            "trip_purpose": "Niet geregistreerd",
            "is_gap_fill": 1,
            "contact_id": None,
        })
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            10,                  # INSERT returns trip_id
            None,                # _write_audit_entry INSERT
            [gap_row],           # get_trip SELECT
            [],                  # enrich_with_contacts (no contacts)
        ])
        svc = _make_service(db=db)

        result = svc.create_gap_fill(TENANT, self._gap_fill_data(), "user@example.com")

        assert result["success"] is True
        assert result["data"]["id"] == 10
        assert result["data"]["is_gap_fill"] is True
        assert result["data"]["trip_category"] == "Privé"
        assert result["data"]["trip_purpose"] == "Niet geregistreerd"

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_defaults_category_and_purpose(self, mock_validate):
        """Defaults trip_category to 'Privé' and trip_purpose to 'Niet geregistreerd'."""
        db = Mock()
        gap_row = _trip_row({
            "id": 10,
            "trip_category": "Privé",
            "trip_purpose": "Niet geregistreerd",
            "is_gap_fill": 1,
            "contact_id": None,
        })
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            10,                  # INSERT
            None,                # _write_audit_entry
            [gap_row],           # get_trip
            [],                  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        # Data without category/purpose — defaults should apply
        data = {
            "vehicle_id": 1,
            "trip_date": "2026-07-12",
            "start_odometer": 45218,
            "end_odometer": 45230,
            "start_address": "Onbekend",
            "end_address": "Onbekend",
        }
        result = svc.create_gap_fill(TENANT, data, "user@example.com")

        assert result["success"] is True
        # Verify INSERT params include defaults
        insert_call = db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        # trip_category is at position 9, trip_purpose at position 10
        assert insert_params[9] == "Privé"
        assert insert_params[10] == "Niet geregistreerd"

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_is_gap_fill_always_true_in_insert(self, mock_validate):
        """is_gap_fill is always True regardless of input data."""
        db = Mock()
        gap_row = _trip_row({"id": 10, "is_gap_fill": 1, "contact_id": None})
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            10,                  # INSERT
            None,                # _write_audit_entry
            [gap_row],           # get_trip
            [],                  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        # Even if caller passes is_gap_fill=False, it should be overridden
        data = self._gap_fill_data({"is_gap_fill": False})
        svc.create_gap_fill(TENANT, data, "user@example.com")

        # Verify INSERT params have is_gap_fill=True.
        # Post-redesign INSERT column order (task 8.1): administration(0),
        # vehicle_id(1), trip_date(2), start_time(3), end_time(4),
        # start_address(5), end_address(6), start_odometer(7), end_odometer(8),
        # trip_category(9), trip_purpose(10), route_description(11),
        # client_name(12), project_name(13), notes(14), is_gap_fill(15),
        # created_by(16). No contact_id / is_billable are written (Req 4.6).
        insert_call = db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        assert insert_params[15] is True

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_does_not_call_detect_gap(self, mock_validate):
        """Gap-fill does NOT call detect_gap (since this IS the gap fill)."""
        db = Mock()
        gap_row = _trip_row({"id": 10, "is_gap_fill": 1, "contact_id": None})
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            10,                  # INSERT
            None,                # _write_audit_entry
            [gap_row],           # get_trip
            [],                  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        with patch.object(svc, "detect_gap") as mock_detect:
            svc.create_gap_fill(TENANT, self._gap_fill_data(), "user@example.com")
            mock_detect.assert_not_called()

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_writes_audit_entry(self, mock_validate):
        """Gap-fill writes audit entry with action='created' and version=1."""
        db = Mock()
        gap_row = _trip_row({"id": 10, "is_gap_fill": 1, "contact_id": None})
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            10,                  # INSERT
            None,                # _write_audit_entry
            [gap_row],           # get_trip
            [],                  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        svc.create_gap_fill(TENANT, self._gap_fill_data(), "user@example.com")

        # Third call should be the audit INSERT
        audit_call = db.execute_query.call_args_list[2]
        audit_query = audit_call[0][0]
        audit_params = audit_call[0][1]
        assert "zzp_trip_audit" in audit_query
        assert audit_params[0] == TENANT       # administration
        assert audit_params[1] == 10           # trip_id
        assert audit_params[2] == 1            # version
        assert audit_params[3] == "created"    # action
        assert audit_params[6] == "user@example.com"  # changed_by

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_end_odometer_must_exceed_start(self, mock_validate):
        """end_odometer <= start_odometer raises ValueError."""
        svc = _make_service()

        data = self._gap_fill_data({"start_odometer": 45230, "end_odometer": 45218})
        with pytest.raises(ValueError, match="end_odometer must be greater"):
            svc.create_gap_fill(TENANT, data, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_vehicle_not_found_raises_value_error(self, mock_validate):
        """Non-existent vehicle raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])  # _validate_vehicle finds nothing
        svc = _make_service(db=db)

        data = self._gap_fill_data({"vehicle_id": 999})
        with pytest.raises(ValueError, match="Vehicle 999 not found"):
            svc.create_gap_fill(TENANT, data, "user@example.com")

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_does_not_mutate_input_data(self, mock_validate):
        """Input data dict is not mutated."""
        db = Mock()
        gap_row = _trip_row({"id": 10, "is_gap_fill": 1, "contact_id": None})
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            10,                  # INSERT
            None,                # _write_audit_entry
            [gap_row],           # get_trip
            [],                  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        original_data = self._gap_fill_data()
        original_copy = dict(original_data)
        svc.create_gap_fill(TENANT, original_data, "user@example.com")

        # Original dict should be unchanged
        assert original_data == original_copy

    @patch("services.zzp_trip_service.TripService.validate_fields")
    def test_skips_category_purpose_validation(self, mock_validate):
        """Gap-fill does NOT validate category/purpose against configured lists."""
        db = Mock()
        gap_row = _trip_row({"id": 10, "is_gap_fill": 1, "contact_id": None})
        db.execute_query = Mock(side_effect=[
            [{"id": 1}],         # _validate_vehicle
            10,                  # INSERT
            None,                # _write_audit_entry
            [gap_row],           # get_trip
            [],                  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        with patch.object(svc, "_validate_category_and_purpose") as mock_val:
            svc.create_gap_fill(TENANT, self._gap_fill_data(), "user@example.com")
            mock_val.assert_not_called()


# ── get_unresolved_gaps ─────────────────────────────────────


class TestGetUnresolvedGaps:
    """Tests for TripService.get_unresolved_gaps.

    Covers: Requirement 4.7 (List unresolved gap-fill entries)
    Unresolved gaps: is_gap_fill=TRUE, trip_purpose='Niet geregistreerd', is_cancelled=FALSE
    """

    def _gap_row(self, id=1, vehicle_id=1, client_name=None):
        """Generate a gap-fill trip row as returned by the DB."""
        return _trip_row({
            "id": id,
            "vehicle_id": vehicle_id,
            "trip_date": date(2026, 7, 12),
            "start_address": "Onbekend",
            "end_address": "Onbekend",
            "start_odometer": 45218,
            "end_odometer": 45230,
            "distance_km": 12,
            "trip_category": "Privé",
            "trip_purpose": "Niet geregistreerd",
            "is_gap_fill": 1,
            "client_name": client_name,
        })

    def test_returns_unresolved_gaps(self):
        """Returns gap-fill trips that still have purpose 'Niet geregistreerd'.

        The redesigned path issues a single SELECT (no contacts enrichment).
        """
        db = Mock()
        gap_rows = [self._gap_row(id=1), self._gap_row(id=2)]
        db.execute_query = Mock(return_value=gap_rows)
        svc = _make_service(db=db)

        result = svc.get_unresolved_gaps(TENANT)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[0]["is_gap_fill"] is True
        assert result[0]["trip_purpose"] == "Niet geregistreerd"
        # No contacts enrichment on the read path (Req 4.5).
        assert "contact" not in result[0]

    def test_filter_by_vehicle_id(self):
        """When vehicle_id is provided, query filters by that vehicle."""
        db = Mock()
        db.execute_query = Mock(return_value=[self._gap_row(id=5, vehicle_id=2)])
        svc = _make_service(db=db)

        result = svc.get_unresolved_gaps(TENANT, vehicle_id=2)

        assert len(result) == 1
        assert result[0]["vehicle_id"] == 2
        # Verify the query includes vehicle_id filter
        query = db.execute_query.call_args_list[0][0][0]
        params = db.execute_query.call_args_list[0][0][1]
        assert "vehicle_id = %s" in query
        assert 2 in params

    def test_empty_results(self):
        """Returns empty list when no unresolved gaps exist."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        result = svc.get_unresolved_gaps(TENANT)

        assert result == []

    def test_tenant_isolation(self):
        """Query is always scoped by administration (tenant)."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_unresolved_gaps("tenant_A")

        query = db.execute_query.call_args[0][0]
        params = db.execute_query.call_args[0][1]
        assert "administration = %s" in query
        assert "tenant_A" in params

    def test_query_filters_are_correct(self):
        """Query includes all required WHERE conditions."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_unresolved_gaps(TENANT)

        query = db.execute_query.call_args[0][0]
        params = db.execute_query.call_args[0][1]
        assert "is_gap_fill = TRUE" in query
        assert "trip_purpose = %s" in query
        assert "Niet geregistreerd" in params
        assert "is_cancelled = FALSE" in query
        assert "ORDER BY trip_date DESC" in query

    def test_without_vehicle_id_no_vehicle_filter(self):
        """When vehicle_id is None, no vehicle_id filter is applied."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_unresolved_gaps(TENANT, vehicle_id=None)

        query = db.execute_query.call_args[0][0]
        assert "vehicle_id = %s" not in query

    def test_no_contact_enrichment(self):
        """Gap results carry client_name directly, with no nested contact.

        The ``enrich_with_contacts`` call site was removed from this path
        (Req 4.5), so a single SELECT runs and no ``contact`` object appears.
        """
        db = Mock()
        gap_row = self._gap_row(id=1, client_name="Acme BV")
        db.execute_query = Mock(return_value=[gap_row])
        svc = _make_service(db=db)

        result = svc.get_unresolved_gaps(TENANT)

        assert len(result) == 1
        assert result[0]["client_name"] == "Acme BV"
        assert "contact" not in result[0]
        # Exactly one query — the SELECT — with no follow-up enrichment query.
        assert db.execute_query.call_count == 1


# ── update_trip ─────────────────────────────────────────────


class TestUpdateTrip:
    """Tests for TripService.update_trip — corrections with audit trail.

    Covers: Requirement 7 (version incrementing, audit logging, correction_reason)
    """

    def _existing_trip_row(self, overrides=None):
        """Generate a raw trip row as returned from the DB (for _get_raw_trip)."""
        row = {
            "id": 1,
            "administration": TENANT,
            "vehicle_id": 1,
            "trip_date": date(2026, 7, 13),
            "start_time": "08:30",
            "end_time": "09:15",
            "start_address": "Keizersgracht 100, Amsterdam",
            "end_address": "Stationsplein 1, Utrecht",
            "start_odometer": 45230,
            "end_odometer": 45275,
            "distance_km": 45,
            "trip_category": "Zakelijk",
            "trip_purpose": "Klantbezoek",
            "route_description": None,
            "client_name": "Acme BV",
            "project_name": "Project Alpha",
            "notes": None,
            "is_gap_fill": False,
            "is_cancelled": False,
            "cancel_reason": None,
            "version": 1,
            "created_at": datetime(2026, 7, 13, 8, 30, 0),
            "updated_at": datetime(2026, 7, 13, 8, 30, 0),
            "created_by": "user@example.com",
        }
        if overrides:
            row.update(overrides)
        return row

    def test_happy_path_updates_fields_and_increments_version(self):
        """Update trip: changes fields, increments version, returns updated trip."""
        db = Mock()
        existing_row = self._existing_trip_row()
        updated_row = _trip_row({
            "end_odometer": 45280,
            "distance_km": 50,
            "trip_purpose": "Vergadering",
            "version": 2,
        })
        db.execute_query = Mock(side_effect=[
            [existing_row],    # _get_raw_trip
            None,              # UPDATE query
            None,              # _write_audit_entry INSERT
            [updated_row],     # get_trip SELECT
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        result = svc.update_trip(
            TENANT, 1,
            {"end_odometer": 45280, "trip_purpose": "Vergadering"},
            correction_reason="Foutieve eindstand gecorrigeerd",
            updated_by="admin@example.com",
        )

        assert result is not None
        assert result["end_odometer"] == 45280
        assert result["trip_purpose"] == "Vergadering"
        assert result["version"] == 2

    def test_version_increments_from_current(self):
        """Version is incremented from the trip's current version."""
        db = Mock()
        existing_row = self._existing_trip_row({"version": 3})
        updated_row = _trip_row({"version": 4, "notes": "Updated"})
        db.execute_query = Mock(side_effect=[
            [existing_row],    # _get_raw_trip (version=3)
            None,              # UPDATE
            None,              # audit INSERT
            [updated_row],     # get_trip
            [{"id": 5, "company_name": "Acme BV"}],  # contacts
        ])
        svc = _make_service(db=db)

        result = svc.update_trip(
            TENANT, 1, {"notes": "Updated"},
            correction_reason="Notes aanpassing",
            updated_by="admin@example.com",
        )

        # Verify UPDATE params include version=4
        update_call = db.execute_query.call_args_list[1]
        update_params = update_call[0][1]
        # version value should be 4 (in the params)
        assert 4 in update_params

    def test_audit_entry_created_with_changed_fields(self):
        """Audit entry is written with correct action, version, and changed_fields."""
        db = Mock()
        existing_row = self._existing_trip_row()
        updated_row = _trip_row({"end_odometer": 45280, "version": 2})
        db.execute_query = Mock(side_effect=[
            [existing_row],    # _get_raw_trip
            None,              # UPDATE
            None,              # _write_audit_entry INSERT
            [updated_row],     # get_trip
            [{"id": 5, "company_name": "Acme BV"}],  # contacts
        ])
        svc = _make_service(db=db)

        svc.update_trip(
            TENANT, 1, {"end_odometer": 45280},
            correction_reason="Foutieve eindstand",
            updated_by="admin@example.com",
        )

        # The audit INSERT is the 3rd call (index 2)
        audit_call = db.execute_query.call_args_list[2]
        audit_query = audit_call[0][0]
        audit_params = audit_call[0][1]
        assert "zzp_trip_audit" in audit_query
        # Check params: (tenant, trip_id, version, action, changed_fields, correction_reason, changed_by)
        assert audit_params[0] == TENANT        # administration
        assert audit_params[1] == 1             # trip_id
        assert audit_params[2] == 2             # version
        assert audit_params[3] == "updated"     # action
        # changed_fields should be JSON with end_odometer diff
        import json
        changed = json.loads(audit_params[4])
        assert "end_odometer" in changed
        assert changed["end_odometer"]["old"] == 45275
        assert changed["end_odometer"]["new"] == 45280
        assert audit_params[5] == "Foutieve eindstand"  # correction_reason
        assert audit_params[6] == "admin@example.com"   # changed_by

    def test_correction_reason_required(self):
        """Missing correction_reason raises ValueError."""
        svc = _make_service()

        with pytest.raises(ValueError, match="correction_reason is required"):
            svc.update_trip(TENANT, 1, {"notes": "test"}, correction_reason="", updated_by="x")

    def test_correction_reason_none_raises(self):
        """None correction_reason raises ValueError."""
        svc = _make_service()

        with pytest.raises(ValueError, match="correction_reason is required"):
            svc.update_trip(TENANT, 1, {"notes": "test"}, correction_reason=None, updated_by="x")

    def test_correction_reason_whitespace_only_raises(self):
        """Whitespace-only correction_reason raises ValueError."""
        svc = _make_service()

        with pytest.raises(ValueError, match="correction_reason is required"):
            svc.update_trip(TENANT, 1, {"notes": "test"}, correction_reason="   ", updated_by="x")

    def test_trip_not_found_raises_value_error(self):
        """Non-existent trip raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])  # _get_raw_trip returns nothing
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="Trip 999 not found"):
            svc.update_trip(
                TENANT, 999, {"notes": "test"},
                correction_reason="Correction", updated_by="user@example.com",
            )

    def test_update_not_blocked_by_prior_billing_state(self):
        """Updates proceed regardless of any prior billing value (Req 4.7).

        The old is_billed "cannot be edited" guard was removed in the tax-log
        redesign; a valid update must complete and persist even when the raw
        row still carries a stale billing flag from before the migration.
        """
        db = Mock()
        existing_row = self._existing_trip_row({"is_billed": True})
        updated_row = _trip_row({"notes": "test", "version": 2})
        db.execute_query = Mock(side_effect=[
            [existing_row],    # _get_raw_trip (stale is_billed=True)
            None,              # UPDATE
            None,              # audit INSERT
            [updated_row],     # get_trip SELECT
        ])
        svc = _make_service(db=db)

        result = svc.update_trip(
            TENANT, 1, {"notes": "test"},
            correction_reason="Correction", updated_by="user@example.com",
        )

        assert result is not None
        assert result["notes"] == "test"
        assert result["version"] == 2

    def test_non_updatable_fields_are_ignored(self):
        """Fields not in UPDATABLE_FIELDS are silently ignored."""
        db = Mock()
        existing_row = self._existing_trip_row()
        db.execute_query = Mock(return_value=[existing_row])
        svc = _make_service(db=db)

        # distance_km, is_billed, version are not updatable
        with pytest.raises(ValueError, match="No valid fields to update"):
            svc.update_trip(
                TENANT, 1,
                {"distance_km": 100, "is_billed": True, "version": 5},
                correction_reason="Test", updated_by="user@example.com",
            )

    def test_no_actual_changes_raises_value_error(self):
        """If all provided values are same as existing, raises ValueError."""
        db = Mock()
        existing_row = self._existing_trip_row()
        db.execute_query = Mock(return_value=[existing_row])
        svc = _make_service(db=db)

        # Provide same values as existing
        with pytest.raises(ValueError, match="No fields have changed"):
            svc.update_trip(
                TENANT, 1,
                {"end_odometer": 45275, "trip_purpose": "Klantbezoek"},
                correction_reason="Test", updated_by="user@example.com",
            )

    def test_multiple_fields_changed_all_in_diff(self):
        """Multiple field changes all appear in the changed_fields diff."""
        db = Mock()
        existing_row = self._existing_trip_row()
        updated_row = _trip_row({
            "end_odometer": 45300,
            "trip_purpose": "Vergadering",
            "notes": "Updated notes",
            "version": 2,
        })
        db.execute_query = Mock(side_effect=[
            [existing_row],    # _get_raw_trip
            None,              # UPDATE
            None,              # audit INSERT
            [updated_row],     # get_trip
            [{"id": 5, "company_name": "Acme BV"}],  # contacts
        ])
        svc = _make_service(db=db)

        svc.update_trip(
            TENANT, 1,
            {"end_odometer": 45300, "trip_purpose": "Vergadering", "notes": "Updated notes"},
            correction_reason="Meerdere correcties",
            updated_by="admin@example.com",
        )

        # Check the UPDATE query has all changed fields
        update_call = db.execute_query.call_args_list[1]
        update_query = update_call[0][0]
        assert "end_odometer = %s" in update_query
        assert "trip_purpose = %s" in update_query
        assert "notes = %s" in update_query
        assert "version = %s" in update_query

    def test_tenant_scoping_in_get_raw_trip(self):
        """_get_raw_trip query includes tenant (administration) parameter."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        with pytest.raises(ValueError):
            svc.update_trip(
                "my_tenant", 1, {"notes": "test"},
                correction_reason="Test", updated_by="user@example.com",
            )

        query = db.execute_query.call_args[0][0]
        params = db.execute_query.call_args[0][1]
        assert "administration = %s" in query
        assert "my_tenant" in params


# ── cancel_trip ─────────────────────────────────────────────


class TestCancelTrip:
    """Tests for TripService.cancel_trip — soft-delete with reason.

    Covers: Requirement 7 (soft cancellation, audit trail, billed trip protection)
    """

    def _existing_trip_row(self, overrides=None):
        """Generate a raw trip row as returned from the DB (for _get_raw_trip)."""
        row = {
            "id": 1,
            "administration": TENANT,
            "vehicle_id": 1,
            "trip_date": date(2026, 7, 13),
            "start_time": "08:30",
            "end_time": "09:15",
            "start_address": "Keizersgracht 100, Amsterdam",
            "end_address": "Stationsplein 1, Utrecht",
            "start_odometer": 45230,
            "end_odometer": 45275,
            "distance_km": 45,
            "trip_category": "Zakelijk",
            "trip_purpose": "Klantbezoek",
            "route_description": None,
            "client_name": "Acme BV",
            "project_name": "Project Alpha",
            "notes": None,
            "is_gap_fill": False,
            "is_cancelled": False,
            "cancel_reason": None,
            "version": 1,
            "created_at": datetime(2026, 7, 13, 8, 30, 0),
            "updated_at": datetime(2026, 7, 13, 8, 30, 0),
            "created_by": "user@example.com",
        }
        if overrides:
            row.update(overrides)
        return row

    def test_happy_path_cancels_trip_and_writes_audit(self):
        """Successful cancellation: sets is_cancelled, writes audit, returns True."""
        db = Mock()
        existing_row = self._existing_trip_row()
        db.execute_query = Mock(side_effect=[
            [existing_row],    # _get_raw_trip
            None,              # UPDATE (set is_cancelled)
            None,              # _write_audit_entry INSERT
        ])
        svc = _make_service(db=db)

        result = svc.cancel_trip(
            TENANT, 1,
            cancel_reason="Dubbel ingevoerd",
            cancelled_by="admin@example.com",
        )

        assert result is True

        # Verify UPDATE query sets is_cancelled and cancel_reason
        update_call = db.execute_query.call_args_list[1]
        update_query = update_call[0][0]
        update_params = update_call[0][1]
        assert "is_cancelled = TRUE" in update_query
        assert "cancel_reason = %s" in update_query
        assert update_params[0] == "Dubbel ingevoerd"
        assert update_params[1] == 1  # trip_id
        assert update_params[2] == TENANT

        # Verify audit entry
        audit_call = db.execute_query.call_args_list[2]
        audit_query = audit_call[0][0]
        audit_params = audit_call[0][1]
        assert "zzp_trip_audit" in audit_query
        assert audit_params[0] == TENANT           # administration
        assert audit_params[1] == 1                # trip_id
        assert audit_params[2] == 1                # version (current)
        assert audit_params[3] == "cancelled"      # action
        assert audit_params[4] is None             # changed_fields (none for cancel)
        assert audit_params[5] == "Dubbel ingevoerd"  # correction_reason
        assert audit_params[6] == "admin@example.com"  # changed_by

    def test_cancel_reason_required_empty_string(self):
        """Empty cancel_reason raises ValueError."""
        svc = _make_service()

        with pytest.raises(ValueError, match="cancel_reason is required"):
            svc.cancel_trip(TENANT, 1, cancel_reason="", cancelled_by="user@example.com")

    def test_cancel_reason_required_none(self):
        """None cancel_reason raises ValueError."""
        svc = _make_service()

        with pytest.raises(ValueError, match="cancel_reason is required"):
            svc.cancel_trip(TENANT, 1, cancel_reason=None, cancelled_by="user@example.com")

    def test_cancel_reason_required_whitespace_only(self):
        """Whitespace-only cancel_reason raises ValueError."""
        svc = _make_service()

        with pytest.raises(ValueError, match="cancel_reason is required"):
            svc.cancel_trip(TENANT, 1, cancel_reason="   ", cancelled_by="user@example.com")

    def test_cancel_not_blocked_by_prior_billing_state(self):
        """Cancellation proceeds regardless of any prior billing value (Req 4.8).

        The old is_billed "cannot be cancelled" guard was removed in the
        tax-log redesign; cancellation must complete even when the raw row
        still carries a stale billing flag from before the migration.
        """
        db = Mock()
        existing_row = self._existing_trip_row({"is_billed": True})
        db.execute_query = Mock(side_effect=[
            [existing_row],    # _get_raw_trip (stale is_billed=True)
            None,              # UPDATE (set is_cancelled)
            None,              # audit INSERT
        ])
        svc = _make_service(db=db)

        result = svc.cancel_trip(
            TENANT, 1,
            cancel_reason="Test reden",
            cancelled_by="user@example.com",
        )

        assert result is True
        # The cancellation UPDATE was executed (no billing-based rejection).
        update_query = db.execute_query.call_args_list[1][0][0]
        assert "is_cancelled = TRUE" in update_query

    def test_already_cancelled_trip_blocked(self):
        """Already-cancelled trips cannot be cancelled again."""
        db = Mock()
        existing_row = self._existing_trip_row({"is_cancelled": True})
        db.execute_query = Mock(return_value=[existing_row])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="is already cancelled"):
            svc.cancel_trip(
                TENANT, 1,
                cancel_reason="Test reden",
                cancelled_by="user@example.com",
            )

    def test_trip_not_found_raises_value_error(self):
        """Non-existent trip raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])  # _get_raw_trip returns nothing
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="Trip 999 not found"):
            svc.cancel_trip(
                TENANT, 999,
                cancel_reason="Test reden",
                cancelled_by="user@example.com",
            )

    def test_tenant_isolation(self):
        """_get_raw_trip query includes tenant (administration) for isolation."""
        db = Mock()
        db.execute_query = Mock(return_value=[])  # Trip not found
        svc = _make_service(db=db)

        with pytest.raises(ValueError):
            svc.cancel_trip(
                "other_tenant", 1,
                cancel_reason="Reden",
                cancelled_by="user@example.com",
            )

        query = db.execute_query.call_args[0][0]
        params = db.execute_query.call_args[0][1]
        assert "administration = %s" in query
        assert "other_tenant" in params


# ── get_trip_history ────────────────────────────────────────


class TestGetTripHistory:
    """Tests for TripService.get_trip_history — audit trail retrieval.

    Covers: Requirement 7 (correction history, audit trail query)
    """

    def test_returns_history_entries_in_chronological_order(self):
        """History entries are ordered by changed_at ASC (oldest first)."""
        db = Mock()
        db.execute_query = Mock(return_value=[
            {
                "version": 1,
                "action": "created",
                "changed_fields": None,
                "correction_reason": None,
                "changed_by": "user@example.com",
                "changed_at": datetime(2026, 7, 13, 8, 30, 0),
            },
            {
                "version": 2,
                "action": "updated",
                "changed_fields": '{"end_odometer": {"old": 45275, "new": 45280}}',
                "correction_reason": "Foutieve eindstand gecorrigeerd",
                "changed_by": "user@example.com",
                "changed_at": datetime(2026, 7, 13, 10, 0, 0),
            },
        ])
        svc = _make_service(db=db)

        result = svc.get_trip_history(TENANT, 1)

        assert len(result) == 2
        # First entry is the creation (earliest)
        assert result[0]["version"] == 1
        assert result[0]["action"] == "created"
        assert result[0]["changed_at"] == "2026-07-13T08:30:00"
        # Second entry is the update (later)
        assert result[1]["version"] == 2
        assert result[1]["action"] == "updated"
        assert result[1]["changed_at"] == "2026-07-13T10:00:00"

        # Verify query includes ORDER BY changed_at ASC
        query = db.execute_query.call_args[0][0]
        assert "ORDER BY changed_at ASC" in query

    def test_json_parsing_of_changed_fields(self):
        """changed_fields JSON string is parsed into a dict."""
        db = Mock()
        changed_json = '{"end_odometer": {"old": 45275, "new": 45280}, "trip_purpose": {"old": "Klantbezoek", "new": "Vergadering"}}'
        db.execute_query = Mock(return_value=[
            {
                "version": 2,
                "action": "updated",
                "changed_fields": changed_json,
                "correction_reason": "Correctie",
                "changed_by": "admin@example.com",
                "changed_at": datetime(2026, 7, 14, 9, 0, 0),
            },
        ])
        svc = _make_service(db=db)

        result = svc.get_trip_history(TENANT, 1)

        assert len(result) == 1
        entry = result[0]
        assert isinstance(entry["changed_fields"], dict)
        assert entry["changed_fields"]["end_odometer"] == {"old": 45275, "new": 45280}
        assert entry["changed_fields"]["trip_purpose"] == {"old": "Klantbezoek", "new": "Vergadering"}

    def test_changed_fields_already_dict(self):
        """If MySQL returns changed_fields as a dict (auto-deserialized JSON), use as-is."""
        db = Mock()
        db.execute_query = Mock(return_value=[
            {
                "version": 2,
                "action": "updated",
                "changed_fields": {"end_odometer": {"old": 45275, "new": 45280}},
                "correction_reason": "Correctie",
                "changed_by": "admin@example.com",
                "changed_at": datetime(2026, 7, 14, 9, 0, 0),
            },
        ])
        svc = _make_service(db=db)

        result = svc.get_trip_history(TENANT, 1)

        entry = result[0]
        assert isinstance(entry["changed_fields"], dict)
        assert entry["changed_fields"]["end_odometer"]["old"] == 45275

    def test_empty_history(self):
        """Trip with no audit entries returns empty list."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        result = svc.get_trip_history(TENANT, 999)

        assert result == []

    def test_tenant_isolation(self):
        """Query includes administration parameter for tenant scoping."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_trip_history("my_tenant", 42)

        query = db.execute_query.call_args[0][0]
        params = db.execute_query.call_args[0][1]
        assert "administration = %s" in query
        assert "trip_id = %s" in query
        assert params == (42, "my_tenant")

    def test_correction_reason_included_when_present(self):
        """correction_reason is included in the entry when not None."""
        db = Mock()
        db.execute_query = Mock(return_value=[
            {
                "version": 2,
                "action": "updated",
                "changed_fields": '{"start_address": {"old": "A", "new": "B"}}',
                "correction_reason": "Adres was verkeerd",
                "changed_by": "user@example.com",
                "changed_at": datetime(2026, 7, 15, 12, 0, 0),
            },
        ])
        svc = _make_service(db=db)

        result = svc.get_trip_history(TENANT, 1)

        assert result[0]["correction_reason"] == "Adres was verkeerd"

    def test_correction_reason_omitted_when_none(self):
        """correction_reason key is not included when value is None (e.g., created entry)."""
        db = Mock()
        db.execute_query = Mock(return_value=[
            {
                "version": 1,
                "action": "created",
                "changed_fields": None,
                "correction_reason": None,
                "changed_by": "user@example.com",
                "changed_at": datetime(2026, 7, 13, 8, 0, 0),
            },
        ])
        svc = _make_service(db=db)

        result = svc.get_trip_history(TENANT, 1)

        assert "correction_reason" not in result[0]

    def test_changed_fields_null_for_created_action(self):
        """For 'created' actions, changed_fields is None."""
        db = Mock()
        db.execute_query = Mock(return_value=[
            {
                "version": 1,
                "action": "created",
                "changed_fields": None,
                "correction_reason": None,
                "changed_by": "creator@example.com",
                "changed_at": datetime(2026, 7, 13, 8, 0, 0),
            },
        ])
        svc = _make_service(db=db)

        result = svc.get_trip_history(TENANT, 1)

        assert result[0]["changed_fields"] is None

    def test_cancelled_action_in_history(self):
        """Cancellation audit entries appear in history with correct action."""
        db = Mock()
        db.execute_query = Mock(return_value=[
            {
                "version": 1,
                "action": "created",
                "changed_fields": None,
                "correction_reason": None,
                "changed_by": "user@example.com",
                "changed_at": datetime(2026, 7, 13, 8, 0, 0),
            },
            {
                "version": 1,
                "action": "cancelled",
                "changed_fields": None,
                "correction_reason": "Dubbel ingevoerd",
                "changed_by": "admin@example.com",
                "changed_at": datetime(2026, 7, 13, 14, 0, 0),
            },
        ])
        svc = _make_service(db=db)

        result = svc.get_trip_history(TENANT, 1)

        assert len(result) == 2
        assert result[0]["action"] == "created"
        assert result[1]["action"] == "cancelled"
        assert result[1]["correction_reason"] == "Dubbel ingevoerd"


# ── get_unbilled_trips (REMOVED — task 9.1) ─────────────────
#
# TestGetUnbilledTrips was deleted: the redesign dropped
# ``TripService.get_unbilled_trips`` entirely — there is no callable
# unbilled-trips service path (Req 4.4). The absence is pinned by
# TestQueryExamplesTaxLog.test_get_unbilled_trips_not_callable below.


# ── mark_as_billed ──────────────────────────────────────────


class TestMarkAsBilled:
    """Tests for TripService.mark_as_billed (Requirement 6).

    Behavior:
    - Accept a list of trip IDs and an invoice_id
    - UPDATE trips: set is_billed=TRUE and invoice_id
    - Only update trips belonging to tenant, not already billed, not cancelled
    - Return the number of trips actually marked as billed
    - Already-billed trips are silently skipped (no error)
    """

    def test_happy_path_marks_trips(self):
        """Marks multiple trips as billed and returns count of affected rows."""
        db = Mock()
        db.execute_query = Mock(return_value=3)  # 3 rows updated
        svc = _make_service(db=db)

        result = svc.mark_as_billed(TENANT, [10, 12, 15], invoice_id=42)

        assert result == 3
        # Verify the query was called
        call_args = db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        # Check UPDATE structure
        assert "UPDATE zzp_trips" in query
        assert "SET is_billed = TRUE" in query
        assert "invoice_id = %s" in query
        assert "administration = %s" in query
        assert "IN" in query
        assert "is_billed = FALSE" in query
        assert "is_cancelled = FALSE" in query
        # Check params: invoice_id, tenant, then trip_ids
        assert params[0] == 42       # invoice_id
        assert params[1] == TENANT   # administration
        assert params[2] == 10       # trip_id 1
        assert params[3] == 12       # trip_id 2
        assert params[4] == 15       # trip_id 3
        # Verify commit=True
        assert call_args[1]["fetch"] is False
        assert call_args[1]["commit"] is True

    def test_returns_count_of_affected_rows(self):
        """Return value matches the number of rows actually updated."""
        db = Mock()
        db.execute_query = Mock(return_value=2)  # Only 2 of 3 eligible
        svc = _make_service(db=db)

        result = svc.mark_as_billed(TENANT, [10, 12, 15], invoice_id=42)

        assert result == 2

    def test_already_billed_trips_skipped(self):
        """Already-billed trips are not updated (WHERE is_billed = FALSE)."""
        db = Mock()
        # Simulate: 3 IDs passed but only 1 was eligible (2 already billed)
        db.execute_query = Mock(return_value=1)
        svc = _make_service(db=db)

        result = svc.mark_as_billed(TENANT, [10, 12, 15], invoice_id=42)

        assert result == 1
        # Verify the WHERE clause includes is_billed = FALSE filter
        query = db.execute_query.call_args[0][0]
        assert "is_billed = FALSE" in query

    def test_cancelled_trips_skipped(self):
        """Cancelled trips are not updated (WHERE is_cancelled = FALSE)."""
        db = Mock()
        # Simulate: all trips are cancelled, 0 affected
        db.execute_query = Mock(return_value=0)
        svc = _make_service(db=db)

        result = svc.mark_as_billed(TENANT, [10, 12, 15], invoice_id=42)

        assert result == 0
        # Verify the WHERE clause includes is_cancelled = FALSE filter
        query = db.execute_query.call_args[0][0]
        assert "is_cancelled = FALSE" in query

    def test_tenant_isolation(self):
        """Only trips belonging to the tenant are updated."""
        db = Mock()
        db.execute_query = Mock(return_value=0)
        svc = _make_service(db=db)

        svc.mark_as_billed("other_tenant", [10, 12], invoice_id=42)

        # Verify tenant is in the params
        params = db.execute_query.call_args[0][1]
        assert params[1] == "other_tenant"
        # Verify WHERE administration = %s is in query
        query = db.execute_query.call_args[0][0]
        assert "administration = %s" in query

    def test_empty_trip_ids_returns_zero(self):
        """Empty trip_ids list returns 0 without hitting the database."""
        db = Mock()
        svc = _make_service(db=db)

        result = svc.mark_as_billed(TENANT, [], invoice_id=42)

        assert result == 0
        db.execute_query.assert_not_called()

    def test_single_trip_id(self):
        """Works correctly with a single trip ID."""
        db = Mock()
        db.execute_query = Mock(return_value=1)
        svc = _make_service(db=db)

        result = svc.mark_as_billed(TENANT, [10], invoice_id=99)

        assert result == 1
        params = db.execute_query.call_args[0][1]
        assert params == (99, TENANT, 10)

    def test_parameterized_query_no_sql_injection(self):
        """Query uses %s placeholders for IN clause (no string interpolation of IDs)."""
        db = Mock()
        db.execute_query = Mock(return_value=2)
        svc = _make_service(db=db)

        svc.mark_as_billed(TENANT, [10, 12], invoice_id=42)

        query = db.execute_query.call_args[0][0]
        # IDs should be %s placeholders, not literal numbers
        assert "10" not in query
        assert "12" not in query
        assert "42" not in query
        # Should have multiple %s placeholders for the IN clause
        assert "%s, %s" in query or "IN (%s, %s)" in query

    def test_returns_zero_when_db_returns_none(self):
        """Handles edge case where execute_query returns None."""
        db = Mock()
        db.execute_query = Mock(return_value=None)
        svc = _make_service(db=db)

        result = svc.mark_as_billed(TENANT, [10], invoice_id=42)

        assert result == 0

# ════════════════════════════════════════════════════════════
# Property-based + example tests — CRUD paths (task 8.2)
#
# Feature: rittenregistratie-tax-log-redesign
#
# These exercise the post-redesign create / gap-fill / update / cancel paths
# against a stateful fake zzp_trips store that mirrors the real SQL the
# TripCrudService + TripQueryService issue. The store deliberately refuses to
# accept any billing/contact-link column (contact_id, is_billable, is_billed,
# invoice_id) on INSERT and never returns one on read, so the billing-free
# invariant is verified structurally rather than by assertion alone.
#
# NOTE (coordination): query/list/get property tests are owned by task 9.2 and
# are intentionally NOT added here.
# ════════════════════════════════════════════════════════════


# Columns the redesigned INSERT writes, in order (task 8.1). distance_km is a
# generated column (end - start) and is NOT part of the INSERT.
_INSERT_COLUMNS = [
    "administration", "vehicle_id", "trip_date", "start_time", "end_time",
    "start_address", "end_address", "start_odometer", "end_odometer",
    "trip_category", "trip_purpose", "route_description",
    "client_name", "project_name", "notes", "is_gap_fill", "created_by",
]

# Columns that must never be persisted on, or returned from, a trip (Req 4.5, 4.6).
_FORBIDDEN_BILLING_COLUMNS = (
    "contact_id", "is_billable", "is_billed", "invoice_id",
)

VALID_CATEGORIES = ("Zakelijk", "Privé", "Woon-werk")


class _FakeTripStore:
    """A stateful fake DatabaseManager for the zzp_trips CRUD/read paths.

    Simulates just enough of the schema to drive create/gap-fill/update/cancel
    and the follow-up get_trip read. Enforces the billing-free invariant: the
    INSERT statement must not reference any forbidden billing column, and reads
    never surface one.
    """

    def __init__(self, vehicle_start_odometer=0, prior_end_odometer=None):
        self.rows = {}          # trip_id -> stored row dict
        self._next_id = 1
        self.vehicle_start_odometer = vehicle_start_odometer
        # Most-recent prior non-cancelled trip end_odometer for the vehicle
        # (None → fall back to the vehicle's start_odometer in detect_gap).
        self.prior_end_odometer = prior_end_odometer
        self.inserted_columns = None   # columns parsed from the last trip INSERT

    # -- helper ---------------------------------------------------------
    def _store_from_insert(self, params):
        row = dict(zip(_INSERT_COLUMNS, params))
        trip_id = self._next_id
        self._next_id += 1
        row["id"] = trip_id
        # Generated column semantics (Req 1.2): distance = end - start.
        row["distance_km"] = int(row["end_odometer"]) - int(row["start_odometer"])
        row.setdefault("is_cancelled", False)
        row.setdefault("cancel_reason", None)
        row.setdefault("version", 1)
        row.setdefault("created_at", datetime(2026, 7, 13, 8, 30, 0))
        row.setdefault("updated_at", datetime(2026, 7, 13, 8, 30, 0))
        self.rows[trip_id] = row
        return trip_id

    # -- DatabaseManager surface ---------------------------------------
    def execute_query(self, query, params=None, fetch=True, commit=False, **kwargs):
        params = params or ()
        q = " ".join(query.split())  # collapse whitespace
        qu = q.upper()

        # Vehicle existence check (_validate_vehicle)
        if "FROM ZZP_VEHICLES" in qu and "SELECT ID" in qu:
            return [{"id": params[0]}]

        # detect_gap: previous end_odometer for the vehicle
        if "SELECT END_ODOMETER FROM ZZP_TRIPS" in qu:
            if self.prior_end_odometer is None:
                return []
            return [{"end_odometer": self.prior_end_odometer}]

        # detect_gap fallback: vehicle start_odometer
        if "SELECT START_ODOMETER FROM ZZP_VEHICLES" in qu:
            return [{"start_odometer": self.vehicle_start_odometer}]

        # Trip INSERT
        if qu.startswith("INSERT INTO ZZP_TRIPS"):
            # Billing-free invariant: the INSERT must not mention any
            # forbidden billing/contact column (Req 4.6).
            for col in _FORBIDDEN_BILLING_COLUMNS:
                assert col not in q, f"INSERT must not write billing column {col!r}"
            # Parse the column list for structural assertions.
            col_blob = q[q.index("(") + 1:q.index(")")]
            self.inserted_columns = [c.strip() for c in col_blob.split(",")]
            return self._store_from_insert(params)

        # Audit INSERT
        if qu.startswith("INSERT INTO ZZP_TRIP_AUDIT"):
            return None

        # Route-preset learning (SELECT then UPSERT) — tolerate as no-op.
        if "ZZP_ROUTE_PRESETS" in qu:
            if qu.startswith("SELECT"):
                return []
            return None

        # _get_raw_trip: SELECT * FROM zzp_trips WHERE id = %s AND administration
        if qu.startswith("SELECT * FROM ZZP_TRIPS"):
            trip_id = params[0]
            row = self.rows.get(trip_id)
            return [dict(row)] if row else []

        # get_trip: SELECT <cols> FROM zzp_trips WHERE id = %s AND administration
        if qu.startswith("SELECT ID, ADMINISTRATION") and "FROM ZZP_TRIPS" in qu:
            trip_id = params[0]
            row = self.rows.get(trip_id)
            if not row:
                return []
            # Reads never surface a billing column (Req 4.5).
            projected = {k: v for k, v in row.items()
                         if k not in _FORBIDDEN_BILLING_COLUMNS}
            return [projected]

        # UPDATE zzp_trips (update_trip / cancel_trip)
        if qu.startswith("UPDATE ZZP_TRIPS"):
            # The WHERE clause binds (..., trip_id, tenant); id is second-to-last.
            trip_id = params[-2]
            row = self.rows.get(trip_id)
            if row is None:
                return 0
            if "IS_CANCELLED = TRUE" in qu:
                row["is_cancelled"] = True
                row["cancel_reason"] = params[0]
            else:
                # Field update: SET col = %s, ..., version = %s WHERE id, admin
                set_blob = q[q.upper().index("SET") + 3:q.upper().index("WHERE")]
                assignments = [a.strip() for a in set_blob.split(",")]
                values = list(params[: len(assignments)])
                for assignment, value in zip(assignments, values):
                    col = assignment.split("=")[0].strip()
                    row[col] = value
            return 1

        return []


def _crud_service(store, parameter_service=None):
    if parameter_service is None:
        parameter_service = Mock()
        parameter_service.get_param = Mock(return_value=None)
    return TripService(db=store, parameter_service=parameter_service)


# Hypothesis strategies -------------------------------------------------

_odometer = st.integers(min_value=0, max_value=9_999_999)
_address = st.text(min_size=1, max_size=120).map(lambda s: s.strip() or "x")
_client_name = st.one_of(
    st.none(),
    st.text(max_size=255),
)


@st.composite
def _valid_trip_strategy(draw):
    """A valid trip payload: end strictly greater than start, valid category."""
    start = draw(st.integers(min_value=0, max_value=9_999_990))
    end = draw(st.integers(min_value=start + 1, max_value=9_999_999))
    return {
        "vehicle_id": 1,
        "trip_date": "2026-07-13",
        "start_address": draw(_address),
        "end_address": draw(_address),
        "start_odometer": start,
        "end_odometer": end,
        "trip_category": draw(st.sampled_from(VALID_CATEGORIES)),
        "trip_purpose": "Klantbezoek",
        "project_name": draw(st.one_of(st.none(), st.text(max_size=80))),
        "notes": draw(st.one_of(st.none(), st.text(max_size=200))),
        "client_name": draw(_client_name),
    }


class TestCrudPropertiesTaxLog:
    """Property-based CRUD tests for the tax-log redesign (task 8.2)."""

    # Feature: rittenregistratie-tax-log-redesign, Property 1: Trip persistence and generated distance
    @settings(max_examples=100, deadline=None)
    @given(data=_valid_trip_strategy())
    def test_property_trip_persistence_and_generated_distance(self, data):
        """A valid trip persists its fields; distance_km == end - start.

        Validates: Requirements 1.1, 1.2, 1.7
        """
        store = _FakeTripStore(prior_end_odometer=data["start_odometer"])
        svc = _crud_service(store)
        with patch.object(TripService, "validate_fields"):
            result = svc.create_trip(TENANT, data, "user@example.com")

        assert result["success"] is True
        trip = result["data"]
        assert trip["trip_date"] == "2026-07-13"
        assert trip["start_address"] == data["start_address"].strip()
        assert trip["end_address"] == data["end_address"].strip()
        assert trip["start_odometer"] == data["start_odometer"]
        assert trip["end_odometer"] == data["end_odometer"]
        assert trip["trip_category"] == data["trip_category"]
        assert trip["trip_purpose"] == data["trip_purpose"]
        assert trip["project_name"] == data["project_name"]
        assert trip["notes"] == data["notes"]
        # Generated distance column (Req 1.2).
        assert trip["distance_km"] == data["end_odometer"] - data["start_odometer"]

    # Feature: rittenregistratie-tax-log-redesign, Property 2: End-before-start odometer is rejected
    @settings(max_examples=100, deadline=None)
    @given(
        start=st.integers(min_value=1, max_value=9_999_999),
        delta=st.integers(min_value=0, max_value=1_000),
    )
    def test_property_end_before_start_odometer_rejected(self, start, delta):
        """end <= start is rejected with an odometer error, nothing persisted.

        Validates: Requirement 1.3
        """
        end = max(0, start - delta)  # end <= start (equal when delta == 0)
        data = {
            "vehicle_id": 1,
            "trip_date": "2026-07-13",
            "start_address": "A",
            "end_address": "B",
            "start_odometer": start,
            "end_odometer": end,
            "trip_category": "Zakelijk",
            "trip_purpose": "Klantbezoek",
        }
        store = _FakeTripStore(prior_end_odometer=start)
        svc = _crud_service(store)
        with patch.object(TripService, "validate_fields"):
            with pytest.raises(ValueError, match="end_odometer must be greater"):
                svc.create_trip(TENANT, data, "user@example.com")
        # Nothing persisted; input values are unchanged (retained for the caller).
        assert store.rows == {}
        assert data["start_odometer"] == start
        assert data["end_odometer"] == end

    # Feature: rittenregistratie-tax-log-redesign, Property 3: Invalid category is rejected
    @settings(max_examples=100, deadline=None)
    @given(
        category=st.text(min_size=1, max_size=30).filter(
            lambda c: c not in VALID_CATEGORIES
        ),
    )
    def test_property_invalid_category_rejected(self, category):
        """A category outside the fixed set is rejected, nothing persisted.

        Validates: Requirement 1.5
        """
        data = {
            "vehicle_id": 1,
            "trip_date": "2026-07-13",
            "start_address": "A",
            "end_address": "B",
            "start_odometer": 100,
            "end_odometer": 200,
            "trip_category": category,
            "trip_purpose": "Klantbezoek",
        }
        store = _FakeTripStore(prior_end_odometer=100)
        svc = _crud_service(store)
        with patch.object(TripService, "validate_fields"):
            with pytest.raises(ValueError, match="Invalid trip_category"):
                svc.create_trip(TENANT, data, "user@example.com")
        assert store.rows == {}

    # Feature: rittenregistratie-tax-log-redesign, Property 8: Billing-free invariant (CRUD side)
    @settings(max_examples=100, deadline=None)
    @given(data=_valid_trip_strategy(), gap_fill=st.booleans())
    def test_property_billing_free_invariant(self, data, gap_fill):
        """Created/gap-filled records never carry a billing/contact field.

        Validates: Requirements 4.5, 4.6
        """
        store = _FakeTripStore(prior_end_odometer=data["start_odometer"])
        svc = _crud_service(store)
        with patch.object(TripService, "validate_fields"):
            if gap_fill:
                result = svc.create_gap_fill(TENANT, data, "user@example.com")
            else:
                result = svc.create_trip(TENANT, data, "user@example.com")

        trip = result["data"]
        # The INSERT wrote no billing/contact column (enforced in the store too).
        assert store.inserted_columns is not None
        for col in _FORBIDDEN_BILLING_COLUMNS:
            assert col not in store.inserted_columns
            assert col not in trip
        # No nested contact object either (Req 4.5).
        assert "contact" not in trip

    # Feature: rittenregistratie-tax-log-redesign, Property 9: Mutations never blocked by billing state
    @settings(max_examples=100, deadline=None)
    @given(
        data=_valid_trip_strategy(),
        stale_is_billed=st.booleans(),
        new_notes=st.text(min_size=1, max_size=60),
    )
    def test_property_mutations_not_blocked_by_billing(
        self, data, stale_is_billed, new_notes
    ):
        """Update + cancel complete regardless of any prior billing value.

        Validates: Requirements 4.7, 4.8
        """
        store = _FakeTripStore(prior_end_odometer=data["start_odometer"])
        svc = _crud_service(store)
        with patch.object(TripService, "validate_fields"):
            created = svc.create_trip(TENANT, data, "user@example.com")
        trip_id = created["data"]["id"]

        # Simulate a stale pre-migration billing flag lingering on the raw row.
        store.rows[trip_id]["is_billed"] = stale_is_billed

        # Update with a valid payload — must persist, no billing-based rejection.
        if store.rows[trip_id].get("notes") == new_notes:
            new_notes = new_notes + "x"
        with patch.object(TripService, "validate_fields"):
            updated = svc.update_trip(
                TENANT, trip_id, {"notes": new_notes},
                correction_reason="Correctie", updated_by="user@example.com",
            )
        assert updated["notes"] == new_notes
        assert store.rows[trip_id]["notes"] == new_notes

        # Cancel — must complete regardless of the stale billing flag.
        ok = svc.cancel_trip(
            TENANT, trip_id, cancel_reason="Afgerond",
            cancelled_by="user@example.com",
        )
        assert ok is True
        assert store.rows[trip_id]["is_cancelled"] is True

    # Feature: rittenregistratie-tax-log-redesign, Property 17: Gap-detection flag reflects odometer continuity
    @settings(max_examples=100, deadline=None)
    @given(
        prior_end=st.integers(min_value=1, max_value=9_000_000),
        gap=st.integers(min_value=1, max_value=5_000),
        has_gap=st.booleans(),
    )
    def test_property_gap_detection_reflects_continuity(
        self, prior_end, gap, has_gap
    ):
        """Gap offered iff start_odometer != prior trip's end_odometer.

        Validates: Requirement 10.2
        """
        start = prior_end + gap if has_gap else prior_end
        data = {
            "vehicle_id": 1,
            "trip_date": "2026-07-13",
            "start_address": "A",
            "end_address": "B",
            "start_odometer": start,
            "end_odometer": start + 10,
            "trip_category": "Zakelijk",
            "trip_purpose": "Klantbezoek",
        }
        store = _FakeTripStore(prior_end_odometer=prior_end)
        svc = _crud_service(store)
        with patch.object(TripService, "validate_fields"):
            result = svc.create_trip(TENANT, data, "user@example.com")

        if has_gap:
            # Continuity broken → a gap warning + gap_fill_offer is present.
            assert "gap_fill_offer" in result
            gap_warnings = [
                w for w in result.get("warnings", [])
                if w["type"] == "odometer_gap"
            ]
            assert len(gap_warnings) == 1
            assert gap_warnings[0]["gap_km"] == gap
        else:
            # Odometers continuous → no gap offer.
            assert "gap_fill_offer" not in result
            gap_warnings = [
                w for w in result.get("warnings", [])
                if w["type"] == "odometer_gap"
            ]
            assert gap_warnings == []


class TestCrudExamplesTaxLog:
    """Example-based CRUD tests for the tax-log redesign (task 8.2)."""

    @pytest.mark.parametrize("category", ["Zakelijk", "Privé", "Woon-werk"])
    def test_three_categories_accepted(self, category):
        """Each of the three fixed categories is accepted on create (Req 1.4)."""
        data = {
            "vehicle_id": 1,
            "trip_date": "2026-07-13",
            "start_address": "Amsterdam",
            "end_address": "Utrecht",
            "start_odometer": 1000,
            "end_odometer": 1045,
            "trip_category": category,
            "trip_purpose": "Klantbezoek",
        }
        store = _FakeTripStore(prior_end_odometer=1000)
        svc = _crud_service(store)
        with patch.object(TripService, "validate_fields"):
            result = svc.create_trip(TENANT, data, "user@example.com")

        assert result["success"] is True
        assert result["data"]["trip_category"] == category

    def test_empty_client_name_persists_as_null(self):
        """An empty/omitted Klant note persists as null on create (Req 2.1)."""
        data = {
            "vehicle_id": 1,
            "trip_date": "2026-07-13",
            "start_address": "Amsterdam",
            "end_address": "Utrecht",
            "start_odometer": 2000,
            "end_odometer": 2050,
            "trip_category": "Zakelijk",
            "trip_purpose": "Klantbezoek",
            # No client_name key provided at all.
        }
        store = _FakeTripStore(prior_end_odometer=2000)
        svc = _crud_service(store)
        with patch.object(TripService, "validate_fields"):
            result = svc.create_trip(TENANT, data, "user@example.com")

        trip_id = result["data"]["id"]
        # The persisted client_name is null (None), not an empty string.
        assert store.rows[trip_id]["client_name"] is None
        assert result["data"]["client_name"] is None


# ════════════════════════════════════════════════════════════
# Property-based + example tests — QUERY paths (task 9.2)
#
# Feature: rittenregistratie-tax-log-redesign
#
# These exercise the post-redesign get_trip / list_trips read paths against a
# recording fake zzp_trips store. The store mirrors the real SQL the
# TripQueryService issues: a single tenant-scoped SELECT per read, no contacts
# JOIN, and tenant filtering by ``administration``. Rows carry a free-text
# ``client_name`` and never a billing/contact-link column, so the billing-free
# read invariant (Property 8) is verified structurally. Query SQL is captured
# so tenant-isolation (Property 18) and the ignored billing filters (Property 7)
# can be asserted against the exact statements and bound params.
#
# NOTE (coordination): the CRUD create/gap-fill/update/cancel property tests
# are owned by task 8.2 (TestCrudPropertiesTaxLog) and are not duplicated here.
# ════════════════════════════════════════════════════════════


def _query_trip_row(trip_id, administration, client_name=None, **overrides):
    """A read-path trip row carrying only post-redesign (non-billing) columns.

    Mirrors the ``_TRIP_COLUMNS`` the redesigned SELECT projects: includes the
    free-text ``client_name`` and excludes every dropped billing/contact-link
    column (contact_id, is_billable, is_billed, invoice_id) — Req 4.5.
    """
    row = {
        "id": trip_id,
        "administration": administration,
        "vehicle_id": 1,
        "trip_date": date(2026, 7, 13),
        "start_time": "08:30",
        "end_time": "09:15",
        "start_address": "Keizersgracht 100, Amsterdam",
        "end_address": "Stationsplein 1, Utrecht",
        "start_odometer": 45230,
        "end_odometer": 45275,
        "distance_km": 45,
        "trip_category": "Zakelijk",
        "trip_purpose": "Klantbezoek",
        "route_description": None,
        "project_name": "Project Alpha",
        "notes": None,
        "client_name": client_name,
        "is_gap_fill": 0,
        "is_cancelled": 0,
        "cancel_reason": None,
        "version": 1,
        "created_at": datetime(2026, 7, 13, 8, 30, 0),
        "updated_at": datetime(2026, 7, 13, 8, 30, 0),
        "created_by": "user@example.com",
    }
    row.update(overrides)
    return row


class _QueryRecordingStore:
    """A recording fake DatabaseManager for the zzp_trips read paths.

    Holds a fixed set of trip rows keyed by id. ``execute_query`` records every
    (query, params) pair, then answers COUNT / data SELECTs for ``list_trips``
    and the single-row SELECT for ``get_trip``. Rows are returned only when the
    bound tenant matches the row's ``administration`` (the tenant is always the
    last positional param on these read queries), modelling the real
    ``WHERE administration = %s`` scoping. Reads never surface a billing column.
    """

    def __init__(self, rows):
        # rows: list of row dicts (each carrying an ``administration``)
        self._rows = [dict(r) for r in rows]
        self.calls = []  # list of (query, params)

    def execute_query(self, query, params=None, fetch=True, commit=False, **kwargs):
        params = tuple(params or ())
        self.calls.append((query, params))
        qu = " ".join(query.split()).upper()

        # Every read path must be tenant-scoped (Req 10.5).
        assert "ADMINISTRATION = %S" in qu, (
            f"read query missing tenant scope: {query!r}"
        )

        if qu.startswith("SELECT COUNT(*)"):
            matched = self._match(query, params)
            return [{"total": len(matched)}]

        # Data SELECT (list) or single-row SELECT (get_trip).
        matched = self._match(query, params)
        # Reads never surface a billing/contact column (Req 4.5).
        return [
            {k: v for k, v in r.items() if k not in _FORBIDDEN_BILLING_COLUMNS}
            for r in matched
        ]

    def _match(self, query, params):
        """Return the stored rows visible to the bound tenant for this query.

        The redesigned read queries bind the tenant to the first positional
        param (``WHERE id = %s AND administration = %s`` has the tenant second;
        ``list_trips`` binds it first). We therefore match any row whose
        ``administration`` appears anywhere in the bound params — a row is only
        ever returned to a query that bound its tenant, so an unbound/foreign
        tenant yields nothing (Req 10.6).
        """
        qu = " ".join(query.split()).upper()
        visible = [r for r in self._rows if r["administration"] in params]

        # get_trip binds a specific id as well.
        if "WHERE ID = %S" in qu:
            # id is the first bound param on the get_trip query.
            trip_id = params[0]
            visible = [r for r in visible if r["id"] == trip_id]
        return visible


_query_client_name = st.one_of(st.none(), st.text(max_size=255))


@st.composite
def _query_rows_strategy(draw, administration=TENANT, min_rows=0, max_rows=6):
    """A set of distinct read-path trip rows for one tenant."""
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    return [
        _query_trip_row(
            trip_id=i + 1,
            administration=administration,
            client_name=draw(_query_client_name),
        )
        for i in range(n)
    ]


class TestQueryPropertiesTaxLog:
    """Property-based query-path tests for the tax-log redesign (task 9.2)."""

    # Feature: rittenregistratie-tax-log-redesign, Property 7: Billing filters ignored (metamorphic)
    @settings(max_examples=100, deadline=None)
    @given(
        rows=_query_rows_strategy(),
        is_billed=st.booleans(),
        # Kept well clear of the default pagination params (limit=50, offset=0)
        # so a collision can't make the "value never reached params" check flaky.
        contact_id=st.integers(min_value=1000, max_value=9999),
    )
    def test_property_billing_filters_ignored(self, rows, is_billed, contact_id):
        """list_trips with is_billed/contact_id filters == without them.

        Metamorphic: adding the removed billing/contact filters to an otherwise
        identical request must not change the result set and must not error
        (Req 4.3).
        """
        base_store = _QueryRecordingStore(rows)
        filtered_store = _QueryRecordingStore(rows)
        base = _crud_service(base_store)
        filtered = _crud_service(filtered_store)

        baseline = base.list_trips(TENANT)
        with_billing = filtered.list_trips(
            TENANT, filters={"is_billed": is_billed, "contact_id": contact_id}
        )

        # Same set of trip ids and same total — the filters were ignored.
        assert with_billing["total"] == baseline["total"]
        assert (
            [t["id"] for t in with_billing["data"]]
            == [t["id"] for t in baseline["data"]]
        )
        # The ignored filter values never reach the DB params.
        for query, params in filtered_store.calls:
            assert "contact_id" not in query
            assert "is_billed" not in query
            assert contact_id not in params

    # Feature: rittenregistratie-tax-log-redesign, Property 8: Billing-free invariant (query side)
    @settings(max_examples=100, deadline=None)
    @given(rows=_query_rows_strategy(min_rows=1))
    def test_property_billing_free_invariant_query_side(self, rows):
        """Retrieved/listed trips carry no billing/contact field.

        Validates: Requirements 4.5, 4.6
        """
        svc = _crud_service(_QueryRecordingStore(rows))

        listed = svc.list_trips(TENANT)["data"]
        assert len(listed) == len(rows)
        for trip in listed:
            for col in _FORBIDDEN_BILLING_COLUMNS:
                assert col not in trip
            assert "contact" not in trip
            # The free-text client note is carried through directly.
            assert "client_name" in trip

        # get_trip for the first row surfaces no billing field either.
        single = svc.get_trip(TENANT, rows[0]["id"])
        assert single is not None
        for col in _FORBIDDEN_BILLING_COLUMNS:
            assert col not in single
        assert "contact" not in single
        assert "client_name" in single

    # Feature: rittenregistratie-tax-log-redesign, Property 18: Tenant isolation on every trip query
    @settings(max_examples=100, deadline=None)
    @given(
        rows=_query_rows_strategy(min_rows=1),
        tenant=st.text(min_size=1, max_size=40).map(lambda s: s.strip() or "t"),
    )
    def test_property_tenant_isolation_on_every_query(self, rows, tenant):
        """Every get/list query binds WHERE administration = %s to the tenant.

        Validates: Requirement 10.5
        """
        store = _QueryRecordingStore(rows)
        svc = _crud_service(store)

        svc.list_trips(tenant)
        svc.get_trip(tenant, rows[0]["id"])

        assert store.calls, "no query was issued"
        for query, params in store.calls:
            q = " ".join(query.split())
            assert "administration = %s" in q
            # The requesting tenant is bound as a positional param.
            assert tenant in params

    # Feature: rittenregistratie-tax-log-redesign, Property 19: Missing tenant yields no rows
    @settings(max_examples=100, deadline=None)
    @given(rows=_query_rows_strategy(min_rows=1))
    def test_property_missing_tenant_yields_no_rows(self, rows):
        """A query bound to a tenant that owns no rows returns nothing.

        The rows all belong to ``TENANT``; a query bound to a different (or
        empty) tenant matches none of them, so the read is scoped out and
        returns no trip rows (Req 10.6).
        """
        store = _QueryRecordingStore(rows)
        svc = _crud_service(store)

        other = "other_tenant_with_no_trips"
        listed = svc.list_trips(other)
        assert listed["total"] == 0
        assert listed["data"] == []
        assert svc.get_trip(other, rows[0]["id"]) is None

        # An empty-string tenant likewise matches nothing (no silent default).
        assert svc.list_trips("")["data"] == []


class TestQueryExamplesTaxLog:
    """Example-based query-path tests for the tax-log redesign (task 9.2)."""

    def test_get_unbilled_trips_not_callable(self):
        """The unbilled-trips service path no longer exists (Req 4.4)."""
        svc = _make_service(db=Mock())
        assert not hasattr(svc, "get_unbilled_trips")
        with pytest.raises(AttributeError):
            svc.get_unbilled_trips(TENANT, contact_id=5)

    def test_enrich_with_contacts_removed(self):
        """The contacts-enrichment service path no longer exists (Req 4.5)."""
        svc = _make_service(db=Mock())
        assert not hasattr(svc, "enrich_with_contacts")
