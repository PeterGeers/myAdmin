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
- Reads that list are **scope-narrowed in the domain layer** (the caller's ``allowed_scopes``
  are applied on top of the repository call — see ``MembershipService.list_members``). The
  repository does NOT push a scope filter into the query; isolation (``tenant_id`` as the
  partition key) is always enforced here regardless (design C4/C6).
- **Uniqueness** (member number per tenant) is a *data* invariant enforced here via a
  DynamoDB conditional write (Property 6) — never assumed by the domain layer.
- ``membership_type`` referential integrity against the Lidmaatschap Beheer catalog (C8) is
  a *domain* concern; the repository only persists the value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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


from ._members_repository_create import MembersCreateMixin
from ._members_repository_lifecycle import MembersLifecycleMixin
from ._members_repository_queries import MembersQueriesMixin
from ._members_repository_read import MembersReadMixin
from ._members_repository_shared import (  # noqa: F401 (surface compat)
    APP_SESSION_TTL_SECONDS,
    MAIL_RECIPIENT_STATUS_BOUNCED,
    MAIL_RECIPIENT_STATUS_COMPLAINT,
    MAIL_RECIPIENT_STATUS_FAILED,
    MAIL_RUN_STATUS_COMPLETED,
    MAIL_RUN_STATUS_QUEUED,
    MAIL_RUN_STATUS_SENDING,
    MAIL_RUN_TTL_SECONDS,
    Delegate,
    Member,
    Membership,
    Payment,
)
from ._members_repository_update import MembersUpdateMixin


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
    ) -> Sequence[Member]:
        """List the tenant's members for ``tenant_id``, optionally narrowed by ``filters``.

        Scope narrowing (the caller's ``allowed_scopes``) is a **domain-layer** concern applied
        on top of this call — see :meth:`MembershipService.list_members`. The repository only
        enforces tenant isolation (``tenant_id`` as partition key) and does not push a scope
        filter into the query.
        """
        ...

    def list_members_page(
        self,
        tenant_id: str,
        *,
        limit: int | None = None,
        start_key: Mapping[str, Any] | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[Sequence[Member], Mapping[str, Any] | None]:
        """Return up to ``limit`` of the tenant's MEMBER records + the resume cursor (Req 25).

        The cursor-paging read path. ``limit`` means **returned bare member records**, not raw
        partition items: because the partition interleaves members with their child items (which
        share the ``member#`` prefix), a tenant-pinned ``Query`` is LOOPED over
        ``LastEvaluatedKey`` until ``limit`` member records are collected (or the partition is
        exhausted). ``limit`` ``None`` (the ``Max`` option) returns one ~1 MB Query page's members
        (not all rows). ``start_key`` resumes a prior page (the decoded ``ExclusiveStartKey``,
        already tenant-checked). Returns ``(members, last_evaluated_key)`` where
        ``last_evaluated_key`` is positioned at the LAST member returned (an honest next-page
        cursor), or ``None`` on the final page. Scope narrowing stays a domain-layer concern
        applied on top; isolation (``tenant_id`` partition key) is enforced here regardless
        (Property 1).
        """
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

    # ── Public-application session de-dup (R3a, application-app task 2.1) ───────────────

    def claim_application_session(
        self, tenant_id: str, session_key: str, member_id: str
    ) -> bool:
        """Claim a public-application session for ``member_id`` iff unclaimed (R3a.3).

        Does a CONDITIONAL ``attribute_not_exists`` put of an ``appsession#<session_key>`` marker
        (the ``mailsent#<job_id>`` idempotency pattern) so only the FIRST submit of a session
        maps the session to its server-minted ``member_id``. Returns ``True`` iff THIS call
        created the marker (so the caller should create the member); ``False`` when the marker
        already existed (a resend — the caller should read the mapped member_id via
        :meth:`get_application_session_member` and UPDATE that record). Tenant-pinned (Property 1).
        """
        ...

    def get_application_session_member(
        self, tenant_id: str, session_key: str
    ) -> str | None:
        """Return the ``member_id`` a session mapped to, or ``None`` if the session is unclaimed.

        A single ``get_item`` on ``appsession#<session_key>`` within the tenant partition
        (isolation is structural — the partition key is pinned to ``tenant_id``). Used by a
        resend to resolve the record to UPDATE rather than insert a second one (R3a.2).
        """
        ...

    # ── Duplicate-flag name+DOB lookup (R3a.5–R3a.8, D25) ───────────────────────────────

    def query_by_name_dob(self, tenant_id: str, name_dob_key: str) -> Sequence[Member]:
        """Return members of ``tenant_id`` whose normalized name+DOB equals ``name_dob_key``.

        A cheap INDEXED read over the ``name_dob_index`` GSI (D25), NOT a partition scan
        (R3a.8). The GSI's hash key is ``tenant_id`` so the query stays inside the tenant
        partition (Property 1) and ``name_dob_key`` is its range key. Returns every matching
        member item (usually zero or one; more than one means pre-existing duplicates). Used
        FLAG-ONLY by the public create path — it never blocks a write (R3a.5/R3a.7).
        """
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

    def get_mail_run(self, tenant_id: str, run_id: str) -> Mapping[str, Any] | None:
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

    def list_members(self, tenant_id: str, *, filters=None):
        raise NotImplementedError(self._PENDING)

    def list_members_page(
        self, tenant_id: str, *, limit=None, start_key=None, filters=None
    ):
        raise NotImplementedError(self._PENDING)

    def save_member(self, tenant_id: str, member):
        raise NotImplementedError(self._PENDING)

    def delete_member(self, tenant_id: str, member_id: str):
        raise NotImplementedError(self._PENDING)

    def claim_application_session(
        self, tenant_id: str, session_key: str, member_id: str
    ):
        raise NotImplementedError(self._PENDING)

    def get_application_session_member(self, tenant_id: str, session_key: str):
        raise NotImplementedError(self._PENDING)

    def query_by_name_dob(self, tenant_id: str, name_dob_key: str):
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


class DynamoDbMembersRepository(
    MembersCreateMixin,
    MembersReadMixin,
    MembersUpdateMixin,
    MembersLifecycleMixin,
    MembersQueriesMixin,
):
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
