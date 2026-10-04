"""Membership-service LIFECYCLE state machine (M1 split): the pure transition computation + hook dispatch. Mixed into ``MembershipService`` -- bodies verbatim."""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sam.members.domain.calculated_fields import CALCULATED_FIELDS
from sam.members.domain.error_codes import (
    ENUM_ROLE_RESTRICTED,
    MEMBERSHIP_TYPE_RETIRED,
    MEMBERSHIP_TYPE_UNKNOWN_REFERENCE,
    VALIDATION_MUST_BE_ONE_OF,
    VALIDATION_REQUIRED,
    VALIDATION_UNSUPPORTED_FIELD_TYPE,
    FieldError,
)
from sam.members.domain.field_resolver import (
    OVERLAY_GROUP,
    FieldOrigin,
    FieldResolver,
    FunctionalGroup,
    ResolvedField,
    StaticOverlayProvider,
    TenantOverlayProvider,
    _member_value,
    evaluate_show_when,
)
from sam.members.domain.field_resolver import (
    FieldConfig as ResolvedFieldConfig,
)
from sam.members.domain.fixed_fields import (
    MEMBER_NUMBER_FIELD_KEY,
    EnumOption,
    FieldGroup,
    FieldType,
    FieldValidationError,
    MemberNumberFormat,
    MembershipStatus,
    roles_for_option,
    validate_fixed_fields,
    validate_member_number_format,
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
from sam.members.domain.scope_canon import scope_canon
from sam.members.domain.scope_dimensions import (
    WILDCARD,
    ScopeConfigProvider,
)
from sam.members.domain.tenant_hooks import HookName, TenantHookRegistry
from sam.members.domain.transition_hooks import TransitionHookRegistry
from sam.members.domain.view_contexts import (
    StaticViewContextsProvider,
    ViewContext,
    ViewContextsProvider,
)
from sam.members.repository.members_repository import (
    Member,
    Membership,
    MembersRepository,
    Payment,
)

from sam.members.domain._membership_errors import (
    DEFAULT_SCOPE_DIMENSION_KEY,
    MEMBERSHIP_STATUS_FIELD_KEY,
    MEMBERSHIP_TYPE_FIELD_KEY,
    MemberNotFound,
    MemberValidationError,
    MembershipTypeConflict,
    MembershipTypeNotFound,
    ScopeDenied,
    TransitionDenied,
    TransitionResult,
    _as_field_error,
)


class LifecycleMixin:
    # ── Lifecycle state machine (design C2, R1.4 — task 5.0) ──────────────────────────

    @staticmethod
    def _current_state(member: Member) -> MembershipStatus | None:
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

    def get_lifecycle_config(self, tenant_id: str) -> LifecycleConfig | None:
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
        context: Mapping[str, Any] | None = None,
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
                    (
                        f"no transition from {from_state.value!r} to {to_state.value!r} is "
                        "declared for this tenant"
                    )
                ],
            )

        # (3) Evaluate the declarative guards + the target state's required-field rules.
        reasons: list[str] = []
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

