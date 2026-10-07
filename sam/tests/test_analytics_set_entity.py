"""
Pure-unit tests for the :class:`AnalyticsSetEntry` entity (F-012).

Pin the entity model's validate() / to_item() / from_item() behaviour, mirroring the sibling
``test_membership_type_catalog`` entity tests. The CRITICAL case is F-011: an EMPTY
``group_columns`` AND EMPTY ``aggregate_measures`` filtered-list definition is first-class —
validate() must accept it (it never requires those to be non-empty).

Validates: finding F-011 (filtered-list set with empty group/measures is valid) + F-012.
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

from sam.members.domain.analytics_set import (
    AnalyticsSetEntry,
    AnalyticsSetValidationError,
)


def _definition(*, group=None, measures=None):
    """A snake_case PivotConfig-shaped definition (the frontend sends this)."""
    return {
        "data_source": "members",
        "group_columns": group if group is not None else [],
        "aggregate_measures": measures if measures is not None else [],
        "filters": {},
        "column_pivot": None,
        "column_nest_levels": [],
        "display_mode": "flat",
        "include_rollup": False,
    }


def _entry(**overrides):
    base = {
        "tenant_id": "h-dcn",
        "set_id": "abc123",
        "name": "Paper clubblad",
        "kind": "count",
        "definition": _definition(
            group=["membership_type"], measures=[{"function": "COUNT", "column": "*"}]
        ),
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return AnalyticsSetEntry(**base)


class TestAnalyticsSetEntryValidate:
    def test_valid_count_set_passes(self):
        _entry(kind="count").validate()  # must not raise

    def test_valid_list_set_passes(self):
        _entry(kind="list").validate()  # must not raise

    def test_empty_group_and_measures_is_first_class(self):
        # THE F-011 regression at the entity level: an empty-group, empty-measures filtered-list
        # set is valid — validate() must NOT require group_columns / aggregate_measures.
        entry = _entry(kind="list", definition=_definition(group=[], measures=[]))
        entry.validate()  # must not raise

    def test_blank_name_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(name="  ").validate()
        assert "name" in exc.value.errors

    def test_blank_tenant_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(tenant_id="").validate()
        assert "tenant_id" in exc.value.errors

    def test_blank_set_id_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(set_id="").validate()
        assert "set_id" in exc.value.errors

    def test_set_id_with_separator_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(set_id="has#hash").validate()
        assert "set_id" in exc.value.errors

    def test_bad_kind_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(kind="pie").validate()
        assert "kind" in exc.value.errors

    def test_non_mapping_definition_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(definition=["not", "a", "mapping"]).validate()
        assert "definition" in exc.value.errors

    # R11.2/R11.3 — origin + created_by (shared-library attribution).
    def test_origin_defaults_to_user(self):
        assert _entry().origin == "user"

    def test_valid_origin_passes(self):
        _entry(origin="user").validate()
        _entry(origin="predefined").validate()

    def test_bad_origin_is_invalid(self):
        with pytest.raises(AnalyticsSetValidationError) as exc:
            _entry(origin="imported").validate()
        assert "origin" in exc.value.errors

    def test_created_by_is_optional_and_ungated(self):
        # created_by is attribution-only (a user sub) — blank is fine, never a validation error.
        _entry(created_by="").validate()
        _entry(created_by="c2559464-sub").validate()


class TestAnalyticsSetEntryRoundTrip:
    def test_to_item_carries_the_domain_shape(self):
        item = _entry(created_by="sub-1").to_item()
        assert item["tenant_id"] == "h-dcn"
        assert item["set_id"] == "abc123"
        assert item["name"] == "Paper clubblad"
        assert item["kind"] == "count"
        assert item["definition"]["data_source"] == "members"
        assert item["origin"] == "user"
        assert item["created_by"] == "sub-1"
        assert item["created_at"] == "2024-01-01T00:00:00+00:00"
        assert item["updated_at"] == "2024-01-01T00:00:00+00:00"

    def test_from_item_defaults_origin_and_created_by_for_legacy_item(self):
        # A legacy stored item written before origin/created_by existed.
        rebuilt = AnalyticsSetEntry.from_item(
            {"tenant_id": "h-dcn", "set_id": "x", "name": "N", "kind": "list"}
        )
        assert rebuilt.origin == "user"
        assert rebuilt.created_by == ""

    def test_to_item_validates_first(self):
        with pytest.raises(AnalyticsSetValidationError):
            _entry(name="").to_item()

    def test_from_item_is_inverse_of_to_item(self):
        original = _entry(kind="list", definition=_definition(group=[], measures=[]))
        rebuilt = AnalyticsSetEntry.from_item(original.to_item())
        assert rebuilt == original

    def test_from_item_tolerates_physical_key_attrs(self):
        item = _entry().to_item()
        item["sk"] = "analyticsset#abc123"  # physical attr the repo adds
        rebuilt = AnalyticsSetEntry.from_item(item)
        assert rebuilt.set_id == "abc123"
        assert rebuilt.name == "Paper clubblad"

    def test_from_item_defaults_absent_definition_and_kind(self):
        rebuilt = AnalyticsSetEntry.from_item(
            {"tenant_id": "h-dcn", "set_id": "x", "name": "N"}
        )
        assert rebuilt.definition == {}
        assert rebuilt.kind == "count"
