# Requirements Document

**Phase 3 — Reshape the Model + UI**

> **Status: REQUIREMENTS.** Requirements-first for Phase 3 of the Members config redesign
> (`impact-analysis.md` §9 steps 8–11, with the model/UI stance from §3 "keep the model, change only
> the UI/authoring", §4 "SAM functions … reshaping", and §5 "pure UI changes"). Phase 3 is the
> *reshaping* phase: it changes how the Members field model is **authored and presented**, not what it
> stores — the runtime (the TOP-rated generic table) and the member data are untouched.
>
> **Prerequisites met (given — not re-opened):** Phase 0 (reliability fixes), Phase 1 (catalog
> backbone), and Phase 2 (deleted the redundant surface — `view_contexts` gone, legacy `overrides`
> dual-accept removed, `SAMPLE_SCOPE_CONFIG` moved to tests) are DONE. Config home is settled =
> **Option B** (Flask authors, SAM reads a first-class projection; `36-config-and-parameters.md`
> unchanged). Phase 4 (config-home decision) is already DECIDED = Option B, so there is no Phase 4
> work and Phase 3 is the last build phase of this redesign.
>
> **Explicitly out of scope — the two high-blast-radius bets (`impact-analysis.md` §10
> "proceed-with-caution"):** adopting "**only `member_id` is fixed**" literally across every consumer,
> and **Option C** (SAM-native authoring, which would delete the projection layer and needs a
> steering-36 revision first). Phase 3 delivers the provenance-badge re-presentation and the new
> authoring UI WITHOUT taking either bet; each is a separate, explicitly-decided future change.

## Introduction

Phase 3 reshapes the Members config *model surface and authoring experience* to the greenfield target
the redesign exists to reach, now that the backbone (Phase 1 catalog) and the subtractive cleanup
(Phase 2) are done. It delivers exactly the four `impact-analysis.md` §9 Phase 3 steps:

- **(8)** collapse the fixed/overlay two-section split into **one field model** (fields reached via the
  group → field drill-down); provenance is DERIVED and drives the field modal's available actions, not a
  shown badge;
- **(9)** fold **scope-binding into a field attribute** (retire the standalone `scope_dimensions`
  editor) while keeping the scope resolution code unchanged;
- **(10)** fold **analytics fully into field attributes / calculated fields** (analytics already rides
  on `config#fields`; represent jubilee-years-type needs as calculated fields and the role aliases as
  field attributes, then remove the separate analytics object from the authoring surface);
- **(11)** rebuild the **group → field → attribute authoring UI** — the largest single piece and where
  the user's core complaint (authoring is awful) is actually resolved.

Phase 3 also retires the **dual editing surface** (`impact-analysis.md` §5): keep the typed
`MembersConfig` editor, exclude the `members.*` namespace from the raw generic parameter editor so
there is **one authoring door**, per `38-sam-module-field-config.md` rule 5.

The guiding constraint from `impact-analysis.md` §3/§4 is that these are **mostly UI / authoring
re-presentation on top of a model that already stores one `field_overlay` object** — the SAM resolution
and scope-access code stay; the Flask projection stays; member data is never touched. The one genuine
model simplification considered — "only `member_id` is fixed" — is deliberately NOT taken this phase
(it is called out as out of scope above), so the provenance collapse is a *presentation* change plus a
bounded `_apply_override` simplification, not a model migration.

## Glossary

_Terms below are grounded in the current code._

- **Fixed vs overlay (provenance)** — today the Members editor presents two sections: fixed base fields
  (`sam/members/domain/fixed_fields.py`) and tenant overlay fields/overrides
  (`TenantOverlay` in `field_resolver.py`). `_as_variable_field` / `_apply_override` carry the
  fixed-vs-overlay distinction through `FieldResolver.resolve`. The sub-editors already write ONE
  `field_overlay` object (`impact-analysis.md` §5).
- **Provenance (derived)** — the Phase 3 re-presentation: the fixed-vs-overlay split collapses into one
  field model, and each field's origin (base / tenant-added / base-overridden) is a SYSTEM-DERIVED,
  read-only signal on the resolved config. It is NOT shown as a badge — it GOVERNS which actions the
  field modal offers (destructive delete for a tenant-added field; reset-to-default / hide for a base
  field), replacing the two-section split (`impact-analysis.md` §9 step 8).
- **`field_overlay`** — the single stored object the typed editor already authors (fields +
  `fixed_overrides` + functional groups + analytics slice), projected as the `config#fields` row.
- **Scope dimension** — a tenant scope axis (`ScopeDimension{key,label,field,values,enabled,...}`) in
  `config#scope`, read by `MembersProjectionReader.get_scope_config` → `ScopeConfig`; resolved into
  `allowed_scopes` in `handler/app.py`. **Already field-bound** — each dimension names the member field
  it filters (`impact-analysis.md` §3, D1a).
- **Scope-as-field-attribute** — the Phase 3 authoring re-presentation: express a field's scope-binding
  as an attribute on the field itself, instead of a standalone `scope_dimensions` editor. The
  resolution code in `handler/app.py` is unchanged (`impact-analysis.md` §9 step 9).
- **Analytics slice** — `AnalyticsConfig` / `AnalyticsRole` / `JubileeRule` / `AddressMapping`; already
  stored on the `config#fields` row (ODI-2), NOT a standalone param (`impact-analysis.md` §0.2).
- **Calculated field** — a code-defined, import-time-guarded, never-stored computed field in the
  9-field registry (`calculated_fields.py`). The mechanism that absorbs analytics needs such as
  jubilee years (`impact-analysis.md` §3, §4).
- **Dual editing surface** — the typed `MembersConfig` editor AND the raw generic parameter editor
  (`ParameterManagement.tsx`, mounted via `AdvancedTab.tsx`) both exposing `members.*` rows
  (`impact-analysis.md` §5). Phase 3 keeps the typed editor and hides the `members.*` namespace from
  the raw editor.
- **Attribute catalog** — the canonical, drift-guarded field vocabulary from Phase 1
  (`sam/members/domain/attribute_catalog.py`); the backbone the new UI authors against
  (`38-sam-module-field-config.md` rule 1).
- **Change-With-Tests contract** — the house rule (`30`/`32`/`34`) that a behavioural edit updates its
  allocated test(s) in the SAME change.
- **The Members table** — the generic filter/sort/paginate runtime (`useFilterableTable`); the
  TOP-rated surface. UNCHANGED by Phase 3 (Phase 3 reshapes authoring, not the runtime).

## Requirements

### R1 — Fixed and overlay fields are one model; provenance is derived and drives field actions, not a badge

**User story:** As a tenant admin, I want to work with one field model — not a confusing fixed-vs-overlay
split the store does not actually keep as two things — and I want the editor to offer the RIGHT actions
for each field (delete a field I added, reset/hide a platform field) without making me reason about an
origin label (`impact-analysis.md` §5, §9 step 8).

#### Acceptance criteria
1. THE Members_Config_Editor SHALL present base and tenant fields through a SINGLE field model (one
   `field_overlay` object), replacing the two-section fixed/overlay split — fields are reached through
   the group → field drill-down of R4, not a separate flat "unified list" surface.
2. THE Field_Resolver SHALL continue to DERIVE each field's provenance (base, tenant-added, or
   base-overridden) on the resolved config; provenance is a SYSTEM-DERIVED, READ-ONLY signal, never a
   tenant-authored attribute.
3. THE Members_Config_Editor SHALL use the derived provenance to govern the ACTIONS the field modal
   offers rather than displaying a provenance badge: a tenant-added field SHALL offer destructive
   delete; a base field SHALL offer reset-to-default / hide (not destructive delete); a base-overridden
   field SHALL offer reset-to-default. THE editor SHALL NOT surface provenance as its own shown
   attribute or badge.
4. THE field model SHALL order fields by the catalog ordering rule `(group.order, field.order, key)`
   per `38-sam-module-field-config.md` rule 2 — THE Members_Config_Editor SHALL NOT introduce a new
   stored position field.
5. THE Members_Config_Editor SHALL continue to author a SINGLE `field_overlay` object (one save → one
   re-projection), per `38-sam-module-field-config.md` rule 5 — the collapse is a presentation change,
   not a new stored shape.
6. THE Phase_3_Plan SHALL NOT adopt the "only `member_id` is fixed" reframing as a model change; the
   provenance collapse SHALL be a presentation re-presentation plus a bounded `_apply_override`
   simplification only, keeping every current fixed field immovable.
7. WHEN the fixed/overlay presentation is collapsed THEN THE Field_Config_Response resolved field SET
   and ordering SHALL be identical to before Phase 3 (no field added, removed, or reordered by the
   re-presentation).

### R2 — Scope-binding is authored as a field attribute, resolution code unchanged

**User story:** As a tenant admin, I want to bind scope to a field from the field itself rather than a
separate scope-dimensions editor, so that scope configuration lives where the field is authored
(`impact-analysis.md` §3, §9 step 9).

#### Acceptance criteria
1. THE Members_Config_Editor SHALL express a field's scope-binding (that the field is a scope axis and
   its enabled/value vocabulary) as an attribute on that field.
2. THE Members_Config_Editor SHALL retire the standalone `scope_dimensions` sub-editor once scope is
   authored as a field attribute.
3. THE scope resolution code in `sam/members/handler/app.py`
   (`resolve_scope_access_for_config`, `_resolve_scope_access_for_admin`, `_gating_dimension_key`,
   `allowed_scopes`) SHALL remain unchanged — Phase 3 changes the authoring representation only
   (`impact-analysis.md` §3 — "the resolution code can stay").
4. THE scope grants model (`scopegrant#<email>#<dim>` projected rows) SHALL be unchanged.
5. WHERE the authoring representation changes THEN THE projected scope config consumed by the resolver
   SHALL remain semantically equivalent — the resolver SHALL produce the same `allowed_scopes` for the
   same tenant/user as before Phase 3.
6. THE Phase_3_Plan SHALL be behaviour-preserving for row-scope enforcement: a user's visible rows
   SHALL be identical before and after Phase 3 for the same scope grants.

### R3 — Analytics is folded into field attributes / calculated fields

**User story:** As a maintainer, I want analytics needs expressed as calculated fields and field
attributes rather than a distinct analytics object, so that there is no separate analytics authoring
surface to reason about (`impact-analysis.md` §0.2, §4, §9 step 10).

#### Acceptance criteria
1. THE Members_Config_Editor SHALL represent jubilee-years-type analytics needs as calculated fields
   (the `calculated_fields.py` registry), not as a standalone analytics object in the authoring UI.
2. THE Members_Config_Editor SHALL represent analytics field-role aliases (e.g. cancellation-date,
   referral-source, address-mapping) as field attributes, not as a distinct analytics editor section.
3. WHEN analytics is folded in THEN THE Members_Config_Editor SHALL remove the separate analytics
   sub-editor section from the authoring UI.
4. THE analytics data SHALL continue to ride on the existing `config#fields` row — Phase 3 SHALL NOT
   introduce a new `members.*` analytics param (there is none today, `impact-analysis.md` §0.2).
5. THE calculated-field registry SHALL remain code-defined, import-time-guarded, and never stored,
   unchanged in mechanism (`impact-analysis.md` §3 — "calculated fields: keep as-is").
6. THE Phase_3_Plan SHALL be behaviour-preserving: any analytics-derived value surfaced today SHALL be
   produced by the equivalent calculated-field / attribute representation after Phase 3.

### R4 — The authoring UI is a group → field → attribute drill-down (table → modal → table → modal)

**User story:** As a tenant admin, I want to DESIGN the system from my functional view — starting from
functional groups, drilling into the fields of a group, then into a field's attributes — so that
configuring Members is intuitive, because the whole model is just "every concept is an attribute of a
field, and every field belongs to a group" (`impact-analysis.md` §9 step 11, §10). There are no
separate editors for scope, analytics, or provenance — those collapse into field attributes reached by
this drill-down.

#### Acceptance criteria
1. THE Members_Config_Editor SHALL present authoring as a group → field → attribute drill-down built on
   the Phase 1 attribute catalog (`38-sam-module-field-config.md` rules 1 and 2), composed as:
   (a) a FUNCTIONAL-GROUPS TABLE; (b) a GROUP MODAL opened by row-click; (c) a FIELDS TABLE of that
   group's fields revealed from the group modal; (d) a FIELD MODAL opened by row-click. Each table uses
   the registered Table/Filter framework and the row-click-opens-modal convention (`32`).
2. THE Functional_Groups_Table SHALL let a tenant CREATE a new functional group and EDIT an existing
   group's attributes (`key`, `label`, `order`) via the group modal, and SHALL let a tenant DELETE a
   group ONLY WHEN that group has no fields; a non-empty group SHALL NOT be deletable (the UI guards it
   and the backend validator remains authoritative on save).
3. THE Field_Modal SHALL expose ALL editable field options as attributes — including name/key, type,
   label, required, visibility, the scope-binding attribute (R2), the analytics-role/alias attribute
   (R3), and calculated-from — with add / edit / delete of attributes, AND SHALL offer a "move to
   another group" action that reassigns the field's `functional_group` to another defined group.
4. THE Members_Config_Editor SHALL derive display order as `(group.order, field.order, key)` — NOT a
   stored absolute position — for both the groups table and each group's fields table.
5. THE new UI SHALL offer only catalog-resolvable field keys and defined-group references in its
   pickers (no free-text that can reference a non-existent field/group), per the catalog-first rule;
   the "move to another group" picker SHALL offer only defined groups.
6. THE new UI SHALL render i18n labels via resource keys with an inline per-language tenant override,
   per `38-sam-module-field-config.md` rule 6 (Option b) — an enum `value` is language-neutral, only
   its `label` is per-language.
7. THE new UI SHALL compose from the registered building blocks where applicable (the Table/Filter
   framework, LazySelect, the API/error standard) per `37-shared-building-blocks.md`, rather than
   growing bespoke equivalents, and SHALL meet the `32-frontend-ui.md` conventions (table & modal
   layout, i18n, row-click-opens-modal) and be accessibility-compliant.
8. THE new UI SHALL save through the single typed save path (one save → one re-projection), per
   `38-sam-module-field-config.md` rule 5 — group create/edit/delete, field edits, attribute
   add/edit/delete, and move-to-group all author the one `field_overlay` object.

### R5 — There is one authoring surface (the dual editing surface is retired)

**User story:** As a SysAdmin, I want the Members config authored in exactly one place, so that the
typed editor and the raw parameter editor cannot drift or confuse (`impact-analysis.md` §5;
`38-sam-module-field-config.md` rule 5).

#### Acceptance criteria
1. THE Raw_Parameter_Editor (`ParameterManagement.tsx`, mounted via `AdvancedTab.tsx`) SHALL exclude
   the `members.*` namespace from the rows it exposes.
2. THE Raw_Parameter_Editor SHALL continue to serve every OTHER namespace unchanged — the component
   SHALL NOT be removed.
3. THE typed `MembersConfig` editor SHALL be the single authoring surface for the `members.*` namespace.
4. WHEN the dual surface is retired THEN no path in the SPA SHALL allow editing a `members.*` parameter
   row outside the typed editor.

### R6 — The SAM model reshaping is bounded and layering-preserving

**User story:** As a module maintainer, I want the SAM-side changes limited to the bounded
`_apply_override` simplification and no more, so that the four-seam layering and the resolution
pipeline stay intact (`35-sam-module-architecture-sam.md`; `impact-analysis.md` §4).

#### Acceptance criteria
1. THE FieldResolver SHALL keep its merge + sort + project pipeline; Phase 3 SHALL only simplify the
   `_apply_override` / fixed-vs-overlay branch to the extent the provenance re-presentation requires.
2. THE SAM domain / repository / handler seams SHALL remain intact (`35-sam-module-architecture-sam.md`)
   — Phase 3 SHALL NOT move a DynamoDB touch-point out of the repository or add business logic to the
   handler edge.
3. THE Phase_3_Plan SHALL NOT delete the projection builders, `projection_sync` config rows, or the
   version machinery (that is Option C, explicitly out of scope — `impact-analysis.md` §9 step 12,
   §10).
4. THE Phase_3_Plan SHALL NOT rename the stored `config#fields` `overrides` attribute or the
   `TenantOverlay.overrides` dataclass field unless a dedicated, separately-decided change calls for it
   (continuing the Phase 2 R6.8 guard).

### R7 — Phase 3 is non-destructive to member data

**User story:** As a data owner, I want Phase 3 to touch no member records, so that the TOP-rated
runtime's data is never at risk (`impact-analysis.md` §4.2, §9).

#### Acceptance criteria
1. THE Phase_3_Plan SHALL NOT perform any migration of member records or any change to the member-data
   shape.
2. WHEN any Phase 3 step is applied THEN THE Member_Data in `sam-members` SHALL be unchanged.
3. IF a config-row shape change is required to fold analytics/scope into fields THEN it SHALL be a
   config-row (parameter / `config#...`) change only, applied via the documented migration path
   (`31-backend-database-flask-mysql.md`), never a member-record change.

### R8 — Every behavioural change updates its allocated tests (Change-With-Tests)

**User story:** As a maintainer, I want the paired tests updated in the same change as each behavioural
edit, so that the reshaping does not pass locally by luck and break the nightly Full Test Suite later
(`30` Change-With-Tests; `impact-analysis.md` §7).

#### Acceptance criteria
1. WHEN the `_apply_override` branch is simplified THEN THE Test_Suite SHALL update
   `test_field_resolver.py` provenance/override cases to the new representation without weakening the
   resolved-field-set assertions.
2. WHEN scope-binding becomes a field attribute THEN THE Test_Suite SHALL update the scope-config
   authoring/validation tests while keeping the scope resolution tests
   (`test_scope_access.py`, `test_scope_dimensions.py`) asserting the SAME `allowed_scopes` outcomes.
3. WHEN analytics is folded in THEN THE Test_Suite SHALL update the analytics authoring tests to the
   calculated-field / attribute representation and keep `test_calculated_fields.py` green.
4. WHEN the new authoring UI lands THEN THE Test_Suite SHALL add Vitest + RTL tests for the
   group → field → attribute drill-down (groups table → group modal → fields table → field modal),
   group create/edit/delete-when-empty, field move-to-group, provenance-driven field-modal actions
   (delete vs reset/hide), the picker-resolvability guard, and the single-save path
   (`33-frontend-testing.md`).
5. WHEN the raw editor excludes `members.*` THEN THE Test_Suite SHALL add a test asserting the
   `members.*` namespace is not editable in `ParameterManagement.tsx` and every other namespace still
   is.
6. IF two tests end up asserting contradictory behaviour about field provenance, scope, or analytics
   THEN THE Developer SHALL stop and reconcile toward the intended new behaviour rather than weaken an
   assertion.
7. THE catalog drift guard (`38-sam-module-field-config.md` rule 1) SHALL remain green across every
   Phase 3 change.

### R9 — Phase 3 ships safely through the deploy pipeline

**User story:** As a release owner, I want Phase 3 shipped through the standard pipeline, so that the
authoring changes reach production without risk to the runtime (`43-cicd-deploys.md`).

#### Acceptance criteria
1. THE Phase_3_Plan SHALL use a feature branch, PR into `test`, then promote `test → main` by merge
   commit, per `43-cicd-deploys.md`.
2. WHEN promoting to prod THEN THE Developer SHALL preview the prod changeset and confirm NO unexpected
   resource replacement (Phase 3 adds no infra/table change).
3. THE Deploy SHALL touch the DATA account only (no Cognito/identity wiring change).
4. WHERE a config-row migration is required (R7.3) THEN it SHALL be run against TEST then PRODUCTION via
   the documented wrapper (`backend/scripts/railway-db.sh`, `#database` skill) — not auto-applied.
5. THE Phase_3_Plan SHALL update the steering it changes (definition-of-done, `40-spec-workflow.md`):
   if the authoring model documented in `38-sam-module-field-config.md` evolves (e.g. the
   group → field → attribute drill-down, provenance-driven field-modal actions, scope-as-attribute
   become part of the reference pattern), that steering SHALL be updated in the same change; if nothing
   changes, the close-out SHALL record "no steering change due" with evidence.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of the
system — a formal statement about what the system should do.*

> **Scope note (PBT classification, per `40-spec-workflow.md`).** Phase 3 is predominantly an
> *authoring/presentation* reshaping over an unchanged store and runtime. Most acceptance criteria are
> structural ("the UI presents X", "the raw editor hides the namespace") or behaviour-preserving
> equivalences, not "for all inputs X, P(X)" universals. The genuinely universal properties below are
> the equivalences that MUST hold for every input: the resolved field set/order invariance across the
> provenance collapse, the scope-resolution equivalence across the authoring-representation change, and
> member-data invariance. The existing config-roundtrip and resolver property suites act as regression
> locks and are not restated here as new properties.

### Property 1: The fixed/overlay collapse preserves the resolved field set and order

*For any* tenant config, the resolved field set and its derived order `(group.order, field.order, key)`
produced by `FieldResolver.resolve` after the fixed/overlay presentation is collapsed SHALL be
identical to the set and order produced before Phase 3 — the collapse adds, removes, and reorders
nothing.

**Validates: Requirements 1.6, 6.1**

### Property 2: Scope resolution is equivalent across the authoring-representation change

*For any* tenant scope config and user scope grants, the `allowed_scopes` the resolver
(`handler/app.py`) computes after scope-binding is authored as a field attribute SHALL equal the
`allowed_scopes` it computed before Phase 3 for the same inputs — the authoring representation changes,
the resolved access does not.

**Validates: Requirements 2.3, 2.5, 2.6**

### Property 3: Analytics folding is value-equivalent

*For any* tenant whose analytics config produces a derived value today (jubilee flag, alias-resolved
field), the equivalent calculated-field / field-attribute representation after Phase 3 SHALL produce
the same derived value for the same member record.

**Validates: Requirements 3.6**

### Property 4: Member data is invariant across every Phase 3 step

*For any* tenant's member records, applying any Phase 3 step (presentation collapse, scope-as-attribute,
analytics folding, UI rebuild, raw-editor exclusion) SHALL leave the member records in `sam-members`
byte-for-byte unchanged.

**Validates: Requirements 7.1, 7.2**

## Out of scope (Phase 3)

- Adopting "**only `member_id` is fixed**" literally across every consumer — the high-blast-radius
  model simplification (`impact-analysis.md` §4.1, §10 "proceed-with-caution"). Phase 3 keeps all
  current fixed fields immovable and does the provenance collapse as a presentation change.
- **Option C** (SAM-native authoring) — would delete the Flask projection builders / `projection_sync`
  config rows / version machinery and requires a steering-36 revision first; explicitly rejected
  (`impact-analysis.md` §9 step 12, §10). Config home stays Option B.
- Renaming the internal `TenantOverlay.overrides` / `config#fields.overrides` names (continues the
  Phase 2 R6.8 guard) unless separately decided.
- Any change to the generic Members table runtime (`useFilterableTable`) — it is the TOP-rated surface
  and is not reshaped.
- Any member-data storage move (member data stays in `sam-members`).
- Starting the next SAM modules (Webshop, Events) — `impact-analysis.md` §11 is forward guidance, not
  Phase 3 work.

## Traceability to the impact analysis

| Req | Source |
|-----|--------|
| R1 | impact-analysis §9 step 8 (collapse fixed/overlay → one field model; the §9 label says "one list + provenance badge", but the delivered form per `design.md` is the group → field drill-down with provenance DRIVING the field-modal actions, not a shown badge); §5 (sub-editors already write one object); §4 (`_apply_override` simplifies) |
| R2 | impact-analysis §9 step 9 (fold scope-binding into a field attribute); §3 (scope already field-bound, resolution code stays) |
| R3 | impact-analysis §9 step 10 (fold analytics into fields/calculated); §0.2 (analytics already not a param), §4 |
| R4 | impact-analysis §9 step 11 (rebuild group → field → attribute UI); §10 (the main investment) |
| R5 | impact-analysis §5 (retire the dual editing surface, exclude `members.*` from the raw editor); `38` rule 5 |
| R6 | impact-analysis §4 ("not a deletion but a reshaping"); §9 step 12 / §10 (Option C and 4.1 out of scope) |
| R7 | impact-analysis §4.2 (no member-data migration) |
| R8 | impact-analysis §7 (test blast radius); `30` Change-With-Tests |
| R9 | `43-cicd-deploys.md`; `40-spec-workflow.md` governance definition-of-done |
