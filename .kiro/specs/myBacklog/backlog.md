
# Time tracking

- Quick add part
  -- Missing product or NOT
  -- What about more people able to track time
  -- What about access to the time tracking app as a stand alone app (cognito/jwt impact)
  -- What is the added value
  -- How can we easy filter a period for submitting (day, week, month or year)


# STR Import Guesty

https://app.guesty.com/reservations?viewId=6a72237ce377681f84e3746c
Add website data loading from guesty
Strip fee is not in Guesty and can be found in stripe link reservation code

What is this : https://report.guesty.com/apps/reservations?apiKey=89b048a6196d1b5fbcbc40f8cb6b75924419bce37cd1efa83af5d4c6b230e089ddb4caaaad87ab85a5444543e00bcd0c80e18d3bb037d66aca1a1f7513fea2ff

## prompt:
Checkin is between 2 months ago and 1 year into the future for Platform Manual


# FIN Recalculation of balance sheet for validation
Out of scope: Full recalculation mode (reading all years while excluding OpeningBalance records) is a separate audit/verification feature to be wired into tenant administration as its own deliverable. See future spec: balance-verification-audit.


# ZZP Modal to manage trip presets
The database has an is_manual boolean field on each preset:

is_manual = true → user-created via the management UI
is_manual = false → auto-learned from trip history
Both show up equally on the Quick Entry screen — the user doesn't need to care how a preset was created. They just see their routes sorted by usage frequency.

Where the distinction matters:

Scenario	Manual	Auto-learned
Shown in Quick Entry	✓ (always)	✓ (top X by use_count)
User can edit	✓	✓
User can delete	✓	✓
Gets pruned if unused for 6 months	No	Yes (falls off the top X)
Created before first trip	✓ (plan ahead)	✗ (needs trips first)
So the practical value of manual presets: you can add a route you will drive (new client, new office) before you've actually driven it. Auto-learned ones only appear after you've used the route.

In the management UI, you could show a small badge ("Handmatig" / "Geleerd") to distinguish them visually, but it's purely informationa

# s3 object management module and SAM
How can we manage s3 management attributes similar as in Flask

# PITR / Backup in dynamodb
Check the current settings and what is needed


# SPEC: Member identity & number policy (member_id vs Lidnummer, numbering, sponsors/clubs)
**One spec — these three concerns are one design decision; a choice on any forces the others.**
Motivating use case: the user wants to also store NON-person entities (sponsors, clubs) in the
member table, which is what surfaces the identity/numbering questions.

## (1) `member_id` (UUID) is internal-only — stop exposing it as administration
There is confusion between `member_id` and the Lidnummer (`member_number`). `member_id` is a
technical internal identifier (row key / UUID) and should NOT appear as a normal administrative
field: not a table column, not a modal row, not something a user reads or edits. The Lidnummer
is the human-facing number. (s5j already removed the UUID row from the Members view modal as a
point fix; this spec sets the general rule + audits any other place the UUID leaks into the UI.)

## (2) Member numbering becomes a GENERIC, opt-in-by-CONFIG platform feature (not tenant code)
**DIRECTION (user, 2026-09-24): the numbering logic in members must become a GENERIC feature
that any tenant can use if they want — configured, not coded per tenant.** Today it is
mis-placed: the generation strategy is hardcoded in the generic core AND the format lives in an
h-dcn code hook. Both move: strategy + format become a GENERIC engine driven by a tenant CONFIG
value. `h-dcn` stops being special — it is just a tenant that opted into a particular config.

### Today (the mis-placement, verified — RCA s5j review)
`MembershipService.create_member` (~line 1280): when a new member has no `member_number` it
calls `self._repo.next_counter(tenant_id, MEMBER_NUMBER_COUNTER)` (atomic DynamoDB `ADD` on a
`counter#member_number` item — `repository/table_design.py`), threads the value into the
`derive_member_number` hook, and **h-dcn's `hdcn_derive_member_number` (`tenants/hdcn/hooks.py`)**
formats it (`L-000042` = prefix `L-` + zero-pad 6, both module constants). All live + tested —
NOT dead code. Problem: the counter strategy is baked into the generic path, and the format is
baked into an h-dcn-named code hook — so "numbering" carries the tenant name and needs code to
change.

### Target: config selects a registered GENERIC strategy, invoked only when required
- **Generic engine owns the strategies** (one implementation each, in the members core, tested
  once): `counter` (atomic sequence — the concurrency-safe mechanism stays in code), `max_plus_one`
  (read highest + 1; needs a uniqueness guard + retry — racy otherwise), `manual` (user enters it,
  no auto-gen), `none` (numberless). Config VALUE selects which; a tenant cannot invent arbitrary
  logic (closed set — adding a strategy is a small code change, not a config change).
- **Tenant CONFIG opts in** — a new param (working name `members.number_policy`) authored via the
  Tenant-Admin → Members editor, e.g. `{ "strategy": "counter", "prefix": "L-", "pad": 6 }`. A
  tenant that does not author one → NO numbering (no counter fetch, no auto-gen). h-dcn's L-/6/
  counter becomes this config — pure data, and **`hdcn_derive_member_number` is DELETED** (the
  `validate_member` motorcycle rule stays a hook — that one is genuinely bespoke).
- **Per member TYPE opt-in** — the number is only linked to a SUBSET of membership types (real
  members yes; sponsors/clubs/donors no). Add an `allocates_number` flag to each
  `MembershipTypeEntry` in the tenant catalog (`sam/members/domain/membership_type_catalog.py` —
  already tenant-config: `type_code`/`label`/`active`/`order`). On create the engine allocates
  only when the member's type `allocates_number` AND the record has no number yet (never renumber).
- **Empty Lidnummer is then valid by construction** — a type that does not allocate has no number;
  the write path must NOT block it. Make `member_number` OPTIONAL: skip the `membernum#<number>`
  uniqueness guard + auto-derivation when empty; enforce uniqueness ONLY when a value is present.

So the answer to "a predefined config option that invokes a piece of code when required": YES —
config value → look up the matching registered strategy → invoke it, gated by (type
`allocates_number`) AND (no existing number). This is the `derive_member_number` hook registry
made data-driven (chosen by CONFIG, not by tenant-in-code).

### Reusable implementation — TWO generics, one per plane (split by responsibility)
The two planes are separately packaged (Flask `backend/src` and SAM `sam/` cannot import each
other), so this is NOT one helper copied twice — it is the two ENDS of one config-driven feature,
following the platform's one-directional flow: **Flask authors + validates + projects → SAM reads
+ executes.**

**FLASK-plane generic — config authoring + validation + projection (`backend/src`).** Owns:
1. DEFINE the strategy as a parameter (`members.number_policy`) in `parameter_schema.py` with
   `options` enumerating the allowed strategy names (`counter`/`max_plus_one`/`manual`/`none`) —
   EXACTLY how `storage.invoice_provider` enumerates its options today.
2. AUTHOR it via the existing Tenant-Admin → Members typed editor + the per-type
   `allocates_number` flag on catalog entries.
3. VALIDATE on save (the `members_config_validation` seam) — reject an unknown strategy / bad
   format. The param `options` are the single source of allowed values.
4. PROJECT it: extend `ProjectionSync` (`backend/src/services/projection_sync.py`) to emit a
   `config#number_policy` row into `governance_projection`, riding the SAME rails as
   `config#fields` / `config#scope` / `config#views`.

**SAM-plane generic — strategy registry + execution (`sam/members`).** Owns:
1. READ the projected `config#number_policy` via the projection reader (same seam as
   overlay/scope).
2. A generic `StrategyRegistry` mapping strategy name → a registered GENERIC implementation, with
   a SAFE DEFAULT + register-time validation (generalise the `TenantHookRegistry` shape from
   `sam/members/domain/tenant_hooks.py`, keyed by a plain string instead of `(HookName,
   tenant_id)`).
3. RESOLVE + EXECUTE at create time: `resolve(policy.strategy)(...)`, gated by the type
   `allocates_number` + "no existing number." The concurrency-safe mechanism behind `counter`
   (atomic `ADD`) / `max_plus_one` (guarded read+write) stays in code here. DELETE
   `hdcn_derive_member_number` — strategies are generic + registered on this plane now.

**HOW to reuse the current Flask shared function (`storage_resolver`) — extract, don't duplicate.**
`services/storage_resolver.py::resolve_storage_provider` is a PROVEN but ONE-OFF (C) dispatch
(reads `storage.invoice_provider` via `ParameterService`, returns a handler, safe default). To
reuse it we PROMOTE its shape into a small generic Flask helper (working name
`StrategyResolver`): constructed with `(namespace, key, {option: handler}, default)`; `resolve(
tenant)` reads the param via the existing `ParameterService` scope chain and returns the handler
or the default. THEN refactor `resolve_storage_provider` to be its FIRST CONSUMER (an instance —
same behavior, its existing tests keep it honest), and the numbering Flask side uses the same
generic for declaring/validating `number_policy`. So we don't add a parallel mechanism beside
storage — we turn storage's one-off into the library and make storage its first user.
- NOTE the degenerate case: storage AUTHORS and EXECUTES in-process (it is a Flask module), so its
  `StrategyResolver` returns a live handler. For NUMBERING the Flask generic stops at
  "validate + project the chosen strategy NAME"; the SAM generic does the execution. Same pattern,
  different execution plane.

**Shared-vocabulary guard (contract with no shared code).** The Flask `options` (allowed strategy
names a tenant may author) and the SAM registry keys MUST agree. Enforce with a test that asserts
every Flask-authored strategy name resolves in the SAM registry (or a documented single source the
two transcribe from) — mirroring how `members_config_validation` keeps its field-key set honest
against the SAM `fixed_fields`.

### Open sub-decisions (design pass, don't blind-change)
- Concurrency: `counter` (no duplicates) vs `max_plus_one` (simpler, racy without a guard — a
  motor club's low concurrency may make it acceptable). Config picks per tenant.
- One flag (`allocates_number` = auto-generate AND require) vs two (allow manual entry but don't
  auto-generate). Lean: one flag first; split only if a real tenant needs the middle ground.
- Keep the `derive_member_number` hook as a rare escape hatch for a format config can't express,
  or go config-only. Lean: config-first, keep the hook as an escape hatch.
- Align with the platform's other tenant-specific mechanisms (SAM `TenantHookRegistry` /
  `HookName`; the Flask "Tenant Administration Functions") — see the note below; the aim is ONE
  pattern (config-value selects a registered generic strategy) rather than per-tenant code.

## (3) Use the member table for sponsors / clubs / non-person entities (the driver)
Storing organisations (sponsors, clubs) alongside people needs a member "kind"/type: which
fixed fields apply, how numbering behaves (usually none/optional — see (2)), and how
scope/overlay behave for a non-person. This is the broader design behind (1) and (2).

## (4) Alignment — one pattern for tenant-configurable behavior (INVESTIGATED 2026-09-24)
"hdcn" in `register_hdcn_hooks` = the tenant **h-dcn**. Goal: converge tenant-specific behavior
on ONE pattern — a CONFIG value (or per-tenant data) selects a registered GENERIC
strategy/handler, invoked when required — NOT per-tenant code branches.

### What actually exists today (read-only investigation of both planes)
Classification: (A) tenant-name branch [anti-pattern] · (B) registry keyed by tenant · (C)
config-value selects handler · (D) parameter-driven data (no code selection).

- **The anti-pattern (A) is ABSENT on the Flask plane.** No hardcoded real tenant names, no
  `if administration == "<tenant>"` behavior branches in `backend/src/**`. (`administration ==
  "all"` in reporting/banking is a UI "all my tenants" data filter, not a branch; `h-dcn`/`hdcn`
  appear ONLY on the SAM plane.) So there is nothing to CLEAN UP — alignment is additive.
- **Flask tenant-admin functions are all GENERIC services parameterized by an `administration`
  string** (data, never a code branch), gated by three data-driven registries:
  - `MODULE_REGISTRY` (`services/module_registry.py`) + `tenant_modules` table — module
    entitlement (D); `has_module`/`module_required`/`activate_module`. Also does a genuine (C)
    dispatch: `module_backing()` / `resolve_module_api_base()` pick flask-vs-sam + the API base
    by MODULE NAME (this is how `MEMBERS` routes to the SAM plane).
  - `FUNCTION_REGISTRY` (`services/function_registry.py`) + `tenant_functions` table +
    `TenantFunctionService` — per-tenant optional-function TOGGLES (D; feature flags, no code
    selected).
  - `ParameterService` (`services/parameter_service.py`) scope chain
    (user→role→tenant→system→CODE_DEFAULTS) + `parameter_schema.py` — the per-tenant config store
    (D). `FieldConfigMixin` (`services/field_config_mixin.py`) is the per-tenant field overlay
    (D) — the direct analogue of the SAM `overlay_provider`.
- **The proven (C) TEMPLATE to copy** lives on the Flask plane already:
  `services/storage_resolver.py::resolve_storage_provider(tenant)` reads the
  `storage.invoice_provider` PARAMETER (options: `google_drive` / `s3_shared` / `s3_tenant`) and
  DISPATCHES to the matching storage handler. This is EXACTLY the shape the member-numbering
  direction (2) wants: a config value selects a registered generic strategy. Use it as the model.
- **SAM plane** (`sam/members/domain/tenant_hooks.py`): `TenantHookRegistry` keyed by
  `(HookName, tenant_id)` with SAFE GENERIC DEFAULTS, register-time validation; `HookName` =
  closed set {DERIVE_MEMBER_NUMBER, VALIDATE_MEMBER, ON_TRANSITION, RESOLVE_VISIBLE_REGIONS,
  CALCULATE_FEE}. Concrete tenant code `sam/members/tenants/hdcn/hooks.py` (only h-dcn, only 2 of
  5 points), wired once in `handler/app.py`. Selection is TENANT-IN-CODE via a registry (B) — the
  core never branches on tenant (Property 5).

### The gap + the aligned direction
- **Difference in SELECTION:** SAM resolves a CALLABLE by `(HookName, tenant_id)` (B); Flask
  resolves DATA/HANDLER by a config VALUE (C/D) and has NO named-callable-registry equivalent.
- **For member numbering specifically (2): use the (C) template, not (B).** Numbering is a
  choice-of-strategy → a `members.number_policy` param whose value names a generic strategy,
  dispatched by a small resolver (like `storage_resolver`). NO tenant literal, NO per-tenant
  callable — this is STRICTLY BETTER than the SAM tenant-hook approach for this case, and it's
  why `hdcn_derive_member_number` should be deleted rather than kept as a hook.
- **For genuinely bespoke behavior** that can't be reduced to a strategy value (e.g. h-dcn's
  motorcycle `validate_member` rule), the SAM `TenantHookRegistry` (B) is the right home; a
  Flask-side equivalent could be added IF/when real bespoke Flask behavior appears (none exists
  today, so it's not urgent — additive when needed).
- **Convergence rule to record as steering:** new tenant-specific behavior lands as (C) a
  config-selected generic strategy by default; only truly un-configurable logic uses (B) a
  tenant-keyed hook registry; NEVER (A) a tenant-name branch. Data differences stay (D).
- This cross-plane alignment write-up may live in the "fail-loud integrity / generic-vs-tenant
  placement" spec or a small steering note — decide when scoping.

- SCOPE: SAM members-domain + repository (`membership_service.create_member`, the numbering
  strategy engine + `members.number_policy` config, the `allocates_number` catalog flag, the
  repository counter + uniqueness guard, DELETE `hdcn_derive_member_number`), the projection of
  the new config, the Tenant-Admin editor surface, plus the frontend audit for leaked
  `member_id`, plus the cross-plane alignment investigation (4). Own spec.
- Relates to: the "fail-loud integrity / generic-vs-tenant placement" spec below (the numbering
  hardcode is an instance of generic-core-owning-a-tenant-concern).


# SPEC: Fail-loud integrity — kill silent fallbacks + reconcile stale projection + post-deploy pre-checks
**One spec — the projection-reconcile gap is an INSTANCE of the fallback pattern ("trust a
stale/derived value instead of failing/resyncing"), so they share a design.** Raised by the user
2026-09-23: *"many of these fallbacks create a mess ... a separate issue broader than the
token/claim issue ... address it as part of the code-quality exercises."*

## Part A — Silent fallbacks hide misconfiguration (the mess)
Across the stack, when a value is missing/ambiguous the code silently substitutes a "reasonable"
default instead of failing loudly. Individually harmless; in aggregate they HIDE real
misconfiguration and make "why is it empty/wrong?" undiagnosable — the failure surfaces far from
its cause (empty lists, wrong-tenant data), never as an error.

Concrete instances seen (evidence, not speculation):
- **Frontend API base URL fallback → localhost.** Deployed SPA baked WITHOUT
  `VITE_MEMBERS_API_BASE_URL` fell back to `127.0.0.1:3000` → prod called localhost, showed no
  members, no error (fixed PR #16). Default masks missing config.
- **Roles fallback in `getCurrentUserRoles()`** — `/api/auth/me` (MySQL merged roles) then FALLS
  BACK to `cognito:groups` on failure. Two sources of truth; on divergence the UI silently trusts
  whichever answered.
- **Active-tenant "default to first tenant"** — the SAM edge (s5f) deliberately rejected this
  (deny, don't default) because a silent default exposes WRONG-TENANT data. The same "just pick
  one" instinct may live in other paths (select-never-default).
- **`.env` static AWS keys overriding `AWS_PROFILE`** (steering 41) — a credential "fallback"
  chain that silently runs against the WRONG account (`ResourceNotFoundException` instead of
  "wrong creds").

## Part B — Stale projection rows are never reconciled (a security-relevant instance)
Found during s5d C.12. `ProjectionSync.sync_administration`
(`backend/src/services/projection_sync.py`) only diff-deletes obsolete `scopegrant#` rows
(`_reconcile_scopegrants`); its docstring notes `tenant`/`module#*`/`role#*`/`config#*` are
"never listed and never deleted." Consequence: a role REMOVED from MySQL `user_tenant_roles`
leaves a STALE `role#<email>#<role>` row in `governance_projection` indefinitely — the projection
keeps advertising a role the source no longer grants (SECURITY-relevant staleness). Real example:
prod `h-dcn` had 3 orphaned role# rows with no MySQL source (`Regio_All`, a `h-scn` typo'd
Tenant_Admin, a `member-test@example.com` row) — cleaned up manually in C.12. The
capability path reads the projection (`has_capability` off `custom:entitlements`), so a stale
`role#` row can INFLATE a resolved entitlement once the PreTokenGen trigger is live — worth
fixing early (likely the FIRST phase of this spec given the security angle).
- Options: extend the reconcile to `role#` (and consider `module#`) with the same
  diff-and-delete pattern, scoped per tenant; OR a periodic reconciliation sweep.

## Direction (needs a design pass — do NOT blind-patch)
- **Inventory** every fallback/default in the request/auth/config paths (frontend + Flask + SAM
  edge). For each: SAFE degenerate case, or MASKING a missing input?
- **Fail loud on missing REQUIRED config** — missing API base URL, missing tenant selection for a
  multi-tenant user, missing entitlement → explicit error at startup/at the edge, not a silent
  substitution. (s5f is the template: select-never-grant, deny-don't-default.)
- **Single source of truth** — remove the roles double-read fallback (MySQL-merged authoritative;
  treat `cognito:groups` divergence as an error to surface).
- **Reconcile derived data** — Part B: no stale projection rows advertising removed capabilities.
- **Post-deploy pre-checks** — after a deploy, verify parameters/config availability (API URLs,
  required env vars, projection freshness) so a missing input is caught at deploy time, not as an
  empty screen in prod.
- **Guard rails** — extend the "no fallback tenant symbol in live code" grep guard (s5f R4.3) into
  a broader lint for known fallback anti-patterns.
- SCOPE: cross-cutting code-quality; own spec. Relates to steering 41, s5f (ADR 0007), and the
  member-number hardcode (generic-vs-tenant placement) in the identity spec above.


# SPEC: Shared frontend component library — enforce reuse (filters, dropdowns, layout)
**One spec — "how do we enforce reuse" + the specific reusable components that keep getting
reinvented.**

## Goal: enforce reuse of code used in many places
How do we make shared building blocks the DEFAULT (not copy-paste)? A discoverable set of
components/hooks + a convention (and ideally a lint/steering nudge) so tables, filters, and
dropdowns are built from one place.

## Piece 1 — Table Filter Framework v2 is not yet a real framework/library
The hybrid table approach exists but isn't packaged as a true reusable library: text-search
filters in column headers (`FilterableHeader`), dropdowns/multi-select above the table
(`FilterPanel`), hooks `useColumnFilters`/`useTableSort`/`useFilterableTable`, parameter-driven
`useTableConfig`, a clear-all/reset. Make it a real, documented, imported-everywhere library.
Guide: `.kiro/specs/Common/Frameworks/table-filter-framework-v2/design.md`.

## Piece 2 — A REUSABLE lazy/edit-on-click dropdown for the WHOLE platform
Raised 2026-09-24 during s5j. A better design than the always-open `<select>` for editing a
field that already has a value: show the CURRENT value as plain text (or a closed control) and
only reveal the dropdown + options WHEN the user interacts (click/focus). The content stays as-is
until the user opens it.
- Why: an always-open `<select {...formikField}>` only preselects when the stored value EXACTLY
  matches a rendered `<option value>`; otherwise it shows the placeholder and the value looks
  BLANK. Bites on: a LEGACY value retired from the option set, a role-gated option the caller
  can't pick, or a value simply absent. (s5j shipped a NARROW stopgap in
  `MembersFieldFormBody.renderOptions` — prepend the current value as a synthetic option; THIS is
  the generic replacement.)
- Scope: ONE reusable component (e.g. `frontend/src/components/common/LazySelect.tsx`) + optional
  `useLazyOptions` hook (options resolved/loaded on OPEN — supports async sources too), used by
  EVERY dropdown (FIN/STR/ZZP/TENADMIN/Members/tenant-admin editors). Contract: always DISPLAY the
  current value (never blank it) even if not in the option set; reveal options only on
  interaction; on pick, replace; a value not in the list is preserved until changed (the
  "tolerate legacy, enforce on change" rule). Chakra-consistent; keyboard + ARIA combobox
  accessible. Migrate incrementally; once Members adopts it, REMOVE the s5j stopgap (leave a
  pointer).
- Calculated/derived fields stay NON-editable (nothing to pick).

## Piece 3 (candidate) — Member modal responsive multi-column layout
The member modal is one long list of fields with functional separators. Nice to have 3–4 columns
on desktop, reducing to 1 on mobile. Fits here IF built on a shared responsive-layout primitive;
otherwise it can be a small standalone tweak. Decide during design.


# Code quality and Full test suite
Do they need updates to support the SAM platform? (Cross-cutting audit — may feed the fail-loud
integrity spec above.)


# Tenant switch doesn't refresh the module menu without a page reload
Observed 2026-09-23. When a multi-tenant user switches tenant via the `TenantSelector` dropdown,
the main menu's module gating (FIN/STR/ZZP/MEMBERS) does NOT update immediately — a full page
refresh is needed. Relevant to "active tenant bounds capability" (s5f): a stale menu could
briefly offer Members for a no-MEMBERS tenant until refresh. (The SAM edge denies regardless — a
UI-freshness bug, not a security hole.)

Investigation so far (wiring looks structurally correct — root cause is runtime/timing, NOT the
obvious "bypasses React state" bug):
- `TenantSelector.tsx` `onChange` → `setCurrentTenant(e.target.value)` (React state via context),
  not a direct localStorage write. Good.
- `TenantContext.tsx` `setCurrentTenant` → `setCurrentTenantState(tenant)` +
  `localStorage.setItem('selectedTenant', tenant)`. Should re-render consumers.
- `useTenantModules.ts` has `useEffect(fetchModules, [currentTenant])` → should refetch
  `/api/tenant/modules` and update `hasFIN/hasSTR/hasZZP/hasMEMBERS`.
- `App.tsx` reads those flags and passes them to `MainMenu`.
So the chain SHOULD refresh reactively. It doesn't — the break is elsewhere.
- SUSPECTS (need reproduction + trace): (a) `apiService.authenticatedGet` builds the `X-Tenant`
  header / caches in a way that races or ignores the state update; (b) a stale closure /
  memoization; (c) `/api/tenant/modules` response cached; (d) `MainMenu` not re-rendering on the
  flag change. `TenantContext` init effect is keyed on `[user]` only (intentional) — not the cause.
- FIX APPROACH: reproduce, trace where the refetch either doesn't fire or resolves against the old
  tenant; key the module fetch to the CURRENT tenant at request time (not a stale localStorage
  read); ensure `MainMenu` re-renders on the flag change.
- Scope: FRONTEND only. Small, own task.
- Files: `frontend/src/components/TenantSelector.tsx`, `context/TenantContext.tsx`,
  `hooks/useTenantModules.ts`, `services/apiService.ts`, `App.tsx`, `components/MainMenu.tsx`.


# SPEC: Tenant Administration architecture — registry-driven admin surfaces
**Problem:** the Tenant-Admin dashboard tabs are a HARDCODED flat list with ad-hoc gating
(`frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`): some tabs always render
(Users, Functions, Storage, Templates, Media, Tenant Info, Sender, Pivot, Landing), FIN shows
`if hasFIN`, Members `if hasMembers`, Advanced `if isSysAdmin`. There is NO model of "which admin
surface belongs to / is needed by which module", so the differences a user sees
(FIN admin gets Advanced/Storage; Members admin gets a 4-subtab editor; etc.) are ACCIDENTAL, not
designed. Standardize it.

## The three KINDS of admin surface (the core model)
1. **Cross-cutting capabilities** — Storage, Functions, Pivot, Templates, Media Assets, Advanced.
   Not owned by one module; they SERVE modules. Storage is the clearest: one tenant choice that
   many object-storing modules (FIN invoices, Members docs, STR) consume.
2. **Module-specific config** — Financial (FIN), Members (MEMBERS). Owned by exactly one module;
   meaningful only when that module is entitled. A module's panel may be a single view (FIN) or a
   sub-tabbed panel (Members' 4 tabs) — richness is the module's own concern, NOT something to
   force uniform.
3. **Namespace-driven parameter views** — "Advanced" is the generic one: it renders ALL params in
   a namespace as a table. It is not a feature; it is a GENERIC parameter editor pointed at a
   namespace. Members' typed config editor is the FRIENDLY version of the same underlying thing.

## The architecture: one registry of admin surfaces + modules declare what they CONSUME
Replace the hardcoded tab list with a registry; each surface declares WHEN it applies:
- **`always`** — platform baseline for any Tenant_Admin (e.g. Users, Tenant Info).
- **`module: <NAME>`** — shown only when that module is entitled (Financial→FIN, Members→MEMBERS).
- **`capability` (cross-cutting)** — shown when ANY entitled module DECLARES it consumes that
  capability. Storage renders because some entitled module said `consumes: storage`, NOT because
  it is hardcoded always-on.

Extend `MODULE_REGISTRY` (`backend/src/services/module_registry.py`) with an admin declaration
per module, e.g.:
```
FIN      → admin_panel: "financial";  consumes: [storage, templates, pivot]
MEMBERS  → admin_panel: "members";    consumes: [storage, media]
STR      → consumes: [storage, pivot]
```
The dashboard DERIVES its tabs: baseline ∪ (module panels for entitled modules) ∪ (cross-cutting
surfaces any entitled module consumes) ∪ (role-gated surfaces e.g. Advanced for SysAdmin). No
if-ladder. Adding a module's admin surface = one registry entry, not editing the dashboard.

## Storage — a SHARED CAPABILITY with a per-tenant choice (the key example)
Storage is "one choice relevant for many modules that store objects." Architecture:
- **Config once** — a tenant-scoped param (`storage.invoice_provider`, options
  google_drive/s3_shared/s3_tenant), authored in the Storage admin surface.
- **Many consumers via one resolver** — `services/storage_resolver.py::resolve_storage_provider`
  is the single dispatch; FIN, Members, STR all call it. (This is the config-value→handler
  pattern; see the "Member number policy" spec's StrategyResolver — Storage is a sibling use.)
- **Surface visibility** — the Storage tab appears when an entitled module declares
  `consumes: storage`. So a Members-only tenant that stores docs still gets Storage; a tenant
  whose modules store nothing does not.

## "Advanced" + Members config — one thing at two polish levels (namespace parameter editing)
Both are PARAMETER-NAMESPACE editors over the `parameters` table:
- Every module namespace gets a GENERIC namespace editor for free (the raw table = "Advanced",
  SysAdmin-gated because raw params are dangerous).
- A module MAY register a TYPED editor that supersedes the raw table for its namespace (Members
  did this with its 4-tab config; FIN could). "Advanced" stays the catch-all for namespaces
  without a typed editor.
This unifies why Members-config and Advanced felt inconsistent — they are the same mechanism
(namespace param editing), one typed, one raw.

## Open questions (design pass)
- Which cross-cutting surfaces are truly `always` vs `capability`-consumed? Today Storage/
  Templates/Media are always-on — likely wrong for a module that stores nothing. Make each an
  explicit per-module `consumes` decision.
- Where does the admin-surface registry live: extend `MODULE_REGISTRY` (backend, projectable) vs
  a frontend-only surface map? Prefer backend so both the entitlement truth and the surface
  declaration share one source.
- Relationship to `tenant_functions` (the Functions tab): that is the WITHIN-module toggle layer;
  the admin-surface registry is the WHICH-surfaces layer. Keep them distinct but consistent.
- SCOPE: `MODULE_REGISTRY` + `TenantAdminDashboard.tsx` + the generic namespace param editor +
  the storage resolver. Relates to: "Member identity & number policy" (StrategyResolver / config
  patterns), "Fail-loud integrity" (generic-vs-tenant placement), "Shared frontend component
  library" (the dashboard is a reuse consumer). Own spec.