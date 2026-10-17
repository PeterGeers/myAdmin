"""
S5 Task 5.1 — tests for the **tenant hook registry** (design C5, Rung 3) + h-dcn's hooks.

Two layers under test:

1. :class:`sam.members.domain.tenant_hooks.TenantHookRegistry` — the generic, tenant-agnostic
   registry of named extension points. Pins: register/resolve by ``(name, tenant_id)``; an
   **unregistered** ``(name, tenant)`` resolves to that hook's **safe generic default** for
   EVERY named point; the safe defaults behave correctly (no-op / empty-errors / identity /
   sensible default); and an unknown hook name is rejected. (The former ``on_transition`` point
   and its ``TransitionHookRegistry`` interop were removed with the lifecycle engine —
   retire-members-status-lifecycle-engine §B: status is a plain open enum edited as an ordinary
   field, so there is no transition hook seam.)

2. :mod:`sam.members.tenants.hdcn.hooks` — h-dcn's concrete Rung-3 implementations. Pins:
   ``register_hdcn_hooks`` binds ONLY the hooks h-dcn needs (``validate_member``); the other
   named points stay on their safe defaults; each registered
   hook does what h-dcn needs; and a DIFFERENT / unregistered tenant gets the safe default
   (Property 5 — no tenant literal leaks into the generic core).

Validates: Requirements R4.3
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.tenant_hooks import (
    HookName,
    TenantHookRegistry,
    default_calculate_fee,
    default_resolve_visible_regions,
    default_validate_member,
)
from sam.members.tenants.hdcn.hooks import (
    HDCN_TENANT_ID,
    hdcn_validate_member,
    register_hdcn_hooks,
)

# h-dcn's active-member hook now compares the plain string literal "active" (the closed
# `MembershipStatus` enum was deleted with the lifecycle engine — §C), so these tests author
# the status value as a plain string.
_ACTIVE = "active"
_PENDING = "pending"

# ── The generic registry: resolve-by-(name, tenant) + safe defaults ───────────────────


def test_register_and_resolve_binds_hook_by_name_and_tenant():
    registry = TenantHookRegistry()
    sentinel = lambda *a, **k: "bound"
    registry.register(HookName.VALIDATE_MEMBER, "club", sentinel)

    assert registry.is_registered(HookName.VALIDATE_MEMBER, "club") is True
    assert registry.resolve(HookName.VALIDATE_MEMBER, "club") is sentinel


def test_register_accepts_string_hook_name():
    registry = TenantHookRegistry()
    sentinel = lambda *a, **k: None
    registry.register("validate_member", "club", sentinel)
    assert registry.resolve("validate_member", "club") is sentinel


@pytest.mark.parametrize(
    "hook_name, expected_default",
    [
        (HookName.VALIDATE_MEMBER, default_validate_member),
        (HookName.RESOLVE_VISIBLE_REGIONS, default_resolve_visible_regions),
        (HookName.CALCULATE_FEE, default_calculate_fee),
    ],
)
def test_unregistered_hook_resolves_to_safe_default_for_every_named_point(
    hook_name, expected_default
):
    # An empty registry: EVERY named point resolves to its own safe generic default.
    registry = TenantHookRegistry()
    assert registry.is_registered(hook_name, "any-tenant") is False
    assert registry.resolve(hook_name, "any-tenant") is expected_default


def test_registering_one_hook_does_not_affect_other_named_points():
    registry = TenantHookRegistry()
    registry.register(HookName.VALIDATE_MEMBER, "club", lambda *a, **k: {"x": "y"})
    # The other points for the SAME tenant stay on their defaults.
    assert registry.resolve(HookName.CALCULATE_FEE, "club") is default_calculate_fee
    assert (
        registry.resolve(HookName.RESOLVE_VISIBLE_REGIONS, "club")
        is default_resolve_visible_regions
    )


def test_register_replaces_previous_hook_for_same_name_and_tenant():
    registry = TenantHookRegistry()
    registry.register(HookName.VALIDATE_MEMBER, "club", lambda *a, **k: {})
    latest = lambda *a, **k: {"last": "wins"}
    registry.register(HookName.VALIDATE_MEMBER, "club", latest)
    assert registry.resolve(HookName.VALIDATE_MEMBER, "club") is latest


def test_register_rejects_unknown_hook_name():
    registry = TenantHookRegistry()
    with pytest.raises(ValueError):
        registry.register("not_a_hook", "club", lambda *a, **k: None)


def test_register_rejects_blank_tenant_and_non_callable():
    registry = TenantHookRegistry()
    with pytest.raises(ValueError):
        registry.register(HookName.VALIDATE_MEMBER, "  ", lambda *a, **k: None)
    with pytest.raises(TypeError):
        registry.register(HookName.VALIDATE_MEMBER, "club", object())


def test_resolve_rejects_unknown_hook_name():
    registry = TenantHookRegistry()
    with pytest.raises(ValueError):
        registry.resolve("bogus", "club")


# ── The safe defaults behave correctly ────────────────────────────────────────────────


def test_default_validate_member_returns_no_errors():
    assert default_validate_member("club", {"membership": {"status": _ACTIVE}}) == {}


def test_default_resolve_visible_regions_is_identity_over_resolved_regions():
    assert default_resolve_visible_regions("club", {"sub": "u1"}, ["Noord", "Zuid"]) == [
        "Noord",
        "Zuid",
    ]


def test_default_calculate_fee_returns_none():
    assert default_calculate_fee("club", {"membership": {}}, {}) is None


# ── dispatch convenience ────────────────────────────────────────────────────────────


def test_dispatch_calls_resolved_hook_with_tenant_and_args():
    registry = TenantHookRegistry()
    seen = {}

    def validate(tenant_id, record):
        seen["tenant"] = tenant_id
        seen["record"] = record
        return {"e": "r"}

    registry.register(HookName.VALIDATE_MEMBER, "club", validate)
    out = registry.dispatch(HookName.VALIDATE_MEMBER, "club", {"member_id": "m1"})
    assert out == {"e": "r"}
    assert seen == {"tenant": "club", "record": {"member_id": "m1"}}


def test_dispatch_of_unregistered_point_uses_the_safe_default():
    registry = TenantHookRegistry()
    # No hook registered → dispatch runs the default. calculate_fee default → None.
    assert registry.dispatch(HookName.CALCULATE_FEE, "club", {"membership": {}}, {}) is None
    # validate default → empty errors.
    assert registry.dispatch(HookName.VALIDATE_MEMBER, "club", {}) == {}


# ── h-dcn's registered hooks ──────────────────────────────────────────────────────────


def test_register_hdcn_hooks_binds_only_the_hooks_hdcn_needs():
    registry = TenantHookRegistry()
    register_hdcn_hooks(registry)

    # Registered (Rung 3): validate_member only. (s5k retired derive_member_number.)
    assert registry.is_registered(HookName.VALIDATE_MEMBER, HDCN_TENANT_ID)
    assert registry.resolve(HookName.VALIDATE_MEMBER, HDCN_TENANT_ID) is hdcn_validate_member

    # Left on the safe default (Rung 1-2 / unused): resolve_visible_regions, calculate_fee —
    # the rung-distribution finding for the Go/No-Go. (on_transition was removed with the
    # lifecycle engine — §B.)
    assert not registry.is_registered(HookName.RESOLVE_VISIBLE_REGIONS, HDCN_TENANT_ID)
    assert not registry.is_registered(HookName.CALCULATE_FEE, HDCN_TENANT_ID)

    assert registry.registered_hooks(HDCN_TENANT_ID) == [HookName.VALIDATE_MEMBER]


def test_hdcn_validate_member_requires_motorcycle_only_when_active():
    active_without_motor = {"membership": {"status": _ACTIVE}, "overlay": {}}
    errors = hdcn_validate_member(HDCN_TENANT_ID, active_without_motor)
    assert "overlay.motor" in errors

    active_with_motor = {
        "membership": {"status": _ACTIVE},
        "overlay": {"motor": "BMW R1250GS"},
    }
    assert hdcn_validate_member(HDCN_TENANT_ID, active_with_motor) == {}

    # motor_type is an accepted alternate key.
    active_with_motor_type = {
        "membership": {"status": _ACTIVE},
        "overlay": {"motor_type": "Honda"},
    }
    assert hdcn_validate_member(HDCN_TENANT_ID, active_with_motor_type) == {}

    # A non-active member is not required to have a motorcycle yet.
    pending = {"membership": {"status": _PENDING}, "overlay": {}}
    assert hdcn_validate_member(HDCN_TENANT_ID, pending) == {}


def test_hdcn_hooks_do_not_leak_to_other_tenants():
    # h-dcn's hooks are registered for "h-dcn" only; a different tenant gets the safe default
    # (Property 5 — no tenant literal in the generic core; resolution is by tenant_id).
    registry = TenantHookRegistry()
    register_hdcn_hooks(registry)

    # h-dcn's validate_member is registered for "h-dcn" only; another tenant gets the safe
    # default (Property 5 — resolution is by tenant_id, no tenant literal in the core).
    assert not registry.is_registered(HookName.VALIDATE_MEMBER, "other-club")
    assert registry.resolve(HookName.VALIDATE_MEMBER, "other-club") is default_validate_member
