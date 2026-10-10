"""
The **template service** (R2) — CRUD over mail templates + render-with-merge AT SEND TIME,
built behind a **module-agnostic seam** so it extracts to ``sam/shared/templates/`` unchanged
on a second consumer (steering 35, rule 5a + rule of three — do NOT build the shared library
now).

Why a standalone service and not a Members mixin
------------------------------------------------
The sibling analytics-set CRUD is a Members mixin because it reaches member-specific concerns
(the field resolver, scope vocabulary). Templates have NONE of that: a template is a name, a
set of per-language subject + body, and a list of merge-field KEYS. So this service is a plain
class that depends ONLY on two injected PORTS (dependency inversion), carrying no member,
scope, DynamoDB, or S3 knowledge:

- :class:`TemplateMetadataStore` — the on-plane METADATA store (get/list/save/delete of a
  :class:`~sam.members.domain.template.TemplateEntry`). The Members repository
  (:class:`~sam.members.repository.members_repository.DynamoDbMembersRepository`) structurally
  satisfies it (it has exactly these four ``*_template`` methods), but the service never names
  the Members repo — it depends on the Protocol, so a second module can supply its own store.
- :class:`TemplateBodyStore` — the BODY/logo blob store (put/get/delete of the body HTML text
  by its S3 key). The S3-backed implementation is a later task (2.1 defines the key layout via
  :func:`sam.members.repository.table_design.template_body_s3_key`); the service never imports
  boto3. :class:`InMemoryTemplateBodyStore` is provided for tests/dev.

The actual mail-merge is :func:`sam.members.domain.template.render_with_merge` — pure and
module-agnostic. The service orchestrates: on a send it loads the chosen language's body text
through the body store, then merges the per-recipient values into subject + body. The merge
happens ON-PLANE at send time — never in an AI prompt, so member PII is never sent to the AI
adapter (R2).

Layering (steering 35)
----------------------
handler (thin) → THIS service (business logic, storage-agnostic) → ports (metadata store /
body store). The service validates + stamps authoritative identity (``tenant_id`` is never
trusted from a body) and leaves all persistence to the injected ports.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from sam.members.domain.template import (
    TemplateEntry,
    TemplateLanguage,
    TemplateValidationError,
    render_with_merge,
)

__all__ = [
    "InMemoryTemplateBodyStore",
    "RenderedMessage",
    "TemplateBodyStore",
    "TemplateMetadataStore",
    "TemplateNotFound",
    "TemplateService",
]


# ── Ports (the module-agnostic seam) ───────────────────────────────────────────────────


@runtime_checkable
class TemplateMetadataStore(Protocol):
    """The METADATA persistence port for templates (tenant-scoped).

    Exactly the four template methods the Members repository exposes — but named as a Protocol
    so this service depends on the SHAPE, not the Members repo. A second module supplies its
    own store without touching this service. Every method is keyed by ``tenant_id`` (structural
    tenant isolation — Property 1).
    """

    def get_template(self, tenant_id: str, template_id: str) -> TemplateEntry | None: ...

    def list_templates(self, tenant_id: str) -> Sequence[TemplateEntry]: ...

    def save_template(self, tenant_id: str, entry: TemplateEntry) -> TemplateEntry: ...

    def delete_template(self, tenant_id: str, template_id: str) -> None: ...


@runtime_checkable
class TemplateBodyStore(Protocol):
    """The BODY/logo blob store port — the body HTML text keyed by its (S3) object key.

    The service NEVER inlines a body in the metadata item (400 KB item limit); it stores the
    body text here and keeps only the key in the metadata. The production implementation is
    S3-backed (``myadmin-shared``, tenant-prefixed per
    :func:`~sam.members.repository.table_design.template_body_s3_key`) and lands in a later
    task; the service depends only on this Protocol so it carries no boto3 dependency.
    """

    def put_body(self, key: str, body_html: str) -> None:
        """Store (or replace) the body HTML text at ``key``."""
        ...

    def get_body(self, key: str) -> str | None:
        """Return the body HTML text at ``key``, or ``None`` if absent."""
        ...

    def delete_body(self, key: str) -> None:
        """Delete the body object at ``key`` (idempotent — absent key is a no-op)."""
        ...


class InMemoryTemplateBodyStore:
    """A dict-backed :class:`TemplateBodyStore` for tests / local dev (no S3, no boto3).

    Faithful to the port surface: ``put_body`` / ``get_body`` / ``delete_body`` over an
    in-memory ``{key: body_html}`` map. The S3-backed production store is a later task; this
    lets the service's CRUD + render be exercised end to end without AWS.
    """

    def __init__(self, initial: Mapping[str, str] | None = None):
        self._bodies: dict[str, str] = dict(initial or {})

    def put_body(self, key: str, body_html: str) -> None:
        if not key:
            raise ValueError("body-store key must be non-empty")
        self._bodies[key] = body_html if isinstance(body_html, str) else str(body_html)

    def get_body(self, key: str) -> str | None:
        return self._bodies.get(key)

    def delete_body(self, key: str) -> None:
        self._bodies.pop(key, None)


# ── Errors ──────────────────────────────────────────────────────────────────────────────


class TemplateNotFound(Exception):
    """Raised when a template is not found for the tenant (→ 404 at the edge)."""

    def __init__(self, tenant_id: str, template_id: str):
        self.tenant_id = tenant_id
        self.template_id = template_id
        super().__init__(f"template {template_id!r} not found for tenant {tenant_id!r}")


# ── Rendered output ─────────────────────────────────────────────────────────────────────


class RenderedMessage:
    """The result of rendering a template for ONE recipient: a merged subject + body.

    A plain value object (not a dataclass to keep this file dependency-light). ``subject`` and
    ``body_html`` have every ``{{ merge_field }}`` resolved from the recipient's values.
    """

    __slots__ = ("body_html", "lang", "subject")

    def __init__(self, *, subject: str, body_html: str, lang: str):
        self.subject = subject
        self.body_html = body_html
        self.lang = lang

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RenderedMessage)
            and other.subject == self.subject
            and other.body_html == self.body_html
            and other.lang == self.lang
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"RenderedMessage(lang={self.lang!r}, subject={self.subject!r}, "
            f"body_html={self.body_html!r})"
        )


# ── The service ─────────────────────────────────────────────────────────────────────────


class TemplateService:
    """CRUD + render-with-merge for mail templates, behind the module-agnostic seam (R2).

    Depends only on the two injected ports (metadata store + body store) — no member, scope,
    DynamoDB, or S3 knowledge — so the whole service extracts to ``sam/shared/templates/``
    unchanged on a second consumer (steering 35). ``tenant_id`` is AUTHORITATIVE on every
    method (never trusted from a body). ``template_id`` is server-chosen (uuid4 hex) on create.

    Args:
        metadata_store: the on-plane metadata persistence port.
        body_store: the body/logo blob store port.
        body_key_builder: a callable ``(tenant_id, template_id, lang) -> s3_key`` that yields
            the body object key for a language. Defaults to
            :func:`~sam.members.repository.table_design.template_body_s3_key` (the canonical
            tenant-prefixed layout from task 2.1), injectable so a second module can key its
            bodies its own way without this service importing the Members repository package.
    """

    def __init__(
        self,
        metadata_store: TemplateMetadataStore,
        body_store: TemplateBodyStore,
        *,
        body_key_builder=None,
    ):
        self._meta = metadata_store
        self._bodies = body_store
        if body_key_builder is None:
            # Default to the canonical layout defined by task 2.1. Imported lazily so the
            # service module itself carries no hard dependency on the repository package (keeps
            # the seam clean for extraction).
            from sam.members.repository.table_design import template_body_s3_key

            body_key_builder = template_body_s3_key
        self._body_key_builder = body_key_builder

    # ── helpers ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _body_key(self, tenant_id: str, template_id: str, lang: str) -> str:
        return self._body_key_builder(tenant_id, template_id, lang)

    @staticmethod
    def _merge_fields_from_body(body_payload: Mapping[str, Mapping[str, Any]]) -> list[str]:
        """Discover the union of ``{{ merge_field }}`` keys across every language body.

        A convenience for ``create`` / ``update`` when the caller does not pass ``merge_fields``
        explicitly: it scans each language's body text so the stored metadata self-describes
        which fields the template uses. First-appearance order, de-duplicated across languages.
        """
        from sam.members.domain.template import merge_placeholders

        seen: list[str] = []
        for variant in body_payload.values():
            body_html = variant.get("body_html", "") if isinstance(variant, Mapping) else ""
            for key in merge_placeholders(body_html):
                if key not in seen:
                    seen.append(key)
        return seen

    @staticmethod
    def _sanitize_lines(raw_lines: Any) -> list[list[str]]:
        """Coerce a label body's ``lines`` to a clean list-of-lists of non-blank field keys.

        Each line is kept as the list of its non-blank string field keys (blanks/non-strings
        dropped); a line that ends up empty is dropped entirely. The result MAY be empty — the
        label-kind path hands it to :meth:`TemplateEntry.validate`, which rejects a label with
        no usable lines (so an all-blank ``lines`` surfaces as a 422, not a silent empty label).
        """
        if not isinstance(raw_lines, (list, tuple)):
            return []
        cleaned: list[list[str]] = []
        for line in raw_lines:
            if not isinstance(line, (list, tuple)):
                continue
            keys = [k.strip() for k in line if isinstance(k, str) and k.strip()]
            if keys:
                cleaned.append(keys)
        return cleaned

    def _serialize(
        self, entry: TemplateEntry, *, include_bodies: bool = False
    ) -> dict[str, Any]:
        """Project a template entry to the JSON-friendly shape the handler returns.

        Carries the metadata only (``template_id`` / ``name`` / ``languages`` /
        ``merge_fields`` / ``logo_asset_ref`` / ``origin`` / ``created_by`` / timestamps);
        ``tenant_id`` is omitted (the caller already knows the tenant context). Body HTML is
        NOT included — it is loaded on demand via :meth:`render_for_recipient`.
        """
        def _variant_dict(variant: Any) -> dict[str, Any]:
            d = dict(variant.to_dict())
            if include_bodies:
                # Resolve the stored body HTML (None -> empty string; the picker leaves the
                # body blank and the user fills it). Loaded only on GET-by-id, not on list.
                d["body_html"] = self._bodies.get_body(variant.s3_body_key) or ""
            return d

        payload: dict[str, Any] = {
            "template_id": entry.template_id,
            "name": entry.name,
            "languages": {
                lang: _variant_dict(variant) for lang, variant in entry.languages.items()
            },
            "merge_fields": list(entry.merge_fields),
            "logo_asset_ref": entry.logo_asset_ref,
            "origin": entry.origin,
            "created_by": entry.created_by,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        # Carry the label-template discriminator + content through serialization (labels
        # sub-spec R-L1). Additive: a mail template (default kind, no lines) projects exactly as
        # before — `kind`/`lines` are emitted only when they carry meaning, so the mail client
        # shape is unchanged. A label template surfaces both so the picker/editor can tell it
        # apart and round-trip its lines.
        if entry.kind != "mail":
            payload["kind"] = entry.kind
        if entry.lines:
            payload["lines"] = [list(line) for line in entry.lines]
        return payload

    def _build_languages(
        self,
        tenant_id: str,
        template_id: str,
        body_payload: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, TemplateLanguage]:
        """Build the ``{lang: TemplateLanguage}`` metadata AND write each body to the body store.

        ``body_payload`` is ``{lang: {"subject": str, "body_html": str}}`` from the caller. For
        each language this computes the canonical body key, writes the body HTML to the body
        store under that key, and records the subject + key in the metadata. The body text
        never lands in the metadata item (only its key).
        """
        languages: dict[str, TemplateLanguage] = {}
        for lang, variant in body_payload.items():
            if not isinstance(variant, Mapping):
                continue
            subject = str(variant.get("subject", "") or "")
            body_html = str(variant.get("body_html", "") or "")
            key = self._body_key(tenant_id, template_id, lang)
            self._bodies.put_body(key, body_html)
            languages[str(lang)] = TemplateLanguage(subject=subject, s3_body_key=key)
        return languages

    # ── list / get ──────────────────────────────────────────────────────────────────

    def list_templates(self, tenant_id: str) -> list[dict[str, Any]]:
        """List the tenant's templates (metadata only), sorted by name for determinism."""
        return [self._serialize(e) for e in self._meta.list_templates(tenant_id)]

    def get_template(self, tenant_id: str, template_id: str) -> dict[str, Any]:
        """Fetch one template's metadata by id (404 if absent)."""
        entry = self._meta.get_template(tenant_id, template_id)
        if entry is None:
            raise TemplateNotFound(tenant_id, template_id)
        # GET-by-id resolves each language's body HTML from the body store so the compose
        # picker can SEED the editable subject + body (R2). list_templates stays metadata-only.
        return self._serialize(entry, include_bodies=True)

    # ── create / update / delete ──────────────────────────────────────────────────────

    def create_template(
        self,
        tenant_id: str,
        body: Mapping[str, Any],
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Create a template for the tenant and write its per-language body text.

        ``tenant_id`` is authoritative (never a body ``tenant_id`` / ``template_id`` —
        verify-before-trust). Generates ``template_id = uuid4().hex`` (server-chosen opaque id).
        Reads ``name``, ``languages`` (``{lang: {subject, body_html}}``), optional
        ``logo_asset_ref``, and optional ``merge_fields`` (defaulting to the union discovered in
        the body text) from the body. Writes each language body to the body store, builds the
        metadata, stamps ``origin='user'`` + ``created_by`` + ``created_at=updated_at=now``,
        validates, persists the metadata, and returns the serialized template.
        """
        payload = dict(body) if isinstance(body, Mapping) else {}
        template_id = uuid.uuid4().hex
        now = self._now()

        kind = payload.get("kind")
        kind = kind if isinstance(kind, str) and kind else "mail"

        if kind == "label":
            # LABEL template (labels sub-spec R-L1): content is `lines`, NOT a mail body — so we
            # do NOT discover merge fields, require `languages`, or write any body-store object.
            # `TemplateEntry.validate()` rejects a label with no usable lines (→ 422).
            lines = self._sanitize_lines(payload.get("lines"))
            logo = payload.get("logo_asset_ref")
            entry = TemplateEntry(
                tenant_id=tenant_id,
                template_id=template_id,
                name=str(payload.get("name", "")),
                languages={},
                merge_fields=(),
                logo_asset_ref=logo if isinstance(logo, str) and logo else None,
                origin="user",
                created_by=created_by or "",
                created_at=now,
                updated_at=now,
                kind="label",
                lines=lines,
            )
            entry.validate()
            saved = self._meta.save_template(tenant_id, entry)
            return self._serialize(saved)

        raw_langs = payload.get("languages")
        body_payload: dict[str, Mapping[str, Any]] = (
            {str(k): v for k, v in raw_langs.items() if isinstance(v, Mapping)}
            if isinstance(raw_langs, Mapping)
            else {}
        )
        languages = self._build_languages(tenant_id, template_id, body_payload)

        merge_fields = payload.get("merge_fields")
        if not isinstance(merge_fields, (list, tuple)):
            merge_fields = self._merge_fields_from_body(body_payload)
        else:
            merge_fields = [str(m) for m in merge_fields if isinstance(m, str) and m.strip()]

        logo = payload.get("logo_asset_ref")
        entry = TemplateEntry(
            tenant_id=tenant_id,
            template_id=template_id,
            name=str(payload.get("name", "")),
            languages=languages,
            merge_fields=merge_fields,
            logo_asset_ref=logo if isinstance(logo, str) and logo else None,
            origin="user",
            created_by=created_by or "",
            created_at=now,
            updated_at=now,
        )
        entry.validate()
        saved = self._meta.save_template(tenant_id, entry)
        return self._serialize(saved)

    def update_template(
        self, tenant_id: str, template_id: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update an existing template's metadata and/or body text (404 if absent).

        Loads the entry within the tenant (Property 1); an absent ``template_id`` raises
        :class:`TemplateNotFound` (→ 404). Merges the body over the existing entry — path
        ``template_id`` + authoritative ``tenant_id`` fix identity, ``created_at`` /
        ``created_by`` / ``origin`` are preserved, ``updated_at`` is bumped. When ``languages``
        is present it REPLACES the language set (writing new bodies to the body store);
        otherwise the existing languages are kept. Returns the serialized template.
        """
        existing = self._meta.get_template(tenant_id, template_id)
        if existing is None:
            raise TemplateNotFound(tenant_id, template_id)

        payload = dict(body) if isinstance(body, Mapping) else {}
        now = self._now()

        name = str(payload["name"]) if "name" in payload else existing.name

        # Resolve the kind: an explicit body `kind` wins, otherwise the stored entry's kind is
        # preserved. A label template persists its `lines` and writes NO mail body.
        raw_kind = payload.get("kind")
        kind = raw_kind if isinstance(raw_kind, str) and raw_kind else existing.kind

        if kind == "label":
            lines = (
                self._sanitize_lines(payload.get("lines"))
                if "lines" in payload
                else [list(line) for line in existing.lines]
            )
            logo = (
                payload.get("logo_asset_ref")
                if "logo_asset_ref" in payload
                else existing.logo_asset_ref
            )
            updated = TemplateEntry(
                tenant_id=tenant_id,  # authoritative — never the body
                template_id=template_id,  # the path is authoritative for identity
                name=name,
                languages={},
                merge_fields=(),
                logo_asset_ref=logo if isinstance(logo, str) and logo else None,
                origin=existing.origin,  # preserved
                created_by=existing.created_by,  # preserved
                created_at=existing.created_at,  # preserved
                updated_at=now,  # bumped
                kind="label",
                lines=lines,
            )
            updated.validate()
            saved = self._meta.save_template(tenant_id, updated)
            return self._serialize(saved)

        if "languages" in payload and isinstance(payload.get("languages"), Mapping):
            body_payload = {
                str(k): v
                for k, v in payload["languages"].items()
                if isinstance(v, Mapping)
            }
            languages = self._build_languages(tenant_id, template_id, body_payload)
            # Recompute merge fields from the new bodies unless the caller overrides them.
            default_merge = self._merge_fields_from_body(body_payload)
        else:
            languages = dict(existing.languages)
            default_merge = list(existing.merge_fields)

        merge_fields = payload.get("merge_fields")
        if isinstance(merge_fields, (list, tuple)):
            merge_fields = [
                str(m) for m in merge_fields if isinstance(m, str) and m.strip()
            ]
        else:
            merge_fields = default_merge

        logo = (
            payload.get("logo_asset_ref")
            if "logo_asset_ref" in payload
            else existing.logo_asset_ref
        )

        updated = TemplateEntry(
            tenant_id=tenant_id,  # authoritative — never the body
            template_id=template_id,  # the path is authoritative for identity
            name=name,
            languages=languages,
            merge_fields=merge_fields,
            logo_asset_ref=logo if isinstance(logo, str) and logo else None,
            origin=existing.origin,  # preserved
            created_by=existing.created_by,  # preserved (original author attribution)
            created_at=existing.created_at,  # preserved
            updated_at=now,  # bumped
        )
        updated.validate()
        saved = self._meta.save_template(tenant_id, updated)
        return self._serialize(saved)

    def delete_template(self, tenant_id: str, template_id: str) -> dict[str, Any]:
        """Delete a template (metadata + every language body). 404 if absent.

        Does a get-first to raise :class:`TemplateNotFound` for an absent id (→ 404), deletes
        each language's body object through the body store, then deletes the metadata item.
        Returns the serialized template that was deleted.
        """
        existing = self._meta.get_template(tenant_id, template_id)
        if existing is None:
            raise TemplateNotFound(tenant_id, template_id)
        for variant in existing.languages.values():
            if variant.s3_body_key:
                self._bodies.delete_body(variant.s3_body_key)
        self._meta.delete_template(tenant_id, template_id)
        return self._serialize(existing)

    # ── render with merge (AT SEND TIME) ──────────────────────────────────────────────

    def render_for_recipient(
        self,
        tenant_id: str,
        template_id: str,
        lang: str,
        merge_values: Mapping[str, Any],
        *,
        default: str = "",
    ) -> RenderedMessage:
        """Render ONE recipient's personalized message from a stored template (R2 mail-merge).

        This is the send-time merge: it loads the template metadata (404 if absent), picks the
        requested ``lang`` (:class:`TemplateValidationError` if the template has no such
        language), loads that language's body text from the body store, and merges
        ``merge_values`` into BOTH the subject and the body via
        :func:`~sam.members.domain.template.render_with_merge`. A ``per_recipient`` send calls
        this once per member with that member's values, so each recipient gets a personalized
        subject + body. The merge is on-plane — member values never leave this path (never an
        AI prompt).

        Args:
            tenant_id: authoritative tenant (Property 1).
            template_id: the stored template.
            lang: the language variant to render (e.g. ``"nl"`` / ``"en"``).
            merge_values: this recipient's ``{field_key: value}`` map.
            default: replacement for an absent / ``None`` placeholder value (default ``""``).

        Returns:
            A :class:`RenderedMessage` with the merged ``subject`` + ``body_html`` for ``lang``.
        """
        entry = self._meta.get_template(tenant_id, template_id)
        if entry is None:
            raise TemplateNotFound(tenant_id, template_id)

        variant = entry.language(lang)
        if variant is None:
            raise TemplateValidationError(
                {
                    "lang": _language_error(lang, sorted(entry.languages.keys())),
                }
            )

        body_html = self._bodies.get_body(variant.s3_body_key)
        if body_html is None:
            # The metadata references a body key with no stored object — a data/ops fault, not a
            # client error. Surface it clearly rather than silently sending an empty body.
            raise TemplateValidationError(
                {
                    "s3_body_key": _missing_body_error(variant.s3_body_key),
                }
            )

        subject = render_with_merge(variant.subject, merge_values, default=default)
        rendered_body = render_with_merge(body_html, merge_values, default=default)
        return RenderedMessage(subject=subject, body_html=rendered_body, lang=lang)


# ── small FieldError factories (kept local to avoid widening the error-codes vocabulary) ──


def _language_error(lang: str, available: list[str]):
    from sam.members.domain.error_codes import TEMPLATE_LANGUAGES, FieldError

    return FieldError(
        code=TEMPLATE_LANGUAGES,
        detail=(
            f"template has no {lang!r} language variant "
            f"(available: {', '.join(available) or 'none'})"
        ),
        params={"requested": lang, "available": available},
    )


def _missing_body_error(key: str):
    from sam.members.domain.error_codes import TEMPLATE_LANGUAGES, FieldError

    return FieldError(
        code=TEMPLATE_LANGUAGES,
        detail=f"no stored body object at key {key!r} (template body is missing)",
        params={"s3_body_key": key},
    )
