# Phase 1 — Catalog Backbone — Design

> **Status: DESIGN.** Implements `requirements.md`. Grounded in the current SAM field model
> (`sam/members/domain/{fixed_fields,calculated_fields,field_resolver}.py`,
> `_membership_catalog.py`, `_membership_writes.py`, `seed_overlay.py`) and the Flask authoring
> schema (`backend/src/config/members_parameters.json`).
>
> **Design stance:** Phase 1 is *additive consolidation*. It introduces ONE new domain artifact —
> the attribute catalog — assembled FROM the existing registries, plus a base functional-group set.
> It changes NO merge semantics, NO stored shape, NO runtime contract. Every runtime behavior keeps
> flowing through `FieldResolver.resolve`; the catalog sits beside it as the single description the
> authoring UI (Phase 3) and the save-time validator read.

## 0. Applicable steering & reusable patterns (per `40-spec-workflow.md` → "Writing Design")

The spec-workflow requires design to reference the relevant platform conventions/frameworks. The
ones that GOVERN this phase, and how the design conforms:

- **`36-config-and-parameters.md` (config model) — directly governs.** The catalog is Members
  config. This design obeys 36's rules: MySQL `parameters` is the single writer (Option B,
  unchanged); the catalog is a projection-fed READ shape, never a parallel config store (rule 1);
  it is **data, not strategy** — no `if tenant == …` branch (rule 2); validation at the save seam
  stays `members_config_validation.py` (rule 4); and 36 **rule 5** ("no shared code across planes —
  guard a shared vocabulary with a test") is exactly what the catalog's drift guard (R7) and the
  Flask ⇄ catalog conformance test (R7.2) implement. The i18n key-vocabulary agreement (§3) is the
  same rule-5 pattern.
- **`35-sam-module-architecture-sam.md` (SAM layering) — governs placement.** The catalog is a
  storage-agnostic **domain** artifact in `sam/members/domain/` (the field model is domain, per
  the four-seam layering); it is read by the handler edge, never the reverse. R9's module-neutral
  shaping + the new `38` steering follow 35's "build per-module first, extract on the rule of three."
- **`32-frontend-ui.md` + `Common/Internationalization/TRANSLATION_KEY_CONVENTIONS.md` (i18n) —
  governs R3's key scheme.** The resource-key default layer (§3) MUST use the platform's documented
  key convention (`{namespace}:{category}.{key}`, camelCase, one of the 8 fixed namespaces), NOT an
  ad-hoc scheme. Reconciled in §3 below.
- **`37-shared-building-blocks.md` (registry) — informs R9.** The catalog is a candidate future
  shared block; it is NOT registered now (single consumer). `38` records the pattern; registration
  waits for the second module (rule of three). No existing block is reinvented — the catalog does
  not touch the Table Filter Framework / LazySelect / API-response standard (those are Phase 3 UI).
- **`34-backend-testing.md` / `33-frontend-testing.md` (tests) — govern the test tasks.** Test
  naming (`test_{unit}_{scenario}_{expected}`), markers, and directory placement
  (`sam/tests/`, `backend/tests/unit/`) follow these; see tasks per-phase testing.
- **`Common/end-user-documentation/` ("every feature needs a manual section").** Phase 1 is a
  backbone/model change with no end-user-visible surface of its own (the UI is Phase 3), so no
  end-user manual page is due THIS phase; the obligation is explicitly carried forward to the
  Phase 3 authoring-UI spec. Recorded as a close-out note, not skipped silently.

## 1. Where the artifact lives (and why)

### Decision: the catalog is a derived VIEW over the registries, not a second source of truth

The Phase 0 `CALCULATED_FIELD_KEYS` drift bug (two hand-maintained copies of one list) is the exact
anti-pattern to avoid (R7.3). So the catalog is **not** a new hand-authored JSON of fields. It is a
**pure function of the live registries**:

```
build_attribute_catalog()  ==  f(FIXED_FIELDS, CALCULATED_FIELDS, OverlayField/FixedFieldOverride schema, BASE_FUNCTIONAL_GROUPS)
```

- **Module:** `sam/members/domain/attribute_catalog.py` (SAM plane — the field model is SAM-owned;
  `analysis.md` 2.1). Pure, import-time safe, no DynamoDB/boto3 — mirrors `fixed_fields.py`.
- **The catalog has two parts:**
  1. **The attribute vocabulary** — the set of `AttributeSpec`s describing every attribute a field
     may carry (name, type, required-vs-optional, applicable origins, authorable-vs-platform-fixed).
     This is authored IN `attribute_catalog.py` as a small constant, because it describes the SHAPE
     of a field definition (which is code-defined, not data) — it is the one genuinely new,
     hand-written piece, and it is tiny and stable.
  2. **The field inventory** — the concrete list of base fields with their current attribute values,
     **computed from `FIXED_FIELDS` + `CALCULATED_FIELDS`** (never re-typed). This is what R7.2's
     drift guard pins.
- **Base functional-group set** — `BASE_FUNCTIONAL_GROUPS` constant (see §4), reconciled with the
  existing `seed_overlay.SEED_FUNCTIONAL_GROUPS` so there is one base-group definition, not two.

Rationale: the attribute *vocabulary* is behavioral shape (belongs in code); the field *inventory*
is already code (the registries) and must stay single-sourced. Putting the catalog in the SAM domain
keeps it next to the registries it derives from, so a drift test can import both in one process.

### What the Flask plane gets

The Flask authoring schema (`backend/src/config/members_parameters.json`) stays the EDITOR schema
(control definitions), but Phase 1 makes it **conform to the catalog**: a test asserts the editor
schema's field-def attributes are a subset of the catalog's authorable attributes, so the two cannot
silently diverge (closing the gap `analysis.md` 2.4 described). No cross-plane import — the test
reads the JSON and the catalog independently and compares (mirrors how
`members_config_validation.py` transcribes keys without importing SAM, per steering 30).

## 2. The catalog data model

```python
# sam/members/domain/attribute_catalog.py  (new; pure, import-time safe)

class AttributeApplies(str, Enum):
    FIXED = "fixed"
    CALCULATED = "calculated"
    VARIABLE = "variable"

@dataclass(frozen=True)
class AttributeSpec:
    """One attribute a field definition may carry (the vocabulary entry)."""
    key: str                                   # e.g. "type", "label", "functional_group"
    value_type: str                            # "string"|"bool"|"int"|"enum"|"i18n"|"object"|"list"
    required: bool                             # required for a field DEFINITION (not the member value)
    applies_to: tuple[AttributeApplies, ...]   # which origins may carry it
    tenant_authorable: bool                    # True = a tenant may set/override it; False = platform-fixed
    required_when: tuple[tuple[str, str], ...] = ()   # conditional requirement, e.g. (("type","enum"),)
    note: str = ""                             # human doc (surfaced to the authoring UI)

@dataclass(frozen=True)
class CatalogField:
    """One base field as the catalog sees it — COMPUTED from the registries, never hand-typed."""
    dotted_key: str                            # "personal.first_name"
    key: str
    origin: AttributeApplies                   # fixed | calculated (variable fields are tenant data, not base)
    storage_group: str                         # "personal" | "membership"
    type: str                                  # FieldType value
    required: bool
    label: Mapping[str, str]                   # {nl,en}  (see §3 i18n decision)
    functional_group: str                      # resolved via default_functional_group()
    order: int
    read_only: bool                            # True for calculated
    # plus any attribute values the registry sets (choices/options/show_when/member_number_format)

@dataclass(frozen=True)
class AttributeCatalog:
    attributes: tuple[AttributeSpec, ...]              # the vocabulary (R1)
    fields: tuple[CatalogField, ...]                   # base inventory, computed from registries (R1.4/R7.2)
    functional_groups: tuple[FunctionalGroup, ...]     # the BASE group set (R5), reuses the existing dataclass
    label_convention: str                              # "i18n-keys+tenant-inline-override" (R3 — recorded IN the artifact)

def build_attribute_catalog() -> AttributeCatalog: ...
```

### The attribute vocabulary (R1.1/R1.2/R1.3/R1.5) — one `AttributeSpec` per supported attribute

Derived 1:1 from what `FixedField` / `CalculatedField` / `OverlayField` / `FixedFieldOverride` carry
today. Illustrative rows (full set in tasks):

| attribute `key` | value_type | required | applies_to | tenant_authorable | required_when |
|---|---|---|---|---|---|
| `key` | string | yes | fixed, calculated, variable | no (identity) | — |
| `type` | enum (`string\|date\|enum\|reference`) | yes | all | no for fixed/calc; yes for variable | — |
| `required` | bool | no (default false) | fixed, variable | yes (tighten-only for fixed; calc always false) | — |
| `label` | i18n | yes | all | yes | — |
| `visible` | bool | no (default true) | all | yes | — |
| `order` | int | no (default 0) | all | yes | — |
| `functional_group` | string (ref) | no (→ base default) | all | yes | — |
| `choices` | list[string] | conditional | fixed(enum), variable(enum) | yes | type == enum |
| `options` | list[`{value,label,roles?}`] | conditional | fixed(enum), variable(enum) | yes | type == enum (rich form) |
| `show_when` | object | no | all | yes | — |
| `member_number_format` | object | no | fixed(member_number) | yes | key == member_number |
| `calculated_from` | list[string] | n/a (read-only output) | calculated | no (platform) | — |
| `scope_binding` | bool | no (default false) | fixed, variable | yes | — (R8 — declared only) |
| `alias` | i18n | no | all | yes | — (R8 — declared only) |

- The `type == enum ⇒ choices/options required` rule (R1.3) is encoded as
  `required_when=(("type","enum"),)` on `choices`/`options`, matching
  `FieldResolver._reject_invalid_overlay`'s choiceless-enum rejection (with the documented
  scope-dimension-backed exception noted on the spec).
- `scope_binding` and `alias` are **declared** (R8.1) but marked clearly as Phase-3-wired in `note`.

### The field inventory (R1.4) — computed, drift-guarded

`build_attribute_catalog()` iterates `FIXED_FIELDS` then `CALCULATED_FIELDS` and projects each into a
`CatalogField` using the SAME accessors the resolver uses (`dotted_key()`,
`default_functional_group()`, `type.value`, `required`, `label`, `order`). No field names or labels
are re-typed. R7.2's test asserts `{cf.dotted_key for cf in catalog.fields}` ==
`{f.dotted_key() for f in FIXED_FIELDS} | {c.dotted_key() for c in CALCULATED_FIELDS}` and that each
`CatalogField`'s platform-fixed attributes equal the registry's.

## 3. The i18n label model — Option (b) (R3)

### Decision: resource keys as the DEFAULT for shipped labels; inline per-language dict as the per-tenant OVERRIDE

Driven by the "add a third language" impact. Two kinds of label behave differently and the model
reflects that with ONE precedence rule (not two competing conventions):

| Label kind | Source | Who owns it | Add a language |
|---|---|---|---|
| Shipped field/group labels | i18n resource key | translators (resource files) | drop locale file |
| Shipped enum option labels (built-in `status`) | i18n resource key | translators | drop locale file |
| Tenant custom field / group labels | inline `{nl,en,…}` dict | the tenant | tenant backfills |
| Tenant enum option labels | inline `{nl,en,…}` dict, keyed by the canonical `value` | the tenant | tenant backfills |

- **Key scheme (R3.1) — conforms to `TRANSLATION_KEY_CONVENTIONS.md` + `32-frontend-ui.md`.** The
  platform convention is `{namespace}:{category}.{key}`, camelCase keys, one of the 8 fixed frontend
  namespaces resolved via `useTypedTranslation(namespace)`. Members' admin config labels belong under
  the existing **`admin`** namespace (its `tenantAdmin` / `configuration` categories), so shipped
  labels resolve from keys shaped:
  - fields → `admin:membersConfig.field.<fieldKey>` (e.g. `admin:membersConfig.field.firstName`);
  - groups → `admin:membersConfig.group.<groupKey>` (e.g. `admin:membersConfig.group.administrative`);
  - enum options → `admin:membersConfig.enum.<fieldKey>.<optionValue>` (e.g.
    `admin:membersConfig.enum.status.active`).
  Note the field/option KEY segments are the canonical field keys/enum values, which are
  `snake_case` by the field model's own rule (`first_name`, `member_number`) — that is the ONE
  deliberate deviation from the convention's camelCase-keys guidance, because the segment IS the
  stored canonical key (translating it would break the value/key, R3.4); the category path
  (`membersConfig.field` …) stays camelCase per convention. The design task SHALL confirm the exact
  namespace/category with the i18n conventions doc before coding (it may land under a new
  `admin:membersConfig.*` category rather than overloading an existing one). The frontend `admin`
  namespace resource files (nl + en) carry the DEFAULT text; adding a language = adding that locale's
  file, **no domain code change, no deploy of `fixed_fields.py`/`calculated_fields.py`**.
- **Tenant labels (R3.2):** a custom field/group/enum-option label is runtime DATA, so it is stored
  as an inline per-language dict `{nl, en, …}` (today's shape, extended to any locale). The authoring
  UI shows one text input per supported locale. There is no resource key for a field the tenant
  invented after build time.
- **Precedence — one rule (R3.3):** for any label + locale, a tenant inline value WINS; absent that,
  the resource key default is used (shipped items); absent both, the fallback order applies. So the
  resolver/serializer resolves a label as:
  `tenant_inline[locale]  ??  resource(key)[locale]  ??  fallback(locale)`.
- **Enum values are language-neutral (R3.4) — the critical guardrail.** `EnumOption.value` stays a
  single canonical token; ONLY `EnumOption.label` is per-language. Translating a `value` would
  silently invalidate stored member records (filters/pivots/analytics key off `value`), so the model
  makes it impossible: the per-language dict hangs off the `label`, keyed to the stable `value`.
  Shipped enum labels use `members.enum.<field>.<value>`; tenant enum labels use the inline dict. The
  tenant supplies the per-language labels for its own enum options; the platform never invents them.
- **Missing-locale fallback (R3.5):** `active locale → en → nl → the canonical key` — deterministic,
  never blank. Documented in the artifact.
- **Add-a-language impact, stated (R3.6):** locale `X` needs (a) a new `X` resource file covering ALL
  shipped keys (translator-owned, no domain deploy) and (b) an OPTIONAL per-tenant backfill of inline
  `X` labels for that tenant's custom fields/groups/enum options — until done they fall back per the
  rule above. No stored `value` and no member record changes.
- **Artifact records the rule (R3.7):** `label_convention = "i18n-keys+tenant-inline-override"` +
  the fallback order, so the authoring UI and validator read the rule, not folklore.

### What changes vs today, and the migration framing

Today everything is inline `{nl,en}` (shipped AND tenant). Option (b) introduces the resource-key
DEFAULT layer for shipped labels on top of that. To keep Phase 1 non-breaking (R2):

- The shipped `{nl,en}` dicts in `FIXED_FIELDS` / `CALCULATED_FIELDS` are **kept** as the
  fallback/default behind the resource keys (R3.7) — not deleted in Phase 1. The frontend `admin`
  i18n namespace (`membersConfig.*` category) is **seeded** from those same `{nl,en}` values for the
  base keys (so `nl`/`en` are covered on day one), and a THIRD language is then purely a new resource
  file.
- The resource-key lookup + inline-override merge is the one render-side addition. Where it lands:
  the SERVED label can stay an inline dict (the serializer resolves resource-key defaults into the
  `{nl,en,…}` dict it already emits, then overlays tenant inline values) — so the
  `GET /members/field-config` RESPONSE SHAPE is unchanged (still `label: {nl,en,…}`), and only its
  SOURCE changes (resource default ⊕ tenant override) (keeps R2.2). The frontend's existing
  `resolveLabel(label, lang)` keeps working unchanged.
- **The Flask authoring save** stores tenant inline labels as `{nl, en, …}` keyed by locale (the
  former `label_en`/`label_nl` editor inputs become one input per supported locale, folded into the
  dict — the single bridge point stays, now locale-generic rather than two hardcoded inputs).

> **Why not pure render-time resource keys for everything?** A tenant's custom-field label is created
> at runtime and cannot live in a build-time resource bundle — pure (b) can't represent it. Option
> (b)-as-specified (resource default + tenant inline override) is the only model that makes shipped
> labels translator-owned AND lets tenants name their own fields/enum options per language.

## 4. Functional-group identity + base set (R4, R5)

### Decision: first-class object (confirm current model), add a BASE_FUNCTIONAL_GROUPS constant

The current `FunctionalGroup` (`key`, `label{nl,en}`, `order`) is already a first-class authored
object on `TenantOverlay.functional_groups` (R4.1 — Phase 1 ratifies it, adds the missing base set).

```python
# sam/members/domain/attribute_catalog.py  (or a small sibling module imported by it)
BASE_FUNCTIONAL_GROUPS: tuple[FunctionalGroup, ...] = (
    FunctionalGroup(key="personal",       label={"nl": "Persoonlijk",  "en": "Personal"},        order=1),
    FunctionalGroup(key="address",        label={"nl": "Adres",        "en": "Address"},         order=2),
    FunctionalGroup(key="membership",     label={"nl": "Lidmaatschap", "en": "Membership"},      order=3),
    FunctionalGroup(key="administrative", label={"nl": "Administratie","en": "Administrative"},  order=4),
)
```

- **Reconciled with the seed fixture (R5.2):** `seed_overlay.SEED_FUNCTIONAL_GROUPS` becomes a
  re-export of / is defined in terms of `BASE_FUNCTIONAL_GROUPS` (minus any seed-only extras like
  `group_a`, which stays seed/test data) — ONE base-group definition, not two. A test asserts every
  base/calculated field's `default_functional_group()` is a key in `BASE_FUNCTIONAL_GROUPS` (R5.2
  closure: `administrative`, `membership`, `personal` all covered; `address` covers the
  address-group intent named in `fixed_fields.py`).
- **Merge rule (R5.3):** resolved groups = `BASE_FUNCTIONAL_GROUPS` ⊕ tenant
  `overlay.functional_groups`, tenant key WINS on collision, base keys fill the rest. Whether a
  tenant may HIDE a base group is decided NO for Phase 1 (a base group is always present; hiding is a
  Phase-3 authoring concern) — documented, not implemented.
- **Reference validation extended (R4.2 / R5.4):** today `_reject_invalid_overlay` only knows the
  tenant's authored catalog and skips the check when it is empty. Phase 1 defines the catalog's group
  set as `BASE ⊕ tenant`, so a field referencing a base key (e.g. `administrative`) is reference-
  VALID even when the tenant authored no catalog — turning today's "empty ⇒ unchecked" into
  "empty ⇒ validated against the base set." **This is the one resolver-adjacent change in Phase 1**;
  it is strictly more permissive-preserving (nothing that validated before fails now) and is covered
  by R2.1's "identical FieldConfig" test plus a new test for the base-key-resolves case.
- **Role-gating of a group (R4.3):** NOT in Phase 1 (the current `FunctionalGroup` has no
  `permission_roles`); recorded as a deferred option so the catalog shape does not preclude it.

## 5. Display ordering contract (R6)

Two independent orderings, both already present, now stated as a contract:

- **Section order** = `functional_group.order`, ties broken by `key` → `(order, key)` (today's group
  sort).
- **Within-section field order** = field `order`, overridable via `FixedFieldOverride.order`.
- **The display position of a field** = `(functional_group.order, field.order, field.key)` (R6.3).

> **Explicit caveat (R6.3):** this is DIFFERENT from the resolver's current flat sort key
> `(storage_group, order, key)`, which orders by STORAGE bucket (`personal`/`membership`/`overlay`),
> not by display group. Phase 1 does NOT change the resolver's sort (R2.1 — identical FieldConfig).
> Instead it DOCUMENTS the display-ordering contract and makes it derivable by the consumer (the
> authoring UI, Phase 3) from `functional_groups` (ordered) + each field's `functional_group` + its
> `order`. The design decides: the served config already carries everything needed (`functional_groups`
> ordered by `order,key`, each field's `functional_group` + `order`), so NO new field is added to the
> response for ordering — the UI computes display position from existing data. Ties break by `key`
> (R6.4). Ordering is advisory/presentation-only (R6.5).

## 6. Self-validation + drift guard (R7)

`build_attribute_catalog()` runs import-time assertions (like `fixed_fields.py` /
`calculated_fields.py` do today) and raises `ValueError` on:
- a duplicate `AttributeSpec.key`;
- a `CatalogField.functional_group` not in `BASE_FUNCTIONAL_GROUPS` keys (R7.1);
- an enum attribute rule inconsistent with the `FieldType` set.

Tests (R7.2):
- `test_attribute_catalog.py` — inventory == registries; each `CatalogField`'s platform-fixed
  attributes == registry values; the base-group closure; the vocabulary covers every attribute the
  dataclasses carry.
- `test_members_parameters_schema_conforms_to_catalog` (Flask plane) — the editor JSON's field-def
  attribute keys ⊆ the catalog's `tenant_authorable` attribute keys (no editor control for a
  non-existent/non-authorable attribute).

## 7. What explicitly does NOT change in Phase 1

- `FieldResolver.resolve` merge/sort — unchanged (except the base-group-aware reference validation,
  §4, which only makes previously-skipped checks pass).
- `ResolvedField` / `FieldConfig` / the `GET /members/field-config` response shape — unchanged
  (R2.1/R2.2). The catalog is a separate artifact; it is NOT injected into the field-config response
  in Phase 1 (serving the catalog to the authoring UI is wired when the UI needs it — Phase 3 — or
  via a dedicated read documented there; Phase 1 only builds + validates it).
- Stored `members.field_overlay` shape — unchanged; no data migration (R2.3).
- `scope_binding` / `alias` — declared in the vocabulary, NOT wired into the resolver/render (R8.2).

## 8. Testing strategy

- **SAM unit** (`sam/tests/test_attribute_catalog.py`): catalog builds; inventory ⇄ registry drift
  guard; base-group closure; vocabulary completeness; import-time self-validation raises on injected
  inconsistency; i18n `label_convention` recorded.
- **SAM unit** (extend `test_field_resolver.py`): a field referencing a BASE functional-group key
  resolves without `OverlayError` when the tenant authored no catalog (the one behavior §4 adds);
  `resolve()` output unchanged for existing fixtures (R2.1).
- **i18n label-resolution** (`resolveLabel` + the serializer): shipped label resolves from the
  resource-key default when the tenant authored no override; a tenant inline value wins when present;
  an enum option's `value` is never translated (only its `label`); the missing-locale fallback
  (`active → en → nl → key`) is deterministic. A test adds a third locale (`de`) resource entry for a
  base key and asserts it resolves without any domain code change (R3.1/R3.3/R3.4/R3.5/R3.6).
- **Flask unit** (`backend/tests/unit/`): the tenant-label save folds per-locale inputs into the
  `{nl,en,…}` inline dict (round-trip); editor-schema ⊆ catalog conformance (R7.2) — reading the JSON
  + a transcribed catalog view without importing SAM (steering 30 cross-plane boundary).
- **Regression:** full existing SAM + Flask + frontend field-model suites pass unchanged (R2.4).

## 9. Design decisions log (for the record)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Catalog = derived view over the registries, not a 2nd source | avoid the Phase-0 drift class (R7.3) |
| D2 | Catalog lives in `sam/members/domain/attribute_catalog.py` | next to the registries it derives from; SAM owns the field model |
| D3 | i18n = Option (b): resource keys default for shipped labels ⊕ tenant inline per-language override; enum `value` language-neutral | adding a language = resource-file drop for everything shipped; tenant labels are irreducible data either way (R3) |
| D4 | Functional group stays a first-class object + add `BASE_FUNCTIONAL_GROUPS` | matches code; closes the "empty catalog ⇒ unchecked" gap (R5.4) |
| D5 | Base-group-aware reference validation is the ONLY resolver-adjacent change | strictly preservation-safe; enables R5.4 |
| D6 | Display position = `(group.order, field.order, key)`, derived by the UI, no new response field | ordering already derivable; keeps R2.1 |
| D7 | `scope_binding` + `alias` declared only | forward-compat for Phase 3 without runtime change (R8) |
| D8 | Role-gating of groups + tenant-hiding a base group deferred | not in current model; don't preclude, don't build |
| D9 | Catalog shaped module-neutrally but kept in `sam/members/domain/`; no shared library | extraction-ready now, extracted on the 2nd module (rule of three, R9) |
| D10 | Add guidance steering `38-sam-module-field-config.md` (`auto`) | document the proven Members pattern for Webshop/Events, per impact-analysis §11 |

## 10. R9 — module-neutral shape + the `38` steering file

Phase 1 builds the catalog **module-first** (it lives in `sam/members/domain/attribute_catalog.py`),
but shapes the MODEL so a second SAM module can adopt it without a rewrite — and documents the
pattern as recommended practice. No shared code is extracted now (rule of three; steering 35/37).

### Shaping constraints (a design/review checklist, not new code) — R9.1

The catalog model carries no Members-only concepts in its SHAPE:
- `AttributeSpec` / `CatalogField` / `AttributeCatalog` describe a GENERIC field-definition model
  (attribute vocabulary + computed inventory + group set + label rule). None of these dataclasses
  reference `members`, h-dcn, or a Members-only field name.
- The functional-group model (`key`, `label`, `order`, base-set ⊕ tenant merge) is generic.
- The i18n rule (resource-key default ⊕ tenant inline override; `value` language-neutral) is stated
  module-neutrally (the key scheme `members.*` is Members' INSTANCE of a generic `<module>.*` scheme).
- The drift-guard pattern (catalog inventory ⇄ registries) is a generic technique.

Members-specific DATA stays Members-specific and is NOT generalized: the actual `FIXED_FIELDS` /
`CALCULATED_FIELDS`, the `BASE_FUNCTIONAL_GROUPS` values, the `members.field.<key>` resource keys.
It is the shape that is reusable, not the data (R9.1).

### The steering file — `38-sam-module-field-config.md` (R9.3/R9.4)

A THIN, `auto`-included guidance file in the `3x` conventions layer, sibling to
`35-sam-module-architecture-sam.md` / `36-config-and-parameters.md` / `37-shared-building-blocks.md`.
It records the five proven Members config lessons (impact-analysis §11) + the Option-(b) i18n rule as
RECOMMENDED PRACTICE for a new SAM module, points at Members as the reference implementation and this
spec folder for detail, and states the rule-of-three extraction boundary. It does NOT copy the
catalog's detail (facts-in-one-place, `00-index.md`); it points.

Content outline (the file itself is written in tasks §9):
1. **Catalog-first.** Model a module's fields as ONE canonical, versioned attribute catalog derived
   from the module's registries — not an implicit spread across code + hand-transcribed copies
   (the Phase-0 drift class).
2. **Group → field → attribute, with explicit ordering.** First-class functional groups (`key`,
   `label`, `order`) + a base set; display position `(group.order, field.order, key)`.
3. **No standalone view/analytics param objects.** Columns/sort/filter/pagination are runtime
   behaviours of the generic table + per-user prefs; analytics needs are calculated fields + pivot
   filters — not stored config surfaces (the `view_contexts` lesson).
4. **First-class, versioned, observable config projection.** If config is Flask-authored and
   projected, version it per-param (not off a coarse tenant row — the Phase-0 version-bump trap) and
   expose a read-side delivered/loaded status (Phase-0 step 3). Ship this from day one, don't retrofit.
5. **One authoring surface.** A typed editor supersedes the raw param table for the module's
   namespace; never grow two doors to the same rows.
6. **i18n = Option (b).** Resource-key defaults for shipped labels (translator-owned; add a language
   = a resource file), inline per-language dict for tenant-authored labels; an enum `value` is
   language-neutral, only its `label` is per-language.
7. **Extraction boundary.** The generic *code* (a shared `sam/shared` catalog library) is extracted
   on the SECOND module that needs it (rule of three, steering 35/37) — not shipped speculatively.
   Until then, a new module COPIES the Members shape from the reference impl, guided by this file.
