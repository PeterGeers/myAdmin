"""
The tenant-scoped **mail-template** entity + the module-agnostic merge renderer (R2).

A template is a tenant-owned, named, bilingual (NL/EN) mail template the Members module
stores so a user does not retype a message each send. This module owns ONLY the
tenant-agnostic pieces that a second module could reuse unchanged (steering 35, rule of
three — extract to ``sam/shared/templates/`` on a second consumer, do NOT build the shared
library now):

- :class:`TemplateEntry` — the **metadata** model (name, per-language subject + S3 body-key
  ref, merge fields, optional logo asset ref, origin, attribution) + its ``validate()`` and the
  storage-shape ``to_item`` / ``from_item`` mapping. Mirrors
  :mod:`sam.members.domain.analytics_set` / :mod:`sam.members.domain.preferred_list`.
- :func:`render_with_merge` — fills a template's ``{{merge_field}}`` placeholders from a
  per-recipient value map, AT SEND TIME. Pure, storage-agnostic, and free of any
  member-specific logic (it operates on strings + a plain mapping), so it is reusable by any
  module and never leaks member PII into anything but the rendered output.

The template **body HTML** and any **logo binary** are NOT stored here — they live in S3
``myadmin-shared`` under the tenant-prefixed layout (see
:func:`sam.members.repository.table_design.template_body_s3_key`) and are referenced by key.
The metadata item only carries the per-language ``s3_body_key`` ref; the body text is loaded
through the service's body-store seam at render/send time. Nothing in this module talks to
DynamoDB, S3, or boto3.

Metadata shape::

    { "tenant_id": "<pk>", "template_id": "<server-chosen id>" (SK id),
      "name": "Welcome clubblad",
      "languages": { "nl": {"subject": "...", "s3_body_key": "<tenant>/templates/<id>/nl.html"},
                     "en": {"subject": "...", "s3_body_key": "<tenant>/templates/<id>/en.html"} },
      "merge_fields": ["first_name", "membership_type", ...],
      "logo_asset_ref": "<asset id>" | None,
      "origin": "user" | "preset",
      "created_by": "<Cognito sub>", "created_at": "<ISO-8601 UTC>", "updated_at": "..." }
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sam.members.domain.error_codes import (
    TEMPLATE_ID,
    TEMPLATE_LANGUAGES,
    TEMPLATE_MERGE_FIELDS,
    TEMPLATE_NAME,
    TEMPLATE_ORIGIN,
    TEMPLATE_TENANT,
    FieldError,
)

__all__ = [
    "MERGE_PLACEHOLDER_PATTERN",
    "SORT_KEY_SEPARATOR",
    "TEMPLATE_KINDS",
    "TEMPLATE_ORIGINS",
    "TemplateEntry",
    "TemplateLanguage",
    "TemplateValidationError",
    "render_with_merge",
]

#: Mirrors ``table_design.SORT_KEY_SEPARATOR`` — a ``template_id`` may not contain it (the id
#: becomes a sort-key segment). Duplicated here (not imported) to keep the domain layer free of
#: any dependency on the repository/storage layer (dependencies point downward only).
SORT_KEY_SEPARATOR = "#"

#: The valid ``origin`` values. ``user`` is a tenant-authored template; ``preset`` is a
#: shipped/prefab template a tenant may start from. Default: ``user``.
TEMPLATE_ORIGINS: tuple[str, ...] = ("user", "preset")

#: The valid ``kind`` values (labels sub-spec R-L1). ``mail`` is the historical HTML-body
#: template (per-language subject + body); ``label`` is an address-label template whose content
#: is ``lines`` (ordered lines of pivot-result field keys) and carries no mail body. ``kind`` is
#: a DISCRIMINATOR so both coexist in the one ``template#`` store. Default (absent/``None``) is
#: ``mail`` so every template written before this field existed stays a mail template — the
#: addition is backward-compatible.
TEMPLATE_KINDS: tuple[str, ...] = ("mail", "label")

#: The ``{{ field_name }}`` merge-placeholder grammar used by :func:`render_with_merge`. A
#: placeholder is a field key (letters, digits, underscores, dots — e.g. ``first_name`` or
#: ``membership.type``) wrapped in double braces, with optional surrounding whitespace inside
#: the braces (``{{first_name}}`` and ``{{ first_name }}`` are the same placeholder). Kept as a
#: module constant so the renderer, any validator, and tests agree on one grammar.
MERGE_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")


class TemplateValidationError(Exception):
    """Raised when a template entry is malformed (a client/data bug → 422 at the edge).

    Carries ``errors`` — a mapping of field name → :class:`FieldError` (machine ``code`` +
    English ``detail``, API standard v1.0) — so a caller surfaces every problem at once,
    localizable via the code (mirrors :class:`AnalyticsSetValidationError`).
    """

    def __init__(self, errors: Mapping[str, FieldError]):
        self.errors: dict[str, FieldError] = dict(errors)
        detail = "; ".join(f"{k}: {v.detail}" for k, v in self.errors.items())
        super().__init__(f"template entry is invalid: {detail}")


@dataclass(frozen=True)
class TemplateLanguage:
    """One language variant of a template: a ``subject`` + the S3 ``s3_body_key`` of its body.

    Frozen value. The body HTML is NEVER inlined here (400 KB item limit + it may be large /
    binary-adjacent) — only the S3 key that locates it. Both fields must be non-blank for a
    language to be stored.
    """

    subject: str
    s3_body_key: str

    def is_blank(self) -> bool:
        """True when either the subject or the body key is missing/blank (an unusable variant)."""
        return not (self.subject or "").strip() or not (self.s3_body_key or "").strip()

    def to_dict(self) -> dict[str, str]:
        """Serialize to the plain ``{subject, s3_body_key}`` dict the metadata item stores."""
        return {"subject": self.subject, "s3_body_key": self.s3_body_key}

    @classmethod
    def from_value(cls, value: Mapping[str, Any]) -> TemplateLanguage:
        """Rebuild from a stored ``{subject, s3_body_key}`` mapping (tolerant of extra keys)."""
        if not isinstance(value, Mapping):
            return cls(subject="", s3_body_key="")
        return cls(
            subject=str(value.get("subject", "") or ""),
            s3_body_key=str(value.get("s3_body_key", "") or ""),
        )


@dataclass(frozen=True)
class TemplateEntry:
    """One tenant's stored mail-template METADATA (R2).

    Frozen because an entry is data resolved and shared like the sibling entities
    (:class:`AnalyticsSetEntry`). Fields map 1:1 to the design's metadata shape:

    - ``tenant_id`` — the owning tenant (partition key). A blank tenant is a cross-tenant hazard
      and is refused (Property 1).
    - ``template_id`` — the entry's stable server-chosen id (sort-key id). Non-blank, no key
      separator.
    - ``name`` — the user-authored, non-blank template name (presentation).
    - ``languages`` — a mapping of language code (e.g. ``"nl"`` / ``"en"``) →
      :class:`TemplateLanguage`. At least one usable (non-blank subject + body key) language is
      required — an empty / all-blank ``languages`` is invalid (a template with no body is
      unusable).
    - ``merge_fields`` — the ordered list of merge-field keys the body uses (e.g.
      ``["first_name", "membership_type"]``). MAY be empty (a static template with no merge
      fields). Each must be a non-blank string. This is declarative metadata; the actual merge
      happens in :func:`render_with_merge` at send time.
    - ``logo_asset_ref`` — optional reference into the asset/branding system for a header logo;
      ``None`` when the template carries no logo.
    - ``origin`` — ``'user'`` (default) or ``'preset'``.
    - ``created_by`` — the verified Cognito ``sub`` of the creator (attribution only; never an
      access gate). Optional.
    - ``created_at`` / ``updated_at`` — ISO-8601 UTC timestamp strings stamped by the service.
    """

    tenant_id: str
    template_id: str
    name: str
    languages: Mapping[str, TemplateLanguage] = field(default_factory=dict)
    merge_fields: Sequence[str] = field(default_factory=tuple)
    logo_asset_ref: str | None = None
    origin: str = "user"
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    #: The template KIND discriminator (labels sub-spec R-L1). ``"mail"`` (the default — and
    #: what an absent/``None`` stored value resolves to) is the historical HTML-body template;
    #: ``"label"`` is an address-label template whose content is :attr:`lines`. See
    #: :data:`TEMPLATE_KINDS`.
    kind: str = "mail"
    #: The LABEL content model (labels sub-spec R-L1), only meaningful when ``kind == "label"``:
    #: an ordered list of lines, each line a list of pivot-result field keys (a multi-key line
    #: is space-joined at compose time). No hard line limit. Empty/absent for a mail template.
    lines: Sequence[Sequence[str]] = field(default_factory=tuple)

    # ── validation ──────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate the entry shape, raising :class:`TemplateValidationError` on failure.

        Rules: non-blank ``tenant_id``; non-blank ``template_id`` with no key separator;
        non-blank ``name``; ``languages`` is a mapping with AT LEAST ONE usable variant
        (non-blank subject + body key); ``merge_fields`` is a list of non-blank strings (empty is
        valid); ``origin`` in {``'user'``, ``'preset'``}. Returns None when well-formed.
        """
        errors: dict[str, FieldError] = {}

        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            errors["tenant_id"] = FieldError(
                code=TEMPLATE_TENANT,
                detail="must be a non-blank string (tenant isolation, Property 1)",
            )

        if not isinstance(self.template_id, str) or not self.template_id.strip():
            errors["template_id"] = FieldError(
                code=TEMPLATE_ID, detail="must be a non-blank string"
            )
        elif SORT_KEY_SEPARATOR in self.template_id:
            errors["template_id"] = FieldError(
                code=TEMPLATE_ID,
                detail=(
                    f"must not contain {SORT_KEY_SEPARATOR!r} (it becomes a sort-key id segment)"
                ),
                params={"separator": SORT_KEY_SEPARATOR},
            )

        if not isinstance(self.name, str) or not self.name.strip():
            errors["name"] = FieldError(
                code=TEMPLATE_NAME, detail="must be a non-blank string"
            )

        if self.kind not in TEMPLATE_KINDS:
            errors["kind"] = FieldError(
                code=TEMPLATE_ORIGIN,
                detail=f"must be one of: {', '.join(TEMPLATE_KINDS)}",
                params={"allowed": list(TEMPLATE_KINDS)},
            )

        if self.kind == "label":
            # A LABEL template's content is `lines` (ordered lines of field keys); it carries NO
            # mail body, so `languages` is not required for it (R-L1). At least one non-empty line
            # with at least one non-blank field key is required — a label with no lines is empty.
            if not isinstance(self.lines, (list, tuple)) or not self.lines:
                errors["lines"] = FieldError(
                    code=TEMPLATE_LANGUAGES,
                    detail=(
                        "a label template must carry a non-empty list of lines "
                        "(each line a list of field keys)"
                    ),
                )
            else:
                usable_lines = [
                    line
                    for line in self.lines
                    if isinstance(line, (list, tuple))
                    and any(isinstance(k, str) and k.strip() for k in line)
                ]
                if not usable_lines:
                    errors["lines"] = FieldError(
                        code=TEMPLATE_LANGUAGES,
                        detail=(
                            "at least one line must carry a non-blank field key "
                            "(a label with no usable lines is empty)"
                        ),
                    )
        else:
            # Mail template (default) — unchanged: at least one usable language variant required.
            if not isinstance(self.languages, Mapping) or not self.languages:
                errors["languages"] = FieldError(
                    code=TEMPLATE_LANGUAGES,
                    detail="must be a non-empty mapping of language code to {subject, s3_body_key}",
                )
            else:
                usable = [
                    lang
                    for lang in self.languages.values()
                    if isinstance(lang, TemplateLanguage) and not lang.is_blank()
                ]
                if not usable:
                    errors["languages"] = FieldError(
                        code=TEMPLATE_LANGUAGES,
                        detail=(
                            "at least one language must carry a non-blank subject and body key "
                            "(a template with no usable body is unsendable)"
                        ),
                    )

        if not isinstance(self.merge_fields, (list, tuple)):
            errors["merge_fields"] = FieldError(
                code=TEMPLATE_MERGE_FIELDS,
                detail="must be a list of merge-field key strings",
            )
        else:
            for mf in self.merge_fields:
                if not isinstance(mf, str) or not mf.strip():
                    errors["merge_fields"] = FieldError(
                        code=TEMPLATE_MERGE_FIELDS,
                        detail="every merge field must be a non-blank string",
                    )
                    break

        if self.origin not in TEMPLATE_ORIGINS:
            errors["origin"] = FieldError(
                code=TEMPLATE_ORIGIN,
                detail=f"must be one of: {', '.join(TEMPLATE_ORIGINS)}",
                params={"allowed": list(TEMPLATE_ORIGINS)},
            )

        if errors:
            raise TemplateValidationError(errors)

    # ── storage-shape mapping (used by the repository; storage-agnostic here) ─────────

    def to_item(self) -> dict[str, Any]:
        """Serialize to the plain dict the repository persists (validated first).

        Carries the domain-facing attributes only; the repository stamps the physical
        primary-key attributes on top. Validates before serializing so a malformed entry can
        never be written. ``languages`` is flattened to plain ``{lang: {subject, s3_body_key}}``.
        """
        self.validate()
        item: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "template_id": self.template_id,
            "name": self.name,
            "languages": {
                lang: variant.to_dict() for lang, variant in self.languages.items()
            },
            "merge_fields": list(self.merge_fields),
            "logo_asset_ref": self.logo_asset_ref,
            "origin": self.origin,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        # `kind`/`lines` are ADDITIVE (labels sub-spec R-L1): a mail template (the default kind,
        # no lines) serializes EXACTLY as before — the discriminator + lines are written only
        # when they carry meaning, so existing mail items are byte-identical and round-trip
        # unchanged. A label template carries both.
        if self.kind != "mail":
            item["kind"] = self.kind
        if self.lines:
            item["lines"] = [list(line) for line in self.lines]
        return item

    @classmethod
    def from_item(cls, item: Mapping[str, Any]) -> TemplateEntry:
        """Rebuild an entry from a stored item (inverse of :meth:`to_item`).

        Tolerant of the physical primary-key attributes the repository adds (e.g. ``sk``): it
        reads only the domain attributes. ``languages`` / ``merge_fields`` default to empty when
        absent (defensive — a stored entry should always carry at least one language), and
        ``origin`` defaults to ``'user'`` for a legacy item written before the field existed.
        """
        if not isinstance(item, Mapping):
            raise TemplateValidationError(
                {
                    "item": FieldError(
                        code=TEMPLATE_LANGUAGES, detail="must be a mapping"
                    )
                }
            )
        raw_languages = item.get("languages") or {}
        languages: dict[str, TemplateLanguage] = {}
        if isinstance(raw_languages, Mapping):
            for lang, variant in raw_languages.items():
                languages[str(lang)] = TemplateLanguage.from_value(variant)

        raw_merge = item.get("merge_fields") or []
        merge_fields = (
            [str(m) for m in raw_merge if isinstance(m, str) and m]
            if isinstance(raw_merge, (list, tuple))
            else []
        )

        origin = item.get("origin")
        created_by = item.get("created_by")
        logo = item.get("logo_asset_ref")

        # `kind` defaults to "mail" for a legacy item written before the field existed
        # (backward-compatible, R-L1). `lines` rebuilds the label content model (list of lists of
        # field-key strings), tolerating a malformed/absent value as empty.
        raw_kind = item.get("kind")
        kind = raw_kind if isinstance(raw_kind, str) and raw_kind else "mail"
        raw_lines = item.get("lines")
        lines: list[list[str]] = []
        if isinstance(raw_lines, (list, tuple)):
            for line in raw_lines:
                if isinstance(line, (list, tuple)):
                    lines.append([str(k) for k in line if isinstance(k, str) and k])

        return cls(
            tenant_id=item.get("tenant_id", ""),
            template_id=item.get("template_id", ""),
            name=item.get("name", ""),
            languages=languages,
            merge_fields=merge_fields,
            logo_asset_ref=logo if isinstance(logo, str) and logo else None,
            origin=origin if isinstance(origin, str) and origin else "user",
            created_by=created_by if isinstance(created_by, str) else "",
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
            kind=kind,
            # No lines → the dataclass default (empty tuple) so a mail entry rebuilt from a
            # legacy item stays `== ` the original (which also defaults lines to `()`), keeping
            # the round-trip identity test green.
            lines=tuple(tuple(line) for line in lines) if lines else tuple(),
        )

    def language(self, lang: str) -> TemplateLanguage | None:
        """Return the :class:`TemplateLanguage` for ``lang``, or ``None`` if the template has none."""
        variant = self.languages.get(lang) if isinstance(self.languages, Mapping) else None
        return variant if isinstance(variant, TemplateLanguage) else None

    def sort_order_key(self) -> tuple[str, str]:
        """Stable sort key for list presentation: ``(name, template_id)`` ascending."""
        return (self.name, self.template_id)


# ── Merge rendering (module-agnostic; happens AT SEND TIME, never in an AI prompt) ─────


def merge_placeholders(text: str) -> list[str]:
    """Return the ordered, de-duplicated merge-field keys referenced by ``text``.

    Scans ``text`` for ``{{ field }}`` placeholders (see :data:`MERGE_PLACEHOLDER_PATTERN`) and
    returns each distinct key once, in first-appearance order. A non-string ``text`` yields an
    empty list. Pure and storage-agnostic — used to discover which merge values a body needs.
    """
    if not isinstance(text, str) or not text:
        return []
    seen: list[str] = []
    for match in MERGE_PLACEHOLDER_PATTERN.finditer(text):
        key = match.group(1)
        if key not in seen:
            seen.append(key)
    return seen


def render_with_merge(
    text: str,
    values: Mapping[str, Any],
    *,
    default: str = "",
) -> str:
    """Fill ``{{ field }}`` placeholders in ``text`` from ``values`` — the send-time merge (R2).

    This is the real mail-merge: for a ``per_recipient`` send the caller passes ONE recipient's
    field values and gets that recipient's personalized text back. It is deliberately pure and
    module-agnostic — it operates only on a string and a plain ``{field: value}`` mapping, with
    NO knowledge of members, DynamoDB, or S3 — so the whole template store/renderer can extract
    to ``sam/shared/templates/`` unchanged on a second consumer (steering 35, rule of three).

    Behaviour:
    - Every ``{{ field }}`` whose key is present in ``values`` is replaced by ``str(value)``.
    - A placeholder whose key is ABSENT from ``values`` is replaced by ``default`` (``""`` by
      default) rather than left as a raw ``{{ field }}`` — a recipient never sees an unfilled
      placeholder, and a missing value never crashes the send.
    - Whitespace inside the braces is tolerated (``{{first_name}}`` == ``{{ first_name }}``).
    - A ``None`` value renders as ``default`` (an explicit null is treated as "no value") so a
      recipient never sees the literal ``None``.

    Args:
        text: The template body or subject containing ``{{ field }}`` placeholders.
        values: The per-recipient merge values (``{field_key: value}``).
        default: The replacement for an absent / ``None`` placeholder value.

    Returns:
        ``text`` with every placeholder resolved. A non-string ``text`` is returned coerced to
        ``str`` (an empty string stays empty).
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text
    mapping = dict(values or {})

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in mapping:
            return default
        value = mapping[key]
        return default if value is None else str(value)

    return MERGE_PLACEHOLDER_PATTERN.sub(_replace, text)
