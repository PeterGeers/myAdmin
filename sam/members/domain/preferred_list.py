"""
The per-user **preferred-list** entity (R11.2 layer 2 — member-analytics Phase 12).

A preferred list is a user's PRIVATE, curated, ordered selection of analytics sets drawn from
the TENANT-SHARED set library (predefined code presets + user-created shared sets). It stores
**references**, not copies — one definition per set, no duplication (R11.2 / R11.5). Exactly
one preferred list per user, keyed by the user's Cognito ``sub`` (the authenticated principal —
user ≠ member, R11.1; a user may be a member, both, or neither).

Reference shape: each entry in ``refs`` is a **tagged reference string** —
``preset:<key>`` for a predefined (code) preset, or ``set:<id>`` for a shared user-created set.
The resolver on the read side skips a reference that no longer resolves (R11.6); this entity
does NOT itself validate that a reference points at something that exists (the shared library
is a separate concern) — it only validates the SHAPE (a list of non-blank strings).

This module owns only the **entity model** (tenant-agnostic shape + validation + the
storage-shape ``to_item`` / ``from_item`` mapping), mirroring
:mod:`sam.members.domain.analytics_set`. The repository methods that persist it live in
:mod:`sam.members.repository.members_repository`; the CRUD domain methods live in
:mod:`sam.members.domain._membership_analytics`. Nothing here talks to DynamoDB or boto3.

Entry shape::

    { "tenant_id": "<pk>", "sub": "<owning user's Cognito sub>" (SK id),
      "refs": ["preset:jubilees", "set:ab12cd…", …],   # ordered tagged references
      "updated_at": "<ISO-8601 UTC>" }
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sam.members.domain.error_codes import (
    PREF_LIST_REFS,
    PREF_LIST_SUB,
    PREF_LIST_TENANT,
    FieldError,
)

__all__ = [
    "SORT_KEY_SEPARATOR",
    "PreferredList",
    "PreferredListValidationError",
]

#: Mirrors ``table_design.SORT_KEY_SEPARATOR`` — a ``sub`` may not contain it (an opaque Cognito
#: sub never does). Duplicated here (not imported) to keep the domain layer free of any
#: dependency on the repository/storage layer (dependencies point downward only).
SORT_KEY_SEPARATOR = "#"


class PreferredListValidationError(Exception):
    """Raised when a preferred-list entry is malformed (a client/data bug → 422 at the edge).

    Carries ``errors`` — a mapping of field name → :class:`FieldError` — so a caller surfaces
    every problem at once, mirroring :class:`AnalyticsSetValidationError`.
    """

    def __init__(self, errors: Mapping[str, FieldError]):
        self.errors: dict[str, FieldError] = dict(errors)
        detail = "; ".join(f"{k}: {v.detail}" for k, v in self.errors.items())
        super().__init__(f"preferred-list entry is invalid: {detail}")


@dataclass(frozen=True)
class PreferredList:
    """One user's preferred list of analytics sets (R11.2 layer 2).

    Frozen because an entry is data resolved and shared like the sibling entities. Fields:

    - ``tenant_id`` — the owning tenant (partition key). A blank tenant is a cross-tenant
      hazard and is refused (Property 1).
    - ``sub`` — the owning user's Cognito ``sub`` (sort-key id). The preferred list is PRIVATE
      to this principal; ``sub`` is the authenticated user, NEVER a ``member_id`` (user ≠
      member — R11.1). Non-blank, no key separator.
    - ``refs`` — the ordered list of tagged reference strings (``preset:<key>`` / ``set:<id>``).
      MAY be empty (a user with no curated preferences). Each must be a non-blank string; the
      SHAPE is validated here, not whether each reference currently resolves (R11.6 — the read
      side skips a dangling reference).
    - ``updated_at`` — ISO-8601 UTC timestamp string stamped by the domain on save.
    """

    tenant_id: str
    sub: str
    refs: Sequence[str] = field(default_factory=tuple)
    updated_at: str = ""

    # ── validation ──────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate the entry SHAPE, raising :class:`PreferredListValidationError` on failure.

        Rules: non-blank ``tenant_id``; non-blank ``sub`` with no key separator; ``refs`` is a
        list/tuple of non-blank strings (an empty list is valid — a user with no preferences).
        Does NOT validate that each ref points at an existing set/preset (R11.6). Returns None
        when well-formed.
        """
        errors: dict[str, FieldError] = {}

        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            errors["tenant_id"] = FieldError(
                code=PREF_LIST_TENANT,
                detail="must be a non-blank string (tenant isolation, Property 1)",
            )

        if not isinstance(self.sub, str) or not self.sub.strip():
            errors["sub"] = FieldError(
                code=PREF_LIST_SUB,
                detail="must be a non-blank string (the owning user sub)",
            )
        elif SORT_KEY_SEPARATOR in self.sub:
            errors["sub"] = FieldError(
                code=PREF_LIST_SUB,
                detail=(
                    f"must not contain {SORT_KEY_SEPARATOR!r} (it becomes a sort-key id segment)"
                ),
                params={"separator": SORT_KEY_SEPARATOR},
            )

        if not isinstance(self.refs, (list, tuple)):
            errors["refs"] = FieldError(
                code=PREF_LIST_REFS, detail="must be a list of reference strings"
            )
        else:
            for ref in self.refs:
                if not isinstance(ref, str) or not ref.strip():
                    errors["refs"] = FieldError(
                        code=PREF_LIST_REFS,
                        detail="every reference must be a non-blank string",
                    )
                    break

        if errors:
            raise PreferredListValidationError(errors)

    # ── storage-shape mapping (used by the repository; storage-agnostic here) ─────────

    def to_item(self) -> dict[str, Any]:
        """Serialize to the plain dict the repository persists (validated first).

        Carries the domain-facing attributes only (``tenant_id`` / ``sub`` / ``refs`` /
        ``updated_at``); the repository stamps the physical primary-key attributes on top.
        Validates before serializing so a malformed entry can never be written.
        """
        self.validate()
        return {
            "tenant_id": self.tenant_id,
            "sub": self.sub,
            "refs": list(self.refs),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_item(cls, item: Mapping[str, Any]) -> PreferredList:
        """Rebuild an entry from a stored item (inverse of :meth:`to_item`).

        Tolerant of the physical primary-key attributes the repository adds (e.g. ``sk``): it
        reads only the domain attributes. ``refs`` defaults to an empty list when absent.
        """
        if not isinstance(item, Mapping):
            raise PreferredListValidationError(
                {"item": FieldError(code=PREF_LIST_REFS, detail="must be a mapping")}
            )
        raw_refs = item.get("refs") or []
        refs = (
            [str(r) for r in raw_refs if isinstance(r, str) and r]
            if isinstance(raw_refs, (list, tuple))
            else []
        )
        return cls(
            tenant_id=item.get("tenant_id", ""),
            sub=item.get("sub", ""),
            refs=refs,
            updated_at=item.get("updated_at", ""),
        )

    @classmethod
    def empty(cls, tenant_id: str, sub: str) -> PreferredList:
        """An empty preferred list for a user who has not curated one yet (R11 empty-is-valid)."""
        return cls(tenant_id=tenant_id, sub=sub, refs=[], updated_at="")
