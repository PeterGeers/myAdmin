"""
S5 Task 5.1 — the **tenant hook registry** (design C5, Rung 3 of the ladder).

The named-extension-point set the generic membership core (design C2) may call, each resolved
by ``tenant_id`` and each with a **safe generic default** so the core can call any hook
*unconditionally* — an unregistered tenant simply gets the fail-safe default, never an error
and never a tenant conditional (Property 5).

The named extension points (design C5 / `generic-membership-design.md` §3 Rung 3):

- ``validate_member(tenant_id, record) -> errors``  — tenant-specific member validation
  beyond the platform-fixed field rules (e.g. h-dcn Motor / club-field checks). The generic
  core validates the fixed base + the reference/overlay itself; this hook is where a tenant
  layers on rules that are neither config (Rung 1) nor a declarative rule (Rung 2). Safe
  default: **no extra errors** (an empty mapping).
- ``resolve_visible_regions(tenant_id, user, default_regions) -> [region]``  — a tenant's
  regional-visibility nuance. In myAdmin this is **already fully declarative** via
  :func:`sam.members.domain.scope_access.resolve_scope_access` (task 3.1, Rung 1-2), so
  h-dcn does NOT register it — it stays on the safe default, which is a POSITIVE
  rung-distribution finding for the Go/No-Go (a difference that stayed *below* Rung 3). Safe
  default: **pass the already-resolved regions through unchanged** (identity).
- ``calculate_fee(tenant_id, record, context) -> Optional[number]``  — defined for
  completeness (design C5 mentions it for future clubs); h-dcn does not need it. Safe
  default: **None** (no computed fee).

Design discipline (the ladder, R1.3): a difference is only expressed as a Rung-3 hook when it
is neither tenant **config** (Rung 1) nor a declarative **rule** (Rung 2). The registry is
deliberately tenant-agnostic — it knows hook *names* and ``tenant_id`` keys, never a concrete
tenant (no ``if tenant == "h-dcn"``). h-dcn's concrete implementations live ONLY in the
tenant-scoped package :mod:`sam.members.tenants.hdcn.hooks` (Property 5).

The ``on_transition`` extension point was RETIRED with the membership lifecycle engine (see
spec ``retire-members-status-lifecycle-engine``): status is now a plain tenant-driven field
and a status change is an ordinary member edit, so there is no transition seam to dispatch.
The unified registry is otherwise storage- and tenant-agnostic (no boto3 / HTTP).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import (
    Any,
)

__all__ = [
    "HookName",
    "TenantHookRegistry",
    # safe generic defaults (exported so tests / callers can assert identity)
    "default_validate_member",
    "default_resolve_visible_regions",
    "default_calculate_fee",
]

# s5k: the ``derive_member_number`` extension point was RETIRED — member numbering is no longer
# auto-generated on any plane (``member_number`` is a plain optional string the caller/import
# supplies). The HookName value + its safe default were removed.


class HookName(str, Enum):
    """The named extension points the generic core may call (design C5).

    A closed vocabulary so a typo'd hook name is a programming error caught at registration
    time (:meth:`TenantHookRegistry.register`), not a silently-never-called hook. Values are
    the design's names verbatim.
    """

    VALIDATE_MEMBER = "validate_member"
    RESOLVE_VISIBLE_REGIONS = "resolve_visible_regions"
    CALCULATE_FEE = "calculate_fee"


# ── Safe generic defaults (one per named point) ──────────────────────────────────────
#
# Every named point has a default so the core can call it unconditionally: an unregistered
# tenant resolves to these. Side-effect points are no-ops; value-producing points are an
# identity / empty / sensible default that never grants or invents anything.


def default_validate_member(
    tenant_id: str, record: Mapping[str, Any]
) -> dict[str, str]:
    """Safe default for ``validate_member``: no tenant-specific errors (an empty mapping).

    The generic core already validates the platform-fixed fields; a tenant with no bespoke
    member validation adds nothing. Returns a fresh mutable mapping so a caller may merge into
    it without mutating a shared constant.
    """
    return {}


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


def default_calculate_fee(
    tenant_id: str,
    record: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
) -> float | None:
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
    HookName.RESOLVE_VISIBLE_REGIONS: default_resolve_visible_regions,
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
    """

    def __init__(self) -> None:
        # name -> { tenant_id -> hook }. Only registered hooks are stored; unregistered
        # (name, tenant) resolves to the default. Every known name gets an (empty) bucket so a
        # resolve for a valid name never KeyErrors on the outer dict.
        self._hooks: dict[HookName, dict[str, Callable[..., Any]]] = {
            name: {} for name in HookName
        }

    # ── name coercion ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _coerce_name(hook_name: HookName | str) -> HookName:
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
        self, hook_name: HookName | str, tenant_id: str, hook: Callable[..., Any]
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

    def is_registered(self, hook_name: HookName | str, tenant_id: str) -> bool:
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
        self, hook_name: HookName | str, tenant_id: str
    ) -> Callable[..., Any]:
        """Return ``tenant_id``'s ``hook_name`` implementation, or its safe generic default.

        The core always gets a callable back — an unregistered ``(name, tenant)`` resolves to
        the hook's default (:data:`_DEFAULTS`), so calling a hook is unconditional and never
        branches on the tenant.
        """
        name = self._coerce_name(hook_name)
        return self._hooks[name].get(tenant_id, _DEFAULTS[name])

    def dispatch(
        self, hook_name: HookName | str, tenant_id: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Resolve ``hook_name`` for ``tenant_id`` and invoke it with ``*args, **kwargs``.

        A thin convenience over :meth:`resolve` — the generic core calls this so it never
        holds a hook reference or branches on registration. Returns whatever the resolved hook
        returns (``None`` for the side-effect points, a value for the value-producing ones).
        """
        hook = self.resolve(hook_name, tenant_id)
        return hook(tenant_id, *args, **kwargs)


