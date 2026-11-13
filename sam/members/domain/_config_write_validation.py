"""Body/field/option validation guards.
Part of ConfigWriteService (task 9).
"""

from __future__ import annotations

from collections.abc import Mapping

from services import projection_schema as schema

from sam.members.domain import field_formats
from sam.members.domain.fixed_fields import field_by_key

from ._config_write_shared import OVERLAY_GROUP, ConfigWriteValidationError


class ConfigWriteValidationMixin:
    """Body/field/option validation guards."""

    def _validate_body(self, config_id: str, body: Mapping, tenant_id: str) -> dict:
        """Dispatch to the per-``configId`` body validator.

        Each SAM-owned id shapes + validates only its own attributes — ``fields`` (Task 1.5),
        ``scope`` (Task 3.3), and ``mail`` (Task 5.1) are all implemented here. ``fields`` also
        needs ``tenant_id`` to MERGE the incoming slices onto the current stored row (bugfix).
        """
        if config_id == schema.CONFIG_ID_FIELDS:
            return self._validate_fields_body(body, tenant_id)
        validators = {
            schema.CONFIG_ID_SCOPE: self._validate_scope_body,
            schema.CONFIG_ID_MAIL: self._validate_mail_body,
        }
        validator = validators.get(config_id)
        if validator is None:
            # The edge already rejects an id outside {fields, scope, mail}; reaching here means a
            # writable id whose authoring step has not landed yet. Fail loudly rather than write a
            # half-shaped row.
            raise ValueError(
                f"no config-write validator wired for config_id {config_id!r}"
            )
        return validator(body)

    def _validate_fields_body(self, body: Mapping, tenant_id: str = "") -> dict:
        """Validate + shape a ``config#fields`` body into the reader's ``get_overlay`` shape (R7).

        Authors the ``fields`` / ``overrides`` / ``functional_groups`` attributes ONLY — the exact
        shape ``MembersProjectionReader.get_overlay`` reads (R7.1). Validation is SHAPE-ONLY (the
        reader degrades individual malformed entries gracefully, so the service checks container
        types, not every leaf):

        - ``fields`` — a mapping of ``{name: spec}``; each ``spec`` must be a mapping (R7.1).
        - ``overrides`` — a mapping of ``{dotted_key: spec}``; each ``spec`` must be a mapping.
        - ``functional_groups`` — a MAP keyed by group key (spec 03, design C6 / D2a), each entry a
          mapping with a non-blank ``key``; a legacy LIST is still accepted and normalized to the
          MAP during the LIST→MAP migration rollout (review Must-fix #4).

        It does **NOT** author ``default_page_size`` — that tenant-level scalar is RETIRED in favor
        of the per-user runtime Rows_Per_Page_Selector (R7.2 / Requirement 25). Any
        ``default_page_size`` in the body is dropped, never written.

        Each per-field ``scope`` sub-object is preserved **verbatim** (R7.3): the service copies the
        field spec through unchanged so Task 2 can derive ``config#scope`` from the per-field
        ``scope`` attributes. It reshapes nothing inside a field spec.

        Application-form slug (spec 12 Task 1.1 / R4.2, design §Data Models): the row also carries
        the form's own public ``slug`` plus the publish-state metadata ``published_at`` /
        ``published_version`` (both authored by the publish path, Task 2.2). On a fields write this
        service authors the ``slug`` from the body — validating its FORMAT with the landing
        ``SLUG_PATTERN`` rules (:func:`form_slug.validate_slug_format`) and rejecting a malformed
        slug fail-loud with the standard caller-safe envelope — while CARRYING the publish-state
        metadata through from the current stored row (a plain fields save never fabricates or wipes
        it). Slug UNIQUENESS is NOT checked here (that is the Task-1.2 ``_slugs/{slug}`` marker).
        """
        if not isinstance(body, Mapping):
            raise ConfigWriteValidationError(
                "config#fields body must be an object with fields/overrides/functional_groups"
            )

        fields_in = self._validate_fields_map(body.get("fields"))
        # Fixed-field overrides: the canonical stored attribute is ``overrides`` (what
        # ``MembersProjectionReader.get_overlay`` reads). The frontend field_overlay object and the
        # legacy Flask ``build_config_fields_row`` builder author this map under the INPUT ALIAS
        # ``fixed_overrides``. Accept either on the wire and normalize to ``overrides``. Precedence
        # fix (bugfix): fall back to the alias when ``overrides`` is empty OR absent — a
        # present-but-empty ``overrides`` must NOT shadow a populated ``fixed_overrides`` (that
        # dropped every base-field toggle the Application Form Builder sent). A populated canonical
        # ``overrides`` still wins when both are non-empty.
        overrides_raw = body.get("overrides")
        if not overrides_raw:
            overrides_raw = body.get("fixed_overrides")
        overrides_in = self._validate_overrides_map(overrides_raw)
        functional_groups_in = self._validate_functional_groups(
            body.get("functional_groups")
        )

        # MERGE-ON-WRITE (bugfix): a config#fields PUT carries only the slice(s) the client is
        # authoring, but the repository put REPLACES the whole row. Without a merge, a partial body
        # (e.g. the Application Form Builder sending only application-attribute toggles under
        # ``overrides``/``fixed_overrides`` with empty ``fields``/``functional_groups``) would WIPE
        # the tenant's other slices. When an overlay reader is wired, load the CURRENT stored row
        # and merge the incoming slices onto it PER KEY: an incoming field/override spec REPLACES
        # the stored entry for that key (so a toggle updates it), and a stored entry the body OMITS
        # is PRESERVED. ``functional_groups`` (an ordered list) is replaced only when the body
        # carries a non-empty list, else the stored groups are kept. No reader (unit tests without
        # one) → legacy replace with exactly what the body carried.
        fields, overrides, functional_groups = self._merge_fields_slices(
            tenant_id, fields_in, overrides_in, functional_groups_in, body
        )

        # Per-field APPLICATION-attribute hardening (R8): the write path is the authoritative
        # author now that the Flask `_validate_application_attrs` guard is off the authoring path
        # (R8.4). Reject a subset ⊄ choices, an unknown `format.checker`, a malformed `format`,
        # or a relax of a platform-required field — fail-loud, BEFORE the row is written, keyed to
        # the offending field (R8.1/R8.3). Validated over the MERGED result so a preserved entry is
        # re-checked too.
        self._validate_application_attributes(fields, overrides)

        # OPTION-INTEGRITY hardening (03b BU-1, Req 3.2a/3.4a): the unified enum model hangs a
        # field's vocabulary off its own `options`, so the write seam is the authoritative place to
        # keep that vocabulary well-formed. Two checks over the MERGED result (so a preserved
        # option list is re-checked too), BEFORE the row is written, keyed to the offending field:
        #   - a required / off-form enum must keep ≥1 `allowed:true` option (Req 3.4a); and
        #   - an option `value` still referenced by a member must not VANISH or be RENAMED out of
        #     the field's options (Req 3.2a) — it MAY instead be set `allowed:false` (retired).
        # The removal/rename check needs the CURRENT stored options to diff against, read from the
        # same merge reader seam used for the slice merge above.
        self._validate_option_integrity(fields, overrides, tenant_id)

        # Author the three reader-read overlay attributes — no default_page_size (R7.2) — PLUS the
        # application-form slug + publish-state metadata (spec 12 Task 1.1 / R4.2, design §Data
        # Models). ``slug`` comes from the body (format-validated below); ``published_at`` /
        # ``published_version`` are carried through from the current stored row (publish owns them,
        # Task 2.2) so a plain fields save never fabricates or wipes publish state.
        attributes: dict = {
            "fields": fields,
            "overrides": overrides,
            "functional_groups": functional_groups,
        }
        self._author_form_slug(attributes, body, tenant_id)
        return attributes

    def _validate_application_attributes(
        self, fields: Mapping, overrides: Mapping
    ) -> None:
        """Validate the per-field application attributes over BOTH specs, fail-loud (R8).

        The SAM equivalent of the retired Flask ``members_config_validation
        ._validate_application_attrs`` (R8.4) — the well-formedness write-time invariants, now
        enforced by the authoritative author so a crafted or buggy write can never store an
        incoherent ``config#fields`` row:

        1. **subset ⊆ choices (R8.1a):** a present ``application_choices`` must be a list whose
           every entry is a valid choice of the field's own resolved choices (``options[].value``
           / ``choices``). A subset on a field with no choices, or an entry not in choices, is a
           write error.
        2. **known checker (R8.1b):** a present ``format`` must be a well-formed ``{checker,
           params?}`` mapping whose ``checker`` is in :func:`field_formats.known_tokens`. Anything
           else is rejected (a tenant attaches a KNOWN token, it never authors a checker).

        The former no-relax invariant (a platform-required field could not carry
        ``application_required = False``) was a Hardcoded_Binding that OVERRULED the admin and is
        REMOVED (03b Req 1.1/1.4): the admin now freely sets application-requiredness for any field.

        Reasons are COLLECTED across both maps (every offending field, not just the first) and, if
        any are found, raised as ONE :class:`ConfigWriteValidationError` whose message is keyed to
        the offending field(s) (R8.3) — caller-safe, no internals leaked.
        """
        reasons: dict[str, str] = {}

        # overrides — keyed by the canonical dotted key of a fixed/calculated field.
        for dotted, spec in overrides.items():
            if not isinstance(spec, Mapping):
                continue
            self._collect_application_attr_reasons(dotted, spec, reasons)

        # fields — the added variable fields. The error key mirrors the Flask dotted form
        # (`overlay.<key>`) so a rejected write names the field consistently across planes.
        for name, spec in fields.items():
            if not isinstance(spec, Mapping):
                continue
            key = spec.get("key") if isinstance(spec.get("key"), str) else name
            dotted = f"{OVERLAY_GROUP}.{key}"
            self._collect_application_attr_reasons(dotted, spec, reasons)

        if reasons:
            detail = "; ".join(
                f"{field}: {reason}" for field, reason in reasons.items()
            )
            raise ConfigWriteValidationError(
                f"config#fields application-attribute validation failed: {detail}"
            )

    @staticmethod
    def _collect_application_attr_reasons(
        dotted: str,
        spec: Mapping,
        reasons: dict[str, str],
    ) -> None:
        """Append a reason under ``dotted`` for any application-attribute violation on one spec.

        Mirrors the well-formedness rules of the retired Flask ``_validate_application_attrs``
        (R8.4); batched (never raises here) so the caller collects every offending field before
        raising one :class:`ConfigWriteValidationError`. The no-relax binding (03b Req 1) is gone —
        requiredness on the form is the admin's to set.
        """
        # 1) enum application-subset ⊆ field choices (R8.1a).
        subset = spec.get("application_choices")
        if subset is not None:
            if not isinstance(subset, (list, tuple)):
                reasons[dotted] = "application_choices must be a list"
            else:
                choices = ConfigWriteValidationMixin._field_choice_values(spec)
                if choices is None:
                    reasons[dotted] = (
                        "application_choices is set but the field declares no choices "
                        "(only an enum field with choices can carry an application subset)"
                    )
                else:
                    extra = [v for v in subset if v not in choices]
                    if extra:
                        reasons[dotted] = (
                            "application_choices entries are not valid field choices: "
                            f"{extra!r}"
                        )

        # 2) format.checker must be a platform-known token (R8.1b).
        fmt = spec.get("format")
        if fmt is not None:
            if not isinstance(fmt, Mapping):
                reasons[dotted] = "format must be an object with a 'checker' token"
            else:
                checker = fmt.get("checker")
                if (
                    not isinstance(checker, str)
                    or checker not in field_formats.known_tokens()
                ):
                    known = ", ".join(sorted(field_formats.known_tokens()))
                    reasons[dotted] = (
                        f"format.checker {checker!r} is not a platform-known token "
                        f"(known: {known})"
                    )

    @staticmethod
    def _field_choice_values(spec: Mapping) -> set | None:
        """The field's resolved CHOICE vocabulary as a set, or ``None`` when it declares none.

        Reads the field's vocabulary from the ONE canonical ``options`` list (``{value,...}`` dicts
        or bare strings). Used to validate that an ``application_choices`` subset is drawn from the
        field's actual vocabulary (R3.2 — the public-form subset concept is PRESERVED). Returns the
        non-blank string values as a set for subset-membership checks, or ``None`` when the field
        declares no usable vocabulary (not an enum / value-less) — the caller treats an
        ``application_choices`` subset on such a field as a write error (you cannot subset a field
        that has no choices).

        The legacy ``choices`` fallback was RETIRED (spec 03a, F12/N2): now that C7 backfills every
        live row to ``options`` and C2 drops ``choices`` from the write surface, the
        ``_collect(...) or _collect(spec.get("choices"))`` coalesce is dead — this helper reads
        ``options`` ONLY, matching the one-vocabulary model (R2.1). Only the vocabulary SOURCE
        tightened; the ``application_choices`` subset VALIDATION behaviour is unchanged.
        """

        def _collect(raw) -> list | None:
            if not isinstance(raw, (list, tuple)):
                return None
            values: list = []
            for entry in raw:
                value = entry.get("value") if isinstance(entry, Mapping) else entry
                if isinstance(value, str) and value.strip():
                    values.append(value)
            return values or None

        values = _collect(spec.get("options"))
        return set(values) if values else None

    def _validate_option_integrity(
        self, fields: Mapping, overrides: Mapping, tenant_id: str
    ) -> None:
        """Enforce the unified enum-model option-integrity rules at the write seam (R3.2a/R3.4a).

        Two well-formedness checks over the MERGED field/override specs (NOT an overrule of the
        admin — a config that violates them is simply not well-formed under the unified model):

        1. **≥1 ``allowed:true`` option (R3.4a).** A REQUIRED enum, or one that is OFF the
           application form (``application_visible`` falsey → the form supplies a default), must
           keep at least one option with ``allowed`` truthy. An absent ``allowed`` reads as
           ``true`` (back-compat). A write that would zero the allowed set for such a field is
           rejected — the form would have no default / no selectable value. A field that declares
           NO ``options`` (a plain string field, or an open enum sourcing its vocabulary elsewhere)
           is NOT subject to this rule.
        2. **In-use option cannot vanish/rename (R3.2a).** An option ``value`` present in the
           CURRENT stored options of a field but ABSENT from the new (merged) option set has been
           removed or renamed. If a member still references that value it MUST NOT disappear — the
           admin may instead set it ``allowed:false`` (retired/grandfathered), which keeps the
           value present. "Referenced by a member" is observed via the injected ``usage_probe``
           (storage-agnostic, steering 35/39); with no probe wired the leg does not block.

        Reasons are COLLECTED across both maps (every offending field) and, if any are found,
        raised as ONE caller-safe :class:`ConfigWriteValidationError` naming the offending
        field(s)/option(s) (R8.3) — no raw internals leaked.
        """
        current = self._current_fields_row(tenant_id)
        current_fields = (
            current.get("fields") if isinstance(current.get("fields"), Mapping) else {}
        )
        # The current override map may be stored under either the canonical ``overrides`` or the
        # authoring wire alias ``fixed_overrides`` (the reader serves the alias) — accept either so
        # the option diff sees the real prior vocabulary.
        current_overrides = current.get("fixed_overrides")
        if not isinstance(current_overrides, Mapping):
            current_overrides = current.get("overrides")
        if not isinstance(current_overrides, Mapping):
            current_overrides = {}

        reasons: dict[str, str] = {}

        # overrides — keyed by canonical dotted key (e.g. ``membership.membership_type``). The
        # field key the probe is asked about is the dotted key's bare field name.
        for dotted, spec in overrides.items():
            if not isinstance(spec, Mapping):
                continue
            field_key = dotted.split(".")[-1]
            self._collect_option_integrity_reasons(
                dotted,
                field_key,
                spec,
                current_overrides.get(dotted),
                reasons,
                platform_required=self._is_platform_required(dotted),
                tenant_id=tenant_id,
            )

        # fields — tenant-added variable fields. Keyed by the overlay-dotted form for a consistent,
        # caller-safe error key across planes; the probe is asked about the bare field key.
        for name, spec in fields.items():
            if not isinstance(spec, Mapping):
                continue
            field_key = spec.get("key") if isinstance(spec.get("key"), str) else name
            dotted = f"{OVERLAY_GROUP}.{field_key}"
            self._collect_option_integrity_reasons(
                dotted,
                field_key,
                spec,
                current_fields.get(name),
                reasons,
                platform_required=False,
                tenant_id=tenant_id,
            )

        if reasons:
            detail = "; ".join(
                f"{field}: {reason}" for field, reason in reasons.items()
            )
            raise ConfigWriteValidationError(
                f"config#fields option-integrity validation failed: {detail}"
            )

    @staticmethod
    def _is_platform_required(dotted: str) -> bool:
        """True when the canonical dotted key names a platform-required fixed field (registry)."""
        fixed = field_by_key(dotted)
        return bool(fixed is not None and fixed.required)

    def _collect_option_integrity_reasons(
        self,
        dotted: str,
        field_key: str,
        spec: Mapping,
        current_spec,
        reasons: dict[str, str],
        *,
        platform_required: bool,
        tenant_id: str,
    ) -> None:
        """Append option-integrity reasons for one field spec under ``dotted`` (R3.2a/R3.4a).

        Batched (never raises here) so the caller collects every offending field before raising
        one :class:`ConfigWriteValidationError`. A field that declares no ``options`` is skipped
        entirely — the integrity rules are about an enum's own vocabulary.
        """
        new_options = self._options_of(spec)
        if new_options is None:
            # No authored vocabulary on this spec → neither rule applies.
            return

        # R3.4a — a required enum, or one OFF the application form, must keep ≥1 allowed option.
        required = platform_required or spec.get("required") is True
        off_form = spec.get("application_visible") is not True
        if (required or off_form) and not self._has_allowed_option(new_options):
            reasons[dotted] = (
                "a required or off-form enum must keep at least one allowed:true option "
                "(the form has no default / no selectable value otherwise)"
            )
            # The zero-allowed violation is the more fundamental one; still fall through so a
            # separate in-use-removal reason can also surface if present (both help the admin).

        # R3.2a — an in-use option value must not vanish/rename out of the field's options.
        current_options = self._options_of(current_spec)
        if current_options:
            new_values = {o["value"] for o in new_options}
            for opt in current_options:
                value = opt.get("value")
                if not isinstance(value, str) or not value:
                    continue
                if value in new_values:
                    continue  # still present (possibly only toggled allowed:false) → fine
                if self._option_referenced_by_member(tenant_id, field_key, value):
                    # Keep the first in-use reason per field if a zero-allowed reason already set;
                    # otherwise this becomes the field's reason. Use a distinct key suffix so both
                    # a zero-allowed AND an in-use reason can be surfaced for the same field.
                    key = (
                        dotted
                        if dotted not in reasons
                        else f"{dotted} (option {value!r})"
                    )
                    reasons[key] = (
                        f"option {value!r} is still referenced by a member and cannot be "
                        "removed or renamed; set it allowed:false to retire it instead"
                    )

    @staticmethod
    def _options_of(spec) -> list[dict] | None:
        """The option dicts of a field spec as a list, or ``None`` when it declares no options.

        Each entry is normalized to a dict with at least a ``value`` key. A bare-string option is
        promoted to ``{"value": <str>}`` (an unranked, allowed option by default). ``None`` /
        absent / a non-list ``options`` → ``None`` (the field declares no authored vocabulary).
        """
        if not isinstance(spec, Mapping):
            return None
        raw = spec.get("options")
        if not isinstance(raw, (list, tuple)):
            return None
        out: list[dict] = []
        for entry in raw:
            if isinstance(entry, Mapping):
                out.append(dict(entry))
            elif isinstance(entry, str) and entry.strip():
                out.append({"value": entry})
        return out

    @staticmethod
    def _has_allowed_option(options: list[dict]) -> bool:
        """True when at least one option is allowed — an ABSENT ``allowed`` reads as ``True``."""
        for opt in options:
            if opt.get("allowed", True):
                return True
        return False

    def _option_referenced_by_member(
        self, tenant_id: str, field_key: str, value: str
    ) -> bool:
        """Ask the injected ``usage_probe`` whether a member references option ``value`` (R3.2a).

        Storage-agnostic (steering 35/39) — the write service never queries the members table. The
        probe (shared with the delete-field guard) is consulted through whichever shape it exposes:

        - an option-level ``option_in_use(tenant_id, field_key, value) -> bool`` (preferred), or
        - the richer ``field_usage(tenant_id, field_key) -> Mapping`` the delete-field guard uses,
          from which a ``values`` collection (the per-value usage the field reports) is read and
          membership of ``value`` checked.

        With no probe wired, or a probe exposing neither shape, the leg is UNOBSERVABLE and returns
        ``False`` (does not block) — production always wires a probe; a member still pointing at a
        removed option is then caught on member save (BU-2).
        """
        probe = self._usage_probe
        if probe is None:
            return False
        if hasattr(probe, "option_in_use"):
            return bool(probe.option_in_use(tenant_id, field_key, value))
        if hasattr(probe, "field_usage"):
            usage = probe.field_usage(tenant_id, field_key)
            if isinstance(usage, Mapping):
                values = usage.get("values")
                if isinstance(values, (list, tuple, set)):
                    return value in values
        return False

    @staticmethod
    def _validate_fields_map(raw) -> dict:
        """Validate the ``fields`` map; preserve each field spec (incl. ``scope``) verbatim (R7.3).

        ``None`` / absent → ``{}`` (empty overlay is valid — the reader resolves it to the fixed
        base). Each value must be a mapping; each spec is carried through unchanged so a per-field
        ``scope`` attribute is preserved verbatim for the Task 2 ``config#scope`` derivation. The
        service does NOT reshape, drop, or default anything inside a field spec.
        """
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigWriteValidationError("config#fields 'fields' must be an object")
        for name, spec in raw.items():
            if not isinstance(spec, Mapping):
                raise ConfigWriteValidationError(
                    f"config#fields field {name!r} must be an object"
                )
        # Preserve each spec verbatim (shallow copy of the container only) — the per-field `scope`
        # sub-object rides through untouched for Task 2 derivation (R7.3).
        return {name: dict(spec) for name, spec in raw.items()}

    @staticmethod
    def _validate_overrides_map(raw) -> dict:
        """Validate the fixed-field ``overrides`` map; preserve each override spec verbatim.

        ``None`` / absent → ``{}``. Each value must be a mapping (a fixed-field override spec); a
        per-override ``scope`` attribute is likewise carried through verbatim for Task 2.
        """
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigWriteValidationError(
                "config#fields 'overrides' must be an object"
            )
        for dotted, spec in raw.items():
            if not isinstance(spec, Mapping):
                raise ConfigWriteValidationError(
                    f"config#fields override {dotted!r} must be an object"
                )
        return {dotted: dict(spec) for dotted, spec in raw.items()}

    @staticmethod
    def _validate_functional_groups(raw) -> dict:
        """Validate the ``functional_groups`` catalog; author it as a MAP keyed by group ``key``.

        **LIST→MAP migration (spec 03, design C6 / D2a / review Must-fix #4).** The stored shape is
        migrating from an ordered LIST ``[{key, label, order}, …]`` (legacy) to a MAP
        ``{key: {key, label, order}, …}`` (new, truncation-proof per-path ``update_item``). This
        validator DUAL-ACCEPTS both wire shapes (a stale SPA bundle or a migrated one) and always
        emits the canonical MAP the reader now dual-reads, so a write never regresses a row to the
        legacy LIST:

        - ``None`` / absent → ``{}`` (empty-is-valid).
        - a **MAP** ``{gkey: entry}``: each ``entry`` must be a mapping; its own ``key`` (when a
          non-blank string) is authoritative, else the map key fills it in. The entry's ``order`` /
          ``label`` ride through verbatim (``order`` is re-homed into the entry, Q3a).
        - a **LIST** ``[entry, …]``: each ``entry`` must be a mapping carrying a non-blank ``key``;
          it is re-keyed by that ``key`` into the MAP.

        A keyless/non-mapping entry is a malformed body (fail-loud 400), never a silently-dropped
        row — the same strictness the pre-migration validator enforced.
        """
        if raw is None:
            return {}
        if isinstance(raw, Mapping):
            groups: dict = {}
            for gkey, entry in raw.items():
                if not isinstance(entry, Mapping):
                    raise ConfigWriteValidationError(
                        "config#fields functional_groups entries must be objects"
                    )
                normalized = dict(entry)
                key = normalized.get("key")
                if not (isinstance(key, str) and key.strip()):
                    if not (isinstance(gkey, str) and gkey.strip()):
                        raise ConfigWriteValidationError(
                            "config#fields functional_groups entries must carry a non-blank 'key'"
                        )
                    key = gkey
                    normalized["key"] = gkey
                groups[str(key)] = normalized
            return groups
        if isinstance(raw, (list, tuple)):
            groups = {}
            for entry in raw:
                if not isinstance(entry, Mapping):
                    raise ConfigWriteValidationError(
                        "config#fields functional_groups entries must be objects"
                    )
                key = entry.get("key")
                if not isinstance(key, str) or not key.strip():
                    raise ConfigWriteValidationError(
                        "config#fields functional_groups entries must carry a non-blank 'key'"
                    )
                groups[str(key)] = dict(entry)
            return groups
        raise ConfigWriteValidationError(
            "config#fields 'functional_groups' must be a map keyed by group key "
            "(a legacy list is also accepted during the LIST→MAP migration)"
        )
