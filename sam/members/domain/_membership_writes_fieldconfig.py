"""Membership-service WRITE path — RESOLVED field-config surface (split from ``_membership_writes``).

Mixed into ``MembershipService`` via the composed ``WritesMixin`` (re-exported from
``_membership_writes``). Owns the resolved-view reads the presentation-only frontend consumes:
the authenticated staff field config, the public application-form schema, and their serialization
helpers + the scope-dimension vocabulary. Per steering 39 the RAW stored overlay shape is
deliberately never surfaced here — consumers get a resolved domain view. Bodies moved verbatim;
cross-mixin calls (``_serialize_field``, ``_serialize_catalog_option``) resolve at runtime via the
composed service class.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sam.members.domain import field_formats
from sam.members.domain._membership_errors import (
    MEMBERSHIP_TYPE_FIELD_KEY,
)
from sam.members.domain.applicant_locale import (
    SUPPORTED_LOCALES,
)
from sam.members.domain.field_resolver import (
    FunctionalGroup,
    ResolvedField,
)


class FieldConfigSurfaceMixin:
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
        scope_vocab = self._scope_vocab(tenant_id)
        config = self._field_resolver.resolve(tenant_id, scope_vocab=scope_vocab)
        options = self._active_membership_type_options(tenant_id)

        # ── The ONE selectable-vocabulary assembly seam (design C4 / F8) ──────────────
        # For EVERY field, resolve its canonical `options` from its INJECTED source here —
        # NOT per-kind inside each serializer. `_assemble_field_options` is the single
        # `assembleSelectableOptions` pass the design calls for: the pure `FieldResolver`
        # stays catalog/DB-free, and this read-assembly layer populates reference options
        # (from the injected active-catalog map) and scope options (from the injected
        # `scope_vocab`) uniformly alongside inline enum options. The serializers below
        # consume the ONE `options` this computed — they do not re-branch by kind.
        assembled = {
            f.dotted_key(): self._assemble_field_options(
                f, options=options, scope_vocab=scope_vocab
            )
            for f in config.fields
        }

        fields = [
            self._serialize_field(f, field_options=assembled[f.dotted_key()])
            for f in config.fields
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
            # NOTE (spec 03 task 5.3, steering 39 guard): the RAW stored `config#fields` overlay
            # (`fields` / `overrides` / `fixed_overrides` / `functional_groups`, dotted
            # `{group}.{key}` keys) is DELIBERATELY NOT surfaced here. The raw storage shape MUST
            # NOT cross the repository boundary into an API response (steering 39 / R2.3 / R3) —
            # serving `field_overlay` was the root cause of the partial-overlay-overwrites-full-
            # record drift (`.kiro/specs/Members/root-cause-analysis.md`): the frontend seeded a
            # whole overlay object and PUT it back whole. Under the Change-Op model (spec 03, C3)
            # the authoring editors seed from the Flat_View above (`fields` / `by_group` /
            # `functional_groups`, each resolved field carrying its four application attributes via
            # `_serialize_field`) and WRITE by domain identity (Change-Ops), never reconstructing a
            # storage key. The raw reader (`get_raw_fields_overlay`) remains an INTERNAL helper —
            # used only by the Change-Op CRUD service's validate-and-place step — and is never
            # exposed on the API/cross-boundary path.
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
        scope_vocab = self._scope_vocab(tenant_id)
        config = self._field_resolver.resolve(tenant_id, scope_vocab=scope_vocab)
        options = self._active_membership_type_options(tenant_id)

        fields = [
            self._serialize_public_field(
                f,
                # The SAME ONE `options` the read-assembly seam (design C4 / F8) populated for the
                # staff read — the public serializer consumes it and then applies the R3.2 subset
                # FILTER, so both reads resolve the same vocabulary from the same assembly point.
                field_options=self._assemble_field_options(
                    f, options=options, scope_vocab=scope_vocab
                ),
            )
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
        field_options: Sequence[Mapping[str, Any]] | None,
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
        - ``options`` — the ONE canonical vocabulary the read-assembly seam (design C4 / F8)
          populated (``field_options``) with the enum **application SUBSET FILTER applied**
          (R4a.2/R3.2): the subset narrows the seam's ``options`` down to the public-safe values
          for ANY selectable kind uniformly (``membership_type`` reference, scope, or inline
          enum) — ``None`` for a non-choice field. The subset FILTER is the only projection left;
          the per-kind branch and the ``field.choices`` fallback are retired (F10). Fail-loud if a
          subset entry is not in the seam's vocabulary (R4a.4);
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

        payload["options"] = self._public_field_options(
            field, field_options=field_options
        )

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
        field_options: Sequence[Mapping[str, Any]] | None,
    ) -> list[Any] | None:
        """The exposed public option list — the seam's ONE ``options`` with the SUBSET FILTER (R4a.2).

        Consumes ``field_options`` — the single canonical vocabulary the read-assembly seam
        (design C4 / F8, :meth:`_assemble_field_options`) populated from the field's declared
        source (active catalog for ``membership_type``, scope-dimension values for a scope-backed
        field, or the inline enum's rich options). This serializer NO LONGER branches by field
        kind and NO LONGER reads ``field.choices`` as a fallback vocabulary source (F10): it
        applies ONLY the R3.2 public-SUBSET FILTER — a legitimately different projection that
        narrows the seam's vocabulary down to the tenant's declared ``application_choices``.

        Returns ``None`` for a non-selectable field (no seam vocabulary). Otherwise returns the
        seam options narrowed to the subset, with the staff-only ``roles`` gate dropped from the
        public contract. When no subset is declared (``application_choices is None``) every option
        is offered (back-compatible default, R4a.2).

        Fail-loud (R4a.4): a declared subset entry that is NOT in the seam's vocabulary is a config
        bug and raises :class:`OverlayError` (caller-safe — keyed by the field's dotted key, no
        internal detail leaked), so a broken subset surfaces here rather than exposing an off-list
        value. This preserves the subset-⊆-vocabulary discipline uniformly for every kind.
        """
        # No selectable source populated by the seam → no option list (a non-choice field, or a
        # field whose declared source did not propagate — the latter is the asymmetry task 9/C6
        # strengthens into a loud error at the seam).
        if field_options is None:
            return None

        subset = field.application_choices
        if subset is None:
            # No subset declared → the full seam vocabulary, roles dropped (back-compatible).
            return [self._public_option(o) for o in field_options]

        # Fail-loud: the subset MUST be ⊆ the seam vocabulary (R4a.4). A dangling entry is a
        # config bug, surfaced caller-safe (dotted key only), never a silently off-list value.
        vocabulary = {str(o.get("value")) for o in field_options}
        dangling = [v for v in subset if v not in vocabulary]
        if dangling:
            from sam.members.domain.field_resolver import OverlayError

            offenders = ", ".join(repr(v) for v in dangling)
            raise OverlayError(
                {
                    field.dotted_key(): (
                        f"application_choices subset entr"
                        f"{'y' if len(dangling) == 1 else 'ies'} {offenders} "
                        f"not in the field's resolved options (R4a.4)"
                    )
                }
            )
        allowed = set(subset)
        return [
            self._public_option(o)
            for o in field_options
            if str(o.get("value")) in allowed
        ]

    @staticmethod
    def _public_option(option: Mapping[str, Any]) -> dict[str, Any]:
        """Project ONE seam option to its PUBLIC shape: drop the staff-only ``roles`` gate (R4a).

        The seam's canonical option carries ``{value, label, order?, roles?}``; the public form
        contract never exposes the value-level ``roles`` gate (a STAFF concern). Everything else
        (``value`` / i18n ``label`` / the reference ``order``) rides through unchanged, so the
        public read is the SAME vocabulary the staff read serializes, minus ``roles``.
        """
        return {k: v for k, v in option.items() if k != "roles"}

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

    def _assemble_field_options(
        self,
        field: ResolvedField,
        *,
        options: Sequence[Mapping[str, Any]],
        scope_vocab: Mapping[str, Sequence[str]],
    ) -> list[dict[str, Any]] | None:
        """The ONE selectable-vocabulary assembly pass (design C4 / F8, R2.1/R2.6).

        Resolves a field's canonical ``options`` from its DECLARED SOURCE at this single
        read-assembly point — the ``assembleSelectableOptions`` the design pins — so every
        consumer (the staff :meth:`_serialize_field` and the public
        :meth:`_public_field_options`) reads the ONE ``options`` this computed and NONE branches
        by field kind. The three sources are the ONLY per-kind decision, and all are INJECTED
        (the pure :class:`FieldResolver` reads no catalog/DB):

        - **reference** (``membership_type``): the injected ACTIVE-catalog options map
          (``_active_membership_type_options``) — the F8 reference population, moved from the
          one-off merge in :meth:`get_field_config` into this uniform pass. Returned as plain
          ``{value, label, order}`` dicts.
        - **scope-backed** (an overlay enum whose key is bound to a tenant scope dimension — its
          key is present in the injected ``scope_vocab``): the dimension's values projected to
          rich ``{value, label}`` options. ``scope_vocab`` / ``scope_dimensions.values`` is the
          single source of truth, so a scope dropdown needs no duplicated inline vocabulary.
        - **inline enum**: the field's own rich :class:`EnumOption`s (``{value, label, roles?}``),
          sourced purely by the resolver — unchanged.

        Returns ``None`` for a field that declares no selectable source. There is deliberately NO
        ``field.choices`` fallback here (F9/F10): a bare value list is not a canonical source —
        after the C7 backfill / C5 reader collapse every live selectable row carries ``options``.
        A field whose DECLARED source exists but did not propagate into ``options`` is the
        ASYMMETRY the uniform fail-loud boundary (task 9 / C6) raises on; this pass is the single
        point that decision hooks into — today it returns the (empty/absent) result, and task 9
        strengthens exactly this seam to raise on the asymmetry rather than degrade.
        """
        # reference — the injected active-catalog map (F8). Population lives at the seam, never
        # in the pure resolver.
        if field.dotted_key() == MEMBERSHIP_TYPE_FIELD_KEY:
            return [dict(o) for o in options]

        # scope-backed — project the injected scope dimension's values to rich options. The key
        # ∈ scope_vocab is the SAME discriminator the resolver uses for a scope-dimension-backed
        # enum, so inline-options fields (which are NOT in scope_vocab) still resolve inline.
        if field.key in scope_vocab:
            return [
                {"value": str(v), "label": {}} for v in scope_vocab[field.key]
            ]

        # inline enum — the field's own rich options, sourced purely by the resolver. Reuses the
        # catalog mixin's enum serializer (resolved at runtime on the composed service class, same
        # as the other cross-mixin calls here) so the {value,label,roles?} shape is identical.
        if field.options is not None:
            return [self._serialize_enum_option(o) for o in field.options]

        # No selectable source declared (a plain string/number field, or a not-yet-populated
        # field). No `field.choices` fallback (F9/F10): a bare value list is not a canonical
        # source. Task 9 (C6) strengthens THIS point to raise when a DECLARED source exists but
        # failed to propagate (the asymmetry); a legitimately sourceless field stays `None`.
        return None

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
