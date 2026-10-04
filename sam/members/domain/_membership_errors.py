"""Membership-service shared vocabulary (M1 split): module-level constants,
exception types, the ``TransitionResult`` dataclass, and the ``_as_field_error``
coercion helper. Extracted verbatim from ``membership_service.py`` so every mixin
sub-module and the facade import ONE canonical copy (no behaviour change).
"""
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

def _as_field_error(value: Any) -> FieldError:
    """Coerce a validation-map value to a :class:`FieldError` (API standard v1.0).

    The domain validators emit :class:`FieldError` directly, but two sources feed the merged map
    as plain strings: a tenant ``validate_member`` hook (which has no code vocabulary) and any
    legacy caller. Wrap such a string under the generic ``validation.invalidFormat`` code, keeping
    the original text as the human English ``detail`` so nothing is lost. An already-``FieldError``
    value passes through unchanged.
    """
    if isinstance(value, FieldError):
        return value
    return FieldError(code=VALIDATION_UNSUPPORTED_FIELD_TYPE, detail=str(value))



MEMBERSHIP_STATUS_FIELD_KEY = f"{FieldGroup.MEMBERSHIP.value}.status"

#: The canonical dotted key of the ``membership_type`` fixed field (design C8). The resolved
#: field config injects the tenant's ACTIVE Lidmaatschap Beheer catalog entries as this
#: field's selectable options, so the presentation-only frontend renders a dropdown of ONLY
#: that tenant's active types (no free text, no hardcoded vocabulary — R2.4).
MEMBERSHIP_TYPE_FIELD_KEY = f"{FieldGroup.MEMBERSHIP.value}.membership_type"

#: The fallback scope-dimension key the handler edge uses to KEY the tenant-wide-collapse map
#: for an un-partitioned tenant (a tenant with no enabled dimension → ``{DEFAULT_SCOPE_
#: DIMENSION_KEY: ["*"]}`` — R3.2). h-dcn's gating dimension happens to be ``region``. Since
#: s5d task 4.2 the service no longer takes a gating ``dimension_key`` on the read/write path
#: — ``_in_scope`` iterates the per-dimension ``allowed_scopes`` map directly — so this
#: constant is only consumed at the edge to name the single collapse entry, never hardcoded
#: into the domain scope check.
DEFAULT_SCOPE_DIMENSION_KEY = "region"

class MemberNotFound(Exception):
    """Raised when a member does not exist for the tenant, OR is out of the caller's scope.

    The two cases are deliberately indistinguishable to the caller (the edge maps this to a
    ``404``): a scoped user must not be able to tell "this member exists but is in another
    scope" apart from "this member does not exist", or the 404/403 difference would leak the
    existence of out-of-scope records. Isolation is still structural — the repository was
    only ever asked within ``tenant_id`` (Property 1).
    """

    def __init__(self, tenant_id: str, member_id: str):
        self.tenant_id = tenant_id
        self.member_id = member_id
        super().__init__(f"member {member_id!r} not found for tenant {tenant_id!r}")


class MembershipTypeNotFound(Exception):
    """Raised when a Lidmaatschap Beheer catalog entry does not exist for the tenant (→ 404).

    The catalog ``get`` read (design C8, task 3.4) is tenant-scoped by the verified
    ``tenant_id`` (Property 1); an absent ``type_code`` — or one that exists only for another
    tenant — is an ordinary not-found the edge maps to a ``404`` (mirroring
    :class:`MemberNotFound` → 404 for the member read). Retired (``active=false``) entries are
    NOT a not-found: the management view still returns them, so a soft-deleted type fetched by
    code returns it (with ``active: false``), never a 404.
    """

    def __init__(self, tenant_id: str, type_code: str):
        self.tenant_id = tenant_id
        self.type_code = type_code
        super().__init__(
            f"membership type {type_code!r} not found for tenant {tenant_id!r}"
        )


class MembershipTypeConflict(Exception):
    """Raised when CREATING a catalog entry whose ``type_code`` already exists (→ 409).

    The catalog ``create`` (design C8, task 5.3) is a *create*, not an upsert: a ``type_code``
    is the reference key member records store, so silently overwriting an existing entry on a
    "create" would let a client mutate a live type behind an ``update``-shaped API and risk
    changing the meaning of every member already referencing it. So create refuses a duplicate
    code with a conflict (the edge maps it to a ``409``); an intentional change goes through the
    ``update`` route (idempotent upsert). ``update`` and ``deactivate`` never raise this.
    """

    def __init__(self, tenant_id: str, type_code: str):
        self.tenant_id = tenant_id
        self.type_code = type_code
        super().__init__(
            f"membership type {type_code!r} already exists for tenant {tenant_id!r}"
        )


class TransitionDenied(Exception):
    """Raised when a membership transition is not permitted (design C2 — never a silent allow).

    A transition is denied when it is not declared in the tenant's lifecycle graph, or when
    one or more declarative guards fail, or when the tenant has no lifecycle config at all.
    ``reasons`` carries the human-readable cause(s) so the write route (task 5.2) / edge can
    surface them (mapped to a 409/422). A denied transition NEVER mutates the member or fires
    the ``on_transition`` hook.
    """

    def __init__(
        self,
        tenant_id: str,
        from_state: MembershipStatus | None,
        to_state: MembershipStatus,
        reasons: Sequence[str],
    ):
        self.tenant_id = tenant_id
        self.from_state = from_state
        self.to_state = to_state
        self.reasons = tuple(reasons)
        frm = getattr(from_state, "value", from_state)
        to = getattr(to_state, "value", to_state)
        detail = "; ".join(self.reasons) or "transition not allowed"
        super().__init__(
            f"transition {frm!r} -> {to!r} denied for tenant {tenant_id!r}: {detail}"
        )


class MemberValidationError(Exception):
    """Raised when a member write fails validation (fixed-field OR tenant ``validate_member``).

    The write path (task 5.2) validates a member in two authoritative passes, both here in
    the domain (never the frontend, R2.3 / Property 2): the platform-fixed field registry
    (:func:`~sam.members.domain.fixed_fields.validate_fixed_fields`) and the tenant's
    Rung-3 ``validate_member`` hook (design C5 — h-dcn's motor-club rule, task 5.1). The two
    error maps are MERGED so a caller sees every problem at once, mirroring
    :class:`~sam.members.domain.fixed_fields.FieldValidationError`. The edge maps this to a
    ``422`` (unprocessable) — a well-formed request that violates the data rules.
    """

    def __init__(self, errors: Mapping[str, FieldError]):
        self.errors: dict[str, FieldError] = {
            str(k): _as_field_error(v) for k, v in errors.items()
        }
        detail = "; ".join(f"{k}: {v.detail}" for k, v in self.errors.items())
        super().__init__(f"member validation failed: {detail}")


class ScopeDenied(Exception):
    """Raised when a scoped caller attempts a WRITE outside their ``allowed_scopes`` (→ 403).

    Reads map an out-of-scope member to a 404 (no existence leak — see
    :class:`MemberNotFound`); a WRITE is different — the caller has been authenticated and
    granted the write capability, but is trying to create/update/delete a record in a scope
    they do not hold, so the honest answer is an authorization denial (``403``), Property 4.
    Deny is the default: a non-wildcard caller may only write within the scope values they
    were granted, and self-service lets a member act on their OWN record only.
    """

    def __init__(self, tenant_id: str, message: str = "write outside allowed scope"):
        self.tenant_id = tenant_id
        super().__init__(f"{message} (tenant {tenant_id!r}, Property 4)")


@dataclass(frozen=True)
class TransitionResult:
    """The outcome of a PERMITTED transition COMPUTATION (design C2 — the pure decision).

    This is what :meth:`MembershipService.transition_membership` returns on success: the
    ``from_state`` / ``to_state`` and the ``member`` record with its ``membership.status``
    updated to the new state. It is a **computation**, not a persist — the state machine
    decides + dispatches the ``on_transition`` hook here, and the WRITE route (task 5.2) is
    responsible for saving the returned ``member`` via the repository (see the persist-boundary
    note on :meth:`MembershipService.transition_membership`).
    """

    tenant_id: str
    member: Member
    from_state: MembershipStatus
    to_state: MembershipStatus

