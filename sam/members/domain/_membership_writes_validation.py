"""Membership-service WRITE path — authoritative record VALIDATION (split from ``_membership_writes``).

Mixed into ``MembershipService`` via the composed ``WritesMixin`` (re-exported from
``_membership_writes``). Owns the authoritative server-side validation chain for a member
record: fixed + overlay required-ness, ``show_when`` hidden-not-required gating, value-level
enum role gating, overlay-enum ``choices`` gating, ``member_number`` format, the declarative
``FieldFormat`` step, and the ``membership_type`` catalog-reference check. Bodies moved verbatim.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sam.members.domain import field_formats
from sam.members.domain._membership_errors import (
    MEMBERSHIP_TYPE_FIELD_KEY,
    MemberValidationError,
    _as_field_error,
)
from sam.members.domain.error_codes import (
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
from sam.members.repository.members_repository import (
    Member,
)


class ValidationMixin:
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
            if _is_blank(ValidationMixin._record_value(record, field)):
                errors[dotted] = FieldError(
                    code=VALIDATION_REQUIRED, detail="is required"
                )

        # (b) Public-path identity tightening (R6.1/R6.1a): email + name + DOB, always required
        # on the public path, tenant config may not relax (R4b.4).
        for dotted in ValidationMixin._APPLICATION_REQUIRED_IDENTITY_KEYS:
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
            value = ValidationMixin._record_value(record, field)
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
            value = ValidationMixin._record_value(record, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if previous is not None:
                # UPDATE: only enforce when the value actually changed (tolerate legacy).
                if ValidationMixin._record_value(previous, field) == value:
                    continue
            # The resolver's contract is that `choices` is a bare value list, but a tenant's raw
            # overlay JSON can carry rich option objects ({"value","label"}) under `choices`
            # (instead of `options`); those flow through un-normalized. Coerce every choice to its
            # string value so the membership check + error join are robust to either shape and can
            # never raise (a malformed shape must surface as a 422, never a 502).
            allowed_values = [ValidationMixin._choice_value(c) for c in field.choices]
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
        value = ValidationMixin._record_value(record, field)
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
            value = ValidationMixin._record_value(record, field)
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

    def _resolved_membership_type_options(
        self, tenant_id: str
    ) -> Sequence[Any] | None:
        """The ``membership_type`` field's resolved ENUM options (03b BU-2, Req 3.2/3.2a/3.4a).

        The unified model (Req 3.1): a selectable field carries its OWN vocabulary as rich
        :class:`EnumOption`s, each with an ``allowed`` (retired/grandfather) flag. The reference
        check reads the ``membership_type`` field's options from the resolved config — NOT the
        separate ``membershiptype#<code>`` catalog — so "reference" is a feature on the field, not
        a distinct store. Returns the field's :attr:`options` (the rich option list) when present,
        else ``None`` (the field carries no inline vocabulary — see the transitional fallback in
        :meth:`_validate_membership_type_reference`).
        """
        config = self._field_resolver.resolve(
            tenant_id, scope_vocab=self._scope_vocab(tenant_id)
        )
        field = config.field(MEMBERSHIP_TYPE_FIELD_KEY)
        if field is None:
            return None
        return field.options

    def _validate_membership_type_reference(
        self, tenant_id: str, record: Member
    ) -> None:
        """Authoritatively validate the member's ``membership_type`` reference (03b BU-2, C8).

        The domain — never the frontend — is the authority for referential integrity (R2.4,
        Property 2): the React dropdown that lists a tenant's assignable types is convenience
        only, so a create/update MUST re-check the effective ``membership.membership_type``. Under
        the 03b unified enum model (Req 3.1) the reference check reads the ``membership_type``
        FIELD's OWN resolved options (``{value, label, allowed}``) rather than the separate
        ``membershiptype#<code>`` catalog — "reference" is a feature on the field:

        - the value must be one of the field's option ``value``s — an UNKNOWN value →
          :data:`MEMBERSHIP_TYPE_UNKNOWN_REFERENCE` (Req 3.2a: a record pointing at a removed
          option is read-stable but save-blocked until its value is changed to an existing one);
        - the matched option must be ``allowed:true`` — a RETIRED (``allowed:false``) option is
          not assignable to a new/changed record → :data:`MEMBERSHIP_TYPE_RETIRED` (Req 3.2,
          grandfather semantics: existing members keep the value, it just leaves the picker).

        **Transitional catalog fallback (03b migration safety, Req 6.4 — the EXPAND-before-reader
        gate).** This re-pointed reader ships BEFORE the migration folds the catalog into the
        field's options (Task 7). While the field carries NO inline options yet, it FALLS BACK to
        the legacy ``membershiptype#<code>`` catalog (existence + ``active``) so a deploy that
        lands before the fold cannot break member writes. The fallback is REMOVED in CONTRACT
        (Task 10.2) once the fold is verified and the catalog rows are retired.

        A missing ``membership_type`` is NOT rejected here — the fixed-field registry
        (:func:`validate_fixed_fields`) owns the "required" rule. This method only rejects a
        *present* value, merging its error into the caller's :class:`MemberValidationError`
        (a 422). It runs only on create/changed-value updates (the caller's ``_membership_type_of``
        compare, design C8) — never on reads — so an EXISTING member referencing a since-retired/
        removed value stays valid and updatable when the update does not change the value.
        """
        membership = record.get("membership")
        if not isinstance(membership, Mapping):
            return
        type_code = membership.get("membership_type")
        if type_code is None or (isinstance(type_code, str) and not type_code.strip()):
            # Absence/blank is the fixed-field registry's concern (required-ness), not ours.
            return
        code = str(type_code)

        options = self._resolved_membership_type_options(tenant_id)
        if not options:
            # Transitional fallback (Req 6.4): the field has no inline vocabulary yet (pre-fold),
            # so validate against the legacy catalog exactly as before. Removed in CONTRACT.
            self._validate_membership_type_reference_from_catalog(tenant_id, code)
            return

        matched = next((o for o in options if str(o.value) == code), None)
        if matched is None:
            raise MemberValidationError(
                {
                    MEMBERSHIP_TYPE_FIELD_KEY: FieldError(
                        code=MEMBERSHIP_TYPE_UNKNOWN_REFERENCE,
                        detail=(
                            f"unknown membership type {code!r} "
                            "(not one of the membership_type field's options)"
                        ),
                        params={"type_code": code},
                    )
                }
            )
        if not matched.allowed:
            raise MemberValidationError(
                {
                    MEMBERSHIP_TYPE_FIELD_KEY: FieldError(
                        code=MEMBERSHIP_TYPE_RETIRED,
                        detail=(
                            f"membership type {code!r} is retired (allowed=false) "
                            "and cannot be assigned to a new or updated member"
                        ),
                        params={"type_code": code},
                    )
                }
            )

    def _validate_membership_type_reference_from_catalog(
        self, tenant_id: str, code: str
    ) -> None:
        """Legacy catalog reference check — the transitional fallback (03b, removed in CONTRACT).

        The pre-03b behaviour: a present ``membership_type`` must reference a catalog entry that
        EXISTS for this tenant and is ACTIVE. Preserved verbatim so a deploy landing before the
        EXPAND fold (Task 7) — when the field still carries no inline options — keeps rejecting an
        unknown/retired type exactly as it did. :meth:`_validate_membership_type_reference` calls
        this ONLY while the field has no inline options; once the fold lands the field-option path
        governs and this fallback is deleted with the catalog (Task 10.2).
        """
        entry = self._repo.get_membership_type(tenant_id, code)
        if entry is None:
            raise MemberValidationError(
                {
                    MEMBERSHIP_TYPE_FIELD_KEY: FieldError(
                        code=MEMBERSHIP_TYPE_UNKNOWN_REFERENCE,
                        detail=(
                            f"unknown membership type {code!r} "
                            "(not in the tenant's Lidmaatschap Beheer catalog)"
                        ),
                        params={"type_code": code},
                    )
                }
            )
        if not entry.active:
            raise MemberValidationError(
                {
                    MEMBERSHIP_TYPE_FIELD_KEY: FieldError(
                        code=MEMBERSHIP_TYPE_RETIRED,
                        detail=(
                            f"membership type {code!r} is retired (active=false) "
                            "and cannot be assigned to a new or updated member"
                        ),
                        params={"type_code": code},
                    )
                }
            )
