# Requirements Document

**Phase 2 — Delete the Redundant Surface**

> **Status: REQUIREMENTS.** Derived from this folder's `design.md` (design-first workflow). Phase 2
> of the Members config redesign (`impact-analysis.md` §9) — exactly the two deliverables defined
> there, nothing more:
> **(6)** retire `view_contexts` (order-critical, SPA-gated); **(7)** clean dead code (the legacy
> `overrides` dual-accept + `SAMPLE_SCOPE_CONFIG`).
>
> **Prerequisites met (given):** Phase 0 (reliability fixes) and Phase 1 (catalog backbone) are DONE;
> they are not re-verified or re-opened here. Config home is settled = **Option B** (Flask authors,
> SAM reads a first-class projection; steering 36 unchanged), so Phase 2 is a symmetric removal across
> the Flask writer and the SAM reader, not a config-home change.
>
> **Explicitly out of scope — Phase 3** (`impact-analysis.md` §9 steps 8–11): collapsing fixed/overlay
> into one list + provenance badge, folding scope-binding into a field attribute, folding analytics
> into field attributes/calculated fields, and rebuilding the group → field → attribute UI. Phase 2
> speaks ONLY in "Phase 2" terms and does not reintroduce the `recommendation.md` 1–7 step numbering.

## Introduction

Phase 2 of the Members config redesign delivers exactly the two impact-analysis (`impact-analysis.md`
§9) deliverables and nothing more: retiring `view_contexts` (an order-critical, SPA-gated removal) and
cleaning dead code (the legacy `overrides` dual-accept read branches plus the `SAMPLE_SCOPE_CONFIG`
test fixture). The prerequisites are already satisfied — Phase 0 (reliability fixes) and Phase 1
(catalog backbone) are done — and the config home is settled as Option B (Flask authors, SAM reads a
first-class projection), so Phase 2 is a symmetric removal across the Flask writer and the SAM reader
rather than a config-home change. All further redesign work described as Phase 3 is out of scope here.

## Glossary

_Terms below are grounded in the current code._

- **`view_contexts`** — a Members config surface: a stored list of named, selectable column-sets
  (`key` / bilingual `label` / `permission_roles` / `columns` / `filterable_columns` /
  `default_sort` / `page_size`). PURE UI config — nothing server-side acts on its contents
  (`impact-analysis.md` §1.1). Authored as `members.view_contexts` (Flask), projected as the
  `config#views` row, read in SAM via `MembersProjectionReader.get_view_contexts`, serialized onto
  `GET /members/field-config` via `_serialize_view_context`, consumed by the SPA.
- **Field-config response / contract** — the JSON `GET /members/field-config` returns; a cross-artifact
  contract between the SAM module (server) and the SPA (client), which deploy as separate artifacts.
- **`config#views`** — the DynamoDB projection row carrying a tenant's view contexts; built by Flask's
  `build_config_views_row`, read by SAM's `get_view_contexts`.
- **`page_size`** — the per-context rows-per-page setting inside a `view_context`. The ONE residual of
  `view_contexts` that is not pure throw-away (`impact-analysis.md` §1.1 — "the real residual is
  pagination/`page_size` only").
- **`default_page_size`** — the Phase 2 home for pagination: a single tenant-level field-config
  default scalar, with a per-user preference override and a platform fallback.
- **Dual-accept** — the back-compat read branches that honour BOTH `fixed_overrides` (the canonical,
  authored/validated key) and a legacy `overrides` key when reading the stored overlay. Present in the
  Flask builder (`_projection_config_builders.py`) and the SAM reader (`projection_config_reader.py`).
- **`SAMPLE_SCOPE_CONFIG`** — a synthetic scope-dimension fixture (region North/South/East/West) in
  `sam/members/domain/scope_dimensions.py`; a test fixture only, never a runtime fallback (D16/D17).
- **Change-With-Tests contract** — the house rule (`30`/`32`/`34`) that a behavioural edit updates its
  allocated test(s) in the SAME change.
- **The Members table** — the generic filter/sort/paginate table (`useFilterableTable` /
  `FilterableHeader`) the SPA renders; the TOP-rated surface. It STAYS; Phase 2 removes the stored
  contexts that fed it.

## Requirements

### R1 — `view_contexts` is retired in a fixed, SPA-gated order

**User story:** As the owner of the TOP-rated Members runtime, I want `view_contexts` removed in the
one safe sequence, so that no deployed SPA ever reads a field a deployed server has stopped serving and
the field-config contract never breaks mid-rollout (`impact-analysis.md` §6.1 — "reverse order breaks
the field-config contract").

#### Acceptance criteria
1. THE Phase_2_Plan SHALL retire `view_contexts` in exactly four ordered steps: (a) re-home
   `page_size` to a field/tenant default, (b) strip SPA consumption, (c) remove server serialization,
   (d) drop the param + projection + domain — in that order.
2. WHEN step (a) is applied THEN THE Field_Config_Response SHALL carry the new pagination default
   ALONGSIDE the existing `view_contexts` array (additive), so that a client built before step (b)
   continues to function unchanged.
3. WHEN step (b) is applied THEN THE SPA SHALL no longer read the `view_contexts` field from the
   field-config response for any behaviour (context selection, columns, pagination, filtering).
4. THE Server SHALL NOT remove the `view_contexts` array from the field-config response (step c) until
   step (b) has shipped — i.e. step (c) SHALL depend on step (b) completing first.
5. THE Phase_2_Plan SHALL NOT delete the `view_contexts` param, the `config#views` projection row, or
   the view-context domain modules (step d) until the server has stopped serializing the array
   (step c) — i.e. step (d) SHALL depend on step (c) completing first.
6. WHILE the window between step (b) and step (c) is open, THE Server SHALL continue to serve the
   (now inert) `view_contexts` array without error, so that the backward-compat window carries no risk.
7. THE Task_Graph SHALL encode the (a) → (b) → (c) → (d) sequence as hard dependencies so that a later
   step cannot be scheduled before its predecessor completes.

### R2 — Pagination (`page_size`) is preserved as a tenant/field default, not lost

**User story:** As a tenant admin, I want the Members table to keep a sensible default page size after
`view_contexts` is gone, so that pagination is not lost when the view surface is removed
(`impact-analysis.md` §1.1 — "keep as a field/tenant default: `page_size`/pagination").

#### Acceptance criteria
1. THE Field_Config_Response SHALL expose a single tenant-level `default_page_size` scalar
   (`int` or null) that replaces the per-context `page_size`.
2. WHERE a tenant has authored a `default_page_size` THEN THE Members_Table SHALL use it as the
   default rows-per-page.
3. WHERE a user has set a per-user page-size preference THEN THE Members_Table SHALL prefer the user
   preference over the tenant `default_page_size`.
4. IF neither a user preference nor a tenant `default_page_size` is set THEN THE Members_Table SHALL
   fall back to the platform table-toolkit default, matching today's behaviour when
   `view_context.page_size` is null.
5. THE Phase_2_Plan SHALL NOT retain any per-context page size, because after the context dropdown is
   removed there is a single Members table.
6. THE `default_page_size` SHALL be authored on the Flask parameter plane (Option B) as a
   tenant/field default — NOT as a stored view object — conforming to `38-sam-module-field-config.md`
   rule 3.

### R3 — SPA consumption of `view_contexts` is stripped, the generic table kept

**User story:** As a developer, I want all SPA view-context machinery removed while the generic
filter/sort/paginate table stays, so that the TOP-rated surface is preserved and the opaque
context/"unresolved columns" UX is retired (`impact-analysis.md` §1.1, §5).

#### Acceptance criteria
1. THE SPA SHALL remove, from `MembersPage.tsx`, the view-context normalization, availability,
   selection, and dropdown machinery (`normalizeViewContexts`, `isContextAvailable`, the
   `viewContexts` / `availableContexts` / `selectedContext` / `selectedContextKey` state and memos,
   and the context `<Select>` control).
2. WHEN the view-context machinery is removed THEN THE Members_Table SHALL render over the resolved
   `FieldConfig` visible fields directly, preserving the default behaviour the empty-`columns` default
   context produced today.
3. THE SPA SHALL remove the view-context sub-editor from the typed Members config editor
   (`MembersConfig/`), while retaining every other sub-editor (fields, overrides, functional groups,
   scope, mail, analytics, status).
4. THE SPA SHALL remove the `ViewContext` type and the `view_contexts` field from the `FieldConfig`
   type, and add the optional `default_page_size` field.
5. THE SPA SHALL remove the now-dead `viewContext.*` i18n resource keys.
6. THE Members_Table filter/sort/paginate toolkit (`useFilterableTable` / `FilterableHeader`) SHALL
   remain in use for column filtering and sorting.

### R4 — The server stops serializing `view_contexts`

**User story:** As a module maintainer, I want the server to stop emitting the inert `view_contexts`
array once no client reads it, so that the field-config response carries no dead surface.

#### Acceptance criteria
1. WHEN step (c) is applied THEN THE Field_Config_Response SHALL NOT contain a `view_contexts` key.
2. THE MembershipService SHALL remove `_serialize_view_context` and the `view_contexts` array
   construction from `get_field_config`.
3. THE MembershipService SHALL remove the view-contexts provider dependency and its wiring.
4. WHEN step (c) is applied THEN THE Field_Config_Response SHALL still contain `default_page_size`
   (the step-(a) home), so pagination remains served.

### R5 — The param, projection, and domain for `view_contexts` are deleted

**User story:** As a module maintainer, I want `view_contexts` removed symmetrically from the Flask
writer and the SAM reader, so that no half-removed config surface remains
(`36-config-and-parameters.md` rule 1).

#### Acceptance criteria
1. THE Flask_Parameter_Schema SHALL NOT define a `view_contexts` param in the `members` namespace.
2. THE Flask_Validation SHALL remove `validate_view_contexts` and its dispatch branch.
3. THE Flask_Projection SHALL remove `build_config_views_row`, `_map_view_context`, their helper
   constants, and the `config#views` row assembly in `projection_sync`.
4. THE Projection_Schema SHALL remove the `config#views` record-type entry.
5. THE SAM_Projection_Reader SHALL remove `get_view_contexts`, `_build_view_context`, and the
   `config#views` id constant.
6. THE SAM_Domain SHALL delete the `view_contexts.py` and `seed_view_contexts.py` modules in full,
   and remove any provider wiring that constructed/injected a view-contexts provider.
7. WHEN step (d) is complete THEN a repository-wide search of product code SHALL return zero
   references to `view_contexts`, `ViewContext`, `get_view_contexts`, `build_config_views_row`,
   `config#views`, or `_serialize_view_context`.

### R6 — The legacy `overrides` dual-accept is removed after a one-time row migration

**User story:** As a maintainer, I want the dead legacy `overrides` read branch removed once stored
rows are migrated to the canonical `fixed_overrides` key, so that only one key is accepted and no
production row is stranded (`impact-analysis.md` §1.2).

#### Acceptance criteria
1. THE Phase_2_Plan SHALL run a one-time migration that rewrites every stored `members.field_overlay`
   config row carrying a legacy top-level `overrides` key so the data lives under `fixed_overrides`.
2. WHEN a stored overlay carries BOTH `overrides` and `fixed_overrides` keys THEN THE Migration SHALL
   keep the `fixed_overrides` entry on a per-key collision (the canonical authored key wins).
3. THE Migration SHALL rewrite the stored JSON key name only and SHALL NOT alter member records or the
   override VALUES.
4. THE Migration SHALL be idempotent — re-running after the rename SHALL make no further change.
5. THE Migration SHALL be an `administration`-scoped migration under `backend/src/migrations/`, applied
   manually via `DatabaseMigration.run_all_migrations()` (not auto-applied), using parameterized
   queries, with a dry-run default — conforming to `31-backend-database-flask-mysql.md`.
6. THE Phase_2_Plan SHALL NOT delete the dual-accept read branches (in the Flask builder and the SAM
   reader) until the migration has run — i.e. the branch deletion SHALL depend on the migration.
7. WHEN the dual-accept branches are deleted THEN THE Flask_Projection and THE SAM_Projection_Reader
   SHALL accept ONLY the `fixed_overrides` input key.
8. THE Phase_2_Plan SHALL NOT rename the internal `TenantOverlay.overrides` dataclass field or the
   `config#fields` `overrides` projected attribute, because collapsing the fixed/overlay model is
   Phase 3.

### R7 — `SAMPLE_SCOPE_CONFIG` is moved into tests

**User story:** As a maintainer, I want the synthetic scope fixture out of the domain and into the test
tree, so that no synthetic/tenant vocabulary lives in a storage-agnostic domain module (`35`,
Decision D16/D17).

#### Acceptance criteria
1. THE SAM_Domain SHALL remove `SAMPLE_SCOPE_CONFIG` from `scope_dimensions.py` (and its `__all__`
   entry and the docstring references framing it as a domain-provided sample).
2. THE Test_Suite SHALL define `SAMPLE_SCOPE_CONFIG` in a shared fixtures module under `sam/tests/`.
3. THE five current consumers (`test_scope_normalization_verify.py`, `test_scope_access.py`,
   `test_scope_dimensions.py`, `conftest.py`, `members_parity_harness.py`) SHALL import
   `SAMPLE_SCOPE_CONFIG` from the test fixtures module.
4. THE scope MODEL (`ScopeDimension`, `ScopeConfig`, `WILDCARD`, the providers) SHALL remain in the
   SAM domain unchanged — only the sample DATA moves.
5. THE relocation SHALL be behaviour-preserving — no runtime path depends on `SAMPLE_SCOPE_CONFIG`
   (it was never a runtime fallback).

### R8 — Phase 2 is non-destructive to member data

**User story:** As a data owner, I want Phase 2 to touch no member records, so that the TOP-rated
runtime's data is never at risk (`impact-analysis.md` §4.2).

#### Acceptance criteria
1. THE Phase_2_Plan SHALL NOT perform any migration of member records or any change to the member-data
   shape.
2. THE ONLY data migration in Phase 2 SHALL be the one-time `overrides → fixed_overrides` config-row
   key rename (R6).
3. WHEN any Phase 2 step is applied THEN THE Member_Data in `sam-members` SHALL be unchanged.

### R9 — Every behavioural change updates its allocated tests (Change-With-Tests)

**User story:** As a maintainer, I want the paired tests updated in the same change as each
behavioural edit, so that the deletion does not pass locally by luck and break the nightly Full Test
Suite later (`30` Change-With-Tests; `impact-analysis.md` §7).

#### Acceptance criteria
1. WHEN the view-context surface is deleted THEN THE Test_Suite SHALL delete `test_seed_view_contexts.py`
   and `MembersPage.viewContexts.test.tsx`, and rewrite the view-context assertions in
   `test_config_roundtrip_props.py` and the MembersConfig editor tests.
2. WHEN the Flask surface is removed THEN THE Test_Suite SHALL update `test_projection_sync.py`
   (no `config#views` item), `test_parameter_schema.py` (no `view_contexts` param), and the
   members_config_validation tests (no view validator).
3. WHEN the `fixed_overrides`-only read path lands THEN THE Test_Suite SHALL update
   `test_field_resolver.py` override cases to the `fixed_overrides` key.
4. WHEN pagination is re-homed THEN THE Test_Suite SHALL add a test asserting the precedence
   `userPreference ?? default_page_size ?? platformDefault` and that an absent config yields the
   platform default.
5. WHEN the one-time migration lands THEN THE Test_Suite SHALL add a migration test asserting the key
   rewrite, the collision rule, idempotence, and that member records are untouched.
6. IF two tests end up asserting contradictory behaviour about `view_contexts` THEN THE Developer SHALL
   stop and reconcile toward the intended new behaviour (absent) rather than weaken an assertion.
7. THE Test_Suite SHALL keep unchanged the tests `impact-analysis.md` §7 lists as "keep"
   (`test_calculated_fields.py`, `test_empty_is_valid_props.py`, scope logic tests apart from the
   import-path change, `test_members_projection_reader.py` apart from the views cases).

### R10 — Phase 2 ships safely through the deploy pipeline

**User story:** As a release owner, I want Phase 2 shipped through the standard pipeline with the
ordering preserved across deploy artifacts, so that the SPA-before-server sequence holds in production
(`43-cicd-deploys.md`).

#### Acceptance criteria
1. THE Phase_2_Plan SHALL use a feature branch, PR into `test`, then promote `test → main` by merge
   commit, per `43-cicd-deploys.md`.
2. THE Deploy SHALL ship step (b) (frontend, `deploy-frontend.yml`) and confirm it is live on every
   client BEFORE step (c)/(d) ship on the SAM module (`deploy-sam-members.yml`).
3. WHEN promoting to prod THEN THE Developer SHALL preview the prod changeset and confirm NO unexpected
   resource replacement (Phase 2 adds no infra/table change).
4. THE Deploy SHALL touch the DATA account only (no Cognito/identity wiring change).
5. THE one-time migration SHALL be run against TEST then PRODUCTION via the documented wrapper
   (`backend/scripts/railway-db.sh`, `#database` skill) — not auto-applied.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of the
system — a formal statement about what the system should do.*

> **Scope note (PBT classification, per `40-spec-workflow.md`).** Phase 2 is predominantly a
> *deletion* plus a one-time *re-home* and a one-time *migration*. Most acceptance criteria are
> structural ("surface X no longer exists"), example-based ("absent config → platform default"), or
> integration/ordering constraints — none of which is a "for all inputs X, P(X)" universal property.
> The genuinely universal properties below are the ones that DO quantify over inputs: the pagination
> precedence rule, the migration key-rename invariant (including the collision rule and idempotence),
> and the member-data invariance. The retained config-roundtrip props act as *regression locks* and
> are not restated here as new properties.

### Property 1: Pagination precedence is total and deterministic

*For any* combination of (user page-size preference present/absent, tenant `default_page_size`
present/absent), the resolved rows-per-page SHALL equal the first present of
`userPreference → default_page_size → platformDefault`, and SHALL always resolve to a positive integer
(never blank, never zero).

**Validates: Requirements 2.2, 2.3, 2.4, 9.4**

### Property 2: The `overrides → fixed_overrides` migration preserves data and is idempotent

*For any* stored overlay JSON, rewriting its legacy `overrides` key into `fixed_overrides` SHALL
produce an overlay whose `fixed_overrides` map contains every override entry present before (with the
pre-existing `fixed_overrides` entry winning on a key collision), SHALL leave all other overlay keys
and all member records unchanged, and SHALL be a fixed point — running the migration again produces an
identical overlay.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 8.1, 8.3**

### Property 3: Member data is invariant across every Phase 2 step

*For any* tenant's member records, applying any Phase 2 step (a config default re-home, a surface
deletion, the config-row key migration) SHALL leave the member records in `sam-members` byte-for-byte
unchanged.

**Validates: Requirements 8.1, 8.3**

### Property 4: The field-config response contains no view-context surface after step (c)

*For any* tenant (configured or unconfigured), the `GET /members/field-config` response produced after
step (c) SHALL contain no `view_contexts` key and SHALL contain a `default_page_size` entry, and the
resolved field set it serves SHALL be identical to the field set served before Phase 2 (the deletion
removes an inert array, not any field).

**Validates: Requirements 4.1, 4.4, 1.6**

## Out of scope (Phase 2)

- Collapsing fixed/overlay into one list + provenance badge; the "only `member_id` is fixed"
  reframing — **Phase 3** (`impact-analysis.md` §9 step 8).
- Folding scope-binding into a field attribute (retiring the standalone `scope_dimensions` editor) —
  **Phase 3** (step 9). Phase 2 moves only the `SAMPLE_SCOPE_CONFIG` fixture, not the scope model.
- Folding analytics into field attributes / calculated fields — **Phase 3** (step 10).
- Rebuilding the group → field → attribute authoring UI — **Phase 3** (step 11).
- Any change to the config home (settled = Option B) or steering 36.
- Any member-data storage move (member data stays in `sam-members`).
- Renaming the internal `TenantOverlay.overrides` / `config#fields.overrides` names (R6.8).

## Traceability to the impact analysis

| Req | Source |
|-----|--------|
| R1 | impact-analysis §9 step 6 (order (a)→(d)); §6.1 (reverse order breaks the field-config contract) |
| R2 | impact-analysis §1.1 ("keep as a field/tenant default: `page_size`/pagination"); §9 step 6(a) |
| R3 | impact-analysis §1.1 (SPA is the only consumer), §5 (pure UI changes); §9 step 6(b) |
| R4 | impact-analysis §1.1 (`_serialize_view_context` + the `view_contexts` array); §9 step 6(c) |
| R5 | impact-analysis §1.1 (deletable list), §4 (SAM symbols gone); §9 step 6(d) |
| R6 | impact-analysis §1.2 (legacy `overrides` dead), §6.4 (one-time rewrite before dual-accept removal); §9 step 7 |
| R7 | impact-analysis §1.3 (`SAMPLE_SCOPE_CONFIG` belongs in tests); §9 step 7 |
| R8 | impact-analysis §4.2 (no member-data migration), §6 |
| R9 | impact-analysis §7 (test blast radius); `30` Change-With-Tests |
| R10 | `43-cicd-deploys.md`; impact-analysis §6.1 (SPA-gated ordering across deploy artifacts) |
