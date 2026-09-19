"""
S5 Task 3.2 — the generic membership engine's **READ surface** (design C2, R1.2/R3.1/R3.3).

This is the storage-agnostic, tenant-agnostic domain service the handler edge delegates the
READ routes to (design C1 read routes → C2 → C6). It owns the **read behaviour** the thin
handler must not: it asks the injected :class:`~sam.members.repository.members_repository.
MembersRepository` for the tenant's records (every repository call is keyed by ``tenant_id``
— structural isolation, Property 1) and then applies **domain-layer scope filtering** by the
caller's ``allowed_scopes`` (design C4, Property 4). It never contains an ``if tenant == ...``
and never touches DynamoDB or HTTP; it is a pure orchestration of repository reads + the
scope/ownership rules.

Read behaviour (design C2 read surface / migration-plan Step 3):

- :meth:`MembershipService.list_members` — the tenant's members, narrowed by scope.
- :meth:`MembershipService.export_members` — same as list (scope-narrowed); the export
  projection shape.
- :meth:`MembershipService.get_member` — a single member, scope-enforced, with a
  **self-service** path so a member may read their OWN record even without a broad scope.
- :meth:`MembershipService.list_memberships` / :meth:`MembershipService.get_membership` —
  a member's memberships, scope-checked via the parent member.
- :meth:`MembershipService.get_member_payments` — a member's payments, scope-checked via the
  parent member.

**Scope filtering (design C4, Property 4).** The rule is uniform across every read:

- ``allowed_scopes == ["*"]`` (:data:`~sam.members.domain.scope_dimensions.WILDCARD`) →
  tenant-wide, every record of the tenant is visible.
- a non-empty **subset** → only records whose ``scope_values[<dimension_key>]`` intersects
  the subset are visible (a scoped user stays inside their tenant, narrowed to their values).
- ``allowed_scopes == []`` → **deny** (see nothing) — the scope-deny default (Property 4); a
  list returns empty, a single fetch is a scope miss (the edge maps that to a 404-style
  "no such member for you", never a cross-scope leak).

The gating **dimension key** (h-dcn: ``"region"``) is threaded in, derived generically from
the tenant's scope config by the caller (the handler edge), never hardcoded here.

**Self-service (design C1 / routes ``self_service``).** ``get_member``/membership/payment
reads accept a ``requester_sub`` + ``self_service`` flag: a member may read their OWN record
(matched on the record's identity — a cognito ``sub`` stored on the record, else the
``member_id``, else the personal contact/email) even when their scope would otherwise deny
it. Self-service NEVER widens access to other members — ownership is matched per-record.

Layering (``sam-module-architecture.md``): SAM-plane **domain** code. It depends on the
repository **Protocol** (dependency-inversion), so tests inject an in-memory fake and the
service never learns where the data lives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sam.members.domain.field_resolver import (
    FieldResolver,
    ResolvedField,
    StaticOverlayProvider,
    TenantOverlayProvider,
)
from sam.members.domain.fixed_fields import (
    FieldGroup,
    FieldValidationError,
    MembershipStatus,
    validate_fixed_fields,
)
from sam.members.domain.lifecycle_config import (
    GuardEvaluation,
    LifecycleConfig,
    LifecycleConfigProvider,
    StaticLifecycleConfigProvider,
    evaluate_guards,
    evaluate_required_fields,
)
from sam.members.domain.membership_type_catalog import (
    MembershipTypeEntry,
    MembershipTypeValidationError,
)
from sam.members.domain.scope_dimensions import WILDCARD
from sam.members.domain.tenant_hooks import HookName, TenantHookRegistry
from sam.members.domain.transition_hooks import TransitionHookRegistry
from sam.members.repository.members_repository import (
    Member,
    MemberNumberConflictError,
    Membership,
    MembersRepository,
    Payment,
)

__all__ = [
    "MembershipService",
    "MemberNotFound",
    "MembershipTypeNotFound",
    "MembershipTypeConflict",
    "TransitionDenied",
    "TransitionResult",
    "MemberValidationError",
    "ScopeDenied",
    "MEMBERSHIP_STATUS_FIELD_KEY",
    "DEFAULT_SCOPE_DIMENSION_KEY",
    "MEMBERSHIP_TYPE_FIELD_KEY",
    "MEMBER_NUMBER_COUNTER",
]

#: The per-tenant counter name the write path draws member numbers from (design C6). The
#: atomic ``next_counter(tenant_id, MEMBER_NUMBER_COUNTER)`` fetch is the write-path's job
#: (task 5.1's note: keep the ``derive_member_number`` hook pure by threading the value in).
MEMBER_NUMBER_COUNTER = "member_number"

#: The canonical dotted key of the ``status`` fixed field — the attribute the lifecycle state
#: machine reads the member's current state from and writes the new state to.
MEMBERSHIP_STATUS_FIELD_KEY = f"{FieldGroup.MEMBERSHIP.value}.status"

#: The canonical dotted key of the ``membership_type`` fixed field (design C8). The resolved
#: field config injects the tenant's ACTIVE Lidmaatschap Beheer catalog entries as this
#: field's selectable options, so the presentation-only frontend renders a dropdown of ONLY
#: that tenant's active types (no free text, no hardcoded vocabulary — R2.4).
MEMBERSHIP_TYPE_FIELD_KEY = f"{FieldGroup.MEMBERSHIP.value}.membership_type"

#: The scope dimension key a read narrows on when the caller does not thread one in. h-dcn's
#: gating dimension is ``region``; this is only the *fallback* — the handler edge derives the
#: real key generically from the tenant's scope config and passes it in, so nothing is
#: hardcoded on the request path (the constant merely keeps a lone service call sensible).
DEFAULT_SCOPE_DIMENSION_KEY = "region"


class MemberNotFound(Exception):
    """Raised when a member does not exist for the tenant, OR is out of the caller's scope.

    The two cases are deliberately indistinguishable to the caller (the edge maps this to a
    ``404``): a scoped user must not be able to tell "this member exists but is in another
    scope" apart from "this member does not exist", or the 404/403 difference would leak the
    existence of out-of-scope records. Isolation is still structural — the repository was
    only ever asked within ``tenant_id`` (Property 1).
    """

    def __init__(self, tenant_id: str, member_id: str):
        self.tenant_id = tenant_id
        self.member_id = member_id
        super().__init__(f"member {member_id!r} not found for tenant {tenant_id!r}")


class MembershipTypeNotFound(Exception):
    """Raised when a Lidmaatschap Beheer catalog entry does not exist for the tenant (→ 404).

    The catalog ``get`` read (design C8, task 3.4) is tenant-scoped by the verified
    ``tenant_id`` (Property 1); an absent ``type_code`` — or one that exists only for another
    tenant — is an ordinary not-found the edge maps to a ``404`` (mirroring
    :class:`MemberNotFound` → 404 for the member read). Retired (``active=false``) entries are
    NOT a not-found: the management view still returns them, so a soft-deleted type fetched by
    code returns it (with ``active: false``), never a 404.
    """

    def __init__(self, tenant_id: str, type_code: str):
        self.tenant_id = tenant_id
        self.type_code = type_code
        super().__init__(
            f"membership type {type_code!r} not found for tenant {tenant_id!r}"
        )


class MembershipTypeConflict(Exception):
    """Raised when CREATING a catalog entry whose ``type_code`` already exists (→ 409).

    The catalog ``create`` (design C8, task 5.3) is a *create*, not an upsert: a ``type_code``
    is the reference key member records store, so silently overwriting an existing entry on a
    "create" would let a client mutate a live type behind an ``update``-shaped API and risk
    changing the meaning of every member already referencing it. So create refuses a duplicate
    code with a conflict (the edge maps it to a ``409``); an intentional change goes through the
    ``update`` route (idempotent upsert). ``update`` and ``deactivate`` never raise this.
    """

    def __init__(self, tenant_id: str, type_code: str):
        self.tenant_id = tenant_id
        self.type_code = type_code
        super().__init__(
            f"membership type {type_code!r} already exists for tenant {tenant_id!r}"
        )


class TransitionDenied(Exception):
    """Raised when a membership transition is not permitted (design C2 — never a silent allow).

    A transition is denied when it is not declared in the tenant's lifecycle graph, or when
    one or more declarative guards fail, or when the tenant has no lifecycle config at all.
    ``reasons`` carries the human-readable cause(s) so the write route (task 5.2) / edge can
    surface them (mapped to a 409/422). A denied transition NEVER mutates the member or fires
    the ``on_transition`` hook.
    """

    def __init__(
        self,
        tenant_id: str,
        from_state: Optional[MembershipStatus],
        to_state: MembershipStatus,
        reasons: Sequence[str],
    ):
        self.tenant_id = tenant_id
        self.from_state = from_state
        self.to_state = to_state
        self.reasons = tuple(reasons)
        frm = getattr(from_state, "value", from_state)
        to = getattr(to_state, "value", to_state)
        detail = "; ".join(self.reasons) or "transition not allowed"
        super().__init__(
            f"transition {frm!r} -> {to!r} denied for tenant {tenant_id!r}: {detail}"
        )


class MemberValidationError(Exception):
    """Raised when a member write fails validation (fixed-field OR tenant ``validate_member``).

    The write path (task 5.2) validates a member in two authoritative passes, both here in
    the domain (never the frontend, R2.3 / Property 2): the platform-fixed field registry
    (:func:`~sam.members.domain.fixed_fields.validate_fixed_fields`) and the tenant's
    Rung-3 ``validate_member`` hook (design C5 — h-dcn's motor-club rule, task 5.1). The two
    error maps are MERGED so a caller sees every problem at once, mirroring
    :class:`~sam.members.domain.fixed_fields.FieldValidationError`. The edge maps this to a
    ``422`` (unprocessable) — a well-formed request that violates the data rules.
    """

    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        detail = "; ".join(f"{k}: {v}" for k, v in self.errors.items())
        super().__init__(f"member validation failed: {detail}")


class ScopeDenied(Exception):
    """Raised when a scoped caller attempts a WRITE outside their ``allowed_scopes`` (→ 403).

    Reads map an out-of-scope member to a 404 (no existence leak — see
    :class:`MemberNotFound`); a WRITE is different — the caller has been authenticated and
    granted the write capability, but is trying to create/update/delete a record in a scope
    they do not hold, so the honest answer is an authorization denial (``403``), Property 4.
    Deny is the default: a non-wildcard caller may only write within the scope values they
    were granted, and self-service lets a member act on their OWN record only.
    """

    def __init__(self, tenant_id: str, message: str = "write outside allowed scope"):
        self.tenant_id = tenant_id
        super().__init__(f"{message} (tenant {tenant_id!r}, Property 4)")


@dataclass(frozen=True)
class TransitionResult:
    """The outcome of a PERMITTED transition COMPUTATION (design C2 — the pure decision).

    This is what :meth:`MembershipService.transition_membership` returns on success: the
    ``from_state`` / ``to_state`` and the ``member`` record with its ``membership.status``
    updated to the new state. It is a **computation**, not a persist — the state machine
    decides + dispatches the ``on_transition`` hook here, and the WRITE route (task 5.2) is
    responsible for saving the returned ``member`` via the repository (see the persist-boundary
    note on :meth:`MembershipService.transition_membership`).
    """

    tenant_id: str
    member: Member
    from_state: MembershipStatus
    to_state: MembershipStatus


class MembershipService:
    """The generic membership engine — READ surface (design C2) + lifecycle state machine.

    Storage-agnostic + tenant-agnostic. Holds a :class:`MembersRepository` (injected), and
    for every read: (1) asks the repository for the tenant's data (keyed by ``tenant_id`` —
    Property 1), then (2) applies domain-layer scope filtering by ``allowed_scopes`` (design
    C4, Property 4) and, for single-record reads, the self-service ownership rule.

    For the WRITE path's workflow it also owns the **lifecycle state machine**
    (:meth:`transition_membership`, task 5.0): it resolves the tenant's declarative
    :class:`LifecycleConfig`, checks a requested transition against the graph, evaluates the
    declarative guards, and — only on success — dispatches the ``on_transition`` hook and
    returns the state-updated record. The generic core has no ``if tenant == ...`` — every
    difference is config (the graph), a declarative rule (the guards), or a registered hook
    (the side-effect); Property 5.

    Args:
        repository: The tenant-scoped persistence contract (the only DynamoDB touch-point).
        overlay_provider: Supplies each tenant's variable field overlay, resolved by
            ``tenant_id`` (design C3). Injected so the service stays storage-agnostic and
            tenant-agnostic — it builds a :class:`FieldResolver` over whatever provider is
            handed in. Defaults to an empty :class:`StaticOverlayProvider` (every tenant
            resolves to exactly the fixed base — the fail-safe, empty-by-default overlay).
        lifecycle_provider: Supplies each tenant's :class:`LifecycleConfig`, resolved by
            ``tenant_id`` (design C2). Defaults to an empty
            :class:`StaticLifecycleConfigProvider` — a tenant with no configured lifecycle has
            no state machine, so a transition request for it is denied (never a silent allow).
        transition_hooks: The tenant-keyed ``on_transition`` hook registry (design C5). The
            engine dispatches through it after a transition is permitted; an unregistered
            tenant resolves to the safe no-op default. Defaults to an empty registry (task 5.1
            populates h-dcn's hook). Prefer passing ``tenant_hooks`` (the unified registry) so
            the WRITE path (task 5.2) can also reach ``validate_member`` /
            ``derive_member_number``; if only ``transition_hooks`` is supplied, the write-path
            hooks fall back to their safe generic defaults.
        tenant_hooks: The unified :class:`~sam.members.domain.tenant_hooks.TenantHookRegistry`
            (design C5, all named extension points). When supplied, the WRITE path resolves
            ``validate_member`` + ``derive_member_number`` through it AND the engine dispatches
            ``on_transition`` through its ``transition_registry()`` view — so one registry
            wires every hook. ``transition_hooks`` (the 5.0 seam) is honoured for backwards
            compatibility when ``tenant_hooks`` is omitted.
    """

    def __init__(
        self,
        repository: MembersRepository,
        overlay_provider: Optional[TenantOverlayProvider] = None,
        lifecycle_provider: Optional[LifecycleConfigProvider] = None,
        transition_hooks: Optional[TransitionHookRegistry] = None,
        tenant_hooks: Optional[TenantHookRegistry] = None,
    ):
        self._repo = repository
        self._field_resolver = FieldResolver(
            overlay_provider if overlay_provider is not None else StaticOverlayProvider()
        )
        self._lifecycle_provider: LifecycleConfigProvider = (
            lifecycle_provider
            if lifecycle_provider is not None
            else StaticLifecycleConfigProvider()
        )
        # The unified Rung-3 registry (design C5). The WRITE path (task 5.2) resolves
        # validate_member / derive_member_number through it; an unregistered tenant resolves
        # to the safe generic default (Property 5). Defaults to an empty registry.
        self._tenant_hooks = (
            tenant_hooks if tenant_hooks is not None else TenantHookRegistry()
        )
        # The on_transition seam the 5.0 engine consumes. When a unified registry is supplied
        # its transition view wins (one registry wires everything); otherwise honour an
        # explicitly-passed 5.0-style TransitionHookRegistry, else an empty one.
        if tenant_hooks is not None:
            self._transition_hooks = tenant_hooks.transition_registry()
        elif transition_hooks is not None:
            self._transition_hooks = transition_hooks
        else:
            self._transition_hooks = TransitionHookRegistry()

    # ── Scope helpers (domain-layer scope filtering — design C4, Property 4) ──────────

    @staticmethod
    def _is_wildcard(allowed_scopes: Sequence[str]) -> bool:
        """True when the caller may see every record of the tenant (``["*"]``)."""
        return list(allowed_scopes) == [WILDCARD]

    @staticmethod
    def _is_deny(allowed_scopes: Sequence[str]) -> bool:
        """True when the caller has no scope grant (empty) → see nothing (Property 4)."""
        return len(list(allowed_scopes)) == 0

    @staticmethod
    def _record_scope_values(
        member: Member, dimension_key: str
    ) -> List[str]:
        """The member's values for the gating dimension, normalised to a list of strings.

        Reads ``member["scope_values"][dimension_key]`` (the design data model), tolerating
        a scalar or a list and a record that carries no scope values at all (→ empty list,
        which a scoped caller never intersects → not visible; a wildcard caller sees it
        anyway because wildcard short-circuits before this is consulted).
        """
        scope_values = member.get("scope_values") or {}
        if not isinstance(scope_values, Mapping):
            return []
        raw = scope_values.get(dimension_key)
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, (list, tuple, set)):
            return [str(v) for v in raw]
        return [str(raw)]

    def _in_scope(
        self,
        member: Member,
        allowed_scopes: Sequence[str],
        dimension_key: str,
    ) -> bool:
        """Whether ``member`` is visible to a caller holding ``allowed_scopes``.

        The single scope rule every read shares: wildcard sees all; a deny (empty) sees
        none; a subset sees a record only when the record's values for the gating dimension
        intersect the granted subset (design C4, Property 4).
        """
        if self._is_wildcard(allowed_scopes):
            return True
        if self._is_deny(allowed_scopes):
            return False
        granted = set(allowed_scopes)
        record_values = set(self._record_scope_values(member, dimension_key))
        return bool(granted & record_values)

    # ── Self-service ownership (design C1 self_service routes) ────────────────────────

    @staticmethod
    def _owns_record(member: Member, requester_sub: Optional[str]) -> bool:
        """Whether ``requester_sub`` identifies the owner of ``member`` (self-service).

        A member may read their OWN record even without a broad scope grant. Ownership is
        matched on the record's identity, in priority order, tolerant of what the record
        carries (the fixed registry has no cognito field yet, so we accept whichever
        identity is present):

        1. a cognito subject stored on the record (``sub`` / ``cognito_sub``);
        2. the ``member_id`` (a token whose subject *is* the member id);
        3. the personal contact/email (``personal.contact``).

        A missing ``requester_sub`` never matches (no ambient ownership). This never widens
        access to *other* members — it is a per-record identity check.
        """
        if not requester_sub:
            return False
        candidates: set[str] = set()
        for key in ("sub", "cognito_sub"):
            value = member.get(key)
            if value:
                candidates.add(str(value))
        member_id = member.get("member_id")
        if member_id:
            candidates.add(str(member_id))
        personal = member.get("personal") or {}
        if isinstance(personal, Mapping):
            contact = personal.get("contact")
            if contact:
                candidates.add(str(contact))
        return str(requester_sub) in candidates

    def _visible_member_or_raise(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Sequence[str],
        dimension_key: str,
        *,
        requester_sub: Optional[str],
        self_service: bool,
    ) -> Member:
        """Fetch a member and enforce scope + self-service, or raise :class:`MemberNotFound`.

        The shared gate behind every single-member read (``get_member`` and the child reads
        that hang off a member). It fetches within the tenant (Property 1), then allows the
        read when EITHER the member is in the caller's scope OR the caller owns the record
        via self-service. Anything else is an indistinguishable not-found (no existence
        leak).
        """
        member = self._repo.get_member(tenant_id, member_id)
        if member is None:
            raise MemberNotFound(tenant_id, member_id)

        if self._in_scope(member, allowed_scopes, dimension_key):
            return member
        if self_service and self._owns_record(member, requester_sub):
            return member
        raise MemberNotFound(tenant_id, member_id)

    # ── Member reads ──────────────────────────────────────────────────────────────────

    def list_members(
        self,
        tenant_id: str,
        allowed_scopes: Sequence[str],
        *,
        filters: Optional[Mapping[str, Any]] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> List[Member]:
        """List the tenant's members, narrowed to the caller's scope (design C4, Property 4).

        Asks the repository for the tenant's members (keyed by ``tenant_id`` — Property 1),
        optionally passing ``filters`` through, then narrows by ``allowed_scopes``: wildcard
        returns all, a subset returns only members whose gating-dimension values intersect
        the subset, and an empty scope returns ``[]`` (deny-by-default). Ordering is the
        repository's.
        """
        if self._is_deny(allowed_scopes):
            # Deny-by-default: no scope grant → see nothing, without even scanning results.
            return []
        members = self._repo.list_members(tenant_id, filters=filters)
        if self._is_wildcard(allowed_scopes):
            return list(members)
        return [
            m for m in members if self._in_scope(m, allowed_scopes, dimension_key)
        ]

    def export_members(
        self,
        tenant_id: str,
        allowed_scopes: Sequence[str],
        *,
        filters: Optional[Mapping[str, Any]] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> List[Member]:
        """Export the tenant's members (scope-narrowed) — the export projection.

        Same scope semantics as :meth:`list_members` (a scoped exporter exports only their
        scope; an empty scope exports nothing). Kept a distinct method so the export
        projection can diverge from the list projection later without touching the scope
        rule; today it returns the same scope-filtered records.
        """
        return self.list_members(
            tenant_id, allowed_scopes, filters=filters, dimension_key=dimension_key
        )

    def get_member(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        self_service: bool = False,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Member:
        """Fetch one member by id, enforcing scope + self-service (design C1/C4).

        Fetches within the tenant (Property 1) and returns the member when it is in the
        caller's scope, OR — when ``self_service`` — when the caller owns the record
        (matched on ``requester_sub``). Otherwise raises :class:`MemberNotFound` (the edge
        maps that to a 404 without leaking whether the member exists out of scope).
        """
        return self._visible_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )

    def get_self(
        self,
        tenant_id: str,
        requester_sub: Optional[str],
        *,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Member:
        """Return the calling member's OWN record (the ``GET /members/me`` self-service read).

        Pure self-service: there is no broad scope grant on this route (its capability is
        ``None``); the caller is only ever entitled to their own record. We resolve the
        record by scanning the tenant's members for the one the ``requester_sub`` owns
        (tenant-scoped — Property 1), and raise :class:`MemberNotFound` if none matches.
        Because ownership is a per-record identity match, this can never return another
        member.
        """
        if not requester_sub:
            raise MemberNotFound(tenant_id, "<self>")
        for member in self._repo.list_members(tenant_id):
            if self._owns_record(member, requester_sub):
                return member
        raise MemberNotFound(tenant_id, "<self>")

    # ── Membership reads (scope-checked via the parent member) ────────────────────────

    def list_memberships(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        self_service: bool = False,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> List[Membership]:
        """List a member's memberships, gated by the parent member's visibility.

        The membership read is only permitted once the parent member passes the scope /
        self-service gate (:meth:`_visible_member_or_raise`), so a scoped caller cannot read
        the memberships of an out-of-scope member. Then the repository is asked for that
        member's memberships (tenant-scoped — Property 1).
        """
        self._visible_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        return list(self._repo.list_memberships(tenant_id, member_id))

    def get_membership(
        self,
        tenant_id: str,
        member_id: str,
        membership_id: str,
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        self_service: bool = False,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Membership:
        """Fetch one membership of a member, gated by the parent member's visibility.

        Enforces the parent member's scope / self-service gate first, then fetches the
        membership within the tenant. A missing membership (under a visible member) raises
        :class:`MemberNotFound` — the edge maps it to a 404.
        """
        self._visible_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        membership = self._repo.get_membership(tenant_id, member_id, membership_id)
        if membership is None:
            raise MemberNotFound(tenant_id, member_id)
        return membership

    # ── Member-scoped payments (scope-checked via the parent member) ──────────────────

    def get_member_payments(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        self_service: bool = False,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> List[Payment]:
        """List a member's payments, gated by the parent member's visibility.

        Same gate as the membership reads: the parent member must be visible (scope or
        self-service) before its payments are returned, so payments never leak across scope.
        The repository read is tenant-scoped (Property 1).
        """
        self._visible_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        return list(self._repo.list_member_payments(tenant_id, member_id))

    # ── Lifecycle state machine (design C2, R1.4 — task 5.0) ──────────────────────────

    @staticmethod
    def _current_state(member: Member) -> Optional[MembershipStatus]:
        """Read a member's current lifecycle state from ``membership.status``.

        Returns the parsed :class:`MembershipStatus`, or ``None`` when the record carries no
        status yet (a brand-new member) or an unrecognised value (treated as "no known state"
        so the engine denies any transition *from* it rather than guessing).
        """
        membership = member.get("membership") or {}
        if not isinstance(membership, Mapping):
            return None
        raw = membership.get("status")
        if raw is None:
            return None
        try:
            return MembershipStatus(raw)
        except ValueError:
            return None

    @staticmethod
    def _with_status(member: Member, to_state: MembershipStatus) -> Member:
        """Return a shallow copy of ``member`` with ``membership.status`` set to ``to_state``.

        The pure state-update half of the transition computation — it does not persist (that
        is the WRITE route, task 5.2). The copy is deep enough to avoid mutating the caller's
        ``membership`` sub-mapping in place.
        """
        updated = dict(member)
        membership = dict(updated.get("membership") or {})
        membership["status"] = to_state.value
        updated["membership"] = membership
        return updated

    def get_lifecycle_config(self, tenant_id: str) -> Optional[LifecycleConfig]:
        """Return the tenant's :class:`LifecycleConfig`, or ``None`` if none is configured.

        A thin pass-through to the injected provider, exposed so the WRITE route (task 5.2)
        and tests can inspect the graph a tenant runs without reaching into the service's
        internals.
        """
        return self._lifecycle_provider.get_lifecycle_config(tenant_id)

    def transition_membership(
        self,
        tenant_id: str,
        member: Member,
        to_state: MembershipStatus,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TransitionResult:
        """Compute a membership lifecycle transition (design C2, R1.4) — the pure decision.

        The tenant-agnostic state-machine engine. It:

        1. resolves the tenant's :class:`LifecycleConfig` (deny if the tenant has none —
           there is no state machine to run);
        2. reads the member's current state from ``membership.status`` and checks the
           requested ``current -> to_state`` edge exists in the tenant's transition **graph**
           (deny if it does not — never a silent allow);
        3. evaluates the transition's declarative **guards** against ``(member, context)`` and
           the declarative **required-field** rules for the target state (deny, with reasons,
           if any fail);
        4. on success, computes the state-updated record and dispatches the tenant's
           ``on_transition`` **hook** (the safe no-op default when none is registered) for
           side-effects; and
        5. returns a :class:`TransitionResult` carrying the updated record + from/to states.

        **Persist boundary (task 5.2).** This method is the pure transition *computation* +
        hook dispatch — it does NOT save. The WRITE route (task 5.2) calls this, then persists
        the returned ``TransitionResult.member`` via
        :meth:`MembersRepository.save_member` / ``save_membership``. Keeping the decision here
        (storage-agnostic, tenant-agnostic) and the write there keeps the engine testable
        without a repository and lets 5.2 own the conditional-write/uniqueness concerns.

        Raises:
            TransitionDenied: if the tenant has no lifecycle config, the edge is not in the
                graph, or a guard / required-field rule fails. The member is never mutated and
                the hook never fires on a denial.
        """
        ctx: Mapping[str, Any] = context or {}
        config = self._lifecycle_provider.get_lifecycle_config(tenant_id)
        from_state = self._current_state(member)

        if config is None:
            raise TransitionDenied(
                tenant_id,
                from_state,
                to_state,
                ["tenant has no configured membership lifecycle"],
            )

        # The target state must be one the tenant even uses.
        if not config.is_allowed_state(to_state):
            raise TransitionDenied(
                tenant_id,
                from_state,
                to_state,
                [f"{to_state.value!r} is not an allowed state for this tenant"],
            )

        if from_state is None:
            raise TransitionDenied(
                tenant_id,
                from_state,
                to_state,
                ["member has no current lifecycle state to transition from"],
            )

        # (2) The edge must exist in the declared graph — else deny (never a silent allow).
        rule = config.transition(from_state, to_state)
        if rule is None:
            raise TransitionDenied(
                tenant_id,
                from_state,
                to_state,
                [
                    f"no transition from {from_state.value!r} to {to_state.value!r} is "
                    "declared for this tenant"
                ],
            )

        # (3) Evaluate the declarative guards + the target state's required-field rules.
        reasons: List[str] = []
        guard_eval: GuardEvaluation = evaluate_guards(rule.guards, member, ctx)
        if guard_eval.denied:
            reasons.extend(guard_eval.reasons)
        required_eval: GuardEvaluation = evaluate_required_fields(
            config.required_fields, member, to_state, ctx
        )
        if required_eval.denied:
            reasons.extend(required_eval.reasons)
        if reasons:
            raise TransitionDenied(tenant_id, from_state, to_state, reasons)

        # (4) Permitted — compute the state-updated record, then dispatch the tenant hook.
        updated = self._with_status(member, to_state)
        self._transition_hooks.dispatch(tenant_id, updated, from_state, to_state)

        # (5) Return the decision; the WRITE route (task 5.2) persists it.
        return TransitionResult(
            tenant_id=tenant_id,
            member=updated,
            from_state=from_state,
            to_state=to_state,
        )

    # ── Write path (design C1 write / C2 / C5 / C6 — task 5.2) ────────────────────────
    #
    # Orchestration only: validate (fixed fields + tenant validate_member hook) → derive the
    # member number via the hook on create (threading the atomic counter value in) → for a
    # transition call the lifecycle engine above → persist via the repository (the SOLE
    # DynamoDB touch-point + owner of uniqueness/atomicity). No ``if tenant``, no boto3, no
    # HTTP here (Property 5). Scope + verify-before-trust are enforced BEFORE any persist.

    def _validate_member_record(self, tenant_id: str, record: Member, *, partial: bool) -> None:
        """Validate a member record authoritatively (design C2/C5, R2.3, Property 2).

        Two passes, both server-side (the frontend enforces nothing): the platform-fixed
        field registry (:func:`validate_fixed_fields`, ``partial`` for updates), then the
        tenant's Rung-3 ``validate_member`` hook (h-dcn's motor-club rule, task 5.1 — the
        safe no-error default for an unregistered tenant). Both error maps are merged and
        raised as one :class:`MemberValidationError` so the caller sees every problem at once.
        """
        errors: Dict[str, str] = {}
        try:
            validate_fixed_fields(record, partial=partial)
        except FieldValidationError as exc:
            errors.update(exc.errors)

        hook_errors = self._tenant_hooks.dispatch(
            HookName.VALIDATE_MEMBER, tenant_id, record
        )
        if isinstance(hook_errors, Mapping):
            errors.update({str(k): str(v) for k, v in hook_errors.items()})

        if errors:
            raise MemberValidationError(errors)

    @staticmethod
    def _membership_type_of(record: Mapping[str, Any]) -> Optional[str]:
        """The record's ``membership.membership_type`` reference, or ``None`` if unset.

        Used to detect whether an update actually CHANGES the type (so the reference check is
        only re-run on a real change — partial-update friendliness, design C8). Tolerant of a
        record with no ``membership`` block.
        """
        membership = record.get("membership")
        if not isinstance(membership, Mapping):
            return None
        value = membership.get("membership_type")
        return str(value) if value is not None else None

    def _validate_membership_type_reference(self, tenant_id: str, record: Member) -> None:
        """Authoritatively validate the member's ``membership_type`` catalog reference (C8).

        The domain — never the frontend — is the authority for referential integrity (R2.4,
        Property 2): the React dropdown that lists a tenant's active types is convenience only,
        so a create/update MUST re-check the effective ``membership.membership_type`` against
        the tenant's LIVE catalog. The rule (design C8):

        - the value must reference a catalog entry that **exists** for THIS tenant (Property 1,
          tenant-agnostic — the check is against the tenant's own catalog, no ``if tenant``);
        - that entry must be **active** — a soft-deleted (retired) type is not assignable to a
          new/edited member (it has left the dropdown), so it fails the reference check;
        - an **unknown** code fails too.

        A missing ``membership_type`` is NOT rejected here — the fixed-field registry
        (:func:`validate_fixed_fields`) owns the "required" rule (a create with no type already
        fails there; a partial update that does not touch it is left alone). This method only
        rejects a *present* value that does not resolve to a live entry, merging its error into
        the caller's :class:`MemberValidationError` (a 422). It is applied only on create/update
        writes — never on reads — so an EXISTING member that references a since-retired type
        stays valid (we do not retroactively invalidate stored members, design C8).
        """
        membership = record.get("membership")
        if not isinstance(membership, Mapping):
            return
        type_code = membership.get("membership_type")
        if type_code is None or (isinstance(type_code, str) and not type_code.strip()):
            # Absence/blank is the fixed-field registry's concern (required-ness), not ours.
            return

        entry = self._repo.get_membership_type(tenant_id, str(type_code))
        if entry is None:
            raise MemberValidationError(
                {
                    MEMBERSHIP_TYPE_FIELD_KEY: (
                        f"unknown membership type {str(type_code)!r} "
                        "(not in the tenant's Lidmaatschap Beheer catalog)"
                    )
                }
            )
        if not entry.active:
            raise MemberValidationError(
                {
                    MEMBERSHIP_TYPE_FIELD_KEY: (
                        f"membership type {str(type_code)!r} is retired (active=false) "
                        "and cannot be assigned to a new or updated member"
                    )
                }
            )

    def _sanitize_write_payload(self, body: Mapping[str, Any]) -> Dict[str, Any]:
        """Copy a client write payload, stripping fields the client may NEVER set.

        Verify-before-trust (Property 2): the ``tenant_id`` / partition key is authoritative
        from the verified context and is stamped by the service, never accepted from the body.
        We drop any client-supplied ``tenant_id`` / DynamoDB partition-key attribute so a
        caller cannot steer a write into another tenant's partition. ``scope_values`` are kept
        as data but a scoped caller's scope is authorized separately (:meth:`_authorize_write`).
        """
        payload = {k: v for k, v in dict(body).items() if k not in ("tenant_id", "PK", "pk")}
        return payload

    def _authorize_write(
        self,
        tenant_id: str,
        member: Member,
        allowed_scopes: Sequence[str],
        dimension_key: str,
        *,
        requester_sub: Optional[str],
        self_service: bool,
    ) -> None:
        """Authorize a WRITE against the caller's scope, or raise :class:`ScopeDenied` (403).

        Deny-by-default (Property 4): a wildcard caller may write any record of the tenant; a
        scoped (non-wildcard) caller may only write a record whose gating-dimension values
        intersect their grant; an empty scope denies unless self-service applies. Self-service
        lets a member write their OWN record (matched on ``requester_sub``) even without a
        broad scope — used by the delegate routes so a member can manage their own delegates.
        Reuses the same ``_in_scope`` rule the reads share, so read/write scope stays uniform.
        """
        if self._in_scope(member, allowed_scopes, dimension_key):
            return
        if self_service and self._owns_record(member, requester_sub):
            return
        raise ScopeDenied(tenant_id)

    def create_member(
        self,
        tenant_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Member:
        """Create a member for the tenant (design C1 write / C2 / C5 / C6, R1.4/R3.3).

        Orchestration: sanitize the payload (never trust a body ``tenant_id`` — Property 2) →
        stamp the authoritative ``tenant_id`` → set the initial lifecycle state from the
        tenant's :class:`LifecycleConfig` when the body carries none → derive the member number
        via the tenant ``derive_member_number`` hook when absent, threading in an atomic
        ``next_counter`` value (the counter fetch is the write-path's job; the hook stays pure)
        → validate (fixed fields + tenant ``validate_member``) → authorize the write against
        the caller's scope → persist via ``save_member`` (a conditional write; a racing/
        duplicate member number raises :class:`MemberNumberConflictError` → the edge maps it to
        a 409, never a silent overwrite — Property 6).
        """
        record = self._sanitize_write_payload(body)
        record["tenant_id"] = tenant_id  # authoritative — verify-before-trust (Property 2)

        membership = dict(record.get("membership") or {})

        # Initial lifecycle state from the tenant's config when the body sets none.
        config = self._lifecycle_provider.get_lifecycle_config(tenant_id)
        if not membership.get("status") and config is not None:
            membership["status"] = config.initial_state.value

        # Derive the member number via the tenant hook when absent, threading the atomic
        # counter value in (the fetch is the write-path's job; the hook is pure — task 5.1).
        if not membership.get("member_number"):
            next_number = self._repo.next_counter(tenant_id, MEMBER_NUMBER_COUNTER)
            derived = self._tenant_hooks.dispatch(
                HookName.DERIVE_MEMBER_NUMBER, tenant_id, {**record, "membership": membership},
                next_number,
            )
            if derived:
                membership["member_number"] = str(derived)
        record["membership"] = membership

        self._validate_member_record(tenant_id, record, partial=False)
        # Authoritative referential-integrity check (design C8, task 5.3): the member's
        # membership_type must reference a LIVE catalog entry for the tenant (the dropdown is
        # convenience only — never trusted). A missing/unknown/retired reference → 422. This
        # CLOSES the loop 5.2 opened (it carried the value but deferred the catalog check).
        self._validate_membership_type_reference(tenant_id, record)
        self._authorize_write(
            tenant_id,
            record,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=False,
        )
        return self._repo.save_member(tenant_id, record)

    def update_member(
        self,
        tenant_id: str,
        member_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        self_service: bool = False,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Member:
        """Partial-update a member (design C1 write / C2, R1.4/R3.3).

        Loads the existing member within the tenant (Property 1) and authorizes the write
        against the EXISTING record's scope (a scoped caller cannot touch an out-of-scope
        member — :class:`ScopeDenied` → 403). Deep-merges the sanitized body over the existing
        record (the client never sets ``tenant_id`` — Property 2; ``member_id`` stays the
        path's), re-authorizes on the MERGED record (a scoped caller may not move a member OUT
        of their scope either), re-validates (fixed fields ``partial=True`` + tenant
        ``validate_member``), and re-saves (idempotent for the same member number — the repo
        allows it, Property 6).
        """
        existing = self._repo.get_member(tenant_id, member_id)
        if existing is None:
            raise MemberNotFound(tenant_id, member_id)

        self._authorize_write(
            tenant_id,
            existing,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )

        patch = self._sanitize_write_payload(body)
        merged = self._deep_merge(dict(existing), patch)
        merged["tenant_id"] = tenant_id
        merged["member_id"] = member_id  # the path is authoritative for identity

        # A scoped caller must not move a member OUT of (or into a foreign) scope.
        self._authorize_write(
            tenant_id,
            merged,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )

        self._validate_member_record(tenant_id, merged, partial=True)
        # Referential integrity on update (design C8, task 5.3), applied ONLY when the patch
        # CHANGES the membership_type reference. This is the partial-update-friendly rule the
        # spec asks for: a patch that MOVES the reference to a new value must point at a LIVE
        # catalog entry (unknown/retired → 422), but an update that does NOT touch the type is
        # left alone — so an EXISTING member that references a since-retired type stays
        # updatable (name/contact edits, transitions, etc.) without being forced to re-pick a
        # type (C8 — no retroactive invalidation of stored members). Comparing the effective
        # merged value against the stored one detects a real change (a patch that re-sends the
        # SAME code is a no-op and is not re-validated).
        if self._membership_type_of(merged) != self._membership_type_of(existing):
            self._validate_membership_type_reference(tenant_id, merged)
        return self._repo.save_member(tenant_id, merged)

    def delete_member(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Dict[str, Any]:
        """Delete a member (admin-gated at the edge; scope-checked here — design C6).

        Loads the member within the tenant (Property 1), authorizes the delete against its
        scope (:class:`ScopeDenied` → 403 for a scoped caller reaching out of scope), then
        deletes via the repository — which frees the ``membernum#`` uniqueness guard so the
        number can be reused (Property 6). Returns a small deletion receipt.
        """
        existing = self._repo.get_member(tenant_id, member_id)
        if existing is None:
            raise MemberNotFound(tenant_id, member_id)
        self._authorize_write(
            tenant_id,
            existing,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=False,
        )
        self._repo.delete_member(tenant_id, member_id)
        return {"deleted": True, "member_id": member_id}

    # ── Membership create / update / delete / transition (design C1 write / C2) ───────

    def create_membership(
        self,
        tenant_id: str,
        member_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Membership:
        """Create a membership for a member, gated by the parent member's write scope.

        The parent member must exist within the tenant and be writable by the caller (scope —
        :class:`ScopeDenied` → 403), then the membership is persisted via ``save_membership``
        (tenant-scoped — Property 1). The membership id is the client's; a missing id is a
        validation error the repository surfaces.
        """
        self._writable_member_or_raise(
            tenant_id, member_id, allowed_scopes, dimension_key, requester_sub=requester_sub
        )
        membership = self._sanitize_write_payload(body)
        return self._repo.save_membership(tenant_id, member_id, membership)

    def update_membership(
        self,
        tenant_id: str,
        member_id: str,
        membership_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Membership:
        """Update a membership, gated by the parent member's write scope.

        Enforces the parent member's write gate, then loads the membership within the tenant
        (a missing one → :class:`MemberNotFound` → 404), merges the sanitized body over it
        (the ``membership_id`` stays the path's), and re-saves.
        """
        self._writable_member_or_raise(
            tenant_id, member_id, allowed_scopes, dimension_key, requester_sub=requester_sub
        )
        existing = self._repo.get_membership(tenant_id, member_id, membership_id)
        if existing is None:
            raise MemberNotFound(tenant_id, member_id)
        merged = self._deep_merge(dict(existing), self._sanitize_write_payload(body))
        merged["membership_id"] = membership_id
        return self._repo.save_membership(tenant_id, member_id, merged)

    def delete_membership(
        self,
        tenant_id: str,
        member_id: str,
        membership_id: str,
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Dict[str, Any]:
        """Delete a membership (admin-gated at the edge; parent member's write scope here)."""
        self._writable_member_or_raise(
            tenant_id, member_id, allowed_scopes, dimension_key, requester_sub=requester_sub
        )
        self._repo.delete_membership(tenant_id, member_id, membership_id)
        return {"deleted": True, "member_id": member_id, "membership_id": membership_id}

    def transition_member(
        self,
        tenant_id: str,
        member_id: str,
        to_state: MembershipStatus,
        allowed_scopes: Sequence[str],
        *,
        context: Optional[Mapping[str, Any]] = None,
        requester_sub: Optional[str] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> TransitionResult:
        """Apply + PERSIST a lifecycle transition to a member (design C2 / C5, R1.4).

        The full WRITE-path transition (distinct from the pure computation
        :meth:`transition_membership`): load the member within the tenant (Property 1),
        authorize the write against its scope (:class:`ScopeDenied` → 403), compute the
        transition via the lifecycle engine (guards + ``on_transition`` hook fire ONLY on a
        permitted move; a denial raises :class:`TransitionDenied` → 409/422 and never mutates
        or fires the hook), then persist the state-updated record via ``save_member``. Returns
        the :class:`TransitionResult` (now persisted).
        """
        member = self._repo.get_member(tenant_id, member_id)
        if member is None:
            raise MemberNotFound(tenant_id, member_id)
        self._authorize_write(
            tenant_id,
            member,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=False,
        )
        result = self.transition_membership(
            tenant_id, member, to_state, context=context
        )
        self._repo.save_member(tenant_id, result.member)
        return result

    def bulk_transition_members(
        self,
        tenant_id: str,
        member_ids: Sequence[str],
        to_state: MembershipStatus,
        allowed_scopes: Sequence[str],
        *,
        context: Optional[Mapping[str, Any]] = None,
        requester_sub: Optional[str] = None,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Dict[str, Any]:
        """Apply one transition to many members, reporting a per-item outcome (admin capability).

        Applies :meth:`transition_member` to each id independently and records a per-item
        result (``ok`` / the from→to states, or the failure reason) so a partial batch surfaces
        exactly which items moved and which were denied/not-found — never an all-or-nothing
        silent failure. Each item's guards/scope/hook are enforced individually.
        """
        results: List[Dict[str, Any]] = []
        for member_id in member_ids:
            try:
                outcome = self.transition_member(
                    tenant_id,
                    member_id,
                    to_state,
                    allowed_scopes,
                    context=context,
                    requester_sub=requester_sub,
                    dimension_key=dimension_key,
                )
                results.append(
                    {
                        "member_id": member_id,
                        "ok": True,
                        "from": outcome.from_state.value,
                        "to": outcome.to_state.value,
                    }
                )
            except (TransitionDenied, MemberNotFound, ScopeDenied) as exc:
                results.append(
                    {"member_id": member_id, "ok": False, "error": str(exc)}
                )
        return {
            "to_state": to_state.value,
            "results": results,
            "succeeded": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
        }

    # ── Delegates (design C1 write — task 5.2; self-service) ──────────────────────────

    def manage_delegates(
        self,
        tenant_id: str,
        member_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        self_service: bool = True,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Dict[str, Any]:
        """Replace a member's delegate set (design C1 write; self-service allowed).

        The parent member must be writable by the caller — via scope OR, because this is a
        self-service route, because the caller OWNS the record (a member managing their own
        delegates), else :class:`ScopeDenied` → 403. Accepts either ``{"delegates": [...]}``
        or a bare list, and replaces the set via ``save_delegates`` (tenant-scoped — Property
        1). Returns the stored set.
        """
        self._writable_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        if isinstance(body, Mapping):
            raw = body.get("delegates", [])
        else:
            raw = body
        delegates = list(raw) if isinstance(raw, (list, tuple)) else []
        stored = self._repo.save_delegates(tenant_id, member_id, delegates)
        return {"member_id": member_id, "delegates": list(stored)}

    def send_delegate_invitation(
        self,
        tenant_id: str,
        member_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Sequence[str],
        *,
        requester_sub: Optional[str] = None,
        self_service: bool = True,
        dimension_key: str = DEFAULT_SCOPE_DIMENSION_KEY,
    ) -> Dict[str, Any]:
        """Record a delegate INVITATION intent for a prospective delegate (design C1 write).

        Pilot scope: no live email/SNS here (no shared mail util is wired into this module,
        and introducing one would exceed the pilot's minimal, reversible footprint). Instead
        the invitation intent is appended to the member's delegate set as a pending entry
        (``status="invited"``) via the same tenant-scoped ``save_delegates`` seam, so the
        behaviour is real, reversible, and tenant-scoped — a later task can attach an actual
        notification channel behind this method without changing its contract. Requires a
        ``delegate_email`` (or ``email``) in the body; a missing one is a
        :class:`MemberValidationError` (→ 422).

        Note: sending the actual email/SNS notification is intentionally deferred for the
        pilot — this records the intent only.
        """
        self._writable_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        email = None
        if isinstance(body, Mapping):
            email = body.get("delegate_email") or body.get("email")
        if not (isinstance(email, str) and email.strip()):
            raise MemberValidationError(
                {"delegate_email": "a delegate email is required to send an invitation"}
            )
        existing = list(self._repo.list_member_delegates(tenant_id, member_id))
        invitation = {
            "email": email,
            "status": "invited",
            "invited_by": requester_sub,
        }
        existing.append(invitation)
        stored = self._repo.save_delegates(tenant_id, member_id, existing)
        return {"member_id": member_id, "invitation": invitation, "delegates": list(stored)}

    # ── Write-path shared helpers ─────────────────────────────────────────────────────

    def _writable_member_or_raise(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Sequence[str],
        dimension_key: str,
        *,
        requester_sub: Optional[str] = None,
        self_service: bool = False,
    ) -> Member:
        """Load a member within the tenant and authorize a WRITE against it, or raise.

        A missing member is :class:`MemberNotFound` (→ 404); an out-of-scope write is
        :class:`ScopeDenied` (→ 403). Shared by every child-write (membership/delegate)
        so the parent member's write authorization is enforced uniformly (Property 1/4).
        """
        member = self._repo.get_member(tenant_id, member_id)
        if member is None:
            raise MemberNotFound(tenant_id, member_id)
        self._authorize_write(
            tenant_id,
            member,
            allowed_scopes,
            dimension_key,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        return member

    @staticmethod
    def _deep_merge(base: Dict[str, Any], patch: Mapping[str, Any]) -> Dict[str, Any]:
        """Recursively merge ``patch`` into a copy of ``base`` (partial-update semantics).

        Nested mappings (e.g. ``personal`` / ``membership``) are merged key-by-key so a
        partial update touches only the supplied sub-fields; a scalar/list in ``patch``
        replaces the base value. Absent keys in ``patch`` leave the base unchanged — the
        ``partial=True`` update contract.
        """
        result = dict(base)
        for key, value in patch.items():
            if (
                key in result
                and isinstance(result[key], Mapping)
                and isinstance(value, Mapping)
            ):
                result[key] = MembershipService._deep_merge(dict(result[key]), value)
            else:
                result[key] = value
        return result

    # ── Resolved field config (design C3 + C8, R2.3/R2.4 — task 3.3) ──────────────────

    def get_field_config(self, tenant_id: str) -> Dict[str, Any]:
        """Return the tenant's resolved field config for the presentation-only frontend.

        Composes the two authoritative domain pieces (the frontend holds NO rules — it
        renders what this returns, R2.3, verify-before-trust):

        1. :meth:`FieldResolver.resolve` — the fixed base ⊕ per-tenant overlay field config
           (design C3), keyed by the verified ``tenant_id`` (never a client-supplied tenant).
        2. :meth:`MembersRepository.list_membership_types` with ``active_only=True`` — the
           tenant's ACTIVE Lidmaatschap Beheer catalog entries (design C8), ordered by
           ``(order, type_code)``. Soft-deleted (``active=false``) types are excluded, so
           they never appear as a selectable option.

        The active catalog entries are injected as the ``membership_type`` field's ``options``
        (that fixed field is a :class:`~sam.members.domain.fixed_fields.FieldType.REFERENCE`),
        so the frontend renders a dropdown of ONLY that tenant's active types — no free text,
        no hardcoded vocabulary (R2.4).

        Returns a JSON-friendly dict (the edge ``json.dumps`` it): the flat ordered ``fields``
        list, the same fields bucketed ``by_group`` (``personal`` / ``membership`` / overlay),
        and the standalone ``membership_type_options`` catalog feed.
        """
        config = self._field_resolver.resolve(tenant_id)
        options = self._active_membership_type_options(tenant_id)

        fields = [
            self._serialize_field(f, options=options) for f in config.fields
        ]
        by_group: Dict[str, List[Dict[str, Any]]] = {}
        for field_payload in fields:
            by_group.setdefault(field_payload["group"], []).append(field_payload)

        return {
            "tenant_id": config.tenant_id,
            "fields": fields,
            "by_group": by_group,
            "membership_type_options": options,
        }

    def _active_membership_type_options(self, tenant_id: str) -> List[Dict[str, Any]]:
        """The tenant's ACTIVE catalog entries as JSON-friendly dropdown options (design C8).

        Asks the repository for the tenant's active membership types (``active_only=True``,
        tenant-scoped — Property 1), already ordered by ``(order, type_code)``. Each option
        carries the reference ``value`` (``type_code``) the member record stores plus its
        i18n ``label`` and ``order`` for presentation. Retired (soft-deleted) types are
        excluded by the repository, so they never render.

        Reuses :meth:`_serialize_catalog_option` so the dropdown feed and the catalog list
        route (task 3.4) project each entry identically (one serializer, one shape).
        """
        entries = self._repo.list_membership_types(tenant_id, active_only=True)
        return [self._serialize_catalog_option(entry) for entry in entries]

    # ── Lidmaatschap Beheer catalog reads (design C8, R2.4 — task 3.4) ────────────────

    def list_membership_types(
        self, tenant_id: str, *, active_only: bool = False
    ) -> List[Dict[str, Any]]:
        """List the tenant's Lidmaatschap Beheer catalog entries (design C8, R2.4).

        The MANAGEMENT read behind ``GET /membership-types``. Asks the repository for the
        tenant's catalog (keyed by ``tenant_id`` — Property 1), already ordered by
        ``(order, type_code)``, and projects each entry to the JSON-friendly management shape
        (:meth:`_serialize_catalog_entry` — carries ``active`` so an admin can see which types
        are retired). The frontend renders it and enforces nothing (authority stays here).

        Args:
            active_only: ``False`` (default) returns ALL entries incl. soft-deleted
                (``active=false``) so the management view shows retired types (design C8
                soft-delete semantics); ``True`` returns only the assignable ones — the same
                active-only view the dropdown feed uses. The active/all choice is explicit and
                lives on the domain read, not hidden in the handler.
        """
        entries = self._repo.list_membership_types(tenant_id, active_only=active_only)
        return [self._serialize_catalog_entry(entry) for entry in entries]

    def get_membership_type(self, tenant_id: str, type_code: str) -> Dict[str, Any]:
        """Fetch one Lidmaatschap Beheer catalog entry by its ``type_code`` (design C8, R2.4).

        The read behind ``GET /membership-types/{type_code}``. Fetches within the tenant
        (Property 1) and returns the entry in the JSON-friendly management shape. An absent
        code (or one that exists only for another tenant) raises :class:`MembershipTypeNotFound`
        — the edge maps that to a ``404`` (consistent with :class:`MemberNotFound`). A
        soft-deleted (``active=false``) entry is still returned (management shows retired
        types), never a 404.
        """
        entry = self._repo.get_membership_type(tenant_id, type_code)
        if entry is None:
            raise MembershipTypeNotFound(tenant_id, type_code)
        return self._serialize_catalog_entry(entry)

    # ── Lidmaatschap Beheer catalog writes (design C8, R2.4/R1.4 — task 5.3) ──────────
    #
    # CRUD for catalog entries: create + update persist a validated entry; delete is a
    # SOFT-delete (active=false), never a hard delete — existing members keep their reference
    # while the type leaves the dropdown (C8 referential integrity). All tenant-scoped
    # (Property 1) and tenant-agnostic (no ``if tenant``): the catalog is the tenant's own
    # managed data. The repository is the sole DynamoDB touch-point + validates on persist.

    def create_membership_type(
        self, tenant_id: str, body: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Create a Lidmaatschap Beheer catalog entry for the tenant (design C8, R2.4).

        Builds a :class:`MembershipTypeEntry` from the client body, stamping the authoritative
        ``tenant_id`` (never trusting a body ``tenant_id`` — verify-before-trust, Property 2),
        validates it (:meth:`MembershipTypeEntry.validate` — non-blank code with no key
        separator, a non-blank ``nl`` label, an integer ``order``), and persists it. Create is
        NOT an upsert: a ``type_code`` that already exists for the tenant raises
        :class:`MembershipTypeConflict` (→ 409) so a create can never silently mutate a live
        type (an intentional change goes through :meth:`update_membership_type`). A malformed
        body raises :class:`MembershipTypeValidationError` (→ 422). Returns the persisted entry
        in the management shape.
        """
        entry = self._entry_from_body(tenant_id, body)
        entry.validate()
        if self._repo.get_membership_type(tenant_id, entry.type_code) is not None:
            raise MembershipTypeConflict(tenant_id, entry.type_code)
        saved = self._repo.save_membership_type(tenant_id, entry)
        return self._serialize_catalog_entry(saved)

    def update_membership_type(
        self, tenant_id: str, type_code: str, body: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing catalog entry (design C8, R2.4).

        Loads the entry within the tenant (Property 1); an absent code raises
        :class:`MembershipTypeNotFound` (→ 404). Merges the client body over the existing
        entry — the path's ``type_code`` is authoritative for identity (a body ``type_code`` /
        ``tenant_id`` can never move the entry), the ``label`` is replaced when supplied, and
        ``active`` / ``order`` are overridden when present — then validates and persists.
        Returns the updated entry in the management shape.
        """
        existing = self._repo.get_membership_type(tenant_id, type_code)
        if existing is None:
            raise MembershipTypeNotFound(tenant_id, type_code)

        payload = dict(body) if isinstance(body, Mapping) else {}
        label = existing.label
        if "label" in payload and isinstance(payload.get("label"), Mapping):
            label = dict(payload["label"])
        active = bool(payload["active"]) if "active" in payload else existing.active
        order = existing.order
        if "order" in payload:
            try:
                order = int(payload["order"])
            except (TypeError, ValueError):
                raise MembershipTypeValidationError({"order": "must be an integer"})

        updated = MembershipTypeEntry(
            tenant_id=tenant_id,          # authoritative — never the body
            type_code=type_code,          # the path is authoritative for identity
            label=label,
            active=active,
            order=order,
        )
        updated.validate()
        saved = self._repo.save_membership_type(tenant_id, updated)
        return self._serialize_catalog_entry(saved)

    def deactivate_membership_type(
        self, tenant_id: str, type_code: str
    ) -> Dict[str, Any]:
        """Soft-delete (retire) a catalog entry: ``active=false`` — NEVER a hard delete (C8).

        The retired type keeps existing members' references valid (design C8 referential
        integrity) while leaving the dropdown for new/edited members (the active-only feed +
        the reference check both exclude it). Tenant-scoped (Property 1); an absent code raises
        :class:`MembershipTypeNotFound` (→ 404). Idempotent — retiring an already-retired type
        returns it unchanged. Returns the retired entry in the management shape (``active`` will
        be ``False``); the entry is still gettable in the management view (it is not removed).
        """
        retired = self._repo.deactivate_membership_type(tenant_id, type_code)
        if retired is None:
            raise MembershipTypeNotFound(tenant_id, type_code)
        return self._serialize_catalog_entry(retired)

    @staticmethod
    def _entry_from_body(tenant_id: str, body: Mapping[str, Any]) -> MembershipTypeEntry:
        """Build a :class:`MembershipTypeEntry` from a client create body (unvalidated).

        Stamps the authoritative ``tenant_id`` (never a body value — Property 2) and reads the
        entry's ``type_code`` / ``label`` / ``active`` / ``order`` from the body with the
        entity's defaults (``active=True``, ``order=0``). The caller validates the result. A
        non-integer ``order`` is left as-is so :meth:`MembershipTypeEntry.validate` surfaces it
        as a field error (a 422) rather than the handler guessing.
        """
        payload = dict(body) if isinstance(body, Mapping) else {}
        label = payload.get("label")
        return MembershipTypeEntry(
            tenant_id=tenant_id,
            type_code=str(payload.get("type_code", "")),
            label=dict(label) if isinstance(label, Mapping) else {},
            active=bool(payload.get("active", True)),
            order=payload.get("order", 0),
        )

    @staticmethod
    def _serialize_catalog_option(entry: MembershipTypeEntry) -> Dict[str, Any]:
        """Project a catalog entry to the DROPDOWN-OPTION shape (the active-only feed, C8).

        The presentation shape the ``membership_type`` field's ``options`` carry: the
        reference ``value`` (``type_code``) the member record stores, its i18n ``label``, and
        the ``order`` for rendering. It deliberately omits ``active`` — the dropdown only ever
        lists active entries, so the flag would be noise.
        """
        return {
            "value": entry.type_code,
            "label": dict(entry.label),
            "order": int(entry.order),
        }

    @staticmethod
    def _serialize_catalog_entry(entry: MembershipTypeEntry) -> Dict[str, Any]:
        """Project a catalog entry to the MANAGEMENT shape (the catalog read routes, C8).

        Carries the full management view — ``type_code`` (the reference key), i18n ``label``,
        ``active`` (so an admin sees which types are retired), and ``order`` — as pure JSON.
        Distinct from :meth:`_serialize_catalog_option` (the dropdown feed) which drops
        ``active`` because that feed is active-only.
        """
        return {
            "type_code": entry.type_code,
            "label": dict(entry.label),
            "active": bool(entry.active),
            "order": int(entry.order),
        }

    @staticmethod
    def _serialize_field(
        field: ResolvedField,
        *,
        options: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Project a :class:`ResolvedField` into the JSON-friendly shape the frontend renders.

        Carries only what the frontend needs to render (key/group/type/required/label/
        visible/order/origin) and nothing it needs to enforce (authority stays server-side).
        The ``type`` / ``origin`` enums are flattened to their string values so the payload is
        pure JSON. For the ``membership_type`` reference field the active catalog entries are
        injected as ``options``; other fields carry their static ``choices`` (e.g. the closed
        ``status`` enum) as ``options`` when present, else ``None``.
        """
        payload: Dict[str, Any] = {
            "key": field.key,
            "group": field.group,
            "type": field.type.value,
            "required": bool(field.required),
            "label": dict(field.label),
            "visible": bool(field.visible),
            "order": int(field.order),
            "origin": field.origin.value,
        }
        if field.dotted_key() == MEMBERSHIP_TYPE_FIELD_KEY:
            payload["options"] = [dict(o) for o in options]
        elif field.choices is not None:
            payload["options"] = list(field.choices)
        else:
            payload["options"] = None
        return payload
