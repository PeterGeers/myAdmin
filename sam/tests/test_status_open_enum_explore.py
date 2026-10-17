"""
retire-members-status-lifecycle-engine — Task 1: the **bug-condition exploration test**.

This test is written BEFORE the retirement and is EXPECTED TO FAIL on the current (unfixed)
code — its failure is what confirms the bug: ``membership.status`` is a CLOSED code vocabulary
(``MembershipStatus``) wired onto the ``status`` ``FixedField`` as ``choices``, AND status
CHANGES are gatekept by the transition state engine (``HDCN_LIFECYCLE_CONFIG`` + the graph/guard
evaluator). The same test will PASS once the fix retires the engine and turns ``status`` into a
plain, tenant-driven OPEN enum (``choices=None``), authored exactly like ``gender``.

Property 1 (Bug Condition — design §Correctness Properties): for a tenant that authors/sets a
``status`` value the closed set rejects, OR a status change the graph/guards block, the FIXED
system SHALL carry the tenant value through resolve → projection, accept it on a member
create/update (open-enum validation), and allow any value → any value status change as an
ordinary field edit (no graph, no guard, no transition modal).

**Scoped PBT approach** (per the task): the property is pinned to the concrete failing case
``status="died"`` / label "Overleden", plus ONE arbitrary extra tenant-authored status value
drawn by Hypothesis (so the property is "any tenant-authored status value", exercised over the
input space rather than a single hard-coded example).

The three facets assert the real SAM-domain surfaces the retirement changes:

1. **Resolve → projection → validate (Expected Behavior 2.1 / 2.2 / 2.3).** A tenant
   ``fixed_overrides["membership.status"]`` authoring ``died`` (+ the extra value) resolves into
   the ``config#fields`` ``status.choices`` (this already survives the SAM resolver — like a
   ``gender`` value). The bug bites at the AUTHORITATIVE validation gate ``create``/``update``
   use: :func:`validate_fixed_fields` re-checks ``status`` against the CLOSED registry
   ``MembershipStatus`` set, NOT the resolved tenant choices — so a member carrying
   ``status="died"`` is rejected with "must be one of: application, pending, active, suspended,
   lapsed, left". After the fix (``choices=None``) the open-enum path accepts it.

2. **Member create with a tenant status value (2.3).** The create/update validation of a record
   whose ``membership.status`` is the tenant-authored value SHALL succeed. On unfixed code it
   raises :class:`FieldValidationError`. (Driven through :func:`validate_fixed_fields`, the sole
   authoritative fixed-field gate both ``create_member`` and ``update_member`` run — no DynamoDB
   needed to surface the closed-set rejection.)

3. **Status change is a plain edit (2.4).** Changing a member's status ``active → application``
   SHALL be an ordinary field edit (any → any) with no transition graph. On unfixed code the
   engine denies it — ``HDCN_LIFECYCLE_CONFIG`` declares no ``active → application`` edge, so the
   graph lookup returns ``None`` (never a silent allow). After the fix there is no engine and the
   change is a plain partial update that validates.

DO NOT modify product code to make this test pass — it encodes the intended post-retirement
behavior and is re-run unchanged by task 3.7 to validate the fix.

Validates: Requirements 1.1, 1.2, 1.3, 1.4 (and, as the post-fix target, 2.1, 2.2, 2.3, 2.4)
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import (
    FieldResolver,
    FixedFieldOverride,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import (
    EnumOption,
    FieldType,
    FieldValidationError,
    field_by_key,
    validate_fixed_fields,
)

# The closed platform status set the UNFIXED code gatekeeps against (design Bug Condition).
_PLATFORM_STATUS = ("application", "pending", "active", "suspended", "lapsed", "left")

# The concrete failing case the bug was reported on: a tenant adds `died` / "Overleden".
_DIED = EnumOption(value="died", label={"en": "Passed Away", "nl": "Overleden"})

_TENANT = "h-dcn"


def _status_override_options(extra_value: str) -> tuple[EnumOption, ...]:
    """The tenant's authored `membership.status` option list: the 6 platform values + `died` + one extra.

    This is exactly how a tenant authors `gender` values via `members.field_overlay` — a rich
    `{value, label}` option list the Flask plane projects onto `config#fields`.
    """
    platform = tuple(
        EnumOption(value=v, label={"en": v.capitalize()}) for v in _PLATFORM_STATUS
    )
    return platform + (_DIED, EnumOption(value=extra_value, label={"en": extra_value}))


def _overlay_with_status_values(extra_value: str) -> TenantOverlay:
    return TenantOverlay(
        overrides={
            "membership.status": FixedFieldOverride(
                options=_status_override_options(extra_value)
            )
        }
    )


def _member_with_status(status_value: str) -> dict:
    """A minimal, otherwise-valid member record carrying the tenant-authored status value."""
    return {
        "personal": {"last_name": "Jansen"},
        "membership": {
            "status": status_value,
            "membership_type": "gewoon",
            "joined_date": "2020-01-01",
        },
    }


# A tenant-authored status value that is NOT one of the closed platform values (so it exercises
# the bug condition). Kept to simple non-blank tokens — the point is "a value the closed set
# rejects", not fuzzing the string codec.
_extra_status_values = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_",
    min_size=3,
    max_size=12,
).filter(lambda s: s.strip() and s not in _PLATFORM_STATUS and s != "died")


@settings(max_examples=25)
@given(extra_value=_extra_status_values)
def test_tenant_authored_status_value_survives_projection_and_validates(extra_value):
    """Property 1 facet A+B (2.1/2.2/2.3): a tenant status value survives resolve AND validates.

    EXPECTED ON UNFIXED CODE: FAILS — `validate_fixed_fields` rejects the tenant value against
    the closed `MembershipStatus` set ("must be one of: ..."), even though it resolved into
    `config#fields`. EXPECTED AFTER THE FIX: PASSES — `status` is an open enum (`choices=None`),
    so the value both survives projection and validates.
    """
    overlay = _overlay_with_status_values(extra_value)
    resolver = FieldResolver(StaticOverlayProvider({_TENANT: overlay}))

    # (A) The tenant value survives resolve → projection into config#fields status.choices (2.1/2.2).
    cfg = resolver.resolve(_TENANT)
    status_field = cfg.field("membership.status")
    assert status_field is not None and status_field.type is FieldType.ENUM
    resolved_choices = tuple(status_field.choices or ())
    assert "died" in resolved_choices, (
        "COUNTEREXAMPLE (2.1/2.2): tenant-authored 'died' did not reach the resolved "
        f"config#fields status.choices (got {resolved_choices!r})"
    )
    assert extra_value in resolved_choices, (
        "COUNTEREXAMPLE (2.1/2.2): tenant-authored status value "
        f"{extra_value!r} did not reach the resolved status.choices (got {resolved_choices!r})"
    )

    # (B) A member carrying the tenant value validates (2.3) — the AUTHORITATIVE gate create/
    # update run. On UNFIXED code this raises FieldValidationError because `validate_fixed_fields`
    # re-checks `status` against the CLOSED MembershipStatus set, not the resolved tenant choices.
    try:
        validate_fixed_fields(_member_with_status("died"))
    except FieldValidationError as exc:  # pragma: no cover - the unfixed-code path
        pytest.fail(
            "COUNTEREXAMPLE (2.3): create/update of a member with membership.status='died' "
            f"was REJECTED by the closed-set gate: {exc.errors['membership.status'].detail!r}. "
            "The tenant value survived projection but can never be set on a member — the bug."
        )

    validate_fixed_fields(_member_with_status(extra_value))  # the arbitrary extra value too


def test_create_member_with_died_status_is_accepted():
    """Property 1 facet B, concrete case (2.3): the reported `died` value must be settable.

    EXPECTED ON UNFIXED CODE: FAILS — raises FieldValidationError "must be one of: application,
    pending, active, suspended, lapsed, left". EXPECTED AFTER THE FIX: PASSES.
    """
    try:
        validate_fixed_fields(_member_with_status("died"))
    except FieldValidationError as exc:  # pragma: no cover - the unfixed-code path
        pytest.fail(
            "COUNTEREXAMPLE (2.3): membership.status='died' rejected — "
            f"{exc.errors['membership.status'].detail!r}"
        )


def test_status_field_is_an_open_enum_like_gender():
    """Property 1 (2.5): post-fix, `status` is a plain OPEN enum (`choices=None`), like `gender`.

    EXPECTED ON UNFIXED CODE: FAILS — `status.choices` is the closed 6-value `MembershipStatus`
    tuple. EXPECTED AFTER THE FIX: PASSES — `status.choices is None` (tenant supplies the values).
    """
    status = field_by_key("membership.status")
    gender = field_by_key("personal.gender")
    assert status is not None and gender is not None
    assert status.choices is None, (
        "COUNTEREXAMPLE (2.5): membership.status is still a CLOSED enum "
        f"(choices={status.choices!r}); the fix opens it like gender (choices={gender.choices!r})"
    )


def test_status_change_active_to_application_is_a_plain_edit():
    """Property 1 facet C (2.4): a status change `active -> application` is an ordinary edit.

    EXPECTED ON UNFIXED CODE: FAILS at the import — the transition STATE ENGINE still exists and
    `HDCN_LIFECYCLE_CONFIG` declares no `active -> application` edge, so the engine denies the
    change (never a silent allow). This asserts the engine is GONE and the change is a plain
    partial `update` that validates. EXPECTED AFTER THE FIX: PASSES — no engine; the edit
    validates as any-to-any.
    """
    # On unfixed code the lifecycle engine is present and gatekeeps the change. After the
    # retirement the module is deleted, so its import fails — which is the intended post-fix
    # signal that status change is no longer engine-gated. We encode the bug by asserting the
    # engine does NOT block `active -> application`.
    try:
        from sam.members.domain.lifecycle_config import HDCN_LIFECYCLE_CONFIG
        from sam.members.domain.fixed_fields import MembershipStatus
    except ImportError:
        # Post-fix: the engine + closed enum are gone. A status change is a plain field edit.
        validate_fixed_fields(
            {"membership": {"status": "application"}}, partial=True
        )
        return

    # Unfixed: the engine gatekeeps. `active -> application` is NOT a declared edge, so the
    # graph lookup returns None → the engine denies the change. That denial IS the bug.
    edge = HDCN_LIFECYCLE_CONFIG.transition(
        MembershipStatus.ACTIVE, MembershipStatus.APPLICATION
    )
    assert edge is not None, (
        "COUNTEREXAMPLE (2.4): status change active -> application is DENIED by the transition "
        "engine (no such edge in HDCN_LIFECYCLE_CONFIG) — status change is gatekept by the "
        "state machine instead of being an ordinary any-to-any field edit."
    )
