"""
S5 Task 5.0 — tests for the **lifecycle state-machine engine + ``on_transition`` hook seam**.

These pin ``MembershipService.transition_membership`` (design C2) — the tenant-agnostic
state machine — and the ``on_transition`` hook seam (design C5):

- an **allowed** transition succeeds, updates ``membership.status``, and fires the tenant's
  ``on_transition`` hook;
- a transition **not in the graph** is denied (never a silent allow);
- a transition whose declarative **guard fails** is denied, with reasons, and the hook does
  NOT fire and the record is NOT mutated;
- a tenant with **no lifecycle config** denies every transition;
- an **unregistered** hook resolves to the safe no-op default (the engine still succeeds);
- the returned :class:`TransitionResult` is a pure computation — the service never persists
  (that is task 5.2).

Backed by the same in-memory fake-repo pattern as ``test_membership_service_reads.py``.

Validates: Requirements R1.4, R4.2
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
    GuardRule,
    LifecycleConfig,
    RuleOperator,
    StaticLifecycleConfigProvider,
    TransitionRule,
)
from sam.members.domain.membership_service import (
    MembershipService,
    TransitionDenied,
    TransitionResult,
)
from sam.members.domain.transition_hooks import (
    NOOP_TRANSITION_HOOK,
    TransitionHookRegistry,
)


# ── A minimal repository (the engine does not touch it for a transition COMPUTATION) ──


class FakeMembersRepository:
    """Enough of :class:`MembersRepository` to construct the service; transitions don't read it."""

    def get_member(self, tenant_id, member_id):
        return None

    def list_members(self, tenant_id, *, filters=None, scope_filter=None):
        return []

    def list_membership_types(self, tenant_id, *, active_only=False):
        return []


def _service(*, lifecycle=None, hooks=None) -> MembershipService:
    return MembershipService(
        FakeMembersRepository(),
        lifecycle_provider=lifecycle,
        transition_hooks=hooks,
    )


def _simple_lifecycle(tenant_id: str = "club") -> LifecycleConfig:
    return LifecycleConfig(
        tenant_id=tenant_id,
        allowed_states=(MS.PENDING, MS.ACTIVE, MS.LEFT),
        initial_state=MS.PENDING,
        transitions=(
            TransitionRule(
                from_state=MS.PENDING,
                to_state=MS.ACTIVE,
                guards=(
                    GuardRule(
                        field="membership.member_number",
                        op=RuleOperator.PRESENT,
                        reason="member number required to activate",
                    ),
                ),
            ),
            TransitionRule(from_state=MS.ACTIVE, to_state=MS.LEFT),
        ),
    )


def _member(status, **extra):
    membership = {"status": status.value if hasattr(status, "value") else status}
    membership.update(extra.pop("membership", {}))
    return {"member_id": "m-1", "membership": membership, "personal": {}, **extra}


# ── Allowed transition ────────────────────────────────────────────────────────────────


def test_allowed_transition_updates_status_and_fires_hook():
    calls = []

    def hook(tenant_id, member, from_state, to_state):
        calls.append((tenant_id, member["membership"]["status"], from_state, to_state))

    registry = TransitionHookRegistry()
    registry.register("club", hook)
    svc = _service(
        lifecycle=StaticLifecycleConfigProvider({"club": _simple_lifecycle()}),
        hooks=registry,
    )

    member = _member(MS.PENDING, membership={"member_number": "M-1"})
    result = svc.transition_membership("club", member, MS.ACTIVE)

    assert isinstance(result, TransitionResult)
    assert result.from_state is MS.PENDING
    assert result.to_state is MS.ACTIVE
    assert result.member["membership"]["status"] == MS.ACTIVE.value
    # Hook fired once with the post-transition record.
    assert calls == [("club", MS.ACTIVE.value, MS.PENDING, MS.ACTIVE)]


def test_transition_does_not_mutate_the_caller_record():
    svc = _service(lifecycle=StaticLifecycleConfigProvider({"club": _simple_lifecycle()}))
    member = _member(MS.PENDING, membership={"member_number": "M-1"})
    svc.transition_membership("club", member, MS.ACTIVE)
    # The original record is untouched (pure computation returns a copy).
    assert member["membership"]["status"] == MS.PENDING.value


def test_unguarded_transition_succeeds():
    svc = _service(lifecycle=StaticLifecycleConfigProvider({"club": _simple_lifecycle()}))
    member = _member(MS.ACTIVE, membership={"member_number": "M-1"})
    result = svc.transition_membership("club", member, MS.LEFT)
    assert result.to_state is MS.LEFT


# ── Denials (never a silent allow) ────────────────────────────────────────────────────


def test_transition_not_in_graph_is_denied():
    svc = _service(lifecycle=StaticLifecycleConfigProvider({"club": _simple_lifecycle()}))
    member = _member(MS.PENDING, membership={"member_number": "M-1"})
    with pytest.raises(TransitionDenied) as exc:
        svc.transition_membership("club", member, MS.LEFT)  # PENDING->LEFT is undeclared
    assert exc.value.from_state is MS.PENDING
    assert exc.value.to_state is MS.LEFT


def test_guard_failure_is_denied_with_reason_and_no_hook_fires():
    fired = []
    registry = TransitionHookRegistry()
    registry.register("club", lambda *a: fired.append(a))
    svc = _service(
        lifecycle=StaticLifecycleConfigProvider({"club": _simple_lifecycle()}),
        hooks=registry,
    )
    member = _member(MS.PENDING)  # no member_number → guard fails
    with pytest.raises(TransitionDenied) as exc:
        svc.transition_membership("club", member, MS.ACTIVE)
    assert "member number required to activate" in exc.value.reasons
    assert fired == []  # the hook must not fire on a denied transition


def test_transition_to_unknown_state_for_tenant_is_denied():
    svc = _service(lifecycle=StaticLifecycleConfigProvider({"club": _simple_lifecycle()}))
    member = _member(MS.PENDING, membership={"member_number": "M-1"})
    with pytest.raises(TransitionDenied):
        svc.transition_membership("club", member, MS.SUSPENDED)  # not an allowed state


def test_tenant_without_lifecycle_config_denies_transition():
    svc = _service(lifecycle=StaticLifecycleConfigProvider())  # empty
    member = _member(MS.PENDING, membership={"member_number": "M-1"})
    with pytest.raises(TransitionDenied) as exc:
        svc.transition_membership("club", member, MS.ACTIVE)
    assert any("no configured membership lifecycle" in r for r in exc.value.reasons)


def test_member_with_no_current_state_is_denied():
    svc = _service(lifecycle=StaticLifecycleConfigProvider({"club": _simple_lifecycle()}))
    member = {"member_id": "m-1", "membership": {}, "personal": {}}  # no status
    with pytest.raises(TransitionDenied):
        svc.transition_membership("club", member, MS.ACTIVE)


# ── The on_transition hook seam + safe default ────────────────────────────────────────


def test_unregistered_hook_resolves_to_safe_noop_default():
    registry = TransitionHookRegistry()
    assert registry.is_registered("club") is False
    assert registry.resolve("club") is NOOP_TRANSITION_HOOK


def test_engine_succeeds_with_the_noop_default_when_no_hook_registered():
    # No hook registry passed → default empty registry → no-op default; transition still works.
    svc = _service(lifecycle=StaticLifecycleConfigProvider({"club": _simple_lifecycle()}))
    member = _member(MS.PENDING, membership={"member_number": "M-1"})
    result = svc.transition_membership("club", member, MS.ACTIVE)
    assert result.to_state is MS.ACTIVE


def test_registry_register_replaces_previous_hook():
    registry = TransitionHookRegistry()
    registry.register("club", lambda *a: None)
    sentinel = lambda *a: None
    registry.register("club", sentinel)
    assert registry.resolve("club") is sentinel


def test_registry_rejects_blank_tenant_and_non_callable():
    registry = TransitionHookRegistry()
    with pytest.raises(ValueError):
        registry.register("  ", lambda *a: None)
    with pytest.raises(TypeError):
        registry.register("club", object())  # type: ignore[arg-type]


def test_noop_default_returns_none():
    assert NOOP_TRANSITION_HOOK("club", {}, MS.PENDING, MS.ACTIVE) is None


# ── h-dcn wired as data — the engine drives it with no tenant conditional ─────────────


def test_engine_runs_hdcn_application_to_pending_only_when_approved():
    svc = _service(lifecycle=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}))
    member = _member(MS.APPLICATION)

    with pytest.raises(TransitionDenied):
        svc.transition_membership("h-dcn", member, MS.PENDING)  # no approval flag

    result = svc.transition_membership("h-dcn", member, MS.PENDING, context={"approved": True})
    assert result.to_state is MS.PENDING


def test_engine_runs_hdcn_pending_to_active_with_required_fields():
    svc = _service(lifecycle=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}))
    incomplete = _member(MS.PENDING)
    with pytest.raises(TransitionDenied):
        svc.transition_membership("h-dcn", incomplete, MS.ACTIVE)

    complete = _member(
        MS.PENDING,
        membership={"member_number": "M-1"},
        personal={"email": "rider@h-dcn.nl"},
    )
    result = svc.transition_membership("h-dcn", complete, MS.ACTIVE)
    assert result.to_state is MS.ACTIVE
    assert result.member["membership"]["status"] == MS.ACTIVE.value
