"""Membership-service WRITE path — PUBLIC application intake (split from ``_membership_writes``).

Mixed into ``MembershipService`` via the composed ``WritesMixin`` (re-exported from
``_membership_writes``). Owns the public application-form create path: field gate + un-flatten,
``membership_type`` subset/default (D21/R11), the GDPR consent stamp, the possible-duplicate
flag, and the submission spine that reuses the authenticated validation chain. Bodies moved
verbatim; cross-mixin calls (``_collect_member_record_errors``, ``_validate_application_required``,
``_validate_membership_type_reference``, ``_reject_invalid_overlay_enum_values``, ``_deep_merge``)
resolve at runtime via the composed service class.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sam.members.domain._membership_errors import (
    MEMBERSHIP_TYPE_FIELD_KEY,
    MemberValidationError,
)
from sam.members.domain.applicant_locale import (
    locale_record_patch,
    normalize_locale,
)
from sam.members.domain.application_choices import (
    validate_application_choice,
)
from sam.members.domain.error_codes import (
    CONSENT_REQUIRED,
    VALIDATION_MUST_BE_ONE_OF,
    FieldError,
)
from sam.members.domain.field_resolver import (
    OVERLAY_GROUP,
    ResolvedField,
)
from sam.members.domain.field_resolver import (
    FieldConfig as ResolvedFieldConfig,
)
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import (
    Member,
)

#: Sentinel distinguishing "field was not submitted at all" from an explicit ``None``/blank on
#: the public-application path. A missing field is simply not carried onto the record; a present
#: blank IS carried so the required-ness rules (task 2.4) can reject a blank required field.
_MISSING = object()


class ApplicationWritesMixin:
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
