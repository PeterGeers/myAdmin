"""Membership-service analytics-set CRUD surface (mirrors ``_membership_catalog``).

Mixed into ``MembershipService`` — bodies mirror the CatalogMixin pattern end to end.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sam.members.domain._membership_errors import (
    AnalyticsSetConflict,
    AnalyticsSetNotFound,
)
from sam.members.domain.analytics_set import (
    AnalyticsSetEntry,
)
from sam.members.domain.preferred_list import (
    PreferredList,
)


class AnalyticsSetsMixin:
    """CRUD surface for tenant-scoped member analytics-sets (corrects finding F-012).

    Storage-agnostic + tenant-agnostic. The injected :class:`MembersRepository` (accessed as
    ``self._repo``) is the sole DynamoDB touch-point. ``tenant_id`` is AUTHORITATIVE on every
    method (never trusted from a body). ``set_id`` is server-chosen (uuid4 hex, no natural
    key). Validation never requires ``group_columns`` / ``aggregate_measures`` to be non-empty
    (F-011 — a filtered-list set is first-class).
    """

    # ── list / get ──────────────────────────────────────────────────────────────────

    def list_analytics_sets(self, tenant_id: str) -> list[dict[str, Any]]:
        """List the tenant's analytics-sets, sorted by name asc for determinism.

        Returns the JSON-friendly shape (:meth:`_serialize_analytics_set`) for each entry.
        """
        entries = self._repo.list_analytics_sets(tenant_id)
        return [self._serialize_analytics_set(entry) for entry in entries]

    def get_analytics_set(self, tenant_id: str, set_id: str) -> dict[str, Any]:
        """Fetch one analytics-set by its ``set_id`` (404 if absent)."""
        entry = self._repo.get_analytics_set(tenant_id, set_id)
        if entry is None:
            raise AnalyticsSetNotFound(tenant_id, set_id)
        return self._serialize_analytics_set(entry)

    # ── create / update / delete ────────────────────────────────────────────────────

    def create_analytics_set(
        self, tenant_id: str, body: Mapping[str, Any], created_by: str | None = None
    ) -> dict[str, Any]:
        """Create a (tenant-shared) analytics-set for the tenant (R11.2 layer 1).

        Stamps the authoritative ``tenant_id`` (never trusting a body ``tenant_id`` / ``set_id``
        — verify-before-trust, Property 2). Generates ``set_id = uuid4().hex`` (server-chosen
        opaque id — unlike the catalog's client-supplied ``type_code``, an analytics-set has no
        natural key). Reads ``name`` / ``kind`` / ``definition`` from the body, stamps
        ``origin = 'user'`` and ``created_by`` = the verified caller ``sub`` (ATTRIBUTION only —
        R11.3; never trusted from the body, never an access gate), and
        ``created_at = updated_at = now(UTC) ISO``, validates, persists, and returns the
        serialized entry. The set joins the TENANT-SHARED library — visible to every user in the
        tenant (R11.2). Raises :class:`AnalyticsSetConflict` if the generated id already exists
        (effectively impossible with uuid4, carried for symmetry).
        """
        payload = dict(body) if isinstance(body, Mapping) else {}
        now = datetime.now(timezone.utc).isoformat()
        set_id = uuid.uuid4().hex
        definition = payload.get("definition")

        entry = AnalyticsSetEntry(
            tenant_id=tenant_id,
            set_id=set_id,
            name=str(payload.get("name", "")),
            kind=str(payload.get("kind", "count")),
            definition=dict(definition) if isinstance(definition, Mapping) else {},
            # Every stored set is user-origin (presets stay in code, R11.5). created_by is the
            # authenticated principal's sub (R11.1 — user ≠ member); attribution only.
            origin="user",
            created_by=created_by or "",
            created_at=now,
            updated_at=now,
        )
        entry.validate()

        # Conflict guard (symmetry with catalog create; uuid4 collisions are near-impossible).
        if self._repo.get_analytics_set(tenant_id, set_id) is not None:
            raise AnalyticsSetConflict(tenant_id, set_id)

        saved = self._repo.save_analytics_set(tenant_id, entry)
        return self._serialize_analytics_set(saved)

    def update_analytics_set(
        self, tenant_id: str, set_id: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update an existing analytics-set (404 if absent).

        Loads the entry within the tenant (Property 1); an absent set_id raises
        :class:`AnalyticsSetNotFound` (→ 404). Merges the client body over the existing
        entry — path ``set_id`` + ``tenant_id`` are authoritative for identity, ``created_at``
        is preserved, ``updated_at`` is bumped — then validates and persists. Returns the
        updated entry in the serialized shape.
        """
        existing = self._repo.get_analytics_set(tenant_id, set_id)
        if existing is None:
            raise AnalyticsSetNotFound(tenant_id, set_id)

        payload = dict(body) if isinstance(body, Mapping) else {}
        now = datetime.now(timezone.utc).isoformat()

        name = str(payload["name"]) if "name" in payload else existing.name
        kind = str(payload["kind"]) if "kind" in payload else existing.kind
        definition = existing.definition
        if "definition" in payload and isinstance(payload.get("definition"), Mapping):
            definition = dict(payload["definition"])

        updated = AnalyticsSetEntry(
            tenant_id=tenant_id,  # authoritative — never the body
            set_id=set_id,  # the path is authoritative for identity
            name=name,
            kind=kind,
            definition=definition,
            origin=existing.origin,  # preserved — identity, never changed by an edit
            created_by=existing.created_by,  # preserved — original author attribution (R11.3)
            created_at=existing.created_at,  # preserved from original
            updated_at=now,  # bumped
        )
        updated.validate()
        saved = self._repo.save_analytics_set(tenant_id, updated)
        return self._serialize_analytics_set(saved)

    def delete_analytics_set(self, tenant_id: str, set_id: str) -> dict[str, Any]:
        """Delete an analytics-set (hard delete). 404 if absent.

        Does a get-first to raise :class:`AnalyticsSetNotFound` for an absent set_id so the
        edge maps it to 404. Unlike catalog entries (soft-delete for referential integrity),
        analytics-sets have no referencing records, so a hard delete is correct.
        """
        existing = self._repo.get_analytics_set(tenant_id, set_id)
        if existing is None:
            raise AnalyticsSetNotFound(tenant_id, set_id)
        self._repo.delete_analytics_set(tenant_id, set_id)
        return self._serialize_analytics_set(existing)

    # ── preferred list (per-user, R11.2 layer 2) ────────────────────────────────────

    def get_preferred_list(self, tenant_id: str, sub: str) -> dict[str, Any]:
        """Return user ``sub``'s preferred list (empty refs when the user has none).

        Keyed by the authenticated ``sub`` (user ≠ member — R11.1); the preferred list is
        private to that principal. A user who has not curated one yet gets an EMPTY list
        (empty-is-valid, R11) — never a 404. Returns the JSON-friendly serialized shape.
        """
        entry = self._repo.get_preferred_list(tenant_id, sub)
        if entry is None:
            entry = PreferredList.empty(tenant_id, sub)
        return self._serialize_preferred_list(entry)

    def save_preferred_list(
        self, tenant_id: str, sub: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Create or REPLACE user ``sub``'s preferred list from the request body (R11.2).

        ``tenant_id`` and ``sub`` are AUTHORITATIVE (the verified principal — never trusted
        from the body). Reads ``refs`` (the ordered tagged-reference list) from the body,
        coercing each entry to a string and dropping blanks/non-strings, stamps
        ``updated_at = now(UTC) ISO``, validates, persists (a full replace — exactly one list
        per user), and returns the serialized shape. An empty / absent ``refs`` is valid (the
        user clears their preferences).
        """
        payload = dict(body) if isinstance(body, Mapping) else {}
        now = datetime.now(timezone.utc).isoformat()
        raw_refs = payload.get("refs")
        refs = (
            [str(r) for r in raw_refs if isinstance(r, str) and r.strip()]
            if isinstance(raw_refs, (list, tuple))
            else []
        )
        entry = PreferredList(
            tenant_id=tenant_id,  # authoritative — never the body
            sub=sub,  # authoritative — the verified principal, never the body (R11.1)
            refs=refs,
            updated_at=now,
        )
        entry.validate()
        saved = self._repo.save_preferred_list(tenant_id, entry)
        return self._serialize_preferred_list(saved)

    # ── serialization helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _serialize_preferred_list(entry: PreferredList) -> dict[str, Any]:
        """Project a preferred-list entry to the JSON-friendly shape the handler returns.

        Carries ``sub`` (owner), ``refs`` (ordered tagged references), ``updated_at``.
        ``tenant_id`` is omitted (the caller already knows the tenant context).
        """
        return {
            "sub": entry.sub,
            "refs": list(entry.refs),
            "updated_at": entry.updated_at,
        }

    @staticmethod
    def _serialize_analytics_set(entry: AnalyticsSetEntry) -> dict[str, Any]:
        """Project an analytics-set entry to the JSON-friendly shape the handler returns.

        Carries ``set_id``, ``name``, ``kind``, ``definition``, ``origin``, ``created_by``,
        ``created_at``, ``updated_at`` as plain JSON. ``tenant_id`` is omitted (the caller
        already knows the tenant context). ``created_by`` is surfaced for attribution display
        (R11.3) — the SPA shows "created by" but never gates on it.
        """
        return {
            "set_id": entry.set_id,
            "name": entry.name,
            "kind": entry.kind,
            "definition": dict(entry.definition),
            "origin": entry.origin,
            "created_by": entry.created_by,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
