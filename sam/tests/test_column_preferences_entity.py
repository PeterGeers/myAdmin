"""
Pure-unit tests for the :class:`ColumnPreferences` entity (session-columns R6.1 / R6.6 / R4.5).

Pin the entity model's validate() / to_item() / from_item() behaviour, mirroring the sibling
preferred-list entity (``columns`` ↔ ``refs``). The CRITICAL cases: validation is SHAPE-only
(an empty column list is first-class — a user with no chosen columns, R6.4; a key that no longer
resolves is NEVER a validation error — it is skipped on READ, R6.6), and the record stores field
KEYS only (reference-not-copy, R6.6).

Validates: Requirements 6.1, 6.6, 4.5.
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

from sam.members.domain.column_preferences import (
    ColumnPreferences,
    ColumnPreferencesValidationError,
)


def _entry(**overrides):
    base = {
        "tenant_id": "h-dcn",
        "sub": "c2559464-user-sub",
        "columns": ["years_member", "membership.region"],
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return ColumnPreferences(**base)


class TestColumnPreferencesValidate:
    def test_valid_entry_passes(self):
        _entry().validate()  # must not raise

    def test_empty_columns_is_first_class(self):
        # A user with no chosen columns is valid — validate() must NOT require a non-empty list
        # (R6.4: empty is the first-time default, applied client-side, never an error).
        _entry(columns=[]).validate()  # must not raise

    def test_tuple_columns_are_accepted(self):
        _entry(columns=("a", "b")).validate()  # must not raise

    def test_blank_tenant_is_invalid(self):
        with pytest.raises(ColumnPreferencesValidationError) as exc:
            _entry(tenant_id="  ").validate()
        assert "tenant_id" in exc.value.errors

    def test_non_string_tenant_is_invalid(self):
        with pytest.raises(ColumnPreferencesValidationError) as exc:
            _entry(tenant_id=None).validate()  # type: ignore[arg-type]
        assert "tenant_id" in exc.value.errors

    def test_blank_sub_is_invalid(self):
        with pytest.raises(ColumnPreferencesValidationError) as exc:
            _entry(sub="").validate()
        assert "sub" in exc.value.errors

    def test_sub_with_separator_is_invalid(self):
        # The sub becomes a sort-key id segment; a '#' would make colprefs#<sub> ambiguous.
        with pytest.raises(ColumnPreferencesValidationError) as exc:
            _entry(sub="has#hash").validate()
        assert "sub" in exc.value.errors

    def test_non_list_columns_is_invalid(self):
        with pytest.raises(ColumnPreferencesValidationError) as exc:
            _entry(columns="years_member").validate()  # type: ignore[arg-type]
        assert "columns" in exc.value.errors

    def test_blank_column_key_is_invalid(self):
        with pytest.raises(ColumnPreferencesValidationError) as exc:
            _entry(columns=["years_member", "  "]).validate()
        assert "columns" in exc.value.errors

    def test_non_string_column_key_is_invalid(self):
        with pytest.raises(ColumnPreferencesValidationError) as exc:
            _entry(columns=["ok", 123]).validate()  # type: ignore[list-item]
        assert "columns" in exc.value.errors

    def test_dangling_key_is_shape_valid(self):
        # SHAPE-only: a key that no longer resolves to a field is a non-blank string, so it is
        # VALID here — it is skipped on READ (R6.6), never a validation error.
        _entry(columns=["a_field_that_was_removed"]).validate()  # must not raise

    def test_error_collects_every_problem_at_once(self):
        with pytest.raises(ColumnPreferencesValidationError) as exc:
            ColumnPreferences(tenant_id="", sub="", columns="nope").validate()  # type: ignore[arg-type]
        assert set(exc.value.errors) >= {"tenant_id", "sub", "columns"}


class TestColumnPreferencesRoundTrip:
    def test_to_item_carries_the_domain_shape(self):
        item = _entry().to_item()
        assert item == {
            "tenant_id": "h-dcn",
            "sub": "c2559464-user-sub",
            "columns": ["years_member", "membership.region"],
            "updated_at": "2024-01-01T00:00:00+00:00",
        }

    def test_to_item_validates_first(self):
        with pytest.raises(ColumnPreferencesValidationError):
            _entry(sub="").to_item()

    def test_to_item_copies_columns_to_a_list(self):
        item = _entry(columns=("a", "b")).to_item()
        assert item["columns"] == ["a", "b"]
        assert isinstance(item["columns"], list)

    def test_from_item_is_inverse_of_to_item(self):
        original = _entry()
        rebuilt = ColumnPreferences.from_item(original.to_item())
        assert rebuilt == original

    def test_from_item_tolerates_physical_key_attrs(self):
        item = _entry().to_item()
        item["sk"] = "colprefs#c2559464-user-sub"  # physical attr the repo adds
        rebuilt = ColumnPreferences.from_item(item)
        assert rebuilt.sub == "c2559464-user-sub"
        assert rebuilt.columns == ["years_member", "membership.region"]

    def test_from_item_defaults_absent_columns_to_empty(self):
        rebuilt = ColumnPreferences.from_item(
            {"tenant_id": "h-dcn", "sub": "s"}
        )
        assert rebuilt.columns == []
        assert rebuilt.updated_at == ""

    def test_from_item_drops_blank_and_non_string_keys(self):
        rebuilt = ColumnPreferences.from_item(
            {"tenant_id": "h-dcn", "sub": "s", "columns": ["ok", "", 7, "two"]}
        )
        assert rebuilt.columns == ["ok", "two"]

    def test_from_item_tolerates_non_list_columns(self):
        rebuilt = ColumnPreferences.from_item(
            {"tenant_id": "h-dcn", "sub": "s", "columns": "not-a-list"}
        )
        assert rebuilt.columns == []

    def test_from_item_rejects_non_mapping(self):
        with pytest.raises(ColumnPreferencesValidationError):
            ColumnPreferences.from_item(["not", "a", "mapping"])  # type: ignore[arg-type]


class TestColumnPreferencesEmpty:
    def test_empty_builds_a_valid_empty_set(self):
        entry = ColumnPreferences.empty("h-dcn", "s")
        assert entry.columns == []
        entry.validate()  # must not raise
