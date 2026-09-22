"""
S5 Task 5.0 — the ``on_transition`` **hook seam** (design C5, Rung 3 — the SEAM only).

This defines the extension point the generic lifecycle engine
(:meth:`~sam.members.domain.membership_service.MembershipService.transition_membership`)
calls **after** a transition has been permitted by the graph + declarative guards (Rung 1 +
Rung 2, ``lifecycle_config.py``), so a tenant can run genuinely bespoke side-effects that
cannot be expressed as config or a declarative rule — e.g. h-dcn sending a welcome mail on
activation, or stamping a derived member number (design C5 / `generic-membership-design.md`
§3 Rung 3).

Scope of THIS task (5.0): **the seam + a SAFE GENERIC DEFAULT only.** It ships:

- :class:`OnTransitionHook` — the named hook interface, signature per design C5
  ``on_transition(tenant, member, from_state, to_state)``;
- :class:`TransitionHookRegistry` — a tenant-keyed registry/dispatch that resolves a hook by
  ``tenant_id``; and
- :data:`NOOP_TRANSITION_HOOK` — the safe generic default (a pure no-op) an **unregistered**
  tenant resolves to, so the engine can always call *a* hook and a tenant that needs no
  side-effect pays nothing.

The actual h-dcn hook implementations + the full population of the registry are **task 5.1**;
this module only guarantees the engine has a stable seam to call and a fail-safe default. It
is tenant-agnostic (dispatch is by ``tenant_id`` — no ``if tenant == "h-dcn"``, Property 5),
storage-agnostic (no boto3 / HTTP; a *hook implementation* may do I/O, but the seam does
not), and side-effect-free by default.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

from .fixed_fields import MembershipStatus

__all__ = [
    "OnTransitionHook",
    "NOOP_TRANSITION_HOOK",
    "noop_on_transition",
    "TransitionHookRegistry",
]


@runtime_checkable
class OnTransitionHook(Protocol):
    """The ``on_transition`` extension-point signature (design C5).

    Invoked by the engine once a membership transition has been *permitted* (the graph allows
    it and every declarative guard held). A hook runs side-effects; its return value is
    ignored by the engine. A hook MUST NOT be relied on to *veto* a transition — vetoing is
    the job of the declarative guards (Rung 2), which run first; a hook that raises signals a
    side-effect failure, which the write route (task 5.2) decides how to surface.

    Args:
        tenant_id: The tenant the transition belongs to (dispatch key).
        member: The member record being transitioned (post-decision, pre-persist).
        from_state: The state the member is leaving.
        to_state: The state the member is entering.
    """

    def __call__(
        self,
        tenant_id: str,
        member: Mapping[str, Any],
        from_state: MembershipStatus,
        to_state: MembershipStatus,
    ) -> None:
        ...


def noop_on_transition(
    tenant_id: str,
    member: Mapping[str, Any],
    from_state: MembershipStatus,
    to_state: MembershipStatus,
) -> None:
    """The safe generic default hook: do nothing.

    A tenant with no registered ``on_transition`` hook resolves to this (via
    :meth:`TransitionHookRegistry.resolve`), so the engine can always call *a* hook without a
    tenant conditional and a tenant that needs no side-effect on a transition pays nothing.
    """
    return None


#: The single shared no-op instance the engine falls back to for an unregistered tenant.
NOOP_TRANSITION_HOOK: OnTransitionHook = noop_on_transition


class TransitionHookRegistry:
    """A tenant-keyed registry of :class:`OnTransitionHook` implementations (design C5).

    The dispatch seam the engine uses: :meth:`resolve` maps a ``tenant_id`` to its registered
    hook, falling back to :data:`NOOP_TRANSITION_HOOK` when a tenant has registered none
    (the fail-safe default — an unregistered hook is a no-op, never an error). Task 5.1
    populates it with h-dcn's implementations from a tenant-scoped package; this module ships
    it empty so the engine has a stable seam from task 5.0 onward.

    It is deliberately tiny and tenant-agnostic: registration and resolution are pure
    ``tenant_id`` lookups — the registry has no knowledge of any specific tenant (Property 5).
    """

    def __init__(self, hooks: Optional[Mapping[str, OnTransitionHook]] = None):
        self._hooks: dict[str, OnTransitionHook] = dict(hooks or {})

    def register(self, tenant_id: str, hook: OnTransitionHook) -> None:
        """Register ``hook`` as the ``on_transition`` implementation for ``tenant_id``.

        Registering again for the same tenant replaces the previous hook (last registration
        wins) — task 5.1 registers h-dcn's here.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if not callable(hook):
            raise TypeError("hook must be callable (an OnTransitionHook)")
        self._hooks[tenant_id] = hook

    def is_registered(self, tenant_id: str) -> bool:
        """Whether ``tenant_id`` has a registered hook (as opposed to the no-op default)."""
        return tenant_id in self._hooks

    def resolve(self, tenant_id: str) -> OnTransitionHook:
        """Return the hook registered for ``tenant_id``, or the safe no-op default.

        The engine always gets a callable back — an unregistered tenant resolves to
        :data:`NOOP_TRANSITION_HOOK`, so calling a hook is unconditional and never branches on
        the tenant.
        """
        return self._hooks.get(tenant_id, NOOP_TRANSITION_HOOK)

    def dispatch(
        self,
        tenant_id: str,
        member: Mapping[str, Any],
        from_state: MembershipStatus,
        to_state: MembershipStatus,
    ) -> None:
        """Resolve the tenant's hook and invoke it with the transition facts (design C5).

        A convenience the engine calls after a transition is permitted: resolve by tenant,
        then call the hook (the no-op default when none is registered). The hook's return
        value is ignored.
        """
        hook = self.resolve(tenant_id)
        hook(tenant_id, member, from_state, to_state)
