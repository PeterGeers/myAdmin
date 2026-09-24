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

from dataclasses import replace
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.repository import table_design as td

__all__ = [
    "MembersRepository",
    "DynamoDbMembersRepository",
]

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

    def get_member(self, tenant_id: str, member_id: str) -> Optional[Member]:
        """Return the member ``member_id`` for ``tenant_id``, or ``None`` if absent."""
        ...

    def list_members(
        self,
        tenant_id: str,
        *,
        filters: Optional[Mapping[str, Any]] = None,
        scope_filter: Optional[Mapping[str, Sequence[str]]] = None,
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
    ) -> Optional[Membership]:
        """Return a single membership of a member, or ``None`` if absent."""
        ...

    def list_memberships(
        self, tenant_id: str, member_id: str
    ) -> Sequence[Membership]:
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

    def list_member_payments(
        self, tenant_id: str, member_id: str
    ) -> Sequence[Payment]:
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
    ) -> Optional[MembershipTypeEntry]:
        """Return the catalog entry ``type_code`` for ``tenant_id``, or ``None`` if absent."""
        ...

    def save_membership_type(
        self, tenant_id: str, entry: MembershipTypeEntry
    ) -> MembershipTypeEntry:
        """Create or update a catalog entry for ``tenant_id`` (validated before persist)."""
        ...

    def deactivate_membership_type(
        self, tenant_id: str, type_code: str
    ) -> Optional[MembershipTypeEntry]:
        """Soft-delete a catalog entry (``active=false``) — never a hard delete (C8).

        Deactivating keeps existing members' references valid while removing the type from the
        dropdown for new/edited members, so historical member records are never orphaned.
        Returns the deactivated entry, or ``None`` if no such entry exists.
        """
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

    def get_member(self, tenant_id: str, member_id: str) -> Optional[Member]:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.member_sk(member_id))
        )
        return response.get("Item")

    def list_members(
        self,
        tenant_id: str,
        *,
        filters: Optional[Mapping[str, Any]] = None,
        scope_filter: Optional[Mapping[str, Sequence[str]]] = None,
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
    ) -> Optional[Membership]:
        self._require_tenant(tenant_id)
        response = self.table.get_item(
            Key=td.build_key(tenant_id, td.membership_sk(member_id, membership_id))
        )
        return response.get("Item")

    def list_memberships(
        self, tenant_id: str, member_id: str
    ) -> Sequence[Membership]:
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
        item = td.floats_to_decimal({
            **td.build_key(tenant_id, td.delegates_sk(member_id)),
            "member_id": member_id,
            "delegates": stored,
        })
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

    def list_member_payments(
        self, tenant_id: str, member_id: str
    ) -> Sequence[Payment]:
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
    ) -> Optional[MembershipTypeEntry]:
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
        bound = entry if entry.tenant_id == tenant_id else replace(entry, tenant_id=tenant_id)
        payload = bound.to_item()
        item = td.build_membership_type_item(tenant_id, bound.type_code, payload)
        self.table.put_item(Item=item)
        return bound

    def deactivate_membership_type(
        self, tenant_id: str, type_code: str
    ) -> Optional[MembershipTypeEntry]:
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
