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
        self, tenant_id: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Create an analytics-set for the tenant.

        Stamps the authoritative ``tenant_id`` (never trusting a body ``tenant_id`` / ``set_id``
        — verify-before-trust, Property 2). Generates ``set_id = uuid4().hex`` (server-chosen
        opaque id — unlike the catalog's client-supplied ``type_code``, an analytics-set has no
        natural key). Reads ``name`` / ``kind`` / ``definition`` from the body, stamps
        ``created_at = updated_at = now(UTC) ISO``, validates, persists, and returns the
        serialized entry. Raises :class:`AnalyticsSetConflict` if the generated id already
        exists (effectively impossible with uuid4, carried for symmetry).
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

    # ── serialization helper ────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_analytics_set(entry: AnalyticsSetEntry) -> dict[str, Any]:
        """Project an analytics-set entry to the JSON-friendly shape the handler returns.

        Carries ``set_id``, ``name``, ``kind``, ``definition``, ``created_at``, ``updated_at``
        as plain JSON. ``tenant_id`` is omitted (the caller already knows the tenant context).
        """
        return {
            "set_id": entry.set_id,
            "name": entry.name,
            "kind": entry.kind,
            "definition": dict(entry.definition),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
