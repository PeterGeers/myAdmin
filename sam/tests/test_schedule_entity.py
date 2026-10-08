"""
Pure-unit tests for the :class:`ScheduleEntry` entity (R5 — scheduled execution foundation).

Pin the entity model's validate() / to_item() / from_item() behaviour (mirroring the sibling
``test_analytics_set_entity`` / ``test_template_entity`` tests): both-ways validation, a
to_item/from_item round-trip, the legacy ``enabled`` default, and a blank/non-string ``cron``
rejected. The entity is STORAGE-ONLY — the "the set must have a delivery block" rule (R5) is a
service/route gate (task 5.2), so it is deliberately NOT asserted here (the entity never reads
the referenced set).

Validates: Requirements R5
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

from sam.members.domain.schedule import (
    ScheduleEntry,
    ScheduleValidationError,
)


def _entry(**overrides):
    base = {
        "tenant_id": "h-dcn",
        "schedule_id": "sch-1",
        "set_id": "set-9",
        "cron": "cron(0 8 1 * ? *)",
        "created_by": "sub-1",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return ScheduleEntry(**base)


class TestScheduleEntryValidate:
    def test_valid_entry_passes(self):
        _entry().validate()  # must not raise

    def test_rate_expression_is_valid(self):
        _entry(cron="rate(30 days)").validate()

    def test_at_expression_is_valid(self):
        _entry(cron="at(2024-06-01T08:00:00)").validate()

    def test_blank_tenant_is_invalid(self):
        with pytest.raises(ScheduleValidationError) as exc:
            _entry(tenant_id="").validate()
        assert "tenant_id" in exc.value.errors

    def test_blank_schedule_id_is_invalid(self):
        with pytest.raises(ScheduleValidationError) as exc:
            _entry(schedule_id="   ").validate()
        assert "schedule_id" in exc.value.errors

    def test_schedule_id_with_separator_is_invalid(self):
        with pytest.raises(ScheduleValidationError) as exc:
            _entry(schedule_id="has#hash").validate()
        assert "schedule_id" in exc.value.errors

    def test_blank_set_id_is_invalid(self):
        with pytest.raises(ScheduleValidationError) as exc:
            _entry(set_id="").validate()
        assert "set_id" in exc.value.errors

    def test_blank_cron_is_invalid(self):
        with pytest.raises(ScheduleValidationError) as exc:
            _entry(cron="   ").validate()
        assert "cron" in exc.value.errors

    def test_non_string_cron_is_invalid(self):
        with pytest.raises(ScheduleValidationError) as exc:
            _entry(cron=123).validate()
        assert "cron" in exc.value.errors

    def test_non_bool_enabled_is_invalid(self):
        # A truthy string must NOT pass as the live/disabled flag.
        with pytest.raises(ScheduleValidationError) as exc:
            _entry(enabled="yes").validate()
        assert "enabled" in exc.value.errors

    def test_enabled_defaults_to_true(self):
        assert _entry().enabled is True

    def test_disabled_schedule_is_valid(self):
        entry = _entry(enabled=False)
        entry.validate()
        assert entry.enabled is False

    def test_reports_multiple_errors_at_once(self):
        with pytest.raises(ScheduleValidationError) as exc:
            _entry(tenant_id="", set_id="", cron="").validate()
        assert {"tenant_id", "set_id", "cron"} <= set(exc.value.errors)


class TestScheduleEntryRoundTrip:
    def test_to_item_carries_the_shape(self):
        item = _entry().to_item()
        assert item["tenant_id"] == "h-dcn"
        assert item["schedule_id"] == "sch-1"
        assert item["set_id"] == "set-9"
        assert item["cron"] == "cron(0 8 1 * ? *)"
        assert item["created_by"] == "sub-1"
        assert item["enabled"] is True

    def test_to_item_validates_first(self):
        with pytest.raises(ScheduleValidationError):
            _entry(cron="").to_item()

    def test_from_item_is_inverse_of_to_item(self):
        original = _entry(enabled=False)
        rebuilt = ScheduleEntry.from_item(original.to_item())
        assert rebuilt == original

    def test_from_item_tolerates_physical_key_attrs(self):
        item = _entry().to_item()
        item["sk"] = "schedule#sch-1"  # physical attr the repo adds
        rebuilt = ScheduleEntry.from_item(item)
        assert rebuilt.schedule_id == "sch-1"
        assert rebuilt.set_id == "set-9"

    def test_from_item_defaults_legacy_enabled_to_true(self):
        # A legacy item written before `enabled` existed loads as enabled=True.
        rebuilt = ScheduleEntry.from_item(
            {
                "tenant_id": "h-dcn",
                "schedule_id": "sch-1",
                "set_id": "set-9",
                "cron": "rate(1 day)",
            }
        )
        assert rebuilt.enabled is True
        assert rebuilt.created_by == ""

    def test_from_item_coerces_enabled_to_bool(self):
        rebuilt = ScheduleEntry.from_item(
            {
                "tenant_id": "h-dcn",
                "schedule_id": "sch-1",
                "set_id": "set-9",
                "cron": "rate(1 day)",
                "enabled": False,
            }
        )
        assert rebuilt.enabled is False

    def test_sort_order_key_is_set_then_schedule(self):
        assert _entry().sort_order_key() == ("set-9", "sch-1")
