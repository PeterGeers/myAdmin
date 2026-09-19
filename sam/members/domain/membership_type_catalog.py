"""
S5 Task 1.5 — the **Lidmaatschap Beheer** membership-type catalog entity (design C8,
R2.1/R2.4; see ``generic-membership-design.md``).

This is a **new coupling** the migration adds (not present in h-dcn today): a tenant-scoped,
managed **catalog of membership types**. The member record's ``membership.membership_type``
fixed field (task 1.1) holds a **reference** to a catalog entry's ``type_code`` — never free
text — so a member can only be assigned a type that *exists* (and is ``active``) in that
tenant's catalog.

This module owns only the **entity model** (the tenant-agnostic entry shape + its validation +
the storage-shape ``to_item`` / ``from_item`` mapping). The repository METHODS that persist it
live in :mod:`sam.members.repository.members_repository`; the authoritative *reference* check
(does a member's ``membership_type`` point at a live catalog entry?) is the MembershipService's
job in the domain layer (C8, task 5.3). Nothing here talks to DynamoDB or boto3.

Design constraints honoured here (per the design of record):

- **Tenant-scoped fixed-domain entity.** Entry shape (design C8):
  ``{ "tenant_id": "<pk>", "type_code": "erelid" (SK), "label": {"nl": ..., "en": ...},
  "active": true, "order": 10 }``. Stored in the tenant-scoped data layer (``tenant_id`` PK).
- **Generic, tenant-agnostic.** Empty-by-default, tenant-owned. **No ``if tenant == "h-dcn"``** —
  h-dcn seeds its own types (Erelid/Donateur/Sponsor/…) as *data* later (task 4.2), exactly
  like the field overlay (task 1.2) and scope config (task 1.3).
- **Soft-delete only.** Deactivating a type (``active=false``) keeps existing members valid but
  removes it from the dropdown for new/edited members — a hard delete would orphan historical
  member records, so the repository offers no hard delete (design C8: referential integrity).
- **``type_code`` is the reference key.** It is the value the member record stores and the
  catalog's sort-key id; it must be a well-formed, non-blank code with no key separator (which
  would make the sort key ambiguous — see ``table_design``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

__all__ = [
    "CATALOG_LOCALES",
    "MembershipTypeEntry",
    "MembershipTypeValidationError",
    "SORT_KEY_SEPARATOR",
]

#: The i18n locales a catalog label carries (design C8: ``label {"nl": ..., "en": ...}``).
#: Kept as a constant so the entity, the resolved-field-config endpoint (task 3.3), and any
#: seed data (task 4.2) agree on one set. Extra locales on a payload are preserved but not
#: required; a well-formed entry must at minimum carry a non-blank ``nl`` label.
CATALOG_LOCALES: tuple[str, ...] = ("nl", "en")

#: The catalog's *required* label locale. A membership type must at least be named in Dutch
#: (the platform's primary locale); other locales are optional and preserved as given.
_REQUIRED_LOCALE = "nl"

#: Mirrors ``table_design.SORT_KEY_SEPARATOR`` — a ``type_code`` may not contain it, since the
#: code becomes a sort-key id segment. Duplicated here (not imported) to keep the domain layer
#: free of any dependency on the repository/storage layer (dependencies point downward only).
SORT_KEY_SEPARATOR = "#"


class MembershipTypeValidationError(Exception):
    """Raised when a membership-type catalog entry is malformed (a config/data bug).

    Carries ``errors`` — a mapping of field name → human-readable reason — so a caller
    surfaces every problem at once rather than one at a time (mirrors
    ``FieldValidationError`` / ``ScopeConfigError`` in the sibling domain modules).
    """

    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        detail = "; ".join(f"{k}: {v}" for k, v in self.errors.items())
        super().__init__(f"membership-type catalog entry is invalid: {detail}")


@dataclass(frozen=True)
class MembershipTypeEntry:
    """One entry in a tenant's Lidmaatschap Beheer catalog (design C8).

    Frozen because an entry is data resolved and shared like the sibling config models
    (:class:`ScopeDimension`, :class:`FixedField`). The fields map 1:1 to the design's entry
    shape:

    - ``tenant_id`` — the owning tenant (partition key). Every entry is tenant-scoped; a blank
      tenant is a cross-tenant hazard and is refused (Property 1).
    - ``type_code`` — the entry's stable code (sort-key id). This is the value the member
      record's ``membership.membership_type`` references. Non-blank, no key separator.
    - ``label`` — i18n display label (``{"nl": ..., "en": ...}``); presentation only. Must at
      least carry a non-blank ``nl`` label.
    - ``active`` — ``True`` while the type may be assigned to new/edited members; a soft-delete
      sets it ``False`` (existing members keep their reference, the dropdown drops it).
    - ``order`` — presentation order in the dropdown (ascending). Ties break on ``type_code``.
    """

    tenant_id: str
    type_code: str
    label: Mapping[str, str] = field(default_factory=dict)
    active: bool = True
    order: int = 0

    # ── validation ──────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate the entry shape, raising :class:`MembershipTypeValidationError` on failure.

        Rules: non-blank ``tenant_id``; non-blank ``type_code`` with no key separator; a
        ``label`` mapping carrying at least a non-blank ``nl`` label; an integer ``order``.
        Returns None when the entry is well-formed.
        """
        errors: dict[str, str] = {}

        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            errors["tenant_id"] = "must be a non-blank string (tenant isolation, Property 1)"

        if not isinstance(self.type_code, str) or not self.type_code.strip():
            errors["type_code"] = "must be a non-blank string"
        elif SORT_KEY_SEPARATOR in self.type_code:
            errors["type_code"] = (
                f"must not contain {SORT_KEY_SEPARATOR!r} (it becomes a sort-key id segment)"
            )

        if not isinstance(self.label, Mapping):
            errors["label"] = "must be a mapping of locale -> label"
        else:
            nl = self.label.get(_REQUIRED_LOCALE)
            if not isinstance(nl, str) or not nl.strip():
                errors["label"] = f"must carry a non-blank {_REQUIRED_LOCALE!r} label"

        # bool is a subclass of int; accept True/False for order? No — order is a position.
        if isinstance(self.order, bool) or not isinstance(self.order, int):
            errors["order"] = "must be an integer"

        if errors:
            raise MembershipTypeValidationError(errors)

    def deactivated(self) -> "MembershipTypeEntry":
        """Return a copy with ``active=False`` — the soft-delete transform (no hard delete)."""
        return replace(self, active=False)

    # ── storage-shape mapping (used by the repository; storage-agnostic here) ─────────

    def to_item(self) -> dict[str, Any]:
        """Serialize to the plain dict the repository persists (validated first).

        The dict carries the domain-facing attributes only (``tenant_id`` / ``type_code`` /
        ``label`` / ``active`` / ``order``); the repository stamps the physical primary-key
        attributes (partition/sort key) on top. Validates before serializing so a malformed
        entry can never be written.
        """
        self.validate()
        return {
            "tenant_id": self.tenant_id,
            "type_code": self.type_code,
            "label": dict(self.label),
            "active": bool(self.active),
            "order": int(self.order),
        }

    @classmethod
    def from_item(cls, item: Mapping[str, Any]) -> "MembershipTypeEntry":
        """Rebuild an entry from a stored item (inverse of :meth:`to_item`).

        Tolerant of the physical primary-key attributes the repository adds (e.g. ``sk``):
        it reads only the domain attributes. ``active`` defaults to ``True`` and ``order`` to
        ``0`` when absent, matching the dataclass defaults.
        """
        if not isinstance(item, Mapping):
            raise MembershipTypeValidationError({"item": "must be a mapping"})
        raw_order = item.get("order", 0)
        try:
            order = int(raw_order)
        except (TypeError, ValueError):
            order = 0
        label = item.get("label") or {}
        return cls(
            tenant_id=item.get("tenant_id", ""),
            type_code=item.get("type_code", ""),
            label=dict(label) if isinstance(label, Mapping) else {},
            active=bool(item.get("active", True)),
            order=order,
        )

    def sort_order_key(self) -> tuple[int, str]:
        """Stable sort key for dropdown presentation: ``(order, type_code)`` ascending."""
        return (int(self.order), self.type_code)
