"""Direct unit tests for services/_projection_scope_builder.py.

Covers the config#scope projection row builder.
Reference: .kiro/specs/code-quality-maintenance/code-quality-fixes/
"""

import datetime as dt
from unittest.mock import Mock

import pytest

from services._projection_scope_builder import (
    _map_scope_dimension,
    _scope_dimension_from_field as sdf,
    _scope_dimensions_from_overlay as dims_from_overlay,
    build_config_scope_row,
)

TENANT = "test_admin"
TENANT_TS = dt.datetime(2026, 1, 1, 12, 0, 0)
TENANT_ROW = {"administration": TENANT, "updated_at": TENANT_TS}


def _param_service(overlay=...):
    svc = Mock()
    svc.get_param_revision.return_value = None

    def _get_param(namespace, key, tenant=...):
        if key.endswith("overlay"):
            return overlay
        return None

    svc.get_param.side_effect = _get_param
    return svc


class TestMapScopeDimension:
    def test_defaults_are_filled_in(self):
        dim = _map_scope_dimension({})
        assert dim["key"] is None
        assert dim["field"] is None
        assert dim["label"] == {}
        assert dim["enabled"] is True
        assert dim["values"] == []
        assert dim["required_for"] == []

    def test_authored_values_are_kept(self):
        raw = {
            "key": "region",
            "field": "region",
            "label": {"nl": "Regio"},
            "enabled": False,
            "values": ["A"],
            "required_for": ["x"],
        }
        assert _map_scope_dimension(raw) == raw

    def test_unknown_keys_are_dropped(self):
        assert "bogus" not in _map_scope_dimension({"key": "region", "bogus": 1})

    def test_explicit_none_falls_back_to_default(self):
        dim = _map_scope_dimension({"values": None, "enabled": None})
        assert dim["values"] == []
        assert dim["enabled"] is True


class TestScopeDimensionFromField:
    def test_values_come_from_field_options(self):
        dim = sdf("region", {}, {"options": [{"value": "A"}, {"value": "B"}]})
        assert dim["key"] == "region"
        assert dim["field"] == "region"
        assert dim["values"] == ["A", "B"]

    def test_legacy_scope_values_are_a_fallback(self):
        dim = sdf("region", {"values": ["Legacy"]}, {})
        assert dim["values"] == ["Legacy"]

    def test_scope_attributes_are_carried(self):
        scope = {"enabled": False, "label": {"nl": "Regio"}, "required_for": ["x"]}
        dim = sdf("region", scope, {"options": [{"value": "A"}]})
        assert dim["enabled"] is False
        assert dim["label"] == {"nl": "Regio"}
        assert dim["required_for"] == ["x"]


class TestScopeDimensionsFromOverlay:
    def test_non_mapping_overlay_yields_empty(self):
        assert dims_from_overlay("nope") == []
        assert dims_from_overlay(None) == []

    def test_fields_without_scope_are_ignored(self):
        assert dims_from_overlay({"fields": {"a": {"key": "a"}}}) == []

    def test_fixed_overrides_precede_variable_fields(self):
        overlay = {
            "fixed_overrides": {
                "personal.region": {
                    "key": "personal.region",
                    "scope": {"enabled": True},
                }
            },
            "fields": {"team": {"key": "team", "scope": {"enabled": True}}},
        }
        assert [d["key"] for d in dims_from_overlay(overlay)] == ["region", "team"]

    def test_duplicate_keys_keep_the_first_occurrence(self):
        overlay = {
            "fixed_overrides": {
                "region": {"key": "region", "scope": {"enabled": False}}
            },
            "fields": {"region": {"key": "region", "scope": {"enabled": True}}},
        }
        dims = dims_from_overlay(overlay)
        assert len(dims) == 1
        assert dims[0]["enabled"] is False


class TestBuildConfigScopeRow:
    def test_missing_tenant_key_raises(self):
        with pytest.raises(ValueError, match="cross-tenant hazard"):
            build_config_scope_row({}, _param_service({}))

    def test_empty_overlay_is_a_valid_empty_row(self):
        item = build_config_scope_row(TENANT_ROW, _param_service({}))
        assert item.tenant_id == TENANT
        assert item.sort_key == "config#scope"
        assert item.attributes == {"dimensions": []}

    def test_dimensions_are_derived_from_overlay(self):
        overlay = {
            "fields": {
                "region": {
                    "key": "region",
                    "options": [{"value": "A"}, {"value": "B"}],
                    "scope": {"enabled": True},
                }
            }
        }
        dims = build_config_scope_row(TENANT_ROW, _param_service(overlay)).attributes[
            "dimensions"
        ]
        assert [d["key"] for d in dims] == ["region"]
        assert dims[0]["values"] == ["A", "B"]

    def test_version_falls_back_to_tenant_row(self):
        item = build_config_scope_row(TENANT_ROW, _param_service({}))
        assert item.version == TENANT_TS.isoformat()
