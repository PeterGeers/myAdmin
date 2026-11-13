"""Create/save operations for every aggregate family.

Part of DynamoDbMembersRepository (task 6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from sam.members.domain.analytics_set import AnalyticsSetEntry
from sam.members.domain.column_preferences import ColumnPreferences
from sam.members.domain.preferred_list import PreferredList
from sam.members.domain.schedule import ScheduleEntry
from sam.members.domain.template import TemplateEntry
from sam.members.repository import table_design as td

from ._members_repository_shared import (
    MAIL_RUN_STATUS_QUEUED,
    Delegate,
    Member,
    Membership,
)


class MembersCreateMixin:
    """Create/save operations for every aggregate family."""

    def save_member(self, tenant_id: str, member: Member) -> Member:
        """Create or update a member, enforcing per-tenant member-number uniqueness.

        s5k: ``member_number`` (Lidnummer) is an OPTIONAL plain string the caller/import supplies
        — it may be empty. There is NO auto-generation and NO ``membernum#`` uniqueness guard:
        this is a single ``PutItem`` (no transaction). A duplicate member number is a
        data-quality concern, not a write-time conflict (the guard mechanism was removed — see
        spec s5k). The member is still keyed by its ``member_id`` (the internal row key).
        """
        self._require_tenant(tenant_id)
        member_id = member.get("member_id")
        if not member_id:
            raise ValueError("member must carry a non-empty 'member_id'")

        item = td.build_member_item(tenant_id, member_id, member)
        self.table.put_item(Item=item)
        return item

    def save_membership(
        self, tenant_id: str, member_id: str, membership: Membership
    ) -> Membership:
        self._require_tenant(tenant_id)
        membership_id = membership.get("membership_id")
        if not membership_id:
            raise ValueError("membership must carry a non-empty 'membership_id'")
        item = td.floats_to_decimal(dict(membership))  # DynamoDB-safe numbers
        item[td.PARTITION_KEY_ATTR] = tenant_id
        item[td.SORT_KEY_ATTR] = td.membership_sk(member_id, membership_id)
        item.setdefault("member_id", member_id)
        self.table.put_item(Item=item)
        return item

    def save_delegates(
        self, tenant_id: str, member_id: str, delegates: Sequence[Delegate]
    ) -> Sequence[Delegate]:
        """Replace the member's delegate set (stored as a single item under the member)."""
        self._require_tenant(tenant_id)
        stored = list(delegates)
        item = td.floats_to_decimal(
            {
                **td.build_key(tenant_id, td.delegates_sk(member_id)),
                "member_id": member_id,
                "delegates": stored,
            }
        )
        self.table.put_item(Item=item)
        return stored

    def save_analytics_set(
        self, tenant_id: str, entry: AnalyticsSetEntry
    ) -> AnalyticsSetEntry:
        """Create or update an analytics-set, validated before persist.

        The entry's own ``tenant_id`` must match the caller's ``tenant_id`` (no cross-tenant
        write, Property 1). :meth:`AnalyticsSetEntry.to_item` validates the shape, and
        :func:`table_design.build_analytics_set_item` stamps the authoritative primary key, so
        a malformed or misplaced entry can never be written.
        """
        self._require_tenant(tenant_id)
        if entry.tenant_id and entry.tenant_id != tenant_id:
            raise ValueError(
                f"entry.tenant_id {entry.tenant_id!r} does not match the caller tenant "
                f"{tenant_id!r} (no cross-tenant write, Property 1)"
            )
        bound = (
            entry
            if entry.tenant_id == tenant_id
            else replace(entry, tenant_id=tenant_id)
        )
        payload = bound.to_item()
        item = td.build_analytics_set_item(tenant_id, bound.set_id, payload)
        self.table.put_item(Item=item)
        return bound

    def save_template(self, tenant_id: str, entry: TemplateEntry) -> TemplateEntry:
        """Create or update a template, validated before persist.

        The entry's own ``tenant_id`` must match the caller's ``tenant_id`` (no cross-tenant
        write, Property 1). :meth:`TemplateEntry.to_item` validates the shape, and
        :func:`table_design.build_template_item` stamps the authoritative primary key, so a
        malformed or misplaced entry can never be written. Only the METADATA is persisted here;
        the body HTML / logo binary live in S3 and are written through the service's body-store
        seam.
        """
        self._require_tenant(tenant_id)
        if entry.tenant_id and entry.tenant_id != tenant_id:
            raise ValueError(
                f"entry.tenant_id {entry.tenant_id!r} does not match the caller tenant "
                f"{tenant_id!r} (no cross-tenant write, Property 1)"
            )
        bound = (
            entry
            if entry.tenant_id == tenant_id
            else replace(entry, tenant_id=tenant_id)
        )
        payload = bound.to_item()
        item = td.build_template_item(tenant_id, bound.template_id, payload)
        self.table.put_item(Item=item)
        return bound

    def save_schedule(self, tenant_id: str, entry: ScheduleEntry) -> ScheduleEntry:
        """Create or update a schedule, validated before persist.

        The entry's own ``tenant_id`` must match the caller's ``tenant_id`` (no cross-tenant
        write, Property 1). :meth:`ScheduleEntry.to_item` validates the shape, and
        :func:`table_design.build_schedule_item` stamps the authoritative primary key, so a
        malformed or misplaced entry can never be written. The tenant is PINNED in the schedule
        (an unattended run has no interactive user — R5); the "set must have a delivery block"
        rule (R5) is a SERVICE/route gate (task 5.2), NOT enforced here (storage-only entity).
        """
        self._require_tenant(tenant_id)
        if entry.tenant_id and entry.tenant_id != tenant_id:
            raise ValueError(
                f"entry.tenant_id {entry.tenant_id!r} does not match the caller tenant "
                f"{tenant_id!r} (no cross-tenant write, Property 1)"
            )
        bound = (
            entry
            if entry.tenant_id == tenant_id
            else replace(entry, tenant_id=tenant_id)
        )
        payload = bound.to_item()
        item = td.build_schedule_item(tenant_id, bound.schedule_id, payload)
        self.table.put_item(Item=item)
        return bound

    def save_preferred_list(
        self, tenant_id: str, entry: PreferredList
    ) -> PreferredList:
        """Create or REPLACE user ``sub``'s preferred list, validated before persist.

        The entry's own ``tenant_id`` must match the caller's ``tenant_id`` (no cross-tenant
        write, Property 1). A plain ``PutItem`` replaces the whole list (there is exactly one
        per user — R11.2). :meth:`PreferredList.to_item` validates the shape and
        :func:`table_design.build_pref_list_item` stamps the authoritative primary key, so a
        malformed or misplaced entry can never be written.
        """
        self._require_tenant(tenant_id)
        if entry.tenant_id and entry.tenant_id != tenant_id:
            raise ValueError(
                f"entry.tenant_id {entry.tenant_id!r} does not match the caller tenant "
                f"{tenant_id!r} (no cross-tenant write, Property 1)"
            )
        bound = (
            entry
            if entry.tenant_id == tenant_id
            else replace(entry, tenant_id=tenant_id)
        )
        payload = bound.to_item()
        item = td.build_pref_list_item(tenant_id, bound.sub, payload)
        self.table.put_item(Item=item)
        return bound

    def save_column_preferences(
        self, tenant_id: str, entry: ColumnPreferences
    ) -> ColumnPreferences:
        """Create or REPLACE user ``sub``'s column preferences, validated before persist.

        The entry's own ``tenant_id`` must match the caller's ``tenant_id`` (no cross-tenant
        write, Property 8). A plain ``PutItem`` replaces the whole list (there is exactly one
        per user — R6.5). :meth:`ColumnPreferences.to_item` validates the shape and
        :func:`table_design.build_column_prefs_item` stamps the authoritative primary key, so a
        malformed or misplaced entry can never be written.
        """
        self._require_tenant(tenant_id)
        if entry.tenant_id and entry.tenant_id != tenant_id:
            raise ValueError(
                f"entry.tenant_id {entry.tenant_id!r} does not match the caller tenant "
                f"{tenant_id!r} (no cross-tenant write, Property 8)"
            )
        bound = (
            entry
            if entry.tenant_id == tenant_id
            else replace(entry, tenant_id=tenant_id)
        )
        payload = bound.to_item()
        item = td.build_column_prefs_item(tenant_id, bound.sub, payload)
        self.table.put_item(Item=item)
        return bound

    def create_mail_run(
        self,
        tenant_id: str,
        run_id: str,
        *,
        mode: str,
        triggered_by: str | None,
        recipient_count: int,
    ) -> Mapping[str, Any]:
        """Write the ``mailrun#<run_id>`` tally at ENQUEUE with ``status=queued`` (R9.1).

        Idempotent on the ``run_id``: a re-enqueue of the SAME logical run (an at-least-once
        retry of the enqueue itself) must NOT clobber a run the worker has already advanced to
        ``sending`` / ``completed`` or whose counts it has incremented — so if a tally already
        exists this is a no-op that returns it. The first write sets ``sent=0`` / ``failed=0`` /
        ``status=queued`` + the TTL (default 90 days). Metadata only — never bodies / member PII.
        """
        self._require_tenant(tenant_id)
        if not run_id:
            raise ValueError("run_id must be non-empty")
        existing = self.get_mail_run(tenant_id, run_id)
        if existing is not None:
            return existing  # idempotent — don't reset an already-advanced run
        now = self._now_iso()
        entry = {
            "mode": mode,
            "triggered_by": triggered_by,
            "recipient_count": int(recipient_count),
            "status": MAIL_RUN_STATUS_QUEUED,
            "sent": 0,
            "failed": 0,
            "created_at": now,
            "updated_at": now,
            "ttl": self._ttl_epoch(),
        }
        item = td.build_mail_run_item(tenant_id, run_id, entry)
        self.table.put_item(Item=item)
        return item
