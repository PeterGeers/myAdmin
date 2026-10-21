"""Unit tests for the Task 5.5 ``config#mail`` SAM migration script's PURE logic.

Paired test for ``backend/scripts/migrate_config_mail_to_sam.py`` (spec 02 Task 5.5,
change-with-tests contract, steering 30/34). Covers the bug-prone pure part —
``shape_config_mail_body`` — which encodes the migration invariant for the mail leg:

    ``build_config_mail_row`` already produces the EXACT shape the ``MembersProjectionReader``
    mail accessors read back (R1.4). So, unlike the scope shaper (which NORMALIZES a single
    ``dimensions`` key), the mail shaper only needs to return a NEW, non-aliasing shallow copy
    of the builder's attributes — carrying ``mail_enabled`` / ``mail_local_part`` /
    ``mail_certified`` always and ``mail_domain`` / ``mail_reply_to_default`` / ``consent_notice``
    only when authored — WITHOUT mutating the builder's row.

These tests are pure dict logic — no MySQL, no boto3, no cross-plane ``sam.*`` import (steering
30/31/36: the Flask plane / its tests do not import the SAM package; the operational script
bridges both planes only at runtime).

Validates: Requirements 1.4, 10.2, 5.1 (mail-subset equivalence; reply-to-default is net-new)
Reference: .kiro/specs/Members/02 - members-config-sam-owned-write-path/
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

# conftest puts backend/ on sys.path, so the operational script imports as a package module.
# Only the PURE helper is exercised here — importing it does not pull in boto3/MySQL.
from scripts.migrate_config_mail_to_sam import shape_config_mail_body


class TestShapeCarriesBuilderAttributes:
    """The shaped body is the builder's attributes verbatim (already the reader's shape)."""

    def test_shape_carries_full_authored_row_verbatim(self):
        attrs = {
            "mail_enabled": True,
            "mail_local_part": "info",
            "mail_certified": True,
            "mail_domain": "example.org",
            "mail_reply_to_default": "replies@example.org",
            "application_scope_copy": False,
        }
        body = shape_config_mail_body(attrs)
        assert body == attrs

    def test_shape_carries_fail_closed_minimal_row(self):
        # An un-authored tenant projects a fail-closed row — carried verbatim, nothing added.
        attrs = {
            "mail_enabled": False,
            "mail_local_part": "noreply",
            "mail_certified": False,
            "application_scope_copy": False,
        }
        body = shape_config_mail_body(attrs)
        assert body == attrs
        # No fabricated optional attributes (domain / reply-to / consent notice stay absent).
        assert "mail_domain" not in body
        assert "mail_reply_to_default" not in body
        assert "consent_notice" not in body

    def test_shape_does_not_fabricate_reply_to_default(self):
        # Task 5.1: mail_reply_to_default is SAM-only net-new; the shaper never invents one.
        body = shape_config_mail_body(
            {"mail_enabled": True, "mail_local_part": "noreply", "mail_certified": True}
        )
        assert "mail_reply_to_default" not in body


class TestShapeEmptyIsValid:
    """Empty / None attributes → an empty dict (never raises)."""

    def test_shape_none_attrs_is_empty_dict(self):
        assert shape_config_mail_body(None) == {}

    def test_shape_empty_attrs_is_empty_dict(self):
        assert shape_config_mail_body({}) == {}


class TestShapeNeverMutatesInput:
    """The shaper returns a NEW dict — the builder's row is untouched (non-aliasing)."""

    def test_shape_does_not_mutate_the_input_dict(self):
        attrs = {"mail_enabled": True, "mail_local_part": "info"}
        before = {k: v for k, v in attrs.items()}
        shape_config_mail_body(attrs)
        assert attrs == before

    def test_shape_result_is_a_new_object(self):
        attrs = {"mail_enabled": True}
        body = shape_config_mail_body(attrs)
        assert body == attrs
        assert body is not attrs  # a copy, so later mutation can't alias back


class TestShapeProperty:
    """Property: the result is ALWAYS a dict equal to the input's contents and never raises."""

    @given(
        st.one_of(
            st.none(),
            st.dictionaries(
                st.sampled_from(
                    [
                        "mail_enabled",
                        "mail_certified",
                        "mail_local_part",
                        "mail_domain",
                        "mail_reply_to_default",
                        "application_scope_copy",
                    ]
                ),
                st.one_of(st.booleans(), st.text(max_size=12)),
                max_size=6,
            ),
        )
    )
    def test_result_is_always_a_faithful_dict_copy(self, attrs):
        body = shape_config_mail_body(attrs)
        assert isinstance(body, dict)
        assert body == (attrs or {})
        # Always a new object when a dict was supplied (non-aliasing guarantee).
        if attrs is not None:
            assert body is not attrs
