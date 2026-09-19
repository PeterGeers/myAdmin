"""
S5 Task 5.0 — the **membership lifecycle config model + declarative rule evaluator** (design C2).

This is Rung 1 (config/data) + Rung 2 (declarative rules) of the generic/tenant-specific
ladder (`generic-membership-design.md` §3). It owns the *tenant-agnostic core* of the
membership lifecycle state machine:

- the **lifecycle config model** — allowed states, the transition graph (from-state →
  allowed to-states), per-transition declarative **guards**, and declarative
  **required-field-by-context** rules ("field X required when status = Y"), and
- the **declarative rule evaluator** — a small, generic interpreter that evaluates a guard
  rule (field comparison / presence) against a member record + transition context and
  returns allow / deny(+reason).

It deliberately mirrors the sibling config seams so the whole module family reads the same
way (Property 5 — the generic core has NO tenant conditionals; every difference is
config/rule/hook):

- ``scope_dimensions.py`` — ``ScopeConfig`` (a frozen config dataclass whose
  ``__post_init__`` fails fast via ``_reject_invalid_config``) + ``ScopeConfigProvider`` /
  ``StaticScopeConfigProvider`` + ``HDCN_SCOPE_CONFIG`` as *data*, and
- ``field_resolver.py`` — the ``TenantOverlayProvider`` / ``StaticOverlayProvider`` seam.

Here the analogues are :class:`LifecycleConfig` (frozen, self-validating),
:class:`LifecycleConfigProvider` (Protocol) / :class:`StaticLifecycleConfigProvider`, and
:data:`HDCN_LIFECYCLE_CONFIG` (h-dcn's states + transitions + guards wired as **data**, not
an ``if tenant == "h-dcn"``).

What this module is NOT:
- It is not the state-machine *engine* — that is ``MembershipService.transition_membership``
  (task 5.0, in ``membership_service.py``), which looks a tenant's :class:`LifecycleConfig`
  up, asks this module whether a transition is allowed + its guards pass, and then dispatches
  the ``on_transition`` hook. This module is the pure *config + rule evaluation* half.
- It is not the ``on_transition`` **hook** — that seam lives in ``transition_hooks.py``
  (task 5.0 defines the seam + safe default; task 5.1 registers h-dcn's implementations).
- It does not persist anything (the repository / task 5.2) and touches no boto3/HTTP.

The **status vocabulary is fixed** (:class:`~sam.members.domain.fixed_fields.MembershipStatus`
— application/pending/active/suspended/lapsed/left); the **transition graph between those
states is tenant config** (a tenant declares which state → which state is allowed, with
optional declarative guards). This module fixes neither the graph nor the rules — it fixes
only how they are *shaped, validated, and interpreted*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

from .fixed_fields import MembershipStatus

__all__ = [
    "RuleOperator",
    "GuardRule",
    "RequiredFieldRule",
    "TransitionRule",
    "LifecycleConfig",
    "LifecycleConfigError",
    "GuardEvaluation",
    "evaluate_guards",
    "evaluate_required_fields",
    "LifecycleConfigProvider",
    "StaticLifecycleConfigProvider",
    "HDCN_LIFECYCLE_CONFIG",
]


# ── The declarative rule schema (Rung 2 — DATA the engine interprets) ─────────────────


class RuleOperator(str, Enum):
    """The closed, generic set of comparisons a declarative rule may express.

    Kept deliberately small and value-oriented: a rule is *data* (a field path + an
    operator + an optional expected value), interpreted by :func:`evaluate_guards` — there
    is **no** ``eval`` of arbitrary code and **no** tenant branch. Anything genuinely
    bespoke (a computed condition that cannot be expressed here) is deferred to a Rung-3
    ``on_transition`` hook, never smuggled into the operator set.
    """

    PRESENT = "present"          # the field exists and is non-null / non-blank
    ABSENT = "absent"            # the field is missing or null / blank
    EQUALS = "equals"            # field == value
    NOT_EQUALS = "not_equals"    # field != value
    IN = "in"                    # field ∈ value (value is a sequence)
    NOT_IN = "not_in"            # field ∉ value (value is a sequence)


#: The prefixes a rule's ``field`` path may address, so a rule can read either the member
#: record itself or the transition *context* (the runtime facts the engine threads in — e.g.
#: ``context.actor_role``, ``context.approved``). A path with no recognised prefix is read
#: from the member record (the common case, e.g. ``membership.member_number``).
_CONTEXT_PREFIX = "context."


@dataclass(frozen=True)
class GuardRule:
    """One declarative guard: a field path + operator (+ optional expected value).

    A guard is evaluated against ``(member, context)``; ALL guards on a transition must hold
    for the transition to be allowed (logical AND — express alternatives as separate
    transitions if needed). ``field`` is a dotted path into the member record (e.g.
    ``membership.member_number``, ``personal.contact``) or, when prefixed ``context.``, into
    the transition context supplied at call time (e.g. ``context.approved``). ``reason`` is
    the human-readable denial message surfaced when the guard fails.
    """

    field: str
    op: RuleOperator
    value: Any = None
    reason: Optional[str] = None

    def denial_reason(self) -> str:
        """The message to surface when this guard denies a transition."""
        if self.reason:
            return self.reason
        return f"guard failed: {self.field} {self.op.value} {self.value!r}"


@dataclass(frozen=True)
class RequiredFieldRule:
    """A declarative "field X required when status = Y" rule (design §3 Rung 2 / C2).

    Interpreted by :func:`evaluate_required_fields`: whenever a member is (or is moving) to
    :attr:`when_status`, :attr:`field` must be present (non-null / non-blank) on the record.
    This is the same generic presence check as :attr:`RuleOperator.PRESENT`, expressed as a
    status-scoped rule so a tenant can declare context-dependent required-ness as data.
    """

    field: str
    when_status: MembershipStatus
    reason: Optional[str] = None

    def denial_reason(self) -> str:
        if self.reason:
            return self.reason
        return f"{self.field} is required when status is {self.when_status.value}"


@dataclass(frozen=True)
class TransitionRule:
    """One allowed transition in the graph: ``from_state → to_state`` with optional guards.

    The presence of a :class:`TransitionRule` for ``(from_state, to_state)`` is what makes a
    transition *possible*; the :attr:`guards` (all of which must hold) are what make it
    *permitted* for a given member. A transition with no guards is unconditionally allowed
    once it is in the graph.
    """

    from_state: MembershipStatus
    to_state: MembershipStatus
    guards: tuple[GuardRule, ...] = ()


class LifecycleConfigError(Exception):
    """Raised when a tenant's lifecycle config is malformed (a config bug, not user input).

    Carries ``reasons`` (a key → why map) so a misconfiguration surfaces every problem at
    once — mirroring ``ScopeConfigError`` / ``OverlayError`` / ``FieldValidationError``.
    """

    def __init__(self, reasons: Mapping[str, str]):
        self.reasons = dict(reasons)
        detail = "; ".join(f"{k}: {v}" for k, v in self.reasons.items())
        super().__init__(f"invalid lifecycle config: {detail}")


@dataclass(frozen=True)
class LifecycleConfig:
    """A tenant's membership-lifecycle configuration (design C2, Rung 1 + Rung 2).

    Frozen because it is configuration data, resolved once per tenant and shared. It carries:

    - :attr:`allowed_states` — the subset (and ordering) of the fixed
      :class:`MembershipStatus` vocabulary this tenant uses. A member may only sit in one of
      these; every transition endpoint must be one of these.
    - :attr:`initial_state` — the state a brand-new member starts in (must be an allowed
      state). Informational for the engine / write route (task 5.2).
    - :attr:`transitions` — the transition graph: the allowed ``from → to`` edges, each with
      optional declarative :class:`GuardRule` guards.
    - :attr:`required_fields` — declarative "field X required when status = Y" rules
      (context-dependent required-ness), evaluated when a member enters that status.

    Construction validates the whole config eagerly (:meth:`__post_init__` →
    :func:`_reject_invalid_config`) so a bad graph fails FAST at wiring time (an unknown
    state, a transition to an undeclared state, a self-loop, a duplicate edge), never
    silently at request time — mirroring ``ScopeConfig.__post_init__``.
    """

    tenant_id: str
    allowed_states: tuple[MembershipStatus, ...]
    initial_state: MembershipStatus
    transitions: tuple[TransitionRule, ...] = ()
    required_fields: tuple[RequiredFieldRule, ...] = ()

    def __post_init__(self) -> None:
        _reject_invalid_config(
            self.tenant_id,
            self.allowed_states,
            self.initial_state,
            self.transitions,
            self.required_fields,
        )

    # ── graph queries ──────────────────────────────────────────────────────────────────

    def is_allowed_state(self, state: MembershipStatus) -> bool:
        """Whether ``state`` is one of the states this tenant uses."""
        return state in self.allowed_states

    def transition(
        self, from_state: MembershipStatus, to_state: MembershipStatus
    ) -> Optional[TransitionRule]:
        """Return the :class:`TransitionRule` for the edge, or ``None`` if not in the graph.

        A ``None`` result means the transition is **not declared** — the engine denies it
        (never a silent allow). A non-``None`` result carries the guards the engine must
        still evaluate before permitting the move.
        """
        for t in self.transitions:
            if t.from_state is from_state and t.to_state is to_state:
                return t
        return None

    def allowed_to_states(
        self, from_state: MembershipStatus
    ) -> tuple[MembershipStatus, ...]:
        """The states reachable from ``from_state`` by a declared transition (order kept)."""
        return tuple(
            t.to_state for t in self.transitions if t.from_state is from_state
        )

    def required_fields_for(
        self, status: MembershipStatus
    ) -> tuple[RequiredFieldRule, ...]:
        """The declarative required-field rules that apply when a member is at ``status``."""
        return tuple(r for r in self.required_fields if r.when_status is status)


# ── Config validation (fail fast on a misconfiguration) ──────────────────────────────


def _reject_invalid_config(
    tenant_id: str,
    allowed_states: Sequence[MembershipStatus],
    initial_state: MembershipStatus,
    transitions: Sequence[TransitionRule],
    required_fields: Sequence[RequiredFieldRule],
) -> None:
    """Raise :class:`LifecycleConfigError` if the lifecycle config is malformed.

    Enforced invariants (a config bug, never user input):

    - ``tenant_id`` is a non-empty string;
    - at least one allowed state, and the allowed states are :class:`MembershipStatus`
      members with no duplicates;
    - ``initial_state`` is one of the allowed states;
    - every transition's ``from_state`` / ``to_state`` is an allowed state (no transition to
      or from an undeclared state), is not a self-loop, and no ``(from, to)`` edge is declared
      twice;
    - every guard addresses a non-empty field path, and a set-membership operator
      (``IN`` / ``NOT_IN``) carries a sequence value while an ``EQUALS`` / ``NOT_EQUALS``
      operator carries a scalar;
    - every required-field rule's ``when_status`` is an allowed state and its ``field`` is a
      non-empty path.
    """
    reasons: dict[str, str] = {}

    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise LifecycleConfigError({"<tenant_id>": "must be a non-empty string"})

    states = tuple(allowed_states)
    if not states:
        reasons["<allowed_states>"] = "at least one allowed state is required"
    if any(not isinstance(s, MembershipStatus) for s in states):
        reasons["<allowed_states>"] = "every allowed state must be a MembershipStatus"
    if len(set(states)) != len(states):
        reasons["<allowed_states>"] = "allowed states must be unique"

    allowed_set = set(states)

    if initial_state not in allowed_set:
        reasons["<initial_state>"] = (
            f"initial_state {getattr(initial_state, 'value', initial_state)!r} "
            "must be one of the allowed states"
        )

    seen_edges: set[tuple[MembershipStatus, MembershipStatus]] = set()
    for t in transitions:
        edge_label = (
            f"{getattr(t.from_state, 'value', t.from_state)}"
            f"->{getattr(t.to_state, 'value', t.to_state)}"
        )
        if t.from_state not in allowed_set:
            reasons[edge_label] = "from_state is not an allowed state"
            continue
        if t.to_state not in allowed_set:
            reasons[edge_label] = "to_state is not an allowed state"
            continue
        if t.from_state is t.to_state:
            reasons[edge_label] = "a transition must not be a self-loop"
            continue
        edge = (t.from_state, t.to_state)
        if edge in seen_edges:
            reasons[edge_label] = "duplicate transition edge"
            continue
        seen_edges.add(edge)

        for guard in t.guards:
            guard_reason = _validate_guard(guard)
            if guard_reason is not None:
                reasons[f"{edge_label}:{guard.field}"] = guard_reason

    for rule in required_fields:
        label = f"required:{rule.field}"
        if not isinstance(rule.field, str) or not rule.field.strip():
            reasons[label] = "required-field rule needs a non-empty field path"
            continue
        if rule.when_status not in allowed_set:
            reasons[label] = "when_status is not an allowed state"

    if reasons:
        raise LifecycleConfigError(reasons)


def _validate_guard(guard: GuardRule) -> Optional[str]:
    """Return a reason if the guard is structurally malformed, else ``None``."""
    if not isinstance(guard.field, str) or not guard.field.strip():
        return "guard needs a non-empty field path"
    if guard.op in (RuleOperator.IN, RuleOperator.NOT_IN):
        if not isinstance(guard.value, (list, tuple, set)):
            return f"operator {guard.op.value} requires a sequence value"
    if guard.op in (RuleOperator.EQUALS, RuleOperator.NOT_EQUALS):
        if guard.value is None:
            return f"operator {guard.op.value} requires a value to compare against"
    return None


# ── The declarative rule evaluator (Rung 2 — interpret, never eval) ───────────────────


@dataclass(frozen=True)
class GuardEvaluation:
    """The result of evaluating a transition's guards: allow / deny (+ collected reasons).

    ``reasons`` lists the denial message of every guard that failed, so a caller can surface
    all of them at once (a denied transition is never a silent allow — design "never a silent
    allow"). An allowed evaluation carries an empty ``reasons`` tuple.
    """

    allowed: bool
    reasons: tuple[str, ...] = ()

    @property
    def denied(self) -> bool:
        return not self.allowed


def _resolve_path(field_path: str, member: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    """Read a dotted ``field_path`` from either the transition context or the member record.

    A path prefixed ``context.`` is read from ``context`` (the runtime transition facts); any
    other path is read from ``member``. Traversal is null-tolerant — a missing segment yields
    ``None`` (which ``PRESENT`` treats as absent and ``ABSENT`` treats as satisfied), so a
    guard never raises on a partial record.
    """
    if field_path.startswith(_CONTEXT_PREFIX):
        source: Any = context
        remainder = field_path[len(_CONTEXT_PREFIX):]
    else:
        source = member
        remainder = field_path

    current: Any = source
    for segment in remainder.split("."):
        if isinstance(current, Mapping):
            current = current.get(segment)
        else:
            return None
        if current is None:
            return None
    return current


def _is_present(value: Any) -> bool:
    """Whether ``value`` counts as present (non-null and, for strings, non-blank)."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _guard_holds(guard: GuardRule, member: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    """Evaluate a single guard against ``(member, context)`` — pure data interpretation."""
    actual = _resolve_path(guard.field, member, context)
    op = guard.op
    if op is RuleOperator.PRESENT:
        return _is_present(actual)
    if op is RuleOperator.ABSENT:
        return not _is_present(actual)
    if op is RuleOperator.EQUALS:
        return actual == guard.value
    if op is RuleOperator.NOT_EQUALS:
        return actual != guard.value
    if op is RuleOperator.IN:
        return actual in tuple(guard.value or ())
    if op is RuleOperator.NOT_IN:
        return actual not in tuple(guard.value or ())
    # Defensive: an unknown operator is a programming error, not user input → deny.
    return False


def evaluate_guards(
    guards: Sequence[GuardRule],
    member: Mapping[str, Any],
    context: Optional[Mapping[str, Any]] = None,
) -> GuardEvaluation:
    """Evaluate ALL guards on a transition (logical AND) against ``(member, context)``.

    Returns a :class:`GuardEvaluation`: ``allowed=True`` with no reasons when every guard
    holds; ``allowed=False`` carrying the denial reason of each failing guard otherwise. No
    guards → unconditionally allowed. Purely interprets the declarative rule *data* — no
    ``eval``, no tenant branch (Property 5).
    """
    ctx: Mapping[str, Any] = context or {}
    failed: list[str] = []
    for guard in guards:
        if not _guard_holds(guard, member, ctx):
            failed.append(guard.denial_reason())
    if failed:
        return GuardEvaluation(allowed=False, reasons=tuple(failed))
    return GuardEvaluation(allowed=True)


def evaluate_required_fields(
    rules: Sequence[RequiredFieldRule],
    member: Mapping[str, Any],
    status: MembershipStatus,
    context: Optional[Mapping[str, Any]] = None,
) -> GuardEvaluation:
    """Evaluate the "field required when status = Y" rules that apply at ``status``.

    Every rule whose :attr:`RequiredFieldRule.when_status` equals ``status`` must find its
    ``field`` present on the member record; a missing/blank field is a denial carrying the
    rule's reason. Returns a :class:`GuardEvaluation` (allow / deny + collected reasons),
    mirroring :func:`evaluate_guards` so a caller handles both uniformly.
    """
    ctx: Mapping[str, Any] = context or {}
    failed: list[str] = []
    for rule in rules:
        if rule.when_status is not status:
            continue
        value = _resolve_path(rule.field, member, ctx)
        if not _is_present(value):
            failed.append(rule.denial_reason())
    if failed:
        return GuardEvaluation(allowed=False, reasons=tuple(failed))
    return GuardEvaluation(allowed=True)


# ── The config provider seam (mirrors scope_dimensions' ScopeConfigProvider) ──────────


@runtime_checkable
class LifecycleConfigProvider(Protocol):
    """Supplies a tenant's :class:`LifecycleConfig`, resolved by ``tenant_id``.

    The engine depends on this shape, not on where the config lives — exactly as
    ``FieldResolver`` depends on a ``TenantOverlayProvider`` and the scope resolver on a
    ``ScopeConfigProvider``. The SAM-plane concrete provider is DynamoDB-backed tenant config,
    injected in a later step; the domain layer never imports it.

    Unlike scope/overlay (which have a safe *empty* default), a tenant with NO lifecycle
    config has no state machine to run — a transition request for such a tenant is a
    misconfiguration. Implementations therefore MAY return ``None`` for an unknown tenant and
    the engine treats "no config" as "no transitions allowed" (deny, never a silent allow).
    """

    def get_lifecycle_config(self, tenant_id: str) -> Optional[LifecycleConfig]:
        ...


class StaticLifecycleConfigProvider:
    """An in-memory :class:`LifecycleConfigProvider` backed by a ``{tenant_id: config}`` map.

    The storage-agnostic default: used by tests and any caller that already holds the config
    (e.g. seeded h-dcn config, :data:`HDCN_LIFECYCLE_CONFIG`), and the reference against which
    the DynamoDB-backed provider is later swapped in. Each config is validated eagerly at
    construction (a bad graph fails FAST at wiring time). An unknown tenant yields ``None`` —
    the engine denies transitions for a tenant with no configured lifecycle.
    """

    def __init__(self, configs: Optional[Mapping[str, LifecycleConfig]] = None):
        materialised = dict(configs or {})
        for tenant_id, cfg in materialised.items():
            if not isinstance(cfg, LifecycleConfig):
                raise LifecycleConfigError(
                    {tenant_id: "value must be a LifecycleConfig"}
                )
            # A LifecycleConfig validates itself in __post_init__; touch it to be explicit.
            _ = cfg.allowed_states
        self._configs: dict[str, LifecycleConfig] = materialised

    def get_lifecycle_config(self, tenant_id: str) -> Optional[LifecycleConfig]:
        return self._configs.get(tenant_id)


# ── h-dcn wiring (the first tenant — DATA, not code; Rung 1 + Rung 2) ─────────────────

#: h-dcn's membership lifecycle wired as **data** (design C2, `generic-membership-design.md`).
#: The generic core has no ``if tenant == "h-dcn"``; h-dcn is simply the first ``tenant_id``
#: whose lifecycle config the provider carries. The graph mirrors h-dcn's real workflow:
#:
#:   application → pending → active ⇄ suspended, active → lapsed, and any live state → left.
#:
#: Guards and required-fields are expressed **declaratively** where possible (Rung 2):
#:   - activating a member requires a member number and a contact on the record;
#:   - approving an application into ``pending`` requires an approval flag threaded in via the
#:     transition context (``context.approved``) — h-dcn's ``verzoek_lid`` approval flow.
#: Anything genuinely bespoke (e.g. a Motor-specific validation, or a computed member-number
#: derivation) is deferred to a Rung-3 ``on_transition`` hook (task 5.1), not encoded here.
_S = MembershipStatus

HDCN_LIFECYCLE_CONFIG: LifecycleConfig = LifecycleConfig(
    tenant_id="h-dcn",
    allowed_states=(
        _S.APPLICATION,
        _S.PENDING,
        _S.ACTIVE,
        _S.SUSPENDED,
        _S.LAPSED,
        _S.LEFT,
    ),
    initial_state=_S.APPLICATION,
    transitions=(
        # Self-signup request approved → pending (h-dcn verzoek_lid): needs an approval flag.
        TransitionRule(
            from_state=_S.APPLICATION,
            to_state=_S.PENDING,
            guards=(
                GuardRule(
                    field="context.approved",
                    op=RuleOperator.EQUALS,
                    value=True,
                    reason="application must be approved before it can move to pending",
                ),
            ),
        ),
        # Pending → active: a real member needs a member number and a contact on file.
        TransitionRule(
            from_state=_S.PENDING,
            to_state=_S.ACTIVE,
            guards=(
                GuardRule(
                    field="membership.member_number",
                    op=RuleOperator.PRESENT,
                    reason="a member number is required to activate a membership",
                ),
                GuardRule(
                    field="personal.contact",
                    op=RuleOperator.PRESENT,
                    reason="a contact is required to activate a membership",
                ),
            ),
        ),
        # Active ⇄ suspended (temporary), active → lapsed (missed renewal).
        TransitionRule(from_state=_S.ACTIVE, to_state=_S.SUSPENDED),
        TransitionRule(from_state=_S.SUSPENDED, to_state=_S.ACTIVE),
        TransitionRule(from_state=_S.ACTIVE, to_state=_S.LAPSED),
        TransitionRule(from_state=_S.LAPSED, to_state=_S.ACTIVE),
        # Leaving the club — terminal — from any live state.
        TransitionRule(from_state=_S.ACTIVE, to_state=_S.LEFT),
        TransitionRule(from_state=_S.SUSPENDED, to_state=_S.LEFT),
        TransitionRule(from_state=_S.LAPSED, to_state=_S.LEFT),
        TransitionRule(from_state=_S.PENDING, to_state=_S.LEFT),
    ),
    required_fields=(
        # An active h-dcn member must carry a member number and a contact (context-dependent
        # required-ness expressed as data — the same invariant the pending→active guard checks,
        # asserted for the resting state too).
        RequiredFieldRule(field="membership.member_number", when_status=_S.ACTIVE),
        RequiredFieldRule(field="personal.contact", when_status=_S.ACTIVE),
    ),
)
