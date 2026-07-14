"""Unit tests for TripService — CRUD, filtering, enrichment, summary, bijtelling.

Covers: Requirements 2, 5, 6 (Trip CRUD, bijtelling tracking, summaries)
Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.2
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date, datetime
from decimal import Decimal

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
        "contact_id": 5,
        "project_name": "Project Alpha",
        "notes": None,
        "is_billable": 1,
        "is_billed": 0,
        "invoice_id": None,
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
        "contact_id": 5,
        "project_name": "Project Alpha",
        "is_billable": True,
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
        assert result["data"]["is_billable"] is True
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
        """Getting an existing trip returns formatted dict with contact."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [_trip_row()],       # SELECT trip
            [{"id": 5, "company_name": "Acme BV"}],  # enrich contacts
        ])
        svc = _make_service(db=db)

        result = svc.get_trip(TENANT, 1)

        assert result is not None
        assert result["id"] == 1
        assert result["trip_date"] == "2026-07-13"
        assert result["contact"] == {"id": 5, "company_name": "Acme BV"}

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

    def test_filter_by_contact_id(self):
        """Filter by contact_id adds WHERE clause."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 0}],
            [],
        ])
        svc = _make_service(db=db)

        svc.list_trips(TENANT, filters={"contact_id": 5})

        count_query = db.execute_query.call_args_list[0][0][0]
        assert "contact_id = %s" in count_query

    def test_filter_by_is_billed(self):
        """Filter by is_billed adds WHERE clause."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [{"total": 0}],
            [],
        ])
        svc = _make_service(db=db)

        svc.list_trips(TENANT, filters={"is_billed": True})

        count_query = db.execute_query.call_args_list[0][0][0]
        assert "is_billed = %s" in count_query

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


# ── enrich_with_contacts ────────────────────────────────────


class TestEnrichWithContacts:
    """Tests for TripService.enrich_with_contacts."""

    def test_trips_with_contacts_enriched(self):
        """Trips with contact_id get nested contact object."""
        db = Mock()
        db.execute_query = Mock(return_value=[
            {"id": 5, "company_name": "Acme BV"},
            {"id": 8, "company_name": "Widget Corp"},
        ])
        svc = _make_service(db=db)

        trips = [
            {"id": 1, "contact_id": 5},
            {"id": 2, "contact_id": 8},
        ]
        result = svc.enrich_with_contacts(TENANT, trips)

        assert result[0]["contact"] == {"id": 5, "company_name": "Acme BV"}
        assert result[1]["contact"] == {"id": 8, "company_name": "Widget Corp"}

    def test_trips_without_contacts_get_none(self):
        """Trips without contact_id get contact=None."""
        db = Mock()
        svc = _make_service(db=db)

        trips = [{"id": 1, "contact_id": None}]
        result = svc.enrich_with_contacts(TENANT, trips)

        assert result[0]["contact"] is None
        # No DB call needed when no contact_ids
        db.execute_query.assert_not_called()

    def test_orphaned_fk_returns_none(self):
        """Trip with contact_id pointing to non-existent contact gets None."""
        db = Mock()
        db.execute_query = Mock(return_value=[])  # Contact not found
        svc = _make_service(db=db)

        trips = [{"id": 1, "contact_id": 999}]
        result = svc.enrich_with_contacts(TENANT, trips)

        assert result[0]["contact"] is None

    def test_batch_query_optimization(self):
        """Multiple trips with different contacts use a single batch query."""
        db = Mock()
        db.execute_query = Mock(return_value=[
            {"id": 5, "company_name": "Acme BV"},
            {"id": 8, "company_name": "Widget Corp"},
        ])
        svc = _make_service(db=db)

        trips = [
            {"id": 1, "contact_id": 5},
            {"id": 2, "contact_id": 8},
            {"id": 3, "contact_id": 5},  # duplicate contact_id
        ]
        svc.enrich_with_contacts(TENANT, trips)

        # Only ONE query should have been made (batch)
        assert db.execute_query.call_count == 1
        # Query should use IN clause with deduplicated IDs
        query = db.execute_query.call_args[0][0]
        assert "IN" in query


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

        # Verify INSERT params have is_gap_fill=True (position 16)
        insert_call = db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        assert insert_params[16] is True

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

    def _gap_row(self, id=1, vehicle_id=1, contact_id=None):
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
            "contact_id": contact_id,
        })

    def test_returns_unresolved_gaps(self):
        """Returns gap-fill trips that still have purpose 'Niet geregistreerd'."""
        db = Mock()
        gap_rows = [self._gap_row(id=1), self._gap_row(id=2)]
        db.execute_query = Mock(side_effect=[
            gap_rows,  # SELECT unresolved gaps
            [],        # enrich_with_contacts (no contacts)
        ])
        svc = _make_service(db=db)

        result = svc.get_unresolved_gaps(TENANT)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[0]["is_gap_fill"] is True
        assert result[0]["trip_purpose"] == "Niet geregistreerd"

    def test_filter_by_vehicle_id(self):
        """When vehicle_id is provided, query filters by that vehicle."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [self._gap_row(id=5, vehicle_id=2)],  # SELECT
            [],  # enrich_with_contacts
        ])
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

    def test_enriches_with_contacts(self):
        """Results are enriched with contact information."""
        db = Mock()
        gap_row = self._gap_row(id=1, contact_id=5)
        db.execute_query = Mock(side_effect=[
            [gap_row],  # SELECT unresolved gaps
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        result = svc.get_unresolved_gaps(TENANT)

        assert len(result) == 1
        assert result[0]["contact"] == {"id": 5, "company_name": "Acme BV"}


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
            "contact_id": 5,
            "project_name": "Project Alpha",
            "notes": None,
            "is_billable": True,
            "is_billed": False,
            "invoice_id": None,
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

    def test_billed_trip_cannot_be_edited(self):
        """Billed trips (is_billed=True) cannot be updated."""
        db = Mock()
        existing_row = self._existing_trip_row({"is_billed": True})
        db.execute_query = Mock(return_value=[existing_row])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="is billed and cannot be edited"):
            svc.update_trip(
                TENANT, 1, {"notes": "test"},
                correction_reason="Correction", updated_by="user@example.com",
            )

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
            "contact_id": 5,
            "project_name": "Project Alpha",
            "notes": None,
            "is_billable": True,
            "is_billed": False,
            "invoice_id": None,
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

    def test_billed_trip_cannot_be_cancelled(self):
        """Billed trips (is_billed=True) cannot be cancelled."""
        db = Mock()
        existing_row = self._existing_trip_row({"is_billed": True})
        db.execute_query = Mock(return_value=[existing_row])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="is billed and cannot be cancelled"):
            svc.cancel_trip(
                TENANT, 1,
                cancel_reason="Test reden",
                cancelled_by="user@example.com",
            )

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


# ── get_unbilled_trips ──────────────────────────────────────


class TestGetUnbilledTrips:
    """Tests for TripService.get_unbilled_trips.

    Covers: Requirement 6 (Client billing — get unbilled billable trips)
    Filter: administration + contact_id + is_billable=TRUE + is_billed=FALSE + is_cancelled=FALSE
    Order: trip_date ASC (oldest first for chronological billing)
    """

    def _unbilled_row(self, id=1, contact_id=5, trip_date=None):
        """Generate an unbilled billable trip row."""
        return _trip_row({
            "id": id,
            "contact_id": contact_id,
            "trip_date": trip_date or date(2026, 7, 10),
            "is_billable": 1,
            "is_billed": 0,
            "is_cancelled": 0,
        })

    def test_returns_unbilled_trips_for_contact(self):
        """Returns unbilled billable trips for the specified contact."""
        db = Mock()
        rows = [
            self._unbilled_row(id=1, trip_date=date(2026, 7, 10)),
            self._unbilled_row(id=2, trip_date=date(2026, 7, 12)),
        ]
        db.execute_query = Mock(side_effect=[
            rows,  # SELECT unbilled trips
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        result = svc.get_unbilled_trips(TENANT, contact_id=5)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[0]["is_billable"] is True
        assert result[0]["is_billed"] is False
        assert result[0]["contact"] == {"id": 5, "company_name": "Acme BV"}

    def test_empty_results_when_no_unbilled_trips(self):
        """Returns empty list when no unbilled trips exist for the contact."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        result = svc.get_unbilled_trips(TENANT, contact_id=99)

        assert result == []

    def test_tenant_isolation(self):
        """Query is always scoped by administration (tenant)."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_unbilled_trips("tenant_A", contact_id=5)

        query = db.execute_query.call_args[0][0]
        params = db.execute_query.call_args[0][1]
        assert "administration = %s" in query
        assert "tenant_A" in params

    def test_correct_filter_conditions(self):
        """Query includes all required WHERE conditions for unbilled billing."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_unbilled_trips(TENANT, contact_id=5)

        query = db.execute_query.call_args[0][0]
        params = db.execute_query.call_args[0][1]
        assert "administration = %s" in query
        assert "contact_id = %s" in query
        assert "is_billable = TRUE" in query
        assert "is_billed = FALSE" in query
        assert "is_cancelled = FALSE" in query
        assert "ORDER BY trip_date ASC" in query
        assert TENANT in params
        assert 5 in params

    def test_ordered_by_trip_date_ascending(self):
        """Results are ordered oldest first for chronological billing."""
        db = Mock()
        rows = [
            self._unbilled_row(id=1, trip_date=date(2026, 7, 5)),
            self._unbilled_row(id=2, trip_date=date(2026, 7, 10)),
            self._unbilled_row(id=3, trip_date=date(2026, 7, 15)),
        ]
        db.execute_query = Mock(side_effect=[
            rows,  # SELECT (ordered by DB)
            [{"id": 5, "company_name": "Acme BV"}],  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        result = svc.get_unbilled_trips(TENANT, contact_id=5)

        # Verify ORDER BY ASC in the query
        query = db.execute_query.call_args_list[0][0][0]
        assert "ORDER BY trip_date ASC" in query
        # Results should be in chronological order
        assert result[0]["trip_date"] == "2026-07-05"
        assert result[1]["trip_date"] == "2026-07-10"
        assert result[2]["trip_date"] == "2026-07-15"

    def test_enriches_with_contacts(self):
        """Results are enriched with contact information."""
        db = Mock()
        row = self._unbilled_row(id=1, contact_id=5)
        db.execute_query = Mock(side_effect=[
            [row],  # SELECT unbilled trips
            [{"id": 5, "company_name": "Client BV"}],  # enrich_with_contacts
        ])
        svc = _make_service(db=db)

        result = svc.get_unbilled_trips(TENANT, contact_id=5)

        assert len(result) == 1
        assert result[0]["contact"] == {"id": 5, "company_name": "Client BV"}

    def test_uses_parameterized_query(self):
        """Query uses %s placeholders (not f-string interpolation) for safety."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_unbilled_trips(TENANT, contact_id=5)

        query = db.execute_query.call_args[0][0]
        # Verify parameterized — no literal tenant or contact_id in query
        assert TENANT not in query
        assert "5" not in query.replace("%s", "")


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
