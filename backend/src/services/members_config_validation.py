"""
s5c Task 2.4 — authoritative save-time validation for the ``members.*`` parameters
(Flask/MySQL plane; design C-SCHEMA / C-VIEW, Property 7 fail-fast).

This is the Flask-plane guard that runs on a PUT of a ``members.*`` parameter *before*
the value is stored, so a bad config never corrupts the projected tenant config:

- **``members.field_overlay``** — reuses the SAM-domain ``FieldResolver._reject_invalid_overlay``
  semantics (fail-fast): reject an override of an unknown field key, a variable field colliding
  with a fixed/calculated key, an enum variable field with no choices, and — the s5c addition
  (R4.9) — any ``functional_group`` (on a fixed override or a variable field) that is not present
  in the tenant's ``functional_groups`` catalog. It also rejects loosening a platform-required
  fixed field (optional-only tightening).

Cross-plane reuse decision (task 2.4 guidance)
----------------------------------------------
The task asks us to *prefer reuse* of the SAM-domain resolver, and to reimplement the minimal
equivalent (referencing the same contract) only if a cross-plane import is not clean. **We
reimplement here**, because:

- The two planes are independently deployed and packaged: the Flask/MySQL app (``backend/src``,
  Railway) and the SAM module (``sam/members``, Lambda) have **separate** Python paths, pytest
  configs, and dependency trees. ``backend/src`` does not (and must not) place ``sam`` on its
  import path — importing ``sam.members.domain.field_resolver`` into the Flask runtime would
  couple the Railway service to the Lambda package and drag SAM's dependencies into Flask.
- The projection layer already re-expresses these same overlay/scope shapes on the Flask plane
  (``projection_sync.py`` reads ``members.*`` and builds ``config#fields`` / ``config#scope``);
  a small, self-contained validator here is consistent with that boundary.

To keep the two implementations honest, the platform base field-key set below is a **direct
transcription** of the canonical keys in ``sam/members/domain/fixed_fields.py`` +
``calculated_fields.py`` (the single source of truth for field names). The rejection is
fail-fast with a descriptive :class:`MembersConfigError` (mirroring ``OverlayError`` /
``FieldValidationError``) and never mutates or stores the config.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

__all__ = [
    "CALCULATED_FIELD_KEYS",
    "FIXED_FIELD_KEYS",
    "OVERLAY_GROUP",
    "MembersConfigError",
    "fold_field_overlay_labels",
    "fold_members_param",
    "validate_default_page_size",
    "validate_field_overlay",
    "validate_mail_certified",
    "validate_mail_domain",
    "validate_mail_local_part",
    "validate_members_param",
]


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
    all reasons and raises once, mirroring the batched ``MembersConfigError``).
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
      value-less scope axis never reaches the derived ``config#scope`` projection.

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

    if reasons:
        raise MembersConfigError(reasons)


# ── mail config validation (R4 / §5f — per-tenant From + certification gate) ──────────
#
# These three params feed the config#mail projection (design Data Models): the Members send
# path composes the envelope From as "<mail_local_part|noreply>@<mail_domain>" and reads
# mail_certified as the fail-closed pre-send gate. We validate the AUTHORED shape here so a
# malformed domain / local-part never reaches the projection (where it would silently produce
# a broken sender). All three are OPTIONAL params: an unset/empty value is accepted (the From
# simply cannot be composed until a domain is authored; mail_local_part defaults to "noreply"
# in the schema; mail_certified is absent → the pre-send gate fails closed, no send).

#: A bare DNS domain: one or more dot-separated labels, each 1–63 chars of letters/digits/
#: hyphens (not leading/trailing a hyphen), with a final alphabetic TLD label. No scheme, no
#: "@", no path, no whitespace — the From is composed from "<local_part>@<domain>".
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)

#: An email local-part token: letters/digits and the common unquoted-local-part punctuation,
#: no "@" and no whitespace. Kept conservative on purpose (generic addresses like "noreply",
#: "info", "onderhoud") — not the full RFC 5321 quoted-string grammar.
_LOCAL_PART_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$")


def _is_blank(value: Any) -> bool:
    """A None or empty/whitespace-only string counts as 'unset' for an optional mail param."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_mail_domain(value: Any) -> None:
    """Fail fast if ``members.mail_domain`` is not a bare DNS domain (R4, §5f).

    Accepts an unset/empty value (optional param). Otherwise the value must be a string that
    is a bare domain (e.g. ``h-dcn.nl``) — no scheme, no ``@``, no path, no whitespace — since
    the send path composes the From as ``<mail_local_part|noreply>@<mail_domain>`` and never
    projects a literal address.

    Raises :class:`MembersConfigError` (``{"mail_domain": reason}``) on any violation.
    """
    if _is_blank(value):
        return
    if not isinstance(value, str):
        raise MembersConfigError({"mail_domain": "must be a string (a bare domain)"})
    domain = value.strip()
    if "@" in domain or "/" in domain or "://" in domain:
        raise MembersConfigError(
            {"mail_domain": "must be a bare domain (no '@', scheme or path)"}
        )
    if not _DOMAIN_RE.match(domain):
        raise MembersConfigError(
            {"mail_domain": f"{value!r} is not a valid domain (e.g. 'h-dcn.nl')"}
        )


def validate_mail_local_part(value: Any) -> None:
    """Fail fast if ``members.mail_local_part`` is not a single local-part token (R4, §5f).

    Accepts an unset/empty value (optional param — the schema default is ``noreply``).
    Otherwise the value must be a string with no ``@`` and no whitespace (e.g. ``info``,
    ``onderhoud``), since it becomes the part before ``@`` in the composed From.

    Raises :class:`MembersConfigError` (``{"mail_local_part": reason}``) on any violation.
    """
    if _is_blank(value):
        return
    if not isinstance(value, str):
        raise MembersConfigError({"mail_local_part": "must be a string"})
    local = value.strip()
    if "@" in local or any(ch.isspace() for ch in local):
        raise MembersConfigError(
            {
                "mail_local_part": "must be a single local-part token (no '@' or whitespace)"
            }
        )
    if not _LOCAL_PART_RE.match(local):
        raise MembersConfigError(
            {"mail_local_part": f"{value!r} is not a valid email local-part"}
        )


def validate_mail_certified(value: Any) -> None:
    """Fail fast if ``members.mail_certified`` is not a boolean (R4, §5f, Option B).

    Accepts an unset/None value (optional param → the pre-send gate fails closed, no send).
    Otherwise the value must be a real ``bool`` — the fail-closed pre-send certification gate
    reads it, so an ambiguous truthy string (``"false"``) must NOT be stored as if it were
    certified.

    Raises :class:`MembersConfigError` (``{"mail_certified": reason}``) on any violation.
    """
    if value is None:
        return
    if not isinstance(value, bool):
        raise MembersConfigError({"mail_certified": "must be a boolean (true/false)"})


# ── default_page_size validation (R2.1, R2.6 — a positive-int tenant DEFAULT) ──────────
#
# Phase 2 re-homes pagination (`view_contexts[*].page_size`) to ONE tenant-level scalar
# `members.default_page_size` — a DEFAULT, not a stored view object (steering 38 rule 3).
# The resolver's positive-integer guarantee (requirements Property 1) must hold at the
# SOURCE too: a non-positive or non-integer default is rejected here on the authoring
# (Flask writer) path, so an invalid default never reaches the projection. The param is
# OPTIONAL — an unset/None value is accepted (the table toolkit's own default applies).


def validate_default_page_size(value: Any) -> None:
    """Fail fast if ``members.default_page_size`` is not a positive integer (R2.1, R2.6).

    Accepts an unset/None value (optional param → the table toolkit's own default applies).
    Otherwise the value must be a positive ``int`` (> 0): a boolean, a float, a string, or a
    non-positive integer (0 or negative) is rejected, so the served tenant default can only
    ever be a positive rows-per-page — honouring the resolver's positive-integer guarantee at
    the authoring source. This is a tenant/field DEFAULT, not a stored view object
    (``38-sam-module-field-config.md`` rule 3).

    Raises :class:`MembersConfigError` (``{"default_page_size": reason}``) on any violation.
    """
    if value is None:
        return
    # bool is a subclass of int — reject it explicitly so True/False is never stored as 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise MembersConfigError(
            {"default_page_size": "must be a positive integer"}
        )
    if value <= 0:
        raise MembersConfigError(
            {"default_page_size": f"must be a positive integer (got {value})"}
        )


# ── tenant-label fold: per-locale editor inputs → inline {nl,en,…} dict (R3.2) ─────────
#
# Phase-1 i18n Option (b), design §3: a tenant-authored field/group/enum-option label is
# runtime DATA stored as an inline per-language dict ``{nl, en, …}``. The Flask authoring
# editor (``members_parameters.json`` field_def) presents that as ONE text input per
# supported locale, keyed ``label_<locale>`` (``label_nl`` / ``label_en`` / … ) — the
# former two hardcoded ``label_en``/``label_nl`` inputs, now locale-generic. The SAM-plane
# consumers (``field_resolver`` ``OverlayField``/``FixedFieldOverride``/``FunctionalGroup``)
# and the governance projection builders (``_projection_config_builders._map_*``) read a
# single inline ``label`` dict. This fold is the single bridge point that assembles the
# per-locale inputs into that ``label`` dict on save, BEFORE the overlay is stored — so the
# stored (and therefore served) shape stays the ``{nl,en,…}`` dict (R2.2, shape unchanged).

#: An editor per-locale label input key: ``label_<locale>`` (e.g. ``label_nl``, ``label_en``,
#: ``label_de``). Locale-generic by construction — adding a language needs no code change here
#: (R3.6); the locale segment is the trailing token. ``label`` itself (the folded dict) is NOT
#: matched (no trailing ``_<locale>``), so an already-folded overlay passes through untouched.
_LOCALE_INPUT_RE = re.compile(r"^label_([A-Za-z][A-Za-z0-9-]*)$")


def _fold_entry_labels(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Fold a single field-def entry's per-locale ``label_<locale>`` inputs into ``label``.

    Returns a NEW dict (never mutates ``entry``). Any ``label_<locale>`` key with a string
    value is removed and its value placed under ``label[<locale>]``. An existing inline
    ``label`` dict is preserved and MERGED into (a per-locale input WINS for its own locale,
    so re-authoring one language updates just that key). An entry carrying neither a
    per-locale input nor a ``label`` dict is returned unchanged (shape preserved). A
    ``label_<locale>`` whose value is not a string (an authoring quirk) is dropped from the
    output rather than folded, so the stored ``label`` dict stays ``{str: str}``.
    """
    folded: dict[str, Any] = {}
    label: dict[str, str] = {}

    # Seed from an already-present inline label dict (backward-compatible round-trip).
    existing = entry.get("label")
    if isinstance(existing, Mapping):
        for loc, text in existing.items():
            if isinstance(loc, str) and isinstance(text, str):
                label[loc] = text

    saw_locale_input = False
    for key, value in entry.items():
        match = _LOCALE_INPUT_RE.match(key) if isinstance(key, str) else None
        if match:
            saw_locale_input = True
            if isinstance(value, str):
                label[match.group(1)] = value
            # Non-string per-locale input: drop it (don't carry label_<locale> through).
            continue
        if key == "label":
            # Replaced by the merged `label` below; skip the raw copy.
            continue
        folded[key] = value

    # Only (re)attach a `label` dict when there is something to carry, OR the entry already
    # had an inline label dict — so an entry with no label at all stays label-free.
    if label or (isinstance(existing, Mapping) and not saw_locale_input):
        folded["label"] = label
    elif isinstance(existing, Mapping):
        # existing was present but empty and no inputs: preserve the (empty) dict shape.
        folded["label"] = label

    return folded


def _fold_entry_map(raw: Any) -> Any:
    """Fold labels for every value in a ``map<field_def>`` ({key: entry}); copy otherwise."""
    if not isinstance(raw, Mapping):
        return raw
    out: dict[str, Any] = {}
    for name, entry in raw.items():
        out[name] = _fold_entry_labels(entry) if isinstance(entry, Mapping) else entry
    return out


def _fold_entry_list(raw: Any) -> Any:
    """Fold labels for every entry in a ``list<object>``; copy otherwise."""
    if not isinstance(raw, (list, tuple)):
        return raw
    return [
        _fold_entry_labels(entry) if isinstance(entry, Mapping) else entry
        for entry in raw
    ]


def fold_field_overlay_labels(overlay: Any) -> Any:
    """Fold per-locale editor label inputs across a ``members.field_overlay`` object (R3.2).

    Returns a NEW overlay object (never mutates the input) in which every authored
    field-def entry — the ``functional_groups`` catalog (list), the added ``fields`` map,
    and the ``fixed_overrides`` map — has its per-locale ``label_<locale>`` inputs folded
    into a single inline ``label`` ``{nl, en, …}`` dict (design §3). All other keys/shapes
    are carried through unchanged, so the folded overlay is byte-for-byte the same as the
    input except for the label assembly — keeping the stored (and served) shape the inline
    dict the SAM resolver and the projection builders already consume (R2.2).

    Idempotent: an overlay whose labels are ALREADY inline ``{nl,en}`` dicts (no
    ``label_<locale>`` inputs) is returned structurally unchanged — so re-folding a stored
    overlay is a no-op (round-trip stable).
    """
    if not isinstance(overlay, Mapping):
        return overlay

    folded = dict(overlay)
    if "functional_groups" in folded:
        folded["functional_groups"] = _fold_entry_list(folded["functional_groups"])
    if "fields" in folded:
        folded["fields"] = _fold_entry_map(folded["fields"])
    if "fixed_overrides" in folded:
        folded["fixed_overrides"] = _fold_entry_map(folded["fixed_overrides"])
    return folded


def fold_members_param(key: str, value: Any) -> Any:
    """Fold per-locale label inputs for one ``members.<key>`` value on save (R3.2).

    The save-path pre-store transform companion to :func:`validate_members_param`: for the
    keys whose authored shape carries tenant labels (currently ``field_overlay``), assemble
    the editor's per-locale ``label_<locale>`` inputs into the stored inline ``{nl,en,…}``
    dict. For every other key the value is returned unchanged. Never mutates the input;
    returns the value to store.
    """
    if key == "field_overlay":
        return fold_field_overlay_labels(value)
    return value


# ── dispatch entry point used by the parameter save path ───────────────────────────────


def validate_members_param(
    key: str,
    value: Any,
) -> None:
    """Validate one ``members.<key>`` value on save; no-op for keys with no save-time rule.

    Dispatches to the per-key validator:
    - ``field_overlay``    → :func:`validate_field_overlay`
    - ``mail_domain``       → :func:`validate_mail_domain`
    - ``mail_local_part``   → :func:`validate_mail_local_part`
    - ``mail_certified``    → :func:`validate_mail_certified`
    - ``default_page_size`` → :func:`validate_default_page_size`

    ``scope_dimensions`` has no cross-reference rule of its own here (its internal shape is
    validated by the SAM ``ScopeConfig`` on read); a PUT of it is accepted as-is. Raises
    :class:`MembersConfigError` on any violation; returns None otherwise.
    """
    if key == "field_overlay":
        validate_field_overlay(value)
    elif key == "mail_domain":
        validate_mail_domain(value)
    elif key == "mail_local_part":
        validate_mail_local_part(value)
    elif key == "mail_certified":
        validate_mail_certified(value)
    elif key == "default_page_size":
        validate_default_page_size(value)
