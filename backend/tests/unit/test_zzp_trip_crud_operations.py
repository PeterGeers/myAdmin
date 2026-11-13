"""Direct unit tests for services/zzp_trip_crud_service.py.

Covers trip creation validation, odometer-gap warnings, correction
updates (version bump + audit), soft cancellation, and audit writing.

Reference: .kiro/specs/ZZP/rittenregistratie/design.md section 4.1
"""

from unittest.mock import Mock

import pytest

from services.zzp_trip_crud_service import TripCrudService

TENANT = "test_admin"

TRIP_DATA = {
    "vehicle_id": 1,
    "trip_date": "2026-04-01",
    "start_address": "A",
    "end_address": "B",
    "start_odometer": 1000,
    "end_odometer": 1100,
    "trip_category": "Zakelijk",
    "trip_purpose": "Klantbezoek",
}


def _crud(gap=None, existing=None):
    parent = Mock()
    parent.db = Mock()
    parent.db.execute_query.side_effect = lambda sql, params=None, **kw: (
        7 if "INSERT INTO zz" in sql else []
    )
    parent._parse_date.side_effect = lambda value: value
    parent.detect_gap.return_value = gap
    parent.get_trip.return_value = {"id": 7}
    parent._get_raw_trip.return_value = existing
    parent._normalize_for_comparison.side_effect = lambda value: value
    parent._serialize_value.side_effect = lambda value: value
    parent._get_ritten_param.return_value = 300
    parent.parameter_service = Mock()
    return TripCrudService(parent), parent


class TestCreateTrip:
    def test_odometer_must_advance(self):
        crud, _ = _crud()
        bad = dict(TRIP_DATA, end_odometer=1000)
        with pytest.raises(ValueError, match="end_odometer must be greater"):
            crud.create_trip(TENANT, bad, "tester")

    def test_success_returns_trip_and_writes_audit(self):
        crud, parent = _crud()
        result = crud.create_trip(TENANT, TRIP_DATA, "tester")
        assert result["success"] is True
        assert result["data"] == {"id": 7}
        calls = [c[0][0] for c in parent.db.execute_query.call_args_list]
        assert any("INSERT INTO zzp_trip_audit" in sql for sql in calls)

    def test_gap_detection_adds_warning_and_offer(self):
        gap = {
            "gap_km": 50,
            "previous_end_odometer": 950,
            "current_start_odometer": 1000,
        }
        crud, _ = _crud(gap=gap)
        result = crud.create_trip(TENANT, TRIP_DATA, "tester")
        assert result["warnings"][0]["type"] == "odometer_gap"
        assert result["gap_fill_offer"]["start_odometer"] == 950

    def test_large_distance_adds_warning(self):
        crud, _ = _crud()
        far = dict(TRIP_DATA, end_odometer=2000)
        result = crud.create_trip(TENANT, far, "tester")
        assert [w["type"] for w in result["warnings"]] == ["large_distance"]


class TestUpdateTrip:
    def test_correction_reason_is_required(self):
        crud, _ = _crud(existing={"id": 7, "notes": "a"})
        with pytest.raises(ValueError, match="correction_reason is required"):
            crud.update_trip(TENANT, 7, {"notes": "b"}, "  ", "tester")

    def test_unknown_trip_is_rejected(self):
        crud, _ = _crud(existing=None)
        with pytest.raises(ValueError, match="not found for this tenant"):
            crud.update_trip(TENANT, 7, {"notes": "b"}, "fix", "tester")

    def test_no_updatable_fields_is_rejected(self):
        crud, _ = _crud(existing={"id": 7})
        with pytest.raises(ValueError, match="No valid fields to update"):
            crud.update_trip(TENANT, 7, {"bogus": 1}, "fix", "tester")

    def test_unchanged_values_are_rejected(self):
        crud, _ = _crud(existing={"id": 7, "notes": "a"})
        with pytest.raises(ValueError, match="No fields have changed"):
            crud.update_trip(TENANT, 7, {"notes": "a"}, "fix", "tester")

    def test_success_bumps_version_and_audits(self):
        crud, parent = _crud(existing={"id": 7, "version": 2, "notes": "a"})
        parent.get_trip.return_value = {"id": 7, "version": 3}
        updated = crud.update_trip(TENANT, 7, {"notes": "b"}, "fix", "tester")
        assert updated == {"id": 7, "version": 3}
        update_call = parent.db.execute_query.call_args_list[0][0]
        assert "UPDATE zzp_trips" in update_call[0]
        assert update_call[1][-1] == TENANT
        audit_call = parent.db.execute_query.call_args_list[1][0]
        assert "INSERT INTO zzp_trip_audit" in audit_call[0]
        assert audit_call[1][2] == 3


class TestCancelTrip:
    def test_reason_is_required(self):
        crud, _ = _crud(existing={"id": 7})
        with pytest.raises(ValueError, match="cancel_reason is required"):
            crud.cancel_trip(TENANT, 7, "", "tester")

    def test_unknown_trip_is_rejected(self):
        crud, _ = _crud(existing=None)
        with pytest.raises(ValueError, match="not found for this tenant"):
            crud.cancel_trip(TENANT, 7, "duplicate", "tester")

    def test_already_cancelled_is_rejected(self):
        crud, _ = _crud(existing={"id": 7, "is_cancelled": True})
        with pytest.raises(ValueError, match="already cancelled"):
            crud.cancel_trip(TENANT, 7, "duplicate", "tester")

    def test_success_soft_cancels_and_audits(self):
        crud, parent = _crud(existing={"id": 7, "version": 4})
        assert crud.cancel_trip(TENANT, 7, "duplicate", "tester") is True
        sql, params = parent.db.execute_query.call_args_list[0][0]
        assert "is_cancelled = TRUE" in sql
        assert params == ("duplicate", 7, TENANT)
