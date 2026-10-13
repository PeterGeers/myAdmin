"""
Unit tests for s5c Phase-2 tasks 2.2 / 2.3 / 2.4 (Flask/MySQL plane).

- 2.2 / 2.3: the members-parameters definition endpoint serves the config params with the
  composite types (`map<field_def>` for field_overlay, `list<object>` for scope_dimensions,
  plus the nested functional_groups `list<object>`). Phase 2 (R5.1) retired the
  `view_contexts` param/definition.
- 2.4 (Property 7, R4.9): authoritative save-time validation rejects a field_overlay with a
  dangling functional_group (or an invalid overlay), and ACCEPTS a valid one — fail-fast, no
  config corruption.

These are pure Flask-plane tests: the endpoint is exercised via a minimal blueprint-only app
(no auth, no DB); the validator is a pure function (no DB, no mocks).

Reference: .kiro/specs/multi-tenant/s5c-members-runnable-in-spa/design.md (C-SCHEMA / C-VIEW)
"""

import json

import pytest
import flask

from services.members_config_validation import (
    MembersConfigError,
    validate_field_overlay,
    validate_mail_certified,
    validate_mail_domain,
    validate_mail_local_part,
    validate_members_param,
    validate_default_page_size,
    FIXED_FIELD_KEYS,
    CALCULATED_FIELD_KEYS,
)


# ---------------------------------------------------------------------------
# 2.2 / 2.3 — the members-parameters definition endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def config_client():
    """A minimal Flask app with only the public config blueprint (no auth, no DB)."""
    from routes.config_routes import config_bp

    app = flask.Flask(__name__)
    app.register_blueprint(config_bp)
    return app.test_client()


class TestMembersParametersEndpoint:

    def test_members_parameters_responds_without_auth(self, config_client):
        resp = config_client.get("/api/config/members-parameters")
        assert resp.status_code == 200

    def test_members_parameters_returns_three_params_with_composite_types(
        self, config_client
    ):
        resp = config_client.get("/api/config/members-parameters")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

        by_key = {d["key"]: d for d in data}
        # The members.* definition params the typed editor renders (Phase 2 R5.1 retired
        # the `view_contexts` definition).
        assert set(by_key) == {"field_overlay", "scope_dimensions"}
        assert "view_contexts" not in by_key

        # field_overlay is a map<field_def> composite.
        assert by_key["field_overlay"]["type"] == "map<field_def>"
        # scope_dimensions is a list<object> composite.
        assert by_key["scope_dimensions"]["type"] == "list<object>"

        # Each carries the ledger-def language fields (labels + module gate).
        for d in data:
            assert d["module"] == "MEMBERS"
            assert "label_en" in d and "label_nl" in d

    def test_members_parameters_field_overlay_declares_composite_subtypes(
        self, config_client
    ):
        resp = config_client.get("/api/config/members-parameters")
        data = json.loads(resp.data)
        overlay = next(d for d in data if d["key"] == "field_overlay")

        sub = {f["key"]: f for f in overlay["object_fields"]}
        # functional_groups catalog is a nested list<object>.
        assert sub["functional_groups"]["type"] == "list<object>"
        # fields + fixed_overrides are map<field_def>, each carrying a field_def with
        # a functional_group sub-field (R4.9).
        assert sub["fields"]["type"] == "map<field_def>"
        assert sub["fixed_overrides"]["type"] == "map<field_def>"
        field_def_keys = {f["key"] for f in sub["fields"]["field_def"]}
        assert "functional_group" in field_def_keys


# ---------------------------------------------------------------------------
# 2.4 — field_overlay save validation (reuse of _reject_invalid_overlay semantics)
# ---------------------------------------------------------------------------


class TestFieldOverlayValidation:

    def test_validate_field_overlay_valid_overlay_accepts(self):
        overlay = {
            "functional_groups": [
                {"key": "motor", "label_en": "Motor", "order": 1},
            ],
            "fields": {
                "motor_brand": {
                    "type": "string",
                    "label_en": "Motor brand",
                    "functional_group": "motor",
                }
            },
            "fixed_overrides": {
                "personal.street": {"functional_group": "motor"},
            },
        }
        # Should not raise.
        validate_field_overlay(overlay)

    def test_validate_field_overlay_dangling_functional_group_raises(self):
        overlay = {
            "functional_groups": [
                {"key": "motor", "label_en": "Motor", "order": 1},
            ],
            "fields": {
                "motor_brand": {
                    "type": "string",
                    "functional_group": "does_not_exist",
                }
            },
        }
        with pytest.raises(MembersConfigError) as exc:
            validate_field_overlay(overlay)
        assert "overlay.motor_brand" in exc.value.reasons

    def test_validate_field_overlay_override_dangling_group_raises(self):
        overlay = {
            "functional_groups": [{"key": "address", "label_en": "Address", "order": 1}],
            "fixed_overrides": {
                "personal.street": {"functional_group": "nope"},
            },
        }
        with pytest.raises(MembersConfigError) as exc:
            validate_field_overlay(overlay)
        assert "personal.street" in exc.value.reasons

    def test_validate_field_overlay_unknown_override_target_raises(self):
        overlay = {"fixed_overrides": {"personal.not_a_field": {"visible": False}}}
        with pytest.raises(MembersConfigError):
            validate_field_overlay(overlay)

    def test_validate_field_overlay_variable_key_collides_raises(self):
        overlay = {"fields": {"email": {"type": "string"}}}
        with pytest.raises(MembersConfigError) as exc:
            validate_field_overlay(overlay)
        assert "overlay.email" in exc.value.reasons

    def test_validate_field_overlay_loosen_required_raises(self):
        overlay = {"fixed_overrides": {"personal.email": {"required": False}}}
        with pytest.raises(MembersConfigError):
            validate_field_overlay(overlay)

    def test_validate_field_overlay_enum_without_choices_raises(self):
        overlay = {"fields": {"blood_type": {"type": "enum"}}}
        with pytest.raises(MembersConfigError):
            validate_field_overlay(overlay)

    def test_validate_field_overlay_empty_catalog_skips_group_check(self):
        # No functional_groups catalog → group references use base defaults (no check).
        overlay = {"fields": {"motor_brand": {"type": "string", "functional_group": "x"}}}
        validate_field_overlay(overlay)  # should not raise


# ---------------------------------------------------------------------------
# mail/0.1 — mail config save validation (R4 / §5f: per-tenant From + cert gate)
# ---------------------------------------------------------------------------


class TestMailDomainValidation:

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_validate_mail_domain_blank_accepts(self, value):
        # Optional param — unset/blank is accepted (From simply can't be composed yet).
        validate_mail_domain(value)

    @pytest.mark.parametrize(
        "value", ["h-dcn.nl", "example.com", "sub.example.co.uk", "a.io"]
    )
    def test_validate_mail_domain_bare_domain_accepts(self, value):
        validate_mail_domain(value)

    def test_validate_mail_domain_trims_whitespace(self):
        validate_mail_domain("  h-dcn.nl  ")  # surrounding whitespace tolerated

    @pytest.mark.parametrize(
        "value",
        [
            "noreply@h-dcn.nl",      # has "@" (an address, not a bare domain)
            "https://h-dcn.nl",      # has a scheme
            "h-dcn.nl/path",         # has a path
            "localhost",             # no TLD label
            "h dcn.nl",              # whitespace inside
            "-bad.nl",               # label starts with a hyphen
            "bad-.nl",               # label ends with a hyphen
            "example.123",           # non-alphabetic TLD
        ],
    )
    def test_validate_mail_domain_malformed_raises(self, value):
        with pytest.raises(MembersConfigError) as exc:
            validate_mail_domain(value)
        assert "mail_domain" in exc.value.reasons

    def test_validate_mail_domain_non_string_raises(self):
        with pytest.raises(MembersConfigError) as exc:
            validate_mail_domain(123)
        assert "mail_domain" in exc.value.reasons


class TestMailLocalPartValidation:

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_validate_mail_local_part_blank_accepts(self, value):
        # Optional param — unset/blank defers to the schema default ("noreply").
        validate_mail_local_part(value)

    @pytest.mark.parametrize(
        "value", ["noreply", "info", "onderhoud", "no-reply", "a.b+c"]
    )
    def test_validate_mail_local_part_token_accepts(self, value):
        validate_mail_local_part(value)

    @pytest.mark.parametrize(
        "value",
        [
            "info@h-dcn.nl",   # has "@"
            "no reply",         # whitespace inside
            "bad\tpart",       # whitespace (tab) inside
        ],
    )
    def test_validate_mail_local_part_invalid_raises(self, value):
        with pytest.raises(MembersConfigError) as exc:
            validate_mail_local_part(value)
        assert "mail_local_part" in exc.value.reasons

    def test_validate_mail_local_part_non_string_raises(self):
        with pytest.raises(MembersConfigError) as exc:
            validate_mail_local_part(42)
        assert "mail_local_part" in exc.value.reasons


class TestMailCertifiedValidation:

    @pytest.mark.parametrize("value", [True, False, None])
    def test_validate_mail_certified_bool_or_none_accepts(self, value):
        # Real bool (either way) or unset (None → gate fails closed) is accepted.
        validate_mail_certified(value)

    @pytest.mark.parametrize("value", ["true", "false", 1, 0, "yes"])
    def test_validate_mail_certified_non_bool_raises(self, value):
        # Fail-closed gate: an ambiguous truthy string must never be stored as certified.
        with pytest.raises(MembersConfigError) as exc:
            validate_mail_certified(value)
        assert "mail_certified" in exc.value.reasons


# ---------------------------------------------------------------------------
# Phase 2 step (a) — default_page_size save validation (R2.1, R2.6)
# ---------------------------------------------------------------------------


class TestDefaultPageSizeValidation:
    """`members.default_page_size`: an optional positive-int tenant DEFAULT (not a view object)."""

    def test_validate_default_page_size_none_accepts(self):
        # Optional param — unset defers to the table toolkit's own default.
        validate_default_page_size(None)

    @pytest.mark.parametrize("value", [1, 10, 25, 50, 100, 1000])
    def test_validate_default_page_size_positive_int_accepts(self, value):
        validate_default_page_size(value)  # should not raise

    @pytest.mark.parametrize("value", [0, -1, -25])
    def test_validate_default_page_size_non_positive_raises(self, value):
        with pytest.raises(MembersConfigError) as exc:
            validate_default_page_size(value)
        assert "default_page_size" in exc.value.reasons

    @pytest.mark.parametrize("value", [True, False])
    def test_validate_default_page_size_bool_raises(self, value):
        # bool is an int subclass — reject so True/False is never stored as 1/0.
        with pytest.raises(MembersConfigError) as exc:
            validate_default_page_size(value)
        assert "default_page_size" in exc.value.reasons

    @pytest.mark.parametrize("value", [25.0, "25", "fifty", [25], {"size": 25}])
    def test_validate_default_page_size_non_int_raises(self, value):
        with pytest.raises(MembersConfigError) as exc:
            validate_default_page_size(value)
        assert "default_page_size" in exc.value.reasons


# ---------------------------------------------------------------------------
# 2.4 — dispatch entry point
# ---------------------------------------------------------------------------


class TestValidateMembersParamDispatch:

    def test_validate_members_param_field_overlay_dispatches(self):
        overlay = {
            "functional_groups": [{"key": "g", "label_en": "G"}],
            "fields": {"x": {"type": "string", "functional_group": "missing"}},
        }
        with pytest.raises(MembersConfigError):
            validate_members_param("field_overlay", overlay)

    def test_validate_members_param_scope_dimensions_is_noop(self):
        # scope_dimensions has no cross-reference rule here → accepted as-is.
        validate_members_param("scope_dimensions", [{"key": "region", "enabled": True}])

    def test_validate_members_param_mail_domain_dispatches(self):
        validate_members_param("mail_domain", "h-dcn.nl")  # valid → no raise
        with pytest.raises(MembersConfigError):
            validate_members_param("mail_domain", "noreply@h-dcn.nl")

    def test_validate_members_param_mail_local_part_dispatches(self):
        validate_members_param("mail_local_part", "info")  # valid → no raise
        with pytest.raises(MembersConfigError):
            validate_members_param("mail_local_part", "info@h-dcn.nl")

    def test_validate_members_param_mail_certified_dispatches(self):
        validate_members_param("mail_certified", True)  # valid → no raise
        with pytest.raises(MembersConfigError):
            validate_members_param("mail_certified", "true")

    def test_validate_members_param_default_page_size_dispatches(self):
        validate_members_param("default_page_size", 25)   # valid → no raise
        validate_members_param("default_page_size", None)  # optional → no raise
        with pytest.raises(MembersConfigError):
            validate_members_param("default_page_size", 0)

    def test_validate_members_param_unknown_key_is_noop(self):
        # A key with no save-time rule is accepted as-is (no raise).
        validate_members_param("mail_enabled", True)

    def test_validate_members_param_base_key_sets_match_contract(self):
        # Guardrail: the transcribed base key sets stay non-empty and disjoint.
        assert FIXED_FIELD_KEYS
        assert CALCULATED_FIELD_KEYS
        assert not (FIXED_FIELD_KEYS & CALCULATED_FIELD_KEYS)

    def test_calculated_field_keys_match_sam_source_of_truth(self):
        # Drift guard (Phase 0 step 1): this Flask transcription MUST mirror all nine
        # entries of sam/members/domain/calculated_fields.CALCULATED_FIELDS. The two
        # planes are intentionally not import-coupled (see the module docstring), so the
        # canonical set is pinned here as a literal — if a calculated field is added or
        # renamed in the SAM registry, update both the transcription and this assertion.
        assert CALCULATED_FIELD_KEYS == frozenset(
            {
                "personal.display_name",
                "personal.age",
                "personal.birthday",
                "personal.birth_day",
                "personal.birth_month",
                "personal.birth_year",
                "personal.birth_quarter",
                "membership.years_member",
                "membership.application_year",
            }
        )
