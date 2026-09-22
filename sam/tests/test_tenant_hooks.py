"""
S5 Task 5.1 — tests for the **tenant hook registry** (design C5, Rung 3) + h-dcn's hooks.

Two layers under test:

1. :class:`sam.members.domain.tenant_hooks.TenantHookRegistry` — the generic, tenant-agnostic
   registry of named extension points. Pins: register/resolve by ``(name, tenant_id)``; an
   **unregistered** ``(name, tenant)`` resolves to that hook's **safe generic default** for
   EVERY named point; the safe defaults behave correctly (no-op / empty-errors / identity /
   sensible default); an unknown hook name is rejected; and the ``on_transition`` view stays
   byte-for-byte compatible with the task-5.0 ``TransitionHookRegistry`` the
   :class:`MembershipService` consumes (so the 5.0 dispatch behaviour is identical).

2. :mod:`sam.members.tenants.hdcn.hooks` — h-dcn's concrete Rung-3 implementations. Pins:
   ``register_hdcn_hooks`` binds ONLY the hooks h-dcn needs (``derive_member_number``,
   ``validate_member``); the other named points stay on their safe defaults; each registered
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

from sam.members.domain.fixed_fields import MembershipStatus as MS
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import MembershipService
from sam.members.domain.tenant_hooks import (
    HookName,
    TenantHookRegistry,
    default_calculate_fee,
    default_derive_member_number,
    default_on_transition,
    default_resolve_visible_regions,
    default_validate_member,
)
from sam.members.domain.transition_hooks import (
    NOOP_TRANSITION_HOOK,
    TransitionHookRegistry,
)
from sam.members.tenants.hdcn.hooks import (
    HDCN_TENANT_ID,
    hdcn_derive_member_number,
    hdcn_validate_member,
    register_hdcn_hooks,
)


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
    registry.register("derive_member_number", "club", sentinel)
    assert registry.resolve("derive_member_number", "club") is sentinel


@pytest.mark.parametrize(
    "hook_name, expected_default",
    [
        (HookName.VALIDATE_MEMBER, default_validate_member),
        (HookName.ON_TRANSITION, default_on_transition),
        (HookName.RESOLVE_VISIBLE_REGIONS, default_resolve_visible_regions),
        (HookName.DERIVE_MEMBER_NUMBER, default_derive_member_number),
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
    assert registry.resolve(HookName.ON_TRANSITION, "club") is default_on_transition
    assert (
        registry.resolve(HookName.DERIVE_MEMBER_NUMBER, "club")
        is default_derive_member_number
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
    assert default_validate_member("club", {"membership": {"status": "active"}}) == {}


def test_default_on_transition_is_a_noop_returning_none():
    assert default_on_transition("club", {}, MS.PENDING, MS.ACTIVE) is None


def test_default_resolve_visible_regions_is_identity_over_resolved_regions():
    assert default_resolve_visible_regions("club", {"sub": "u1"}, ["Noord", "Zuid"]) == [
        "Noord",
        "Zuid",
    ]


def test_default_derive_member_number_keeps_existing_then_falls_back_to_counter():
    keep = default_derive_member_number("club", {"membership": {"member_number": "X-9"}}, 42)
    assert keep == "X-9"
    counter = default_derive_member_number("club", {"membership": {}}, 42)
    assert counter == "42"
    none = default_derive_member_number("club", {"membership": {}}, None)
    assert none is None


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
    # No hook registered → dispatch runs the default (no-op → None).
    assert registry.dispatch(HookName.ON_TRANSITION, "club", {}, MS.PENDING, MS.ACTIVE) is None
    # validate default → empty errors.
    assert registry.dispatch(HookName.VALIDATE_MEMBER, "club", {}) == {}


# ── task-5.0 interop: the on_transition view is identical to a TransitionHookRegistry ──


def test_transition_registry_view_carries_registered_on_transition_hooks():
    registry = TenantHookRegistry()
    hook = lambda tenant_id, member, frm, to: None
    registry.register(HookName.ON_TRANSITION, "club", hook)

    view = registry.transition_registry()
    assert isinstance(view, TransitionHookRegistry)
    assert view.is_registered("club") is True
    assert view.resolve("club") is hook
    # An unregistered tenant in the view resolves to the same 5.0 no-op default.
    assert view.resolve("other") is NOOP_TRANSITION_HOOK


def test_membership_service_dispatches_on_transition_through_the_unified_registry_view():
    # Build ONE unified registry, register an on_transition hook, hand its view to the service.
    calls = []

    def on_transition(tenant_id, member, frm, to):
        calls.append((tenant_id, member["membership"]["status"], frm, to))

    unified = TenantHookRegistry()
    unified.register(HookName.ON_TRANSITION, "h-dcn", on_transition)

    class _Repo:
        def get_member(self, t, m):
            return None

        def list_members(self, t, *, filters=None, scope_filter=None):
            return []

        def list_membership_types(self, t, *, active_only=False):
            return []

    svc = MembershipService(
        _Repo(),
        lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        transition_hooks=unified.transition_registry(),
    )

    member = {
        "member_id": "m-1",
        "membership": {"status": MS.PENDING.value, "member_number": "L-000001"},
        "personal": {"email": "rider@h-dcn.nl"},
    }
    result = svc.transition_membership("h-dcn", member, MS.ACTIVE)
    assert result.to_state is MS.ACTIVE
    assert calls == [("h-dcn", MS.ACTIVE.value, MS.PENDING, MS.ACTIVE)]


# ── h-dcn's registered hooks ──────────────────────────────────────────────────────────


def test_register_hdcn_hooks_binds_only_the_hooks_hdcn_needs():
    registry = TenantHookRegistry()
    register_hdcn_hooks(registry)

    # Registered (Rung 3): derive_member_number + validate_member.
    assert registry.is_registered(HookName.DERIVE_MEMBER_NUMBER, HDCN_TENANT_ID)
    assert registry.is_registered(HookName.VALIDATE_MEMBER, HDCN_TENANT_ID)
    assert registry.resolve(HookName.DERIVE_MEMBER_NUMBER, HDCN_TENANT_ID) is (
        hdcn_derive_member_number
    )
    assert registry.resolve(HookName.VALIDATE_MEMBER, HDCN_TENANT_ID) is hdcn_validate_member

    # Left on the safe default (Rung 1-2 / unused): on_transition, resolve_visible_regions,
    # calculate_fee — the rung-distribution finding for the Go/No-Go.
    assert not registry.is_registered(HookName.ON_TRANSITION, HDCN_TENANT_ID)
    assert not registry.is_registered(HookName.RESOLVE_VISIBLE_REGIONS, HDCN_TENANT_ID)
    assert not registry.is_registered(HookName.CALCULATE_FEE, HDCN_TENANT_ID)

    assert registry.registered_hooks(HDCN_TENANT_ID) == [
        HookName.VALIDATE_MEMBER,
        HookName.DERIVE_MEMBER_NUMBER,
    ]


def test_hdcn_derive_member_number_formats_from_counter():
    assert hdcn_derive_member_number(HDCN_TENANT_ID, {"membership": {}}, 42) == "L-000042"
    assert hdcn_derive_member_number(HDCN_TENANT_ID, {"membership": {}}, 1) == "L-000001"


def test_hdcn_derive_member_number_keeps_existing_and_handles_missing_counter():
    kept = hdcn_derive_member_number(
        HDCN_TENANT_ID, {"membership": {"member_number": "L-000007"}}, 99
    )
    assert kept == "L-000007"  # idempotent — never renumbers a backfilled member
    assert hdcn_derive_member_number(HDCN_TENANT_ID, {"membership": {}}, None) is None


def test_hdcn_validate_member_requires_motorcycle_only_when_active():
    active_without_motor = {"membership": {"status": MS.ACTIVE.value}, "overlay": {}}
    errors = hdcn_validate_member(HDCN_TENANT_ID, active_without_motor)
    assert "overlay.motor" in errors

    active_with_motor = {
        "membership": {"status": MS.ACTIVE.value},
        "overlay": {"motor": "BMW R1250GS"},
    }
    assert hdcn_validate_member(HDCN_TENANT_ID, active_with_motor) == {}

    # motor_type is an accepted alternate key.
    active_with_motor_type = {
        "membership": {"status": MS.ACTIVE.value},
        "overlay": {"motor_type": "Honda"},
    }
    assert hdcn_validate_member(HDCN_TENANT_ID, active_with_motor_type) == {}

    # A non-active member is not required to have a motorcycle yet.
    pending = {"membership": {"status": MS.PENDING.value}, "overlay": {}}
    assert hdcn_validate_member(HDCN_TENANT_ID, pending) == {}


def test_hdcn_hooks_do_not_leak_to_other_tenants():
    # h-dcn's hooks are registered for "h-dcn" only; a different tenant gets the safe default
    # (Property 5 — no tenant literal in the generic core; resolution is by tenant_id).
    registry = TenantHookRegistry()
    register_hdcn_hooks(registry)

    assert not registry.is_registered(HookName.DERIVE_MEMBER_NUMBER, "other-club")
    assert (
        registry.resolve(HookName.DERIVE_MEMBER_NUMBER, "other-club")
        is default_derive_member_number
    )
    assert registry.resolve(HookName.VALIDATE_MEMBER, "other-club") is default_validate_member
    # The default derive for another tenant keeps the existing number / uses the counter,
    # with NO h-dcn "L-" formatting.
    assert (
        registry.resolve(HookName.DERIVE_MEMBER_NUMBER, "other-club")(
            "other-club", {"membership": {}}, 42
        )
        == "42"
    )
