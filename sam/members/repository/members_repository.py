"""
S5 Task 1.0 — the Members **repository interface** (the sole DynamoDB touch-point; stubs).

Design C6, R3.1, and the layering steering: this interface is the ONLY seam the domain
layer uses to reach persistence, and it is where **tenant isolation lives**. The contract
below bakes that in structurally — **every** method takes ``tenant_id`` as its first
argument, so a caller literally cannot ask for data without naming the tenant, and the
concrete implementation keys every DynamoDB operation by it (partition key + IAM
``dynamodb:LeadingKeys``). A domain-layer bug therefore cannot read or write another
tenant's records (Property 1).

Scope of THIS task (1.0): **interface + stubs only.** Method bodies raise
:class:`NotImplementedError`; the tenant-scoped table shape (keys, counters,
member-payments) and the boto3-backed implementation are defined in task 1.4 and provisioned
in Step 4. The signatures here mirror the route map's behaviour groups (member CRUD,
membership lifecycle, delegates, member payments) so the read routes (Step 3) and write
routes (Step 5) have a stable seam to build against.

Design notes carried on the signatures (for the tasks that implement them):
- Reads that list are **scope-narrowed in the domain layer**, but the repository accepts an
  optional ``scope_filter`` so the narrowing can be pushed into the query where the key
  design allows (design C4/C6). Isolation (``tenant_id``) is always enforced regardless.
- **Uniqueness** (member number per tenant) is a *data* invariant enforced here via a
  DynamoDB conditional write (Property 6) — never assumed by the domain layer.
- ``membership_type`` referential integrity against the Lidmaatschap Beheer catalog (C8) is
  a *domain* concern; the repository only persists the value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from sam.members.domain.analytics_set import AnalyticsSetEntry
from sam.members.domain.column_preferences import ColumnPreferences
from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.domain.preferred_list import PreferredList
from sam.members.domain.schedule import ScheduleEntry
from sam.members.domain.template import TemplateEntry
from sam.members.repository import table_design as td

__all__ = [
    "DynamoDbMembersRepository",
    "MembersRepository",
]

# --- Send-run status constants (R9, mail-spec task 3.1) --------------------------------

#: How long a send-run status record (``mailrun#`` + its ``mailrecipient#`` failures) is retained
#: (seconds) via DynamoDB TTL — the design DEFAULT of 90 days. 90d covers ~3 monthly newsletter
#: cycles of look-back; the records are tiny metadata. TTL is best-effort auto-cleanup; a manual
#: delete (:meth:`DynamoDbMembersRepository.delete_mail_run`) is also supported. (Distinct from the
#: dedupe marker's 14d — a different, short-lived purpose.)
MAIL_RUN_TTL_SECONDS = 90 * 24 * 60 * 60

#: The send-run status lifecycle (R9.1): written ``queued`` at enqueue, advanced to ``sending`` /
#: ``completed`` by the worker as it drains the run's jobs.
MAIL_RUN_STATUS_QUEUED = "queued"
MAIL_RUN_STATUS_SENDING = "sending"
MAIL_RUN_STATUS_COMPLETED = "completed"

#: The FAILURE sub-record statuses (R9.5): a send-time ``failed`` or a late async ``bounced`` /
#: ``complaint`` (R8.4). A success is never stored (it is counted in the run tally).
MAIL_RECIPIENT_STATUS_FAILED = "failed"
MAIL_RECIPIENT_STATUS_BOUNCED = "bounced"
MAIL_RECIPIENT_STATUS_COMPLAINT = "complaint"


# Convenience aliases so the intent of each argument is legible in the signatures.
Member = Mapping[str, Any]
Membership = Mapping[str, Any]
Payment = Mapping[str, Any]
Delegate = Mapping[str, Any]


@runtime_checkable
class MembersRepository(Protocol):
    """The tenant-scoped persistence contract for the Members module (C6).

    Implementations are the only code that talks to DynamoDB. Every method is keyed by
    ``tenant_id`` (structural tenant isolation, Property 1). This is a ``Protocol`` so the
    domain layer depends on the shape, not a concrete class, and tests can supply an
    in-memory fake without inheritance.

    Task 1.0 ships a stub base (:class:`_StubMembersRepository` below) whose methods raise
    :class:`NotImplementedError`; the concrete implementation lands in task 1.4 / Step 4.
    """

    # ── Member CRUD ──────────────────────────────────────────────────────────────────

    def get_member(self, tenant_id: str, member_id: str) -> Member | None:
        """Return the member ``member_id`` for ``tenant_id``, or ``None`` if absent."""
        ...

    def list_members(
        self,
        tenant_id: str,
        *,
        filters: Mapping[str, Any] | None = None,
        scope_filter: Mapping[str, Sequence[str]] | None = None,
    ) -> Sequence[Member]:
        """List the tenant's members, optionally narrowed by filters / scope values."""
        ...

    def save_member(self, tenant_id: str, member: Member) -> Member:
        """Create or update a member for ``tenant_id``.

        Member-number uniqueness per tenant is enforced by a DynamoDB conditional write
        (Property 6); on conflict the implementation raises a uniqueness/conflict error the
        domain layer can surface — it never silently overwrites.
        """
        ...

    def delete_member(self, tenant_id: str, member_id: str) -> None:
        """Delete the member ``member_id`` for ``tenant_id``."""
        ...

    # ── Membership lifecycle ───────────────────────────────────────────────────────────

    def get_membership(
        self, tenant_id: str, member_id: str, membership_id: str
    ) -> Membership | None:
        """Return a single membership of a member, or ``None`` if absent."""
        ...

    def list_memberships(self, tenant_id: str, member_id: str) -> Sequence[Membership]:
        """List a member's memberships for ``tenant_id``."""
        ...

    def save_membership(
        self, tenant_id: str, member_id: str, membership: Membership
    ) -> Membership:
        """Create or update a membership for a member under ``tenant_id``."""
        ...

    def delete_membership(
        self, tenant_id: str, member_id: str, membership_id: str
    ) -> None:
        """Delete a membership of a member for ``tenant_id``."""
        ...

    # ── Delegates ──────────────────────────────────────────────────────────────────────

    def save_delegates(
        self, tenant_id: str, member_id: str, delegates: Sequence[Delegate]
    ) -> Sequence[Delegate]:
        """Replace the set of delegates for a member under ``tenant_id``."""
        ...

    def list_member_delegates(
        self, tenant_id: str, member_id: str
    ) -> Sequence[Delegate]:
        """List a member's delegate set for ``tenant_id`` (empty when none is stored)."""
        ...

    # ── Member-scoped payments ───────────────────────────────────────────────────────

    def list_member_payments(self, tenant_id: str, member_id: str) -> Sequence[Payment]:
        """List a member's payments for ``tenant_id``."""
        ...

    # ── Counters (member-number allocation, etc.) ──────────────────────────────────────

    # ── Lidmaatschap Beheer catalog (membership types, design C8) ──────────────────────

    def list_membership_types(
        self, tenant_id: str, *, active_only: bool = False
    ) -> Sequence[MembershipTypeEntry]:
        """List a tenant's membership-type catalog entries, presentation-ordered.

        ``active_only=True`` returns just the assignable types (the dropdown feed for
        new/edited members); the default returns all entries (incl. soft-deleted) for the
        management view. Results are ordered by ``(order, type_code)``. A tenant with no
        catalog yields an empty list (empty-by-default, C8).
        """
        ...

    def get_membership_type(
        self, tenant_id: str, type_code: str
    ) -> MembershipTypeEntry | None:
        """Return the catalog entry ``type_code`` for ``tenant_id``, or ``None`` if absent."""
        ...

    def save_membership_type(
        self, tenant_id: str, entry: MembershipTypeEntry
    ) -> MembershipTypeEntry:
        """Create or update a catalog entry for ``tenant_id`` (validated before persist)."""
        ...

    def deactivate_membership_type(
        self, tenant_id: str, type_code: str
    ) -> MembershipTypeEntry | None:
        """Soft-delete a catalog entry (``active=false``) — never a hard delete (C8).

        Deactivating keeps existing members' references valid while removing the type from the
        dropdown for new/edited members, so historical member records are never orphaned.
        Returns the deactivated entry, or ``None`` if no such entry exists.
        """
        ...

    # ── Analytics-sets (member saved-sets, F-012) ──────────────────────────────────

    def get_analytics_set(
        self, tenant_id: str, set_id: str
    ) -> AnalyticsSetEntry | None:
        """Return the analytics-set ``set_id`` for ``tenant_id``, or ``None`` if absent."""
        ...

    def list_analytics_sets(self, tenant_id: str) -> Sequence[AnalyticsSetEntry]:
        """List a tenant's analytics-set entries, sorted by ``(name, set_id)``."""
        ...

    def save_analytics_set(
        self, tenant_id: str, entry: AnalyticsSetEntry
    ) -> AnalyticsSetEntry:
        """Create or update an analytics-set for ``tenant_id`` (validated before persist)."""
        ...

    def delete_analytics_set(self, tenant_id: str, set_id: str) -> None:
        """Delete an analytics-set for ``tenant_id``."""
        ...

    # ── Mail templates (on-plane metadata, R2) ──────────────────────────────────────

    def get_template(self, tenant_id: str, template_id: str) -> TemplateEntry | None:
        """Return the template ``template_id`` for ``tenant_id``, or ``None`` if absent."""
        ...

    def list_templates(self, tenant_id: str) -> Sequence[TemplateEntry]:
        """List a tenant's template entries, sorted by ``(name, template_id)``."""
        ...

    def save_template(self, tenant_id: str, entry: TemplateEntry) -> TemplateEntry:
        """Create or update a template for ``tenant_id`` (validated before persist)."""
        ...

    def delete_template(self, tenant_id: str, template_id: str) -> None:
        """Delete a template for ``tenant_id``."""
        ...

    # ── Schedules (recurring run of a set + delivery, R5) ───────────────────────────

    def get_schedule(self, tenant_id: str, schedule_id: str) -> ScheduleEntry | None:
        """Return the schedule ``schedule_id`` for ``tenant_id``, or ``None`` if absent."""
        ...

    def list_schedules(self, tenant_id: str) -> Sequence[ScheduleEntry]:
        """List a tenant's schedule entries, sorted by ``(set_id, schedule_id)``."""
        ...

    def save_schedule(self, tenant_id: str, entry: ScheduleEntry) -> ScheduleEntry:
        """Create or update a schedule for ``tenant_id`` (validated before persist)."""
        ...

    def delete_schedule(self, tenant_id: str, schedule_id: str) -> None:
        """Delete a schedule for ``tenant_id``."""
        ...

    # ── Preferred lists (per-user, R11.2) ──────────────────────────────────────────

    def get_preferred_list(self, tenant_id: str, sub: str) -> PreferredList | None:
        """Return user ``sub``'s preferred list for ``tenant_id``, or ``None`` if unset."""
        ...

    def save_preferred_list(
        self, tenant_id: str, entry: PreferredList
    ) -> PreferredList:
        """Create or replace user ``sub``'s preferred list (validated before persist)."""
        ...

    # ── Column preferences (per-user overview columns, session-columns R6) ──────────

    def get_column_preferences(
        self, tenant_id: str, sub: str
    ) -> ColumnPreferences | None:
        """Return user ``sub``'s column preferences for ``tenant_id``, or ``None`` if unset."""
        ...

    def save_column_preferences(
        self, tenant_id: str, entry: ColumnPreferences
    ) -> ColumnPreferences:
        """Create or replace user ``sub``'s column preferences (validated before persist)."""
        ...

    # ── Send-run status (mailrun tally + FAILURE-ONLY sub-records, R9) ──────────────

    def create_mail_run(
        self,
        tenant_id: str,
        run_id: str,
        *,
        mode: str,
        triggered_by: str | None,
        recipient_count: int,
    ) -> Mapping[str, Any]:
        """Write a ``mailrun#<run_id>`` tally at ENQUEUE with ``status=queued`` (R9.1).

        Idempotent on the ``run_id`` (re-enqueuing the same logical run must not reset a run the
        worker has already advanced). Sets the TTL (default 90 days). Tenant-pinned (Property 3).
        """
        ...

    def update_mail_run_status(
        self, tenant_id: str, run_id: str, status: str
    ) -> Mapping[str, Any] | None:
        """Advance a run's ``status`` (``queued`` → ``sending`` → ``completed``), from the worker."""
        ...

    def increment_mail_run_counts(
        self, tenant_id: str, run_id: str, *, sent: int = 0, failed: int = 0
    ) -> Mapping[str, Any] | None:
        """Atomically add to a run's ``sent`` / ``failed`` tally as the worker processes jobs."""
        ...

    def record_mail_failure(
        self,
        tenant_id: str,
        run_id: str,
        *,
        address: str,
        status: str = MAIL_RECIPIENT_STATUS_FAILED,
        reason: str | None = None,
        message_id: str | None = None,
        adjust_run_tally: bool = False,
    ) -> Mapping[str, Any]:
        """Write a FAILURE-ONLY ``mailrecipient#<run_id>#<n>`` sub-record (R9.5).

        A send-time failure, or a LATE async bounce/complaint (R8.4) for a previously-sent
        recipient — the latter CREATES the sub-record at event time (``adjust_run_tally=True``
        also moves the run's tally from sent→failed). Sets the TTL (default 90 days). Tenant-pinned.
        """
        ...

    def get_mail_run(
        self, tenant_id: str, run_id: str
    ) -> Mapping[str, Any] | None:
        """Return a run's ``mailrun#<run_id>`` tally for ``tenant_id``, or ``None`` if absent."""
        ...

    def list_mail_run_failures(
        self, tenant_id: str, run_id: str
    ) -> Sequence[Mapping[str, Any]]:
        """List a run's FAILURE sub-records (``mailrecipient#<run_id>#…``), tenant-pinned."""
        ...

    def list_mail_runs(self, tenant_id: str) -> Sequence[Mapping[str, Any]]:
        """List a tenant's send-run tallies, newest first (feeds the status/history read route)."""
        ...

    def delete_mail_run(self, tenant_id: str, run_id: str) -> None:
        """Manual-delete a run tally AND all its FAILURE sub-records, tenant-pinned (R9 retention)."""
        ...


class _StubMembersRepository:
    """A do-nothing repository whose every method raises :class:`NotImplementedError`.

    The scaffold ships this so the wiring is importable and the interface is exercisable in
    tests, while making it impossible to accidentally rely on unbuilt persistence: any call
    fails loudly. Task 1.4 / Step 4 replace it with the boto3-backed, ``tenant_id``-keyed
    implementation. It structurally satisfies :class:`MembersRepository` (a ``Protocol``).
    """

    _PENDING = "MembersRepository is a task-1.0 stub; implemented in task 1.4 / Step 4"

    def get_member(self, tenant_id: str, member_id: str):
        raise NotImplementedError(self._PENDING)

    def list_members(self, tenant_id: str, *, filters=None, scope_filter=None):
        raise NotImplementedError(self._PENDING)

    def save_member(self, tenant_id: str, member):
        raise NotImplementedError(self._PENDING)

    def delete_member(self, tenant_id: str, member_id: str):
        raise NotImplementedError(self._PENDING)

    def get_membership(self, tenant_id: str, member_id: str, membership_id: str):
        raise NotImplementedError(self._PENDING)

    def list_memberships(self, tenant_id: str, member_id: str):
        raise NotImplementedError(self._PENDING)

    def save_membership(self, tenant_id: str, member_id: str, membership):
        raise NotImplementedError(self._PENDING)

    def delete_membership(self, tenant_id: str, member_id: str, membership_id: str):
        raise NotImplementedError(self._PENDING)

    def save_delegates(self, tenant_id: str, member_id: str, delegates):
        raise NotImplementedError(self._PENDING)

    def list_member_delegates(self, tenant_id: str, member_id: str):
        raise NotImplementedError(self._PENDING)

    def list_member_payments(self, tenant_id: str, member_id: str):
        raise NotImplementedError(self._PENDING)

    def list_membership_types(self, tenant_id: str, *, active_only: bool = False):
        raise NotImplementedError(self._PENDING)

    def get_membership_type(self, tenant_id: str, type_code: str):
        raise NotImplementedError(self._PENDING)

    def save_membership_type(self, tenant_id: str, entry):
        raise NotImplementedError(self._PENDING)

    def deactivate_membership_type(self, tenant_id: str, type_code: str):
        raise NotImplementedError(self._PENDING)

    def get_analytics_set(self, tenant_id: str, set_id: str):
        raise NotImplementedError(self._PENDING)

    def list_analytics_sets(self, tenant_id: str):
        raise NotImplementedError(self._PENDING)

    def save_analytics_set(self, tenant_id: str, entry):
        raise NotImplementedError(self._PENDING)

    def delete_analytics_set(self, tenant_id: str, set_id: str):
        raise NotImplementedError(self._PENDING)

    def get_template(self, tenant_id: str, template_id: str):
        raise NotImplementedError(self._PENDING)

    def list_templates(self, tenant_id: str):
        raise NotImplementedError(self._PENDING)

    def save_template(self, tenant_id: str, entry):
        raise NotImplementedError(self._PENDING)

    def delete_template(self, tenant_id: str, template_id: str):
        raise NotImplementedError(self._PENDING)

    def get_schedule(self, tenant_id: str, schedule_id: str):
        raise NotImplementedError(self._PENDING)

    def list_schedules(self, tenant_id: str):
        raise NotImplementedError(self._PENDING)

    def save_schedule(self, tenant_id: str, entry):
        raise NotImplementedError(self._PENDING)

    def delete_schedule(self, tenant_id: str, schedule_id: str):
        raise NotImplementedError(self._PENDING)

    def get_preferred_list(self, tenant_id: str, sub: str):
        raise NotImplementedError(self._PENDING)

    def save_preferred_list(self, tenant_id: str, entry):
        raise NotImplementedError(self._PENDING)

    def get_column_preferences(self, tenant_id: str, sub: str):
        raise NotImplementedError(self._PENDING)

    def save_column_preferences(self, tenant_id: str, entry):
        raise NotImplementedError(self._PENDING)

    def create_mail_run(
        self, tenant_id, run_id, *, mode, triggered_by, recipient_count
    ):
        raise NotImplementedError(self._PENDING)

    def update_mail_run_status(self, tenant_id, run_id, status):
        raise NotImplementedError(self._PENDING)

    def increment_mail_run_counts(self, tenant_id, run_id, *, sent=0, failed=0):
        raise NotImplementedError(self._PENDING)

    def record_mail_failure(
        self,
        tenant_id,
        run_id,
        *,
        address,
        status=MAIL_RECIPIENT_STATUS_FAILED,
        reason=None,
        message_id=None,
        adjust_run_tally=False,
    ):
        raise NotImplementedError(self._PENDING)

    def get_mail_run(self, tenant_id, run_id):
        raise NotImplementedError(self._PENDING)

    def list_mail_run_failures(self, tenant_id, run_id):
        raise NotImplementedError(self._PENDING)

    def list_mail_runs(self, tenant_id):
        raise NotImplementedError(self._PENDING)

    def delete_mail_run(self, tenant_id, run_id):
        raise NotImplementedError(self._PENDING)


# ── Task 1.4 — the concrete boto3-backed, tenant-scoped implementation ───────────────────


class DynamoDbMembersRepository:
    """The boto3-backed Members repository — the sole DynamoDB touch-point (design C6).

    Structurally satisfies :class:`MembersRepository` (a ``Protocol``) so the domain layer
    depends on the shape, not this class. Every method is keyed by ``tenant_id`` and every
    operation is scoped to that tenant's partition (``tenant_id`` PK), so no layer above can
    cross tenants even with a bug (Property 1). Isolation is structural (``tenant_id`` PK);
    writes are plain single-item ``PutItem``/``DeleteItem`` (s5k removed the member-number
    uniqueness guard + atomic counter — numbering is no longer generated or guarded).

    The table handle is **injected** (dependency-inversion) so tests supply an in-memory fake
    / local ``dynamodb-local`` table, and production resolves the fail-fast real table lazily
    via :func:`sam.members.repository.table_design.get_members_table_resource`.

    Args:
        table: A boto3 DynamoDB Table (or a compatible fake). If omitted, the real table is
            resolved lazily + fail-fast on first use.
        client: An optional boto3 DynamoDB *client*. If omitted, it is resolved lazily from the
            table's ``meta.client`` when needed.
    """

    def __init__(self, table=None, *, client=None):
        self._table = table
        self._client = client

    # ── lazy, fail-fast resource resolution ──────────────────────────────────────────

    @property
    def table(self):
        """The Members table, resolved lazily + fail-fast on first use."""
        if self._table is None:
            self._table = td.get_members_table_resource()
        return self._table

    @property
    def client(self):
        """The DynamoDB client for transactional writes (resolved from the table if needed)."""
        if self._client is None:
            self._client = self.table.meta.client
        return self._client

    @property
    def table_name(self) -> str:
        """The physical table name (needed to address items in a transaction)."""
        return self.table.name

    # ── internal helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _require_tenant(tenant_id: str) -> None:
        """Guard: no operation is allowed without an explicit tenant (Property 1)."""
        if not tenant_id:
            raise ValueError(
                "tenant_id is required — every Members operation is tenant-scoped "
                "(no cross-tenant access, Property 1)"
            )

    def _query_prefix(self, tenant_id: str, sk_prefix: str) -> list[dict]:
        """Query one tenant partition for items whose SK begins with ``sk_prefix``.

        The partition key is pinned to ``tenant_id`` (isolation) and the sort-key
        ``begins_with`` narrows to the requested sub-tree — still entirely inside the tenant's
        partition. Paginates via ``LastEvaluatedKey`` so large members are fully returned.
        """
        from boto3.dynamodb.conditions import Key

        condition = Key(td.PARTITION_KEY_ATTR).eq(tenant_id) & Key(
            td.SORT_KEY_ATTR
        ).begins_with(sk_prefix)

        items: list[dict] = []
        kwargs: dict = {"KeyConditionExpression": condition}
        while True:
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []) or [])
            last = response.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        return items

    # ── Member CRUD ────────────────────────────────────────────────────────────────────

    def get_member(self, tenant_id: str, member_id: str) -> Member | None:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.member_sk(member_id))
        )
        return response.get("Item")

    def list_members(
        self,
        tenant_id: str,
        *,
        filters: Mapping[str, Any] | None = None,
        scope_filter: Mapping[str, Sequence[str]] | None = None,
    ) -> Sequence[Member]:
        """List the tenant's member records (SK ``member#<id>`` exactly, not their children).

        Isolation is structural: the query pins ``tenant_id`` as the partition key. ``filters``
        / ``scope_filter`` narrowing is a **domain-layer** concern (a scoped user stays inside
        their tenant); this method surfaces the tenant's members and leaves narrowing to the
        caller unless a future key design lets the filter be pushed down. Child items
        (memberships/delegates/payments/counters/guards) are excluded by shape.
        """
        self._require_tenant(tenant_id)
        members: list[dict] = []
        # A member *record* SK has exactly two segments: ("member", <member_id>). We query
        # every ``member#...`` item in the partition and keep only the bare records (child
        # items — memberships/delegates/payments — share the ``member#`` prefix but have more
        # segments), so a list never leaks a member's sub-entities.
        prefix = td.RECORD_TYPE_MEMBER + td.SORT_KEY_SEPARATOR
        for item in self._query_prefix(tenant_id, prefix):
            segments = td.split_sort_key(item.get(td.SORT_KEY_ATTR, ""))
            if len(segments) == 2 and segments[0] == td.RECORD_TYPE_MEMBER:
                members.append(item)
        return members

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

    def delete_member(self, tenant_id: str, member_id: str) -> None:
        """Delete a member record.

        s5k: a single ``DeleteItem`` of the member record. There is no ``membernum#`` guard to
        release (the uniqueness-guard mechanism was removed — see spec s5k), so no transaction is
        needed. (Memberships/delegates/payments are removed by the domain layer's higher-level
        flows / Step 5.)
        """
        self._require_tenant(tenant_id)
        self.table.delete_item(Key=td.build_key(tenant_id, td.member_sk(member_id)))

    # ── Membership lifecycle ───────────────────────────────────────────────────────────

    def get_membership(
        self, tenant_id: str, member_id: str, membership_id: str
    ) -> Membership | None:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.membership_sk(member_id, membership_id))
        )
        return response.get("Item")

    def list_memberships(self, tenant_id: str, member_id: str) -> Sequence[Membership]:
        self._require_tenant(tenant_id)
        prefix = td.build_sort_key(
            td.RECORD_TYPE_MEMBER, member_id, td.RECORD_TYPE_MEMBERSHIP
        )
        return self._query_prefix(tenant_id, prefix)

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

    def delete_membership(
        self, tenant_id: str, member_id: str, membership_id: str
    ) -> None:
        self._require_tenant(tenant_id)
        self.table.delete_item(
            Key=td.build_key(tenant_id, td.membership_sk(member_id, membership_id))
        )

    # ── Delegates ──────────────────────────────────────────────────────────────────────

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

    def list_member_delegates(
        self, tenant_id: str, member_id: str
    ) -> Sequence[Delegate]:
        """Return a member's stored delegate set (empty list when none exists).

        The delegate set is a single item under the member (``member#<id>#delegates``); this
        reads it within the tenant partition (isolation is structural — Property 1) and
        returns its ``delegates`` list, or ``[]`` when the member has no delegate item yet.
        """
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.delegates_sk(member_id))
        )
        item = response.get("Item")
        if not item:
            return []
        delegates = item.get("delegates")
        return list(delegates) if isinstance(delegates, (list, tuple)) else []

    # ── Member-scoped payments ───────────────────────────────────────────────────────

    def list_member_payments(self, tenant_id: str, member_id: str) -> Sequence[Payment]:
        self._require_tenant(tenant_id)
        prefix = td.build_sort_key(
            td.RECORD_TYPE_MEMBER, member_id, td.RECORD_TYPE_PAYMENT
        )
        return self._query_prefix(tenant_id, prefix)

    # ── Lidmaatschap Beheer catalog (membership types, design C8) ──────────────────────

    def list_membership_types(
        self, tenant_id: str, *, active_only: bool = False
    ) -> Sequence[MembershipTypeEntry]:
        """List the tenant's membership-type catalog entries, presentation-ordered.

        Queries the ``membershiptype#`` sub-tree of the tenant partition (isolation is
        structural — the partition key is pinned to ``tenant_id``), rebuilds each stored item
        into a :class:`MembershipTypeEntry`, optionally drops soft-deleted entries, and sorts
        by ``(order, type_code)`` so the dropdown/management view render deterministically.
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_MEMBERSHIP_TYPE + td.SORT_KEY_SEPARATOR
        entries = [
            MembershipTypeEntry.from_item(item)
            for item in self._query_prefix(tenant_id, prefix)
        ]
        if active_only:
            entries = [e for e in entries if e.active]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    def get_membership_type(
        self, tenant_id: str, type_code: str
    ) -> MembershipTypeEntry | None:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.membership_type_sk(type_code))
        )
        item = response.get("Item")
        return MembershipTypeEntry.from_item(item) if item is not None else None

    def save_membership_type(
        self, tenant_id: str, entry: MembershipTypeEntry
    ) -> MembershipTypeEntry:
        """Create or update a catalog entry, validated before persist.

        The entry's own ``tenant_id`` must match the caller's ``tenant_id`` (no cross-tenant
        write, Property 1). :meth:`MembershipTypeEntry.to_item` validates the shape, and
        :func:`table_design.build_membership_type_item` stamps the authoritative primary key,
        so a malformed or misplaced entry can never be written.
        """
        self._require_tenant(tenant_id)
        if entry.tenant_id and entry.tenant_id != tenant_id:
            raise ValueError(
                f"entry.tenant_id {entry.tenant_id!r} does not match the caller tenant "
                f"{tenant_id!r} (no cross-tenant write, Property 1)"
            )
        # Bind the entry to the caller's tenant, then validate + serialize.
        bound = (
            entry
            if entry.tenant_id == tenant_id
            else replace(entry, tenant_id=tenant_id)
        )
        payload = bound.to_item()
        item = td.build_membership_type_item(tenant_id, bound.type_code, payload)
        self.table.put_item(Item=item)
        return bound

    def deactivate_membership_type(
        self, tenant_id: str, type_code: str
    ) -> MembershipTypeEntry | None:
        """Soft-delete a catalog entry (``active=false``) — never a hard delete (C8).

        Reads the entry, flips ``active`` to ``False``, and re-persists it, so existing member
        references stay valid while the type leaves the dropdown for new/edited members.
        Returns the deactivated entry, or ``None`` if no such entry exists.
        """
        self._require_tenant(tenant_id)
        existing = self.get_membership_type(tenant_id, type_code)
        if existing is None:
            return None
        if not existing.active:
            return existing  # already soft-deleted — idempotent
        return self.save_membership_type(tenant_id, existing.deactivated())

    # ── Analytics-sets (member saved-sets, F-012) ──────────────────────────────────

    def get_analytics_set(
        self, tenant_id: str, set_id: str
    ) -> AnalyticsSetEntry | None:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.analytics_set_sk(set_id))
        )
        item = response.get("Item")
        return AnalyticsSetEntry.from_item(item) if item is not None else None

    def list_analytics_sets(self, tenant_id: str) -> Sequence[AnalyticsSetEntry]:
        """List the tenant's analytics-set entries, sorted by ``(name, set_id)``.

        Queries the ``analyticsset#`` sub-tree of the tenant partition (isolation is
        structural — the partition key is pinned to ``tenant_id``), rebuilds each stored item
        into an :class:`AnalyticsSetEntry`, and sorts by ``(name, set_id)`` so the list renders
        deterministically.
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_ANALYTICS_SET + td.SORT_KEY_SEPARATOR
        entries = [
            AnalyticsSetEntry.from_item(item)
            for item in self._query_prefix(tenant_id, prefix)
        ]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

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

    def delete_analytics_set(self, tenant_id: str, set_id: str) -> None:
        """Hard-delete an analytics-set (F-012 — no referencing records to orphan)."""
        self._require_tenant(tenant_id)
        self.table.delete_item(Key=td.build_key(tenant_id, td.analytics_set_sk(set_id)))

    # ── Mail templates (on-plane metadata, R2) ──────────────────────────────────────

    def get_template(self, tenant_id: str, template_id: str) -> TemplateEntry | None:
        """Return the template ``template_id`` for ``tenant_id``, or ``None`` if absent.

        A single ``get_item`` on ``template#<template_id>`` within the tenant partition
        (isolation is structural — the partition key is pinned to ``tenant_id``).
        """
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.template_sk(template_id))
        )
        item = response.get("Item")
        return TemplateEntry.from_item(item) if item is not None else None

    def list_templates(self, tenant_id: str) -> Sequence[TemplateEntry]:
        """List the tenant's template entries, sorted by ``(name, template_id)``.

        Queries the ``template#`` sub-tree of the tenant partition (isolation is structural —
        the partition key is pinned to ``tenant_id``), rebuilds each stored item into a
        :class:`TemplateEntry`, and sorts by ``(name, template_id)`` so the list renders
        deterministically.
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_TEMPLATE + td.SORT_KEY_SEPARATOR
        entries = [
            TemplateEntry.from_item(item)
            for item in self._query_prefix(tenant_id, prefix)
        ]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

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

    def delete_template(self, tenant_id: str, template_id: str) -> None:
        """Hard-delete a template's metadata item for ``tenant_id``.

        Deletes only the ``template#<template_id>`` metadata item; the service is responsible
        for cleaning up the template's S3 body/logo objects through its body-store seam.
        """
        self._require_tenant(tenant_id)
        self.table.delete_item(
            Key=td.build_key(tenant_id, td.template_sk(template_id))
        )

    # ── Schedules (recurring run of a set + delivery, R5) ───────────────────────────

    def get_schedule(self, tenant_id: str, schedule_id: str) -> ScheduleEntry | None:
        """Return the schedule ``schedule_id`` for ``tenant_id``, or ``None`` if absent.

        A single ``get_item`` on ``schedule#<schedule_id>`` within the tenant partition
        (isolation is structural — the partition key is pinned to ``tenant_id``).
        """
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.schedule_sk(schedule_id))
        )
        item = response.get("Item")
        return ScheduleEntry.from_item(item) if item is not None else None

    def list_schedules(self, tenant_id: str) -> Sequence[ScheduleEntry]:
        """List the tenant's schedule entries, sorted by ``(set_id, schedule_id)``.

        Queries the ``schedule#`` sub-tree of the tenant partition (isolation is structural —
        the partition key is pinned to ``tenant_id``), rebuilds each stored item into a
        :class:`ScheduleEntry`, and sorts by ``(set_id, schedule_id)`` so the list renders
        deterministically.
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_SCHEDULE + td.SORT_KEY_SEPARATOR
        entries = [
            ScheduleEntry.from_item(item)
            for item in self._query_prefix(tenant_id, prefix)
        ]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

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

    def delete_schedule(self, tenant_id: str, schedule_id: str) -> None:
        """Hard-delete a schedule for ``tenant_id`` (no referencing records to orphan)."""
        self._require_tenant(tenant_id)
        self.table.delete_item(
            Key=td.build_key(tenant_id, td.schedule_sk(schedule_id))
        )

    # ── Preferred lists (per-user, R11.2) ──────────────────────────────────────────

    def get_preferred_list(self, tenant_id: str, sub: str) -> PreferredList | None:
        """Return user ``sub``'s preferred list for ``tenant_id``, or ``None`` if unset.

        A single ``get_item`` on ``preflist#<sub>`` within the tenant partition (isolation is
        structural — the partition key is pinned to ``tenant_id``). A missing item → ``None``
        (the domain treats that as an empty list — empty-is-valid, R11).
        """
        self._require_tenant(tenant_id)
        if not sub:
            return None
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.pref_list_sk(sub))
        )
        item = response.get("Item")
        return PreferredList.from_item(item) if item is not None else None

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

    # ── Column preferences (per-user overview columns, session-columns R6) ──────────

    def get_column_preferences(
        self, tenant_id: str, sub: str
    ) -> ColumnPreferences | None:
        """Return user ``sub``'s column preferences for ``tenant_id``, or ``None`` if unset.

        A single ``get_item`` on ``colprefs#<sub>`` within the tenant partition (isolation is
        structural — the partition key is pinned to ``tenant_id``). A missing item → ``None``
        (the domain treats that as an empty column set — empty-is-valid, R6.4).
        """
        self._require_tenant(tenant_id)
        if not sub:
            return None
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.column_prefs_sk(sub))
        )
        item = response.get("Item")
        return ColumnPreferences.from_item(item) if item is not None else None

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

    # ── Send-run status (mailrun tally + FAILURE-ONLY sub-records, R9) ──────────────
    #
    # The design's DECIDED model (design "Resolved implementation choices"): a SUMMARY TALLY
    # (``mailrun#<run_id>``) + FAILURE-ONLY sub-records (``mailrecipient#<run_id>#<n>``).
    # Successful recipients are only COUNTED in the run tally — never stored per-recipient. The
    # enqueue path writes the ``queued`` tally with the recipient count; the worker advances the
    # status and increments ``sent`` / ``failed`` and, on a failure (incl. a late async
    # bounce/complaint — R8.4), writes a failure sub-record. Both record kinds carry a ``ttl``
    # epoch attribute (DynamoDB TTL, default 90 days) and support a manual delete. Every op pins
    # ``tenant_id`` (Property 3 — these metadata records can only ever match within their tenant).

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _ttl_epoch() -> int:
        """The DynamoDB TTL epoch (default 90 days from now) for a send-run status record."""
        from sam.members.repository.members_repository import MAIL_RUN_TTL_SECONDS

        return int(datetime.now(timezone.utc).timestamp()) + MAIL_RUN_TTL_SECONDS

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

    def update_mail_run_status(
        self, tenant_id: str, run_id: str, status: str
    ) -> Mapping[str, Any] | None:
        """Advance a run's ``status`` from the worker (``queued`` → ``sending`` → ``completed``).

        A read-modify-write of the tenant-pinned tally (the worker drains one job at a time —
        BatchSize 1 — so there is no concurrent writer to race). Returns the updated tally, or
        ``None`` when no such run exists (nothing to advance). ``ttl`` / ``created_at`` are
        preserved; ``updated_at`` is refreshed.
        """
        self._require_tenant(tenant_id)
        if status not in (
            MAIL_RUN_STATUS_QUEUED,
            MAIL_RUN_STATUS_SENDING,
            MAIL_RUN_STATUS_COMPLETED,
        ):
            raise ValueError(f"unknown mail-run status {status!r}")
        current = self.get_mail_run(tenant_id, run_id)
        if current is None:
            return None
        updated = dict(current)
        updated["status"] = status
        updated["updated_at"] = self._now_iso()
        item = td.build_mail_run_item(tenant_id, run_id, updated)
        self.table.put_item(Item=item)
        return item

    def increment_mail_run_counts(
        self, tenant_id: str, run_id: str, *, sent: int = 0, failed: int = 0
    ) -> Mapping[str, Any] | None:
        """Add to a run's ``sent`` / ``failed`` tally as the worker processes jobs (R9.1).

        A read-modify-write of the tenant-pinned tally (worker BatchSize 1 — no concurrent
        writer). Returns the updated tally, or ``None`` when no such run exists. Negative deltas
        are supported so a late bounce can move a count from sent→failed (see
        :meth:`record_mail_failure` with ``adjust_run_tally=True``); the tally is floored at 0.
        """
        self._require_tenant(tenant_id)
        current = self.get_mail_run(tenant_id, run_id)
        if current is None:
            return None
        updated = dict(current)
        updated["sent"] = max(0, int(updated.get("sent", 0)) + int(sent))
        updated["failed"] = max(0, int(updated.get("failed", 0)) + int(failed))
        updated["updated_at"] = self._now_iso()
        item = td.build_mail_run_item(tenant_id, run_id, updated)
        self.table.put_item(Item=item)
        return item

    def record_mail_failure(
        self,
        tenant_id: str,
        run_id: str,
        *,
        address: str,
        status: str = MAIL_RECIPIENT_STATUS_FAILED,
        reason: str | None = None,
        message_id: str | None = None,
        adjust_run_tally: bool = False,
    ) -> Mapping[str, Any]:
        """Write a FAILURE-ONLY ``mailrecipient#<run_id>#<n>`` sub-record (R9.5, design decision).

        Written ONLY for a failure — a send-time reject / no-address, or a LATE async
        bounce/complaint (R8.4) for a recipient that SUCCEEDED at send time (there is no
        sub-record yet, since successes are only counted). ``adjust_run_tally=True`` is the late
        path: it ALSO moves the run tally from sent→failed (``sent -= 1`` / ``failed += 1``),
        since the recipient was previously counted as sent. The ``<n>`` sort-key segment is the
        run's current failure COUNT (``failed``) so two failures never collide. Sets the TTL
        (default 90 days). Tenant-pinned (Property 3). Metadata only — the ``reason`` is an SES
        code/message, never member PII beyond the address being mailed.
        """
        self._require_tenant(tenant_id)
        if not run_id:
            raise ValueError("run_id must be non-empty")
        if status not in (
            MAIL_RECIPIENT_STATUS_FAILED,
            MAIL_RECIPIENT_STATUS_BOUNCED,
            MAIL_RECIPIENT_STATUS_COMPLAINT,
        ):
            raise ValueError(f"unknown mail-recipient failure status {status!r}")

        # The failure sequence is the run's failure count SO FAR (0-based) — a stable, collision-
        # free per-run discriminator. Fall back to the number of existing sub-records if the run
        # tally is absent (defensive — a late bounce could arrive after a manual run delete).
        run = self.get_mail_run(tenant_id, run_id)
        if run is not None:
            seq = int(run.get("failed", 0))
        else:
            seq = len(self.list_mail_run_failures(tenant_id, run_id))

        entry: dict[str, Any] = {
            "address": address,
            "status": status,
            "updated_at": self._now_iso(),
            "ttl": self._ttl_epoch(),
        }
        if reason is not None:
            entry["reason"] = reason
        if message_id is not None:
            entry["message_id"] = message_id
        item = td.build_mail_recipient_item(tenant_id, run_id, str(seq), entry)
        self.table.put_item(Item=item)

        # Adjust the run tally. On the LATE path the recipient was previously counted as sent, so
        # move it sent→failed; otherwise just increment failed (a send-time failure the worker is
        # recording as it processes the job).
        if run is not None:
            if adjust_run_tally:
                self.increment_mail_run_counts(tenant_id, run_id, sent=-1, failed=1)
            else:
                self.increment_mail_run_counts(tenant_id, run_id, failed=1)
        return item

    def get_mail_run(
        self, tenant_id: str, run_id: str
    ) -> Mapping[str, Any] | None:
        """Return the ``mailrun#<run_id>`` tally for ``tenant_id``, or ``None`` if absent.

        A single ``get_item`` within the tenant partition (isolation is structural — the
        partition key is pinned to ``tenant_id``; Property 3).
        """
        self._require_tenant(tenant_id)
        if not run_id:
            return None
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.mail_run_sk(run_id))
        )
        return response.get("Item")

    def list_mail_run_failures(
        self, tenant_id: str, run_id: str
    ) -> Sequence[Mapping[str, Any]]:
        """List a run's FAILURE sub-records (``mailrecipient#<run_id>#…``), tenant-pinned.

        A ``begins_with`` query on the run's failure prefix inside the tenant partition
        (isolation is structural — Property 3). An empty list when the run had no failures
        (the common case — successes are only counted in the tally, not stored).
        """
        self._require_tenant(tenant_id)
        if not run_id:
            return []
        prefix = td.mail_recipient_sk_prefix(run_id) + td.SORT_KEY_SEPARATOR
        return self._query_prefix(tenant_id, prefix)

    def list_mail_runs(self, tenant_id: str) -> Sequence[Mapping[str, Any]]:
        """List the tenant's send-run tallies, NEWEST FIRST (feeds the R9 status/history route).

        Queries the ``mailrun#`` sub-tree of the tenant partition (isolation is structural — the
        partition key is pinned to ``tenant_id``; Property 3) and sorts by ``created_at``
        descending so the history view shows the most recent runs first. Returns only the TALLY
        items (the ``mailrecipient#`` failures live under a different record-type prefix, so they
        are never swept in here).
        """
        self._require_tenant(tenant_id)
        prefix = td.RECORD_TYPE_MAIL_RUN + td.SORT_KEY_SEPARATOR
        runs = list(self._query_prefix(tenant_id, prefix))
        runs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return runs

    def delete_mail_run(self, tenant_id: str, run_id: str) -> None:
        """Manual-delete a run tally AND all its FAILURE sub-records (R9 retention; tenant-pinned).

        Deletes the ``mailrun#<run_id>`` tally and every ``mailrecipient#<run_id>#…`` failure
        sub-record so a manual delete leaves no orphaned failures behind (the complement to the
        TTL auto-cleanup). Every delete is keyed by ``tenant_id`` (Property 3).
        """
        self._require_tenant(tenant_id)
        if not run_id:
            raise ValueError("run_id must be non-empty")
        for failure in self.list_mail_run_failures(tenant_id, run_id):
            sk = failure.get(td.SORT_KEY_ATTR)
            if sk:
                self.table.delete_item(Key=td.build_key(tenant_id, sk))
        self.table.delete_item(
            Key=td.build_key(tenant_id, td.mail_run_sk(run_id))
        )
