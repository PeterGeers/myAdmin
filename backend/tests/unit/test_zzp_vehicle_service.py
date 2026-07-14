"""Unit tests for VehicleService — CRUD operations and edge cases.

Covers: Requirement 1 (Vehicle registration and management)
Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.1
"""

import pytest
from unittest.mock import Mock
from datetime import date, datetime

from services.zzp_vehicle_service import VehicleService
from db_exceptions import IntegrityError


TENANT = "test_admin"


def _make_service(db=None, parameter_service=None):
    """Create a VehicleService with mocked dependencies."""
    db = db or Mock()
    return VehicleService(db=db, parameter_service=parameter_service)


def _vehicle_row(overrides=None):
    """Generate a realistic vehicle row dict as returned by the DB."""
    row = {
        "id": 1,
        "administration": TENANT,
        "license_plate": "AB-123-CD",
        "make": "Volkswagen",
        "model": "Golf",
        "year_built": 2020,
        "vin": "WVWZZZ1KZYW123456",
        "vehicle_type": "private_for_business",
        "odometer_unit": "km",
        "owner_lease_company": None,
        "start_odometer": 45000,
        "start_date": date(2026, 1, 1),
        "is_active": 1,
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 1, 10, 0, 0),
        "created_by": "user@example.com",
    }
    if overrides:
        row.update(overrides)
    return row


# ── create_vehicle ──────────────────────────────────────────


class TestCreateVehicle:
    """Tests for VehicleService.create_vehicle."""

    def test_happy_path_all_fields(self):
        """Create vehicle with all fields returns formatted vehicle dict."""
        db = Mock()
        # execute_query for INSERT returns the new ID
        db.execute_query = Mock(side_effect=[
            1,  # INSERT returns vehicle_id
            [_vehicle_row()],  # get_vehicle SELECT
        ])
        svc = _make_service(db=db)

        data = {
            "license_plate": "ab-123-cd",
            "make": "Volkswagen",
            "model": "Golf",
            "year_built": 2020,
            "vin": "WVWZZZ1KZYW123456",
            "vehicle_type": "private_for_business",
            "odometer_unit": "km",
            "owner_lease_company": None,
            "start_odometer": 45000,
            "start_date": "2026-01-01",
        }
        result = svc.create_vehicle(TENANT, data, created_by="user@example.com")

        assert result["id"] == 1
        assert result["license_plate"] == "AB-123-CD"
        assert result["is_active"] is True
        assert result["start_odometer"] == 45000
        # Verify INSERT was called with fetch=False, commit=True
        insert_call = db.execute_query.call_args_list[0]
        assert insert_call[1]["fetch"] is False
        assert insert_call[1]["commit"] is True

    def test_license_plate_uppercased_and_stripped(self):
        """License plate is normalized to uppercase and stripped."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            1,
            [_vehicle_row({"license_plate": "XY-987-ZZ"})],
        ])
        svc = _make_service(db=db)

        data = {
            "license_plate": "  xy-987-zz  ",
            "vehicle_type": "business",
            "start_odometer": 0,
            "start_date": "2026-01-01",
        }
        svc.create_vehicle(TENANT, data, created_by="user@example.com")

        # Verify the INSERT params have the uppercased/stripped plate
        insert_call = db.execute_query.call_args_list[0]
        params = insert_call[0][1]
        assert params[1] == "XY-987-ZZ"

    def test_duplicate_license_plate_raises_integrity_error(self):
        """Duplicate license plate for same tenant raises IntegrityError."""
        db = Mock()
        db.execute_query = Mock(side_effect=IntegrityError(
            "Duplicate entry", error_code=1062, original_error=Exception("dup")
        ))
        svc = _make_service(db=db)

        data = {
            "license_plate": "AB-123-CD",
            "vehicle_type": "private_for_business",
            "start_odometer": 45000,
            "start_date": "2026-01-01",
        }
        with pytest.raises(IntegrityError, match="already exists"):
            svc.create_vehicle(TENANT, data, created_by="user@example.com")

    def test_missing_required_field_raises_value_error(self):
        """Missing required field raises ValueError."""
        svc = _make_service()
        data = {"license_plate": "AB-123-CD", "vehicle_type": "business"}
        # Missing start_odometer and start_date
        with pytest.raises(ValueError, match="Missing required field"):
            svc.create_vehicle(TENANT, data, created_by="user@example.com")

    def test_invalid_vehicle_type_raises_value_error(self):
        """Invalid vehicle_type raises ValueError."""
        svc = _make_service()
        data = {
            "license_plate": "AB-123-CD",
            "vehicle_type": "truck",
            "start_odometer": 0,
            "start_date": "2026-01-01",
        }
        with pytest.raises(ValueError, match="Invalid vehicle_type"):
            svc.create_vehicle(TENANT, data, created_by="user@example.com")

    def test_negative_start_odometer_raises_value_error(self):
        """Negative start_odometer raises ValueError."""
        svc = _make_service()
        data = {
            "license_plate": "AB-123-CD",
            "vehicle_type": "private_for_business",
            "start_odometer": -100,
            "start_date": "2026-01-01",
        }
        with pytest.raises(ValueError, match="non-negative"):
            svc.create_vehicle(TENANT, data, created_by="user@example.com")


# ── update_vehicle ──────────────────────────────────────────


class TestUpdateVehicle:
    """Tests for VehicleService.update_vehicle."""

    def test_happy_path_change_make_model_year(self):
        """Update make/model/year succeeds and returns updated vehicle."""
        db = Mock()
        updated_row = _vehicle_row({"make": "Toyota", "model": "Corolla", "year_built": 2022})
        db.execute_query = Mock(side_effect=[
            [_vehicle_row()],  # get_vehicle (existing check)
            None,              # UPDATE query
            [updated_row],     # get_vehicle (return updated)
        ])
        svc = _make_service(db=db)

        result = svc.update_vehicle(TENANT, 1, {
            "make": "Toyota", "model": "Corolla", "year_built": 2022
        })

        assert result["make"] == "Toyota"
        assert result["model"] == "Corolla"
        assert result["year_built"] == 2022

    def test_cannot_change_start_odometer_if_trips_exist(self):
        """Changing start_odometer when trips exist raises ValueError."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [_vehicle_row()],   # get_vehicle (existing)
            [{"1": 1}],         # _has_trips returns a row (trips exist)
        ])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="Cannot change start_odometer"):
            svc.update_vehicle(TENANT, 1, {"start_odometer": 50000})

    def test_change_start_odometer_allowed_if_no_trips(self):
        """Changing start_odometer succeeds when no trips exist."""
        db = Mock()
        updated_row = _vehicle_row({"start_odometer": 50000})
        db.execute_query = Mock(side_effect=[
            [_vehicle_row()],   # get_vehicle (existing)
            [],                 # _has_trips returns empty (no trips)
            None,               # UPDATE
            [updated_row],      # get_vehicle (return updated)
        ])
        svc = _make_service(db=db)

        result = svc.update_vehicle(TENANT, 1, {"start_odometer": 50000})
        assert result["start_odometer"] == 50000

    def test_vehicle_not_found_raises_value_error(self):
        """Updating non-existent vehicle raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="not found"):
            svc.update_vehicle(TENANT, 999, {"make": "Ford"})

    def test_no_changes_returns_existing(self):
        """Empty update dict returns existing vehicle unchanged."""
        db = Mock()
        db.execute_query = Mock(return_value=[_vehicle_row()])
        svc = _make_service(db=db)

        result = svc.update_vehicle(TENANT, 1, {})
        assert result["id"] == 1
        # Only one DB call (get_vehicle), no UPDATE executed
        assert db.execute_query.call_count == 1


# ── deactivate_vehicle ──────────────────────────────────────


class TestDeactivateVehicle:
    """Tests for VehicleService.deactivate_vehicle."""

    def test_sets_is_active_false(self):
        """Deactivating a vehicle sets is_active=False and returns True."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [_vehicle_row()],  # get_vehicle (existing check)
            None,              # UPDATE is_active = FALSE
        ])
        svc = _make_service(db=db)

        result = svc.deactivate_vehicle(TENANT, 1)

        assert result is True
        # Verify the UPDATE query sets is_active = FALSE
        update_call = db.execute_query.call_args_list[1]
        assert "is_active = FALSE" in update_call[0][0]
        assert update_call[1]["commit"] is True

    def test_vehicle_not_found_raises_value_error(self):
        """Deactivating non-existent vehicle raises ValueError."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="not found"):
            svc.deactivate_vehicle(TENANT, 999)


# ── get_vehicle ─────────────────────────────────────────────


class TestGetVehicle:
    """Tests for VehicleService.get_vehicle."""

    def test_existing_vehicle_returns_data(self):
        """Getting an existing vehicle returns formatted dict."""
        db = Mock()
        db.execute_query = Mock(return_value=[_vehicle_row()])
        svc = _make_service(db=db)

        result = svc.get_vehicle(TENANT, 1)

        assert result is not None
        assert result["id"] == 1
        assert result["license_plate"] == "AB-123-CD"
        assert result["is_active"] is True
        # Dates should be ISO formatted
        assert result["start_date"] == "2026-01-01"
        assert isinstance(result["created_at"], str)

    def test_non_existent_returns_none(self):
        """Getting a non-existent vehicle returns None."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        result = svc.get_vehicle(TENANT, 999)
        assert result is None

    def test_tenant_scoping_in_query(self):
        """Query includes tenant (administration) parameter for isolation."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        svc.get_vehicle(TENANT, 1)

        call_args = db.execute_query.call_args[0]
        assert "administration = %s" in call_args[0]
        assert TENANT in call_args[1]


# ── list_vehicles ───────────────────────────────────────────


class TestListVehicles:
    """Tests for VehicleService.list_vehicles."""

    def test_active_only_true_filters_inactive(self):
        """active_only=True only returns active vehicles."""
        db = Mock()
        active_row = _vehicle_row({"id": 1, "is_active": 1})
        db.execute_query = Mock(return_value=[active_row])
        svc = _make_service(db=db)

        result = svc.list_vehicles(TENANT, active_only=True)

        assert len(result) == 1
        assert result[0]["is_active"] is True
        # Verify query contains is_active = TRUE filter
        query = db.execute_query.call_args[0][0]
        assert "is_active = TRUE" in query

    def test_active_only_false_returns_all(self):
        """active_only=False returns both active and inactive vehicles."""
        db = Mock()
        rows = [
            _vehicle_row({"id": 1, "is_active": 1}),
            _vehicle_row({"id": 2, "is_active": 0, "license_plate": "ZZ-999-AA"}),
        ]
        db.execute_query = Mock(return_value=rows)
        svc = _make_service(db=db)

        result = svc.list_vehicles(TENANT, active_only=False)

        assert len(result) == 2
        # Verify query does NOT filter by is_active
        query = db.execute_query.call_args[0][0]
        assert "is_active = TRUE" not in query

    def test_empty_list_returns_empty(self):
        """No vehicles for tenant returns empty list."""
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_service(db=db)

        result = svc.list_vehicles(TENANT)
        assert result == []


# ── get_last_odometer ───────────────────────────────────────


class TestGetLastOdometer:
    """Tests for VehicleService.get_last_odometer."""

    def test_returns_end_odometer_from_most_recent_trip(self):
        """Returns end_odometer from the most recent non-cancelled trip."""
        db = Mock()
        db.execute_query = Mock(return_value=[{"end_odometer": 48500}])
        svc = _make_service(db=db)

        result = svc.get_last_odometer(TENANT, 1)

        assert result == 48500
        # Verify query orders by trip_date DESC, id DESC
        query = db.execute_query.call_args[0][0]
        assert "ORDER BY trip_date DESC" in query
        assert "is_cancelled = FALSE" in query

    def test_no_trips_returns_start_odometer(self):
        """No trips for vehicle returns the vehicle's start_odometer."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [],                  # No trips found
            [_vehicle_row()],    # get_vehicle for fallback
        ])
        svc = _make_service(db=db)

        result = svc.get_last_odometer(TENANT, 1)
        assert result == 45000

    def test_vehicle_not_found_raises_value_error(self):
        """No trips and no vehicle raises ValueError."""
        db = Mock()
        db.execute_query = Mock(side_effect=[
            [],   # No trips
            [],   # Vehicle not found
        ])
        svc = _make_service(db=db)

        with pytest.raises(ValueError, match="not found"):
            svc.get_last_odometer(TENANT, 999)
