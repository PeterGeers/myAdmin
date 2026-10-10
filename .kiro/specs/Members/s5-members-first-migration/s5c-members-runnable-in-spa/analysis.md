# S5c — Members-runnable-in-SPA: grounded gap analysis (should-have-been vs has-been)

- Status: **READ-ONLY decision-support analysis** (not a spec). No code or spec files were
  modified to produce this. Written to help a requirements author write a correct **s5c**
  spec.
- Method: every claim below is checked against actual code/config/specs in
  `/home/peter/projects/myAdmin` (platform) and `/home/peter/projects/h-dcn` (reference
  app). Where a fact could not be verified from the code it is marked **UNVERIFIED**.
- Sources read: roadmap S5 (`Analysis/overall_roadmap.md`); ADR 0003/0005/0006
  (`docs/decisions/`); steering 20/21/22/23/35/42 (`.kiro/steering/`); s5 spec
  (`requirements.md`, `generic-membership-design.md`, `scope-dimension-design.md`,
  `members-wireframe.md`, `go-no-go.md`); s5b spec (`tasks.md` incl. Session notes);
  h-dcn frontend (`MemberAdminPage.tsx`, `MemberAdminTable.tsx`, `config/memberFields/*`,
  `config/workflows/membershipWorkflow.ts`) + backend (`handler/`, `shared/auth_utils.py`);
  myAdmin `sam/members/*`, `sam/pretokengen/*`, `backend/src/services/projection_*.py`,
  `parameter_schema.py`, `parameter_service.py`, `module_registry.py`,
  `scripts/local/onboard-hdcn-local.py`, and the members frontend
  (`MembersPage.tsx`, `components/members/*`, `membersApiService.ts`, `types/members.ts`,
  `hooks/useMemberFieldConfig.ts`).

---

## Executive summary (the biggest gaps + disposition recommendation)

The prior pilot (s5b) is **runnable but not representative, and it bypassed the exact
mechanism it was meant to prove.** Three specific, code-confirmed bypasses: (1) capability
never travelled the S4 token channel — no PreTokenGen trigger exists on any pool the module
uses, so a flag-gated `cognito:groups` fallback (`MEMBERS_LOCAL_AUTH_FALLBACK`) fakes it;
(2) onboarding ran through a CLI script (`onboard-hdcn-local.py`) that writes MySQL rows
directly, not through the SPA SysAdmin/Tenant-Admin surfaces; (3) local dev is pointed at
**prod Pool A** (`eu-west-1_Hdp40eWmu`) and an off-model `Members_CRUD` group was added to a
prod user to make the page work. The member model is also **thin vs the real h-dcn app**:
the module's fixed registry is ~9 fields (name/contact/address/birthdate + member_number/
status/membership_type/joined/left) against h-dcn's ~30+ fields across Personal/Address/
Membership/Motor/Financial/Administrative, five table view-contexts, and rich enums. The
**user-defined-field / parameter authoring UI is unreachable** because `members.*` is never
declared in `parameter_schema.py` (the schema-driven Tenant-Admin UI has nothing to render);
the projection builder + CLI read/write `members.scope_dimensions`/`members.field_overlay`
directly, so nobody could author them through the SPA. Disposition: **KEEP s5** as the domain
reference (its module domain/repository/routes and generic model are sound and heavily
tested), **mark s5b SUPERSEDED by s5c** (keep its real artifacts — the SAM template, domain
wiring, projection C2 rows, frontend page/modals — and unwind its shortcuts; the off-model
prod `Members_CRUD` group was **already removed 2026-09-19**). Note the capability channel
was not a defect but a **deliberately-deferred generic-platform prerequisite** (ADR 0006 / S4
T18): s5b faked it rather than switching it on. s5c should **own**: switching on that generic
PreTokenGen channel (dev/test then prod), a non-prod dev/test pool, the `members.*` parameter
schema + authoring UI, a representative member surface, and a gated prod cutover; and **reuse**
the s5 domain + the s5b frontend/projection plumbing + the S4 PreTokenGen Lambda.

**Verdict**: NEEDS_CHANGES — a new **s5c** spec is warranted, and **s5b is CLOSED as SUPERSEDED, not completed** (no further work happens inside the s5b spec; its reusable artifacts are carried into s5c). "Not a completed pilot" means the roadmap must NOT record the Members pilot as done/passed — s5b demonstrated a page rendering over hand-seeded data but did not prove the end-to-end fact-propagation the pilot exists to prove. **Note on verification status:** Section B was the initial investigation; several of its points were subsequently VERIFIED against code/steering and RESOLVED in Section F (F.2 the PreTokenGen channel as a deferred generic prerequisite; F.3 the backing-agnostic resolver + the projection gate; F.8 the `enqueue_sync` wiring, code-confirmed at every endpoint). The only items still genuinely UNVERIFIED are the **physical IAM wiring of T18** (Lambda deploy + cross-account invoke permission + trigger attach — the *design* is settled, only the implementation remains) and whether the **periodic reconciliation backstop is scheduled** in each environment. Any change to Cognito or prod stays gated + test-pool-first + detach-to-rollback regardless.

---

## A. Representative target (should-have-been) — the real h-dcn Leden Overzicht

Grounded in the actual h-dcn app. A requirements author can lift acceptance criteria
directly from these files.

**Screen shape** (`frontend/src/modules/members/MemberAdminPage.tsx`): a
`Ledenadministratie` page with a Chakra `Tabs` set — **Leden Overzicht** (always),
**Rapportages** (Members_Read/CRUD/Export/System_User_Management), **Welcome Packs**
(Members_CRUD), **Cognito Beheer** (System_User_Management/Members_CRUD, with nested
Gebruikers/Groepen/Pool-instellingen sub-tabs). A plain `hdcnLeden` member is routed to a
**self-service view** of their own record instead of the table. Data load forces a
cache-bypassing fetch and applies regional filtering client-side.

**The table** (`frontend/src/components/MemberAdminTable.tsx`, 792 lines) — the
representative surface:
- **Multiple view "contexts"** selectable from a dropdown, each a different column set
  (`config/memberFields/tableConfig.ts`): `memberOverview`, `memberCompact`, `motorView`
  (motor-focused for rides/events), `communicationView` (mailing/clubblad/newsletter/
  privacy), `financialView` (payment method + IBAN, IBAN masked in the table). Contexts are
  permission-gated per role.
- **Columns actually present** across contexts: `lidnummer`, `korte_naam` (calculated full
  name), `geboortedatum`, `email`, `telefoon`, `straat`, `postcode`, `woonplaats`, `land`,
  `regio`, `status`, `lidmaatschap`, `ingangsdatum`, `jaren_lid` (computed from
  ingangsdatum), plus motor (`motormerk`, `motortype`, `bouwjaar`, `kenteken`),
  communication (`clubblad`, `nieuwsbrief`, `privacy`), and financial (`betaalwijze`,
  `bankrekeningnummer`).
- **Filters**: per-column `FilterableHeader` text filters + in-header `select` dropdown
  filters for enum columns (region/status/lidmaatschap etc.), plus sort per column
  (`useFilterableTable`). A live **statistics strip** shows counts per status and the highest
  `lidnummer`, responsive mobile/desktop layouts.
- **Bulk actions**: row checkboxes (shown only for `Members_CRUD`/`Members_Status_Approve`),
  select-all/indeterminate, a `BulkActionBar`, `useBulkTransition`, and a `BulkResultSummary`
  modal (bulk lifecycle transitions).
- **Row interaction**: row-click opens `MemberEditView` (unified view/edit modal, 809 lines);
  add-member routes to a membership application form; export is present in the UI
  (`onExport`) but the current handler shows "coming soon" (backend `export_members` exists).

**Modals / views**: `MemberEditView` (view+edit unified), `MemberReadView`,
`MemberSelfServiceView`, `NewMemberApplicationForm` / `MemberApplicationForm`,
plus `modules/members/components/`: `MemberDetailModal`, `MemberEditModal`,
`MembershipFormModal`, `MemberWorkflowPanel` + `MemberWorkflowTimeline`,
`TransitionConfirmDialog`, `GroupManagement`/`GroupModal`/`GroupMembersModal`,
`UserManagement`/`UserModal`, `PoolSettings`, `CsvUpload`, `WelcomePackList`.

**User-defined / variable fields (representative meaning)**: h-dcn's member fields are a
**field-registry** (`config/memberFields/fields/*.ts`) grouped Personal / Address /
Membership / Motor / Financial / Administrative, each field carrying `label`, `dataType`,
`inputType`, `enumOptions`, `enumPermissions` (role-restricted enum values), `validation`,
`showWhen` (conditional visibility, e.g. motor fields only for `Gewoon lid`/`Gezins lid`),
`conditionalEdit`, `permissions` (view/edit per role + `regionalRestricted`), computed
fields (`jaren_lid`, `korte_naam`). This is the "hybrid registry" the s5 wireframe names:
fixed base + per-context overrides + role-based field permissions. The migrated
representative target must reach at least this expressiveness, not a flat 4-field table.

**Membership types (vocabulary)**: `lidmaatschap` enum =
`Gewoon lid, Gezins lid, Donateur, Gezins donateur, Erelid, Overig` with **role-restricted**
values (`Erelid`/`Overig` only for CRUD/admin). **Status** enum =
`Actief, Opgezegd, wachtRegio, wachtBetaling, Aangemeld, Geschorst, HdcnAccount, Club,
Sponsor, Overig`.

**Region / subgroup scoping** (`backend/shared/auth_utils.py`): region is a first-class
concept — `determine_regional_access` maps `System_CRUD`/`System_User_Management` → all,
`Regio_All` → national, `Regio_<X>` → that region subset, none → deny-with-message
("Permission requires region assignment"). Region **values** (note: richer than the pilot's
Noord/Zuid/Oost/West): `Noord-Holland, Zuid-Holland, Friesland, Utrecht, Oost, Limburg,
Groningen/Drenthe, Brabant/Zeeland, Duitsland, Overig`.

**Membership lifecycle** (`config/workflows/membershipWorkflow.ts`, backend authority):
states `draft → applied(Aangemeld) → pending(wachtRegio) → wait_payment(wachtBetaling) →
active(Actief)`, plus `cancelled(Opgezegd)`, `suspended(Geschorst)`, `rejected(Afgewezen)`.
Transitions carry actors + required fields (APPROVE requires `regio`; REJECT/SUSPEND require
`reason`), which the migrated engine must reproduce.

**Backend member slice** (`backend/handler/`): ~18 member-related Lambda actions —
`create_member, get_member_byid, get_member_self, get_members, get_members_filtered,
update_member, delete_member, export_members`; membership `create/get_byid/get/update/
delete/transition_member/bulk_transition_members`; `manage_delegates,
send_delegate_invitation`; `get_member_payments` (+ shared payments admin handlers). Data
model today: `MembersTable`, `CountersTable`, `PaymentsTable`; no `tenant_id` partitioning.

---

## B. Three-channel fact propagation — the core platform guarantee

For each of the three facts: source → channel → module-read, with PROVEN vs
BYPASSED/UNPROVEN in (i) dev/test and (ii) prod. This is the crux of why s5b is not
representative.

### B.1 Capability ("may act on Members")
- **Intended (ADR 0006 / steering 20 / s5 R6.1):** source = MySQL `user_tenant_roles` ∩
  `tenant_modules`; channel = PreTokenGen Lambda stamps `custom:entitlements`; read by
  `has_capability` in `sam/shared`.
- **Built:** the pieces exist. `sam/pretokengen/handler.py` is a correct V2 PreTokenGen
  Lambda reading the projection (not MySQL), fail-safe/fail-fast; the module edge
  (`sam/members/handler/app.py`) calls three-state `has_capability` and denies on `None`.
- **(i) dev/test — BYPASSED (confirmed).** No pool used by the module has the PreTokenGen
  trigger attached: steering `23-aws-accounts.md` states Pool A and the test pool both have
  **empty `LambdaConfig`** ("no Pre-Token-Generation trigger"). Local tokens carry
  `cognito:groups` but no `custom:entitlements`, so `has_capability` → `None`. s5b added
  `MEMBERS_LOCAL_AUTH_FALLBACK=true` (`sam/members/env-vars.local.json`) which, per
  `_local_dev_group_grants_capability` in `app.py`, derives the capability from any
  `Members_*` group — i.e. **capability is faked via `cognito:groups`**, the exact
  anti-pattern S2/S4 forbid. The s5b Session notes admit this explicitly.
- **(ii) prod — UNPROVEN.** The live Pool A PreTokenGen trigger is S5 Step 7 / s5b Phase 8,
  both `not_started`. `env-vars.local.json` sets the flags but `template.yaml` defaults them
  empty, so prod would deny (correct) — meaning the capability channel has **never been
  exercised end-to-end** anywhere.

### B.2 Scope grant ("which subgroup")
- **Intended (s5 scope-dimension-design + s5b design C5):** source = MySQL
  `user_tenant_roles` (`Regio_All`/`Regio_<value>`) + parameter dimension values; channel =
  projection row `scopegrant#<email>#<dimension>`; read by module's `resolve_scope_access`
  via the projection reader → `_resolve_scope_access` in `app.py`.
- **Built:** genuinely present. `projection_schema.py` registers `RECORD_TYPE_SCOPEGRANT`;
  `projection_sync.py` builds `scopegrant#<email>#<dimension>` by decoding `user_tenant_roles`
  against the authored `members.scope_dimensions`; the module reads projected grant *values*
  (not role names) and routes them through the domain `resolve_scope_access` (deny-by-default
  when a `required_for` capability has no grant). This is the one channel that is close to
  correct by construction.
- **(i) dev/test — PARTIALLY PROVEN but via CLI, not governance UI.** The grant was created
  by `onboard-hdcn-local.py step2_role`, which **INSERTs `Regio_All` into `user_tenant_roles`
  directly** and then calls `ProjectionSync.sync_administration("h-dcn")` in-process — not via
  the Tenant-Admin `POST /api/tenant-admin/users/{user}/groups` endpoint and its
  `enqueue_sync` trigger. So the *channel shape* (MySQL → `scopegrant#` → reader) is
  exercised, but **not driven by a real governance write through the SPA** (the s5b `[H]`
  Tenant-Admin tasks 11.2 remained prod-only/unrun for local). The on-change trigger
  (`enqueue_sync` after `user_tenant_roles` writes) is coded (task 6.2); its firing from the
  actual SysAdmin/Tenant-Admin endpoints was later **VERIFIED (see F.8)** — it fires at every
  governance endpoint. So the channel is sound; s5c must simply DRIVE it through the SPA rather
  than via the CLI.
- **(ii) prod — UNPROVEN.** Prod projection is empty until s5c registers/authors real data
  (Phase 8 not_started).

### B.3 Tenant config (scope dimension values + field overlay / user-defined fields)
- **Intended (s5b design C2):** source = MySQL parameters `members.scope_dimensions` /
  `members.field_overlay`; channel = projection `config#scope` / `config#fields`; read by the
  module `MembersProjectionReader` feeding `ScopeConfigProvider` + `TenantOverlayProvider`.
- **Built (read side):** solid. `projection_schema.py` registers `RECORD_TYPE_CONFIG`
  (`config#scope`, `config#fields`); `projection_sync.py` builds both rows from
  `ParameterService.get_param("members", ...)`, empty-is-valid; the module reader wires them
  behind the S5 provider seams (`app.py` swaps `Static*` providers for the projection reader).
- **AUTHORING UI — BROKEN / UNREACHABLE (confirmed root cause of the reported blocker).**
  The Tenant-Admin parameter UI is **schema-driven**: `parameter_schema.py`'s
  `get_schema_for_tenant(tenant_modules)` returns only namespaces present in
  `PARAMETER_SCHEMA` (and gated by their `module`). `PARAMETER_SCHEMA` today contains
  `storage`, `str_branding`, `zzp_branding`, `fin`, `str` — **there is no `members`
  namespace and no `members.scope_dimensions`/`members.field_overlay` definitions at all**
  (grep for `members` in `parameter_*.py` → no matches). `projection_sync.py`'s own comments
  concede this: *"The `members.*` namespace declaration/gating to the active MEMBERS module is
  a later `[H]` task (11.x, `parameter_schema.py`)"* — that task was never done. Consequently
  the SPA's schema-driven parameter authoring surface **has nothing to render for members**,
  even with the module active — which is exactly the user's report that user-defined fields /
  the parameter authoring UI are not reachable in myAdmin. The only way the values got set was
  `onboard-hdcn-local.py step1_params`, which calls `ParameterService.set_param(scope="tenant",
  "members", "scope_dimensions"/"field_overlay", ...)` **directly, bypassing the schema/UI**.
- **(i) dev/test:** config channel PROVEN at the data level (CLI-authored → projected →
  module reads), but the **authoring path is UNPROVEN** (no UI). **(ii) prod:** UNPROVEN.

**Net:** of the three channels, only **scope-grant** and **tenant-config** are structurally
built and exercised at the data level (both via CLI, not the SPA); **capability** is faked in
dev and unproven in prod; and the **config authoring UI does not exist**. So s5b did not prove
the platform's central guarantee — it demonstrated a page rendering over hand-seeded data.

---

## C. What was actually built (has-been) + how, and every deviation vs steering

**SAM Members module (`sam/members/`)** — substantial and well-layered per steering 35:
- `handler/routes.py` — a clean **24-route** union (member CRUD 8, membership lifecycle 7,
  delegates 2, member payments 1, + new Lidmaatschap Beheer catalog 6), import-time
  consistency checks. Best-practice consolidation of h-dcn's 18 handlers. **KEEP.**
- `handler/app.py` — thin verified-auth edge (`get_verified_claims`/`has_capability`),
  tenant-from-verified-entitlement, scope seam. **Contains the two local-dev fallbacks**
  (`_local_dev_group_grants_capability`, tenant fallback), flag-gated, prod-empty. Deviation
  to unwind.
- `handler/router.py`; `domain/` (`fixed_fields.py`, `field_resolver.py`,
  `membership_service.py`, `membership_type_catalog.py`, `lifecycle_config.py`,
  `scope_access.py`, `scope_dimensions.py`, `tenant_hooks.py`, `transition_hooks.py`);
  `repository/` (`members_repository.py`, `projection_config_reader.py`, `table_design.py`);
  `migration/` (`hdcn_backfill.py`, `hdcn_catalog_seed.py`); `tenants/hdcn/hooks.py`
  (only place h-dcn logic lives — 2 of 5 hooks). Generic core, no tenant conditionals.
- **Thin data model:** `fixed_fields.py` fixes only `personal.{name,contact,address,
  birthdate}` + `membership.{member_number,status,membership_type,joined,left}` and a
  6-value status enum (`application/pending/active/suspended/lapsed/left`). This is a
  deliberate generic base, but **far thinner than h-dcn's real field set** (Section A) and,
  as shipped for the pilot, the h-dcn overlay is essentially just `motor_type` (per the CLI
  seed) — hence the "4 members, few fixed fields" symptom.

**Members frontend** (`frontend/src/pages/MembersPage.tsx` + `components/members/*` +
`membersApiService.ts` + `types/members.ts` + `useMemberFieldConfig.ts`): a real Leden
Overzicht page composing the shared toolkit (Chakra table, `FilterableHeader`,
`useFilterableTable`, compact/full view from field config, region Badge, CSV export) with
view/edit/delete/add/transition/bulk-transition modals. `membersApiService.ts` unwraps the
`{data:[...]}` envelope and flattens nested records. Solid work, but drives a thin model and
was validated against faked auth. **KEEP as the frontend base; broaden to representative.**

**Projection + identity plumbing** (`backend/src/services/`): `projection_schema.py` (record
types + `build_sort_key`), `projection_builder.py`, `projection_sync.py` (C2 rows +
one-directional), `projection_sync_trigger.py` (`enqueue_sync`); `sam/pretokengen/`
(handler + `projection_governance_reader.py`) — the PreTokenGen Lambda, **built but not wired
to any pool**. `module_registry.py` has a correct `MEMBERS` entry (backing `sam`,
`api_base_env: MEMBERS_MODULE_API_BASE`, `data_namespace: members`,
`required_roles: [Members_CRUD, Members_Read, Members_Export]`).

**Deviations vs steering (each confirmed in code):**
1. **Capability faked via `cognito:groups`** — `MEMBERS_LOCAL_AUTH_FALLBACK` +
   `_local_dev_group_grants_capability` (`app.py`, `env-vars.local.json`). Violates
   steering 21 (`cognito:groups` = GLOBAL roles only; per-tenant capability never on the
   token) and ADR 0006 (capability travels via `custom:entitlements`).
2. **Local tenant fallback** — `MEMBERS_LOCAL_TENANT_ID=h-dcn` substitutes a tenant when the
   verified entitlement resolves none. A hardcoded-tenant fallback, contrary to
   verify-before-trust / "no `h-dcn` default" (the edge's own docstring forbids it in the
   real path).
3. **Off-model `Members_CRUD` group on prod Pool A** — s5b Session notes: `Members_CRUD` was
   added to `webmaster@h-dcn.nl` in `eu-west-1_Hdp40eWmu` (prod, account 344561557829) to make
   the page work. Per-tenant `Members_*` roles must live in MySQL `user_tenant_roles`, never as
   Cognito groups (steering 21). Reversible, but pollutes prod identity.
4. **Local dev coupled to PROD Pool A** — `env-vars.local.json` `HDCN_COGNITO_ISSUER` =
   `eu-west-1_Hdp40eWmu`. Violates the roadmap/steering test-first rule ("validate on the test
   pool, never prod-first"); the standing test pool `eu-west-1_xyrlzfqbl` exists for this.
5. **CLI-only onboarding** — `onboard-hdcn-local.py` writes `user_tenant_roles` and
   `members.*` params directly and runs the sync in-process, bypassing the SysAdmin/
   Tenant-Admin SPA endpoints that are the intended production governance path (s5b tasks
   10/11 remained unrun for local).
6. **Missing `members.*` parameter schema** — no `members` namespace in `parameter_schema.py`,
   so the schema-driven authoring UI is unreachable (Section B.3). The projection builder and
   CLI depend on parameter values that no UI can create.
7. **Thin table / model** — 4 seeded members, ~9 fixed fields, overlay ≈ `motor_type` only;
   not representative of the h-dcn surface in Section A.

---

## D. Verdict table — Add / Refactor / Remove / Keep (per component)

| Component | Verdict | One-line reason (grounded in A–C) |
| --- | --- | --- |
| `sam/members/domain/*` (service, scope, lifecycle, hooks, catalog) | **KEEP** | Generic, layered, tenant-agnostic, heavily tested (S5 "612 tests"); the sound core (C). |
| `sam/members/domain/fixed_fields.py` (base registry) | **REFACTOR** | Too thin vs representative h-dcn (A); broaden fixed base or push more into a real overlay. |
| `sam/members/repository/*` (members_repo, table_design, projection_config_reader) | **KEEP** | `tenant_id`+`LeadingKeys` isolation and the projection reader are correct per steering 35. |
| `sam/members/handler/routes.py` + `router.py` | **KEEP** | 24-route consolidation is the best-practice shape S5 intended (C). |
| `sam/members/handler/app.py` verified-auth edge | **KEEP (core)** | Thin adapter, three-state `has_capability`, projected-grant scope seam — the right edge. |
| `_local_dev_group_grants_capability` + `MEMBERS_LOCAL_AUTH_FALLBACK` | **REMOVE** | Fakes capability from `cognito:groups`; the bypass s5c must eliminate by wiring PreTokenGen (B.1). |
| `MEMBERS_LOCAL_TENANT_ID` tenant fallback | **REMOVE** | Hardcoded-tenant fallback violates verify-before-trust; unneeded once tokens carry entitlement. |
| Prod Pool A `Members_CRUD` group on webmaster@h-dcn.nl | **REMOVED (done 2026-09-19)** | Off-model per-tenant role; belonged in MySQL `user_tenant_roles` (steering 21). Already removed; Pool A restored to pre-session state. |
| `projection_schema.py` (record types) | **KEEP** | `config#*` / `scopegrant#*` / `module`/`role` types are correct and the sole SK composer. |
| `projection_sync.py` + `projection_builder.py` (C2 builders) | **KEEP** | One-directional MySQL→DynamoDB builders for scope/fields/grants work; reads only. |
| `projection_sync_trigger.py` (`enqueue_sync`) | **KEEP** | Fires at every governance endpoint — code-confirmed (F.8). Only open item: confirm the periodic reconcile backstop is scheduled per env. |
| `sam/pretokengen/*` (PreTokenGen Lambda + reader) | **KEEP + WIRE** | Correct Lambda, but attached to **no pool**; s5c must wire it to a dev/test pool then prod (B.1). |
| `parameter_schema.py` — `members` namespace | **ADD** | Absent today → authoring UI unreachable; must declare `members.scope_dimensions`/`field_overlay` (B.3). |
| Tenant-Admin parameter/field-config authoring UI (members) | **ADD/REFACTOR** | Schema-driven UI renders nothing for members until the schema exists; make user-defined fields authorable in the SPA. |
| Members frontend page + modals | **KEEP + REFACTOR** | Real page/modals; broaden to representative columns/contexts/filters/self-service (A). |
| `frontend/src/hooks/useMemberFieldConfig.ts` | **KEEP** | Field-config hook is the right seam for a richer overlay-driven UI. |
| `scripts/local/onboard-hdcn-local.py` | **REFACTOR (demote to test fixture)** | Useful local seeder, but must not substitute for SPA onboarding; drive real onboarding through SysAdmin/Tenant-Admin. |
| Dev/test Cognito pool for the module | **ADD** | Decouple local dev from prod Pool A; use/extend `eu-west-1_xyrlzfqbl` with a PreTokenGen trigger. |
| `module_registry.py` `MEMBERS` entry | **KEEP** | Correct sam-backed registration; no change needed. |

---

## E. Disposition of the s5 and s5b specs

- **s5 (`s5-members-first-migration`) → KEEP (as the domain reference of record).** It is the
  parent domain build: requirements, `generic-membership-design.md`,
  `scope-dimension-design.md`, `members-wireframe.md`, `go-no-go.md`. Its model held (2-of-5
  hooks, zero Rung-4). s5c should **reuse** it and not re-derive the generic membership model.
  One caveat: its `go-no-go.md` records a **Conditional-Go** whose two conditions (live UX
  walkthrough; live Pool A trigger) were **never satisfied** — s5c should treat the pilot as
  *not yet passed*, not as a Go.
- **s5b (`s5b-members-runnable-in-spa`) → MARK SUPERSEDED by s5c** (do not delete; do not treat
  as done). Keep as history + source of reusable artifacts.
  - **Real / keepable artifacts (already-done work s5c reuses):** the SAM app packaging
    (`sam/members/template.yaml` + layer Makefile fix), the projection C2 record types +
    builders + sync trigger, the module projection reader wiring, the frontend
    service/types/page/modals, and the MkDocs members manual (task 23).
  - **Flawed shortcuts to unwind (do NOT carry into s5c):** the two local auth/tenant
    fallback flags, the prod-Pool-A coupling in `env-vars.local.json`, the prod `Members_CRUD`
    Cognito group, and reliance on the CLI as the onboarding path. Its Phase-3/Phase-8 `[H]`
    tasks (real SysAdmin/Tenant-Admin onboarding, prod deploy, live trigger) are `not_started`
    and are precisely what s5c must actually do.
- **What s5c should OWN vs REUSE:**
  - **OWN:** (1) real capability propagation — stand up/extend a **non-prod dev/test pool**
    with the PreTokenGen trigger and prove `custom:entitlements` end-to-end; (2) the
    `members.*` **parameter schema + authoring UI** so scope dimensions and user-defined
    (overlay) fields are authorable in the SPA; (3) real **SPA onboarding** of h-dcn via
    SysAdmin (tenant + `MEMBERS` entitlement + role defs) and Tenant-Admin (users + role
    assignment + params), with `enqueue_sync` firing on those writes; (4) a **representative**
    member surface (fields/contexts/filters/self-service) matching Section A; (5) removal of
    the local fallbacks and prod-pool coupling; (6) after a successful dev/test run, an
    **actual gated deployment to PROD** — deploy the Members SAM app + wire the live Pool A
    PreTokenGen trigger + onboard h-dcn through the prod SPA + project + verify scoped/general
    users in prod — **to PROVE the full CI/CD path works end-to-end** (build → deploy →
    provision → project → verify), with a reversible governance rollback. The prod cutover is
    a first-class s5c deliverable, not a deferred phase; it is the ultimate proof the three
    channels propagate in production, gated + test-pool-first + detach-to-rollback per steering 23.
  - **REUSE:** the entire s5 domain (routes/service/repository/hooks), the s5b projection
    plumbing (schema/builders/sync/reader) and the s5b frontend page/modals, and the
    PreTokenGen Lambda code.

---

## F. Open questions / risks for the requirements author

1. **Dev/test pool standup.** The standing test pool `eu-west-1_xyrlzfqbl` currently has **no
   PreTokenGen trigger** (steering 23). Who creates the trigger there, and does the module's
   `HDCN_COGNITO_ISSUER`/JWKS get repointed from prod Pool A to the test pool for local + CI?
   (This decouples dev from prod — the "test-pool hygiene switch" the s5b notes flag.)

   **RESOLVED (owner: s5c).** Repoint the module's Cognito config from prod Pool A to the
   standing test pool `myAdmin-test` for local + CI: set `HDCN_COGNITO_ISSUER` =
   `https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl`, the matching
   `HDCN_COGNITO_JWKS_URI` (`.../eu-west-1_xyrlzfqbl/.well-known/jwks.json`), and
   `HDCN_COGNITO_CLIENT_ID` = `43s15cm8qcgg8an85udt0e087u` (`myAdmin-test-client`). This is
   config-not-code: the issuer→pool registry (`auth/pool_registry.py`) selects the pool by
   `iss`, so repointing the env vars is the whole change; local/CI then log in as throwaway
   test users in `myAdmin-test`, never a prod user (which is also why the prod-Pool-A
   `Members_CRUD` hack was never the right lever).

   The trigger is created on the **test pool FIRST** (test-pool-first rule). Per steering 23 /
   ADR 0006 the S4 PreTokenGen Lambda lives in the **data account** (506221081911, reads the
   projection same-account) and the **pool attaches the trigger** from the **identity account**
   (344561557829) — a cross-account invoke; since `myAdmin-test` is also in the identity
   account, the same cross-account invoke pattern applies. s5c owns: wire the cross-account
   invoke permission from `myAdmin-test` to the data-account Lambda, seed a test user whose
   projected entitlement is non-empty, and prove `custom:entitlements` appears in the
   test-pool token and the module authorizes off it with **zero** reliance on `cognito:groups`.
   Only after that passes is the **live Pool A trigger** attached — the gated, highest-blast-
   radius prod step (S5 Step 7 / s5c's prod CI/CD deliverable), detach-to-rollback.

   **Deliberate divergence from the steering note:** the note says the test pool *mirrors*
   Pool A and Pool A has empty `LambdaConfig`, "so there is nothing to mirror." s5c
   intentionally goes BEYOND a pure mirror by ADDING a PreTokenGen trigger to `myAdmin-test`,
   precisely to prove the capability channel Pool A does not yet exercise — prove on test,
   then promote to Pool A. **Dependency:** requires the projection to actually carry h-dcn's
   token-relevant governance for the test user (see F.3 — projection widening, currently
   UNVERIFIED); without that the test-pool token's entitlement would be empty.
2. **PreTokenGen entitlement channel — GENERIC platform prerequisite (RESOLVED).**
   **Position:** the PreTokenGen entitlement channel is **generic platform infrastructure**, not
   a Members feature. Its **scope is platform-wide** (it serves every SAM-backed module — Members,
   Events, Webshop, and any future one); the **need** simply surfaces in the **first SAM app that
   requires it**, which is Members (s5c). So s5c is the *forcing function/first consumer*, NOT the
   owner of the mechanism, and Members adds **zero value to the mechanism itself** — it only proves
   and consumes it. Members' actual added value is its own domain, the `members.*` parameter
   schema + authoring UI, and the representative Leden Overzicht surface.

   **Requirement (not conditional, not optional):** the channel **MUST be implemented and tested
   in dev/test as a prerequisite generic-infra feature, and — after dev/test passes — implemented
   in prod** as a normal step of the dev→prod promotion. This supersedes S5's framing of the live
   trigger as a *conditional* post-gate Step 7: because s5c's explicit purpose is to prove the
   capability channel is real end-to-end, the trigger is a required part of the promotion in BOTH
   environments (prove it in dev, then promote to prod), never a fake (`cognito:groups`) or a
   skip.

   **What already exists vs what must be switched on.** The mechanism is built + tested in S4
   (the PreTokenGen Lambda, the one shared resolver `roles ∩ active modules → capabilities`, the
   `custom:entitlements` codec, both-plane readers). The wiring is **specified** in S4 `design.md`
   D2: the Lambda runs in the **data account (506221081911)** next to `governance_projection`
   (read is **same-account**); a pool **attaches the trigger cross-account** via an
   `aws_lambda_permission` (the *invoke* crosses accounts, the *data read* does not). So what s5c
   switches on, as generic platform work, is: (i) **widen the projection** so it carries the
   token-relevant governance for the pool's tenants (see F.3 — the hard prerequisite in BOTH
   environments; without it the claim is empty); (ii) **attach the trigger to the dev/test pool**
   `myAdmin-test` and prove `custom:entitlements` end-to-end there with zero `cognito:groups`
   reliance; then (iii) **attach the trigger to prod Pool A** as the gated promotion step.

   **Safety (why this is a controlled, not scary, step):** the Lambda is **fail-safe** (a
   resolution failure OMITS the claim; login still succeeds; the Flask plane stays authoritative),
   and the trigger is **detach-to-rollback** (removing it instantly restores prior login). It is
   the highest-blast-radius *action* only because it touches prod login when it reaches Pool A —
   hence test-pool-first + gated + detach-to-rollback (S4 R6.2). Open sub-item: confirm the exact
   IAM implementation of T18 (Lambda deploy to data account + cross-account invoke permission +
   trigger attach); the *design* is settled, only the physical wiring remains.

3. **Scope machinery is a generic MEMBERS-MODULE feature; "projection widening" is NOT a blocker for s5c (RESOLVED).**
   **Framing correction:** "SAM-backed" is a property of the **module** (Members), not of a
   tenant. The scope machinery — scope dimensions, `config#scope`, per-user `scopegrant#` — is a
   **Members-module feature**, tenant-agnostic and parameter-driven. A tenant **enables** Members
   via `tenant_modules` and may use scope or not; **h-dcn is simply the first tenant that enabled
   Members and configured region scope** (its own requirement), NOT a special "SAM tenant."

   **Verified in code (why it is not a blocker):** capability resolution is **backing-agnostic** —
   `backend/src/auth/entitlement_resolver.py` computes `roles ∩ active_modules → capabilities` and
   its docstring states it "NEVER inspects a module's optional `backing` block; a `sam` module
   resolves exactly like a `flask` one." The projection sync
   (`projection_sync.py::sync_administration` → `build_projection_items`) projects a tenant's
   `tenant`/`module#…`/`role#…` rows **plus** the Members C2 rows (`config#scope`, `config#fields`,
   `scopegrant#<email>#<dimension>`) **whenever that tenant has a SAM-backed module ENABLED** —
   i.e. the gate is *module-enabled-for-the-tenant*, not "is this a SAM tenant." So for **any
   tenant that has Members enabled** (h-dcn is the example), the PreTokenGen Lambda reads a
   partition that already carries `module#MEMBERS` (active) + `role#…#Members_CRUD` and produces a
   **non-empty `custom:entitlements`** once the trigger is wired. Confirmed: h-dcn's partition
   already held exactly these rows.

   **What the ADR 0006 "widening" caveat actually concerns:** the *different* case of a Pool A
   tenant with **NO SAM-backed module at all** (e.g. a finance-only tenant) — such a tenant projects
   nothing, so its token entitlement stays empty. That is **irrelevant to Members / s5c** and out of
   scope; s5c operates on a tenant that has Members enabled.

   **How the requested scope behaviour maps to the three channels (all built; parameter-driven):**
   - **Capability** — `Members_CRUD` / `Members_Read` ("may act on Members at all") → projected
     `module#MEMBERS` + `role#…` → the backing-agnostic resolver → `custom:entitlements` on the
     token (needs the trigger, F.2).
   - **Scope grant** — `*` (all) or a subset like `["Noord"]` → projected `scopegrant#<email>#region`
     (decoded from the user's `Regio_All` / `Regio_<value>` role in `user_tenant_roles`) → read by
     `resolve_scope_access`; a `Members_CRUD` user scoped to `Noord` sees/acts on ONLY members whose
     `region ∈ {Noord}` (deny-by-default when a `required_for` capability has no grant). This is
     exactly the requested behaviour, already built.
   - **Allowed scope VALUES (the dropdown list)** — the `region` dimension's `values`
     (Noord/Zuid/…) live in the `config#scope` row, sourced from the `members.scope_dimensions`
     **parameter** — i.e. "the fields allowed in scope are parameter-driven," as required. This is
     the ONE genuinely-missing piece: the `members.*` parameter schema + authoring UI does not
     exist yet (see F.4), so today those values can only be set by the CLI, not the SPA.

   **Net:** F.3 is verified as **NOT a blocker** for s5c — the scope feature is generic, parameter-driven, and already projected for any Members-enabled tenant; the real remaining work is
   the `members.*` authoring UI (F.4), not projection widening.

4. **How user-defined fields are authored and surfaced.** Decide the `members.*` parameter
   schema shape for `scope_dimensions` and `field_overlay` (they are `json` params today),
   whether the Tenant-Admin UI edits raw JSON or gets a structured field-builder, and how the
   overlay maps to the module `TenantOverlay` (fields + fixed-field overrides). This is the
   direct fix for the reported "user-defined fields not reachable" blocker.

   **RESOLVED (direction):** REUSE the existing **ledger-account definition-driven typed-editor**
   pattern (`backend/src/config/ledger_parameters.json` + `GET /api/config/ledger-parameters` +
   `AccountModal.tsx`, incl. the `string[]`+`options` multi-select + `depends_on` + `module` gate)
   for `members.*` — extended as far as Members needs (a **list of scope-dimension objects**, and a
   **map of field-overlay definitions**). This gives a structured, bilingual, no-raw-JSON authoring
   UI and feeds the already-built `config#scope`/`config#fields` projection unchanged. Do NOT build
   a bespoke field-builder from scratch, and do NOT rely on the raw-JSON `ParameterManagement`
   editor as the authoring path. A **generic** definition-driven config-editor framework (unifying
   `PARAMETER_SCHEMA` + `ParameterManagement` + the ledger editor) is captured as a separate
   platform backlog item — `.kiro/specs/myBacklog/json-editor.md` — to be extracted AFTER Members
   is its 2nd real consumer; it must NOT block s5c.

   **Write-granularity + draft-state (RESOLVED — s5c design rules).** How the projection is
   invoked is a **documented myAdmin standard**, not user-visible plumbing: a committed governance/
   parameter write calls `enqueue_sync(administration)` after commit (F.8); the default in-process
   trigger drains **synchronously**, re-projecting that ONE tenant, idempotent + conditional-write
   (F.8), backstopped by the periodic `reconcile()`. There is **no user-facing "propagate now"**
   button, and none is needed for the pilot (propagation is an automatic consequence of Save).
   Rules for s5c authoring:
   - **Save the whole config object per logical edit — NEVER push per field/keystroke.**
     `members.scope_dimensions` (the dimension LIST) and `members.field_overlay` (the field MAP)
     stay **single JSON parameters**; the typed editor edits them in-form and commits once → one
     PUT → one `enqueue_sync` → one per-tenant re-projection. (Per-field saves would fire N syncs
     and, because the default trigger drains synchronously, make each save sluggish; idempotency
     keeps it correct but it is wasteful — avoid.)
   - **No draft/resume in the pilot.** The parameter model has no draft concept: unsaved edits
     live only in form state (lost on interruption), and a Save immediately projects. So an
     interrupted edit either loses unsaved work OR, if partially saved, propagates a partial
     definition live (empty-is-valid → no crash, just a half-authored live state). For s5c use
     **save-once + an unsaved-changes guard** (warn on navigate-away); acceptable because h-dcn's
     config is authored once at onboarding, not tuned daily.
   - **"Edit, stop, continue next day" (draft/publish) is DEFERRED to the generic config-editor
     framework** (`json-editor.md`), NOT built in s5c: a draft copy that is not projected + an
     explicit Publish that promotes draft→live and fires the sync. This is a generic capability
     (every module's config authoring wants it), so it belongs to the framework, not Members.
   
5. **Representative fidelity target.** How close to h-dcn must s5c get (multiple table
   contexts, `showWhen`/conditional fields, role-restricted enums, computed fields,
   self-service view, welcome packs, Cognito-Beheer sub-tabs)? These drive the field/overlay
   model and the acceptance criteria; decide scope explicitly to avoid another thin result.

   **RESOLVED (scope decision).** "Representative" for s5c means a **tenant/parameter-driven**
   member surface, NOT a pixel-for-pixel port of every h-dcn screen. Headline value = the field
   model is genuinely tenant-configurable (fixed base ⊕ tenant overlay), driven by parameters
   (F.4). Scope:
   - **IN (core):** Leden Overzicht table with **parameter-driven columns** + config-driven view
     contexts; **calculated/derived fields** (e.g. `jaren_lid`, `korte_naam` — no stored data) are
     a solid explicit requirement; scope/region badge + filtering; view / edit / add / delete
     modals over the parameter-driven field set; export; single + bulk lifecycle transitions kept
     **deliberately limited** (mirror h-dcn's current limited maturity — do not over-build the
     state machine).
   - **OUT (explicitly excluded):** **Cognito-Beheer** — belongs to myAdmin's platform admin
     (SysAdmin/Tenant-Admin), not the Members module; do not port it. **Welkomstpakketten** —
     empty in h-dcn; ignore.
   - **ENABLED-BUT-NOT-BUILT (follow-up; s5c must impose NO blocking factors):**
     - **Reporting** — crucial, and it **must live in the Members SAM module**, LEVERAGING
       myAdmin's existing reporting toolkit (graphs, violins, pivots, AI commands) rather than
       rebuilding it. NOT built in s5c, but s5c's data model + module boundaries must leave it
       cleanly addable later (open design sub-item: how member DynamoDB data reaches the reporting
       tooling — do not architect it out).
     - **Member onboarding / offboarding workflows** — still a gap even in the h-dcn app, so NOT a
       porting target and NOT built in s5c; must remain possible to add later (basic add + a
       lifecycle status change already exist; the full workflows are future). No blocking factors.
   - **Region values (F.6):** the scope-dimension value list is **tenant PARAMETER data**
     (authored via F.4), NOT hardcoded by s5c. The values only *look* like provinces; they are an
     arbitrary tenant-defined list. Any **seeding defaults** the platform ships should use
     **generic placeholder names** (e.g. Region A / Region B …), never h-dcn's real list —
     baking a tenant's specifics into platform seed data contradicts the parameter-driven
     principle. h-dcn authors its own list as data at onboarding.
6. **Region value set (RESOLVED).** The scope-dimension values are **tenant parameter data**,
   not a platform constant. They resemble provinces but are only partly so — an arbitrary
   tenant-defined list authored via the parameter authoring UI (F.4). Platform **seeding
   defaults use generic placeholder names** (e.g. Region A / Region B), never h-dcn's real list;
   h-dcn authors its actual values as data at onboarding. (Supersedes the earlier note about
   aligning to a fixed 10-value provincial list.)
7. **Prod landing + operational provisioning + rollback (RESOLVED — becomes s5c tasks).**
   Prod deployment is IN scope (a first-class s5c deliverable — prove CI/CD end-to-end) and is
   **human-run, gated, dev/test-first** per steering 23. Beyond "deploy the SAM app," the real
   work is an **operational provisioning playbook** run in dev/test first, then identically in
   prod, with a hard separation of two tracks:
   - **Governance track (authored through the SPA, PROVEN — never scripted around):** tenant +
     `MEMBERS` entitlement + role definitions (SysAdmin), users' role assignments + tenant
     parameters (Tenant-Admin) → MySQL → `enqueue_sync` → projection. Role assignments MUST flow
     through the real endpoints (a script may DRIVE an endpoint but not write MySQL directly), so
     the `enqueue_sync`→projection loop is genuinely exercised (see F.8).
   - **Data/migration track (scripts OK — idempotent + dry-run + verify):** bulk member import
     (e.g. Google-Sheet → `sam-members` DynamoDB; h-dcn `migrationHDCNLedenbestand` is prior art),
     membership-type catalog seed, and a **bulk Cognito user load** (create users in the
     dev/test pool for dev, Pool A for prod). The user list can be **derived from the existing
     h-dcn Cognito pool into an editable file** (~10×2 + 3 users) carrying each user's CRUD/Read
     capability + scope, then loaded (Cognito users via script; their role assignments via the
     governance endpoint per above).
   Prereqs surfaced here that become explicit **s5c tasks** (NOT to be done in this analysis):
   - **Fixed-vs-tenant field split (s5c task):** classify the member field set into **Fixed**
     (universal, JSON-in-code base registry `fixed_fields.py`), **Parameter** (tenant-driven
     overlay, seeded in `members.*` params via the F.4 authoring), and **Calculated** (derived,
     no stored data). The concrete per-field classification table for the h-dcn seed is a spec
     deliverable authored in s5c (new tenants get this via a later onboarding concern). Note the
     sub-rule: a field may be Fixed while its **enum values** are Parameter (tenant config).
   - **Scripts as deliverables (s5c tasks):** the gsheet→DynamoDB importer, the catalog seed, and
     the Cognito-user loader — each idempotent, dry-runnable, with a verify summary, run
     dev/test-first then prod.
   **Prod path (design detail for s5c):** deploy `sam-members`; `governance_projection` +
   `sam-members` are managed-outside-CFN / retain (steering 23 constraint, not a choice); author
   h-dcn via the SPA; run sync; set `MEMBERS_MODULE_API_BASE` (confirm whether needed under the
   direct-to-module-API path, D1 option a); verify scoped + general users in prod.
   **Rollback (non-destructive, governance-based):** detach the PreTokenGen trigger; remove the
   `MEMBERS` entitlement / scope-role assignments; re-project — NO table drops, NO data deletion.
   Parallel-run safety: s5 uses NEW tables so the live h-dcn is untouched throughout.
   **Note:** the off-model prod `Members_CRUD` Cognito group was **already removed 2026-09-19**
   (Pool A restored to pre-session state) — no longer pending work.
8. **Onboarding actor split + enqueue_sync wiring (RESOLVED — documented standard, already
   implemented).** This is a **documented myAdmin standard**, not an open question:
   - **Documented where:** steering `20-platform-architecture.md` (one-directional projection:
     "on-change sync triggers + a periodic reconciliation backstop"); the
     `backend/src/services/projection_sync_trigger.py` docstring states the contract verbatim —
     *"a governance write that mutates `tenants` / `tenant_modules` / `user_tenant_roles` calls
     `enqueue_sync` with the affected `administration`"*, best-effort + reconciliation-backstop;
     steering `30-backend-api-flask-mysql.md` documents the SysAdmin route grouping +
     `@tenant_required(allow_sysadmin=True)`.
   - **Verified implemented at every relevant endpoint (code-confirmed):**
     - **module entitlement** (SysAdmin) — `sysadmin_tenants.py` + `services/module_registry.py`
       call `enqueue_sync(administration)` after activation → the **capability** path.
     - **role assignment / removal** (Tenant-Admin) — `routes/tenant_admin_roles.py` calls
       `enqueue_sync(tenant)` on both assign and remove → the **scope-grant** path.
     - **tenant parameters** (Tenant-Admin) — `routes/parameter_admin_routes.py` calls
       `enqueue_sync(scope_id)` on tenant-scope param create/update/delete → the
       **`config#scope`/`config#fields`** path.
     - **tenant provisioning** — `services/tenant_provisioning_service.py` calls
       `enqueue_sync(administration)`.
   So the real SPA endpoints DO fire the sync at exactly the three write paths s5c needs; the CLI
   was a shortcut, not a missing capability. **s5c's job is to EXERCISE this end-to-end** (author
   via SysAdmin/Tenant-Admin in the SPA, observe the projection update) — NOT to build it.
   - **One thing to confirm (operational, not code):** the trigger is **best-effort** (a failure
     is logged, left to the reconciliation backstop) and the default in-process trigger drains
     synchronously; s5c should confirm the **reconciliation backstop is actually scheduled/runnable**
     in dev/test and prod. The on-change path is proven; the backstop's operational scheduling is
     the only open sub-item.

---

*This is READ-ONLY analysis. No code or spec files were modified in producing it; the only
file written is this `analysis.md`.*
