"""Membership-service WRITE path (M1 split): authoritative validation, member / membership create-update-delete, transitions, delegates, write-path helpers, and the resolved field-config surface. Mixed into ``MembershipService`` -- verbatim."""
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


class WritesMixin:
    # ── Write path (design C1 write / C2 / C5 / C6 — task 5.2) ────────────────────────
    #
    # Orchestration only: validate (fixed fields + tenant validate_member hook) → derive the
    # member number via the hook on create (threading the atomic counter value in) → for a
    # transition call the lifecycle engine above → persist via the repository (the SOLE
    # DynamoDB touch-point + owner of uniqueness/atomicity). No ``if tenant``, no boto3, no
    # HTTP here (Property 5). Scope + verify-before-trust are enforced BEFORE any persist.

    def _validate_member_record(
        self,
        tenant_id: str,
        record: Member,
        *,
        partial: bool,
        caller_roles: Sequence[str] = (),
    ) -> None:
        """Validate a member record authoritatively (design C2/C5, R2.3, Property 2).

        Server-side passes, in order (the frontend enforces nothing — R2.3):

        1. the platform-fixed field registry (:func:`validate_fixed_fields`, ``partial`` for
           updates) — required-ness / type / closed-status enum;
        2. the resolved-field gates (task 4.4, over the tenant's :class:`FieldConfig`):
           - **``show_when`` hidden-not-required** (R4.12): a field whose ``show_when`` condition
             does NOT hold for this record is NOT required — its "is required" error is dropped,
             so the server never demands a value for a field the frontend correctly hid;
           - **value-level enum role gating** (R4.12): a create/edit that sets a role-restricted
             option value the caller's role may not choose is rejected (403-worthy 422 error) —
             the authoritative gate behind the frontend's convenience option filtering;
           - **``member_number`` format** (R4.8): a present ``member_number`` must satisfy the
             tenant format pattern (the manual-entry string field);
        3. the tenant's Rung-3 ``validate_member`` hook (h-dcn's motor-club rule — the safe
           no-error default for an unregistered tenant).

        All error maps are merged and raised as one :class:`MemberValidationError` so the caller
        sees every problem at once. ``caller_roles`` are the verified roles of the writer (from
        the edge context) — empty for a caller with no roles (only unrestricted options allowed).
        """
        config = self._field_resolver.resolve(
            tenant_id, scope_vocab=self._scope_vocab(tenant_id)
        )

        errors: dict[str, FieldError] = {}
        try:
            validate_fixed_fields(record, partial=partial)
        except FieldValidationError as exc:
            errors.update(exc.errors)

        # (2a) show_when hidden-not-required: drop a "required" error for a fixed field whose
        # conditional-visibility condition is not satisfied by the record (R4.12). A hidden
        # field must not be demanded server-side any more than the frontend renders it.
        self._drop_hidden_required_errors(config, record, errors)

        # (2b) required VISIBLE overlay fields (R4.9/R4.12): the fixed-field registry only
        # validates the fixed base, so a required tenant OVERLAY field is enforced here —
        # authoritatively — but ONLY when it is shown (its `show_when` holds). A hidden overlay
        # field is never required (the mirror of the frontend not rendering it), and a partial
        # update leaves an untouched overlay field alone.
        self._validate_required_overlay_fields(config, record, partial, errors)

        # (2c) value-level enum role gating (R4.12) + (2d) member_number format (R4.8).
        self._reject_disallowed_enum_values(config, record, caller_roles, errors)
        self._validate_member_number(config, record, errors)

        hook_errors = self._tenant_hooks.dispatch(
            HookName.VALIDATE_MEMBER, tenant_id, record
        )
        if isinstance(hook_errors, Mapping):
            # A tenant hook returns ``{dotted_key: english_reason}`` (it has no code vocabulary).
            # Wrap each into a FieldError under the generic ``validation.invalidFormat`` code so the
            # merged map is uniformly typed; the tenant string is preserved as the English detail.
            for k, v in hook_errors.items():
                errors[str(k)] = _as_field_error(v)

        if errors:
            raise MemberValidationError(errors)

    @staticmethod
    def _record_value(record: Mapping[str, Any], field: ResolvedField) -> Any:
        """The record's value for a resolved field, honoring its STORAGE group / overlay bucket.

        A fixed/calculated field stores under its ``group`` bucket (``personal`` / ``membership``);
        a variable (overlay) field stores under the ``overlay`` bucket. Tolerant of a flattened
        top-level value too (the shape a client may send). Returns ``None`` when absent.
        """
        bucket = record.get(field.group)
        if isinstance(bucket, Mapping) and field.key in bucket:
            return bucket.get(field.key)
        return record.get(field.key)

    @staticmethod
    def _drop_hidden_required_errors(
        config: ResolvedFieldConfig,
        record: Member,
        errors: dict[str, FieldError],
    ) -> None:
        """Remove "required" errors for fields hidden by an unmet ``show_when`` (R4.12).

        A field whose ``show_when`` condition does not hold for this record is not shown to the
        caller, so the server must not require it either (hidden-not-required). We only DROP a
        required error — we never invent one — so this can only relax, never tighten.

        v1.0 coupling: this now compares the error's machine ``code`` against
        :data:`VALIDATION_REQUIRED` (the ``validation.required`` key) instead of the old English
        ``== "is required"`` string, so the prune survives the field-error refactor and any future
        wording change to the English ``detail``.
        """
        for field in config.fields:
            if field.show_when is None:
                continue
            if evaluate_show_when(field.show_when, record):
                continue
            dotted = field.dotted_key()
            existing = errors.get(dotted)
            if existing is not None and existing.code == VALIDATION_REQUIRED:
                del errors[dotted]

    @staticmethod
    def _validate_required_overlay_fields(
        config: ResolvedFieldConfig,
        record: Member,
        partial: bool,
        errors: dict[str, FieldError],
    ) -> None:
        """Require a VISIBLE, SHOWN overlay field that is marked required (R4.9/R4.12).

        The fixed-field registry (:func:`validate_fixed_fields`) validates only the fixed base,
        so a tenant OVERLAY field's ``required`` is enforced here — authoritatively (R2.3), never
        the frontend. It applies the same ``show_when`` hidden-not-required rule as the fixed
        fields: a required overlay field is demanded only when it is shown (its condition holds)
        AND visible. On a partial update an ABSENT overlay bucket / key means "leave unchanged",
        so a required overlay field is only enforced when the record touches its bucket (create,
        or an update that sends the ``overlay`` block).
        """
        overlay_bucket = record.get(OVERLAY_GROUP)
        has_overlay_bucket = isinstance(overlay_bucket, Mapping)
        for field in config.fields:
            if field.origin is not FieldOrigin.VARIABLE or not field.required or not field.visible:
                continue
            if not evaluate_show_when(field.show_when, record):
                continue  # hidden → not required
            if partial and not has_overlay_bucket:
                continue  # update that does not touch the overlay leaves it unchanged
            value = overlay_bucket.get(field.key) if has_overlay_bucket else None
            if value is None or (isinstance(value, str) and not value.strip()):
                errors[field.dotted_key()] = FieldError(
                    code=VALIDATION_REQUIRED, detail="is required"
                )

    @staticmethod
    def _reject_disallowed_enum_values(
        config: ResolvedFieldConfig,
        record: Member,
        caller_roles: Sequence[str],
        errors: dict[str, FieldError],
    ) -> None:
        """Reject a write that sets a role-restricted enum value the caller may not choose (R4.12).

        For every resolved field carrying rich :class:`EnumOption`s, if the record sets a value
        whose option is role-gated and the caller holds none of the option's roles, record an
        authoritative error. This is the authority behind the frontend's convenience option
        filtering: the client hides options the caller may not pick, but the domain — never the
        client — is the gate (a hand-crafted request that sets a disallowed value is rejected).
        An unknown value is left to the type/reference checks; only KNOWN gated options are
        checked here.
        """
        allowed = tuple(caller_roles or ())
        for field in config.fields:
            if not field.options:
                continue
            value = WritesMixin._record_value(record, field)
            if value is None:
                continue
            gate = roles_for_option(field.options, value)
            if gate is None:
                continue  # unknown value or an open (unrestricted) option — not our concern
            if not any(r in gate for r in allowed):
                gate_roles = sorted(gate)
                errors[field.dotted_key()] = FieldError(
                    code=ENUM_ROLE_RESTRICTED,
                    detail=(
                        f"value {value!r} is restricted to role(s) "
                        f"{', '.join(gate_roles)} — the caller is not permitted to set it"
                    ),
                    params={"value": value, "roles": gate_roles},
                )

    @staticmethod
    def _reject_invalid_overlay_enum_values(
        config: ResolvedFieldConfig,
        record: Member,
        errors: dict[str, FieldError],
        *,
        previous: Member | None = None,
    ) -> None:
        """Reject an OVERLAY enum value that is not one of the field's ``choices`` (A.5).

        Overlay dropdowns (e.g. h-dcn ``motor_brand``) are tenant config: an enum overlay field
        declares a closed ``choices`` list, and the domain — never the frontend — is the
        authority for it (R2.3, same convenience/authority split as everything else). The fixed
        registry validates only fixed enums; this closes the gap for tenant overlay enums.

        **Partial-update-friendly (the "enforce for new, tolerate legacy" contract).** When
        ``previous`` is given (an UPDATE), a field is only checked if the write actually CHANGES
        its value — so an untouched legacy value that predates the closed list (or a value set
        before an option was removed) does NOT block an unrelated edit (e.g. an address change).
        On a CREATE (``previous is None``) every present overlay-enum value is checked. This
        mirrors the ``membership_type`` "only-when-changed" rule (C8) so the two behave alike.

        Only VARIABLE-origin (overlay) enum fields with a non-empty ``choices`` are considered;
        an absent/blank value is left to the required-ness rule. An unknown value records a
        "must be one of: …" error merged into ``errors`` (surfaced as a 422 by the caller).
        """
        for field in config.fields:
            if field.origin is not FieldOrigin.VARIABLE:
                continue
            if field.type is not FieldType.ENUM or not field.choices:
                continue
            value = WritesMixin._record_value(record, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if previous is not None:
                # UPDATE: only enforce when the value actually changed (tolerate legacy).
                if WritesMixin._record_value(previous, field) == value:
                    continue
            # The resolver's contract is that `choices` is a bare value list, but a tenant's raw
            # overlay JSON can carry rich option objects ({"value","label"}) under `choices`
            # (instead of `options`); those flow through un-normalized. Coerce every choice to its
            # string value so the membership check + error join are robust to either shape and can
            # never raise (a malformed shape must surface as a 422, never a 502).
            allowed_values = [WritesMixin._choice_value(c) for c in field.choices]
            if value not in allowed_values:
                allowed = ", ".join(allowed_values)
                errors[field.dotted_key()] = FieldError(
                    code=VALIDATION_MUST_BE_ONE_OF,
                    detail=f"must be one of: {allowed}",
                    params={"allowed": allowed_values},
                )

    @staticmethod
    def _choice_value(choice: Any) -> str:
        """Coerce a single enum choice to its string *value*, tolerant of shape.

        The resolver normalizes `choices` to a bare value list, but a tenant's raw overlay JSON
        can carry rich option objects (``{"value": ..., "label": ...}``) or an ``EnumOption``
        under `choices`. Return the ``value`` for those, else the plain string — so a membership
        check / error message never chokes on a dict (which caused a 502, not a 422).
        """
        if isinstance(choice, Mapping):
            return str(choice.get("value", ""))
        value_attr = getattr(choice, "value", None)
        if value_attr is not None:
            return str(value_attr)
        return str(choice)

    @staticmethod
    def _validate_member_number(
        config: ResolvedFieldConfig,
        record: Member,
        errors: dict[str, FieldError],
    ) -> None:
        """Authoritatively validate a present ``member_number`` against the tenant format (R4.8).

        ``member_number`` is an OPTIONAL manual-entry Fixed **string** (never numeric); its
        tenant format pattern lives on the resolved field (``member_number_format``). When the
        record sets a member number it must satisfy that pattern. An absent value is allowed
        (s5k — member_number is optional, no uniqueness guard); only a PRESENT value is
        format-checked here.
        """
        field = config.field(MEMBER_NUMBER_FIELD_KEY)
        if field is None or field.member_number_format is None:
            return
        value = WritesMixin._record_value(record, field)
        if value is None:
            return
        reason = validate_member_number_format(value, field.member_number_format)
        if reason is not None:
            errors[MEMBER_NUMBER_FIELD_KEY] = reason

    @staticmethod
    def _membership_type_of(record: Mapping[str, Any]) -> str | None:
        """The record's ``membership.membership_type`` reference, or ``None`` if unset.

        Used to detect whether an update actually CHANGES the type (so the reference check is
        only re-run on a real change — partial-update friendliness, design C8). Tolerant of a
        record with no ``membership`` block.
        """
        membership = record.get("membership")
        if not isinstance(membership, Mapping):
            return None
        value = membership.get("membership_type")
        return str(value) if value is not None else None

    def _validate_membership_type_reference(self, tenant_id: str, record: Member) -> None:
        """Authoritatively validate the member's ``membership_type`` catalog reference (C8).

        The domain — never the frontend — is the authority for referential integrity (R2.4,
        Property 2): the React dropdown that lists a tenant's active types is convenience only,
        so a create/update MUST re-check the effective ``membership.membership_type`` against
        the tenant's LIVE catalog. The rule (design C8):

        - the value must reference a catalog entry that **exists** for THIS tenant (Property 1,
          tenant-agnostic — the check is against the tenant's own catalog, no ``if tenant``);
        - that entry must be **active** — a soft-deleted (retired) type is not assignable to a
          new/edited member (it has left the dropdown), so it fails the reference check;
        - an **unknown** code fails too.

        A missing ``membership_type`` is NOT rejected here — the fixed-field registry
        (:func:`validate_fixed_fields`) owns the "required" rule (a create with no type already
        fails there; a partial update that does not touch it is left alone). This method only
        rejects a *present* value that does not resolve to a live entry, merging its error into
        the caller's :class:`MemberValidationError` (a 422). It is applied only on create/update
        writes — never on reads — so an EXISTING member that references a since-retired type
        stays valid (we do not retroactively invalidate stored members, design C8).
        """
        membership = record.get("membership")
        if not isinstance(membership, Mapping):
            return
        type_code = membership.get("membership_type")
        if type_code is None or (isinstance(type_code, str) and not type_code.strip()):
            # Absence/blank is the fixed-field registry's concern (required-ness), not ours.
            return

        entry = self._repo.get_membership_type(tenant_id, str(type_code))
        if entry is None:
            raise MemberValidationError(
                {
                    MEMBERSHIP_TYPE_FIELD_KEY: FieldError(
                        code=MEMBERSHIP_TYPE_UNKNOWN_REFERENCE,
                        detail=(
                            f"unknown membership type {str(type_code)!r} "
                            "(not in the tenant's Lidmaatschap Beheer catalog)"
                        ),
                        params={"type_code": str(type_code)},
                    )
                }
            )
        if not entry.active:
            raise MemberValidationError(
                {
                    MEMBERSHIP_TYPE_FIELD_KEY: FieldError(
                        code=MEMBERSHIP_TYPE_RETIRED,
                        detail=(
                            f"membership type {str(type_code)!r} is retired (active=false) "
                            "and cannot be assigned to a new or updated member"
                        ),
                        params={"type_code": str(type_code)},
                    )
                }
            )

    def _sanitize_write_payload(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Copy a client write payload, stripping fields the client may NEVER set.

        Verify-before-trust (Property 2): the ``tenant_id`` / partition key is authoritative
        from the verified context and is stamped by the service, never accepted from the body.
        We drop any client-supplied ``tenant_id`` / DynamoDB partition-key attribute so a
        caller cannot steer a write into another tenant's partition. The ``member_id`` is
        likewise dropped: it is an OPAQUE INTERNAL identity generated by the SYSTEM (a uuid4 on
        create), never client-controlled and never the human Lidnummer (s5k R1). The scope field
        is a PLAIN member field (S5d D1 — no ``scope_values`` bucket); it is kept as ordinary data
        and a scoped caller's scope is authorized separately (:meth:`_authorize_write`).
        """
        payload = {
            k: v
            for k, v in dict(body).items()
            if k not in ("tenant_id", "PK", "pk", "member_id")
        }
        return payload

    def _authorize_write(
        self,
        tenant_id: str,
        member: Member,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None,
        self_service: bool,
    ) -> None:
        """Authorize a WRITE against the caller's scope, or raise :class:`ScopeDenied` (403).

        Deny-by-default (Property 4/6): a caller may write a record only when it passes EVERY
        scope dimension in ``allowed_scopes`` (:meth:`_in_scope`) — a wildcard on a dimension
        passes that axis, an empty grant on a dimension denies it, and an empty map denies.
        Self-service lets a member write their OWN record (matched on ``requester_sub``) even
        without a broad scope — used by the delegate routes so a member can manage their own
        delegates. Reuses the same ``_in_scope`` rule the reads share, so read/write scope
        stays uniform.
        """
        if self._in_scope(member, allowed_scopes):
            return
        if self_service and self._owns_record(member, requester_sub):
            return
        raise ScopeDenied(tenant_id)

    def create_member(
        self,
        tenant_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        caller_roles: Sequence[str] = (),
    ) -> Member:
        """Create a member for the tenant (design C1 write / C2 / C5 / C6, R1.4/R3.3).

        Orchestration: sanitize the payload (never trust a body ``tenant_id`` — Property 2) →
        stamp the authoritative ``tenant_id`` → set the initial lifecycle state from the
        tenant's :class:`LifecycleConfig` when the body carries none → validate (fixed fields +
        tenant ``validate_member``) → authorize the write against the caller's scope → persist
        via ``save_member`` (a single ``PutItem``).

        s5k: ``member_number`` is a plain OPTIONAL string supplied by the caller/import — there is
        NO auto-generation and NO member-number uniqueness guard. A duplicate number is a
        data-quality concern, not a write-time conflict.
        """
        record = self._sanitize_write_payload(body)
        record["tenant_id"] = tenant_id  # authoritative — verify-before-trust (Property 2)

        # member_id is an OPAQUE INTERNAL identity generated by the SYSTEM — a uuid4, ALWAYS minted
        # here on create (any client-supplied member_id was already stripped by the sanitizer,
        # verify-before-trust). It is never the human Lidnummer (`member_number`, just a field) and
        # never client-controlled (s5k R1). Without it the repository's save_member rejects the
        # record (a 502 on create). The h-dcn backfill mints its own uuid4 the same way.
        record["member_id"] = str(uuid.uuid4())

        membership = dict(record.get("membership") or {})

        # Initial lifecycle state from the tenant's config when the body sets none.
        config = self._lifecycle_provider.get_lifecycle_config(tenant_id)
        if not membership.get("status") and config is not None:
            membership["status"] = config.initial_state.value

        # s5k: NO member-number auto-generation. `member_number` is a plain OPTIONAL string that
        # the caller/import supplies (numeric like `M00012`, alphanumeric like `ABCDEFG`, or
        # empty). The former counter-fetch + `derive_member_number` hook are removed (a club admin
        # types/imports the number; auto-numbering was rejected as too complex — see spec s5k).
        record["membership"] = membership

        self._validate_member_record(
            tenant_id, record, partial=False, caller_roles=caller_roles
        )
        # Authoritative referential-integrity check (design C8, task 5.3): the member's
        # membership_type must reference a LIVE catalog entry for the tenant (the dropdown is
        # convenience only — never trusted). A missing/unknown/retired reference → 422. This
        # CLOSES the loop 5.2 opened (it carried the value but deferred the catalog check).
        self._validate_membership_type_reference(tenant_id, record)
        # A.5: authoritatively enforce OVERLAY enum dropdowns against their `choices` on create
        # (every present value is checked — there is no prior state to tolerate).
        overlay_enum_errors: dict[str, str] = {}
        self._reject_invalid_overlay_enum_values(
            self._field_resolver.resolve(
                tenant_id, scope_vocab=self._scope_vocab(tenant_id)
            ),
            record,
            overlay_enum_errors,
        )
        if overlay_enum_errors:
            raise MemberValidationError(overlay_enum_errors)
        self._authorize_write(
            tenant_id,
            record,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=False,
        )
        return self._repo.save_member(tenant_id, record)

    def update_member(
        self,
        tenant_id: str,
        member_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        self_service: bool = False,
        caller_roles: Sequence[str] = (),
    ) -> Member:
        """Partial-update a member (design C1 write / C2, R1.4/R3.3).

        Loads the existing member within the tenant (Property 1) and authorizes the write
        against the EXISTING record's scope (a scoped caller cannot touch an out-of-scope
        member — :class:`ScopeDenied` → 403). Deep-merges the sanitized body over the existing
        record (the client never sets ``tenant_id`` — Property 2; ``member_id`` stays the
        path's), re-authorizes on the MERGED record (a scoped caller may not move a member OUT
        of their scope either), re-validates (fixed fields ``partial=True`` + tenant
        ``validate_member``), and re-saves (idempotent for the same member number — the repo
        allows it, Property 6).
        """
        existing = self._repo.get_member(tenant_id, member_id)
        if existing is None:
            raise MemberNotFound(tenant_id, member_id)

        self._authorize_write(
            tenant_id,
            existing,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )

        patch = self._sanitize_write_payload(body)
        merged = self._deep_merge(dict(existing), patch)
        merged["tenant_id"] = tenant_id
        merged["member_id"] = member_id  # the path is authoritative for identity

        # A scoped caller must not move a member OUT of (or into a foreign) scope.
        self._authorize_write(
            tenant_id,
            merged,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )

        self._validate_member_record(
            tenant_id, merged, partial=True, caller_roles=caller_roles
        )
        # Referential integrity on update (design C8, task 5.3), applied ONLY when the patch
        # CHANGES the membership_type reference. This is the partial-update-friendly rule the
        # spec asks for: a patch that MOVES the reference to a new value must point at a LIVE
        # catalog entry (unknown/retired → 422), but an update that does NOT touch the type is
        # left alone — so an EXISTING member that references a since-retired type stays
        # updatable (name/contact edits, transitions, etc.) without being forced to re-pick a
        # type (C8 — no retroactive invalidation of stored members). Comparing the effective
        # merged value against the stored one detects a real change (a patch that re-sends the
        # SAME code is a no-op and is not re-validated).
        if self._membership_type_of(merged) != self._membership_type_of(existing):
            self._validate_membership_type_reference(tenant_id, merged)
        # A.5: enforce OVERLAY enum dropdowns against their `choices`, but ONLY for a field the
        # patch actually CHANGES (partial-update-friendly) — an untouched legacy value (e.g. a
        # pre-existing off-list `motor_brand`) does NOT block an unrelated edit like an address
        # change. Mirrors the membership_type "only-when-changed" rule above.
        overlay_enum_errors: dict[str, str] = {}
        self._reject_invalid_overlay_enum_values(
            self._field_resolver.resolve(
                tenant_id, scope_vocab=self._scope_vocab(tenant_id)
            ),
            merged,
            overlay_enum_errors,
            previous=existing,
        )
        if overlay_enum_errors:
            raise MemberValidationError(overlay_enum_errors)
        return self._repo.save_member(tenant_id, merged)

    def delete_member(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
    ) -> dict[str, Any]:
        """Delete a member (admin-gated at the edge; scope-checked here — design C6).

        Loads the member within the tenant (Property 1), authorizes the delete against its
        scope (:class:`ScopeDenied` → 403 for a scoped caller reaching out of scope), then
        deletes via the repository (a single ``DeleteItem``; s5k removed the ``membernum#``
        guard). Returns a small deletion receipt.
        """
        existing = self._repo.get_member(tenant_id, member_id)
        if existing is None:
            raise MemberNotFound(tenant_id, member_id)
        self._authorize_write(
            tenant_id,
            existing,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=False,
        )
        self._repo.delete_member(tenant_id, member_id)
        return {"deleted": True, "member_id": member_id}

    # ── Membership create / update / delete / transition (design C1 write / C2) ───────

    def create_membership(
        self,
        tenant_id: str,
        member_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
    ) -> Membership:
        """Create a membership for a member, gated by the parent member's write scope.

        The parent member must exist within the tenant and be writable by the caller (scope —
        :class:`ScopeDenied` → 403), then the membership is persisted via ``save_membership``
        (tenant-scoped — Property 1). The membership id is the client's; a missing id is a
        validation error the repository surfaces.
        """
        self._writable_member_or_raise(
            tenant_id, member_id, allowed_scopes, requester_sub=requester_sub
        )
        membership = self._sanitize_write_payload(body)
        return self._repo.save_membership(tenant_id, member_id, membership)

    def update_membership(
        self,
        tenant_id: str,
        member_id: str,
        membership_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
    ) -> Membership:
        """Update a membership, gated by the parent member's write scope.

        Enforces the parent member's write gate, then loads the membership within the tenant
        (a missing one → :class:`MemberNotFound` → 404), merges the sanitized body over it
        (the ``membership_id`` stays the path's), and re-saves.
        """
        self._writable_member_or_raise(
            tenant_id, member_id, allowed_scopes, requester_sub=requester_sub
        )
        existing = self._repo.get_membership(tenant_id, member_id, membership_id)
        if existing is None:
            raise MemberNotFound(tenant_id, member_id)
        merged = self._deep_merge(dict(existing), self._sanitize_write_payload(body))
        merged["membership_id"] = membership_id
        return self._repo.save_membership(tenant_id, member_id, merged)

    def delete_membership(
        self,
        tenant_id: str,
        member_id: str,
        membership_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
    ) -> dict[str, Any]:
        """Delete a membership (admin-gated at the edge; parent member's write scope here)."""
        self._writable_member_or_raise(
            tenant_id, member_id, allowed_scopes, requester_sub=requester_sub
        )
        self._repo.delete_membership(tenant_id, member_id, membership_id)
        return {"deleted": True, "member_id": member_id, "membership_id": membership_id}

    def transition_member(
        self,
        tenant_id: str,
        member_id: str,
        to_state: MembershipStatus,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        context: Mapping[str, Any] | None = None,
        requester_sub: str | None = None,
    ) -> TransitionResult:
        """Apply + PERSIST a lifecycle transition to a member (design C2 / C5, R1.4).

        The full WRITE-path transition (distinct from the pure computation
        :meth:`transition_membership`): load the member within the tenant (Property 1),
        authorize the write against its scope (:class:`ScopeDenied` → 403), compute the
        transition via the lifecycle engine (guards + ``on_transition`` hook fire ONLY on a
        permitted move; a denial raises :class:`TransitionDenied` → 409/422 and never mutates
        or fires the hook), then persist the state-updated record via ``save_member``. Returns
        the :class:`TransitionResult` (now persisted).
        """
        member = self._repo.get_member(tenant_id, member_id)
        if member is None:
            raise MemberNotFound(tenant_id, member_id)
        self._authorize_write(
            tenant_id,
            member,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=False,
        )
        result = self.transition_membership(
            tenant_id, member, to_state, context=context
        )
        self._repo.save_member(tenant_id, result.member)
        return result

    def bulk_transition_members(
        self,
        tenant_id: str,
        member_ids: Sequence[str],
        to_state: MembershipStatus,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        context: Mapping[str, Any] | None = None,
        requester_sub: str | None = None,
    ) -> dict[str, Any]:
        """Apply one transition to many members, reporting a per-item outcome (admin capability).

        Applies :meth:`transition_member` to each id independently and records a per-item
        result (``ok`` / the from→to states, or the failure reason) so a partial batch surfaces
        exactly which items moved and which were denied/not-found — never an all-or-nothing
        silent failure. Each item's guards/scope/hook are enforced individually.
        """
        results: list[dict[str, Any]] = []
        for member_id in member_ids:
            try:
                outcome = self.transition_member(
                    tenant_id,
                    member_id,
                    to_state,
                    allowed_scopes,
                    context=context,
                    requester_sub=requester_sub,
                )
                results.append(
                    {
                        "member_id": member_id,
                        "ok": True,
                        "from": outcome.from_state.value,
                        "to": outcome.to_state.value,
                    }
                )
            except (TransitionDenied, MemberNotFound, ScopeDenied) as exc:
                results.append(
                    {"member_id": member_id, "ok": False, "error": str(exc)}
                )
        return {
            "to_state": to_state.value,
            "results": results,
            "succeeded": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
        }

    # ── Delegates (design C1 write — task 5.2; self-service) ──────────────────────────

    def manage_delegates(
        self,
        tenant_id: str,
        member_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        self_service: bool = True,
    ) -> dict[str, Any]:
        """Replace a member's delegate set (design C1 write; self-service allowed).

        The parent member must be writable by the caller — via scope OR, because this is a
        self-service route, because the caller OWNS the record (a member managing their own
        delegates), else :class:`ScopeDenied` → 403. Accepts either ``{"delegates": [...]}``
        or a bare list, and replaces the set via ``save_delegates`` (tenant-scoped — Property
        1). Returns the stored set.
        """
        self._writable_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        if isinstance(body, Mapping):
            raw = body.get("delegates", [])
        else:
            raw = body
        delegates = list(raw) if isinstance(raw, (list, tuple)) else []
        stored = self._repo.save_delegates(tenant_id, member_id, delegates)
        return {"member_id": member_id, "delegates": list(stored)}

    def send_delegate_invitation(
        self,
        tenant_id: str,
        member_id: str,
        body: Mapping[str, Any],
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        self_service: bool = True,
    ) -> dict[str, Any]:
        """Record a delegate INVITATION intent for a prospective delegate (design C1 write).

        Pilot scope: no live email/SNS here (no shared mail util is wired into this module,
        and introducing one would exceed the pilot's minimal, reversible footprint). Instead
        the invitation intent is appended to the member's delegate set as a pending entry
        (``status="invited"``) via the same tenant-scoped ``save_delegates`` seam, so the
        behaviour is real, reversible, and tenant-scoped — a later task can attach an actual
        notification channel behind this method without changing its contract. Requires a
        ``delegate_email`` (or ``email``) in the body; a missing one is a
        :class:`MemberValidationError` (→ 422).

        Note: sending the actual email/SNS notification is intentionally deferred for the
        pilot — this records the intent only.
        """
        self._writable_member_or_raise(
            tenant_id,
            member_id,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        email = None
        if isinstance(body, Mapping):
            email = body.get("delegate_email") or body.get("email")
        if not (isinstance(email, str) and email.strip()):
            raise MemberValidationError(
                {"delegate_email": "a delegate email is required to send an invitation"}
            )
        existing = list(self._repo.list_member_delegates(tenant_id, member_id))
        invitation = {
            "email": email,
            "status": "invited",
            "invited_by": requester_sub,
        }
        existing.append(invitation)
        stored = self._repo.save_delegates(tenant_id, member_id, existing)
        return {"member_id": member_id, "invitation": invitation, "delegates": list(stored)}

    # ── Write-path shared helpers ─────────────────────────────────────────────────────

    def _writable_member_or_raise(
        self,
        tenant_id: str,
        member_id: str,
        allowed_scopes: Mapping[str, Sequence[str]],
        *,
        requester_sub: str | None = None,
        self_service: bool = False,
    ) -> Member:
        """Load a member within the tenant and authorize a WRITE against it, or raise.

        A missing member is :class:`MemberNotFound` (→ 404); an out-of-scope write is
        :class:`ScopeDenied` (→ 403). Shared by every child-write (membership/delegate)
        so the parent member's write authorization is enforced uniformly (Property 1/4/6).
        """
        member = self._repo.get_member(tenant_id, member_id)
        if member is None:
            raise MemberNotFound(tenant_id, member_id)
        self._authorize_write(
            tenant_id,
            member,
            allowed_scopes,
            requester_sub=requester_sub,
            self_service=self_service,
        )
        return member

    @staticmethod
    def _deep_merge(base: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
        """Recursively merge ``patch`` into a copy of ``base`` (partial-update semantics).

        Nested mappings (e.g. ``personal`` / ``membership``) are merged key-by-key so a
        partial update touches only the supplied sub-fields; a scalar/list in ``patch``
        replaces the base value. Absent keys in ``patch`` leave the base unchanged — the
        ``partial=True`` update contract.
        """
        result = dict(base)
        for key, value in patch.items():
            if (
                key in result
                and isinstance(result[key], Mapping)
                and isinstance(value, Mapping)
            ):
                result[key] = WritesMixin._deep_merge(dict(result[key]), value)
            else:
                result[key] = value
        return result

    # ── Resolved field config (design C3 + C8, R2.3/R2.4 — task 3.3) ──────────────────

    def _scope_vocab(self, tenant_id: str) -> dict[str, tuple]:
        """The ``{member_field_key: values}`` map for this tenant's ENABLED scope dimensions.

        S5j (design D1a): built from the injected scope-config provider, keyed by each enabled
        dimension's ``field`` (the member field it binds to — which defaults to, but may differ
        from, the dimension ``key``). Consumed by :meth:`get_field_config` (and the write
        validator) so a scope-dimension-backed overlay ``enum`` sources its dropdown choices
        from ``scope_dimensions.values`` — the single source of truth, no stored duplication.
        Returns an EMPTY map when no provider is wired or the tenant has no enabled dimension
        (→ the resolver behaves exactly as before). Multiple dimensions → multiple entries.
        """
        if self._scope_config_provider is None:
            return {}
        config = self._scope_config_provider.get_scope_config(tenant_id)
        vocab: dict[str, tuple] = {}
        for dim in config.enabled():
            field_key = dim.field or dim.key
            if field_key:
                vocab[field_key] = dim.normalized_values()
        return vocab

    def get_field_config(self, tenant_id: str) -> dict[str, Any]:
        """Return the tenant's resolved field config for the presentation-only frontend.

        Composes the two authoritative domain pieces (the frontend holds NO rules — it
        renders what this returns, R2.3, verify-before-trust):

        1. :meth:`FieldResolver.resolve` — the fixed base ⊕ per-tenant overlay field config
           (design C3), keyed by the verified ``tenant_id`` (never a client-supplied tenant).
        2. :meth:`MembersRepository.list_membership_types` with ``active_only=True`` — the
           tenant's ACTIVE Lidmaatschap Beheer catalog entries (design C8), ordered by
           ``(order, type_code)``. Soft-deleted (``active=false``) types are excluded, so
           they never appear as a selectable option.

        The active catalog entries are injected as the ``membership_type`` field's ``options``
        (that fixed field is a :class:`~sam.members.domain.fixed_fields.FieldType.REFERENCE`),
        so the frontend renders a dropdown of ONLY that tenant's active types — no free text,
        no hardcoded vocabulary (R2.4).

        Returns a JSON-friendly dict (the edge ``json.dumps`` it): the flat ordered ``fields``
        list, the same fields bucketed ``by_group`` (``personal`` / ``membership`` / overlay),
        and the standalone ``membership_type_options`` catalog feed.
        """
        config = self._field_resolver.resolve(
            tenant_id, scope_vocab=self._scope_vocab(tenant_id)
        )
        options = self._active_membership_type_options(tenant_id)

        fields = [
            self._serialize_field(f, options=options) for f in config.fields
        ]
        by_group: dict[str, list[dict[str, Any]]] = {}
        for field_payload in fields:
            by_group.setdefault(field_payload["group"], []).append(field_payload)

        return {
            "tenant_id": config.tenant_id,
            "fields": fields,
            "by_group": by_group,
            # The tenant's functional (display) group catalog (R4.9). The modals + view contexts
            # SECTION the resolved field set by these (design C-SURFACE): each section is a
            # `functional_groups` entry, ordered by `order`. A field whose `functional_group` is
            # not in this catalog falls back to a default section at render (Property 7). Empty
            # when the tenant authored no catalog — the modals then group by the base defaults.
            "functional_groups": [
                self._serialize_functional_group(g) for g in config.functional_groups
            ],
            # The tenant's ENABLED scope dimensions (e.g. region + its allowed values). The Add/
            # Edit modal's scope control + the table's region filter read their option list from
            # this array (frontend `ScopeDimension` shape). Same source as `_scope_vocab`, so the
            # dropdown and the write-validator's allowed set stay in lockstep. Empty when the
            # tenant has no enabled dimension (or no provider is wired).
            "dimensions": self._serialize_scope_dimensions(tenant_id),
            "membership_type_options": options,
            # The tenant's selectable view contexts (S5c task 3.2, design C-VIEW). Sourced from
            # the injected ViewContextsProvider (the projection reader's config#views row in
            # production, a StaticViewContextsProvider in tests), keyed by the verified
            # tenant_id. Empty-is-valid (R5.1): a tenant that authored none surfaces exactly one
            # default context over all visible fields — the provider guarantees ≥1, so this list
            # is never empty and never crashes on an unconfigured tenant. Presentation-only: the
            # frontend renders these; the module enforces nothing off them (row scope stays
            # server-side, orthogonal).
            "view_contexts": [
                self._serialize_view_context(vc)
                for vc in self._view_contexts_provider.get_view_contexts(tenant_id)
            ],
            # The tenant's membership lifecycle, as DECLARED BY THE MODULE (design C2, R5.7).
            # The single + bulk transition modals read their candidate target states from this
            # block ONLY — never a hardcoded status list. A tenant with no configured lifecycle
            # yields `None` here, so the SPA offers NO transition targets (deny-by-default at
            # the UI); the module stays authoritative regardless (it re-validates every
            # transition and answers 409 with reasons on a denial). Presentation-only: the SPA
            # renders the candidate list off this; enforcement stays here.
            "lifecycle": self._serialize_lifecycle(tenant_id),
        }

    def _serialize_lifecycle(self, tenant_id: str) -> dict[str, Any] | None:
        """Project the tenant's :class:`LifecycleConfig` into the SPA's `lifecycle` shape (C2).

        Sourced from the injected :class:`LifecycleConfigProvider` (the module's declarative
        state machine), keyed by the verified ``tenant_id``. Returns ``None`` when the tenant
        has no configured lifecycle — the SPA then offers no transition targets (deny-by-default
        at the UI, R5.7). Deliberately limited: this exposes only the declarative transition
        graph the module already models — no editor, no extra states, no workflow features.

        The shape mirrors the frontend `LifecycleConfigShape`:
          - ``allowed_states``: the tenant's state vocabulary (order kept);
          - ``initial_state``: the state a new member starts in;
          - ``allowed_transitions``: ``{ fromState: [toState, ...] }`` (the preferred edge map
            the modals read for a member's current state / the bulk union);
          - ``requires_approval``: the ``fromState->toState`` edges whose declarative guards
            read ``context.approved`` (so the SPA renders the approval checkbox). Derived from
            the guard data — never a hardcoded edge list.

        Presentation-only: the module re-validates every transition server-side (409 with
        reasons on a denial), so this candidate description is a convenience, never the
        authority.
        """
        config = self._lifecycle_provider.get_lifecycle_config(tenant_id)
        if config is None:
            return None

        allowed_transitions: dict[str, list[str]] = {}
        requires_approval: list[str] = []
        for rule in config.transitions:
            frm = rule.from_state.value
            to = rule.to_state.value
            allowed_transitions.setdefault(frm, []).append(to)
            # An edge whose declarative guards read the `context.approved` fact needs the
            # approval checkbox in the modal — derived from the guard data, not hardcoded.
            if any(
                guard.field == "context.approved" for guard in rule.guards
            ):
                requires_approval.append(f"{frm}->{to}")

        return {
            "allowed_states": [s.value for s in config.allowed_states],
            "initial_state": config.initial_state.value,
            "allowed_transitions": allowed_transitions,
            "requires_approval": requires_approval,
        }

    def _serialize_scope_dimensions(self, tenant_id: str) -> list[dict[str, Any]]:
        """Project the tenant's ENABLED scope dimensions into the frontend `dimensions` shape.

        The Add/Edit modal's region control + the table's region filter read their option list
        from ``FieldConfig.dimensions`` (a ``[{key, label, enabled, values}]`` array — see the
        frontend ``ScopeDimension`` type). Sourced from the SAME injected scope-config provider
        that feeds :meth:`_scope_vocab` (``scope_dimensions.values`` is the single source of
        truth), so the dropdown values and the write-validator's allowed set can never diverge.
        Empty when no provider is wired or the tenant has no enabled dimension.
        """
        if self._scope_config_provider is None:
            return []
        config = self._scope_config_provider.get_scope_config(tenant_id)
        return [
            {
                "key": dim.key,
                "label": dict(dim.label),
                "enabled": bool(dim.enabled),
                "values": list(dim.normalized_values()),
            }
            for dim in config.enabled()
        ]

    @staticmethod
    def _serialize_functional_group(group: FunctionalGroup) -> dict[str, Any]:
        """Project a :class:`FunctionalGroup` (display-section) catalog entry to pure JSON (R4.9).

        Carries the section ``key``, its bilingual ``{nl,en}`` ``label`` (the section heading the
        modals render), and its ``order`` (the section sort). Presentation-only — the frontend
        sections by it; the module enforces nothing off it.
        """
        return {
            "key": group.key,
            "label": dict(group.label),
            "order": int(group.order),
        }

    @staticmethod
    def _serialize_view_context(vc: ViewContext) -> dict[str, Any]:
        """Project a :class:`ViewContext` into the JSON-friendly shape the frontend renders.

        Carries the context's key / bilingual ``{nl,en}`` label / ``permission_roles`` (the
        view-convenience dropdown gate) plus the ``ui.tables``-shaped presentation primitives
        (``columns`` / ``filterable_columns`` / ``default_sort`` / ``page_size``). Sequences are
        flattened to plain lists and the label to a plain dict so the payload is pure JSON (the
        edge ``json.dumps`` it). ``is_default`` rides along so the SPA can tell the synthesized
        empty-is-valid default context apart from an authored one.
        """
        return {
            "key": vc.key,
            "label": dict(vc.label),
            "permission_roles": list(vc.permission_roles),
            "columns": list(vc.columns),
            "filterable_columns": list(vc.filterable_columns),
            "default_sort": dict(vc.default_sort) if vc.default_sort is not None else None,
            "page_size": vc.page_size,
            "is_default": vc.is_default,
        }

    def _active_membership_type_options(self, tenant_id: str) -> list[dict[str, Any]]:
        """The tenant's ACTIVE catalog entries as JSON-friendly dropdown options (design C8).

        Asks the repository for the tenant's active membership types (``active_only=True``,
        tenant-scoped — Property 1), already ordered by ``(order, type_code)``. Each option
        carries the reference ``value`` (``type_code``) the member record stores plus its
        i18n ``label`` and ``order`` for presentation. Retired (soft-deleted) types are
        excluded by the repository, so they never render.

        Reuses :meth:`_serialize_catalog_option` so the dropdown feed and the catalog list
        route (task 3.4) project each entry identically (one serializer, one shape).
        """
        entries = self._repo.list_membership_types(tenant_id, active_only=True)
        return [self._serialize_catalog_option(entry) for entry in entries]

