"""Unit tests for the Task 1.12 ``config#fields`` SAM migration script's PURE logic.

Paired test for ``backend/scripts/migrate_config_fields_to_sam.py`` (spec 02 Task 1.12,
change-with-tests contract, steering 30/34). Covers the one genuinely bug-prone pure part —
``shape_config_fields_body`` — which encodes the spec's single most important migration
invariant:

    Migrate ``members.field_overlay`` ONLY. The ``fields`` / ``overrides`` /
    ``functional_groups`` maps are carried VERBATIM into the SAM ``config#fields`` body, and
    the retired ``default_page_size`` scalar (Req 7.2 / Requirement 25 — now a per-user runtime
    selector) is NEVER copied to SAM.

Because the body is handed straight to the Members projection reader's shape, "drop
default_page_size, preserve everything else" IS the read-back equivalence guarantee for the
``fields`` subset (Req 1.4). These tests are pure dict logic — no MySQL, no boto3, no
cross-plane ``sam.*`` import (steering 30/31/36: the Flask plane / its tests do not import the
SAM package; the operational script bridges both planes only at runtime).

Validates: Requirements 7.2, 10.2, 5.4, 1.4 (fields-subset equivalence)
Reference: .kiro/specs/Members/02 - members-config-sam-owned-write-path/
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

# conftest puts backend/ on sys.path, so the operational script imports as a package module.
# Only the PURE helper is exercised here — importing it does not pull in boto3/MySQL.
from scripts.migrate_config_fields_to_sam import shape_config_fields_body


class TestShapeDropsRetiredPageSize:
    """``default_page_size`` is RETIRED — never carried into the SAM body (Req 7.2/25)."""

    def test_shape_removes_default_page_size_when_present(self):
        attrs = {
            "fields": {"club_number": {"key": "club_number", "type": "string"}},
            "overrides": {"person.email": {"required": True}},
            "functional_groups": [
                {"key": "contact", "label": {"nl": "Contact"}, "order": 0}
            ],
            "default_page_size": 100,
        }
        body = shape_config_fields_body(attrs)
        assert "default_page_size" not in body

    def test_shape_removes_default_page_size_even_when_none(self):
        body = shape_config_fields_body(
            {"fields": {}, "overrides": {}, "default_page_size": None}
        )
        assert "default_page_size" not in body

    def test_shape_noop_when_page_size_absent(self):
        attrs = {"fields": {}, "overrides": {}, "functional_groups": []}
        assert shape_config_fields_body(attrs) == attrs


class TestShapePreservesEverythingElse:
    """The migrated overlay maps are carried VERBATIM — equivalence for the fields subset."""

    def test_shape_preserves_fields_overrides_groups_verbatim(self):
        attrs = {
            "fields": {
                "club_number": {
                    "key": "club_number",
                    "type": "string",
                    "required": True,
                },
                "region": {"key": "region", "type": "enum", "choices": ["N", "Z"]},
            },
            "overrides": {"person.email": {"label": {"nl": "E-mail"}, "visible": True}},
            "functional_groups": [{"key": "club", "label": {"nl": "Club"}, "order": 1}],
            "default_page_size": 250,
        }
        body = shape_config_fields_body(attrs)
        assert body["fields"] == attrs["fields"]
        assert body["overrides"] == attrs["overrides"]
        assert body["functional_groups"] == attrs["functional_groups"]

    def test_shape_does_not_mutate_input(self):
        attrs = {"fields": {"a": {"key": "a"}}, "default_page_size": 50}
        before = {"fields": {"a": {"key": "a"}}, "default_page_size": 50}
        shape_config_fields_body(attrs)
        assert attrs == before  # input untouched (new dict returned)

    def test_shape_handles_empty_and_none_input(self):
        assert shape_config_fields_body({}) == {}
        assert shape_config_fields_body(None) == {}


class TestShapeProperties:
    """Property: shaping = identity on the non-retired keys, and default_page_size always gone."""

    @given(
        fields=st.dictionaries(
            st.text(min_size=1, max_size=8),
            st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), max_size=3),
            max_size=4,
        ),
        overrides=st.dictionaries(
            st.text(min_size=1, max_size=8),
            st.dictionaries(st.text(min_size=1, max_size=5), st.booleans(), max_size=3),
            max_size=4,
        ),
        groups=st.lists(
            st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), max_size=2),
            max_size=3,
        ),
        page_size=st.one_of(st.none(), st.integers(), st.booleans()),
    )
    def test_shape_drops_page_size_and_preserves_the_rest(
        self, fields, overrides, groups, page_size
    ):
        attrs = {
            "fields": fields,
            "overrides": overrides,
            "functional_groups": groups,
            "default_page_size": page_size,
        }
        body = shape_config_fields_body(attrs)
        # Invariant 1: the retired key is never present in the SAM body.
        assert "default_page_size" not in body
        # Invariant 2: every other key is preserved verbatim (equivalence for the fields subset).
        assert body == {
            "fields": fields,
            "overrides": overrides,
            "functional_groups": groups,
        }

    @given(
        extra=st.dictionaries(
            st.text(min_size=1, max_size=8).filter(lambda k: k != "default_page_size"),
            st.integers(),
            max_size=5,
        )
    )
    def test_shape_is_idempotent(self, extra):
        attrs = {**extra, "default_page_size": 100}
        once = shape_config_fields_body(attrs)
        twice = shape_config_fields_body(once)
        assert once == twice
