# Requirements Document

## S5c — Members-runnable-in-SPA (representative pilot, proven dev/test → prod) — Requirements

- Status: **Draft** (requirements phase — check in before design)
- Roadmap step: S5 continuation (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Primary input (settled, do not re-litigate): `analysis.md` (this folder). Its **Section F
  (F.1–F.8)** are RESOLVED decisions; its Executive Summary / Verdict / Section D table reflect
  the current state. Requirements below are built ON those decisions.
- Supersedes: **s5b** (`.kiro/specs/multi-tenant/s5b-members-runnable-in-spa/`) is **CLOSED as
  SUPERSEDED, not completed** — its reusable artifacts are carried into s5c; its shortcuts are
  unwound here.
- Reuses (does not rebuild): the **s5 domain** (`.kiro/specs/multi-tenant/s5-members-first-migration/`
  — routes/service/repository/hooks), the **s5b projection plumbing** (schema/builders/sync/reader)
  and **frontend page/modals**, and the **S4 PreTokenGen Lambda** code.
- Decisions of record: ADR 0003 (platform base), 0004 (verified-JWT only), 0005 (two-pool identity
  + MySQL system-of-record + one-directional projection), 0006 (entitlement-in-token via
  PreTokenGen reading the projection).
- Governing steering: `20-platform-architecture`, `21-identity`, `22-authentication`,
  `23-aws-accounts`, `32-frontend-ui`, `33/34` (testing), `35-sam-module-architecture-sam`,
  `40-spec-workflow`, `42-local-dynamodb`.
- Deferred (must NOT block s5c): the **generic definition-driven config-editor framework +
  draft/publish** (`.kiro/specs/myBacklog/json-editor.md`).

## Introduction

s5 built the generic Members domain; s5b made a page render but **bypassed the exact mechanism it
existed to prove** — capability was faked via a `cognito:groups` fallback, onboarding ran through a
CLI that wrote MySQL directly, local dev pointed at **prod Pool A**, and the `members.*` parameter
authoring UI was unreachable because no `members` namespace existed. s5c makes the Members app run
**representatively** in the myAdmin SPA (Ledenadministratie → Leden Overzicht and its views/modals)
and **proves the platform's central guarantee end-to-end**: the three governance facts (capability,
scope grant, tenant config) propagate MySQL → projection/token → module, first in **local dev/test**
and then in **prod** to prove the full CI/CD path (build → deploy → provision → project → verify).

The pilot's headline value is that the member surface is genuinely **tenant/parameter-driven**
(fixed base ⊕ tenant overlay, calculated fields, scope-driven visibility), not a thin hand-seeded
table, and that the capability channel is **real** (verified `custom:entitlements`, zero
`cognito:groups` fallback) rather than faked.

## Glossary

- **Three channels** — the platform fact-propagation guarantee: **capability** ("may act on
  Members") via `custom:entitlements` on the token; **scope grant** ("which subgroup") via the
  projected `scopegrant#<email>#<dimension>` row; **tenant config** (scope-dimension values +
  field overlay) via the projected `config#scope` / `config#fields` rows. See analysis Section B.
- **PreTokenGen entitlement channel** — the S4 Cognito Pre-Token-Generation Lambda that stamps
  `custom:entitlements` (roles ∩ active modules). **Generic platform infrastructure**, not a
  Members feature; Members is only its first consumer (F.2).
- **Dev/test pool `myAdmin-test`** — `eu-west-1_xyrlzfqbl`, app client `43s15cm8qcgg8an85udt0e087u`;
  the non-prod pool the module points at for local + CI (F.1).
- **Prod Pool A `myAdmin`** — `eu-west-1_Hdp40eWmu`; the production admin pool (23-aws-accounts).
- **Fixed / Parameter / Calculated fields** — the member field classification (F.7): **Fixed** =
  universal-in-code base registry; **Parameter** = tenant overlay (authored as `members.*` params);
  **Calculated** = derived, not stored. A field may be Fixed while its **enum values** are Parameter.
- **Governance track** vs **Data/migration track** — the two hard-separated provisioning tracks
  (F.7): governance is authored through SPA SysAdmin/Tenant-Admin endpoints → MySQL → `enqueue_sync`
  → projection (never scripted around); data/migration is scriptable (idempotent + dry-run + verify).
- **Scope dimension** — a tenant-configurable within-tenant partition (h-dcn's "region"); its
  allowed **values** are tenant PARAMETER data, not a platform constant (F.5/F.6).

## Guiding principles (settled — requirements enforce them)

- **Platform vs module.** The PreTokenGen entitlement channel and the generic config-editor
  framework are **generic platform infra**, NOT Members features. The **scope machinery** (scope
  dimensions, `config#scope`, `scopegrant#`) is a **generic Members-module feature**, tenant-agnostic
  and parameter-driven. Region **values** + user-defined fields are **tenant PARAMETER data**.
- **Verified-JWT only** (ADR 0004): the module authorizes from the verified token/entitlement,
  never from unverified headers and never from a `cognito:groups` capability fallback.
- **MySQL is the system of record; projection is one-directional** (ADR 0005 / steering 20).
- **Test-pool-first + gated + detach-to-rollback** for any prod/Cognito change (steering 23).
- **The PreTokenGen Lambda is fail-safe** — a resolution failure omits the claim; login still
  succeeds; the Flask plane stays authoritative.
- **Tables managed outside CFN / retain** (steering 23) — no table drops in deploy or rollback.
- **Reuse before rebuild** — the s5 domain, s5b plumbing/frontend, and S4 Lambda are carried in.
- **No `if tenant == "h-dcn"` in the generic core** — every h-dcn specific is config/parameter/data
  or a registered hook.

## Requirements

### R1 — Switch on the generic PreTokenGen entitlement channel (dev/test first, then prod)

The capability channel MUST be **implemented and proven end-to-end**, never faked and never skipped.
It is generic platform infra; s5c is the forcing function/first consumer (F.2).

- **R1.1** The S4 PreTokenGen Lambda SHALL be **wired to the dev/test pool `myAdmin-test`
  (`eu-west-1_xyrlzfqbl`) FIRST**, per the test-pool-first rule. This is deliberately BEYOND a pure
  mirror of Pool A (which has empty `LambdaConfig`): s5c adds the trigger to `myAdmin-test` to prove
  the channel Pool A does not yet exercise (F.1/F.2).
- **R1.2** Wiring SHALL follow the settled account model (ADR 0006 / D2 / F.2): the Lambda runs in
  the **data account (506221081911)** and reads the projection **same-account**; the pool attaches
  the trigger from the **identity account (344561557829)** via a cross-account `aws_lambda_permission`
  — the **invoke** crosses accounts, the **data read** does not. s5c SHALL implement the cross-account
  invoke permission from `myAdmin-test` to the data-account Lambda.
- **R1.3** With the trigger on `myAdmin-test`, a test user whose projected entitlement is non-empty
  SHALL receive a **non-empty `custom:entitlements` claim** in the token, and the Members module
  SHALL authorize off that claim with **ZERO reliance on `cognito:groups`**. Empty projection →
  empty entitlement → deny is a valid, handled outcome (fail-safe).
- **R1.4** Only AFTER R1.3 passes in dev/test SHALL the trigger be attached to **prod Pool A** as
  the gated, highest-blast-radius promotion step (R7). The Lambda SHALL remain **fail-safe** and the
  trigger SHALL be **detach-to-rollback** in both environments.
- **R1.5** The open sub-item — the exact **IAM implementation of T18** (Lambda deploy to the data
  account + cross-account invoke permission + trigger attach) — SHALL be implemented and verified by
  s5c; the design is settled (F.2), only the physical wiring remains.

### R2 — Point the module at a non-prod dev/test Cognito pool for local + CI

- **R2.1** The module's Cognito config SHALL be **repointed from prod Pool A to `myAdmin-test`** for
  local + CI (F.1): `HDCN_COGNITO_ISSUER` =
  `https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl`, the matching
  `HDCN_COGNITO_JWKS_URI` (`.../eu-west-1_xyrlzfqbl/.well-known/jwks.json`), and
  `HDCN_COGNITO_CLIENT_ID` = `43s15cm8qcgg8an85udt0e087u`. This is **config-not-code** — the
  issuer→pool registry (`auth/pool_registry.py`) selects the pool by `iss`.
- **R2.2** Local/CI SHALL log in as **throwaway test users in `myAdmin-test`**, never a prod user.
- **R2.3** The prod-Pool-A coupling in `env-vars.local.json` (`HDCN_COGNITO_ISSUER` =
  `eu-west-1_Hdp40eWmu`) SHALL be **removed** (Section D: REMOVE; deviation #4).

### R3 — `members.*` parameter schema + structured authoring UI (the reachability fix)

This is the direct fix for the reported "user-defined fields / parameter authoring UI not reachable"
blocker (analysis B.3 root cause: no `members` namespace in `parameter_schema.py`).

- **R3.1** A **`members` namespace** SHALL be declared so the schema-driven Tenant-Admin surface has
  something to render for a Members-enabled tenant. It SHALL cover three tenant parameters, gated to
  the active MEMBERS module:
  - **`members.field_overlay`** — a **map of field-overlay definitions** (*what fields exist* for the
    tenant, layered over the fixed base);
  - **`members.scope_dimensions`** — a **list of scope-dimension objects** (*how rows are
    partitioned/scoped*; the dimension `values` are the allowed scope items);
  - **`members.view_contexts`** — a **list of named view-context objects** (*which fields show
    together in a named, selectable table view*), each context field-compatible with myAdmin's
    existing `ui.tables` per-view shape (`columns` / `filterable_columns` / `default_sort` /
    `page_size`) plus `key` / bilingual `label` / `permission_roles`. This generalizes the existing
    single-view `ui.tables` mechanism to **multiple selectable contexts** (`ui.tables` itself is left
    unchanged; it stays single-view for the FIN/STR tables).
- **R3.2** Authoring SHALL **REUSE the ledger-account definition-driven typed-editor pattern**
  (`backend/src/config/ledger_parameters.json` + `GET /api/config/ledger-parameters` +
  `AccountModal.tsx` — including the `string[]`+`options` multi-select, `depends_on`, and `module`
  gate), extended only as far as Members needs: **list-of-objects** (scope dimensions) and
  **map-of-field-defs** (field overlay). It SHALL be a **structured, bilingual (nl/en), no-raw-JSON**
  editor (F.4).
- **R3.3** s5c SHALL NOT build a bespoke field-builder from scratch, SHALL NOT rely on the raw-JSON
  `ParameterManagement` editor as the authoring path, and SHALL NOT build the **generic
  config-editor framework** (that is deferred to `json-editor.md`) (F.4).
- **R3.4** The authored parameters SHALL feed the **already-built** `config#scope` / `config#fields`
  projection **unchanged**, which the module reader surfaces via the `ScopeConfigProvider` /
  `TenantOverlayProvider` seams.
- **R3.5 (write-granularity).** The editor SHALL **save the whole config object per logical edit —
  never per field/keystroke.** `members.field_overlay`, `members.scope_dimensions`, and
  `members.view_contexts` each stay **single JSON parameters**; one Save → one PUT → one
  `enqueue_sync` → one per-tenant re-projection (F.4).
- **R3.6 (draft-state).** The pilot SHALL use **save-once + an unsaved-changes guard** (warn on
  navigate-away). Draft/publish (edit, stop, continue next day) is **DEFERRED** to the generic
  framework and SHALL NOT be built in s5c (F.4).

### R4 — Field model: Fixed / Parameter / Calculated classification (explicit s5c deliverable)

- **R4.1** s5c SHALL produce a **classification table** for the h-dcn member field set, rebuilt from
  `/home/peter/projects/h-dcn/frontend/src/config/memberFields/`, assigning each field to:
  - **Fixed** — universal-in-code base registry (`sam/members/domain/fixed_fields.py`);
  - **Parameter** — tenant overlay, seeded in `members.*` params via the R3 authoring;
  - **Calculated** — derived, no stored data.
  The table (in `design.md`, Data Models) is the **authoritative source** from which the concrete
  field definitions are built (R4.10).
- **R4.2** The classification SHALL apply the rule: **a field MAY be Fixed while its enum values,
  or its format/validation constraint, are Parameter** (tenant config). Examples: `status` /
  `lidmaatschap` / `regio` are structurally fixed concepts whose **value lists** are tenant parameter
  data; `member_number` is a fixed-type `string` whose **format pattern** is tenant parameter data
  (R4.8). The field's data **type** itself stays Fixed (no per-tenant stored-type variance).
- **R4.3** The base registry (`fixed_fields.py`) SHALL be **broadened** from its current ~9 fields
  toward a representative fixed base (Section D: REFACTOR), with the remainder expressed as the
  tenant overlay — so the seeded h-dcn overlay is a real field set, not `motor_type` alone.
- **R4.4** **Calculated fields** (e.g. `korte_naam` from name parts, `jaren_lid` from
  `ingangsdatum`, `leeftijd` from `geboortedatum`) SHALL be a first-class, explicit requirement —
  derived in the domain/presentation layer, never stored.
- **R4.5** Seeding **defaults** the platform ships SHALL use **generic placeholder names** (e.g.
  Region A / Region B; Field A) — never h-dcn's real list. h-dcn authors its actual field set and
  region values **as parameter data at onboarding** (F.5/F.6).
- **R4.6 (key naming convention).** A field **key** is a stable identifier, never user-facing, never
  translated. **Fixed and Calculated keys SHALL be platform-canonical: English, `snake_case`,
  stable** (they belong to the platform base registry, read by every tenant/module). **Parameter
  (overlay) keys SHALL be tenant-authored** — the platform validates format (`snake_case`) but SHALL
  NOT impose a language (a tenant's own vocabulary, e.g. h-dcn's Dutch overlay keys, is respected).
  The gsheet→DynamoDB importer SHALL map h-dcn's Dutch **source columns** → the English **Fixed
  keys** (R8.2 / task 6.2). Renaming a Fixed key after prod seeding is a data migration, so the
  English-canonical decision is made **before** the prod cutover (R7).
- **R4.7 (bilingual labels).** Every field, scope-dimension, and view-context **label** SHALL be a
  localized `{nl, en}` map, authored bilingually (R3.2) and rendered as `label[language]`. The Dutch
  in h-dcn's field names survives as the `nl` label, not as the key. Enum **values** that are display
  text SHALL likewise carry localized labels where shown to users.
- **R4.8 (member-number: fixed-type string, parameter format; generation is a tenant policy — OUT).**
  - **Type = Fixed `string`.** `member_number` SHALL always be stored as a **string** (never a
    per-tenant numeric type) — stable, sortable, leading-zero-safe. No string↔number override.
  - **Format = Parameter.** The tenant SHALL configure the **format pattern** (e.g. a prefix +
    zero-padded width such as `Nr-0001` / `Nr-00001`, or a regex) as tenant parameter data (part of
    the `member_number` fixed-field config in `members.field_overlay`). The **domain layer SHALL
    authoritatively validate** create/edit/import input against the tenant's pattern (frontend gives
    immediate feedback; server is the authority).
  - **Uniqueness = Fixed.** The repository SHALL enforce per-tenant uniqueness (conditional write →
    409; existing behavior).
  - **Generation = tenant policy, OUT of scope.** How a value is produced (auto-counter, external ID,
    per-region range, none) is tenant-specific. For s5c the pilot SHALL support **manual entry** by
    `Members_CRUD` (typed, validated against the pattern, then held unique); h-dcn's auto-counter
    derivation SHALL remain in its existing `derive_member_number` **tenant hook** and SHALL NOT be
    promoted into the generic base. A **generic, tenant-configurable numbering function** is a future
    item and is **OUT of scope for s5c** (see R11.7). (Note: a padded format like `Nr-0001` naturally
    pairs with auto-numbering later; the pilot only validates typed input against the pattern.)
- **R4.9 (storage group vs functional group).** Two distinct grouping concepts SHALL be modelled
  separately:
  - **Storage group (structural, FIXED):** the member record has a closed set of first-class
    attributes — `personal`, `membership` (fixed-field buckets) and `overlay` (all parameter/variable
    fields) — determined by a field's **origin**, NOT tenant-configurable. A Fixed field stores under
    its `personal`/`membership` group; a Parameter field stores under `overlay`; a Calculated field is
    not stored. Adding a tenant field NEVER changes this shape (R2.2). Address fields (`street`,
    `postal_code`, `city`, `country`) are Fixed under `personal`.
  - **Functional group (presentation/organizational, PARAMETER-DRIVEN):** the field parameters SHALL
    support **tenant-defined functional groups** (e.g. Personal / Address / Membership / Motor /
    Financial / Administrative) and a **`functional_group` assignment per field** — for Fixed,
    Parameter, AND Calculated fields. The functional-group catalog (key + `{nl, en}` label + order)
    SHALL be authored in `members.field_overlay`; a Parameter field carries its `functional_group`
    inline; a Fixed/Calculated field's `functional_group` SHALL be a tenant-overridable presentation
    override (extending `FixedFieldOverride`) with a sensible default in the base. A field's
    `functional_group` SHALL be **reference-validated** against the defined groups (offer-only-defined
    at authoring; reject dangling on Save; fall back to a default section at render — R5.1a-style).
    View contexts and modals SHALL section fields by `functional_group`, independent of the storage
    group.
- **R4.10 (definitions are built FROM the classification table — traceability).** The concrete field
  definitions SHALL be **derived row-by-row from the R4.1 classification table** by each row's
  Classification: every **Fixed** row → one `FixedField` in `fixed_fields.py` (canonical EN key +
  `{nl,en}` label + type + storage group); every **Calculated** row → one derived read-only field
  (with its named inputs); every **Parameter** row → an overlay definition (seeded with generic
  placeholder names, R4.5; h-dcn's real values authored at onboarding). The mapping SHALL be
  **total**: no field is defined that is not a table row, and no table row (except those marked
  `OUT`) is left unimplemented. This traceability SHALL be asserted in tests (task 1.5).
- **R4.11 (dropdown/enum option sources).** Every dropdown's option list SHALL be **tenant data**, in
  one of four homes (no hardcoded platform vocabulary): (1) **enum values on a Fixed field** (e.g.
  `gender`, `status`) authored in `members.field_overlay`; (2) **enum values on a Parameter overlay
  field** (e.g. communication prefs, `payment_method`, `motor_brand`) inside the overlay field's
  `choices`; (3) the **Lidmaatschap Beheer catalog** for `membership_type` (active-only, module data,
  domain-validated, R5.8); (4) the **scope dimension** `values` for `region` (`members.scope_dimensions`).
- **R4.12 (role-restricted enum values + conditional visibility).** The pilot SHALL support
  **value-level role gating** (h-dcn `enumPermissions`): an enum option MAY carry a `roles`
  restriction, so a user sees/assigns only options their role permits (an option with no `roles` is
  open to anyone who may edit the field). The **domain layer SHALL authoritatively reject** a write
  setting a value the caller's role is not permitted (frontend filtering is convenience only). The
  pilot SHALL also honor **conditional visibility** (`show_when`) — a field/dropdown shown only when
  a condition holds (e.g. motor fields for certain membership types), with the server not requiring a
  hidden field.

### R5 — Representative, parameter-driven member surface (Leden Overzicht + views/modals)

"Representative" means **tenant/parameter-driven**, NOT a pixel-for-pixel port of every h-dcn screen
(F.5). Reuse the s5b frontend page/modals; broaden them.

- **R5.1 (columns + view contexts).** The Leden Overzicht table SHALL render **parameter-driven
  columns** organized into **config-driven view contexts** — a **parameter-driven list of named,
  selectable column sets** (`members.view_contexts`, R3.1), NOT a hardcoded column list. Each view
  context uses the **same per-view shape as myAdmin's existing `ui.tables`** (`columns` /
  `filterable_columns` / `default_sort` / `page_size`) plus `key` / bilingual `label` /
  `permission_roles`, generalizing `ui.tables` from its current single-view limit to multiple
  contexts. Each context column is a **`field_key` reference into the resolved field config**
  (`FieldConfig` = fixed base ⊕ tenant overlay ⊕ calculated, `GET /members/field-config`), so
  **parameter-driven (overlay) fields are first-class candidates automatically** — adding an overlay
  field then referencing it in a context are two parameter edits, no code change. The renderer SHALL
  reuse the existing shared toolkit (`useFilterableTable` / `FilterableHeader`) per selected context.
  Field-level view/edit permissions and `visible` on the resolved field remain the authoritative
  gate; a context only chooses *candidate* columns.
- **R5.1a (reference validation).** A view context (and any `field_key` it lists) SHALL be
  **validated against the resolved field set**: at authoring time the editor offers only resolvable
  keys; on Save the backend SHALL reject a context referencing an unresolvable key (mirroring
  `FieldResolver`'s fail-fast on a bad overlay); at render an unresolvable key SHALL be skipped, not
  crash (empty-is-valid). Row **scope filtering (R5.3) is always applied server-side regardless of
  the selected context** — a context chooses *which columns* show, never *which rows*.
- **R5.2 (calculated fields).** Calculated/derived fields (R4.4) SHALL appear in the table and
  modals as read-only values.
- **R5.3 (scope).** A **scope/region badge** SHALL be shown and **scope filtering** SHALL apply: a
  `Members_CRUD`/`Members_Read` user scoped to a subset (e.g. `["Region A"]`) SHALL see/act on ONLY
  members whose region ∈ that subset; admin/all → all; a scope-requiring capability with no grant →
  deny-by-default. This is driven by the projected `scopegrant#` row via `resolve_scope_access`
  (already built — B.2).
- **R5.4 (filters/sort/stats).** Per-column text + enum-select filters, per-column sort, and a live
  statistics strip SHALL be present (reusing the shared toolkit: `FilterableHeader`,
  `useFilterableTable`, region Badge, CSV export), per steering 32.
- **R5.5 (modals).** **View / edit / add / delete** modals SHALL operate over the parameter-driven
  field set, honoring field-level view/edit permissions, **value-level role-restricted enum options
  (R4.12)**, and conditional visibility (`show_when`). Dropdowns SHALL render their options from the
  correct source per R4.11, filtered to the caller's permitted values; the domain layer is the
  authoritative gate.
- **R5.6 (export).** Export SHALL be wired to the backend `export_members` action (not "coming
  soon").
- **R5.7 (transitions).** **Single + bulk lifecycle transitions** SHALL be present but kept
  **deliberately limited** — mirror h-dcn's current limited maturity; do NOT over-build the state
  machine.
- **R5.8 (membership-type dropdown).** `membership_type` SHALL be a dropdown of active **Lidmaatschap
  Beheer** catalog entries (reused from s5), validated authoritatively in the domain layer.

### R6 — Remove the s5b local fallbacks + prod-pool coupling (unwind the bypasses)

- **R6.1** `MEMBERS_LOCAL_AUTH_FALLBACK` + `_local_dev_group_grants_capability` SHALL be **REMOVED**
  — capability is no longer faked from `cognito:groups` once R1 wires PreTokenGen (Section D; B.1).
- **R6.2** The `MEMBERS_LOCAL_TENANT_ID` hardcoded-tenant fallback SHALL be **REMOVED** — tenant is
  resolved from the verified entitlement (Section D; deviation #2).
- **R6.3** The prod-Pool-A coupling in `env-vars.local.json` SHALL be **REMOVED** (R2.3).
- **R6.4** The off-model prod `Members_CRUD` Cognito group on `webmaster@h-dcn.nl` is **already
  removed (2026-09-19)**; s5c SHALL NOT re-introduce any per-tenant `Members_*` Cognito group —
  per-tenant roles live in MySQL `user_tenant_roles` (steering 21).
- **R6.5** `onboard-hdcn-local.py` SHALL be **demoted to a test fixture / data-track helper** and
  SHALL NOT substitute for SPA governance onboarding (R8; Section D).

### R7 — Gated PROD cutover proving the full CI/CD path (first-class deliverable)

Prod deployment is IN scope and is a first-class s5c deliverable — it is the ultimate proof the three
channels propagate in production (F.7). Human-run, gated, dev/test-first (steering 23).

- **R7.1** After a successful dev/test run, s5c SHALL execute the **full CI/CD path in prod**:
  **build → deploy** (`sam-members`) **→ provision** (onboard h-dcn via the prod SPA) **→ project**
  (run/observe sync) **→ verify** (scoped + general users in prod).
- **R7.2** The prod Members SAM app + `governance_projection` SHALL be **managed outside CFN /
  retain** (steering 23 constraint — not a choice); no table is created or dropped by the deploy.
- **R7.3** The live **Pool A PreTokenGen trigger** SHALL be attached as the gated promotion step
  (R1.4), only after the dev/test channel proof passes, detach-to-rollback.
- **R7.4** Verification in prod SHALL confirm: a scoped user sees only their subset; a general
  (all-scope) user sees all; capability is carried by `custom:entitlements` with zero
  `cognito:groups` reliance.
- **R7.5 (rollback).** Rollback SHALL be **non-destructive and governance-based**: detach the
  PreTokenGen trigger; remove the `MEMBERS` entitlement / scope-role assignments; re-project — with
  **NO table drops and NO data deletion**. Parallel-run safety holds because s5 uses NEW tables and
  the live h-dcn app is untouched throughout.

### R8 — Provisioning playbook: governance track vs data/migration track (dev/test-first, then prod)

The playbook SHALL be run **in dev/test first, then identically in prod**, with a **hard separation**
of two tracks (F.7).

- **R8.1 (governance track — SPA only, never scripted around).** Tenant + `MEMBERS` entitlement +
  role definitions (SysAdmin), and users' role assignments + tenant parameters (Tenant-Admin) SHALL
  be authored **through the real SPA endpoints** → MySQL → `enqueue_sync` → projection. **Role
  assignments MUST flow through the real endpoints** (a script MAY drive an endpoint but MUST NOT
  write MySQL directly), so the `enqueue_sync` → projection loop is genuinely exercised (B.2/F.8).
- **R8.2 (data/migration track — scripts OK).** These SHALL be **idempotent, dry-runnable, and emit a
  verify summary**, run dev/test-first then prod:
  - **member import** (Google-Sheet → `sam-members` DynamoDB; h-dcn `migrationHDCNLedenbestand` is
    prior art);
  - **membership-type catalog seed**;
  - **bulk Cognito user load** — create users in `myAdmin-test` for dev, Pool A for prod, from an
    **editable file derived from the existing h-dcn Cognito pool** (~10×2 + 3 users) carrying each
    user's CRUD/Read capability + scope. Cognito users are created by the script; their **role
    assignments flow through the governance endpoint** per R8.1.
- **R8.3** Each data/migration script SHALL be delivered as an **s5c task deliverable** (importer,
  catalog seed, Cognito-user loader).
- **R8.4 (config authoring granularity).** Config authoring SHALL save the whole config object once
  (R3.5); h-dcn's config is authored once at onboarding (save-once + unsaved-changes guard, R3.6).
- **R8.5 (enqueue_sync is already wired).** The on-change sync fires at every governance endpoint
  (module entitlement, role assign/remove, tenant params, tenant provisioning) — code-confirmed
  (F.8). s5c's job is to **EXERCISE it end-to-end via the SPA and observe the projection update**,
  NOT to build it.
- **R8.6 (reconciliation backstop).** s5c SHALL **confirm the periodic reconciliation backstop is
  scheduled/runnable** in dev/test and prod (the only open operational sub-item — F.8); the
  on-change path is already proven.

### R9 — Reuse, do not rebuild

- **R9.1** s5c SHALL REUSE the **s5 domain** (`sam/members/domain/*`, repository, `handler/routes.py`
  + `router.py`, the verified-auth edge core) unchanged except for the removals in R6 and the base-
  registry broadening in R4.3 (Section D verdicts: KEEP / KEEP core / REFACTOR fixed_fields).
- **R9.2** s5c SHALL REUSE the **s5b projection plumbing** (`projection_schema.py`,
  `projection_builder.py`, `projection_sync.py`, `projection_sync_trigger.py`, the module projection
  reader) and the **s5b frontend** service/types/page/modals as the base (KEEP; KEEP + REFACTOR).
- **R9.3** s5c SHALL REUSE the **S4 PreTokenGen Lambda** code (`sam/pretokengen/*`) and only WIRE it
  (R1), not rewrite it.
- **R9.4** The `module_registry.py` `MEMBERS` entry is correct and SHALL be left unchanged (KEEP).

### R10 — Enabled-but-not-built (impose NO blocking factors)

s5c SHALL NOT build these, but SHALL leave them cleanly addable (F.5):

- **R10.1 (reporting).** Reporting is crucial and MUST later live in the **Members SAM module**,
  leveraging myAdmin's existing reporting toolkit (graphs, violins, pivots, AI commands) rather than
  rebuilding it. s5c's data model + module boundaries SHALL leave it cleanly addable (open design
  sub-item: how member DynamoDB data reaches the reporting tooling — do not architect it out).
- **R10.2 (onboarding/offboarding workflows).** Full member onboarding/offboarding workflows are a
  gap even in h-dcn; NOT a porting target and NOT built in s5c, but SHALL remain addable later (basic
  add + a lifecycle status change already exist).

### R11 — Out of scope (explicitly excluded)

- **R11.1 Cognito-Beheer** — belongs to myAdmin's platform admin (SysAdmin/Tenant-Admin), not the
  Members module; SHALL NOT be ported (F.5).
- **R11.2 Welkomstpakketten** — empty in h-dcn; SHALL be ignored (F.5).
- **R11.3 Generic config-editor framework + draft/publish** — DEFERRED to `json-editor.md`; SHALL
  NOT be built in s5c (R3.3/R3.6).
- **R11.4 Projection "widening" for non-Members tenants** — irrelevant to Members; a Members-enabled
  tenant already projects the needed rows (F.3). Out of scope.
- **R11.5 Pool B (end-user pool)** — out of scope; Members admins are Pool A / test-pool users.
- **R11.6 Members ↔ Functions-module (tenant-optional-functions) integration** — expressing a
  Members per-tenant difference as a generic feature toggled on/off via the myAdmin Functions module
  (`.kiro/specs/Common/Tenant/tenant-optional-functions/` — Function_Registry + `tenant_functions`
  toggle + Function_Guard/Function_Hook) is a legitimate mechanism but is **out of scope for s5c**.
  s5c expresses h-dcn specifics via config/parameter/data/hook only (R12.6).
- **R11.7 Generic member-number numbering function** — a tenant-configurable numbering *policy*
  (auto-counter / external ID / per-region range / none) as a platform feature is **out of scope for
  s5c** (R4.8). The pilot uses manual entry; h-dcn's auto-counter stays in its existing tenant hook.

### R12 — Standing constraints (invariants that hold throughout)

- **R12.1** Verified-JWT-only; no unverified-header trust; no `cognito:groups` capability fallback.
- **R12.2** MySQL is the system of record; the DynamoDB projection is one-directional (single writer,
  versioned, idempotent, tenant-scoped, read-only for the module).
- **R12.3** Tables (module `sam-members*`, `governance_projection`) are managed outside CFN / retain.
- **R12.4** Any prod/Cognito change is **test-pool-first + gated + detach-to-rollback**.
- **R12.5** The PreTokenGen Lambda is **fail-safe** (resolution failure omits the claim; login
  succeeds; Flask plane authoritative).
- **R12.6** No `if tenant == "h-dcn"` in the generic core; every h-dcn specific SHALL be expressed
  via the generic ladder: **config → parameter → data → registered hook**. (A fifth mechanism — a
  generic feature a tenant switches on/off via the myAdmin **Functions module** /
  `tenant-optional-functions`, `.kiro/specs/Common/Tenant/tenant-optional-functions/` — is a valid
  way to express a per-tenant difference in general, but wiring Members functions into it is **out
  of scope for s5c**; see R11.6.)
- **R12.7** Tenant isolation in the repository (`tenant_id` partition key + IAM `LeadingKeys`).

## Acceptance criteria

- **Capability channel real:** the PreTokenGen trigger is attached to `myAdmin-test` first; a
  test-pool token carries a non-empty `custom:entitlements`; the module authorizes off it with zero
  `cognito:groups` reliance; the s5b `MEMBERS_LOCAL_AUTH_FALLBACK` / `_local_dev_group_grants_capability`
  are gone.
- **Dev/test pool decoupled:** module Cognito config points at `eu-west-1_xyrlzfqbl` for local + CI;
  no prod-Pool-A coupling in `env-vars.local.json`; local logs in as throwaway test users.
- **Authoring reachable:** a `members` namespace renders a structured, bilingual, no-raw-JSON typed
  editor (reusing the ledger pattern) for `members.field_overlay` (map-of-field-defs),
  `members.scope_dimensions` (list-of-objects), and `members.view_contexts` (list-of-named-column-
  sets, `ui.tables`-shaped); Save-once → one `enqueue_sync` → projection; unsaved-changes guard
  present; no draft/publish, no bespoke framework.
- **Field model:** a Fixed/Parameter/Calculated classification table exists for the h-dcn field set;
  the base registry is broadened; calculated fields (`display_name`, `years_member`, `age`) are
  derived, not stored; seeding defaults use generic placeholder names.
- **Naming + i18n:** Fixed/Calculated keys are English canonical `snake_case`; Parameter keys are
  tenant-authored (format-validated, not language-forced); all field/dimension/view-context labels
  are authored and rendered bilingually (`{nl, en}`); the importer maps Dutch source columns → English
  Fixed keys.
- **Member number:** the `member_number` field is a fixed-type `string`, repository-unique, with a
  tenant-configurable **format pattern** (e.g. `Nr-0001`) validated authoritatively in the domain;
  the pilot supports manual entry by `Members_CRUD`; no platform auto-numbering is built (h-dcn's
  counter stays in its tenant hook) — a generic numbering function is out of scope.
- **Grouping:** storage groups (`personal`/`membership`/`overlay`) are fixed by field origin;
  functional groups are tenant-defined (catalog + per-field `functional_group`, for fixed/parameter/
  calculated), authored via `members.field_overlay`, reference-validated; view contexts + modals
  section by functional group.
- **Dropdowns:** each dropdown's options come from its correct home (fixed-field enum values /
  overlay-field `choices` / membership-type catalog / scope-dimension values) — all tenant data;
  value-level role-restricted enum options are supported (frontend filters, domain rejects
  authoritatively); `show_when` conditional visibility honored.
- **Representative surface:** Leden Overzicht renders parameter-driven columns organized into
  multiple selectable, parameter-driven view contexts (each `field_key` validated against the
  resolved field set); scope badge + scope filtering work end-to-end from the projected grant and
  apply regardless of the selected context; view/edit/add/delete modals + export + deliberately-
  limited single/bulk transitions; membership-type dropdown from the catalog, domain-validated.
- **Provisioning proven:** governance authored through the SPA (SysAdmin + Tenant-Admin) with
  `enqueue_sync` → projection observed; data/migration scripts (import, catalog seed, Cognito loader)
  are idempotent + dry-run + verify; reconciliation backstop confirmed scheduled.
- **Prod CI/CD proven:** build → deploy → provision → project → verify executed in prod; scoped and
  general users verified; live Pool A trigger attached under the gate; non-destructive governance
  rollback demonstrated (no table drops, no data deletion).
- **Reuse honored:** s5 domain + s5b plumbing/frontend + S4 Lambda reused; s5b shortcuts unwound.
- **Boundaries honored:** Cognito-Beheer + Welkomstpakketten not ported; reporting + onboarding
  workflows left cleanly addable.

## Success metrics

- Zero `cognito:groups`-derived capability decisions in dev/test or prod (grep-clean for the removed
  fallbacks; authorization traces show `custom:entitlements` as the source).
- The three channels each demonstrably propagate a real governance write from the SPA to a module
  read (capability, scope grant, config) in both dev/test and prod.
- A scoped user's list is a strict subset; a general user's list is the full set — verified in prod.
- The prod cutover is fully reversible via governance rollback with no data loss.

## Out of scope (summary)

Cognito-Beheer; Welkomstpakketten; the generic config-editor framework + draft/publish; projection
widening for non-Members tenants; Pool B; a pixel-for-pixel port of every h-dcn screen; reporting and
onboarding/offboarding workflows (enabled-but-not-built — addable later, no blocking factors).

## Prerequisites (available)

- s5 domain (routes/service/repository/hooks) + generic membership model; s5b projection plumbing +
  frontend page/modals; S4 PreTokenGen Lambda code + the single resolver + `custom:entitlements`
  codec; the ledger-account typed-editor pattern; `module_registry.py` `MEMBERS` entry; standing
  test pool `myAdmin-test` (`eu-west-1_xyrlzfqbl`); Docker MySQL + local/`test_` DynamoDB (steering 42).
