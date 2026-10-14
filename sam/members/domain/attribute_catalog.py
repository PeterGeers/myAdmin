"""
Phase 1 — Catalog Backbone: the canonical attribute catalog (design §1, §2).

This module is the ONE new domain artifact of the Members config redesign Phase 1: a pure,
import-time-safe description of the member field model, assembled FROM the existing registries
(``fixed_fields.FIXED_FIELDS`` / ``calculated_fields.CALCULATED_FIELDS``) rather than becoming a
second, hand-maintained source of truth (design D1 — avoid the Phase-0 drift class).

It is deliberately **storage-agnostic** (no DynamoDB, no boto3) and **tenant-agnostic**
(no ``if tenant == ...``) — it loads like ``fixed_fields.py`` does, with nothing but constants and
pure functions, so a drift test can import it beside the registries in one process.

Task 1.1 (this change) establishes the first piece: the **base functional-group set**
(:data:`BASE_FUNCTIONAL_GROUPS`). The attribute vocabulary, the computed field inventory, and
``build_attribute_catalog()`` follow in later Phase-1 tasks (design §2–§6).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from .field_resolver import FunctionalGroup

__all__ = [
    "ATTRIBUTE_VOCABULARY",
    "BASE_FUNCTIONAL_GROUPS",
    "AttributeApplies",
    "AttributeCatalog",
    "AttributeSpec",
    "CatalogField",
]


#: The base functional (display) group set every tenant starts with (design §4, R5.1).
#:
#: A functional group is the parameter-driven DISPLAY section a field is shown under — orthogonal
#: to the STORAGE bucket (``personal`` / ``membership`` / ``overlay``, fixed by origin). These four
#: are the platform defaults: they cover every ``functional_group`` the fixed/calculated registries
#: reference or imply — ``personal`` + ``membership`` (storage-group fallbacks via
#: ``default_functional_group()``), ``administrative`` (explicitly named by the system-timestamp
#: fields), and ``address`` (the display group the address fixed fields are moved into, named in
#: ``fixed_fields.py`` and the seed fixture).
#:
#: It is the single base-group definition for the module (``seed_overlay.SEED_FUNCTIONAL_GROUPS`` is
#: reconciled against it in task 1.2); a tenant's authored catalog EXTENDS/overrides it (base ⊕
#: tenant; design §4 merge rule). Pure and import-time safe — a frozen tuple of frozen
#: :class:`FunctionalGroup` dataclasses, so it carries no mutable module-level state.
BASE_FUNCTIONAL_GROUPS: tuple[FunctionalGroup, ...] = (
    FunctionalGroup(key="personal", label={"nl": "Persoonlijk", "en": "Personal"}, order=1),
    FunctionalGroup(key="address", label={"nl": "Adres", "en": "Address"}, order=2),
    FunctionalGroup(key="membership", label={"nl": "Lidmaatschap", "en": "Membership"}, order=3),
    FunctionalGroup(
        key="administrative",
        label={"nl": "Administratie", "en": "Administrative"},
        order=4,
    ),
)


# ── The catalog data model (design §2) ────────────────────────────────────────────────
#
# Task 2.1 (this change) adds the four frozen, pure dataclasses that make up the catalog
# vocabulary + shape. They are DECLARATIONS only — the attribute vocabulary itself (one
# ``AttributeSpec`` per supported attribute, task 2.2), the computed field inventory, and
# ``build_attribute_catalog()`` (task 3) follow. The model carries NO Members-only concept in
# its SHAPE (R9.1): it is a generic field-definition model (attribute vocabulary + computed
# inventory + base group set + the recorded label rule). Frozen because the catalog is a
# constant shared by every tenant; pure + import-time safe (no DynamoDB/boto3), mirroring
# ``fixed_fields.py``.


class AttributeApplies(str, Enum):
    """Which field **origin** an attribute (or a computed field) applies to (design §2).

    Mirrors ``field_resolver.FieldOrigin`` by VALUE (``fixed`` / ``calculated`` / ``variable``)
    so the catalog speaks the same origin vocabulary as the resolver, but it is the catalog's
    own type — the catalog is a derived VIEW, it does not import the resolver's origin enum into
    its public shape. A ``str`` enum so a value compares/serializes as its plain string.
    """

    FIXED = "fixed"
    CALCULATED = "calculated"
    VARIABLE = "variable"


@dataclass(frozen=True)
class AttributeSpec:
    """One attribute a field definition may carry — the vocabulary entry (design §2, R1.1).

    This describes the SHAPE of a field definition (``key``/``type``/``label``/…), NOT a member
    value: ``required`` means "required for a field DEFINITION", not "the member must supply a
    value". ``applies_to`` records which origins may carry the attribute; ``tenant_authorable``
    splits a tenant-settable attribute (``label``/``visible``/``order``/``functional_group``)
    from a platform-fixed one (a fixed field's ``type``; a calculated field's ``required``).
    ``required_when`` encodes a CONDITIONAL requirement as ``((attr, value), …)`` — e.g.
    ``(("type", "enum"),)`` makes ``choices``/``options`` required for an enum field (R1.3,
    mirroring ``FieldResolver._reject_invalid_overlay``'s choiceless-enum rejection). ``note`` is
    human doc surfaced to the authoring UI (and marks ``scope_binding``/``alias`` as Phase-3-wired,
    R8). Frozen — a vocabulary entry is a shared constant, never mutated in place.
    """

    key: str
    value_type: str
    required: bool
    applies_to: tuple[AttributeApplies, ...]
    tenant_authorable: bool
    required_when: tuple[tuple[str, str], ...] = ()
    note: str = ""


@dataclass(frozen=True)
class CatalogField:
    """One base field as the catalog sees it — COMPUTED from the registries, never hand-typed.

    This is the catalog's projection of a shipped ``FixedField`` / ``CalculatedField`` (design §2,
    R1.4): every attribute here is read via the SAME accessors the resolver uses
    (``dotted_key()``, ``type.value``, ``required``, ``label``, ``default_functional_group()``,
    ``order``, ``read_only``) so the inventory stays single-sourced and drift-guarded (R7.2) —
    NO field name or label is re-typed. Variable (tenant) fields are tenant DATA, not part of the
    base inventory, so ``origin`` here is only ``fixed`` or ``calculated``. ``storage_group`` is
    the structural bucket (``personal`` / ``membership``), orthogonal to the display
    ``functional_group``. Frozen — a computed constant.
    """

    dotted_key: str
    key: str
    origin: AttributeApplies
    storage_group: str
    type: str
    required: bool
    label: Mapping[str, str]
    functional_group: str
    order: int
    read_only: bool


@dataclass(frozen=True)
class AttributeCatalog:
    """The canonical attribute catalog: the vocabulary + the computed inventory + the base groups.

    The ONE first-class artifact Phase 1 produces (design §2, R1): the attribute ``vocabulary``
    (R1), the base ``fields`` inventory computed from the registries (R1.4/R7.2), the BASE
    functional-group set (R5, reusing the existing :class:`FunctionalGroup` dataclass), and the
    recorded i18n label rule (R3.7 — the whole rule lives IN the artifact, not in folklore).

    The label rule is recorded as THREE first-class fields so a consumer reads the COMPLETE i18n
    convention off the artifact (task 5.7, R3.7): ``label_convention`` (the convention name —
    ``"i18n-keys+tenant-inline-override"``), ``label_fallback_order`` (the deterministic
    locale-independent fallback tail ``("en", "nl")``, applied after the active locale — R3.5), and
    ``label_key_scheme`` (the :class:`LabelKeyScheme` shipped-label resource-key templates — the
    task-5.1 ``admin:membersConfig.field/group/enum`` scheme). The two newer fields default to the
    empty/``None`` neutral so a hand-constructed catalog (the task-2.1/3.1 shape tests) stays valid;
    :func:`build_attribute_catalog` always populates all three from the module constants.

    Frozen so the assembled catalog is an immutable value a drift test can hold and compare.
    """

    attributes: tuple[AttributeSpec, ...]
    fields: tuple[CatalogField, ...]
    functional_groups: tuple[FunctionalGroup, ...]
    label_convention: str
    label_fallback_order: tuple[str, ...] = ()
    label_key_scheme: LabelKeyScheme | None = None


# ── The attribute vocabulary (design §2 table; R1.1/R1.2/R1.5/R8.1) ────────────────────
#
# Task 2.2 (this change): ONE :class:`AttributeSpec` per attribute the member field model
# carries TODAY, derived 1:1 from what ``FixedField`` / ``CalculatedField`` / ``OverlayField`` /
# ``FixedFieldOverride`` expose (``fixed_fields.py`` / ``calculated_fields.py`` /
# ``field_resolver.py``), transcribed to match the design §2 table row-for-row. This is the one
# genuinely new, hand-written piece of the catalog (the field INVENTORY is computed from the
# registries, task 3) — it describes the SHAPE of a field definition, which is code-defined, not
# tenant data (design §1). It is tiny and stable; `build_attribute_catalog()` (task 3.2) runs a
# duplicate-key fail-fast over it like the registries do.
#
# Conventions encoded here, straight from the §2 table:
#  - ``required`` is "required for a field DEFINITION", never "the member must supply a value".
#  - ``applies_to`` records which field ORIGINS may carry the attribute (fixed/calculated/variable).
#  - ``tenant_authorable`` splits a tenant-settable attribute (label/visible/order/
#    functional_group/…) from a platform-fixed one (a fixed field's ``type``; a calculated field's
#    ``required``; ``calculated_from``). Where the table splits authorability by origin
#    ("no for fixed/calc; yes for variable"), the vocabulary records the broadest tenant-authorable
#    stance (``tenant_authorable=True``) and the ``note`` documents the per-origin nuance — the
#    per-origin platform-fixed values are pinned by the computed inventory + drift guard (task 3),
#    not re-encoded as a second rule here.
#  - ``required_when=(("type","enum"),)`` on ``choices``/``options`` encodes the R1.3 enum rule
#    (an enum field must declare its values), mirroring ``FieldResolver._reject_invalid_overlay``'s
#    choiceless-enum rejection. The ONE documented EXCEPTION (resolver S5j / design D1a): an enum
#    bound to a SCOPE DIMENSION — its key present in the tenant's scope vocabulary
#    (``scope_dimensions.values``) — legitimately carries no inline ``choices``/``options`` because
#    it sources its values from that dimension; the resolver treats it as if it declared those
#    choices, so it is NOT a config bug. Each spec's ``note`` records this exception verbatim.
#  - ``scope_binding`` + ``alias`` are DECLARED here (R8.1) but their ``note`` states plainly they
#    are wired in Phase 3 (resolver/render), not Phase 1 (R8.2/R8.3) — forward-compat only.
ATTRIBUTE_VOCABULARY: tuple[AttributeSpec, ...] = (
    AttributeSpec(
        key="key",
        value_type="string",
        required=True,
        applies_to=(
            AttributeApplies.FIXED,
            AttributeApplies.CALCULATED,
            AttributeApplies.VARIABLE,
        ),
        tenant_authorable=False,
        note="The canonical field key (identity) — never tenant-authored.",
    ),
    AttributeSpec(
        key="type",
        value_type="enum",
        required=True,
        applies_to=(
            AttributeApplies.FIXED,
            AttributeApplies.CALCULATED,
            AttributeApplies.VARIABLE,
        ),
        tenant_authorable=True,
        note=(
            "FieldType value (string|date|enum|reference). Platform-fixed for fixed/calculated "
            "fields; a tenant chooses the type only for a variable (overlay) field."
        ),
    ),
    AttributeSpec(
        key="required",
        value_type="bool",
        required=False,
        applies_to=(AttributeApplies.FIXED, AttributeApplies.VARIABLE),
        tenant_authorable=True,
        note=(
            "Required for a field DEFINITION (not the member value); default false. A tenant may "
            "only TIGHTEN a fixed field (optional→required), never loosen; a calculated field is "
            "always read-only / never required."
        ),
    ),
    AttributeSpec(
        key="label",
        value_type="i18n",
        required=True,
        applies_to=(
            AttributeApplies.FIXED,
            AttributeApplies.CALCULATED,
            AttributeApplies.VARIABLE,
        ),
        tenant_authorable=True,
        note="Localized {nl,en,…} display label; tenant inline value overrides the resource-key default (§3).",
    ),
    AttributeSpec(
        key="visible",
        value_type="bool",
        required=False,
        applies_to=(
            AttributeApplies.FIXED,
            AttributeApplies.CALCULATED,
            AttributeApplies.VARIABLE,
        ),
        tenant_authorable=True,
        note="Default true; a tenant may hide a field.",
    ),
    AttributeSpec(
        key="order",
        value_type="int",
        required=False,
        applies_to=(
            AttributeApplies.FIXED,
            AttributeApplies.CALCULATED,
            AttributeApplies.VARIABLE,
        ),
        tenant_authorable=True,
        note="Default 0; within-group display order (§5 ordering contract).",
    ),
    AttributeSpec(
        key="functional_group",
        value_type="string",
        required=False,
        applies_to=(
            AttributeApplies.FIXED,
            AttributeApplies.CALCULATED,
            AttributeApplies.VARIABLE,
        ),
        tenant_authorable=True,
        note=(
            "Reference to a functional (display) group key; absent → the base default via "
            "default_functional_group(). Validated against BASE_FUNCTIONAL_GROUPS ⊕ the tenant catalog (§4)."
        ),
    ),
    AttributeSpec(
        key="choices",
        value_type="list",
        required=False,
        applies_to=(AttributeApplies.FIXED, AttributeApplies.VARIABLE),
        tenant_authorable=True,
        required_when=(("type", "enum"),),
        note=(
            "The simple value list of an enum field; required when type == enum (R1.3), mirroring "
            "FieldResolver._reject_invalid_overlay's choiceless-enum rejection "
            "(`an enum variable field must declare choices/options`). "
            "EXCEPTION (resolver S5j / design D1a): a scope-dimension-backed enum — whose key is "
            "present in the tenant's scope vocabulary (scope_dimensions.values) — legitimately "
            "carries NO inline choices/options because it sources its values from that dimension, "
            "and is NOT a config bug. The resolver treats such a field as if it declared those "
            "choices; the required_when rule here is the inline-values default, read with that "
            "same exception by any consumer that enforces it."
        ),
    ),
    AttributeSpec(
        key="options",
        value_type="list",
        required=False,
        applies_to=(AttributeApplies.FIXED, AttributeApplies.VARIABLE),
        tenant_authorable=True,
        required_when=(("type", "enum"),),
        note=(
            "The rich enum-option form {value,label,roles?}; required when type == enum (R1.3), "
            "mirroring FieldResolver._reject_invalid_overlay's choiceless-enum rejection. "
            "Same EXCEPTION as `choices` (resolver S5j / design D1a): a scope-dimension-backed "
            "enum (key present in the tenant's scope vocabulary) sources its values from that "
            "dimension and is exempt from needing inline choices/options. "
            "An option's canonical `value` is language-neutral — only its `label` is per-language (§3)."
        ),
    ),
    AttributeSpec(
        key="show_when",
        value_type="object",
        required=False,
        applies_to=(
            AttributeApplies.FIXED,
            AttributeApplies.CALCULATED,
            AttributeApplies.VARIABLE,
        ),
        tenant_authorable=True,
        note="Per-field conditional-visibility condition; a hidden field is not required server-side.",
    ),
    AttributeSpec(
        key="member_number_format",
        value_type="object",
        required=False,
        applies_to=(AttributeApplies.FIXED,),
        tenant_authorable=True,
        required_when=(("key", "member_number"),),
        note=(
            "Tenant member-number format constraint (prefix+width or regex); only meaningful for the "
            "member_number fixed field. Validates a PRESENT value only — no generation, no uniqueness guard."
        ),
    ),
    AttributeSpec(
        key="calculated_from",
        value_type="list",
        required=False,
        applies_to=(AttributeApplies.CALCULATED,),
        tenant_authorable=False,
        note=(
            "The fixed-field inputs a calculated field derives from (the registry's `inputs`); a "
            "read-only, platform-owned output attribute — never tenant-authored."
        ),
    ),
    AttributeSpec(
        key="scope_binding",
        value_type="bool",
        required=False,
        applies_to=(AttributeApplies.FIXED, AttributeApplies.VARIABLE),
        tenant_authorable=True,
        note=(
            "DECLARED ONLY in Phase 1 (R8.1). Default false. Wired into the resolver (and render) "
            "in Phase 3 — not consumed by any Phase-1 runtime path (R8.2/R8.3). Phase-3 open "
            "question (R8.3): how filtering is derived from the flag — the catalog is forward-"
            "compatible with either resolution."
        ),
    ),
    AttributeSpec(
        key="alias",
        value_type="i18n",
        required=False,
        applies_to=(
            AttributeApplies.FIXED,
            AttributeApplies.CALCULATED,
            AttributeApplies.VARIABLE,
        ),
        tenant_authorable=True,
        note=(
            "An optional per-language ({nl,en,…}) alias a tenant may pin ON a field. It is a "
            "label-variant-style attribute carried on the SAME config#fields row — it introduces "
            "NO new members.* param (there never was one; `38` rule 3 / R3.4) — and it changes an "
            "alternate name a tenant gives a field, not the field's rendered display label."
        ),
    ),
)


# ── The computed field inventory + catalog assembly (design §2 "field inventory", §6) ──
#
# Task 3.1 (this change): ``build_attribute_catalog()`` — the pure function that projects the
# shipped registries (``FIXED_FIELDS`` then ``CALCULATED_FIELDS``) into the catalog's
# :class:`CatalogField` inventory and assembles the :class:`AttributeCatalog`.
#
# The field inventory is COMPUTED, never hand-typed (design D1 / R1.4): each ``CatalogField`` is
# read via the SAME accessors the resolver uses to build a ``ResolvedField`` — so the catalog
# cannot drift from the registries, and NO field name or label string is re-typed here. The
# per-origin platform-fixed values mirror the resolver exactly:
#   * fixed field    → origin FIXED,       required = f.required,  read_only = False
#   * calculated     → origin CALCULATED,   required = False,       read_only = True
# (the resolver pins a calculated field's ``required=False`` + ``read_only=True`` unconditionally;
# ``CalculatedField`` exposes no ``required``/``read_only`` accessor, so these are the platform
# constants its projection carries — see ``FieldResolver._as_calculated_field``). ``type`` is the
# ``FieldType`` value (``type.value``), ``storage_group`` the structural bucket (``group.value``),
# and ``functional_group`` the base display group via ``default_functional_group()`` — the same
# accessors the resolver reads.
#
# The attribute vocabulary (``attributes``) and the base group set (``functional_groups``) are the
# already-authored constants; ``label_convention`` records the Phase-1 i18n rule in the artifact
# (R3.7). Import-time self-validation (duplicate / dangling-group / enum-rule fail-fast) is task
# 3.2 and is layered onto this function next; task 3.1 builds the inventory + assembles the catalog.
#
# Pure + import-time safe (no DynamoDB/boto3): it reads only the in-process registry constants.

from .calculated_fields import CALCULATED_FIELDS, CalculatedField
from .fixed_fields import FIXED_FIELDS, FieldType, FixedField

#: The i18n label rule recorded IN the catalog artifact (R3.7, design §3): resource-key defaults
#: for shipped labels, overridden by a tenant's inline per-language dict; the authoring UI and the
#: save-time validator read this rule from the artifact, not from folklore.
LABEL_CONVENTION = "i18n-keys+tenant-inline-override"

#: The deterministic missing-locale fallback order recorded in the artifact (R3.5, design §3):
#: a label with no value for the active locale falls back ``active → en → nl → the canonical key``,
#: never blank. Recorded here (not folklore) so the authoring UI, the serializer, and the frontend
#: ``resolveLabel`` resolve a missing locale the SAME way. The leading ``active`` locale is supplied
#: at render by the caller; the catalog pins the TAIL that is locale-independent (``en`` then ``nl``
#: then the key). Kept as a tuple so a consumer can read the chain off the artifact.
LABEL_FALLBACK_ORDER: tuple[str, ...] = ("en", "nl")


@dataclass(frozen=True)
class LabelKeyScheme:
    """The shipped-label i18n resource-key scheme, recorded IN the artifact (R3.7, design §3).

    The i18n convention is not just a precedence rule — it is also WHERE a shipped label's default
    text lives: a resource key under the frontend ``admin`` namespace, ``membersConfig`` category,
    shaped per field / group / enum option (task 5.1, conforming to ``TRANSLATION_KEY_CONVENTIONS.md``
    + steering ``32``). Recording the scheme on the catalog means a consumer reads the WHOLE i18n
    rule off the artifact (R3.7) — the convention name, the fallback order, AND the key templates —
    rather than re-deriving the key shape from folklore or the frontend resource files.

    The three templates use ``{field_key}`` / ``{group_key}`` / ``{option_value}`` placeholders a
    consumer fills with the canonical (``snake_case``) field key / group key / enum option value —
    the ONE deliberate deviation from the convention's camelCase-keys guidance, because the segment
    IS the stored canonical key/value (translating it would break the key, R3.4; design §3). The
    category path (``membersConfig.field`` …) stays camelCase per convention. Frozen — the scheme is
    a shared constant the frontend seed (task 5.1) and this artifact must agree on byte-for-byte.
    """

    namespace: str
    category: str
    field_template: str
    group_template: str
    enum_template: str

    def field_key(self, field_key: str) -> str:
        """Resolve the resource key for a shipped FIELD label (``admin:membersConfig.field.<key>``)."""
        return self.field_template.format(field_key=field_key)

    def group_key(self, group_key: str) -> str:
        """Resolve the resource key for a shipped GROUP label (``admin:membersConfig.group.<key>``)."""
        return self.group_template.format(group_key=group_key)

    def enum_key(self, field_key: str, option_value: str) -> str:
        """Resolve the resource key for a shipped ENUM OPTION label.

        ``admin:membersConfig.enum.<fieldKey>.<optionValue>`` — the option ``value`` is a stable,
        language-neutral KEY segment, never translated text (R3.4).
        """
        return self.enum_template.format(field_key=field_key, option_value=option_value)


#: The shipped-label resource-key scheme recorded IN the catalog artifact (R3.7, task 5.1 scheme):
#: the frontend ``admin`` namespace, ``membersConfig`` category, and the field / group / enum-option
#: key templates. Single-sourced here so the SAM artifact and the frontend seed (``locales/*/admin.json``
#: + ``membersConfig-translations.test.ts``) read the SAME templates — the rule-5 shared-vocabulary
#: guard (steering 36 / design §6). The frontend test transcribes these templates (no cross-plane
#: import); they must not contradict this constant.
LABEL_KEY_SCHEME = LabelKeyScheme(
    namespace="admin",
    category="membersConfig",
    field_template="admin:membersConfig.field.{field_key}",
    group_template="admin:membersConfig.group.{group_key}",
    enum_template="admin:membersConfig.enum.{field_key}.{option_value}",
)

__all__ += [
    "LABEL_CONVENTION",
    "LABEL_FALLBACK_ORDER",
    "LABEL_KEY_SCHEME",
    "LabelKeyScheme",
    "build_attribute_catalog",
    "resolve_label",
    "validate_catalog_consistency",
]


# ── The resolve-with-precedence rule (task 5.2; design §3, R3.3/R2.2) ──────────────────
#
# The ONE i18n label rule (design §3), implemented as a PURE, locale-independent merge. For a
# given label it layers THREE per-locale sources with a single precedence:
#
#     label[locale] = tenant_inline[locale] ?? resource(key)[locale] ?? fallback(locale)
#
#   * ``tenant_inline`` — the per-language dict a TENANT authored for its own custom field / group /
#     enum-option label (runtime DATA, R3.2). WINS per locale when present.
#   * ``resource`` — the shipped-label i18n-resource values for the item's key (task 5.1's
#     ``admin:membersConfig.*`` namespace), resolved by the CALLER into a ``{locale: text}`` dict
#     (the serializer/edge reads the resource bundle; this pure core does not do I/O). Used per
#     locale when the tenant authored nothing for it.
#   * ``fallback`` — the registry's own inline ``{nl,en}`` dict (``FIXED_FIELDS`` /
#     ``CALCULATED_FIELDS``), kept behind the resource keys in Phase 1 (R3.7). Used per locale when
#     neither a tenant inline value nor a resource value exists.
#
# CRITICAL (R2.2): the rule RETURNS an inline ``{nl, en, …}`` dict — the SAME served shape today,
# so the ``GET /members/field-config`` response contract and the frontend ``resolveLabel`` helper
# are UNCHANGED; only a label's SOURCE changes (resource default ⊕ tenant override), not its shape.
# The merge is PER LOCALE: ``nl`` may come from the tenant inline dict while ``en`` comes from the
# resource layer, in the same returned dict (R3.3 independence).
#
# Phase-1 non-breaking note (R2.1 / the task-4.2 resolver lock): task 5.1 seeded the resource layer
# FROM the registry fallback values for the base ``nl``/``en`` keys, so for a shipped field with no
# tenant override ``resource[locale] == fallback[locale]`` and this rule reproduces the registry's
# inline dict byte-for-byte. The resolver is NOT changed by this task; the rule is the single pure
# source of the precedence, ready for the serializer to apply (design §3 "where it lands").
#
# A locale carries a value only when it is a non-empty string — an empty/blank entry at a tier is
# treated as ABSENT so the next tier supplies that locale (never render blank, R3.5). The set of
# locales in the result is the union of locales present (non-blank) across the three sources, so a
# locale only the tenant authored (e.g. a backfilled ``de``) appears, and a locale only shipped
# (``nl``/``en``) appears — the ``{nl,en,…}`` dict grows with the languages actually present.


def _nonblank(mapping: Mapping[str, str] | None, locale: str) -> str | None:
    """Return ``mapping[locale]`` when it is a present, non-blank string, else ``None``.

    A tier contributes a locale only when it has a real value there; an empty/blank entry is
    treated as ABSENT so the next precedence tier supplies that locale (never render blank, R3.5).
    """
    if not mapping:
        return None
    value = mapping.get(locale)
    if isinstance(value, str) and value.strip():
        return value
    return None


def resolve_label(
    *,
    tenant_inline: Mapping[str, str] | None = None,
    resource: Mapping[str, str] | None = None,
    fallback: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve ONE label to a served inline ``{nl, en, …}`` dict by the precedence rule (R3.3).

    Implements the single i18n rule of design §3 — ``label[locale] = tenant_inline[locale] ??
    resource(key)[locale] ?? fallback(locale)`` — as a PURE, locale-independent merge of three
    ``{locale: text}`` sources. Returns an inline per-language dict (the SAME shape served today,
    so the ``GET /members/field-config`` contract and the frontend ``resolveLabel`` stay unchanged,
    R2.2). The merge is PER LOCALE and INDEPENDENT: each locale is chosen separately, so ``nl`` may
    come from the tenant inline override while ``en`` comes from the resource layer in the same
    returned dict (R3.3).

    A tier contributes a locale only when it holds a non-blank string there; a missing/blank entry
    falls through to the next tier (``tenant_inline`` → ``resource`` → ``fallback``), so a locale
    is never rendered blank when ANY tier can supply it (R3.5). The returned dict's locale set is
    the union of the non-blank locales across the three sources — a tenant-only locale (a
    backfilled ``de``) and a shipped-only locale (``nl``/``en``) both appear, so the ``{nl,en,…}``
    dict grows with the languages actually present. No I/O: the caller resolves the resource bundle
    into the ``resource`` dict; this core only merges.

    Passing no sources yields an empty dict (the degenerate "label with nothing anywhere" case —
    the final frontend ``resolveLabel`` key-fallback then renders the canonical key, never blank).
    """
    locales = set()
    for source in (tenant_inline, resource, fallback):
        if source:
            locales.update(source.keys())

    served: dict[str, str] = {}
    for locale in locales:
        value = (
            _nonblank(tenant_inline, locale)
            or _nonblank(resource, locale)
            or _nonblank(fallback, locale)
        )
        if value is not None:
            served[locale] = value
    return served


def _fixed_to_catalog_field(fld: FixedField) -> CatalogField:
    """Project a :class:`FixedField` into a :class:`CatalogField` via the resolver's accessors.

    Reads EXACTLY the accessors ``FieldResolver`` reads off a fixed field — ``dotted_key()``,
    ``type.value``, ``required``, ``label``, ``default_functional_group()``, ``order`` — plus the
    structural bucket (``group.value``). A fixed field is stored, so ``read_only`` is ``False``.
    No field name or label is re-typed: every value flows from the registry object.
    """
    return CatalogField(
        dotted_key=fld.dotted_key(),
        key=fld.key,
        origin=AttributeApplies.FIXED,
        storage_group=fld.group.value,
        type=fld.type.value,
        required=fld.required,
        label=fld.label,
        functional_group=fld.default_functional_group(),
        order=fld.order,
        read_only=False,
    )


def _calculated_to_catalog_field(calc: CalculatedField) -> CatalogField:
    """Project a :class:`CalculatedField` into a :class:`CatalogField` via the resolver's accessors.

    Mirrors ``FieldResolver._as_calculated_field``: a calculated field is derived, never stored, so
    the platform pins ``required = False`` and ``read_only = True`` for every one (``CalculatedField``
    exposes no ``required``/``read_only`` accessor — these are the resolver's per-origin constants).
    All other values flow from the same accessors the resolver reads (``dotted_key()``,
    ``type.value``, ``label``, ``default_functional_group()``, ``order``, ``group.value``).
    """
    return CatalogField(
        dotted_key=calc.dotted_key(),
        key=calc.key,
        origin=AttributeApplies.CALCULATED,
        storage_group=calc.group.value,
        type=calc.type.value,
        required=False,
        label=calc.label,
        functional_group=calc.default_functional_group(),
        order=calc.order,
        read_only=True,
    )


# ── Import-time self-validation (fail-fast on an internally-inconsistent catalog; §6, R7.1) ──
#
# Task 3.2: the catalog is self-validating, the SAME fail-fast discipline the registries use
# (``fixed_fields.py`` raises on a duplicate dotted key; ``calculated_fields.py`` raises on a
# duplicate / fixed-colliding key — both at import time, so a bad registry can never load). The
# catalog layers the three internal-consistency checks design §6 names onto that discipline:
#
#   1. a duplicate ``AttributeSpec.key`` in the vocabulary — the vocabulary is keyed by attribute
#      name, so two specs sharing a key means one silently shadows the other;
#   2. a ``CatalogField.functional_group`` not among the base functional-group keys — a dangling
#      display-group reference (the "empty catalog ⇒ dangling reference" gap R5 closes, §4);
#   3. an enum-rule inconsistency — a vocabulary ``required_when`` enum rule (``("type", <v>)``)
#      whose declared type value ``<v>`` is NOT a member of the shipped ``FieldType`` set. The R1.3
#      rule mirrors ``FieldResolver._reject_invalid_overlay``'s choiceless-enum rejection by keying
#      off ``type == "enum"``; if that literal ever drifted from ``FieldType.ENUM.value`` (a typo, a
#      renamed enum) the rule would silently never fire, so the catalog pins it to the real
#      ``FieldType`` set and fails fast on the mismatch.
#
# Factored as a PURE helper taking the three pieces so it is unit-testable with deliberately-bad
# inputs (task 3.5) without having to corrupt the module constants; ``build_attribute_catalog()``
# calls it on every build, and the module ALSO runs it once at import time over the shipped catalog
# (so an inconsistent catalog can never load — the registry discipline). Raises ``ValueError`` with
# a message naming the offending key(s); never raises on the real, consistent catalog.


def validate_catalog_consistency(
    attributes: tuple[AttributeSpec, ...],
    fields: tuple[CatalogField, ...],
    functional_groups: tuple[FunctionalGroup, ...],
) -> None:
    """Fail fast (raise :class:`ValueError`) if the assembled catalog is internally inconsistent.

    The three design §6 / R7.1 invariants, checked over the pieces of an :class:`AttributeCatalog`:

    1. **No duplicate attribute key** — each :class:`AttributeSpec` ``key`` is unique in the
       vocabulary (it is the vocabulary's identity; a duplicate silently shadows).
    2. **No dangling display-group reference** — every :class:`CatalogField` ``functional_group``
       is one of ``functional_groups``' keys (the base set).
    3. **No enum-rule drift** — any vocabulary ``required_when`` rule keyed on ``"type"`` must name
       a type value that is a real :class:`FieldType` member value; a rule pointing at a
       non-existent type (``("type", "enumm")``) would never fire and is a config bug.

    Pure and import-time safe (reads only its arguments + the in-process ``FieldType`` set); mirrors
    the registry fail-fast loops. Returns ``None`` when the catalog is consistent.
    """
    # 1. Duplicate attribute key in the vocabulary.
    seen: set[str] = set()
    for spec in attributes:
        if spec.key in seen:
            raise ValueError(f"duplicate attribute key in the catalog vocabulary: {spec.key}")
        seen.add(spec.key)

    # 2. A CatalogField functional_group not present in the base functional-group keys.
    base_group_keys = {g.key for g in functional_groups}
    dangling = {
        cf.dotted_key: cf.functional_group
        for cf in fields
        if cf.functional_group not in base_group_keys
    }
    if dangling:
        raise ValueError(
            f"catalog field(s) reference a functional group absent from the base group set "
            f"{sorted(base_group_keys)}: {dangling}"
        )

    # 3. An enum-rule inconsistency — a required_when `type` rule naming a non-FieldType value.
    valid_type_values = {t.value for t in FieldType}
    for spec in attributes:
        for attr, value in spec.required_when:
            if attr == "type" and value not in valid_type_values:
                raise ValueError(
                    f"attribute {spec.key!r} has an enum-rule inconsistency: required_when "
                    f"type {value!r} is not a valid FieldType {sorted(valid_type_values)}"
                )


def build_attribute_catalog() -> AttributeCatalog:
    """Assemble the canonical :class:`AttributeCatalog` from the live registries (design §2, R1.4).

    Iterates ``FIXED_FIELDS`` then ``CALCULATED_FIELDS`` (fixed fields precede calculated ones in
    the inventory), projecting each into a :class:`CatalogField` with the SAME accessors the
    resolver uses — so the inventory is a derived VIEW over the registries, never a second,
    hand-maintained source of truth (design D1, the Phase-0 drift class). The attribute
    ``vocabulary`` and the base ``functional_groups`` are the module's already-authored constants;
    the COMPLETE i18n rule is recorded in the artifact (R3.7, task 5.7) — ``label_convention``
    (the convention name), ``label_fallback_order`` (:data:`LABEL_FALLBACK_ORDER`, the R3.5 tail),
    and ``label_key_scheme`` (:data:`LABEL_KEY_SCHEME`, the task-5.1 shipped-label resource-key
    templates) — so a consumer reads the whole rule off the catalog, not from folklore.

    Pure and import-time safe: it reads only in-process constants (no DynamoDB, no boto3), mirroring
    how ``fixed_fields.py`` / ``calculated_fields.py`` load. Before returning, it runs
    :func:`validate_catalog_consistency` (fail-fast on an internal inconsistency — a duplicate
    attribute key, a dangling functional-group reference, or an enum-rule drift; design §6, R7.1),
    the same discipline the registries' import-time loops use.
    """
    fields: tuple[CatalogField, ...] = tuple(
        _fixed_to_catalog_field(f) for f in FIXED_FIELDS
    ) + tuple(_calculated_to_catalog_field(c) for c in CALCULATED_FIELDS)

    validate_catalog_consistency(ATTRIBUTE_VOCABULARY, fields, BASE_FUNCTIONAL_GROUPS)

    return AttributeCatalog(
        attributes=ATTRIBUTE_VOCABULARY,
        fields=fields,
        functional_groups=BASE_FUNCTIONAL_GROUPS,
        label_convention=LABEL_CONVENTION,
        label_fallback_order=LABEL_FALLBACK_ORDER,
        label_key_scheme=LABEL_KEY_SCHEME,
    )


# Fail fast at import time on an internally-inconsistent shipped catalog — the SAME discipline
# ``fixed_fields.py`` / ``calculated_fields.py`` apply to their registries (an inconsistent catalog
# can never load). Building the catalog once here runs ``validate_catalog_consistency`` over the
# shipped vocabulary + computed inventory + base group set (design §6, R7.1).
build_attribute_catalog()
