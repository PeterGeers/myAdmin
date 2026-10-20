# Phase 1 — Catalog Backbone — Requirements

> **Status: REQUIREMENTS.** Phase 1 of the Members config redesign (`impact-analysis.md` §9,
> `recommendation.md` §5). Scope = the two "catalog backbone" deliverables:
> **(4)** author the single canonical attribute catalog derived from the existing registries,
> resolving the i18n label question; **(5)** settle functional-group identity + display ordering.
>
> This phase is a **prerequisite** for the Phase 3 group → field → attribute authoring UI
> (`analysis.md` Q4) and the Phase 2 `view_contexts` retirement. It is deliberately **additive and
> non-breaking**: it produces a new first-class artifact and makes group identity/ordering explicit;
> it does **not** change the resolver merge semantics, the stored overlay shape, or the
> `GET /members/field-config` runtime contract (those are Phase 2/3).
>
> **Config home is settled = Option B** (Flask authors; SAM reads a first-class projection; steering
> 36 unchanged — `analysis.md` Q3, `recommendation.md` §4). Phase 1 is writer-agnostic.

## Glossary (grounded in current code)

- **Fixed field** — a platform built-in member field (`sam/members/domain/fixed_fields.py`,
  `FIXED_FIELDS`: 12 personal + 6 membership). `origin = "fixed"`.
- **Calculated field** — a derived, read-only, never-stored field (`calculated_fields.py`,
  9 entries). `origin = "calculated"`.
- **Variable / overlay field** — a tenant-authored custom field (`field_resolver.OverlayField`,
  stored under the `overlay` bucket). `origin = "variable"`.
- **Storage group** (`FieldGroup`) — the structural bucket a field stores under: `personal` /
  `membership` / `overlay`. Fixed by origin.
- **Functional group** (`FunctionalGroup`) — the parameter-driven DISPLAY section a field is shown
  under (e.g. `address`, `motor`, `administrative`). Orthogonal to the storage group; referenced by
  a field's `functional_group` key.
- **Attribute** — one declared property of a field (`key`, `type`, `required`, `label`, `visible`,
  `order`, `choices`/`options`, `functional_group`, `show_when`, `member_number_format`,
  `calculated_from`, scope-binding, alias).
- **Catalog** — the NEW first-class artifact this phase produces: the machine-readable description
  of (a) every attribute a field may carry (name, type, required-vs-optional, applicability per
  origin) and (b) the base functional-group set + ordering.
- **Label shape** — the i18n representation of display text. Two conventions exist today: the SAM
  domain uses a `{"nl":…, "en":…}` dict; the Flask authoring JSON schema
  (`backend/src/config/members_parameters.json`) uses flat `label_en` / `label_nl` editor keys.

## Requirements

### R1 — A single canonical attribute catalog exists as a first-class artifact

**User story:** As a platform maintainer, I want one authoritative description of every field
attribute and its rules, so the authoring UI, the save-time validator, and the field model all read
from one source instead of the current implicit spread across `field_resolver.py`,
`calculated_fields.py`, `fixed_fields.py`, enum validation, and the overlay schema.

#### Acceptance criteria
1. WHEN the catalog artifact is loaded THEN it SHALL enumerate every field **attribute** the model
   supports today, each with: a stable `key`, a `type`, whether it is **required or optional** for a
   field definition, and which field **origins** it applies to (`fixed` / `calculated` / `variable`).
2. The catalog SHALL cover at minimum the attributes present in the current code:
   `key`, `type` (∈ `{string, date, enum, reference}` — the current `FieldType` set),
   `required`, `label`, `visible`, `order`, `choices`, `options` (`{value,label,roles?}`),
   `functional_group`, `show_when`, `member_number_format`, and (read-only, calculated-only)
   `calculated_from`.
3. WHEN `type == enum` THEN the catalog SHALL mark the enum value source
   (`choices`/`options`) as **required** for that field (an enum field with no values and no
   scope-dimension backing is a config bug today — `FieldResolver._reject_invalid_overlay`).
4. The catalog SHALL be **derived from the existing registries** (`FIXED_FIELDS`,
   `CALCULATED_FIELDS`, the `OverlayField` / `FixedFieldOverride` schema) — it is a consolidation,
   NOT a new parallel source of truth. A test SHALL assert the catalog's field inventory matches the
   live registries exactly (no field present in one and absent from the other).
5. The catalog SHALL distinguish, per attribute, whether it is **authorable by a tenant** vs
   **platform-fixed** (e.g. a fixed field's `type` is platform-fixed; its `label`/`visible`/`order`/
   `functional_group` are tenant-overridable; a calculated field's `required` is always `false`).
6. The catalog SHALL be a committed, versioned artifact (its location and format decided in design),
   loadable without a database or AWS call (pure, import-time safe), mirroring how `FIXED_FIELDS` /
   `CALCULATED_FIELDS` load today.

### R2 — The catalog does not change runtime behavior (additive, non-breaking)

**User story:** As the owner of the TOP-rated Members runtime, I want the catalog introduced without
altering what the module serves today, so Phase 1 carries no regression risk.

#### Acceptance criteria
1. WHEN `FieldResolver.resolve(tenant_id)` runs before and after this phase THEN it SHALL produce an
   identical `FieldConfig` for the same input (same fields, same order, same functional groups) —
   the catalog is read ALONGSIDE the resolver, it does not replace the merge.
2. WHEN `GET /members/field-config` is called before and after this phase THEN the response
   contract (keys, shapes) SHALL be unchanged, EXCEPT for any strictly-additive catalog metadata
   explicitly specified in design and gated so an older consumer ignores it.
3. The stored `members.field_overlay` param shape SHALL be unchanged; no migration of tenant data is
   required by Phase 1.
4. All existing SAM + Flask + frontend tests touching the field model SHALL still pass unchanged.

### R3 — The i18n label model is Option (b): resource keys for shipped labels, inline per-language dict for tenant labels

> **DECISION (user, 2026-10-13): Option (b).** Adding a language must be cheap for everything the
> platform SHIPS (translator-owned resource files, no code change), while tenant-authored labels
> stay the tenant's data. The driver is the "add a third language" impact (`analysis.md` Q4 open
> i18n question, decision #8): shipped labels become a resource-file drop; tenant labels are an
> irreducible per-tenant backfill either way.

**User story:** As a platform maintainer, I want built-in field/group/enum labels owned by
translation resource files so adding a language is a resource drop (no domain code change), while a
tenant still names its own custom fields and enum options per language.

#### Acceptance criteria
1. **Shipped labels** (built-in fixed/calculated fields, base functional groups, built-in enum
   option labels such as `status`) SHALL resolve from **i18n resource keys** at render — the DEFAULT
   label source. The key-naming scheme SHALL CONFORM to the platform i18n convention
   (`{namespace}:{category}.{key}`, one of the 8 fixed frontend namespaces,
   `Common/Internationalization/TRANSLATION_KEY_CONVENTIONS.md` + `32-frontend-ui.md`) — NOT an
   ad-hoc scheme; the design SHALL pin the exact namespace/category. Adding a language = adding the
   locale's resource file, with NO change to the domain registries.
2. **Tenant-authored labels** (custom overlay fields, tenant functional groups, tenant enum option
   labels) SHALL be stored as an **inline per-language dict** keyed by locale (`{nl, en, …}`),
   because such a label is runtime DATA that cannot exist in a build-time resource bundle. The
   authoring UI SHALL offer one text input per supported locale.
3. **Precedence (one rule, not two competing conventions):** for a given label, an inline
   per-language value authored by the tenant OVERRIDES the resource-key default for that locale;
   where the tenant authored nothing, the resource key (for shipped items) is used. The design SHALL
   state this precedence explicitly and a test SHALL cover: shipped-default used when no override;
   tenant override wins when present.
4. **Enum values carry NO language; only enum LABELS do.** An enum option's canonical `value` (the
   stored token filters/pivots/analytics key off) SHALL remain a single language-neutral string and
   SHALL NOT change with language or be translated. Only the option's `label` is per-language
   (resource key for shipped options; inline `{nl,en,…}` dict keyed by the canonical `value` for
   tenant options). The design SHALL make this split explicit so translating a value — which would
   silently invalidate stored member records — is impossible by construction. It is the tenant's
   responsibility to supply the per-language labels for its own enum options.
5. **Missing-locale fallback:** WHEN a label has no value for the active locale (neither a tenant
   inline value nor a resource entry) THEN render SHALL fall back deterministically (documented
   order, e.g. active locale → `en` → `nl` → the canonical key) rather than render blank; the
   fallback order SHALL be documented in the artifact.
6. **Adding a language — stated impact (R3 is the "add a third language" requirement):** the design
   SHALL document that adding locale `X` requires (a) a new `X` resource file for ALL shipped labels
   (translator-owned, no deploy of the domain registries) and (b) an OPTIONAL per-tenant backfill of
   inline `X` labels for that tenant's custom fields/groups/enum options (until done, those fall back
   per criterion 5). No stored enum `value` and no member record changes.
7. The chosen model and the fallback order SHALL be recorded in the catalog artifact itself
   (`label_convention = "i18n-keys+tenant-inline-override"`), so the authoring UI and validator read
   the rule, not folklore. The already-stored `{nl,en}` labels in `FIXED_FIELDS` / `CALCULATED_FIELDS`
   MAY remain as the fallback/default source behind the resource keys and SHALL NOT be deleted in
   Phase 1 (removing them is a later cleanup, not required here).

### R4 — Functional-group identity is settled: first-class object

**User story:** As a tenant admin, I want functional groups to be the organizing unit of config —
authored as their own objects with labels and order — so the UI is group → field → attribute and
not an unlinked "overlay vs groups" split (`analysis.md` 2.6 / Q4.3).

#### Acceptance criteria
1. The design SHALL confirm the functional group as a **first-class object** (the current
   `FunctionalGroup`: `key`, `label{nl,en}`, `order`) that fields reference by `key` — NOT merely an
   implicit value derived from distinct per-field `functional_group` strings. (This matches today's
   code; Phase 1 makes it the settled, documented decision and fills the gaps in R5/R6.)
2. A field SHALL reference exactly one functional group by its `key`; the reference SHALL be
   reference-validated against the catalog's group set (today's `_reject_invalid_overlay` dangling-
   group check, extended to also know the BASE groups per R5).
3. The design SHALL state the group's authorable attributes (at least `key`, `label`, `order`) and
   whether optional role-gating of a group is in scope for Phase 1 or deferred (decide explicitly;
   it is not required by the current model).
4. The decision SHALL NOT break a tenant that has authored **no** functional-group catalog: such a
   tenant SHALL continue to resolve against base-default groups exactly as today (empty catalog →
   fields carry their storage-bucket / base-default group; dangling-reference check skipped).

### R5 — A base functional-group set is defined in the catalog

**User story:** As a tenant admin onboarding a new club, I want a sensible default set of functional
groups to exist out of the box, so I am not forced to author a catalog from scratch and so fixed
fields that already name a group (`administrative`, `membership`) resolve against a real catalog
entry.

#### Acceptance criteria
1. The catalog SHALL define a **base functional-group set** with `key`, `label{nl,en}`, and `order`,
   covering at minimum the groups the current fixed/calculated registries reference or imply:
   `personal`, `membership`, `administrative`, and the `address` display group named in
   `fixed_fields.py` comments and the seed fixture (`seed_overlay.SEED_FUNCTIONAL_GROUPS`).
2. The base set SHALL be derived from / reconciled with the existing seed fixture
   (`SEED_FUNCTIONAL_GROUPS`) and the `functional_group` values actually referenced by
   `FIXED_FIELDS` / `CALCULATED_FIELDS` (`administrative`, `membership`), so no shipped field
   references a group absent from the base set. A test SHALL assert this closure (every base-field
   `default_functional_group()` resolves to a base-set key).
3. A tenant's authored functional-group catalog SHALL **extend/override** the base set (same model
   as fields: base defaults ⊕ tenant data); the design SHALL state the merge rule (e.g. tenant key
   wins; base keys fill the rest) and whether a tenant may hide a base group.
4. WHEN a field's `functional_group` references a base-set key (e.g. a fixed field under
   `administrative`) and the tenant authored no catalog THEN resolution SHALL succeed (the base set
   makes today's "empty catalog ⇒ base defaults" path reference-valid, not just unchecked).

### R6 — Display ordering is explicit for both groups and fields

**User story:** As a tenant admin, I want deterministic, authorable ordering of sections and of
fields within a section, so the group → field authoring view and the rendered modals have a stable,
intentional layout (`analysis.md` Q4.3 — "nothing today encodes cross-group display order").

#### Acceptance criteria
1. The catalog/model SHALL define **section ordering** via the functional group's `order` (today's
   `FunctionalGroup.order`, sorted `(order, key)`).
2. The catalog/model SHALL define **within-section field ordering** via each field's `order`
   attribute (today's `FixedField`/`CalculatedField`/`OverlayField` `order`, overridable via
   `FixedFieldOverride.order`).
3. The design SHALL state the ordering CONTRACT the authoring UI and any consumer rely on: a field's
   display position is `(functional_group.order, field.order, field.key)` — distinct from today's
   resolver sort key `(storage_group, order, key)`, which sorts by STORAGE bucket, not display
   group. The design SHALL make this difference explicit and decide whether the served config also
   carries the display ordering or whether the UI derives it from the group catalog + field `order`.
4. Ties (equal `order`) SHALL break deterministically by `key`, so ordering is stable across
   re-renders and re-projections.
5. Ordering SHALL be **advisory/presentation-only** (consistent with the current model where the
   module serves order but enforces nothing off it); no server behavior depends on it.

### R7 — The catalog is self-validating and drift-guarded

**User story:** As a maintainer, I want the catalog to fail fast on internal inconsistency and to be
guarded against drifting from the registries it derives from, so Phase 0's `CALCULATED_FIELD_KEYS`
drift class of bug cannot recur at the catalog layer.

#### Acceptance criteria
1. WHEN the catalog is loaded THEN it SHALL fail fast (import-time, like the existing registry
   guards) on an internal inconsistency: a duplicate attribute key, a field whose `functional_group`
   references a group absent from the base set, or an enum attribute rule contradicting the
   `FieldType` set.
2. A test SHALL assert the catalog's field inventory and each field's platform-fixed attributes stay
   in lock-step with `FIXED_FIELDS` + `CALCULATED_FIELDS` (the same drift-guard discipline Phase 0
   added for the calculated keys), so adding/renaming a registry field without updating the catalog
   fails CI.
3. The design SHALL state whether the catalog is itself the registry (single source) or a derived
   view that is tested against the registries; Phase 1 SHALL NOT create two independently-editable
   copies of the field inventory (the exact anti-pattern that caused the Phase 0 drift bug).

### R8 — Scope-binding and alias are represented as catalog attributes (declaration only)

**User story:** As a config designer, I want the catalog to already model the two residual
field attributes the analysis identified — a `scope-binding` flag and an optional `alias`/display-name
— so Phase 3 can fold scope and the address-label alias into the field model without re-opening the
catalog (`analysis.md` 2.2 / 2.5 / Q4 catalog seed).

#### Acceptance criteria
1. The catalog SHALL **declare** (describe as supported attributes) an optional `scope_binding`
   flag and an optional `alias`/display-name attribute, marked for the origins they apply to.
2. Declaring these in the catalog SHALL NOT by itself change runtime behavior: Phase 1 adds them to
   the catalog's attribute vocabulary only. The actual folding of scope-binding into the resolver
   and the alias into rendering is explicitly **Phase 3** (`impact-analysis.md` §9 steps 9–10) and
   out of scope here.
3. The design SHALL note the open question the analysis left for each (scope: how filtering is
   derived from the flag; alias: whether it is a label variant or a separate attribute) and defer
   the resolution to Phase 3, recording the catalog as forward-compatible with either outcome.

### R9 — The catalog is shaped module-neutrally so a future SAM module can adopt it (extraction-ready, not extracted)

**User story:** As a platform maintainer who knows Webshop and Events are the next SAM modules
(`impact-analysis.md` §11, steering 35), I want the Members attribute-catalog model expressed in
module-neutral terms, so the second module can reuse the SHAPE without a rewrite — while honouring
"rule of three / fold-don't-fork" (steering 35/37, `00-index.md` governance): the shared *code* is
extracted only when that second consumer actually exists, not speculatively now.

#### Acceptance criteria
1. The catalog model — the attribute vocabulary (`AttributeSpec`), the computed field inventory
   (`CatalogField`), functional-group identity + ordering, the i18n resource-key + tenant-inline
   label rule (R3), and the drift-guard pattern (R7) — SHALL be expressed WITHOUT hardcoded
   Members-specific assumptions baked into the MODEL (e.g. the attribute-spec shape, the group
   model, and the label rule carry no `members`-only concepts). Members-specific DATA (the actual
   field list, the h-dcn-shaped base groups) legitimately stays Members-specific; it is the
   model/shape that must be reusable, not the data.
2. Phase 1 SHALL NOT build a shared `sam/shared` field-catalog library or otherwise extract the
   model into a cross-module component. The catalog SHALL remain in `sam/members/domain/` (built
   module-first). Extraction to a shared block is explicitly deferred to the **second SAM module**
   (rule of three, steering 35/37) and is OUT OF SCOPE for this phase.
3. A **recommended-practice steering file** SHALL be added — `38-sam-module-field-config.md`,
   `inclusion: auto`, in the `3x` conventions layer — that captures the proven Members field-config
   lessons as GUIDANCE for a new SAM module (catalog-first; group → field → attribute with explicit
   ordering; no standalone view/analytics param objects; a first-class, versioned, observable config
   projection; a single authoring surface; and the Option-(b) i18n label rule). It SHALL point at
   Members as the reference implementation and SHALL state that the generic *code* abstraction is
   extracted on the rule-of-three, not shipped speculatively — consistent with
   `impact-analysis.md` §11 "Pre-empt / the five config lessons."
4. The steering file SHALL be registered per house governance (`00-index.md` load-behavior table
   updated to list `38` as `auto`; its topic owned by `38` and not duplicated elsewhere —
   facts-in-one-place). It SHALL remain a THIN guidance file that POINTS at this spec + the Members
   reference impl, never copying their detail.
5. R9 SHALL NOT change any Phase 1 runtime behavior or the catalog's acceptance criteria R1–R8; it
   is a shaping + documentation requirement layered on the same artifact (a design/review constraint
   plus one steering file), carrying no additional code surface beyond the steering doc.

## Out of scope (Phase 1)

- Rebuilding the authoring UI (group → field → attribute) — **Phase 3** (`impact-analysis.md` §9
  step 11); Phase 1 only produces the catalog the UI will read.
- Retiring `view_contexts` / deciding the pagination model — **Phase 2**.
- Collapsing the fixed/overlay provenance into one list + badge, and the "only `member_id` is
  fixed" (4.1) reframing — **Phase 3** (high-blast-radius; explicitly deferred).
- Folding scope-binding into the resolver and analytics/alias into field attributes at runtime —
  **Phase 3** (R8 declares them in the catalog only).
- Any change to the config home (settled = Option B) or steering 36.
- Any member-data storage move (member data stays in `sam-members`).
- **Building a shared / generic `sam/shared` field-catalog library** — deferred to the second SAM
  module (rule of three, R9.2). Phase 1 only shapes Members' catalog to be extraction-ready and
  documents the pattern as steering `38`.

## Traceability to the impact analysis / analysis / recommendation

| Req | Source |
|-----|--------|
| R1, R7 | impact-analysis §9 step 4 (author the canonical attribute catalog); analysis Q4 "canonical attribute catalog is a prerequisite"; recommendation §2.2 |
| R2 | impact-analysis §9 (each step "lands safely on its own"); recommendation §5 (model simplification not blocked) |
| R3 | analysis Q4 open i18n question + decision #8; recommendation §2.8; **user decision 2026-10-13 = Option (b)** |
| R4 | analysis 2.6 + Q4.3 (first-class object vs field attribute); recommendation §2.3 |
| R5 | analysis Q4.3 (what a group *is*); seed_overlay.SEED_FUNCTIONAL_GROUPS; fixed_fields `administrative`/`membership` references |
| R6 | analysis Q4.3 (nothing encodes display order); impact-analysis §9 step 5 (encode display order) |
| R8 | analysis 2.2 (scope as field attribute) + 2.5 (alias residual) + Q4 catalog seed; recommendation §2.5 |
| R9 | impact-analysis §11 (start Webshop/Events on the proven Members skeleton + the five config lessons); recommendation §7; steering 35/37 rule-of-three; **user decision 2026-10-13 = shape-generically + guidance steering `38`** |
