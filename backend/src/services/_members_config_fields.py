"""Field-overlay save-time validation for the ``members.field_overlay`` parameter.

Structural split out of ``members_config_validation.py`` (code-quality 2026-10-28
task 10) — this module holds the error type, the platform base field-key / format-token
sets (transcribed from the SAM domain registries), and the field-overlay / scope /
application-attribute validators. ``members_config_validation`` re-exports everything
here, so the public import surface (``from services.members_config_validation import …``)
is unchanged. Behaviour is identical to the pre-split module — this is a pure move.

See the ``members_config_validation`` facade docstring for the full cross-plane reuse
rationale (why the field-key set is transcribed rather than imported from ``sam``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class MembersConfigError(ValueError):
    """Raised when a ``members.*`` parameter fails save-time validation (a config bug).

    Subclasses :class:`ValueError` so the ``members.*`` PUT/save path surfaces it as a 400
    (the parameter routes already translate ``ValueError`` → 400). Carries ``reasons`` (a
    key → human-readable why map) so a misconfiguration surfaces every problem at once —
    mirroring the SAM-domain ``OverlayError`` / ``FieldValidationError``.
    """

    def __init__(self, reasons: Mapping[str, str]):
        self.reasons = dict(reasons)
        detail = "; ".join(f"{k}: {v}" for k, v in self.reasons.items())
        super().__init__(f"invalid members config: {detail}")


#: The storage bucket variable (overlay) fields live under (mirrors field_resolver.OVERLAY_GROUP).
OVERLAY_GROUP = "overlay"

# ── The platform base field-key set — transcribed from the SAM domain registries ──────
# Single source of truth for field NAMES lives in sam/members/domain/{fixed,calculated}_fields.py.
# These sets MUST match those canonical keys (fixed base + calculated fields). Kept as a plain
# transcription so the Flask save path can resolve view-context references without importing SAM.

#: Fixed base fields, as canonical dotted keys (fixed_fields.PERSONAL_FIELDS + MEMBERSHIP_FIELDS).
FIXED_FIELD_KEYS: frozenset[str] = frozenset(
    {
        # personal
        "personal.first_name",
        "personal.last_name",
        "personal.name_infix",
        "personal.initials",
        "personal.birth_date",
        "personal.gender",
        "personal.email",
        "personal.phone",
        "personal.street",
        "personal.postal_code",
        "personal.city",
        "personal.country",
        # membership
        "membership.member_number",
        "membership.status",
        "membership.membership_type",
        "membership.joined_date",
        "membership.created_at",
        "membership.updated_at",
    }
)

#: Calculated (derived, read-only) fields, as canonical dotted keys (calculated_fields.py).
#: MUST stay in lock-step with ``sam/members/domain/calculated_fields.CALCULATED_FIELDS`` (the
#: single source of truth). The four ``birth_*`` keys were previously missing, so a view context
#: referencing a real calculated key (e.g. ``birth_month``) was wrongly rejected at Save — this
#: set now transcribes all nine CalculatedField entries.
CALCULATED_FIELD_KEYS: frozenset[str] = frozenset(
    {
        "personal.display_name",
        "personal.age",
        "personal.birthday",
        "personal.birth_day",
        "personal.birth_month",
        "personal.birth_year",
        "personal.birth_quarter",
        "membership.years_member",
        "membership.application_year",
    }
)

#: All platform base canonical dotted keys (fixed ⊕ calculated) — the fixed half of resolution.
_BASE_DOTTED_KEYS: frozenset[str] = FIXED_FIELD_KEYS | CALCULATED_FIELD_KEYS

#: The bare (undotted) canonical keys — a view context may reference a field by its short key
#: (e.g. "member_number") as in the design examples, so both forms resolve.
_BASE_BARE_KEYS: frozenset[str] = frozenset(
    k.split(".", 1)[1] for k in _BASE_DOTTED_KEYS
)

#: The fixed-base dotted keys that are platform-REQUIRED (may be tightened, never loosened).
#: Transcribed from fixed_fields.py (required=True): the overlay may not make these optional.
_REQUIRED_FIXED_KEYS: frozenset[str] = frozenset(
    {
        "personal.first_name",
        "personal.last_name",
        "personal.email",
        "membership.member_number",
        "membership.status",
        "membership.membership_type",
        "membership.joined_date",
    }
)

# ── The platform-known FieldFormat checker tokens — transcribed from the SAM registry ──
# Member Application Form (application-app R4c.3 / R7.7, task 8.3). A field may carry an
# optional ``format {checker, params}`` attribute naming a PLATFORM-DEFINED checker token.
# The authoritative token set is defined on the SAM plane by
# ``sam/members/domain/field_formats.known_tokens()`` (currently ``{"EMAIL", "IBAN"}``).
# The two planes are intentionally NOT import-coupled (see the module docstring), so — exactly
# like ``CALCULATED_FIELD_KEYS`` mirrors the SAM calculated-field registry — this is a direct
# TRANSCRIPTION pinned as a literal here, with a drift-guard test
# (``test_platform_format_tokens_match_sam_source_of_truth``) that fails if the two diverge.
# A tenant may only ATTACH a known token; it cannot author a checker. An unknown token is
# rejected fail-loud at Save (R4c.3) rather than projecting a broken row the reader must
# silently degrade (R7.3).
PLATFORM_FORMAT_TOKENS: frozenset[str] = frozenset({"EMAIL", "IBAN"})


# ── helpers ───────────────────────────────────────────────────────────────────────────


#: Phase 3 step 9 (R2.1/R2.5) — the field-attribute key under which a field declares it is a
#: scope axis. The authoring representation of scope-binding moves from the standalone
#: ``members.scope_dimensions`` list onto the field itself; the projection builder
#: (``_projection_config_builders._scope_dimensions_from_overlay``) derives the ``config#scope``
#: dimensions from these attributes, keeping the resolver's ``ScopeConfig`` semantically
#: equivalent (Property 2).
_FIELD_SCOPE_ATTR = "scope"


def _field_enum_values(spec: Mapping[str, Any]) -> list | None:
    """The field's ENUM VALUES — the single scope vocabulary (R3.4).

    Mirrors ``_projection_config_builders._enum_values_from_field``: a field's enum
    vocabulary is read from rich ``options`` (``{value,...}`` dicts or bare strings)
    first, then from a bare ``choices`` string list. Returns the ordered list of
    non-blank string values, or ``None`` when the field declares no usable enum
    vocabulary (not an enum / value-less). The builder derives the ``config#scope``
    dimension values from exactly this list, so the validator checks presence here —
    an enabled scope axis on a value-less/non-enum field is rejected at save (R3.4).
    """

    def _collect(raw: Any) -> list | None:
        if not isinstance(raw, (list, tuple)):
            return None
        values: list = []
        for entry in raw:
            value = entry.get("value") if isinstance(entry, Mapping) else entry
            if isinstance(value, str) and value.strip():
                values.append(value)
        return values or None

    return _collect(spec.get("options")) or _collect(spec.get("choices"))


def _validate_field_scope(
    dotted: str, spec: Mapping[str, Any], reasons: dict[str, str]
) -> None:
    """Validate one field's ``scope`` attribute (Phase 3 step 9, R2.1 / R3.4).

    Mirrors the SAM-domain ``ScopeConfig`` / ``_reject_invalid_config`` invariants on the
    authoring plane, so a malformed scope axis is rejected at Save rather than silently
    projecting a broken ``config#scope`` dimension. A field expresses that it IS a scope axis
    by carrying a ``scope`` object; the dimension ``key``/``field`` derive from the field's own
    key (the builder's job), so this validator checks the scope BODY and — under the
    single-vocabulary model — the field's ENUM VOCABULARY:

    - ``scope`` must be an object;
    - ``enabled`` (optional, default ``True``) must be a boolean;
    - a legacy ``scope.values`` (optional, honoured as a FALLBACK ONLY) must be a list of
      non-blank, unique strings when present;
    - **single-vocabulary (R3.4):** an ENABLED scope axis must sit on an ENUM FIELD WITH VALUES
      — the dimension values ARE the field's enum values (``options[].value`` / ``choices``), so
      an enabled axis on a value-less / non-enum field can never grant anything and is a save
      error. A legacy stored ``scope.values`` satisfies this as the migration fallback;
    - ``required_for`` (optional) must be a list of strings.

    Appends a reason under ``dotted`` on any violation (never raises here — the caller collects
    all reasons and raises once, mirroring the batched :class:`MembersConfigError`).
    """
    scope = spec.get(_FIELD_SCOPE_ATTR)
    if not isinstance(scope, Mapping):
        reasons[dotted] = "scope must be an object"
        return

    enabled = scope.get("enabled", True)
    if not isinstance(enabled, bool):
        reasons[dotted] = "scope.enabled must be a boolean"
        return

    # Legacy `scope.values` (fallback only) — still well-formedness-checked when present.
    values = scope.get("values")
    if values is not None:
        if not isinstance(values, (list, tuple)):
            reasons[dotted] = "scope.values must be a list"
            return
        if any((not isinstance(v, str)) or (not v.strip()) for v in values):
            reasons[dotted] = "scope.values must be non-blank strings"
            return
        if len(set(values)) != len(values):
            reasons[dotted] = "scope.values must be unique"
            return

    # Single-vocabulary (R3.4): an enabled scope axis derives its values from the field's enum
    # vocabulary. The field must therefore be an enum WITH values; a legacy `scope.values` is
    # honoured as the migration fallback.
    if enabled and not _field_enum_values(spec) and not values:
        reasons[dotted] = (
            "an enabled scope axis must sit on an enum field with values "
            "(the scope values are the field's enum values)"
        )
        return

    required_for = scope.get("required_for")
    if required_for is not None and (
        not isinstance(required_for, (list, tuple))
        or any(not isinstance(r, str) for r in required_for)
    ):
        reasons[dotted] = "scope.required_for must be a list of strings"


def _field_choice_values(spec: Mapping[str, Any]) -> set[str] | None:
    """The field's resolved CHOICE vocabulary, or ``None`` when it declares none.

    Reuses :func:`_field_enum_values` (the single ``options``/``choices`` reader the scope
    check already uses) and returns the choices as a set for subset membership checks. Returns
    ``None`` when the field is not an enum / declares no usable vocabulary — the caller treats
    an ``application_choices`` subset on such a field as a save error (you cannot subset a
    field that has no choices).
    """
    values = _field_enum_values(spec)
    return set(values) if values else None


def _validate_application_attrs(
    dotted: str,
    spec: Mapping[str, Any],
    reasons: dict[str, str],
    *,
    platform_required: bool,
) -> None:
    """Validate a field's APPLICATION attributes at Save (application-app R4c.3, fail-loud).

    The three write-time invariants this enforces, so a broken ``config#fields`` row is
    rejected at author time rather than projected (R4c.3):

    1. **enum application-subset ⊆ field choices (R4a.4)** — when ``application_choices`` is
       authored it must be a list whose every entry is a valid choice of the field's own
       resolved choice vocabulary (``options[].value`` / ``choices``). A subset entry that is
       not a field choice, or a subset on a field that declares no choices, is a save error.
    2. **``format.checker`` platform-known (R7.7)** — when a ``format`` object is authored it
       must be ``{checker, params?}`` with ``checker`` a PLATFORM-KNOWN token
       (:data:`PLATFORM_FORMAT_TOKENS`). An unknown/non-string checker, or a non-object
       ``format``, is rejected (a tenant attaches a known token, it cannot author a checker).
    3. **application-required cannot relax a platform-required field (R4c.3)** — a field that
       the platform marks ``required`` may not be made ``application_required = False`` on the
       public form; the public form can only ever TIGHTEN requiredness, never relax the
       platform floor (the SAM resolver stays the ultimate authority, but a relax is caught
       here fail-loud at Save).

    Appends a reason under ``dotted`` on any violation (batched; never raises here — the
    caller collects all reasons and raises one :class:`MembersConfigError`).
    """
    # 1) enum application-subset ⊆ field choices (R4a.4).
    subset = spec.get("application_choices")
    if subset is not None:
        if not isinstance(subset, (list, tuple)):
            reasons[dotted] = "application_choices must be a list"
        else:
            choices = _field_choice_values(spec)
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

    # 2) format.checker must be a platform-known token (R7.7).
    fmt = spec.get("format")
    if fmt is not None:
        if not isinstance(fmt, Mapping):
            reasons[dotted] = "format must be an object with a 'checker' token"
        else:
            checker = fmt.get("checker")
            if not isinstance(checker, str) or checker not in PLATFORM_FORMAT_TOKENS:
                known = ", ".join(sorted(PLATFORM_FORMAT_TOKENS))
                reasons[dotted] = (
                    f"format.checker {checker!r} is not a platform-known token "
                    f"(known: {known})"
                )

    # 3) application-required cannot relax a platform-required field (R4c.3).
    if platform_required and spec.get("application_required") is False:
        reasons[dotted] = (
            "application_required cannot relax a platform-required field "
            "(the public form may tighten requiredness, never loosen the platform floor)"
        )


def _catalog_keys(overlay: Mapping[str, Any]) -> set[str]:
    """The set of functional-group keys declared in an overlay's functional_groups catalog."""
    catalog = overlay.get("functional_groups") or []
    keys: set[str] = set()
    if isinstance(catalog, list):
        for entry in catalog:
            if isinstance(entry, Mapping):
                k = entry.get("key")
                if isinstance(k, str) and k:
                    keys.add(k)
    return keys


# ── field_overlay validation (reuse of FieldResolver._reject_invalid_overlay semantics) ─


def validate_field_overlay(overlay: Any) -> None:
    """Fail fast if a ``members.field_overlay`` object would violate a platform invariant.

    Mirrors ``FieldResolver._reject_invalid_overlay`` (SAM domain) plus the R4.9 catalog check:

    - an override target must be a known fixed/calculated field (dotted key);
    - a fixed override may not loosen a platform-required field (optional-only tightening);
    - a variable field key may not collide with a fixed/calculated canonical key;
    - an ``enum`` variable field must declare ``choices``;
    - every ``functional_group`` referenced (fixed override or variable field) must be present
      in the tenant's ``functional_groups`` catalog (checked only when a non-empty catalog is
      authored — an empty catalog uses base defaults, exactly like the domain resolver);
    - a field-level ``scope`` attribute (Phase 3 step 9, R2.1 / single-vocabulary R3.4) — the
      authoring representation that expresses "this field is a scope axis" — must be a
      well-formed scope object AND, when ENABLED, sit on an enum field with values (the scope
      values ARE the field's enum values; :func:`_validate_field_scope`), so a malformed or
      value-less scope axis never reaches the derived ``config#scope`` projection;
    - the per-field APPLICATION attributes (Member Application Form, R4c.3; carried onto both
      overlay fields and fixed overrides by task 8.1) — fail-loud at Save
      (:func:`_validate_application_attrs`): the enum ``application_choices`` subset must be ⊆
      the field's own choices (R4a.4), a ``format.checker`` must be a PLATFORM-KNOWN token
      (:data:`PLATFORM_FORMAT_TOKENS`, R7.7), and ``application_required`` may not relax a
      platform-required fixed field (R4c.3) — so a broken public-form config never projects.

    Raises :class:`MembersConfigError` (with a key → reason map) on any violation.
    """
    if overlay is None:
        return
    if not isinstance(overlay, Mapping):
        raise MembersConfigError({"field_overlay": "must be an object"})

    reasons: dict[str, str] = {}
    catalog = _catalog_keys(overlay)

    def _check_group(dotted: str, group: str | None) -> None:
        # Reference-validate only when the tenant authored a catalog (empty → base defaults).
        if group and catalog and group not in catalog:
            reasons[dotted] = (
                f"functional_group {group!r} is not in the functional_groups catalog"
            )

    # fixed_overrides — keyed by canonical dotted key of a fixed/calculated field.
    overrides = overlay.get("fixed_overrides") or {}
    if isinstance(overrides, Mapping):
        for dotted, spec in overrides.items():
            if dotted not in _BASE_DOTTED_KEYS:
                reasons[dotted] = (
                    "overrides an unknown field "
                    "(only fixed/calculated fields may be overridden)"
                )
                continue
            if isinstance(spec, Mapping):
                if spec.get("required") is False and dotted in _REQUIRED_FIXED_KEYS:
                    reasons[dotted] = (
                        "cannot make a platform-required fixed field optional"
                    )
                _check_group(dotted, spec.get("functional_group"))
                if _FIELD_SCOPE_ATTR in spec:
                    _validate_field_scope(dotted, spec, reasons)
                # Application attributes (R4c.3): a FIXED override may carry the four public-form
                # attrs. A fixed field the platform marks required cannot be relaxed on the form.
                _validate_application_attrs(
                    dotted,
                    spec,
                    reasons,
                    platform_required=dotted in _REQUIRED_FIXED_KEYS,
                )

    # fields — the added variable fields, keyed by canonical key (lands under `overlay`).
    fields = overlay.get("fields") or {}
    if isinstance(fields, Mapping):
        for name, spec in fields.items():
            key = (spec.get("key") if isinstance(spec, Mapping) else None) or name
            dotted = f"{OVERLAY_GROUP}.{key}"
            if key in _BASE_BARE_KEYS:
                reasons[dotted] = (
                    "variable field key collides with a fixed/calculated field key"
                )
            elif (
                isinstance(spec, Mapping)
                and spec.get("type") == "enum"
                and not spec.get("choices")
                and not spec.get("options")
            ):
                reasons[dotted] = "an enum variable field must declare choices/options"
            if isinstance(spec, Mapping):
                _check_group(dotted, spec.get("functional_group"))
                if _FIELD_SCOPE_ATTR in spec:
                    _validate_field_scope(dotted, spec, reasons)
                # Application attributes (R4c.3): an added variable field is never a
                # platform-required field, so only the subset ⊆ choices + known-checker
                # invariants apply (platform_required=False).
                _validate_application_attrs(
                    dotted, spec, reasons, platform_required=False
                )

    if reasons:
        raise MembersConfigError(reasons)
