"""
SAM pytest for the :class:`TemplateService` (R2) — CRUD + render-with-merge AT SEND TIME.

Phase 2 testing (tasks.md): "SAM pytest for the template service (merge render) ...". These
exercise the service through its two injected ports (an in-memory metadata store + the shipped
:class:`InMemoryTemplateBodyStore`), with NO AWS/boto3 — the whole point of the module-agnostic
seam (steering 35). The merge-render case is the heart of R2: a per-recipient send renders ONE
recipient's personalized subject + body, and member values stay on-plane (never an AI prompt).

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
)
from sam.members.domain.template_service import (
    InMemoryTemplateBodyStore,
    RenderedMessage,
    TemplateMetadataStore,
    TemplateNotFound,
    TemplateService,
)


class InMemoryMetadataStore:
    """A tiny tenant-scoped in-memory :class:`TemplateMetadataStore` for tests.

    Keyed by ``(tenant_id, template_id)`` so cross-tenant items are structurally separate —
    the same isolation the real repository's partition key enforces.
    """

    def __init__(self):
        self._store: dict[tuple, TemplateEntry] = {}

    def get_template(self, tenant_id, template_id):
        return self._store.get((tenant_id, template_id))

    def list_templates(self, tenant_id):
        entries = [e for (t, _), e in self._store.items() if t == tenant_id]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    def save_template(self, tenant_id, entry):
        self._store[(tenant_id, entry.template_id)] = entry
        return entry

    def delete_template(self, tenant_id, template_id):
        self._store.pop((tenant_id, template_id), None)


@pytest.fixture()
def body_store() -> InMemoryTemplateBodyStore:
    return InMemoryTemplateBodyStore()


@pytest.fixture()
def meta_store() -> InMemoryMetadataStore:
    return InMemoryMetadataStore()


@pytest.fixture()
def service(meta_store, body_store) -> TemplateService:
    return TemplateService(meta_store, body_store)


def _create_body():
    return {
        "name": "Welcome clubblad",
        "languages": {
            "nl": {
                "subject": "Dag {{first_name}}",
                "body_html": "<p>Beste {{first_name}}, type {{membership_type}}.</p>",
            },
            "en": {
                "subject": "Hi {{first_name}}",
                "body_html": "<p>Dear {{first_name}}, type {{membership_type}}.</p>",
            },
        },
    }


class TestTemplateServiceProtocol:
    def test_in_memory_meta_store_satisfies_the_port(self, meta_store):
        assert isinstance(meta_store, TemplateMetadataStore)


class TestTemplateServiceCrud:
    def test_create_stores_metadata_and_bodies(self, service, body_store):
        result = service.create_template("h-dcn", _create_body(), created_by="sub-1")
        tid = result["template_id"]
        assert result["name"] == "Welcome clubblad"
        assert result["origin"] == "user"
        assert result["created_by"] == "sub-1"
        # merge fields auto-discovered from the body text (union across languages).
        assert set(result["merge_fields"]) == {"first_name", "membership_type"}
        # Body text lives in the body store, keyed by the metadata's s3_body_key — never inline.
        nl_key = result["languages"]["nl"]["s3_body_key"]
        assert tid in nl_key and "templates" in nl_key
        assert "Beste {{first_name}}" in body_store.get_body(nl_key)

    def test_get_resolves_body_html_for_the_compose_picker(self, service):
        # GET-by-id MUST resolve each language's body HTML from the body store so the compose
        # picker can seed the editable subject + body (R2). (Returning metadata-only was the
        # bug that left the compose body empty + the send button disabled.)
        tid = service.create_template("h-dcn", _create_body())["template_id"]
        got = service.get_template("h-dcn", tid)
        assert got["template_id"] == tid
        nl = got["languages"]["nl"]
        assert nl["subject"] == "Dag {{first_name}}"
        assert "s3_body_key" in nl
        assert "Beste {{first_name}}" in nl["body_html"]  # body resolved, not just the key

    def test_list_stays_metadata_only_no_body(self, service):
        # list_templates is the cheap metadata path (picker labels only) — it must NOT load
        # bodies from the store. Only GET-by-id resolves body_html.
        service.create_template("h-dcn", _create_body())
        listed = service.list_templates("h-dcn")
        assert listed, "expected at least one template"
        assert "body_html" not in listed[0]["languages"]["nl"]

    def test_get_absent_raises_not_found(self, service):
        with pytest.raises(TemplateNotFound):
            service.get_template("h-dcn", "nope")

    def test_list_is_tenant_scoped_and_sorted(self, service):
        service.create_template("h-dcn", {**_create_body(), "name": "Zeta"})
        service.create_template("h-dcn", {**_create_body(), "name": "Alpha"})
        service.create_template("other", {**_create_body(), "name": "Alpha"})
        names = [t["name"] for t in service.list_templates("h-dcn")]
        assert names == ["Alpha", "Zeta"]  # sorted, and "other" tenant excluded

    def test_update_replaces_languages_and_bumps_updated_at(self, service, body_store):
        created = service.create_template("h-dcn", _create_body())
        tid = created["template_id"]
        updated = service.update_template(
            "h-dcn",
            tid,
            {
                "name": "Renamed",
                "languages": {
                    "nl": {"subject": "Hoi {{first_name}}", "body_html": "<p>Nieuw {{first_name}}</p>"}
                },
            },
        )
        assert updated["name"] == "Renamed"
        assert set(updated["languages"].keys()) == {"nl"}  # replaced the language set
        assert updated["created_at"] == created["created_at"]  # preserved
        assert updated["updated_at"] >= created["updated_at"]  # bumped
        nl_key = updated["languages"]["nl"]["s3_body_key"]
        assert "Nieuw {{first_name}}" in body_store.get_body(nl_key)

    def test_update_absent_raises_not_found(self, service):
        with pytest.raises(TemplateNotFound):
            service.update_template("h-dcn", "nope", {"name": "x"})

    def test_delete_removes_metadata_and_bodies(self, service, body_store):
        created = service.create_template("h-dcn", _create_body())
        tid = created["template_id"]
        nl_key = created["languages"]["nl"]["s3_body_key"]
        assert body_store.get_body(nl_key) is not None
        service.delete_template("h-dcn", tid)
        assert body_store.get_body(nl_key) is None
        with pytest.raises(TemplateNotFound):
            service.get_template("h-dcn", tid)

    def test_delete_absent_raises_not_found(self, service):
        with pytest.raises(TemplateNotFound):
            service.delete_template("h-dcn", "nope")

    def test_create_invalid_body_raises_validation(self, service):
        # No languages → invalid (a template with no usable body is unsendable).
        with pytest.raises(TemplateValidationError):
            service.create_template("h-dcn", {"name": "No body", "languages": {}})


def _label_body():
    return {
        "name": "Member address labels",
        "kind": "label",
        "lines": [["display_name"], ["street"], ["postal_code", "city"]],
    }


class TestTemplateServiceLabelCrud:
    """Label-template CRUD (labels sub-spec R-L1): kind + lines through the SAME store.

    A label template carries NO mail body — no `languages`, no merge-field discovery, no
    body-store writes. Create/get/list round-trip its `kind` and `lines`.

    Validates: Requirements R-L1
    """

    def test_create_label_persists_kind_and_lines_no_bodies(self, service, body_store):
        result = service.create_template("h-dcn", _label_body(), created_by="sub-1")
        assert result["kind"] == "label"
        assert result["lines"] == [["display_name"], ["street"], ["postal_code", "city"]]
        # A label has no mail body → no languages, no merge fields.
        assert result["languages"] == {}
        assert result["merge_fields"] == []
        assert result["origin"] == "user"
        assert result["created_by"] == "sub-1"
        # No body-store writes for a label template (it has no language bodies).
        assert body_store._bodies == {}

    def test_get_label_returns_kind_and_lines(self, service):
        tid = service.create_template("h-dcn", _label_body())["template_id"]
        got = service.get_template("h-dcn", tid)
        assert got["template_id"] == tid
        assert got["kind"] == "label"
        assert got["lines"] == [["display_name"], ["street"], ["postal_code", "city"]]
        assert got["languages"] == {}

    def test_list_surfaces_label_kind_and_lines(self, service):
        service.create_template("h-dcn", _label_body())
        listed = service.list_templates("h-dcn")
        assert len(listed) == 1
        assert listed[0]["kind"] == "label"
        assert listed[0]["lines"] == [["display_name"], ["street"], ["postal_code", "city"]]

    def test_create_label_sanitizes_blank_keys_and_lines(self, service):
        # Blank field keys dropped from a line; a line left empty is dropped entirely.
        result = service.create_template(
            "h-dcn",
            {
                "name": "Sanitized",
                "kind": "label",
                "lines": [["display_name", "  "], ["   "], ["postal_code", "", "city"]],
            },
        )
        assert result["lines"] == [["display_name"], ["postal_code", "city"]]

    def test_create_label_with_no_usable_lines_is_rejected(self, service):
        # Empty / all-blank lines → nothing usable → validation error (→ 422 at the edge).
        with pytest.raises(TemplateValidationError):
            service.create_template(
                "h-dcn", {"name": "Empty", "kind": "label", "lines": [["  "], []]}
            )
        with pytest.raises(TemplateValidationError):
            service.create_template(
                "h-dcn", {"name": "No lines", "kind": "label", "lines": []}
            )

    def test_update_label_lines_preserves_attribution_and_bumps_updated_at(self, service):
        created = service.create_template("h-dcn", _label_body(), created_by="sub-1")
        tid = created["template_id"]
        updated = service.update_template(
            "h-dcn",
            tid,
            {"lines": [["display_name"], ["country"]]},
        )
        assert updated["kind"] == "label"
        assert updated["lines"] == [["display_name"], ["country"]]
        assert updated["created_by"] == "sub-1"  # preserved
        assert updated["created_at"] == created["created_at"]  # preserved
        assert updated["origin"] == created["origin"]  # preserved
        assert updated["updated_at"] >= created["updated_at"]  # bumped

    def test_update_label_does_not_write_mail_bodies(self, service, body_store):
        tid = service.create_template("h-dcn", _label_body())["template_id"]
        service.update_template("h-dcn", tid, {"lines": [["display_name"]]})
        assert body_store._bodies == {}  # a label update never touches the body store


class TestTemplateServiceRenderWithMerge:
    def test_render_fills_per_recipient_values_in_subject_and_body(self, service):
        tid = service.create_template("h-dcn", _create_body())["template_id"]
        rendered = service.render_for_recipient(
            "h-dcn",
            tid,
            "nl",
            {"first_name": "Ava", "membership_type": "erelid"},
        )
        assert isinstance(rendered, RenderedMessage)
        assert rendered.lang == "nl"
        assert rendered.subject == "Dag Ava"
        assert rendered.body_html == "<p>Beste Ava, type erelid.</p>"

    def test_render_two_recipients_personalizes_each(self, service):
        tid = service.create_template("h-dcn", _create_body())["template_id"]
        a = service.render_for_recipient("h-dcn", tid, "en", {"first_name": "Ava", "membership_type": "lid"})
        b = service.render_for_recipient("h-dcn", tid, "en", {"first_name": "Ben", "membership_type": "erelid"})
        assert a.body_html == "<p>Dear Ava, type lid.</p>"
        assert b.body_html == "<p>Dear Ben, type erelid.</p>"

    def test_render_absent_merge_value_does_not_leak_placeholder(self, service):
        tid = service.create_template("h-dcn", _create_body())["template_id"]
        rendered = service.render_for_recipient("h-dcn", tid, "nl", {"first_name": "Ava"})
        # membership_type missing → filled with the default (""), never a raw {{ }}.
        assert "{{" not in rendered.body_html
        assert rendered.body_html == "<p>Beste Ava, type .</p>"

    def test_render_absent_template_raises_not_found(self, service):
        with pytest.raises(TemplateNotFound):
            service.render_for_recipient("h-dcn", "nope", "nl", {})

    def test_render_missing_language_raises_validation(self, service):
        tid = service.create_template("h-dcn", _create_body())["template_id"]
        with pytest.raises(TemplateValidationError) as exc:
            service.render_for_recipient("h-dcn", tid, "de", {})
        assert "lang" in exc.value.errors

    def test_render_missing_body_object_raises_validation(self, service, meta_store):
        # Metadata references a body key with no stored object (ops/data fault) → clear error.
        entry = TemplateEntry(
            tenant_id="h-dcn",
            template_id="orphan",
            name="Orphan",
            languages={
                "nl": TemplateLanguage(
                    subject="S {{first_name}}",
                    s3_body_key="h-dcn/templates/orphan/nl.html",
                )
            },
            merge_fields=["first_name"],
        )
        meta_store.save_template("h-dcn", entry)
        with pytest.raises(TemplateValidationError) as exc:
            service.render_for_recipient("h-dcn", "orphan", "nl", {"first_name": "Ava"})
        assert "s3_body_key" in exc.value.errors
