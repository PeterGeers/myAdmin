"""
Unit tests for s5c Phase-2 tasks 2.2 / 2.3 / 2.4 (Flask/MySQL plane).

- 2.2 / 2.3: the members-parameters definition endpoint serves the three params with the
  composite types (`map<field_def>` for field_overlay, `list<object>` for scope_dimensions
  and view_contexts, plus the nested functional_groups `list<object>`).
- 2.4 (Property 7, R5.1a / R4.9): authoritative save-time validation rejects a view_contexts
  referencing an unresolvable field_key and a field_overlay with a dangling functional_group
  (or an invalid overlay), and ACCEPTS a valid one — fail-fast, no config corruption.

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
    validate_view_contexts,
    validate_members_param,
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
        # All three members.* params are present.
        assert set(by_key) == {"field_overlay", "scope_dimensions", "view_contexts"}

        # field_overlay is a map<field_def> composite.
        assert by_key["field_overlay"]["type"] == "map<field_def>"
        # scope_dimensions and view_contexts are list<object> composites.
        assert by_key["scope_dimensions"]["type"] == "list<object>"
        assert by_key["view_contexts"]["type"] == "list<object>"

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
# 2.4 — view_contexts save validation (R5.1a, Property 7)
# ---------------------------------------------------------------------------


class TestViewContextsValidation:

    def test_validate_view_contexts_valid_context_accepts(self):
        contexts = [
            {
                "key": "overview",
                "columns": ["member_number", "email", "status"],
                "filterable_columns": ["status"],
                "default_sort": {"field": "last_name", "direction": "asc"},
            }
        ]
        validate_view_contexts(contexts)  # all base keys resolve

    def test_validate_view_contexts_unresolvable_field_key_raises(self):
        contexts = [{"key": "overview", "columns": ["member_number", "not_a_field"]}]
        with pytest.raises(MembersConfigError) as exc:
            validate_view_contexts(contexts)
        assert any("not_a_field" in k for k in exc.value.reasons)

    def test_validate_view_contexts_calculated_field_resolves(self):
        contexts = [{"key": "c", "columns": ["display_name", "age", "years_member"]}]
        validate_view_contexts(contexts)  # calculated fields resolve

    def test_validate_view_contexts_overlay_field_resolves(self):
        overlay = {"fields": {"motor_brand": {"type": "string"}}}
        contexts = [{"key": "c", "columns": ["member_number", "motor_brand"]}]
        validate_view_contexts(contexts, field_overlay=overlay)

    def test_validate_view_contexts_scope_dimension_key_resolves(self):
        scope = [{"key": "region", "enabled": True, "values": ["A", "B"]}]
        contexts = [{"key": "c", "columns": ["member_number", "region"]}]
        validate_view_contexts(contexts, scope_dimensions=scope)

    def test_validate_view_contexts_unresolvable_overlay_field_still_raises(self):
        overlay = {"fields": {"motor_brand": {"type": "string"}}}
        contexts = [{"key": "c", "columns": ["motor_brand", "ghost_field"]}]
        with pytest.raises(MembersConfigError) as exc:
            validate_view_contexts(contexts, field_overlay=overlay)
        assert any("ghost_field" in k for k in exc.value.reasons)

    def test_validate_view_contexts_default_sort_field_validated(self):
        contexts = [{"key": "c", "columns": ["email"], "default_sort": {"field": "ghost"}}]
        with pytest.raises(MembersConfigError):
            validate_view_contexts(contexts)

    def test_validate_view_contexts_empty_list_accepts(self):
        validate_view_contexts([])  # empty-is-valid


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
# 2.4 — dispatch entry point
# ---------------------------------------------------------------------------


class TestValidateMembersParamDispatch:

    def test_validate_members_param_view_contexts_uses_sibling_overlay(self):
        overlay = {"fields": {"motor_brand": {"type": "string"}}}
        contexts = [{"key": "c", "columns": ["motor_brand"]}]
        # With the sibling overlay, motor_brand resolves.
        validate_members_param(
            "view_contexts", contexts, sibling_field_overlay=overlay
        )

    def test_validate_members_param_view_contexts_without_sibling_raises(self):
        contexts = [{"key": "c", "columns": ["motor_brand"]}]
        with pytest.raises(MembersConfigError):
            validate_members_param("view_contexts", contexts)

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

    def test_validate_members_param_unknown_key_is_noop(self):
        # A key with no save-time rule is accepted as-is (no raise).
        validate_members_param("mail_enabled", True)

    def test_validate_members_param_base_key_sets_match_contract(self):
        # Guardrail: the transcribed base key sets stay non-empty and disjoint.
        assert FIXED_FIELD_KEYS
        assert CALCULATED_FIELD_KEYS
        assert not (FIXED_FIELD_KEYS & CALCULATED_FIELD_KEYS)
