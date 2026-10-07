"""
The per-user **column-preferences** entity (session-columns spec R6 — Members overview).

A column-preferences record is a user's PRIVATE, curated, ordered selection of member fields to
surface as columns on the Members overview. It stores **references** (field-config keys), not
copies of field metadata or member data — mirroring the preferred-list's reference-not-copy rule
(R6.6). Exactly one column-preferences record per user, keyed by the user's Cognito ``sub`` (the
authenticated principal — user ≠ member, R11.1; a user may be a member, both, or neither).

Reference shape: each entry in ``columns`` is a **field key** — a reference into the field
config (``GET /members/field-config``). The read side skips a key that no longer resolves (field
removed / hidden, R6.6); this entity does NOT itself validate that a key points at a field that
exists (the field config is a separate concern) — it only validates the SHAPE (a list of
non-blank strings). ``member_number`` need not be stored (it is implied + always-on, R7.3).

This module owns only the **entity model** (tenant-agnostic shape + validation + the
storage-shape ``to_item`` / ``from_item`` mapping), modeled 1:1 on
:mod:`sam.members.domain.preferred_list` (``columns`` ↔ ``refs``). The repository methods that
persist it live in :mod:`sam.members.repository.members_repository`; the CRUD domain methods live
in the handler/domain layer. Nothing here talks to DynamoDB or boto3.

Entry shape::

    { "tenant_id": "<pk>", "sub": "<owning user's Cognito sub>" (SK id),
      "columns": ["years_member", "membership.region", …],   # ordered field keys
      "updated_at": "<ISO-8601 UTC>" }
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sam.members.domain.error_codes import (
    COLUMN_PREFS_COLUMNS,
    COLUMN_PREFS_SUB,
    COLUMN_PREFS_TENANT,
    FieldError,
)

__all__ = [
    "SORT_KEY_SEPARATOR",
    "ColumnPreferences",
    "ColumnPreferencesValidationError",
]

#: Mirrors ``table_design.SORT_KEY_SEPARATOR`` — a ``sub`` may not contain it (an opaque Cognito
#: sub never does). Duplicated here (not imported) to keep the domain layer free of any
#: dependency on the repository/storage layer (dependencies point downward only).
SORT_KEY_SEPARATOR = "#"


class ColumnPreferencesValidationError(Exception):
    """Raised when a column-preferences entry is malformed (a client/data bug → 422 at the edge).

    Carries ``errors`` — a mapping of field name → :class:`FieldError` — so a caller surfaces
    every problem at once, mirroring :class:`PreferredListValidationError`.
    """

    def __init__(self, errors: Mapping[str, FieldError]):
        self.errors: dict[str, FieldError] = dict(errors)
        detail = "; ".join(f"{k}: {v.detail}" for k, v in self.errors.items())
        super().__init__(f"column-preferences entry is invalid: {detail}")


@dataclass(frozen=True)
class ColumnPreferences:
    """One user's chosen overview columns (session-columns R6).

    Frozen because an entry is data resolved and shared like the sibling entities. Fields:

    - ``tenant_id`` — the owning tenant (partition key). A blank tenant is a cross-tenant
      hazard and is refused (Property 8).
    - ``sub`` — the owning user's Cognito ``sub`` (sort-key id). The column set is PRIVATE
      to this principal; ``sub`` is the authenticated user, NEVER a ``member_id`` (user ≠
      member — R11.1). Non-blank, no key separator.
    - ``columns`` — the ordered list of field keys (references into the field config). MAY be
      empty (a user with no chosen columns — the first-time default is applied client-side,
      R6.4). Each must be a non-blank string; the SHAPE is validated here, not whether each key
      currently resolves (R6.6 — the read side skips a dangling key).
    - ``updated_at`` — ISO-8601 UTC timestamp string stamped by the domain on save.
    """

    tenant_id: str
    sub: str
    columns: Sequence[str] = field(default_factory=tuple)
    updated_at: str = ""

    # ── validation ──────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate the entry SHAPE, raising :class:`ColumnPreferencesValidationError` on failure.

        Rules: non-blank ``tenant_id``; non-blank ``sub`` with no key separator; ``columns`` is a
        list/tuple of non-blank strings (an empty list is valid — a user with no chosen columns).
        Does NOT validate that each key points at an existing field (R6.6). Returns None when
        well-formed.
        """
        errors: dict[str, FieldError] = {}

        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            errors["tenant_id"] = FieldError(
                code=COLUMN_PREFS_TENANT,
                detail="must be a non-blank string (tenant isolation, Property 8)",
            )

        if not isinstance(self.sub, str) or not self.sub.strip():
            errors["sub"] = FieldError(
                code=COLUMN_PREFS_SUB,
                detail="must be a non-blank string (the owning user sub)",
            )
        elif SORT_KEY_SEPARATOR in self.sub:
            errors["sub"] = FieldError(
                code=COLUMN_PREFS_SUB,
                detail=(
                    f"must not contain {SORT_KEY_SEPARATOR!r} (it becomes a sort-key id segment)"
                ),
                params={"separator": SORT_KEY_SEPARATOR},
            )

        if not isinstance(self.columns, (list, tuple)):
            errors["columns"] = FieldError(
                code=COLUMN_PREFS_COLUMNS, detail="must be a list of field-key strings"
            )
        else:
            for col in self.columns:
                if not isinstance(col, str) or not col.strip():
                    errors["columns"] = FieldError(
                        code=COLUMN_PREFS_COLUMNS,
                        detail="every column key must be a non-blank string",
                    )
                    break

        if errors:
            raise ColumnPreferencesValidationError(errors)

    # ── storage-shape mapping (used by the repository; storage-agnostic here) ─────────

    def to_item(self) -> dict[str, Any]:
        """Serialize to the plain dict the repository persists (validated first).

        Carries the domain-facing attributes only (``tenant_id`` / ``sub`` / ``columns`` /
        ``updated_at``); the repository stamps the physical primary-key attributes on top.
        Validates before serializing so a malformed entry can never be written.
        """
        self.validate()
        return {
            "tenant_id": self.tenant_id,
            "sub": self.sub,
            "columns": list(self.columns),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_item(cls, item: Mapping[str, Any]) -> ColumnPreferences:
        """Rebuild an entry from a stored item (inverse of :meth:`to_item`).

        Tolerant of the physical primary-key attributes the repository adds (e.g. ``sk``): it
        reads only the domain attributes. ``columns`` defaults to an empty list when absent.
        """
        if not isinstance(item, Mapping):
            raise ColumnPreferencesValidationError(
                {"item": FieldError(code=COLUMN_PREFS_COLUMNS, detail="must be a mapping")}
            )
        raw_columns = item.get("columns") or []
        columns = (
            [str(c) for c in raw_columns if isinstance(c, str) and c]
            if isinstance(raw_columns, (list, tuple))
            else []
        )
        return cls(
            tenant_id=item.get("tenant_id", ""),
            sub=item.get("sub", ""),
            columns=columns,
            updated_at=item.get("updated_at", ""),
        )

    @classmethod
    def empty(cls, tenant_id: str, sub: str) -> ColumnPreferences:
        """An empty column set for a user who has not chosen any yet (R6.4 empty-is-valid)."""
        return cls(tenant_id=tenant_id, sub=sub, columns=[], updated_at="")
