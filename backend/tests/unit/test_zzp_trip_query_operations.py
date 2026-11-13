"""Direct unit tests for services/zzp_trip_query_service.py.

Covers tenant-scoped reads, filter/pagination building, audit-history
parsing, unresolved gap listing, and odometer gap detection.

Reference: .kiro/specs/ZZP/rittenregistratie/design.md section 4.2
"""

import json
from datetime import date, datetime
from unittest.mock import Mock

from services.zzp_trip_query_service import TripQueryService

TENANT = "test_admin"
TRIP = {"id": 1, "trip_date": date(2026, 4, 1), "end_odometer": 1000}


def _query(rows=None):
    parent = Mock()
    parent.db = Mock()
    parent.db.execute_query.return_value = rows if rows is not None else []
    parent._format_trip.side_effect = lambda row: dict(row)
    return TripQueryService(parent)


class TestGetTrip:
    def test_missing_trip_returns_none(self):
        assert _query([]).get_trip(TENANT, 9) is None

    def test_read_is_tenant_scoped(self):
        svc = _query([TRIP])
        assert svc.get_trip(TENANT, 1)["id"] == 1
        _sql, params = svc.db.execute_query.call_args[0]
        assert params == (1, TENANT)
        assert "administration = %s" in _sql


class TestListTrips:
    def test_tenant_and_cancelled_filters_are_applied(self):
        svc = _query([])
        svc.db.execute_query.side_effect = [[{"total": 0}], []]
        result = svc.list_trips(TENANT)
        assert result == {"data": [], "total": 0}
        count_sql, count_params = svc.db.execute_query.call_args_list[0][0]
        assert "administration = %s" in count_sql
        assert "is_cancelled = FALSE" in count_sql
        assert count_params == (TENANT,)

    def test_filters_and_pagination_are_bound(self):
        svc = _query([])
        svc.db.execute_query.side_effect = [[{"total": 3}], []]
        svc.list_trips(
            TENANT,
            {"vehicle_id": 7, "date_from": "2026-01-01", "limit": 10, "offset": 40},
        )
        data_sql, data_params = svc.db.execute_query.call_args_list[1][0]
        assert "vehicle_id = %s" in data_sql
        assert "LIMIT %s OFFSET %s" in data_sql
        assert data_params[-2:] == (10, 40)


class TestTripHistory:
    def test_changed_fields_json_is_parsed(self):
        row = {
            "version": 2,
            "action": "updated",
            "changed_fields": json.dumps({"notes": {"old": "a", "new": "b"}}),
            "correction_reason": "fix",
            "changed_by": "tester",
            "changed_at": datetime(2026, 4, 2, 9, 30),
        }
        svc = _query([row])
        history = svc.get_trip_history(TENANT, 1)
        assert history[0]["version"] == 2
        assert history[0]["changed_fields"] == {"notes": {"old": "a", "new": "b"}}
        assert history[0]["changed_at"] == "2026-04-02T09:30:00"

    def test_history_query_is_tenant_scoped(self):
        svc = _query([])
        svc.get_trip_history(TENANT, 5)
        sql, params = svc.db.execute_query.call_args[0]
        assert "administration = %s" in sql
        assert params == (5, TENANT)


class TestUnresolvedGaps:
    def test_only_unregistered_gap_fills_are_listed(self):
        svc = _query([TRIP])
        assert svc.get_unresolved_gaps(TENANT) == [TRIP]
        sql, params = svc.db.execute_query.call_args[0]
        assert "is_gap_fill = TRUE" in sql
        assert params == (TENANT, "Niet geregistreerd")

    def test_vehicle_filter_is_appended(self):
        svc = _query([])
        svc.get_unresolved_gaps(TENANT, vehicle_id=3)
        sql, params = svc.db.execute_query.call_args[0]
        assert "vehicle_id = %s" in sql
        assert params == (TENANT, "Niet geregistreerd", 3)


class TestDetectGap:
    def test_gap_against_previous_trip(self):
        svc = _query([{"end_odometer": 1000}])
        gap = svc.detect_gap(TENANT, 1, 1200)
        assert gap == {
            "gap_km": 200,
            "previous_end_odometer": 1000,
            "current_start_odometer": 1200,
        }

    def test_no_gap_when_odometers_match(self):
        assert _query([{"end_odometer": 1000}]).detect_gap(TENANT, 1, 1000) is None

    def test_first_trip_falls_back_to_vehicle_start(self):
        svc = _query([])
        svc.db.execute_query.side_effect = [[], [{"start_odometer": 500}]]
        assert svc.detect_gap(TENANT, 1, 700)["gap_km"] == 200

    def test_unknown_vehicle_returns_none(self):
        svc = _query([])
        svc.db.execute_query.side_effect = [[], []]
        assert svc.detect_gap(TENANT, 1, 700) is None
