
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

# Fallback mechanisms create a mess — CODE-QUALITY TRACK (broader than tenant scope)
**Raised by user 2026-09-23** during the s5d "no members shown" debug: *"many of these
fallbacks create a mess ... the fallback mess is a separate issue broader than the token/claim
issue. We should address it in a special path as part of the code-quality exercises."* So this
is its OWN code-quality track item, not folded into any single feature spec.

## The pattern (why it's a mess)
Across the stack, when a value is missing/ambiguous the code silently substitutes a
"reasonable" default instead of failing loudly. Each fallback individually looks harmless; in
aggregate they HIDE real misconfiguration and make "why is it empty / wrong?" undiagnosable —
the failure surfaces far from its cause, as empty lists or wrong-tenant data, never as an error.

## Concrete instances seen this session (evidence, not speculation)
- **Frontend API base URL fallback → localhost.** The deployed SPA was baked WITHOUT
  `VITE_MEMBERS_API_BASE_URL` and silently fell back to `127.0.0.1:3000`, so prod called
  localhost and showed no members with no error (s5d CE.3; fixed PR #16). Classic "default
  masks missing config".
- **Roles fallback in `getCurrentUserRoles()`** — calls `/api/auth/me` (MySQL merged roles)
  then FALLS BACK to `cognito:groups` on failure. Two sources of truth for "what can this user
  do"; when they disagree the UI silently trusts whichever answered, hiding the real state.
- **Active-tenant "default to first tenant"** (the Flask-side habit) — the SAM edge s5f
  DELIBERATELY rejected this (403 instead of default-to-first) precisely because a silent
  default exposes WRONG-TENANT data. The mess: the same "just pick one" instinct lives in other
  code paths and needs the same treatment (select-never-default).
- **Stale projection rows never reconciled** (`role#`/`module#`) — the projection keeps
  advertising a capability the source removed; a "fall back to whatever's projected" read then
  trusts stale data. (Tracked separately under the projection-reconcile item, but it's the same
  class: trust a stale/derived value rather than fail/resync.)
- **`.env` static AWS keys overriding `AWS_PROFILE`** (steering 41) — an env-var "fallback"
  credential chain that silently runs against the WRONG account (`ResourceNotFoundException`
  instead of "you picked the wrong creds"). Environment-level, but same failure shape.

## Direction (needs a design pass — do NOT blind-patch)
- **Inventory** every fallback/default in the request/auth/config paths (frontend + Flask +
  SAM edge). For each: is the default SAFE (a true degenerate case) or is it MASKING a missing
  input?
- **Fail loud on missing REQUIRED config** — a missing API base URL, a missing tenant selection
  for a multi-tenant user, a missing entitlement should be an explicit error at startup / at the
  edge, not a silent substitution. (s5f is the template: select-never-grant, deny-don't-default.)
- **Single source of truth** — remove the roles double-read fallback (pick MySQL-merged as
  authoritative; treat `cognito:groups` divergence as an error to surface, not a silent
  fallback).
- **Post-deploy pre-checks** (the original stub's idea): after a new deployment, verify
  parameters/config availability (API URLs, required env vars, projection freshness) so a
  missing input is caught at deploy time, not as an empty screen in prod.
- **Guard rails**: extend the existing "no fallback tenant symbol in live code" grep guard
  (s5f R4.3) into a broader lint for known fallback anti-patterns.
- SCOPE: cross-cutting code-quality; likely its own spec. Relates to: "Projection sync
  reconcile" item, s5f (the deny-don't-default precedent / ADR 0007), s5d CE.3 (the API-URL
  fallback), steering 41 (the credential fallback).
- Original stub intent preserved: fallbacks *outside tenant scope* "should be impossible";
  add post-deployment pre-checks on parameter/config availability.


# Projection sync does not reconcile obsolete role# / module# / config# rows (only scopegrant#)
Found during s5d C.12 (2026-09-23). `ProjectionSync.sync_administration` (backend/src/services/projection_sync.py)
only diff-deletes obsolete `scopegrant#` rows (`_reconcile_scopegrants`). Its own docstring notes
`tenant`/`module#*`/`role#*`/`config#*` are "never listed and never deleted (out of s5d's scope)".
Consequence: a role REMOVED from MySQL `user_tenant_roles` leaves a STALE `role#<email>#<role>` row in
`governance_projection` indefinitely — the projection keeps advertising a role the source no longer grants
(SECURITY-relevant staleness, same class as the scopegrant staleness that reconcile was built to fix).
Real example: prod `h-dcn` had 3 orphaned role# rows with no MySQL source (`Regio_All`, a `h-scn` typo'd
Tenant_Admin, and a `member-test@example.com` row) — cleaned up manually in C.12.
- Options: extend the reconcile to `role#` (and consider `module#`) with the same diff-and-delete pattern,
  scoped per tenant; OR a periodic reconciliation sweep.
- Note the capability path today is token/entitlement-based (has_capability off `custom:entitlements`), and
  the resolver reads the projection — so a stale `role#` row could inflate a resolved entitlement once the
  PreTokenGen trigger is live (s5d PHASE CE). Worth fixing before/with CE.2.
- Related: "Fall back mechanism outside tenant scope" above (projection integrity / post-deploy pre-checks).


# SAM deploys are ad-hoc (no committed samconfig / CI) — codify test+prod
**[ADDRESSED 2026-09-23 by spec `s5e-codify-sam-deploys`]** — `sam/pretokengen` now has a
committed `samconfig.toml` (distinct `[test]`/`[prod]` stacks) + an OIDC CI workflow
(`deploy-sam-pretokengen.yml`), matching the codified `sam/members`. The cross-account
Cognito invoke permission is now template-owned (`sam deploy` re-asserts it). Deployed to
prod via PR #17 (merge `ef7a677`, workflow run 35921358965 success); orphaned CE.5 hand
permission removed so the template is sole owner. Deploy runbook: `sam/pretokengen/DEPLOY.md`.
Remaining follow-ups (both OUT of s5e scope, see spec ODx2/ODx3): (ODx2) optionally add a CI
job that auto-deploys `--config-env test` on dispatch; (ODx3) fold the ONE remaining manual
step — the Pool A Pre-Token-Generation TRIGGER attach (identity account) — into Terraform.
---
Surfaced during s5d PHASE CE (2026-09-23). The SAM Lambdas are deployed by hand-typed
`sam deploy` commands with INLINE `--parameter-overrides`, not from committed config or CI.
Consequences seen:
- **`sam/pretokengen` has NO `samconfig.toml`** and NO deploy workflow. The prod-stage Lambda
  (`pretokengen-prod`) was never deployed — only `pretokengen-test` exists (stack
  `pretokengen-data`, deployed with `Stage=test`).
- **Stack naming is unpinned + has a footgun:** `Stage` is only a parameter that names the
  function/layer (`pretokengen-${Stage}`), NOT the stack. Re-deploying the SAME stack
  (`pretokengen-data`) with `Stage=prod` would RENAME/REPLACE `pretokengen-test` →
  `pretokengen-prod`, destroying the working test-pool Lambda. Only manual discipline (pick a
  NEW stack name, e.g. `pretokengen-prod`) prevents this — the tooling doesn't.
- The frontend had the same class of gap: a required build env var (`VITE_MEMBERS_API_BASE_URL`)
  was simply missing from `deploy-frontend.yml`, so prod silently shipped the localhost fallback
  (fixed 2026-09-23, PR #16). Root cause = deploy config not complete/committed.
- Credential fragility compounds it: repo `.env` static AWS keys override `AWS_PROFILE`, so a
  plain profile invocation silently hits the WRONG account (see steering 41 / the export-role-creds
  workaround).
FIX (make prod deploys stable + repeatable BEFORE more high-blast-radius prod steps like the
Pool A trigger attach):
- Add a committed `samconfig.toml` per SAM app (`sam/pretokengen`, and confirm `sam/members`)
  with DISTINCT `test` and `prod` environments — each pinning a distinct stack name + params
  (Stage/Region/GovernanceProjectionTableName), so `sam deploy --config-env prod` is one
  reviewed, repeatable command (no inline params, no rename-the-test-Lambda trap).
- Add a GitHub Actions deploy workflow for `sam/pretokengen` (like `deploy-sam-members.yml` /
  `deploy-frontend.yml`) via OIDC, no stored secrets.
- Until then, PHASE CE manual deploys MUST use a NEW stack name for prod and a changeset review.

# SAM Members edge can't resolve an active tenant for multi-tenant users (403)
Discovered during s5d PHASE CE (2026-09-23). BLOCKS s5d PHASE D.
`sam/members/handler/app.py` `_establish_tenant_context(entitlement)` requires
`len(entitlement.tenant_keys) == 1`, otherwise raises `TenantResolutionError` -> 403.
It never inspects the `X-Tenant` request header. Consequence: any user with access to
more than one tenant (e.g. peter@pgeers.nl = 7 tenants, webmaster@h-dcn.nl = ["mytest3","h-dcn"])
gets a 403 from the Members API even though their token correctly carries the
`h-dcn:[members:admin/export/read/write]` capabilities. This surfaces as "no members shown"
in the UI. The early deny happens at the edge (~3.5ms), so members-prod app logs show no error.

This is NOT the intended model. The active tenant is a PER-REQUEST selection:
- the client sends the chosen tenant via `X-Tenant`,
- the edge validates that tenant is a member of the caller's verified tenant list
  (from the token / entitlement), and
- proceeds with that single active tenant for the request.
A single-tenant user is just the degenerate case (one allowed tenant).

This exact pattern is already proven in the Flask/UI side of myAdmin:
`backend/src/auth/tenant_context.py` (`get_current_tenant` / `validate_tenant_access`)
validates `X-Tenant` against the verified `custom:tenants` list. The SAM edge should mirror it.

FIX: replace the `len(tenant_keys) == 1` check with:
- read `X-Tenant` header,
- if absent and exactly one tenant -> use it (back-compat),
- if present -> require it be in `entitlement.tenant_keys`, else 403,
- if absent and multiple tenants -> 400/409 asking the client to specify a tenant.
Then scope the rest of the request to that single active tenant.

- ADR-worthy (active-tenant resolution contract for the SAM edge).
- Unblocks s5d PHASE D. PreTokenGen trigger is already attached to Pool A (harmless) and
  the token capabilities are correct; only the edge resolution is wrong.
- Related: this is the first of the 3 remediation specs; #2 (projection role#/module# reconcile)
  and #3 (codify SAM deploys) are the other two.


# Member modal UI
The modal is one long list of fields with functional seperator. It would be nice to have 3 or 4 columns on a desktop window reducing columns to 1 on a mobile

# Code qaulity and Full test suite
Do they need updates to supprt sam platform

# Tenant switch doesn't refresh the module menu without a page reload
Observed 2026-09-23. When a multi-tenant user switches tenant via the `TenantSelector`
dropdown, the main menu's module gating (FIN/STR/ZZP/MEMBERS sections) does NOT update
immediately — a full page refresh is needed before the menu reflects the new tenant's
modules. Relevant to the "active tenant bounds capability" principle (s5f): a stale menu
could briefly offer the Members app for a tenant that has no MEMBERS module until refresh.
(The SAM edge denies regardless — s5f — so this is a UI-freshness bug, not a security hole.)

Investigation so far (wiring looks structurally correct — root cause is runtime/timing, NOT
the obvious "bypasses React state" bug):
- `TenantSelector.tsx` `onChange` calls `setCurrentTenant(e.target.value)` (React state via
  context) — NOT a direct localStorage write. Good.
- `TenantContext.tsx` `setCurrentTenant` → `setCurrentTenantState(tenant)` +
  `localStorage.setItem('selectedTenant', tenant)`. Updates state, should re-render consumers.
- `useTenantModules.ts` has `useEffect(fetchModules, [currentTenant])` → should refetch
  `/api/tenant/modules` and update `hasFIN/hasSTR/hasZZP/hasMEMBERS` on switch.
- `App.tsx` reads those flags from `useTenantModules()` and passes them to `MainMenu`.
So the chain SHOULD refresh reactively with no reload. It doesn't — so the break is elsewhere.
- SUSPECTS (need reproduction + trace, not yet confirmed): (a) `apiService.authenticatedGet`
  builds the `X-Tenant` header / caches in a way that races or ignores the state update;
  (b) a stale closure / memoization; (c) `/api/tenant/modules` response cached;
  (d) `MainMenu` not re-rendering on the flag change. `TenantContext` init effect is keyed on
  `[user]` only (intentional), so it's not re-initialising the tenant — not the cause.
- FIX APPROACH: reproduce, trace where the refetch either doesn't fire or resolves against the
  old tenant; ensure the module fetch is keyed to the CURRENT tenant value at request time
  (not a stale localStorage read), and that `MainMenu` re-renders on the flag change.
- Scope: FRONTEND only (separate from s5f, which is the SAM API edge). Small, own task.
- Files: `frontend/src/components/TenantSelector.tsx`, `context/TenantContext.tsx`,
  `hooks/useTenantModules.ts`, `services/apiService.ts`, `App.tsx`, `components/MainMenu.tsx`.

# Members field-config 502 — a scope-dimension field declared `enum` in the overlay has no `choices`
**[RESOLVED 2026-09-24 by spec `s5j-members-config-authoring-path`]** — chose option (b): the
field resolver now SOURCES a scope-dimension-backed overlay enum's dropdown `choices` from
`scope_dimensions.values` at resolve time (single source of truth; NO stored duplication; NO
h-dcn data migration; region stays a plain string, dropdown is advisory, change-gated on save).
Matched on the dimension's `field` (not `key`); supports multiple dimensions. Shipped via PR #22
(domain) + PR #23 (the app-wiring follow-up that actually passes `scope_config_provider` into the
service — the first deploy 502'd because that wiring was missing). VERIFIED in prod:
`GET /prod/members/field-config` = 200, zero OverlayError in `members-prod`. The Members table
`region` column + the member modal now render. (Frontend config-editor URL double-prepend bug
fixed in the same spec.) — Original report below for history:
---
Discovered 2026-09-24 during s5d PHASE D (first real browser traffic to the Members API, after
the s5f/s5g/s5h fixes unblocked auth/CORS/IAM). `GET /prod/members/field-config` returns 502.
members-prod log:
```
OverlayError: invalid tenant field overlay: overlay.region: an enum variable field must
declare choices/options
  ... field_resolver.py resolve -> _reject_invalid_overlay -> raise OverlayError
```
ROOT CAUSE (data, verified in prod MySQL): h-dcn's `members.field_overlay` param
(`parameters` where scope='tenant', scope_id='h-dcn', namespace='members', key='field_overlay')
declares `region` as `{"type":"enum", "label":{...}, "order":10, "required":false,
"functional_group":"membership"}` — with **NO `choices`**. Every OTHER enum overlay field
(`motor_brand`, `magazine_pref`, `payment_method`, `newsletter_pref`) carries a `choices` array,
so the field resolver accepts them; `region` alone is rejected → the whole field-config resolve
raises → 502.

WHY it's like this (design tension, NOT a simple typo): `region` is the h-dcn **scope
dimension** (s5d). Its allowed VALUES live in `members.scope_dimensions` (the 10 regions), not as
overlay `choices`. So the overlay authored `region` as a bare `enum` expecting its values to come
from the scope-dimension config, but the field resolver requires an `enum` overlay field to carry
its own `choices`. The two views of "what are region's allowed values" disagree.

OPTIONS (needs a design decision — do NOT blind-patch):
- (a) DATA fix: populate the `region` overlay field's `choices` from the scope_dimensions values
  when authoring/projecting (i.e. the projection or the tenant-admin authoring UI copies the
  scope-dimension values into the overlay field's choices). Keeps the resolver contract intact.
- (b) CODE fix: the field resolver sources an enum field's choices from the tenant's
  `scope_dimensions` when the field IS a scope dimension (don't require inline `choices` for a
  scope-dimension-backed enum). Single source of truth = scope_dimensions.
- (c) MODEL fix: a scope-dimension field is a distinct field TYPE (not a plain `enum`) so the
  resolver knows its values come from scope config, not inline choices.
- Recommendation lean: (b) or (c) — single source of truth for the dimension's values in
  `scope_dimensions`, rather than duplicating them into overlay `choices` (a) which can drift.
- SCOPE: s5d/members-domain territory (`sam/members/domain/field_resolver.py`,
  `scope_dimensions.py`, the projection `config#fields`/`config#scope` rows, and the
  tenant-admin overlay authoring). Own spec/task.
- Impact: blocks the Members field-config call (the typed-field UI config); the member LIST is a
  separate call (fixed separately: the Decimal-serialization bug). Non-security.


# Libraries, Frameworks, Helpers
How can we enforce reuse of code that is used on many places
##  Table Filter Framework v2 is not a real framework / library
Use the Table Filter Framework v2 — a hybrid approach: text search filters in column headers (`FilterableHeader`), dropdowns/multi-select above the table (`FilterPanel`).

- Key hooks: `useColumnFilters`, `useTableSort`, `useFilterableTable`
- Parameter-driven config for complex tables: `useTableConfig`
- Components: `FilterPanel` (above table), `FilterableHeader` (in `<Th>`)
- Clear all / reset button to return to default view

When implementing or modifying tables or filters, read the full framework guide at `.kiro/specs/Common/Frameworks/table-filter-framework-v2/design.md


# RCA: SAM member-number allocation uses a generic atomic counter — but numbering is a TENANT-specific concern
Surfaced 2026-09-24 during s5j review. The user recalled an earlier decision to STOP using the
counter-algorithm for member numbers ("Members-CRUD can detect the highest number by sorting on
the field and add 1 manually"). The SAM write path does NOT reflect that — and the deeper point
is a design-placement issue, not just dead code.

## What the code does today (verified, live — NOT dead code)
- `MembershipService.create_member` (`sam/members/domain/membership_service.py` ~line 1280):
  when a new member has no `member_number`, it calls
  `self._repo.next_counter(tenant_id, MEMBER_NUMBER_COUNTER)` (an atomic DynamoDB `ADD` on a
  `counter#member_number` item — `repository/table_design.py`), threads the value into the
  `derive_member_number` hook, and h-dcn's registered `hdcn_derive_member_number`
  (`tenants/hdcn/hooks.py`) formats it (`L-000042`, prefix + zero-pad).
- `MEMBER_NUMBER_COUNTER = "member_number"` is just the counter's NAME (a per-tenant named
  sequence key), not the field. All of it is reachable and covered by tests.

## The real issue (why this is RCA, not a quick delete)
Member-number allocation is a **tenant-specific policy** (format AND generation strategy differ
per club): h-dcn wants an `L`-prefixed zero-padded atomic sequence; another tenant may want
plain max+1, or externally-assigned numbers, or none. Today the GENERIC write path hardcodes
"fetch an atomic counter, then let the hook format it" — i.e. the *generation strategy* (atomic
counter) lives in the generic core, and only the *format* is delegated to the tenant hook. That
split is arguably wrong: BOTH the strategy and the format are tenant nuances and should sit in
the tenant layer (`derive_member_number` hook), leaving the generic path to just call the hook
and persist. As-is, a tenant that does NOT want counter-based numbering still triggers a
`next_counter` fetch it doesn't use.

## The concurrency tradeoff (must be decided, not assumed)
- **Atomic counter (current):** no duplicate numbers under concurrent creates (the whole reason
  it exists). 
- **"Sort max + 1" (the recalled decision):** simpler, no counter item — BUT racy: two
  concurrent creates read the same max and both write N+1 → duplicate. If chosen, it needs a
  unique constraint + retry, or acceptance of the risk. Note this is a MOTOR club with likely
  low create concurrency, so max+1 may be acceptable in practice — a deliberate call.

## Options (decide, don't blind-change)
- (a) Move the WHOLE allocation (strategy + format) into the tenant `derive_member_number` hook;
  the generic path only calls the hook + persists. Per-tenant: h-dcn keeps its atomic counter;
  a max+1 tenant does its own read-max. Cleanest re: "numbering is tenant-specific".
- (b) Keep the generic counter but make it OPT-IN per tenant (a tenant with no counter policy
  skips the `next_counter` fetch entirely).
- (c) Switch h-dcn specifically to max+1 in its hook (drop the counter) — only if the user
  confirms max+1 is the intended h-dcn behavior AND the concurrency risk is accepted.
- Reconcile with the Flask/MySQL plane: confirm which plane the original "stop the counter"
  decision was for; the SAM plane may simply never have applied it (stale-decision drift).
- SCOPE: SAM members-domain (`membership_service.create_member`, `MEMBER_NUMBER_COUNTER`,
  `tenants/hdcn/hooks.py`, `repository` counter). Own small spec. NOT part of s5j.
- Relates to: the broader "fallback-mess / generic-vs-tenant placement" code-quality track.

# Member-id UUIF
There is confusing in the use of the member


# UX: a REUSABLE lazy/edit-on-click dropdown for the WHOLE myAdmin platform
Raised by user 2026-09-24 during s5j Members edit-modal review. A better design than the current
"always-open `<select>`" for editing a field that already has a value: show the CURRENT value as
plain text (or a closed control) and only reveal the dropdown + its options WHEN the user
interacts with it (click/focus). The content stays as-is until the user deliberately opens it to
change it.

## Why (the problem it solves cleanly)
An always-open `<select {...formikField}>` only displays a preselected option when the stored
value EXACTLY matches one of the rendered `<option value>`s. When it doesn't, the control falls
back to its placeholder and the existing value looks BLANK. This bites whenever the stored value
is: a LEGACY value no longer in the current option set (e.g. a region spelling retired from
`scope_dimensions.values`), a role-gated enum option the current caller can't pick (filtered out),
or simply absent from the list. (s5j shipped a NARROW stopgap for the Members form — prepend the
current value as a synthetic option so it stays visible/selected — see MembersFieldFormBody
`renderOptions`. This backlog item is the GENERIC, better replacement.)

## Scope — a PLATFORM-WIDE reusable control (not Members-only)
Build ONE reusable dropdown component/helper used by EVERY dropdown across the myAdmin frontend
(FIN/STR/ZZP/TENADMIN/Members/tenant-admin config editors, etc.), not a Members-local widget:
- A shared component (e.g. `frontend/src/components/common/LazySelect.tsx` — final name/location
  TBD) + optionally a small hook (`useLazyOptions`) so option lists can be resolved/loaded ON
  OPEN (supports future async option sources too, e.g. catalog/reference fetches on demand).
- Contract: always DISPLAY the current value (never blank it), even if the value is not in the
  option set; reveal the options only on interaction; on pick, replace the value; a value not in
  the list is preserved until changed (honours the "tolerate legacy, enforce on change" rule the
  Members domain already uses).
- Consistent with the app's Chakra UI patterns; keyboard-navigable + accessible (ARIA combobox
  semantics, focus management) — doing this WELL is exactly why it deserves its own task rather
  than an inline change.
- Migrate existing dropdowns to it incrementally; once Members adopts it, REMOVE the s5j
  prepend-current-value stopgap in `MembersFieldFormBody.renderOptions` (leave a pointer there).
- Consider i18n of the display value/label and the "read-only until opened" affordance (a caret /
  edit hint) so users know it's editable.

## Notes / boundaries
- Calculated/derived fields stay NON-editable (correct today) — the lazy control does not apply
  to them (nothing to pick).
- This is a UX/frontend code-quality track item; relates to the broader "fallback-mess /
  generic-vs-tenant placement" track. Own spec.
