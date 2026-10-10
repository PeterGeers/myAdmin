"""
Pure-unit tests for the :class:`TemplateEntry` entity + the module-agnostic merge renderer (R2).

Pin the entity model's validate() / to_item() / from_item() behaviour (mirroring the sibling
``test_analytics_set_entity`` tests) and the pure :func:`render_with_merge` mail-merge used at
send time. The renderer is the heart of R2's "real mail-merge": every recipient's
``{{ field }}`` placeholders are filled from that recipient's values, and an absent value never
leaks a raw placeholder or crashes the send.

Validates: Requirements R2
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

from sam.members.domain.template import (
    TemplateEntry,
    TemplateLanguage,
    TemplateValidationError,
    merge_placeholders,
    render_with_merge,
)


def _lang(subject="Hallo {{first_name}}", key="h-dcn/templates/t1/nl.html"):
    return TemplateLanguage(subject=subject, s3_body_key=key)


def _entry(**overrides):
    base = {
        "tenant_id": "h-dcn",
        "template_id": "t1",
        "name": "Welcome clubblad",
        "languages": {"nl": _lang(), "en": _lang(subject="Hello {{first_name}}",
                                                 key="h-dcn/templates/t1/en.html")},
        "merge_fields": ["first_name"],
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return TemplateEntry(**base)


class TestTemplateEntryValidate:
    def test_valid_entry_passes(self):
        _entry().validate()  # must not raise

    def test_single_language_is_valid(self):
        _entry(languages={"nl": _lang()}).validate()

    def test_empty_merge_fields_is_valid(self):
        # A static template with no merge fields is first-class.
        _entry(merge_fields=[]).validate()

    def test_blank_name_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _entry(name="  ").validate()
        assert "name" in exc.value.errors

    def test_blank_tenant_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _entry(tenant_id="").validate()
        assert "tenant_id" in exc.value.errors

    def test_template_id_with_separator_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _entry(template_id="has#hash").validate()
        assert "template_id" in exc.value.errors

    def test_no_languages_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _entry(languages={}).validate()
        assert "languages" in exc.value.errors

    def test_all_blank_languages_is_invalid(self):
        # A language with a blank body key / subject is unusable; if NONE is usable → invalid.
        with pytest.raises(TemplateValidationError) as exc:
            _entry(languages={"nl": TemplateLanguage(subject="", s3_body_key="")}).validate()
        assert "languages" in exc.value.errors

    def test_non_string_merge_field_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _entry(merge_fields=["ok", 42]).validate()
        assert "merge_fields" in exc.value.errors

    def test_bad_origin_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _entry(origin="imported").validate()
        assert "origin" in exc.value.errors

    def test_origin_defaults_to_user(self):
        assert _entry().origin == "user"

    def test_preset_origin_is_valid(self):
        _entry(origin="preset").validate()


class TestTemplateEntryRoundTrip:
    def test_to_item_carries_the_metadata_shape(self):
        item = _entry(created_by="sub-1", logo_asset_ref="logo-9").to_item()
        assert item["tenant_id"] == "h-dcn"
        assert item["template_id"] == "t1"
        assert item["name"] == "Welcome clubblad"
        assert item["languages"]["nl"]["subject"] == "Hallo {{first_name}}"
        assert item["languages"]["nl"]["s3_body_key"] == "h-dcn/templates/t1/nl.html"
        assert item["merge_fields"] == ["first_name"]
        assert item["logo_asset_ref"] == "logo-9"
        assert item["origin"] == "user"
        assert item["created_by"] == "sub-1"

    def test_to_item_validates_first(self):
        with pytest.raises(TemplateValidationError):
            _entry(name="").to_item()

    def test_from_item_is_inverse_of_to_item(self):
        original = _entry(created_by="sub-1", logo_asset_ref="logo-9")
        rebuilt = TemplateEntry.from_item(original.to_item())
        assert rebuilt == original

    def test_from_item_tolerates_physical_key_attrs(self):
        item = _entry().to_item()
        item["sk"] = "template#t1"  # physical attr the repo adds
        rebuilt = TemplateEntry.from_item(item)
        assert rebuilt.template_id == "t1"
        assert rebuilt.name == "Welcome clubblad"

    def test_from_item_defaults_legacy_fields(self):
        rebuilt = TemplateEntry.from_item(
            {
                "tenant_id": "h-dcn",
                "template_id": "t1",
                "name": "N",
                "languages": {"nl": {"subject": "S", "s3_body_key": "k"}},
            }
        )
        assert rebuilt.origin == "user"
        assert rebuilt.created_by == ""
        assert rebuilt.logo_asset_ref is None
        assert rebuilt.merge_fields == []

    def test_language_accessor(self):
        entry = _entry()
        assert entry.language("nl").subject == "Hallo {{first_name}}"
        assert entry.language("de") is None

    def test_mail_entry_omits_kind_and_lines_in_item(self):
        # Additive guarantee: a mail template (default kind, no lines) serializes EXACTLY as
        # before — the new discriminator / content keys are not emitted for it.
        item = _entry().to_item()
        assert "kind" not in item
        assert "lines" not in item


def _label_entry(**overrides):
    base = {
        "tenant_id": "h-dcn",
        "template_id": "lbl1",
        "name": "Address labels",
        "kind": "label",
        "lines": (("display_name",), ("street",), ("postal_code", "city"), ("country",)),
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return TemplateEntry(**base)


class TestLabelTemplateEntry:
    def test_label_entry_validates_without_languages(self):
        # A label template carries NO mail body — `lines` is its content, `languages` not required.
        _label_entry().validate()

    def test_label_with_no_lines_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _label_entry(lines=()).validate()
        assert "lines" in exc.value.errors

    def test_label_with_only_blank_field_keys_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _label_entry(lines=(("", "  "),)).validate()
        assert "lines" in exc.value.errors

    def test_unknown_kind_is_invalid(self):
        with pytest.raises(TemplateValidationError) as exc:
            _label_entry(kind="sticker").validate()
        assert "kind" in exc.value.errors

    def test_kind_defaults_to_mail(self):
        assert _entry().kind == "mail"

    def test_to_item_carries_kind_and_lines(self):
        item = _label_entry().to_item()
        assert item["kind"] == "label"
        assert item["lines"] == [
            ["display_name"],
            ["street"],
            ["postal_code", "city"],
            ["country"],
        ]

    def test_label_round_trips_through_item(self):
        # The real round-trip contract is the stored item: to_item → from_item → to_item is
        # stable, and the rebuilt entry carries kind + lines. (Direct `==` is avoided here only
        # because `from_item` normalizes merge_fields to a list vs the dataclass's tuple default
        # — a pre-existing, unrelated quirk, not a labels concern.)
        original = _label_entry(merge_fields=[])
        item = original.to_item()
        rebuilt = TemplateEntry.from_item(item)
        assert rebuilt.kind == "label"
        assert rebuilt.lines == original.lines
        assert rebuilt.to_item() == item

    def test_from_item_defaults_kind_mail_and_empty_lines_for_legacy(self):
        # A legacy mail item (no kind / no lines) rebuilds as a mail template unchanged.
        rebuilt = TemplateEntry.from_item(
            {
                "tenant_id": "h-dcn",
                "template_id": "t1",
                "name": "N",
                "languages": {"nl": {"subject": "S", "s3_body_key": "k"}},
            }
        )
        assert rebuilt.kind == "mail"
        assert rebuilt.lines == tuple()


class TestMergePlaceholders:
    def test_discovers_distinct_keys_in_order(self):
        text = "{{first_name}} {{membership_type}} {{first_name}}"
        assert merge_placeholders(text) == ["first_name", "membership_type"]

    def test_tolerates_whitespace_in_braces(self):
        assert merge_placeholders("{{ first_name }}") == ["first_name"]

    def test_empty_or_non_string_yields_empty(self):
        assert merge_placeholders("") == []
        assert merge_placeholders(None) == []


class TestRenderWithMerge:
    def test_fills_present_placeholders(self):
        out = render_with_merge(
            "Dag {{first_name}}, type {{membership_type}}",
            {"first_name": "Ava", "membership_type": "erelid"},
        )
        assert out == "Dag Ava, type erelid"

    def test_whitespace_insensitive_placeholder(self):
        assert render_with_merge("Hi {{ first_name }}", {"first_name": "Ava"}) == "Hi Ava"

    def test_absent_value_renders_default_not_raw_placeholder(self):
        # A missing value must NOT leave a raw {{ }} and must NOT crash.
        assert render_with_merge("Hi {{first_name}}", {}) == "Hi "

    def test_absent_value_uses_custom_default(self):
        assert (
            render_with_merge("Hi {{first_name}}", {}, default="member") == "Hi member"
        )

    def test_none_value_renders_default(self):
        assert render_with_merge("Hi {{first_name}}", {"first_name": None}) == "Hi "

    def test_non_string_value_is_stringified(self):
        assert render_with_merge("N={{count}}", {"count": 3}) == "N=3"

    def test_empty_text_stays_empty(self):
        assert render_with_merge("", {"first_name": "Ava"}) == ""

    def test_none_text_renders_empty(self):
        assert render_with_merge(None, {"first_name": "Ava"}) == ""

    def test_no_placeholders_passthrough(self):
        assert render_with_merge("plain text", {"x": "y"}) == "plain text"
