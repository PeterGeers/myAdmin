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
    "MemberNumberConflictError",
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

    def next_counter(self, tenant_id: str, counter_name: str) -> int:
        """Atomically increment and return a named per-tenant counter.

        Backed by a DynamoDB atomic ``ADD`` so concurrent invocations never collide — the
        data layer owns atomicity (Property 6). Used e.g. to derive member numbers.
        """
        ...

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

    def next_counter(self, tenant_id: str, counter_name: str) -> int:
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


class MemberNumberConflictError(Exception):
    """Raised when a ``save_member`` would violate per-tenant member-number uniqueness.

    Surfaced by :class:`DynamoDbMembersRepository` when the DynamoDB conditional write on the
    ``membernum#<member_number>`` guard fails — i.e. another member in the same tenant already
    claims that number (Property 6). The domain layer turns this into a 409/validation error;
    the repository never silently overwrites.
    """

    def __init__(self, tenant_id: str, member_number: str):
        self.tenant_id = tenant_id
        self.member_number = member_number
        super().__init__(
            f"member number {member_number!r} is already taken for tenant "
            f"{tenant_id!r} (per-tenant uniqueness, Property 6)"
        )


class DynamoDbMembersRepository:
    """The boto3-backed Members repository — the sole DynamoDB touch-point (design C6).

    Structurally satisfies :class:`MembersRepository` (a ``Protocol``) so the domain layer
    depends on the shape, not this class. Every method is keyed by ``tenant_id`` and every
    operation is scoped to that tenant's partition (``tenant_id`` PK), so no layer above can
    cross tenants even with a bug (Property 1). Data-integrity invariants live here:

    - **Member-number uniqueness per tenant** via a ``TransactWriteItems`` that writes the
      member item alongside a ``membernum#<member_number>`` guard carrying an
      ``attribute_not_exists`` condition — a racing writer fails atomically (Property 6).
    - **Atomic counters** via a DynamoDB atomic ``ADD`` update (Property 6).

    The table handle is **injected** (dependency-inversion) so tests supply an in-memory fake
    / local ``dynamodb-local`` table, and production resolves the fail-fast real table lazily
    via :func:`sam.members.repository.table_design.get_members_table_resource`.

    Args:
        table: A boto3 DynamoDB Table (or a compatible fake). If omitted, the real table is
            resolved lazily + fail-fast on first use.
        client: An optional boto3 DynamoDB *client* used for ``transact_write_items`` (the
            resource-level ``Table`` has no transaction API). If omitted, it is resolved
            lazily from the table's ``meta.client`` when a transactional write is needed.
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

    @staticmethod
    def _is_conditional_check_failed(error: Exception) -> bool:
        """True if ``error`` is a DynamoDB conditional-check failure (transactional or not)."""
        response = getattr(error, "response", None) or {}
        code = response.get("Error", {}).get("Code", "")
        if code in ("ConditionalCheckFailedException", "TransactionCanceledException"):
            return True
        # TransactionCanceledException surfaces per-item reasons; a ConditionalCheckFailed
        # reason means our uniqueness guard tripped.
        reasons = response.get("CancellationReasons") or []
        return any(r.get("Code") == "ConditionalCheckFailed" for r in reasons)

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

        The member number (``membership.member_number``) is guarded by a dedicated
        ``membernum#<number>`` item written in the SAME transaction as the member item, under
        an ``attribute_not_exists`` condition. A concurrent writer racing for the same number
        loses the transaction and this raises :class:`MemberNumberConflictError` — uniqueness
        holds even under concurrency (Property 6), and is never assumed by the domain layer.

        For an idempotent re-save of the SAME member (same ``member_id`` + same number) the
        guard already points at this member, so the write is allowed; a guard that points at a
        *different* member is a real conflict.
        """
        self._require_tenant(tenant_id)
        member_id = member.get("member_id")
        if not member_id:
            raise ValueError("member must carry a non-empty 'member_id'")
        membership = member.get("membership") or {}
        member_number = membership.get("member_number")
        if not member_number:
            raise ValueError(
                "member.membership.member_number is required (uniqueness invariant, Property 6)"
            )

        item = td.build_member_item(tenant_id, member_id, member)
        guard_key = td.build_key(tenant_id, td.member_number_sk(member_number))

        # The guard either does not exist yet, or already belongs to THIS member (idempotent
        # re-save). Either passes; a guard owned by a different member fails the condition.
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": item,
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": {
                                **guard_key,
                                "member_id": member_id,
                                "member_number": member_number,
                            },
                            "ConditionExpression": (
                                "attribute_not_exists(#pk) OR #owner = :member_id"
                            ),
                            "ExpressionAttributeNames": {
                                "#pk": td.PARTITION_KEY_ATTR,
                                "#owner": "member_id",
                            },
                            "ExpressionAttributeValues": {":member_id": member_id},
                        }
                    },
                ]
            )
        except Exception as exc:  # boto3 ClientError (or a fake's stand-in)
            if self._is_conditional_check_failed(exc):
                raise MemberNumberConflictError(tenant_id, member_number) from exc
            raise
        return item

    def delete_member(self, tenant_id: str, member_id: str) -> None:
        """Delete a member record and release its member-number uniqueness guard.

        Reads the member to discover its member number, then deletes the member item and the
        matching ``membernum#`` guard in one transaction so the number can be reused and no
        orphaned guard blocks a future member. (Memberships/delegates/payments are removed by
        the domain layer's higher-level flows / Step 5.)
        """
        self._require_tenant(tenant_id)
        existing = self.get_member(tenant_id, member_id)
        transact: list[dict] = [
            {
                "Delete": {
                    "TableName": self.table_name,
                    "Key": td.build_key(tenant_id, td.member_sk(member_id)),
                }
            }
        ]
        member_number = ((existing or {}).get("membership") or {}).get("member_number")
        if member_number:
            transact.append(
                {
                    "Delete": {
                        "TableName": self.table_name,
                        "Key": td.build_key(
                            tenant_id, td.member_number_sk(member_number)
                        ),
                    }
                }
            )
        self.client.transact_write_items(TransactItems=transact)

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

    # ── Counters (member-number allocation, etc.) ──────────────────────────────────────

    def next_counter(self, tenant_id: str, counter_name: str) -> int:
        """Atomically increment and return a named per-tenant counter (atomic ``ADD``).

        A single DynamoDB ``UpdateItem`` with ``ADD #value :one`` returning ``UPDATED_NEW``
        never collides under concurrency — DynamoDB serializes the increments — so two
        invocations can never be handed the same number (Property 6). A first call on a
        missing counter starts from 1.
        """
        self._require_tenant(tenant_id)
        response = self.table.update_item(
            Key=td.build_key(tenant_id, td.counter_sk(counter_name)),
            UpdateExpression="ADD #value :one",
            ExpressionAttributeNames={"#value": "value"},
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["value"])

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
