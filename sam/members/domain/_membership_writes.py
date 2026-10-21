"""Membership-service WRITE path (M1 split): authoritative validation, member / membership create-update-delete, transitions, delegates, write-path helpers, and the resolved field-config surface. Mixed into ``MembershipService`` -- verbatim."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from sam.members.domain._membership_errors import (
    MEMBERSHIP_TYPE_FIELD_KEY,
    MemberNotFound,
    MemberValidationError,
    ScopeDenied,
    _as_field_error,
)
from sam.members.domain import field_formats
from sam.members.domain.applicant_locale import (
    SUPPORTED_LOCALES,
    locale_record_patch,
    normalize_locale,
)
from sam.members.domain.application_choices import (
    application_subset_choices,
    validate_application_choice,
)
from sam.members.domain.error_codes import (
    CONSENT_REQUIRED,
    ENUM_ROLE_RESTRICTED,
    MEMBERSHIP_TYPE_RETIRED,
    MEMBERSHIP_TYPE_UNKNOWN_REFERENCE,
    VALIDATION_MUST_BE_ONE_OF,
    VALIDATION_REQUIRED,
    FieldError,
)
from sam.members.domain.field_resolver import (
    OVERLAY_GROUP,
    FieldOrigin,
    FunctionalGroup,
    ResolvedField,
    evaluate_show_when,
)
from sam.members.domain.field_resolver import (
    FieldConfig as ResolvedFieldConfig,
)
from sam.members.domain.fixed_fields import (
    MEMBER_NUMBER_FIELD_KEY,
    FieldType,
    FieldValidationError,
    roles_for_option,
    validate_fixed_fields,
    validate_member_number_format,
)
from sam.members.domain.tenant_hooks import HookName
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import (
    Member,
    Membership,
)

#: Sentinel distinguishing "field was not submitted at all" from an explicit ``None``/blank on
#: the public-application path. A missing field is simply not carried onto the record; a present
#: blank IS carried so the required-ness rules (task 2.4) can reject a blank required field.
_MISSING = object()


class WritesMixin:
    # ── Write path (design C1 write / C2 / C5 / C6 — task 5.2) ────────────────────────
    #
    # Orchestration only: validate (fixed fields + tenant validate_member hook) → derive the
    # member number via the hook on create (threading the atomic counter value in) → persist via
    # the repository (the SOLE DynamoDB touch-point + owner of uniqueness/atomicity). No ``if
    # tenant``, no boto3, no HTTP here (Property 5). Scope + verify-before-trust are enforced
    # BEFORE any persist. (The lifecycle engine was retired — see spec
    # ``retire-members-status-lifecycle-engine``; status is now a plain tenant-driven field edited
    # like any other field, so there is no transition branch here.)

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
        errors = self._collect_member_record_errors(
            tenant_id, record, partial=partial, caller_roles=caller_roles
        )
        if errors:
            raise MemberValidationError(errors)

    def _collect_member_record_errors(
        self,
        tenant_id: str,
        record: Member,
        *,
        partial: bool,
        caller_roles: Sequence[str] = (),
    ) -> dict[str, FieldError]:
        """Run the full authoritative validation chain, COLLECTING every error (never raising).

        The error-gathering core of :meth:`_validate_member_record` — factored out so a caller
        that must collect errors across MORE than this one chain (the public ``create_application``
        path, task 2.4, which also enforces the application-required overlay + the public-path
        identity tightening) can merge this chain's errors INTO one map and raise a SINGLE
        :class:`MemberValidationError` (R6.5: every problem at once, not one-at-a-time). The
        authenticated callers keep the raise-if-any behaviour through the thin wrapper above.
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

        # (2e) declarative FieldFormat validators (R7.4/R7.5): one generic step over resolved
        # fields carrying a `format`, gated by the field's own `show_when` — a hidden field is
        # neither required nor format-checked. Reusable: the public create_application validator
        # (task 2.4) calls the same step rather than duplicating the loop.
        self._validate_field_formats(config, record, errors)

        hook_errors = self._tenant_hooks.dispatch(
            HookName.VALIDATE_MEMBER, tenant_id, record
        )
        if isinstance(hook_errors, Mapping):
            # A tenant hook returns ``{dotted_key: english_reason}`` (it has no code vocabulary).
            # Wrap each into a FieldError under the generic ``validation.invalidFormat`` code so the
            # merged map is uniformly typed; the tenant string is preserved as the English detail.
            for k, v in hook_errors.items():
                errors[str(k)] = _as_field_error(v)

        return errors

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
            if (
                field.origin is not FieldOrigin.VARIABLE
                or not field.required
                or not field.visible
            ):
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

    #: The dotted keys the PUBLIC application path requires regardless of tenant/platform config
    #: (R6.1/R6.1a): a reply ``email`` (platform-OPTIONAL generally — tightened here, not in the
    #: fixed-field registry), plus the applicant's NAME (``last_name`` — the platform-required
    #: primary name key) and DATE OF BIRTH (``birth_date``). name+DOB anchor the possible-duplicate
    #: flag (R3a.5) and let staff recognise the applicant; tenant ``application_required`` config
    #: can never relax them (R4b.4). ``last_name`` is already platform-required so the fixed-field
    #: registry covers it — it is listed here so the public-path contract is explicit and robust to
    #: a tenant override, never a weakening.
    _APPLICATION_REQUIRED_IDENTITY_KEYS: tuple[str, ...] = (
        "personal.email",
        "personal.last_name",
        "personal.birth_date",
    )

    @staticmethod
    def _validate_application_required(
        config: ResolvedFieldConfig,
        record: Member,
        errors: dict[str, FieldError],
    ) -> None:
        """Enforce PUBLIC-form required-ness: application-required fields + identity (R6.6/R4b).

        The public ``create_application`` path (task 2.4) is the only caller. It closes the gap
        the authenticated chain leaves — ``_validate_member_record`` enforces platform-``required``
        (fixed + overlay) but knows nothing of the FORM-ONLY ``application_required`` tightening
        (R4b) nor the public-path identity rule (R6.1/R6.1a). This one step enforces both,
        COLLECTING a ``VALIDATION_REQUIRED`` :class:`FieldError` per offending field into the
        shared map (the caller raises ONE 422 — R6.5). It never DROPS an error, only adds, so it
        can only tighten.

        Rules:

        * **Application-required (R4b.2/R4b.3).** For every resolved field the tenant marked
          ``application_visible``, when it is ``application_required`` AND shown (its ``show_when``
          holds, R4b.5 — a hidden field is neither required nor validated) AND its submitted value
          is absent/blank → a required error. ``application_required`` can only ADD to the
          platform ``required`` the base chain already enforces (R4b.3: it may tighten an optional
          field but never relax a platform-required one — a platform-required field stays required
          regardless of the form flag).
        * **Identity (R6.1/R6.1a).** ``email`` / ``last_name`` / ``birth_date``
          (:data:`_APPLICATION_REQUIRED_IDENTITY_KEYS`) are required on the public path regardless
          of tenant config — a missing/blank value is a required error. (``email`` is platform-
          OPTIONAL generally; this is a public-path tightening, not a change to the registry.)

        ``tussenvoegsel`` (``personal.name_infix``) and any other shown-but-optional field (R4b.2)
        is NOT in either set, so a blank value is accepted — the whole point of the per-field flag.
        """

        def _is_blank(value: Any) -> bool:
            return value is None or (isinstance(value, str) and not value.strip())

        # (a) Per-field application-required overlay (R4b): a form-selected field marked
        # application_required, shown, with a blank value → required. show_when gating reuses the
        # same hidden-not-required rule as the rest of the chain (R4b.5).
        for field in config.fields:
            if not field.application_required:
                continue
            if not field.application_visible:
                continue  # only a field on the form can be application-required
            if not evaluate_show_when(field.show_when, record):
                continue  # hidden → neither required nor validated (R4b.5)
            dotted = field.dotted_key()
            if dotted in errors:
                continue  # the base chain already flagged it — don't double-record
            if _is_blank(WritesMixin._record_value(record, field)):
                errors[dotted] = FieldError(
                    code=VALIDATION_REQUIRED, detail="is required"
                )

        # (b) Public-path identity tightening (R6.1/R6.1a): email + name + DOB, always required
        # on the public path, tenant config may not relax (R4b.4).
        for dotted in WritesMixin._APPLICATION_REQUIRED_IDENTITY_KEYS:
            if dotted in errors:
                continue
            group, _, key = dotted.partition(".")
            bucket = record.get(group)
            value = bucket.get(key) if isinstance(bucket, Mapping) else None
            if _is_blank(value):
                errors[dotted] = FieldError(
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
    def _validate_field_formats(
        config: ResolvedFieldConfig,
        record: Member,
        errors: dict[str, FieldError],
    ) -> None:
        """Run each resolved field's declarative ``FieldFormat`` checker (R7.4/R7.5, seam c).

        ONE generic validation step over the resolved config: for every field that carries a
        ``format`` (``FieldFormat {checker, params}``), when the record's value is PRESENT and the
        field's ``show_when`` condition holds, look up the platform-defined checker in
        :data:`field_formats.REGISTRY` and merge any returned :class:`FieldError` into the shared
        ``{dotted_key: FieldError}`` map. The checker SET is platform-defined (a tenant attaches a
        KNOWN token, never code — R7.7); the attached token is pure data on the field.

        Gating rules (R7.4 — reuse the field's existing ``show_when``, not a condition on the
        format itself):

        * **Hidden field → skipped entirely.** A field whose ``show_when`` does NOT hold for this
          record is neither required nor format-checked (the mirror of the frontend not rendering
          it, and the same rule ``_drop_hidden_required_errors`` applies to required-ness). This is
          why the IBAN format only runs when incasso is the chosen payment method (R6.3).
        * **Absent value → skipped.** An absent/blank value is left to the required-ness rules
          (``validate_fixed_fields`` / ``_validate_required_overlay_fields``); the format checker
          only runs on a PRESENT value, so an optional, empty formatted field is not an error.

        Defensive: an unknown token degrades to ``None`` at config-read time (R7.3) and
        :func:`field_formats.get_checker` returns ``None`` for any token not in the registry, so a
        stray token is simply not enforced rather than crashing the write (R7.5). Checkers are pure
        and never raise on user input, so this step cannot turn a bad value into a 502.
        """
        for field in config.fields:
            fmt = field.format
            if fmt is None:
                continue
            # Hidden by `show_when` → neither required nor format-checked (R7.4).
            if not evaluate_show_when(field.show_when, record):
                continue
            value = WritesMixin._record_value(record, field)
            # Absent/blank → leave to required-ness; only a PRESENT value is format-checked.
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            checker = field_formats.get_checker(fmt.checker)
            if checker is None:
                continue  # unknown/stray token — not enforced, never crashes (R7.3/R7.5)
            error = checker(value, fmt.params)
            if error is not None:
                errors[field.dotted_key()] = error

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

    def _validate_membership_type_reference(
        self, tenant_id: str, record: Member
    ) -> None:
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

    def _apply_application_membership_type(
        self,
        config: ResolvedFieldConfig,
        record: dict[str, Any],
    ) -> None:
        """Apply the D21/R11 ``membership_type`` rule on the PUBLIC application path (task 2.3).

        The 0.3 decision has two halves, keyed on whether the tenant EXPOSES ``membership_type``
        on the form (a resolved field whose ``application_visible`` is true):

        * **Exposed (R11.2, R4a.3).** The applicant picked from the field's **application subset**
          (the public-safe membership types), the form pre-selecting the first option. The server
          trusts NEITHER the submitted value NOR the default: it re-validates the submitted value
          against the subset here (:func:`validate_application_choice` — the task 3.5 authority),
          raising a 422 ``errors`` entry for a value outside the subset EVEN IF it is a valid
          staff-facing choice. The live-catalog reference check (:meth:`_validate_membership_type_reference`,
          R11) remains the SEPARATE, authoritative half the caller runs after this — this step only
          adds the subset gate, it never weakens the catalog check.
        * **Not exposed (R11.3).** The applicant never supplies a type, so the record would be left
          with no ``membership_type`` and could not stay catalog-valid while ``status=application``.
          A **tenant-default** is stamped server-side: the tenant's FIRST active catalog entry
          (presentation-ordered — the same first-option semantics the exposed form pre-selects). The
          stamp happens ONLY when the field carries no value (a resend that already has one keeps it),
          and the live-catalog reference check the caller runs next still validates the stamped value,
          so a tenant with an empty catalog surfaces the normal unknown-reference 422 rather than a
          silently invalid record (R11.4 — the public path never persists a dangling type).

        This method NEVER relaxes :meth:`_validate_membership_type_reference`; it only adds the
        subset re-validation (exposed) and the default stamp (not exposed). Localized to the
        ``membership_type`` concern so it composes cleanly with the other create_application steps.
        """
        field = config.field(MEMBERSHIP_TYPE_FIELD_KEY)
        exposed = field is not None and field.application_visible

        membership = dict(record.get("membership") or {})
        submitted = membership.get("membership_type")
        is_blank = submitted is None or (
            isinstance(submitted, str) and not submitted.strip()
        )

        if exposed:
            # R4a.3: re-validate the SUBMITTED value against the application subset (not the full
            # staff set). A blank is left to required-ness (membership_type is application-required
            # when exposed, D21 — enforced on the shared validate chain); only a PRESENT value is
            # subset-gated here. The live-catalog check (R11) runs separately in the caller.
            if not is_blank:
                error = self._membership_type_subset_error(field, submitted)
                if error is not None:
                    raise MemberValidationError({MEMBERSHIP_TYPE_FIELD_KEY: error})
            return

        # Not exposed (R11.3): stamp the tenant-default so the record stays catalog-valid. Only
        # when absent/blank — a value that rode in on an unselected field was already dropped by
        # the application field gate, so in practice this is always blank here; the guard keeps a
        # resend's prior value intact regardless.
        if is_blank:
            default_code = self._default_membership_type(record["tenant_id"])
            if default_code is not None:
                membership["membership_type"] = default_code
                record["membership"] = membership

    @staticmethod
    def _membership_type_subset_error(
        field: ResolvedField, submitted: Any
    ) -> FieldError | None:
        """Re-validate a submitted ``membership_type`` against its application subset (R4a.3).

        Reuses the task 3.5 authority :func:`validate_application_choice` for the ENUM case, and
        ALSO gates ``membership_type`` — a ``REFERENCE`` field whose public-safe choices are the
        live catalog, not a static enum (R4a.5). When the field declares an ``application_choices``
        subset (the public-safe type codes), a submitted value OUTSIDE that subset is rejected with
        the same ``must be one of`` field error EVEN IF it is a valid staff-facing catalog type —
        the public path must not let a hand-crafted request pick a type the tenant withheld from the
        form. When NO subset is declared the full set is offered (back-compatible, R4a.2) and only
        the live-catalog reference check (R11, run by the caller) applies.
        """
        # ENUM fields (overlay enums, fixed enums) go through the shared authority unchanged.
        enum_error = validate_application_choice(field, submitted)
        if enum_error is not None:
            return enum_error

        # membership_type is a REFERENCE field: the subset is the declared public-safe type codes,
        # re-validated here (the ENUM-gated authority above is a no-op for a REFERENCE field).
        subset = field.application_choices
        if subset is None:
            return None  # no subset → full catalog offered; the R11 reference check governs
        if str(submitted) not in {str(v) for v in subset}:
            allowed = [str(v) for v in subset]
            return FieldError(
                code=VALIDATION_MUST_BE_ONE_OF,
                detail=f"must be one of: {', '.join(allowed)}",
                params={"allowed": allowed},
            )
        return None

    def _default_membership_type(self, tenant_id: str) -> str | None:
        """The tenant-default ``membership_type`` to stamp when the form does not expose it (R11.3).

        The tenant-default is the FIRST active catalog entry in presentation order — the same
        "first option" the exposed form pre-selects (D21), and a live, assignable type by
        construction (``active_only=True``), so the stamped value passes
        :meth:`_validate_membership_type_reference`. Returns ``None`` for a tenant whose catalog is
        empty; the caller then lets the reference check surface the normal unknown-reference 422
        rather than persisting a dangling type (R11.4).
        """
        entries = self._repo.list_membership_types(tenant_id, active_only=True)
        for entry in entries:
            return str(entry.type_code)
        return None

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
        stamp the authoritative ``tenant_id`` → default ``membership.status`` to the plain
        literal ``"application"`` when the body carries none (R3.1; the lifecycle engine was
        retired, so status is an ordinary tenant-driven field) → validate (fixed fields +
        tenant ``validate_member``) → authorize the write against the caller's scope → persist
        via ``save_member`` (a single ``PutItem``).

        s5k: ``member_number`` is a plain OPTIONAL string supplied by the caller/import — there is
        NO auto-generation and NO member-number uniqueness guard. A duplicate number is a
        data-quality concern, not a write-time conflict.
        """
        record = self._sanitize_write_payload(body)
        record["tenant_id"] = (
            tenant_id  # authoritative — verify-before-trust (Property 2)
        )

        # member_id is an OPAQUE INTERNAL identity generated by the SYSTEM — a uuid4, ALWAYS minted
        # here on create (any client-supplied member_id was already stripped by the sanitizer,
        # verify-before-trust). It is never the human Lidnummer (`member_number`, just a field) and
        # never client-controlled (s5k R1). Without it the repository's save_member rejects the
        # record (a 502 on create). The h-dcn backfill mints its own uuid4 the same way.
        record["member_id"] = str(uuid.uuid4())

        membership = dict(record.get("membership") or {})

        # Default the initial status to the plain literal "application" when the body sets none
        # (R3.1). The lifecycle engine was retired — status is now an ordinary tenant-driven
        # field, so there is no initial_state to read from a LifecycleConfig.
        if not membership.get("status"):
            membership["status"] = "application"

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

    # ── Public-application create (application-app task 2.2; R3, R3a, R4.7/R4.8, R3.5) ──

    #: Privileged keys a PUBLIC applicant may NEVER set on a member record — stripped on top of
    #: the base sanitizer (``tenant_id`` / ``PK`` / ``member_id``) before processing (R4.7/R4.8,
    #: verify-before-trust). ``status`` is forced to ``application`` server-side (R3.1) so a body
    #: status is dropped; ``member_number`` / ``created_at`` / ``updated_at`` are staff-owned
    #: (R4.3). These live under the ``membership`` bucket; the create spine never trusts them.
    _APPLICATION_PRIVILEGED_MEMBERSHIP_KEYS: frozenset[str] = frozenset(
        {"status", "member_number", "created_at", "updated_at"}
    )

    #: Stable keyword appended to ``overlay.additional_info`` when the public applicant's
    #: normalized name+DOB matches an EXISTING member (R3a.5/D25). The existing leftover-info
    #: free-text field carries it as a keyworded entry (NO new flag column, per design) so the
    #: applications inbox can keyword-filter it via the Table Filter Framework v2 (R8b.5). The
    #: flag NEVER blocks the write and NEVER changes the applicant-facing 202 (R3a.7).
    _DUP_KEYWORD: str = "DUP"
    _OVERLAY_ADDITIONAL_INFO_KEY: str = "additional_info"

    #: The top-level member-record attribute the consent stamp is stored under (D26/R12.1a).
    #: A structured ``{version, accepted_at, locale}`` object — member data, not a log (R12.3
    #: does not forbid storing it, R12.1b) — a flat sibling of ``locale`` / ``status``, read
    #: back with one top-level lookup. Shape fixed in design §4 Data Models.
    _CONSENT_RECORD_KEY: str = "consent"

    #: The SYNTHETIC field key a missing-affirmative-consent 422 is reported under (F4/R12.1).
    #: There is no real ``consent`` form field in the field-config; the consent checkbox is a
    #: frontend-rendered affirmative gate (R10a.5), so a reject surfaces on this stable synthetic
    #: dotted key the SPA maps back to the checkbox — distinct from any resolved field.
    _CONSENT_FIELD_KEY: str = "consent"

    def create_application(
        self,
        tenant_id: str,
        body: Mapping[str, Any],
        session_key: str,
        locale: str | None = None,
        consent: Mapping[str, Any] | None = None,
    ) -> Member:
        """Land a PUBLIC applicant's submission as a ``status=application`` member (seam b).

        The CORE public-intake write. It lives beside :meth:`create_member` and REUSES its proven
        spine — the public path is trusted for NOTHING (R3, Property 2):

        1. **Field gate + un-flatten (R3.4/R4.7/R4.8).** Accept ONLY fields the tenant has
           **application-selected** (a resolved field whose ``application_visible`` is true); every
           other submitted key — an unselected ``membership`` field, a staff-only field, an unknown
           key — is IGNORED. The accepted flat values (keyed by each field's ``dotted_key()``) are
           un-flattened back into the nested ``{personal, membership, overlay}`` shape the create
           spine expects (the overview field model, used in reverse).
        2. **Strip privileged fields + force status (R3.1/R4.7/R4.8).** The base sanitizer drops
           ``tenant_id`` / ``member_id``; this additionally drops the staff-owned ``membership``
           keys (``status`` / ``member_number`` / ``created_at`` / ``updated_at``) and then FORCES
           ``membership.status = application`` regardless of anything the client sent — a public
           caller can never escalate a record's state or identity.
        3. **Session de-dup (R3a.1–R3a.3).** Mint a server-side ``member_id`` and CLAIM the session
           via :meth:`claim_application_session` (a conditional ``attribute_not_exists`` put, task
           2.1). The FIRST submit of a session wins the claim → CREATE. A same-session resend (the
           applicant corrected fields and resent, or a double-click race) loses the claim → resolve
           the already-mapped ``member_id`` via :meth:`get_application_session_member` and UPDATE
           that SAME record, preserving its ``member_id`` and ``status=application`` (R3a.2).
        4. **Reuse the create spine (R3.5).** ``_validate_member_record`` (fixed fields + overlay
           gates + ``member_number`` format + the generic ``FieldFormat`` step from 3.4) →
           ``_validate_membership_type_reference`` (R11) → ``_reject_invalid_overlay_enum_values``
           → ``save_member``. One write path, not a second.

        **Consent (D26/F4/R12.1–R12.1c, task 2.6).** ``consent`` carries the applicant's
        affirmative acceptance of the tenant's versioned notice. :meth:`_stamp_application_consent`
        REQUIRES explicit affirmative consent — a submit without it is a HARD 422 reject (no record
        written) — and on acceptance stamps a SERVER-AUTHORITATIVE
        ``consent{version, accepted_at, locale}``: the version is the tenant's CURRENT notice
        version resolved server-side (never the client ``notice_version``, R12.1a), the timestamp
        is server UTC (client timestamp ignored, R12.1b), and the locale is the normalized
        applicant locale (R12.1a). ``locale`` is stamped onto the record as task 5.1's seam
        (authoritative normalization/fallback owned by ``applicant_locale``).

        Scope seams deferred to later tasks (left intentionally un-built): the required-ness 422
        collection (2.4) rides the SAME ``_validate_member_record`` chain this calls; the
        membership_type default stamp (2.3) and duplicate flag (2.5) hang off this method. No
        ``allowed_scopes`` / ``caller_roles``: a public
        applicant has NO verified authority, so the scope/role gates ``create_member`` applies do
        NOT run here — the tenant is authoritative from the resolved slug (R2), and the record is
        a self-submitted ``application`` the staff review gate (approval) governs downstream.
        """
        config = self._field_resolver.resolve(
            tenant_id, scope_vocab=self._scope_vocab(tenant_id)
        )

        # (1) Field gate + un-flatten: keep ONLY application-selected fields, nest by dotted key.
        record = self._application_selected_record(config, body)

        # (3a) Resolve the session → CREATE vs UPDATE. Mint a candidate member_id for a fresh
        # session; the claim is conditional so a race resolves to a single record (R3a.3).
        candidate_member_id = str(uuid.uuid4())
        claimed = self._repo.claim_application_session(
            tenant_id, session_key, candidate_member_id
        )
        if claimed:
            member_id = candidate_member_id
            existing: Member | None = None
        else:
            # A same-session resend: resolve the record this session already created and UPDATE it
            # (preserve its member_id + status=application), rather than inserting a second record.
            member_id = self._repo.get_application_session_member(
                tenant_id, session_key
            )
            if member_id is None:
                # The marker exists but maps to nothing resolvable — fall back to the candidate so
                # the submission is never silently lost (defensive; the claim path owns the id).
                member_id = candidate_member_id
                existing = None
            else:
                existing = self._repo.get_member(tenant_id, member_id)

        # (3b) For a resend, merge the new values OVER the existing record so the applicant's
        # correction wins while prior fields survive (the overview update semantics, in reverse).
        if existing is not None:
            record = self._deep_merge(dict(existing), record)

        # (2) Authoritative identity + tenant stamp (verify-before-trust, Property 2).
        record["tenant_id"] = tenant_id
        record["member_id"] = member_id

        # (2) Force status=application + strip staff-owned membership keys (R3.1/R4.7/R4.8). Done
        # AFTER the merge so a resend can never smuggle a status/member_number through either.
        membership = dict(record.get("membership") or {})
        for privileged in self._APPLICATION_PRIVILEGED_MEMBERSHIP_KEYS:
            membership.pop(privileged, None)
        membership["status"] = (
            "application"  # forced default, never client-trusted (R3.1)
        )

        # Server-stamped spine fields so the `status=application` record is catalog/spine-valid
        # WITHOUT asking the applicant for staff-owned data (R3.5 — the record must pass the same
        # create spine). `joined_date` is a platform-REQUIRED fixed field, but a prospective member
        # has not "joined" — membership begins once staff approve the applicant and move them to
        # an active status, not at submission. So the application date (server UTC today) is
        # stamped as the provisional joined_date: it keeps the record valid and reflects when the
        # person applied, and staff set the real join date on approval. This does NOT relax a
        # platform invariant (the field stays required and present) — it is the same
        # server-authoritative stamp the default `status="application"` is, mirroring
        # `create_member`'s initial-status default. Only stamped when ABSENT so a resend's prior
        # value survives.
        if not membership.get("joined_date"):
            membership["joined_date"] = datetime.now(timezone.utc).date().isoformat()
        record["membership"] = membership

        # membership_type D21/R11 (task 2.3): when the tenant EXPOSES membership_type on the form,
        # re-validate the submitted value against the application subset (R4a.3 — never trust the
        # form default); when it does NOT, stamp the tenant-default so the record stays
        # catalog-valid (R11.3). This NEVER weakens the live-catalog reference check below (R11),
        # which stays the authoritative half and runs on the effective value regardless.
        self._apply_application_membership_type(config, record)

        # Applicant locale (task 5.1/5.2, R6b.4/R14.14): persist the applicant locale onto the
        # record via the single-source `applicant_locale` contract. `locale_record_patch` NORMALIZES
        # before stamping, so an unsupported / wrong-case / blank value is stored as the supported
        # fallback (`nl`) — never the raw client value. This is what a later staff reply, re-send,
        # or confirmation re-render reads back (via `locale_of_record`), so the stored top-level
        # `locale` is ALWAYS `nl`/`en`, mirroring the normalized `consent.locale` stamp. Always
        # stamped (default+fallback `nl` even when the applicant sent nothing) so every application
        # record carries an authoritative locale.
        record.update(locale_record_patch(locale))

        # Consent stamp + affirmative-consent reject (D26/F4/R12.1–R12.1c, task 2.6). REQUIRE the
        # applicant's explicit affirmative consent — a submit without it is a HARD 422 reject (one
        # of the few on the public path, unlike the neutral-202 dup flag). On acceptance, persist a
        # SERVER-AUTHORITATIVE consent record: the tenant's CURRENT notice version (resolved
        # server-side, never the client-supplied notice_version — R12.1a), a server-UTC acceptance
        # timestamp (client timestamp IGNORED — R12.1b), and the applicant's NORMALIZED locale
        # (R12.1a, reusing task 5.1's `normalize_locale`). Done BEFORE the create spine so a
        # rejected submit never reaches `save_member` (no record written, R12.1).
        self._stamp_application_consent(tenant_id, record, consent, locale)

        # (4) Reuse the create spine — the public path adds no second validation route (R3.5) —
        # but COLLECT every error into ONE map so the applicant sees all problems at once (R6.5),
        # rather than failing on the first chain that raises. Required-ness is enforced for ALL
        # required fields (platform + application-required) + the public-path identity fields,
        # email is required+valid, IBAN is mod-97'd WHEN incasso is shown (the FieldFormat step,
        # gated by show_when) — all merged into the single 422 `errors[]` (R6/R6.6, task 2.4).
        errors: dict[str, FieldError] = self._collect_member_record_errors(
            tenant_id, record, partial=False, caller_roles=()
        )
        # Public-form required-ness: application-required overlay (R4b) + identity (R6.1/R6.1a).
        self._validate_application_required(config, record, errors)
        # The live-catalog membership_type reference check (R11): collect its error rather than
        # letting it raise on its own, so a bad type rides in the SAME 422 as any field error.
        try:
            self._validate_membership_type_reference(tenant_id, record)
        except MemberValidationError as exc:
            for k, v in exc.errors.items():
                errors.setdefault(k, v)
        # A.5: overlay enum dropdowns against their `choices` (every present value, create path).
        self._reject_invalid_overlay_enum_values(config, record, errors)
        if errors:
            raise MemberValidationError(errors)

        # (5) Duplicate flag (R3a.5–R3a.8 / D25): FLAG-ONLY, never blocks. If the applicant's
        # normalized name+DOB matches an EXISTING member (via the cheap GSI read), append a
        # `DUP` keyword note to overlay.additional_info for staff review — done BEFORE the write
        # so the note persists in the SAME single PutItem, and localized so a lookup failure can
        # never fail the applicant's submission (the 202 is unchanged either way, R3a.7).
        self._flag_possible_duplicate(tenant_id, record, member_id)

        return self._repo.save_member(tenant_id, record)

    def _stamp_application_consent(
        self,
        tenant_id: str,
        record: dict[str, Any],
        consent: Mapping[str, Any] | None,
        locale: Any,
    ) -> None:
        """Require affirmative consent + stamp the server-authoritative consent record (task 2.6).

        The GDPR consent contract of the public intake (Member Application Form D26/F4/R12.1–
        R12.1c). Two responsibilities, in order:

        1. **Require affirmative consent (F4/R12.1).** A submit WITHOUT the applicant's explicit,
           affirmative consent is REJECTED — a :class:`MemberValidationError` (R1a 422) on the
           synthetic :data:`_CONSENT_FIELD_KEY`. This is one of the few HARD rejects on the public
           path (unlike the neutral-202 duplicate flag): the applicant must affirmatively accept
           the notice, so a missing / falsy / malformed ``consent`` block never writes a record.
           Affirmativeness is read from the client's ``consent.accepted`` boolean
           (:meth:`_consent_is_affirmative`) — the ONLY thing trusted from the client-supplied
           consent block; everything recorded below is server-authoritative.

        2. **Stamp the server-authoritative consent record (R12.1a/R12.1b/R12.1c).** On
           acceptance, persist ``consent{version, accepted_at, locale}`` under
           :data:`_CONSENT_RECORD_KEY`:

           - ``version`` — the TENANT's CURRENT notice version, resolved SERVER-SIDE via the
             consent-notice seam (``self._consent_notice_provider.get_consent_notice_version``),
             NEVER the client-supplied ``notice_version`` (R12.1a). So a later notice revision
             never retroactively changes an existing record's recorded version — the record pins
             the exact version in force at acceptance. A tenant with no authored notice resolves
             to ``None`` (empty-is-valid, R12.1c): the affirmative consent is still recorded, with
             no version to pin.
           - ``accepted_at`` — a SERVER-minted UTC ISO-8601 timestamp (``datetime.now(timezone.utc)``),
             like ``created_at``; any client-supplied ``accepted_at`` / timestamp is IGNORED
             (R12.1b, verify-before-trust).
           - ``locale`` — the applicant's NORMALIZED locale (``nl``/``en``, default+fallback
             ``nl``) via task 5.1's :func:`normalize_locale`, recording which wording LANGUAGE was
             shown (R12.1a). Taken from the ``locale`` the handler resolved for the submission.

        Called BEFORE the create spine in :meth:`create_application`, so a reject raises before any
        ``save_member`` — a submit without affirmative consent leaves NO record (R12.1).
        """
        if not self._consent_is_affirmative(consent):
            raise MemberValidationError(
                {
                    self._CONSENT_FIELD_KEY: FieldError(
                        code=CONSENT_REQUIRED,
                        detail=(
                            "explicit affirmative consent to the privacy/consent notice is "
                            "required to submit this application"
                        ),
                    )
                }
            )

        # Server-authoritative stamp — NOTHING here is trusted from the client (R12.1a/R12.1b):
        # the version is resolved server-side from the tenant's projected notice, the timestamp is
        # minted here, and the locale is the normalized applicant locale.
        record[self._CONSENT_RECORD_KEY] = {
            "version": self._consent_notice_provider.get_consent_notice_version(
                tenant_id
            ),
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "locale": normalize_locale(locale),
        }

    @staticmethod
    def _consent_is_affirmative(consent: Mapping[str, Any] | None) -> bool:
        """Return whether the client supplied EXPLICIT affirmative consent (F4/R12.1).

        True ONLY when ``consent`` is a mapping whose ``accepted`` is the boolean ``True`` — the
        non-pre-ticked affirmative checkbox the form sends as ``consent:{accepted:true, …}``
        (design §3.2). A missing block, a non-mapping, a missing ``accepted``, or any non-``True``
        value (``False`` / ``"true"`` / ``1`` / ``None``) is NOT affirmative — the single thing
        trusted from the client-supplied consent block, and trusted strictly (fail-closed), so a
        hand-crafted or absent consent never satisfies the gate. The RECORDED version/timestamp/
        locale are all server-authoritative (see :meth:`_stamp_application_consent`).
        """
        if not isinstance(consent, Mapping):
            return False
        return consent.get("accepted") is True

    def _flag_possible_duplicate(
        self, tenant_id: str, record: dict[str, Any], member_id: str
    ) -> None:
        """Append a `DUP` note to ``overlay.additional_info`` on a name+DOB match (D25).

        FLAG-ONLY (R3a.5): queries the ``name_dob_index`` GSI for the applicant's normalized
        name+DOB and, if ANY OTHER member of the tenant matches (the record's own id is excluded
        so a same-session resubmit never flags itself), appends the stable `DUP` keyword to the
        existing leftover-info free-text field. It NEVER raises — a lookup error is swallowed so
        the submission's neutral 202 is never affected (R3a.7) — and NEVER blocks the write
        (R3a.5). Idempotent: the keyword is appended only when not already present, so a resend
        does not accumulate duplicate markers.
        """
        try:
            personal = record.get("personal")
            if not isinstance(personal, Mapping):
                return
            name_dob_key = td.normalize_name_dob_key(
                personal.get("first_name"),
                personal.get("name_infix"),
                personal.get("last_name"),
                personal.get("birth_date"),
            )
            if name_dob_key is None:
                return  # missing name or DOB → un-indexable → nothing to match (R6.1a)
            matches = self._repo.query_by_name_dob(tenant_id, name_dob_key)
            has_other_match = any(
                str(m.get("member_id")) != str(member_id) for m in (matches or [])
            )
            if has_other_match:
                self._append_additional_info_keyword(record, self._DUP_KEYWORD)
        except Exception:
            # Flag-only: a duplicate-lookup failure must never fail the applicant's submission
            # or change the response (R3a.7). Swallow and proceed — the record still lands.
            return

    def _append_additional_info_keyword(
        self, record: dict[str, Any], keyword: str
    ) -> None:
        """Append a keyword to ``overlay.additional_info`` (space-separated), idempotently.

        No new flag column (design): the signal rides the existing ``overlay.additional_info``
        leftover-info free-text field as a space-separated keyword entry, keyword-filterable by
        the applications inbox (R8b.5). Appending (not replacing) preserves any existing note; a
        keyword already present is not re-added so a resend never accumulates duplicates.
        """
        overlay = record.get(OVERLAY_GROUP)
        if not isinstance(overlay, dict):
            overlay = dict(overlay) if isinstance(overlay, Mapping) else {}
            record[OVERLAY_GROUP] = overlay
        existing = overlay.get(self._OVERLAY_ADDITIONAL_INFO_KEY)
        existing_text = str(existing).strip() if existing not in (None, "") else ""
        if keyword in existing_text.split():
            return  # already flagged — idempotent (a resubmit must not double-append)
        overlay[self._OVERLAY_ADDITIONAL_INFO_KEY] = (
            f"{existing_text} {keyword}".strip() if existing_text else keyword
        )

    def _application_selected_record(
        self,
        config: ResolvedFieldConfig,
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Un-flatten a public submission to the nested member shape, keeping ONLY form fields.

        The server accepts ONLY fields the tenant has **application-selected** — a resolved field
        whose ``application_visible`` is true (R3.4/R4.8). Every other submitted key is IGNORED, so
        an unselected ``membership`` field, a staff-only field, or an unknown key posted by a
        hand-crafted request simply does not land on the record (verify-before-trust).

        Input shape tolerance: a public form posts the values FLAT, keyed by each field's
        ``dotted_key()`` (``{"personal.first_name": "Sam", ...}`` — design §3.2), optionally wrapped
        in a ``fields`` sub-object. This also tolerates the already-nested
        ``{personal:{...}, membership:{...}, overlay:{...}}`` shape (so a direct domain caller /
        test need not pre-flatten). Each accepted value is placed under its field's STORAGE group
        (``personal`` / ``membership`` / ``overlay``), i.e. the create spine's nested shape (R4.7).
        """
        # The form may nest the field values under a `fields` key (design §3.2) or send them at
        # the top level; accept either. Buckets passed at the top level are also read so a nested
        # submission works without a `fields` wrapper.
        flat_source = (
            body.get("fields") if isinstance(body.get("fields"), Mapping) else body
        )

        record: dict[str, Any] = {}
        for field_obj in config.fields:
            if not field_obj.application_visible:
                continue  # not application-selected → never accepted (R3.4/R4.8)
            dotted = field_obj.dotted_key()
            value = self._lookup_submitted_value(flat_source, field_obj)
            if value is _MISSING:
                continue
            group, _, key = dotted.partition(".")
            record.setdefault(group, {})[key] = value
        return record

    @staticmethod
    def _lookup_submitted_value(
        source: Mapping[str, Any], field_obj: ResolvedField
    ) -> Any:
        """Find a resolved field's submitted value in a (flat or nested) source, else ``_MISSING``.

        Looks up, in order: the FLAT dotted key (``personal.first_name``), the nested bucket
        (``source["personal"]["first_name"]``), then a bare top-level key (``first_name``). Returns
        the sentinel :data:`_MISSING` when the field was not submitted at all — distinct from an
        explicit ``None``/blank, which IS carried through so the required-ness rules (task 2.4) can
        reject a blank required field rather than treating it as absent.
        """
        dotted = field_obj.dotted_key()
        if dotted in source:
            return source[dotted]
        bucket = source.get(field_obj.group)
        if isinstance(bucket, Mapping) and field_obj.key in bucket:
            return bucket[field_obj.key]
        if field_obj.key in source:
            return source[field_obj.key]
        return _MISSING

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
        return {
            "member_id": member_id,
            "invitation": invitation,
            "delegates": list(stored),
        }

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

        fields = [self._serialize_field(f, options=options) for f in config.fields]
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
            # The tenant-level default rows-per-page (Phase 2 step (a) — the former
            # `view_contexts.page_size` re-home, R2.1/R1.2). Sourced from the injected
            # DefaultPageSizeProvider (the projection reader's `config#fields`
            # `default_page_size` scalar in production, a StaticDefaultPageSizeProvider in
            # tests), keyed by the verified tenant_id. After Phase 2 step (c) the `view_contexts`
            # array is gone (the SPA stopped reading it in step (b)); `default_page_size` is now
            # the sole pagination home the module serves. The new SPA resolves pagination as
            # `userPreference ?? default_page_size ?? platformDefault`. Empty-is-valid (R2.4): a
            # tenant that authored no default surfaces `None` here — the renderer then applies the
            # per-user preference and finally the platform table-toolkit default (today's
            # behaviour when a `view_context.page_size` was null). Presentation-only: the module
            # serves it, enforces nothing off it (mirrors `mail_enabled`).
            "default_page_size": self._default_page_size_provider.get_default_page_size(
                tenant_id
            ),
            # The tenant's mail-enabled gate flag (pivot-output-actions R0/R1 task 1.3, design
            # §6.3). Sourced from the injected MailGateProvider — in production the projection
            # reader's `config#mail` row (the per-tenant "mail-enabled / SES-certified"
            # onboarding gate the tenant-admin module writes to MySQL `parameters` and projects
            # one-directionally; a Lambda NEVER queries MySQL for it, ADR 0005/0006), a
            # StaticMailGateProvider in tests. FAIL-CLOSED (R0): `False` when no provider is
            # wired, the row is absent, or the flag is not explicitly projected `True`. The SPA
            # reads it to decide whether to OFFER the mail output actions (R1–R5) — the Mail
            # compose action / send path is only offered when `mail_enabled` is true; otherwise
            # the action is hidden with the shared degradation reason (mirrors how `canExport`
            # gates the result-actions slot). Presentation-only: the module serves it; the
            # worker/send path re-checks the gate server-side regardless (design §9).
            "mail_enabled": self._mail_gate_provider.is_mail_enabled(tenant_id),
            # The AUTHORITATIVE config#mail body for the typed Mail authoring form (spec 02 task
            # 7.1 fix). Sourced from the injected MailConfigProvider — in production the projection
            # reader's config#mail row (get_mail_config), a StaticMailConfigProvider in tests. The
            # typed Mail function (MembersMailConfigEditor) LOADS its initial values from this so it
            # reads the SAME source it writes (PUT /members/config/mail) — NOT the legacy MySQL
            # members.* params, which are SAM-owned/retired now (a saved mail_reply_to_default,
            # SAM-only net-new, would read back blank from MySQL). Reader-shaped body: mail_enabled
            # / mail_local_part / mail_certified always present; mail_domain / mail_reply_to_default
            # / consent_notice only when authored. Empty-is-valid / fail-closed (a missing row →
            # the safe minimal body). Presentation-only: the module serves it; the write path and
            # the pivot `mail_enabled` gate enforce server-side regardless.
            "mail_config": self._mail_config_provider.get_mail_config(tenant_id),
            # The DELIVERED/LOADED status of this tenant's projected config#* rows (Phase 0
            # step 3, impact-analysis §2 / risk #6). A map {config_id: version|None} sourced
            # from the injected ConfigStatusProvider — in production the projection reader's
            # per-row `version` (the monotonic value the one-directional write + the
            # version-bump-trap fix advance; a config PRESENT with a version is DELIVERED and
            # is what the module LOADS), a StaticConfigStatusProvider in tests. A `None` version
            # means that config has NEVER been projected for the tenant ("not yet delivered").
            # Presentation-only: the authoring UI compares each version to the source param's
            # own revision to render a delivered / stale / not-yet-delivered indicator; the
            # module enforces nothing off it (mirrors `mail_enabled`).
            # Empty-is-valid: an unconfigured tenant yields all-None, never a crash.
            "config_status": dict(
                self._config_status_provider.get_config_status(tenant_id)
            ),
            # The PLATFORM-DEFINED set of field-format checker tokens a tenant may attach to a
            # field's `format.checker` (spec 11 S4/R3.3, task 1.3). Served straight from the SAM
            # `field_formats` registry (`EMAIL`, `IBAN` today) so the Application Form Builder's
            # format dropdown is always in lockstep with the platform registry and never drifts
            # from a hand-maintained client-side mirror. Sorted for a stable, deterministic order
            # (the registry itself is an unordered set). Presentation-only: the module serves it;
            # the config-write path is the authoritative gate that a `format.checker` is a known
            # token (R8.1b) — the frontend dropdown is convenience, never the only guard.
            "field_format_tokens": sorted(field_formats.known_tokens()),
        }

    # ── Public application-form field config (seam a/c — task 4.1, R5.1–R5.3) ─────────

    def get_public_field_config(self, tenant_id: str) -> dict[str, Any]:
        """Return the PUBLIC application form's field schema for ``tenant_id`` (R5.1–R5.3).

        The read side of the public intake (design §5 / §2.1 / seam a/c): the config-driven
        contract the public form (frontend Phase 9) fetches BEFORE submit so it can render without
        a hand-coded field list. It is the application-facing counterpart to
        :meth:`get_field_config` (the authenticated, full staff schema), but trusted for nothing
        and narrowed to exactly what an applicant may see:

        1. **Resolve the field set** via the SAME :class:`FieldResolver` (fixed base ⊕ per-tenant
           overlay), keyed by the verified ``tenant_id`` (never a client value) — scope-sourced
           enum choices honoured via :meth:`_scope_vocab`, exactly as the staff read.
        2. **Filter to the application-SELECTED fields (R5.1/R5.2).** ONLY fields the tenant marked
           ``application_visible`` are exposed; every unselected field — a staff-only field, an
           unselected ``membership`` field, or any internal attribute — is omitted, so the public
           schema can never leak a field the tenant did not put on the form.
        3. **Attach, per exposed field (R5.3),** what the renderer needs and NOTHING it needs to
           enforce (the server stays authoritative, R6.6): ``type``, i18n ``label{nl,en}``,
           ``functional_group``, ``order``, ``show_when`` (so a conditional field is only shown
           when its condition holds), the **application-required** flag as ``required`` (R4b.6 —
           the form's requiredness, NOT the staff ``required``), the enum **application SUBSET**
           as the field's ``choices`` (via :func:`application_subset_choices`, R4a.2 — a
           subsetted field exposes ONLY the public-safe values, back-compatibly the full set when
           none is declared), and the declarative ``format`` token (``{checker, params}``, R7.1)
           when the field carries one.

        The returned dict is the **200** body's ``data`` (design §3.1): ``fields`` (the ordered,
        filtered list), ``locales`` (the applicant locale selector's options, R6b — the renderer
        picks each label's language from the chosen locale, defaulting ``nl``), and ``notice``
        (the tenant's CURRENT versioned consent-notice version the form shows + the submit stamps,
        D26/R12.1a — resolved server-side via the consent-notice seam; ``None`` when the tenant
        authored none, empty-is-valid R12.1c).

        **Scope boundary (task 4.1):** this is the schema read only. The tenant-readiness GATE
        (D15/R5.4 — refuse with a neutral 409 when the tenant has no certified sender) is task 4.2
        and wraps this; the handler-layer HTTP shaping / slug resolution is the public edge
        (tasks 1.x). This method is the unit of work: the authoritative, filtered public schema.
        """
        config = self._field_resolver.resolve(
            tenant_id, scope_vocab=self._scope_vocab(tenant_id)
        )
        options = self._active_membership_type_options(tenant_id)

        fields = [
            self._serialize_public_field(f, options=options)
            for f in config.fields
            # R5.1/R5.2: expose ONLY application-selected fields — nothing the tenant did not
            # put on the public form (no staff-only / unselected field, no internal attribute).
            if f.application_visible
        ]

        return {
            "tenant_id": config.tenant_id,
            "fields": fields,
            # The applicant locale selector's options (R6b). The renderer selects each field's
            # label language from the applicant's chosen locale, defaulting to `nl` (R5.3/R6b.1).
            "locales": list(SUPPORTED_LOCALES),
            # The tenant's CURRENT versioned consent-notice version (D26/R12.1a). The form shows
            # the notice and the submit stamps THIS server-resolved version (never a client
            # value). `None` when the tenant authored no notice (empty-is-valid, R12.1c) — the
            # affirmative consent is still required + recorded by `create_application`. The notice
            # TEXT body + the readiness 409 are the Flask projection (8.2) / task 4.2 concern;
            # this surfaces the pinned version the form references.
            "notice": {
                "version": self._consent_notice_provider.get_consent_notice_version(
                    tenant_id
                )
            },
        }

    def _serialize_public_field(
        self,
        field: ResolvedField,
        *,
        options: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Project an application-SELECTED :class:`ResolvedField` to the PUBLIC schema (R5.3).

        The public, applicant-facing counterpart to :meth:`_serialize_field`: it carries ONLY what
        the renderer needs and deliberately OMITS the staff-only attributes (``visible`` /
        ``origin`` / ``provenance`` / ``scope`` / ``member_number_format``) so the public contract
        never leaks internal field state. Per R5.3 it emits:

        - ``key`` (the dotted key the form flattens/un-flattens by) / ``group`` (storage bucket) /
          ``type`` / i18n ``label{nl,en}`` / ``functional_group`` (the display section) / ``order``;
        - ``required`` — the **application-required** flag (R4b.6), the form's own requiredness,
          NOT the staff ``required`` (an applicant's required set is the tenant's form config);
        - ``show_when`` (R4.12) when present — so the form renders/validates a conditional field
          only when actually shown (mirrored authoritatively server-side);
        - ``options`` — the dropdown source with the enum **application SUBSET applied** (R4a.2):
          for ``membership_type`` the ACTIVE catalog entries, FILTERED to the declared subset; for
          any other enum the subsetted ``{value, label}`` options (or the bare subsetted value
          list); ``None`` for a non-choice field. Reuses :func:`application_subset_choices` so the
          public read and the submit validator (:func:`validate_application_choice`) agree on the
          exposed set (fail-loud on a subset ⊄ choices, R4a.4);
        - ``format`` — the declarative validator token ``{checker, params}`` (R7.1) when the field
          carries one, so the form can mirror the checker client-side (server authoritative).
        """
        payload: dict[str, Any] = {
            "key": field.key,
            "group": field.group,
            "type": field.type.value,
            # The PUBLIC-FORM requiredness (R4b.6) — the application-required flag, not the staff
            # `required`. A platform-required field is also application-required at enforcement
            # (R4b.3), but what the form marks is this flag; the server stays authoritative.
            "required": bool(field.application_required),
            "label": dict(field.label),
            "functional_group": field.functional_group or field.group,
            "order": int(field.order),
        }
        if field.show_when is not None:
            payload["show_when"] = dict(field.show_when)

        payload["options"] = self._public_field_options(field, options=options)

        if field.format is not None:
            # The declarative field validator token (R7.1): a `{checker, params}` the form mirrors
            # client-side. Pure data — the checker callable lives in the registry (field_formats),
            # the server remains the authoritative enforcer (task 3.4).
            payload["format"] = {
                "checker": field.format.checker,
                "params": dict(field.format.params),
            }
        return payload

    def _public_field_options(
        self,
        field: ResolvedField,
        *,
        options: Sequence[Mapping[str, Any]],
    ) -> list[Any] | None:
        """The exposed option list for an enum field, with the application SUBSET applied (R4a.2).

        Returns ``None`` for a non-choice field. For an enum:

        - ``membership_type`` (D2 — the first subset consumer): the ACTIVE catalog entries
          (``{value, label, order}``), FILTERED to the field's application subset so the public
          form offers ONLY the public-safe membership types (R4a.5). When no subset is declared,
          every active entry is offered (back-compatible, R4a.2).
        - any other enum with rich :class:`EnumOption`s: the ``{value, label}`` options filtered to
          the subset (the value-level ``roles`` gate is a STAFF concern and is deliberately dropped
          from the public contract).
        - any other enum with a bare choice list: the subsetted bare value list.

        The exposed set is computed by :func:`application_subset_choices` (the single subset
        authority shared with the submit validator, R4a.3) — fail-loud if a subset entry is not a
        valid choice of the field (R4a.4), so a broken subset surfaces here rather than exposing
        an off-list value.
        """
        if field.dotted_key() == MEMBERSHIP_TYPE_FIELD_KEY:
            # The ACTIVE catalog feed, narrowed to the declared public subset (R4a.5/D2).
            # membership_type is a REFERENCE field whose resolved "choices" are the live catalog
            # (not `field.choices`), so the subset is filtered against the catalog option values
            # here — NOT via `application_subset_choices` (which guards against `field.choices`).
            # Fail-loud (R4a.4): a declared subset entry that is not an active catalog value is a
            # config bug and raises `OverlayError`, mirroring the subset-⊆-choices discipline. No
            # subset → every active entry is offered (back-compatible default, R4a.2). The live
            # catalog + R11 reference check remain the authoritative submit-time gate.
            subset = field.application_choices
            if subset is None:
                return [dict(o) for o in options]
            catalog_values = {str(o.get("value")) for o in options}
            dangling = [v for v in subset if v not in catalog_values]
            if dangling:
                from sam.members.domain.field_resolver import OverlayError

                offenders = ", ".join(repr(v) for v in dangling)
                raise OverlayError(
                    {
                        field.dotted_key(): (
                            f"application_choices subset entr"
                            f"{'y' if len(dangling) == 1 else 'ies'} {offenders} "
                            f"not in the tenant's active membership-type catalog (R4a.4)"
                        )
                    }
                )
            allowed = set(subset)
            return [dict(o) for o in options if str(o.get("value")) in allowed]

        if field.type is not FieldType.ENUM:
            # A non-enum, non-reference field carries no option list.
            if field.options is None and field.choices is None:
                return None

        # The subset the public form exposes (full set when none declared). This re-runs the
        # subset ⊆ choices guard, so a broken subset is a fail-loud config error (R4a.4).
        allowed = set(application_subset_choices(field))

        if field.options is not None:
            # Rich enum options → public {value,label} (drop the staff-only `roles` gate),
            # filtered to the exposed subset.
            return [
                {"value": o.value, "label": dict(o.label)}
                for o in field.options
                if str(o.value) in allowed
            ]

        if field.choices is not None:
            # Bare value list → the subsetted (ordered) exposed values.
            return list(application_subset_choices(field))

        return None

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
