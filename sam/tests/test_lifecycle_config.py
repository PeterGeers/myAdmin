"""
S5 Task 5.0 — tests for the lifecycle **config model + declarative rule evaluator** (design C2).

These pin the tenant-agnostic core of the membership lifecycle (Rung 1 config + Rung 2
rules): the frozen :class:`LifecycleConfig` model and its fail-fast validation (a bad graph
never constructs), the declarative guard / required-field **evaluator** (allow/deny + reason,
purely interpreting rule data — no eval, no tenant branch), the provider seam (unknown tenant
→ ``None``), and h-dcn's lifecycle wired as **data** (Property 5 — no ``if tenant == ...``).

Mirrors the domain test style of ``test_scope_dimensions.py`` / ``test_field_resolver.py``.

Validates: Requirements R1.4, R4.2
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.fixed_fields import MembershipStatus as MS
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    GuardRule,
    LifecycleConfig,
    LifecycleConfigError,
    LifecycleConfigProvider,
    RequiredFieldRule,
    RuleOperator,
    StaticLifecycleConfigProvider,
    TransitionRule,
    evaluate_guards,
    evaluate_required_fields,
)


# ── A small valid config reused across tests ──────────────────────────────────────────


def _simple_config(tenant_id: str = "club") -> LifecycleConfig:
    return LifecycleConfig(
        tenant_id=tenant_id,
        allowed_states=(MS.PENDING, MS.ACTIVE, MS.LEFT),
        initial_state=MS.PENDING,
        transitions=(
            TransitionRule(from_state=MS.PENDING, to_state=MS.ACTIVE),
            TransitionRule(from_state=MS.ACTIVE, to_state=MS.LEFT),
        ),
    )


# ── Model shape + graph queries ───────────────────────────────────────────────────────


def test_valid_config_constructs_and_answers_graph_queries():
    cfg = _simple_config()
    assert cfg.is_allowed_state(MS.ACTIVE) is True
    assert cfg.is_allowed_state(MS.SUSPENDED) is False
    assert cfg.transition(MS.PENDING, MS.ACTIVE) is not None
    assert cfg.transition(MS.PENDING, MS.LEFT) is None
    assert cfg.allowed_to_states(MS.PENDING) == (MS.ACTIVE,)
    assert cfg.allowed_to_states(MS.ACTIVE) == (MS.LEFT,)


def test_config_is_immutable():
    cfg = _simple_config()
    with pytest.raises((AttributeError, TypeError)):
        cfg.tenant_id = "mutated"  # type: ignore[misc]


def test_required_fields_for_status_filters_by_when_status():
    cfg = LifecycleConfig(
        tenant_id="club",
        allowed_states=(MS.PENDING, MS.ACTIVE),
        initial_state=MS.PENDING,
        transitions=(TransitionRule(from_state=MS.PENDING, to_state=MS.ACTIVE),),
        required_fields=(
            RequiredFieldRule(field="membership.member_number", when_status=MS.ACTIVE),
            RequiredFieldRule(field="personal.contact", when_status=MS.PENDING),
        ),
    )
    active_rules = cfg.required_fields_for(MS.ACTIVE)
    assert len(active_rules) == 1
    assert active_rules[0].field == "membership.member_number"


# ── Config validation (fail fast on a bad graph) ──────────────────────────────────────


def test_empty_tenant_id_rejected():
    with pytest.raises(LifecycleConfigError):
        LifecycleConfig(
            tenant_id="  ",
            allowed_states=(MS.ACTIVE,),
            initial_state=MS.ACTIVE,
        )


def test_no_allowed_states_rejected():
    with pytest.raises(LifecycleConfigError):
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(),
            initial_state=MS.ACTIVE,
        )


def test_duplicate_allowed_states_rejected():
    with pytest.raises(LifecycleConfigError):
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.ACTIVE, MS.ACTIVE),
            initial_state=MS.ACTIVE,
        )


def test_initial_state_not_allowed_rejected():
    with pytest.raises(LifecycleConfigError) as exc:
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.PENDING, MS.ACTIVE),
            initial_state=MS.LEFT,
        )
    assert "<initial_state>" in exc.value.reasons


def test_transition_from_undeclared_state_rejected():
    with pytest.raises(LifecycleConfigError) as exc:
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.PENDING, MS.ACTIVE),
            initial_state=MS.PENDING,
            transitions=(TransitionRule(from_state=MS.SUSPENDED, to_state=MS.ACTIVE),),
        )
    assert any("from_state" in r for r in exc.value.reasons.values())


def test_transition_to_undeclared_state_rejected():
    with pytest.raises(LifecycleConfigError) as exc:
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.PENDING, MS.ACTIVE),
            initial_state=MS.PENDING,
            transitions=(TransitionRule(from_state=MS.PENDING, to_state=MS.LEFT),),
        )
    assert any("to_state" in r for r in exc.value.reasons.values())


def test_self_loop_transition_rejected():
    with pytest.raises(LifecycleConfigError) as exc:
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.ACTIVE,),
            initial_state=MS.ACTIVE,
            transitions=(TransitionRule(from_state=MS.ACTIVE, to_state=MS.ACTIVE),),
        )
    assert any("self-loop" in r for r in exc.value.reasons.values())


def test_duplicate_transition_edge_rejected():
    with pytest.raises(LifecycleConfigError) as exc:
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.PENDING, MS.ACTIVE),
            initial_state=MS.PENDING,
            transitions=(
                TransitionRule(from_state=MS.PENDING, to_state=MS.ACTIVE),
                TransitionRule(from_state=MS.PENDING, to_state=MS.ACTIVE),
            ),
        )
    assert any("duplicate" in r for r in exc.value.reasons.values())


def test_in_operator_guard_without_sequence_value_rejected():
    with pytest.raises(LifecycleConfigError):
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.PENDING, MS.ACTIVE),
            initial_state=MS.PENDING,
            transitions=(
                TransitionRule(
                    from_state=MS.PENDING,
                    to_state=MS.ACTIVE,
                    guards=(GuardRule(field="x", op=RuleOperator.IN, value="not-a-seq"),),
                ),
            ),
        )


def test_equals_operator_guard_without_value_rejected():
    with pytest.raises(LifecycleConfigError):
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.PENDING, MS.ACTIVE),
            initial_state=MS.PENDING,
            transitions=(
                TransitionRule(
                    from_state=MS.PENDING,
                    to_state=MS.ACTIVE,
                    guards=(GuardRule(field="x", op=RuleOperator.EQUALS, value=None),),
                ),
            ),
        )


def test_required_field_rule_with_bad_status_rejected():
    with pytest.raises(LifecycleConfigError):
        LifecycleConfig(
            tenant_id="club",
            allowed_states=(MS.PENDING, MS.ACTIVE),
            initial_state=MS.PENDING,
            transitions=(TransitionRule(from_state=MS.PENDING, to_state=MS.ACTIVE),),
            required_fields=(
                RequiredFieldRule(field="personal.contact", when_status=MS.SUSPENDED),
            ),
        )


# ── The declarative guard evaluator (Rung 2 — interpret, never eval) ──────────────────


def test_no_guards_is_unconditionally_allowed():
    result = evaluate_guards((), member={}, context={})
    assert result.allowed is True
    assert result.reasons == ()


def test_present_guard_allows_when_field_present_denies_when_absent():
    guard = GuardRule(field="membership.member_number", op=RuleOperator.PRESENT, reason="need number")
    present = {"membership": {"member_number": "M-1"}}
    absent = {"membership": {}}
    assert evaluate_guards((guard,), present).allowed is True
    denied = evaluate_guards((guard,), absent)
    assert denied.denied is True
    assert "need number" in denied.reasons


def test_blank_string_counts_as_absent_for_present_guard():
    guard = GuardRule(field="personal.contact", op=RuleOperator.PRESENT)
    assert evaluate_guards((guard,), {"personal": {"contact": "   "}}).denied is True
    assert evaluate_guards((guard,), {"personal": {"contact": "a@b.nl"}}).allowed is True


def test_equals_guard_reads_from_context():
    guard = GuardRule(field="context.approved", op=RuleOperator.EQUALS, value=True, reason="not approved")
    assert evaluate_guards((guard,), member={}, context={"approved": True}).allowed is True
    denied = evaluate_guards((guard,), member={}, context={"approved": False})
    assert denied.denied is True
    assert "not approved" in denied.reasons


def test_in_and_not_in_guards():
    in_guard = GuardRule(field="membership.status", op=RuleOperator.IN, value=("active", "pending"))
    assert evaluate_guards((in_guard,), {"membership": {"status": "active"}}).allowed is True
    assert evaluate_guards((in_guard,), {"membership": {"status": "left"}}).denied is True

    not_in_guard = GuardRule(field="membership.status", op=RuleOperator.NOT_IN, value=("left",))
    assert evaluate_guards((not_in_guard,), {"membership": {"status": "active"}}).allowed is True
    assert evaluate_guards((not_in_guard,), {"membership": {"status": "left"}}).denied is True


def test_absent_guard_is_satisfied_on_missing_nested_path():
    guard = GuardRule(field="membership.left", op=RuleOperator.ABSENT)
    assert evaluate_guards((guard,), {"membership": {}}).allowed is True
    assert evaluate_guards((guard,), {"membership": {"left": "2024-01-01"}}).denied is True


def test_all_failing_guard_reasons_collected():
    guards = (
        GuardRule(field="a", op=RuleOperator.PRESENT, reason="need a"),
        GuardRule(field="b", op=RuleOperator.PRESENT, reason="need b"),
    )
    result = evaluate_guards(guards, member={})
    assert result.denied is True
    assert set(result.reasons) == {"need a", "need b"}


# ── The required-field-by-context evaluator ───────────────────────────────────────────


def test_required_field_rule_denies_when_field_missing_at_status():
    rules = (RequiredFieldRule(field="membership.member_number", when_status=MS.ACTIVE, reason="number required"),)
    denied = evaluate_required_fields(rules, {"membership": {}}, MS.ACTIVE)
    assert denied.denied is True
    assert "number required" in denied.reasons


def test_required_field_rule_allows_when_field_present_at_status():
    rules = (RequiredFieldRule(field="membership.member_number", when_status=MS.ACTIVE),)
    ok = evaluate_required_fields(rules, {"membership": {"member_number": "M-9"}}, MS.ACTIVE)
    assert ok.allowed is True


def test_required_field_rule_ignored_for_other_status():
    rules = (RequiredFieldRule(field="membership.member_number", when_status=MS.ACTIVE),)
    # Moving to PENDING — the ACTIVE-scoped rule must not apply.
    assert evaluate_required_fields(rules, {"membership": {}}, MS.PENDING).allowed is True


# ── The provider seam ─────────────────────────────────────────────────────────────────


def test_static_provider_returns_configured_tenant():
    provider = StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG})
    cfg = provider.get_lifecycle_config("h-dcn")
    assert cfg is not None
    assert cfg.tenant_id == "h-dcn"


def test_static_provider_unknown_tenant_is_none():
    provider = StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG})
    assert provider.get_lifecycle_config("someone-else") is None


def test_static_provider_empty_by_default():
    assert StaticLifecycleConfigProvider().get_lifecycle_config("anyone") is None


def test_static_provider_satisfies_protocol():
    assert isinstance(StaticLifecycleConfigProvider(), LifecycleConfigProvider)


def test_static_provider_rejects_non_config_value():
    with pytest.raises(LifecycleConfigError):
        StaticLifecycleConfigProvider({"bad": object()})  # type: ignore[dict-item]


# ── h-dcn wiring (DATA, not code — Property 5) ────────────────────────────────────────


def test_hdcn_lifecycle_is_valid_data():
    cfg = HDCN_LIFECYCLE_CONFIG
    assert cfg.tenant_id == "h-dcn"
    assert cfg.initial_state is MS.APPLICATION
    # The full fixed vocabulary is in use.
    assert set(cfg.allowed_states) == set(MS)


def test_hdcn_declares_the_expected_workflow_edges():
    cfg = HDCN_LIFECYCLE_CONFIG
    assert cfg.transition(MS.APPLICATION, MS.PENDING) is not None
    assert cfg.transition(MS.PENDING, MS.ACTIVE) is not None
    assert cfg.transition(MS.ACTIVE, MS.SUSPENDED) is not None
    assert cfg.transition(MS.SUSPENDED, MS.ACTIVE) is not None
    assert cfg.transition(MS.ACTIVE, MS.LEFT) is not None
    # A non-declared jump is absent (engine will deny it).
    assert cfg.transition(MS.APPLICATION, MS.ACTIVE) is None


def test_hdcn_application_to_pending_is_guarded_by_approval():
    rule = HDCN_LIFECYCLE_CONFIG.transition(MS.APPLICATION, MS.PENDING)
    assert rule is not None and rule.guards
    # Denied without the approval flag; allowed with it.
    assert evaluate_guards(rule.guards, member={}, context={}).denied is True
    assert evaluate_guards(rule.guards, member={}, context={"approved": True}).allowed is True


def test_hdcn_pending_to_active_requires_number_and_contact():
    rule = HDCN_LIFECYCLE_CONFIG.transition(MS.PENDING, MS.ACTIVE)
    assert rule is not None
    incomplete = {"membership": {}, "personal": {}}
    complete = {"membership": {"member_number": "M-1"}, "personal": {"email": "a@b.nl"}}
    assert evaluate_guards(rule.guards, incomplete).denied is True
    assert evaluate_guards(rule.guards, complete).allowed is True


# ── Property-based test ───────────────────────────────────────────────────────────────

_STATES = list(MS)


@st.composite
def _linear_config(draw) -> LifecycleConfig:
    """A well-formed config: a random non-empty distinct state subset chained linearly.

    Chaining consecutive distinct states guarantees a valid graph (no self-loops, no
    undeclared endpoints, no duplicate edges), so construction must always succeed.
    """
    n = draw(st.integers(min_value=1, max_value=len(_STATES)))
    states = draw(
        st.lists(st.sampled_from(_STATES), min_size=n, max_size=n, unique=True)
    )
    transitions = tuple(
        TransitionRule(from_state=states[i], to_state=states[i + 1])
        for i in range(len(states) - 1)
    )
    return LifecycleConfig(
        tenant_id="t",
        allowed_states=tuple(states),
        initial_state=states[0],
        transitions=transitions,
    )


@given(_linear_config())
def test_property_well_formed_config_always_constructs_and_edges_are_declared(cfg):
    # Every chained edge is queryable; the reverse edge is not declared (deny).
    for t in cfg.transitions:
        assert cfg.transition(t.from_state, t.to_state) is t
        assert cfg.transition(t.to_state, t.from_state) is None
    # Every transition endpoint is an allowed state.
    for t in cfg.transitions:
        assert cfg.is_allowed_state(t.from_state)
        assert cfg.is_allowed_state(t.to_state)
