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

**Scope filtering (design C4, Property 4/6).** ``allowed_scopes`` is a PER-DIMENSION map
``{dimension_key: [values]}`` (s5d ODx2 Option A) the handler edge resolves over EVERY
enabled dimension. A member is visible only if it passes EVERY dimension (AND) — for each
``(dimension_key, values)`` entry, evaluated against the member's OWN field for that
dimension:

- ``values == ["*"]`` (:data:`~sam.members.domain.scope_dimensions.WILDCARD`) → passes that
  dimension (tenant-wide for that axis).
- a non-empty **subset** → passes that dimension only when the member's canonical value for
  the dimension's field intersects the subset (a scoped user stays inside their tenant,
  narrowed to their values).
- ``values == []`` → **fails** that dimension (the scope-deny default, Property 4).

An EMPTY map ``{}`` is deny (see nothing). Single-dimension tenants (h-dcn ``region``) are
the N=1 case — one map entry — so behaviour is unchanged; there is no special-casing of one
vs many dimensions. A denied read is a scope miss: a list returns empty, a single fetch the
edge maps to a 404-style "no such member for you", never a cross-scope leak.

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

from sam.members.domain._membership_catalog import CatalogMixin
from sam.members.domain._membership_errors import (
    DEFAULT_SCOPE_DIMENSION_KEY,
    MEMBERSHIP_STATUS_FIELD_KEY,
    MEMBERSHIP_TYPE_FIELD_KEY,
    MemberNotFound,
    MembershipTypeConflict,
    MembershipTypeNotFound,
    MemberValidationError,
    ScopeDenied,
    TransitionDenied,
    TransitionResult,
)
from sam.members.domain._membership_lifecycle import LifecycleMixin
from sam.members.domain._membership_reads import ReadsMixin
from sam.members.domain._membership_writes import WritesMixin
from sam.members.domain.field_resolver import (
    FieldResolver,
    StaticOverlayProvider,
    TenantOverlayProvider,
)
from sam.members.domain.lifecycle_config import (
    LifecycleConfigProvider,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.scope_dimensions import (
    ScopeConfigProvider,
)
from sam.members.domain.tenant_hooks import TenantHookRegistry
from sam.members.domain.transition_hooks import TransitionHookRegistry
from sam.members.domain.view_contexts import (
    StaticViewContextsProvider,
    ViewContextsProvider,
)
from sam.members.repository.members_repository import (
    MembersRepository,
)

__all__ = [
    "DEFAULT_SCOPE_DIMENSION_KEY",
    "MEMBERSHIP_STATUS_FIELD_KEY",
    "MEMBERSHIP_TYPE_FIELD_KEY",
    "MemberNotFound",
    "MemberValidationError",
    "MembershipService",
    "MembershipTypeConflict",
    "MembershipTypeNotFound",
    "ScopeDenied",
    "TransitionDenied",
    "TransitionResult",
]


class MembershipService(ReadsMixin, LifecycleMixin, WritesMixin, CatalogMixin):
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
            the WRITE path (task 5.2) can also reach ``validate_member``; if only
            ``transition_hooks`` is supplied, the write-path hooks fall back to their safe
            generic defaults.
        tenant_hooks: The unified :class:`~sam.members.domain.tenant_hooks.TenantHookRegistry`
            (design C5, all named extension points). When supplied, the WRITE path resolves
            ``validate_member`` through it AND the engine dispatches
            ``on_transition`` through its ``transition_registry()`` view — so one registry
            wires every hook. ``transition_hooks`` (the 5.0 seam) is honoured for backwards
            compatibility when ``tenant_hooks`` is omitted.
    """

    def __init__(
        self,
        repository: MembersRepository,
        overlay_provider: TenantOverlayProvider | None = None,
        lifecycle_provider: LifecycleConfigProvider | None = None,
        transition_hooks: TransitionHookRegistry | None = None,
        tenant_hooks: TenantHookRegistry | None = None,
        view_contexts_provider: ViewContextsProvider | None = None,
        scope_config_provider: ScopeConfigProvider | None = None,
    ):
        self._repo = repository
        self._field_resolver = FieldResolver(
            overlay_provider if overlay_provider is not None else StaticOverlayProvider()
        )
        # S5j (design D1a): the scope-config provider supplies the tenant's ScopeConfig, from
        # which get_field_config / the write validator derive a {dimension.field: values} map so
        # a scope-dimension-backed overlay enum (h-dcn `region`) sources its dropdown choices
        # from `scope_dimensions.values` (single source of truth). Optional — a service built
        # without it resolves exactly as before (no scope-sourced choices).
        self._scope_config_provider: ScopeConfigProvider | None = scope_config_provider
        # The view-context seam (S5c task 3.2, design C-VIEW). Mirrors the overlay/scope
        # provider injection: the service depends only on the ViewContextsProvider Protocol,
        # never on where the contexts live. Defaults to the empty StaticViewContextsProvider,
        # which yields exactly one default context per tenant (empty-is-valid, R5.1) — so a
        # service built without a provider still surfaces a valid context on get_field_config.
        self._view_contexts_provider: ViewContextsProvider = (
            view_contexts_provider
            if view_contexts_provider is not None
            else StaticViewContextsProvider()
        )
        self._lifecycle_provider: LifecycleConfigProvider = (
            lifecycle_provider
            if lifecycle_provider is not None
            else StaticLifecycleConfigProvider()
        )
        # The unified Rung-3 registry (design C5). The WRITE path (task 5.2) resolves
        # validate_member through it; an unregistered tenant resolves to the safe generic
        # default (Property 5). Defaults to an empty registry.
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

