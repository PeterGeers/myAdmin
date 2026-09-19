"""
S5 Task 5.1 — the **tenant hook registry** (design C5, Rung 3 of the ladder).

Task 5.0 shipped the ``on_transition`` *seam* alone
(:mod:`sam.members.domain.transition_hooks`). Task 5.1 **generalizes** that single seam into
the FULL named-extension-point set the generic membership core (design C2) may call, each
resolved by ``tenant_id`` and each with a **safe generic default** so the core can call any
hook *unconditionally* — an unregistered tenant simply gets the fail-safe default, never an
error and never a tenant conditional (Property 5).

The named extension points (design C5 / `generic-membership-design.md` §3 Rung 3):

- ``validate_member(tenant_id, record) -> errors``  — tenant-specific member validation
  beyond the platform-fixed field rules (e.g. h-dcn Motor / club-field checks). The generic
  core validates the fixed base + the reference/overlay itself; this hook is where a tenant
  layers on rules that are neither config (Rung 1) nor a declarative rule (Rung 2). Safe
  default: **no extra errors** (an empty mapping).
- ``on_transition(tenant_id, member, from_state, to_state) -> None``  — side-effects on a
  permitted lifecycle transition (the seam task 5.0 built). Safe default: **no-op**.
- ``resolve_visible_regions(tenant_id, user, default_regions) -> [region]``  — a tenant's
  regional-visibility nuance. In myAdmin this is **already fully declarative** via
  :func:`sam.members.domain.scope_access.resolve_scope_access` (task 3.1, Rung 1-2), so
  h-dcn does NOT register it — it stays on the safe default, which is a POSITIVE
  rung-distribution finding for the Go/No-Go (a difference that stayed *below* Rung 3). Safe
  default: **pass the already-resolved regions through unchanged** (identity).
- ``derive_member_number(tenant_id, record, next_number) -> str``  — tenant-specific
  member-number derivation. The counter fetch (a storage concern) is threaded in as
  ``next_number`` so the hook itself stays pure/deterministic and storage-agnostic. Safe
  default: **keep the record's existing number**, else stringify ``next_number`` (identity /
  sensible default).
- ``calculate_fee(tenant_id, record, context) -> Optional[number]``  — defined for
  completeness (design C5 mentions it for future clubs); h-dcn does not need it. Safe
  default: **None** (no computed fee).

Design discipline (the ladder, R1.3): a difference is only expressed as a Rung-3 hook when it
is neither tenant **config** (Rung 1) nor a declarative **rule** (Rung 2). The registry is
deliberately tenant-agnostic — it knows hook *names* and ``tenant_id`` keys, never a concrete
tenant (no ``if tenant == "h-dcn"``). h-dcn's concrete implementations live ONLY in the
tenant-scoped package :mod:`sam.members.tenants.hdcn.hooks` (Property 5).

Compatibility with task 5.0: :class:`MembershipService` continues to dispatch
``on_transition`` through a :class:`~sam.members.domain.transition_hooks.TransitionHookRegistry`.
This module keeps that contract intact — :meth:`TenantHookRegistry.transition_registry`
returns a ``TransitionHookRegistry``-shaped view over the unified registry's ``on_transition``
hooks, so a caller can build one unified registry and hand its transition view to the service
without changing the service or any 5.0 test. The unified registry is otherwise storage- and
tenant-agnostic (no boto3 / HTTP).
"""

from __future__ import annotations

from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    Optional,
    Sequence,
)

from .fixed_fields import MembershipStatus
from .transition_hooks import (
    NOOP_TRANSITION_HOOK,
    OnTransitionHook,
    TransitionHookRegistry,
)

__all__ = [
    "HookName",
    "TenantHookRegistry",
    # safe generic defaults (exported so tests / callers can assert identity)
    "default_validate_member",
    "default_on_transition",
    "default_resolve_visible_regions",
    "default_derive_member_number",
    "default_calculate_fee",
]


class HookName(str, Enum):
    """The named extension points the generic core may call (design C5).

    A closed vocabulary so a typo'd hook name is a programming error caught at registration
    time (:meth:`TenantHookRegistry.register`), not a silently-never-called hook. Values are
    the design's names verbatim.
    """

    VALIDATE_MEMBER = "validate_member"
    ON_TRANSITION = "on_transition"
    RESOLVE_VISIBLE_REGIONS = "resolve_visible_regions"
    DERIVE_MEMBER_NUMBER = "derive_member_number"
    CALCULATE_FEE = "calculate_fee"


# ── Safe generic defaults (one per named point) ──────────────────────────────────────
#
# Every named point has a default so the core can call it unconditionally: an unregistered
# tenant resolves to these. Side-effect points are no-ops; value-producing points are an
# identity / empty / sensible default that never grants or invents anything.


def default_validate_member(
    tenant_id: str, record: Mapping[str, Any]
) -> Dict[str, str]:
    """Safe default for ``validate_member``: no tenant-specific errors (an empty mapping).

    The generic core already validates the platform-fixed fields; a tenant with no bespoke
    member validation adds nothing. Returns a fresh mutable mapping so a caller may merge into
    it without mutating a shared constant.
    """
    return {}


def default_on_transition(
    tenant_id: str,
    member: Mapping[str, Any],
    from_state: MembershipStatus,
    to_state: MembershipStatus,
) -> None:
    """Safe default for ``on_transition``: do nothing.

    Delegates to the task-5.0 :data:`~sam.members.domain.transition_hooks.NOOP_TRANSITION_HOOK`
    so the unified registry and the transition seam share one no-op semantics.
    """
    return NOOP_TRANSITION_HOOK(tenant_id, member, from_state, to_state)


def default_resolve_visible_regions(
    tenant_id: str,
    user: Mapping[str, Any],
    default_regions: Sequence[str],
) -> list[str]:
    """Safe default for ``resolve_visible_regions``: pass the resolved regions through.

    Regional visibility in myAdmin is resolved **declaratively** by
    :func:`sam.members.domain.scope_access.resolve_scope_access` (Rung 1-2). This default is
    the identity over the already-resolved ``default_regions`` — a tenant only registers this
    hook if it has a regional nuance that cannot be expressed declaratively (h-dcn does not).
    """
    return list(default_regions)


def default_derive_member_number(
    tenant_id: str,
    record: Mapping[str, Any],
    next_number: Optional[int] = None,
) -> Optional[str]:
    """Safe default for ``derive_member_number``: keep the existing number, else the counter.

    Identity / sensible default: if the record already carries ``membership.member_number``
    it is kept unchanged; otherwise, when a ``next_number`` counter value is threaded in, its
    string form is used; otherwise ``None`` (the caller decides — the default never invents a
    tenant-specific format).
    """
    membership = record.get("membership") if isinstance(record, Mapping) else None
    existing = membership.get("member_number") if isinstance(membership, Mapping) else None
    if existing:
        return str(existing)
    if next_number is not None:
        return str(next_number)
    return None


def default_calculate_fee(
    tenant_id: str,
    record: Mapping[str, Any],
    context: Optional[Mapping[str, Any]] = None,
) -> Optional[float]:
    """Safe default for ``calculate_fee``: no computed fee (``None``).

    Defined for completeness (design C5 mentions it for future clubs). h-dcn does not need it;
    the default computes nothing so the core can call it unconditionally.
    """
    return None


#: The safe generic default for every named point — the fail-safe an unregistered tenant
#: resolves to. Keyed by :class:`HookName` so :meth:`TenantHookRegistry.resolve` can always
#: return a callable without a tenant conditional.
_DEFAULTS: Mapping[HookName, Callable[..., Any]] = {
    HookName.VALIDATE_MEMBER: default_validate_member,
    HookName.ON_TRANSITION: default_on_transition,
    HookName.RESOLVE_VISIBLE_REGIONS: default_resolve_visible_regions,
    HookName.DERIVE_MEMBER_NUMBER: default_derive_member_number,
    HookName.CALCULATE_FEE: default_calculate_fee,
}


class TenantHookRegistry:
    """One tenant-keyed registry of ALL named extension points (design C5, Rung 3).

    The single Rung-3 seam the generic core resolves against. It holds, per
    ``(hook_name, tenant_id)``, a registered implementation, and falls back to that hook's
    **safe generic default** when a tenant has registered none — so the core can call any hook
    unconditionally and an unregistered tenant is fail-safe, never an error (design "missing
    hook → safe generic default").

    Registration and resolution are pure ``(name, tenant_id)`` lookups: the registry has no
    knowledge of any specific tenant and contains no tenant literal (Property 5). h-dcn's
    concrete hooks are bound here by :func:`sam.members.tenants.hdcn.hooks.register_hdcn_hooks`
    — the ONLY place h-dcn logic lives.

    Interop with task 5.0: :meth:`transition_registry` exposes the ``on_transition`` hooks as a
    :class:`~sam.members.domain.transition_hooks.TransitionHookRegistry`, so
    :class:`~sam.members.domain.membership_service.MembershipService` keeps consuming the exact
    same seam it did at 5.0 — the ``on_transition`` dispatch behaviour is identical whether the
    service is handed a bare ``TransitionHookRegistry`` or this unified registry's transition
    view.
    """

    def __init__(self) -> None:
        # name -> { tenant_id -> hook }. Only registered hooks are stored; unregistered
        # (name, tenant) resolves to the default. Every known name gets an (empty) bucket so a
        # resolve for a valid name never KeyErrors on the outer dict.
        self._hooks: Dict[HookName, Dict[str, Callable[..., Any]]] = {
            name: {} for name in HookName
        }

    # ── name coercion ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _coerce_name(hook_name: "HookName | str") -> HookName:
        """Coerce a hook name (enum or its string value) to :class:`HookName`, or raise.

        Accepting the string value as well as the enum keeps call sites ergonomic while still
        rejecting an unknown name loudly (a typo is a programming error, not a silent no-op).
        """
        if isinstance(hook_name, HookName):
            return hook_name
        try:
            return HookName(hook_name)
        except ValueError as exc:
            known = ", ".join(n.value for n in HookName)
            raise ValueError(
                f"unknown hook name {hook_name!r}; known extension points: {known}"
            ) from exc

    # ── registration ───────────────────────────────────────────────────────────────────

    def register(
        self, hook_name: "HookName | str", tenant_id: str, hook: Callable[..., Any]
    ) -> None:
        """Register ``hook`` as ``hook_name``'s implementation for ``tenant_id``.

        Registering again for the same ``(name, tenant)`` replaces the previous hook (last
        registration wins). Rejects an unknown hook name, a blank ``tenant_id``, and a
        non-callable hook — all programming errors that must fail at wiring time, not silently.
        """
        name = self._coerce_name(hook_name)
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if not callable(hook):
            raise TypeError("hook must be callable")
        self._hooks[name][tenant_id] = hook

    def is_registered(self, hook_name: "HookName | str", tenant_id: str) -> bool:
        """Whether ``tenant_id`` has a registered ``hook_name`` (vs. the safe default)."""
        name = self._coerce_name(hook_name)
        return tenant_id in self._hooks[name]

    def registered_hooks(self, tenant_id: str) -> list[HookName]:
        """The named points ``tenant_id`` has actually registered (rung-distribution insight).

        Everything NOT in this list is left on its safe generic default for the tenant — the
        evidence the Go/No-Go uses to count where each tenant's differences landed on the
        ladder (a difference that stayed below Rung 3 never appears here).
        """
        return [name for name in HookName if tenant_id in self._hooks[name]]

    # ── resolution / dispatch ──────────────────────────────────────────────────────────

    def resolve(
        self, hook_name: "HookName | str", tenant_id: str
    ) -> Callable[..., Any]:
        """Return ``tenant_id``'s ``hook_name`` implementation, or its safe generic default.

        The core always gets a callable back — an unregistered ``(name, tenant)`` resolves to
        the hook's default (:data:`_DEFAULTS`), so calling a hook is unconditional and never
        branches on the tenant.
        """
        name = self._coerce_name(hook_name)
        return self._hooks[name].get(tenant_id, _DEFAULTS[name])

    def dispatch(
        self, hook_name: "HookName | str", tenant_id: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Resolve ``hook_name`` for ``tenant_id`` and invoke it with ``*args, **kwargs``.

        A thin convenience over :meth:`resolve` — the generic core calls this so it never
        holds a hook reference or branches on registration. Returns whatever the resolved hook
        returns (``None`` for the side-effect points, a value for the value-producing ones).
        """
        hook = self.resolve(hook_name, tenant_id)
        return hook(tenant_id, *args, **kwargs)

    # ── task-5.0 interop: an on_transition view the MembershipService consumes ──────────

    def transition_registry(self) -> TransitionHookRegistry:
        """A :class:`TransitionHookRegistry` view over this registry's ``on_transition`` hooks.

        Lets a caller build ONE unified registry and still hand
        :class:`~sam.members.domain.membership_service.MembershipService` the exact seam it has
        consumed since task 5.0 — the service's ``on_transition`` dispatch is byte-for-byte
        identical. Registered ``on_transition`` hooks are copied across; an unregistered tenant
        resolves to :data:`~sam.members.domain.transition_hooks.NOOP_TRANSITION_HOOK` there,
        matching this registry's ``on_transition`` default.
        """
        on_transition_hooks: Dict[str, OnTransitionHook] = dict(
            self._hooks[HookName.ON_TRANSITION]
        )
        return TransitionHookRegistry(on_transition_hooks)
