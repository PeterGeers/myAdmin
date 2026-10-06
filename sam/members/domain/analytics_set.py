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
    ANALYTICS_SET_ID,
    ANALYTICS_SET_KIND,
    ANALYTICS_SET_NAME,
    ANALYTICS_SET_TENANT,
    FieldError,
)

__all__ = [
    "ANALYTICS_SET_KINDS",
    "SORT_KEY_SEPARATOR",
    "AnalyticsSetEntry",
    "AnalyticsSetValidationError",
]

#: The valid ``kind`` values a saved set may carry: a ``count`` (aggregate) set or a ``list``
#: (filtered-list) set. Kept as a constant so the entity, the domain CRUD, and any caller agree
#: on one set.
ANALYTICS_SET_KINDS: tuple[str, ...] = ("count", "list")

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
    - ``created_at`` / ``updated_at`` — ISO-8601 UTC timestamp strings stamped by the domain.
    """

    tenant_id: str
    set_id: str
    name: str
    kind: str
    definition: Mapping[str, Any] = field(default_factory=dict)
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

        if errors:
            raise AnalyticsSetValidationError(errors)

    # ── storage-shape mapping (used by the repository; storage-agnostic here) ─────────

    def to_item(self) -> dict[str, Any]:
        """Serialize to the plain dict the repository persists (validated first).

        The dict carries the domain-facing attributes only (``tenant_id`` / ``set_id`` /
        ``name`` / ``kind`` / ``definition`` / ``created_at`` / ``updated_at``); the repository
        stamps the physical primary-key attributes (partition/sort key) on top. Validates before
        serializing so a malformed entry can never be written.
        """
        self.validate()
        return {
            "tenant_id": self.tenant_id,
            "set_id": self.set_id,
            "name": self.name,
            "kind": self.kind,
            "definition": dict(self.definition),
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
        return cls(
            tenant_id=item.get("tenant_id", ""),
            set_id=item.get("set_id", ""),
            name=item.get("name", ""),
            kind=item.get("kind", "count"),
            definition=dict(definition) if isinstance(definition, Mapping) else {},
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )

    def sort_order_key(self) -> tuple[str, str]:
        """Stable sort key for list presentation: ``(name, set_id)`` ascending (determinism)."""
        return (self.name, self.set_id)
