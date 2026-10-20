"""Unit tests for the Task 3.4 ``config#scope`` SAM migration script's PURE logic.

Paired test for ``backend/scripts/migrate_config_scope_to_sam.py`` (spec 02 Task 3.4,
change-with-tests contract, steering 30/34). Covers the bug-prone pure part —
``shape_config_scope_body`` — which encodes the migration invariant for the scope leg:

    The SAM ``config#scope`` body is ``{"dimensions": [...]}`` — exactly the shape
    ``MembersProjectionReader.get_scope_config`` reads back (R8.1). The builder
    (``build_config_scope_row``) already produces this; the shaper NORMALIZES to a dimensions
    list, treats a missing / non-list ``dimensions`` as EMPTY (tenant-wide, R8.5), and NEVER
    mutates the input.

Because the body is handed straight to the reader's shape, "normalize to a dimensions list"
IS the read-back equivalence guarantee for the scope subset. These tests are pure dict logic —
no MySQL, no boto3, no cross-plane ``sam.*`` import (steering 30/31/36: the Flask plane / its
tests do not import the SAM package; the operational script bridges both planes only at runtime).

Validates: Requirements 8.1, 8.5, 10.2, 1.5 (scope-subset equivalence)
Reference: .kiro/specs/Members/02 - members-config-sam-owned-write-path/
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

# conftest puts backend/ on sys.path, so the operational script imports as a package module.
# Only the PURE helper is exercised here — importing it does not pull in boto3/MySQL.
from scripts.migrate_config_scope_to_sam import shape_config_scope_body


class TestShapeNormalizesDimensions:
    """The body is normalized to ``{"dimensions": [...]}`` — the reader's exact shape."""

    def test_shape_carries_dimensions_verbatim(self):
        dims = [
            {
                "key": "region",
                "field": "region",
                "enabled": True,
                "values": ["Noord", "Zuid"],
            },
            {"key": "team", "field": "team", "enabled": False, "values": []},
        ]
        body = shape_config_scope_body({"dimensions": dims})
        assert body == {"dimensions": dims}

    def test_shape_result_has_only_the_dimensions_key(self):
        # A builder row may carry stray attrs; the shaped body authors ONLY dimensions.
        body = shape_config_scope_body(
            {"dimensions": [{"key": "region"}], "version": "x", "stray": 1}
        )
        assert set(body) == {"dimensions"}


class TestShapeEmptyIsValidTenantWide:
    """Empty / missing / malformed dimensions → an EMPTY list (tenant-wide, R8.5)."""

    def test_shape_absent_dimensions_is_empty(self):
        assert shape_config_scope_body({}) == {"dimensions": []}

    def test_shape_none_attrs_is_empty(self):
        assert shape_config_scope_body(None) == {"dimensions": []}

    def test_shape_explicit_empty_list_stays_empty(self):
        assert shape_config_scope_body({"dimensions": []}) == {"dimensions": []}

    def test_shape_non_list_dimensions_degrades_to_empty(self):
        # A malformed (non-list) value never raises and never leaks through — tenant-wide.
        assert shape_config_scope_body({"dimensions": "nope"}) == {"dimensions": []}
        assert shape_config_scope_body({"dimensions": {"k": 1}}) == {"dimensions": []}


class TestShapeNeverMutatesInput:
    """The shaper returns a NEW dict + a NEW dimensions list — the input is untouched."""

    def test_shape_does_not_mutate_the_input_dict(self):
        attrs = {"dimensions": [{"key": "region"}], "default_page_size": 100}
        before = {k: v for k, v in attrs.items()}
        shape_config_scope_body(attrs)
        assert (
            attrs == before
        )  # input unchanged (incl. the stray key, not dropped in place)

    def test_shape_dimensions_list_is_a_new_object(self):
        dims = [{"key": "region"}]
        body = shape_config_scope_body({"dimensions": dims})
        assert body["dimensions"] == dims
        assert (
            body["dimensions"] is not dims
        )  # a copy, so later mutation can't alias back


class TestShapeProperty:
    """Property: the result is ALWAYS ``{"dimensions": <list>}`` and never raises."""

    @given(
        st.one_of(
            st.none(),
            st.dictionaries(st.text(max_size=8), st.integers(), max_size=4),
            st.fixed_dictionaries(
                {
                    "dimensions": st.lists(
                        st.dictionaries(st.text(max_size=6), st.integers(), max_size=3),
                        max_size=4,
                    )
                }
            ),
        )
    )
    def test_result_is_always_a_dimensions_list(self, attrs):
        body = shape_config_scope_body(attrs)
        assert set(body) == {"dimensions"}
        assert isinstance(body["dimensions"], list)
