
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

## (2) Empty Lidnummer must be allowed to save; numbering is a TENANT-specific policy
Two linked problems:
- **Empty `member_number` is currently BLOCKED on save — should be allowed.** The write path
  requires a non-empty `membership.member_number` (see
  `sam/members/repository/members_repository.py` `save_member` + the create-path counter
  derivation) and rejects an empty one. The user's position: Lidnummer is just a CRUD-managed
  field; an empty one must NOT be blocked (sponsors/clubs and any member without a number need
  this).
- **Numbering strategy is hardcoded in the generic core (RCA, s5j review).**
  `MembershipService.create_member` (~line 1280): when a new member has no `member_number` it
  calls `self._repo.next_counter(tenant_id, MEMBER_NUMBER_COUNTER)` (atomic DynamoDB `ADD` on a
  `counter#member_number` item — `repository/table_design.py`), threads the value into the
  `derive_member_number` hook, and h-dcn's `hdcn_derive_member_number` (`tenants/hdcn/hooks.py`)
  formats it (`L-000042`). `MEMBER_NUMBER_COUNTER = "member_number"` is just the counter's NAME.
  All live + tested — NOT dead code. The design-placement issue: member-number allocation is a
  tenant policy (format AND generation strategy differ per club — atomic sequence, plain max+1,
  externally-assigned, or none), yet the generic path hardcodes "fetch atomic counter, then let
  the hook format." BOTH strategy and format should sit in the tenant `derive_member_number`
  hook; the generic path should just call the hook + persist. As-is a tenant that wants no
  counter still triggers a `next_counter` fetch it doesn't use.

  Concurrency tradeoff (decide, don't assume):
  - Atomic counter (current): no duplicate numbers under concurrent creates.
  - "Sort max + 1" (a decision the user recalled making — possibly for the Flask plane and never
    applied to SAM = stale-decision drift): simpler, no counter item, BUT racy (two concurrent
    creates read the same max → duplicate) unless guarded by a unique constraint + retry. A motor
    club has low create concurrency, so max+1 may be acceptable — a deliberate call.

  Options (decide, don't blind-change):
  - (a) Move the WHOLE allocation (strategy + format) into the tenant `derive_member_number`
    hook; generic path only calls the hook + persists. Cleanest re "numbering is tenant-specific."
  - (b) Keep the generic counter but make it OPT-IN per tenant (no policy → skip `next_counter`).
  - (c) Switch h-dcn specifically to max+1 in its hook (drop the counter) — only if the user
    confirms max+1 is intended for h-dcn AND accepts the concurrency tradeoff.
  - Also make `member_number` OPTIONAL: skip the `membernum#<number>` uniqueness guard +
    auto-derivation when empty; only enforce uniqueness when a value IS present.

## (3) Use the member table for sponsors / clubs / non-person entities (the driver)
Storing organisations (sponsors, clubs) alongside people needs a member "kind"/type: which
fixed fields apply, how numbering behaves (usually none/optional — see (2)), and how
scope/overlay behave for a non-person. This is the broader design behind (1) and (2).

- SCOPE: SAM members-domain + repository (`membership_service.create_member`,
  `MEMBER_NUMBER_COUNTER`, `tenants/hdcn/hooks.py`, the repository counter + uniqueness guard),
  plus the frontend audit for leaked `member_id`. Own spec.
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
