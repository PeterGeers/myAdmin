"""
The tenant-scoped **analytics-set** entity (member saved-set), corrects finding F-012.

A member analytics-set is a tenant-owned, named SAVED pivot/list definition the Member
Analytics surface stores. It replaces the Flask ``/api/pivot/models`` (MySQL) store for the
member saved-set path (F-012: a SAM module must own its saved-set data in DynamoDB, not via
the Flask pivot store). Because this module store validates its OWN shape, a filtered-list set
with EMPTY ``group_columns`` and EMPTY ``aggregate_measures`` is first-class (F-011) — the
whole point of the correction: validation here NEVER requires those to be non-empty.

This module owns only the **entity model** (the tenant-agnostic entry shape + its validation +
the storage-shape ``to_item`` / ``from_item`` mapping), mirroring
:mod:`sam.members.domain.membership_type_catalog`. The repository METHODS that persist it live
in :mod:`sam.members.repository.members_repository`; the CRUD domain methods live in
:mod:`sam.members.domain._membership_analytics`. Nothing here talks to DynamoDB or boto3.

Entry shape::

    { "tenant_id": "<pk>", "set_id": "<server-chosen uuid4 hex>" (SK id),
      "name": "Paper clubblad", "kind": "count" | "list",
      "definition": { ...the frontend PivotConfig in snake_case... },
      "created_at": "<ISO-8601 UTC>", "updated_at": "<ISO-8601 UTC>" }

``set_id`` is a SERVER-chosen opaque id (a uuid4 hex generated in the domain create method —
unlike the catalog's client-supplied ``type_code``, an analytics-set has no natural key).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sam.members.domain.error_codes import (
    ANALYTICS_SET_DEFINITION,
    ANALYTICS_SET_DELIVERY,
    ANALYTICS_SET_ID,
    ANALYTICS_SET_KIND,
    ANALYTICS_SET_NAME,
    ANALYTICS_SET_ORIGIN,
    ANALYTICS_SET_TENANT,
    FieldError,
)

__all__ = [
    "ANALYTICS_SET_KINDS",
    "ANALYTICS_SET_ORIGINS",
    "DELIVERY_ATTACHMENTS",
    "DELIVERY_MODES",
    "DELIVERY_MODE_PER_RECIPIENT",
    "DELIVERY_MODE_TO_FIXED",
    "SORT_KEY_SEPARATOR",
    "AnalyticsSetEntry",
    "AnalyticsSetValidationError",
]

#: The valid ``kind`` values a saved set may carry: a ``count`` (aggregate) set or a ``list``
#: (filtered-list) set. Kept as a constant so the entity, the domain CRUD, and any caller agree
#: on one set.
ANALYTICS_SET_KINDS: tuple[str, ...] = ("count", "list")

#: The valid ``origin`` values (R11.2). Every STORED set is ``user`` (predefined presets stay
#: in frontend code and are never persisted — R11.5), but the attribute is carried so the
#: shared library is self-describing and a future ``predefined`` origin (if presets are ever
#: promoted to stored items) needs no shape change. Default: ``user``.
ANALYTICS_SET_ORIGINS: tuple[str, ...] = ("user", "predefined")

#: The two delivery MODES a saved set's optional ``delivery`` block may carry (R3, design §2.1):
#:
#: - ``per_recipient`` — mail each member in the result individually with real mail-merge (the
#:   template's merge fields are filled from each member's row). Recipient addresses come from
#:   the dataset at run time and are therefore NEVER stored on the block.
#: - ``to_fixed`` — send the result as an attachment to an explicit, stored ``recipients`` list
#:   (often one address, e.g. a handling agent outside the dataset).
#:
#: Kept as a constant so the entity, the delivery routes (task 3.3), and the send engine (R4)
#: agree on one discriminator vocabulary.
DELIVERY_MODE_PER_RECIPIENT = "per_recipient"
DELIVERY_MODE_TO_FIXED = "to_fixed"
DELIVERY_MODES: tuple[str, ...] = (DELIVERY_MODE_PER_RECIPIENT, DELIVERY_MODE_TO_FIXED)

#: The optional ``attachment`` kinds a delivery may produce (design §2.1). ``None`` is also
#: valid (no attachment). ``pdf_labels`` carries the shared snake_case ``label_options`` block
#: (``{format, sort, font_size, alignment, border, country, start}`` — one model with R6,
#: task 6.3); ``csv`` is the plain export attachment.
DELIVERY_ATTACHMENTS: tuple[str, ...] = ("csv", "pdf_labels")

#: Mirrors ``table_design.SORT_KEY_SEPARATOR`` — a ``set_id`` may not contain it, since the id
#: becomes a sort-key segment. Duplicated here (not imported) to keep the domain layer free of
#: any dependency on the repository/storage layer (dependencies point downward only).
SORT_KEY_SEPARATOR = "#"


class AnalyticsSetValidationError(Exception):
    """Raised when an analytics-set entry is malformed (a client/data bug → 422 at the edge).

    Carries ``errors`` — a mapping of field name → :class:`FieldError` (machine ``code`` +
    English ``detail``, API standard v1.0) — so a caller surfaces every problem at once,
    localizable via the code (mirrors :class:`MembershipTypeValidationError`).
    """

    def __init__(self, errors: Mapping[str, FieldError]):
        self.errors: dict[str, FieldError] = dict(errors)
        detail = "; ".join(f"{k}: {v.detail}" for k, v in self.errors.items())
        super().__init__(f"analytics-set entry is invalid: {detail}")


@dataclass(frozen=True)
class AnalyticsSetEntry:
    """One entry in a tenant's member analytics-set store.

    Frozen because an entry is data resolved and shared like the sibling config models
    (:class:`MembershipTypeEntry`). The fields map 1:1 to the design's entry shape:

    - ``tenant_id`` — the owning tenant (partition key). Every entry is tenant-scoped; a blank
      tenant is a cross-tenant hazard and is refused (Property 1).
    - ``set_id`` — the entry's stable server-chosen id (sort-key id). Non-blank, no key
      separator. Generated as a uuid4 hex by the domain create method.
    - ``name`` — the user-authored, non-blank set name (presentation).
    - ``kind`` — ``'count'`` (aggregate) or ``'list'`` (filtered list).
    - ``definition`` — the frontend ``PivotConfig`` in snake_case (``data_source``,
      ``group_columns``, ``aggregate_measures``, ``filters``, ``column_pivot``,
      ``column_nest_levels``, ``display_mode``, ``include_rollup``). A mapping. Its
      ``group_columns`` / ``aggregate_measures`` MAY be empty — a filtered-list set is
      first-class (F-011); validation never requires them to be non-empty.
    - ``origin`` — ``'user'`` (default) for a user-created shared set; ``'predefined'`` reserved
      (R11.2). A stored set is always ``user`` today (presets stay in code, R11.5).
    - ``created_by`` — the verified Cognito ``sub`` of the user who created the set
      (ATTRIBUTION/audit only — R11.3; NEVER an access gate: any ``members:write``/admin user may
      edit/delete a shared set regardless of ``created_by``). Independent of membership (user ≠
      member, R11.1) — it is a user principal, not a ``member_id``. Optional (older items / an
      unauthenticated-context create leave it blank).
    - ``delivery`` — the OPTIONAL stored "what to do with the result" block (R3), or ``None`` on
      a set with no delivery (the default; a legacy set written before the field existed loads
      as ``None`` and keeps working). It is an additive field added the EXPLICIT way (declared
      here, validated here, defaulted in :meth:`from_item`) — a generic additive-field
      serializer is deliberately NOT built for one entity (steering 35 rule of three; see
      ``myBacklog/backlog.md``). The block is a mapping::

          { "mode": "per_recipient" | "to_fixed",   # the discriminator
            "template_id": "<template#<id>>" | None, # a template ref (R2); None for a bare set
            "attachment": "csv" | "pdf_labels" | None,
            "recipients": ["agent@example.com", ...], # to_fixed ONLY; absent/empty for per_recipient
            "label_options": {format, sort, font_size, alignment, border, country, start} | None }

      Mode rules (enforced in :meth:`validate`): ``to_fixed`` REQUIRES a non-empty
      ``recipients`` list (it is the fixed-address send); ``per_recipient`` stores NO recipients
      (addresses are resolved from the dataset at run time — a stored recipients list on a
      ``per_recipient`` block is a shape error). ``label_options`` is the SAME shared snake_case
      shape R6 uses interactively (one model, not two — task 6.3).
    - ``created_at`` / ``updated_at`` — ISO-8601 UTC timestamp strings stamped by the domain.
    """

    tenant_id: str
    set_id: str
    name: str
    kind: str
    definition: Mapping[str, Any] = field(default_factory=dict)
    origin: str = "user"
    created_by: str = ""
    delivery: Mapping[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""

    # ── validation ──────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate the entry shape, raising :class:`AnalyticsSetValidationError` on failure.

        Rules: non-blank ``tenant_id``; non-blank ``set_id`` with no key separator; non-blank
        ``name``; ``kind`` in {``'count'``, ``'list'``}; ``definition`` is a mapping. It NEVER
        requires ``group_columns`` / ``aggregate_measures`` to be non-empty — an empty-group,
        empty-measures filtered-list set is first-class (F-011). Returns None when well-formed.
        """
        errors: dict[str, FieldError] = {}

        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            errors["tenant_id"] = FieldError(
                code=ANALYTICS_SET_TENANT,
                detail="must be a non-blank string (tenant isolation, Property 1)",
            )

        if not isinstance(self.set_id, str) or not self.set_id.strip():
            errors["set_id"] = FieldError(
                code=ANALYTICS_SET_ID, detail="must be a non-blank string"
            )
        elif SORT_KEY_SEPARATOR in self.set_id:
            errors["set_id"] = FieldError(
                code=ANALYTICS_SET_ID,
                detail=(
                    f"must not contain {SORT_KEY_SEPARATOR!r} (it becomes a sort-key id segment)"
                ),
                params={"separator": SORT_KEY_SEPARATOR},
            )

        if not isinstance(self.name, str) or not self.name.strip():
            errors["name"] = FieldError(
                code=ANALYTICS_SET_NAME, detail="must be a non-blank string"
            )

        if self.kind not in ANALYTICS_SET_KINDS:
            errors["kind"] = FieldError(
                code=ANALYTICS_SET_KIND,
                detail=f"must be one of: {', '.join(ANALYTICS_SET_KINDS)}",
                params={"allowed": list(ANALYTICS_SET_KINDS)},
            )

        if not isinstance(self.definition, Mapping):
            errors["definition"] = FieldError(
                code=ANALYTICS_SET_DEFINITION,
                detail="must be a mapping (the PivotConfig)",
            )

        if self.origin not in ANALYTICS_SET_ORIGINS:
            errors["origin"] = FieldError(
                code=ANALYTICS_SET_ORIGIN,
                detail=f"must be one of: {', '.join(ANALYTICS_SET_ORIGINS)}",
                params={"allowed": list(ANALYTICS_SET_ORIGINS)},
            )

        # `created_by` is attribution-only (R11.3) — optional and un-gated; a non-string is
        # simply ignored rather than a validation error (never blocks a save).

        # `delivery` (R3) is optional — None/absent is a valid set with no delivery. When
        # present it must be a well-formed, mode-discriminated block (checked below).
        delivery_error = self._validate_delivery()
        if delivery_error is not None:
            errors["delivery"] = delivery_error

        if errors:
            raise AnalyticsSetValidationError(errors)

    def _validate_delivery(self) -> FieldError | None:
        """Validate the optional ``delivery`` block (R3), returning a :class:`FieldError` or None.

        ``None`` delivery is valid (a set with no delivery). A present block must be a mapping
        carrying a ``mode`` in :data:`DELIVERY_MODES`; the mode then discriminates:

        - ``to_fixed`` — REQUIRES a non-empty ``recipients`` list of non-blank address strings
          (the fixed-address send; design §2.1).
        - ``per_recipient`` — stores NO recipients (addresses are resolved from the dataset at
          run time); a non-empty stored ``recipients`` list is a shape error.

        ``template_id`` (when present) must be a string; ``attachment`` (when present) must be
        one of :data:`DELIVERY_ATTACHMENTS`; ``label_options`` (when present) must be a mapping
        (the shared snake_case block — its numeric fields are DynamoDB-coerced by the item
        builder, so this layer only checks the shape, not each scalar). Returns None when valid.
        """
        if self.delivery is None:
            return None

        if not isinstance(self.delivery, Mapping):
            return FieldError(
                code=ANALYTICS_SET_DELIVERY,
                detail="must be a mapping (the delivery block) or null",
            )

        mode = self.delivery.get("mode")
        if mode not in DELIVERY_MODES:
            return FieldError(
                code=ANALYTICS_SET_DELIVERY,
                detail=f"mode must be one of: {', '.join(DELIVERY_MODES)}",
                params={"allowed": list(DELIVERY_MODES)},
            )

        recipients = self.delivery.get("recipients")
        if recipients is not None and not isinstance(recipients, (list, tuple)):
            return FieldError(
                code=ANALYTICS_SET_DELIVERY,
                detail="recipients must be a list of address strings",
            )
        recipient_list = list(recipients) if isinstance(recipients, (list, tuple)) else []

        if mode == DELIVERY_MODE_TO_FIXED:
            if not recipient_list:
                return FieldError(
                    code=ANALYTICS_SET_DELIVERY,
                    detail="a 'to_fixed' delivery requires a non-empty recipients list",
                )
            if any(not isinstance(r, str) or not r.strip() for r in recipient_list):
                return FieldError(
                    code=ANALYTICS_SET_DELIVERY,
                    detail="every 'to_fixed' recipient must be a non-blank address string",
                )
        elif mode == DELIVERY_MODE_PER_RECIPIENT and recipient_list:
            # per_recipient resolves addresses from the dataset at run time — it must NOT carry
            # stored recipients (design §2.1).
            return FieldError(
                code=ANALYTICS_SET_DELIVERY,
                detail="a 'per_recipient' delivery must not store recipient addresses",
            )

        template_id = self.delivery.get("template_id")
        if template_id is not None and not isinstance(template_id, str):
            return FieldError(
                code=ANALYTICS_SET_DELIVERY,
                detail="template_id must be a string or null",
            )

        attachment = self.delivery.get("attachment")
        if attachment is not None and attachment not in DELIVERY_ATTACHMENTS:
            return FieldError(
                code=ANALYTICS_SET_DELIVERY,
                detail=f"attachment must be null or one of: {', '.join(DELIVERY_ATTACHMENTS)}",
                params={"allowed": list(DELIVERY_ATTACHMENTS)},
            )

        label_options = self.delivery.get("label_options")
        if label_options is not None and not isinstance(label_options, Mapping):
            return FieldError(
                code=ANALYTICS_SET_DELIVERY,
                detail="label_options must be a mapping (the shared snake_case block) or null",
            )

        return None

    # ── storage-shape mapping (used by the repository; storage-agnostic here) ─────────

    def to_item(self) -> dict[str, Any]:
        """Serialize to the plain dict the repository persists (validated first).

        The dict carries the domain-facing attributes only (``tenant_id`` / ``set_id`` /
        ``name`` / ``kind`` / ``definition`` / ``origin`` / ``created_by`` / the optional
        ``delivery`` block / ``created_at`` / ``updated_at``); the repository stamps the physical
        primary-key attributes (partition/sort key) on top. Validates before serializing so a
        malformed entry can never be written. ``delivery`` is serialized explicitly (the proven
        additive-field path — steering 35): a present block is emitted as a plain dict, and an
        absent block is written as ``None`` so :meth:`from_item` round-trips it unchanged.
        """
        self.validate()
        return {
            "tenant_id": self.tenant_id,
            "set_id": self.set_id,
            "name": self.name,
            "kind": self.kind,
            "definition": dict(self.definition),
            "origin": self.origin,
            "created_by": self.created_by,
            "delivery": dict(self.delivery) if self.delivery is not None else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_item(cls, item: Mapping[str, Any]) -> AnalyticsSetEntry:
        """Rebuild an entry from a stored item (inverse of :meth:`to_item`).

        Tolerant of the physical primary-key attributes the repository adds (e.g. ``sk``): it
        reads only the domain attributes. ``definition`` defaults to an empty dict and ``kind``
        to ``'count'`` when absent (defensive — a stored entry should always carry them).
        """
        if not isinstance(item, Mapping):
            raise AnalyticsSetValidationError(
                {
                    "item": FieldError(
                        code=ANALYTICS_SET_DEFINITION, detail="must be a mapping"
                    )
                }
            )
        definition = item.get("definition") or {}
        # `origin` defaults to 'user' for a legacy item written before the field existed
        # (every stored set is user-origin — R11.5). `created_by` defaults to blank (older
        # items carry no attribution).
        origin = item.get("origin")
        created_by = item.get("created_by")
        # `delivery` (R3) defaults to None for a legacy set written before the field existed
        # (and for any set that stores no delivery) — such a set must still load unchanged. A
        # present block is read as a plain dict; a non-mapping stored value degrades to None.
        delivery = item.get("delivery")
        return cls(
            tenant_id=item.get("tenant_id", ""),
            set_id=item.get("set_id", ""),
            name=item.get("name", ""),
            kind=item.get("kind", "count"),
            definition=dict(definition) if isinstance(definition, Mapping) else {},
            origin=origin if isinstance(origin, str) and origin else "user",
            created_by=created_by if isinstance(created_by, str) else "",
            delivery=dict(delivery) if isinstance(delivery, Mapping) else None,
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )

    def sort_order_key(self) -> tuple[str, str]:
        """Stable sort key for list presentation: ``(name, set_id)`` ascending (determinism)."""
        return (self.name, self.set_id)
