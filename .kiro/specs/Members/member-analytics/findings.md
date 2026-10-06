# Findings — Member Analytics (post-implementation review)

- Spec: `./requirements.md` (R1–R10), `./design.md`, `./tasks.md`
- Branch: `test` (all tasks implemented and committed)
- Status: **In review** — findings categorized and mapped, fixes pending

---

## Findings

### F-001 — Console: JSON parse error on tenant string
- **Category:** cosmetic (pre-existing, not analytics-specific)
- **Requirement:** n/a (not analytics code)
- **Where:** `frontend/src/services/authService.ts:445` (`getCurrentUserTenants`)
- **Description:** `[Tenants] Failed to parse as JSON, treating as single tenant: "h-dcn" is not
  valid JSON`. The stored tenant value `h-dcn` is a plain string, not a JSON array, so
  `JSON.parse` throws and the catch-branch handles it. The warning is noisy but harmless.
  **Recommendation:** low-priority, suppress the console warning or store tenants as JSON. Not
  an analytics finding — pre-existing.

---

### F-002 — Analytics page not wired into Members function block
- **Category:** functional
- **Requirement:** R1.1 (separate Analytics page, sibling to Leden Overzicht, in the Members
  module's function block)
- **Where:** Members navigation / routing (likely `App.tsx` or a Members nav component)
- **Description:** The Analytics page exists but is not reachable from the main Members function
  block. Per R1.1, the Members function block should expose two entries: "Leden Overzicht"
  (the table) and "Analyse" (analytics). Currently the nav structure doesn't present the
  analytics page as a sibling inside the Members function block.
- **Root cause:** routing/nav wiring adds the analytics page route but does not add it to the
  Members function block's navigation (the block that groups Members sub-pages).

---

### F-003 — Overview only shows member count; avg age and avg years-member missing
- **Category:** functional
- **Requirement:** R2.1 (count + average age + average years-member), R2.5 (absent field → card
  omitted)
- **Where:** `MemberOverviewStats.tsx` → `findCalculatedField` + the row-value read
- **Description:** Only "Number of members: 105" renders. The avg age and avg years-member cards
  are not shown, even though all 1100 members have the calculated `age` and `years_member`
  values.
- **Root cause (likely):** the overview reads `row[AGE_KEY]` (i.e. `row['age']`) directly on the
  flat `MemberRow`, but the calculated fields are enriched into the **nested storage bucket**
  (`member.personal.age`, `member.membership.years_member`). The `flattenMember` in
  `membersApiService.ts` keeps the nested buckets but does NOT promote calculated fields to
  top-level flat aliases (it only promotes `name`, `email`, `status`, `membership_type`,
  `member_number`, `region`). So `row['age']` → `undefined` → `mean([])` → `null` → card
  omitted (R2.5 degradation fires when it shouldn't).
- **Fix:** use the shared `valueFor(row, group, key)` accessor (which reads `row[group][key]`
  first, then `row[key]`) to read calculated values, the same way the table cells read them.
  The storage group for `age` is `personal`, for `years_member` is `membership` — resolve from
  `fieldConfig`.

---

### F-004 — Overview missing: membership types with sum breakdown
- **Category:** functional (enhancement — R2.1 MAY clause)
- **Requirement:** R2.1 (MAY additionally show h-dcn-parity figures: members-per-membership-type)
- **Where:** `MemberOverviewStats.tsx`
- **Description:** The h-dcn `AnalyticsSection` shows a "Lidmaatschap Types" breakdown (type →
  count). This is listed as a MAY in R2.1 and is not implemented.
- **Recommendation:** add a per-membership-type count card/table in the Overview area, grouped by
  the `membership_type` field (always available, fixed field).

---

### F-005 — Distributions: "Not enough data" for both age and years-member
- **Category:** blocker
- **Requirement:** R3.1, R3.5
- **Where:** `MemberDistributions.tsx` → `buildMetricData` → `toNumber(row[metricKey])`
- **Description:** Both violins show "Not enough data to show a distribution" even though all
  1100 members have calculated `age` and `years_member`.
- **Root cause:** same as F-003 — `buildMetricData` reads `row[metricKey]` (flat key) instead of
  `valueFor(row, group, key)` (nested accessor). Every row's `age`/`years_member` resolves to
  `undefined` → `toNumber` → `null` → skipped → 0 valid points → below `MIN_DISTRIBUTION_POINTS`.
- **Fix:** use `valueFor(row, groupForKey(fieldConfig, metricKey), metricKey)` to read the nested
  calculated value, same fix as F-003. Pass `fieldConfig` to `buildMetricData`.

---

### F-006 — Pivot list presets dump the full raw member record (system columns + [object Object])
- **Category:** blocker
- **Requirement:** R4.8 (filtered list = chosen columns, not a raw dump), R4.7 (result renders
  correctly)
- **Where:** `memberPivotAdapter.ts` → `filteredListResult` → `inferListColumns` branch
- **Description:** The list-kind presets (birthday/birth-month, jubilees, new members,
  cancellations, clubblad digital) have `groupColumns: []` and `aggregateMeasures: []`, so the
  adapter falls into the "full projection" branch (`columnKeys.length === 0` → `{ ...row }`). This
  dumps every key on the flat `MemberRow` — including:
  - **System/internal columns:** `overlay`, `tenant_id`, `member_id`, `sk`, `membership_id`,
    `region_display`, `scope_values`
  - **Nested objects rendered as `[object Object]`:** `personal`, `membership` (these are the
    nested storage buckets that `flattenMember` preserves)
  And it **misses** the actually-wanted columns: `birthday`, `birth_month`, address fields, etc.
  (because those live inside the nested buckets, not at the top level).
- **Root cause:** list-kind presets don't specify which columns to show — they rely on the "full
  projection" fallback, which dumps the raw row shape instead of projecting through the resolved
  field config.
- **Fix (two parts):**
  1. **Presets must specify their columns.** Each list-kind preset should carry a `listColumns`
     (or use `aggregateMeasures` with the column keys, per the adapter's design) naming the
     meaningful member fields for that set — e.g. birthday/birth-month needs `name`, `email`,
     `birthday`, `birth_month`, `region`, plus address fields.
  2. **The adapter's full-projection fallback should filter to meaningful fields.** Instead of
     `{ ...row }`, project through `fieldConfig.fields` (only `visible` fields, skip system
     keys), and render nested-bucket values via `valueFor` so `personal.street` etc. resolve
     correctly instead of showing `[object Object]`.

---

### F-007 — Pivot result table missing filter-framework columns
- **Category:** functional
- **Requirement:** R4.7 (result renders using the framework's result table)
- **Where:** `PivotResultTable` rendering of the member pivot result
- **Description:** "Only 1 column Membership type has the filter field" — the other columns lack
  the per-column filter from the filter framework.
- **Root cause:** `PivotResultTable` is the framework's existing component (reused unchanged). It
  may only render filter inputs on columns it recognizes as filterable (group-type columns in an
  aggregate result). In the full-projection/list mode, all columns are typed as `group` but the
  result table may not auto-wire filters for inferred columns. May need the `filterable` flag
  or a table-config override for member-list results.

---

### F-008 — Three export actions where there should be one; "Export underlying data" fails
- **Category:** functional
- **Requirement:** R4.9 (CSV export)
- **Where:** `MemberPivotViews.tsx` export actions area + `PivotResultTable` built-in export
- **Description:** Three export buttons are visible, which is confusing and redundant:
  1. **Above the table (top):** a button with two options — "Export Pivot result" and "Export
     underlying data". Both attempt to download the same dataset. "Export underlying data" fails
     with "Failed to export data".
  2. **Below the table (bottom):** a single export button that does the exact same thing as the
     top "Export Pivot result" — a duplicate — with the **mail button to its right**.
  So the output actions are scattered: two-option export on top, and a duplicate export + mail
  below. There is no single, consistent action group, and PDF-label export (R4.9) isn't clearly
  placed among them either.
- **Root cause:** two layers both render their own export:
  - The **member analytics code** (`MemberPivotViews.tsx`) adds its own export buttons above the
    table (task 8.1, using `csvExport.ts`).
  - The **reused `PivotResultTable`** has its own built-in export button below the table (from the
    framework). Both target the same `PivotResult.data`.
  - "Export underlying data" calls the server's `pivotService.exportUnderlying` →
    `/api/pivot/export`, which is a MySQL/SQL path — the server doesn't know
    `data_source: 'members'` → fails.
- **Fix:**
  1. **Remove the below-table duplicate** — either suppress `PivotResultTable`'s built-in export
     (via a prop if available) or remove the analytics code's above-table export and keep only the
     framework's one.
  2. **Remove "Export underlying data"** — it only makes sense for the server SQL engine, not the
     client-side adapter.
  3. **Result: one consistent output-action group** (CSV export, PDF labels, mail) in one
     location — either above or below the table, not split across both. The design (C4) puts all
     output actions in the capability-gated `pivot-result-actions` slot; that slot should be the
     single home.

---

### F-009 — Pivot sets missing expected columns (address fields, birth date, membership duration, age, date joined)
- **Category:** functional
- **Requirement:** R4.2 (predefined sets), R4.8 (filtered list = chosen columns)
- **Where:** `memberPivotPresets.ts` preset definitions + `memberPivotAdapter.ts` list projection
- **Description:** Multiple presets (birthday/birth-month, jubilees, new members) are missing
  columns the user expects: address fields (street, postal code, city, country), birth date,
  date joined, membership duration, age. Each list-kind preset needs a curated, meaningful
  column set — not just the filter field.
- **Root cause:** same as F-006 — list presets don't specify their columns. Even once F-006's
  full-projection is fixed, each preset must define which columns are relevant for its use case:
  - **Birthday/birth-month:** name, email, birthday, birth_month, region, address fields
  - **Jubilees:** name, email, years_member, joined_date, age, region, address fields
  - **New members:** name, email, joined_date, membership_type, region, address fields
  - **Cancellations:** name, email, cancellation_date, joined_date, region
- **Fix:** add a `listColumns: string[]` to `MemberPivotPreset` for list-kind presets, defining
  the curated column set per preset. The adapter reads `listColumns` for list-kind sets instead
  of falling through to the raw dump.

---

### F-010 — No way to filter pivot sets by date range (e.g. "joined after" for new members)
- **Category:** functional (enhancement)
- **Requirement:** R4.2 (new members by joined date)
- **Where:** `memberPivotPresets.ts` "new-members" preset + `MemberPivotViews.tsx` filter UI
- **Description:** The "New members (Joined date)" preset has no date-range filter (e.g. "joined
  after 2025-01" or a year/month selector). It shows all members. A useful new-members list needs
  at minimum a join-date start filter. Could also be a calculated field `joined_year_month`
  (YYYY-MM) that works as a selectable filter for both current and historical views.
- **Recommendation:** add a date/year-month filter control on the new-members preset (and
  potentially a `joined_year` / `joined_year_month` calculated field in the module to support it
  as a groupable/filterable dimension). This mirrors how the jubilee preset has a year selector.

---

### F-011 — "Create a new set" fails silently ("Failed to save the set")
- **Category:** blocker
- **Requirement:** R4.4 (user-defined + saved sets), R4.8 (filtered-list sets are first-class
  and savable)
- **Where:** `MemberFieldPicker.tsx` → `pivotService.savePivotModel` → backend
  `pivot_routes.py` → `PivotModelStore.save_model` → `validate_definition`
  (`backend/src/services/pivot_model_store.py`)
- **Description:** Creating and saving a new user-defined set fails with a generic "Failed to
  save the set" message, no error detail shown.
- **Root cause (confirmed):** `PivotModelStore.validate_definition` requires **`group_columns`
  to be a non-empty list** and **`aggregate_measures` to be a non-empty list**. This was written
  for the SQL pivot engine where every model is a group-by aggregate. But member **filtered-list**
  sets (R4.8: `kind: 'list'`) have `group_columns: []` and `aggregate_measures: []` — both empty.
  So the backend `validate_definition` raises `ValueError("'group_columns' must be a non-empty
  list")` and the route returns 400, which the frontend renders as the generic "Failed to save"
  toast.
  Storage itself is fine: `pivot_models` MySQL table, tenant-isolated via `administration`,
  accepts any `data_source` string (no source-registry validation). The only gate is the
  validation that assumes every model is a group-by aggregate.
- **Fix:** relax `validate_definition` to accept empty `group_columns` and `aggregate_measures`
  when the model represents a filtered-list set (e.g. when a `kind` or `mode` field is present in
  the definition, or simply allow both to be empty lists without rejecting). This must not break
  the existing FIN/STR pivot models — those always have non-empty group columns + measures, so
  relaxing the "must be non-empty" to "must be a list (may be empty)" is safe. Also surface the
  actual backend error message in the frontend toast instead of the generic "Failed to save".

---

### F-012 — Saved sets persist on the Flask/MySQL plane — violates the SAM/DynamoDB module boundary
- **Category:** blocker (architectural)
- **Requirement:** R4.4 (saved sets), R6.2 (two-plane architecture), steering 20 / 35 (SAM module
  owns its data in DynamoDB; `tenant_id` + IAM `LeadingKeys` tenancy, NOT the Flask
  `administration` model)
- **Where:** `MemberPivotViews.tsx` / `MemberFieldPicker.tsx` → `pivotService` →
  `backend/src/routes/pivot_routes.py` → `PivotModelStore` (`pivot_models` MySQL table)
- **Description:** Member analytics saved sets are persisted in the **Flask/MySQL `pivot_models`
  table** (the FIN/STR pivot store), reached via the Flask `/api/pivot/models` CRUD. The Members
  module is a **SAM/DynamoDB module** — its data belongs in DynamoDB, keyed by `tenant_id`, reached
  through the Members Lambda. Storing member-specific analytics config on the Flask plane:
  - crosses the plane boundary (steering 20/35; R6.2) — a SAM module feature coupled to Flask
    persistence;
  - mixes tenancy models (`administration` column vs. `tenant_id` + partition key / IAM
    `LeadingKeys`);
  - couples the module to a store built for FIN/STR, which forced the aggregate-only validation
    that breaks filtered-list sets (F-011).
  This was a design shortcut ("reuse the existing pivot model CRUD") that should have been flagged
  as a plane violation. The predefined presets are code/config and are fine; it is the **saved
  (user-defined) sets** that are mis-placed.
- **Fix (Option A — chosen):** persist saved member analytics sets in **DynamoDB, inside the
  Members module**. Add a saved-set item type to the `sam-members` table (or a sibling analytics
  table), keyed by `tenant_id` + set id, with CRUD routes on the Members Lambda
  (`POST/GET/PUT/DELETE /members/analytics-sets`), using the module's standard `tenant_id`
  tenancy. The frontend saves/loads/lists/deletes via the **Members API**
  (`membersApiService`), NOT the Flask `pivotService`. This also naturally fixes F-011 (the module
  store defines its own validation — filtered-list sets with empty group/measure are first-class).
- **Keep extractable (forward-looking, see Design note below):** the generic parts — the saved-set
  shape, the CRUD pattern, the client pivot/list adapter, the result/export — SHALL be written
  module-agnostic so they can be lifted into a shared `sam/shared/analytics/` library when the
  **events** / **webshop** modules migrate to the SAM plane (planned post-members-production). Do
  NOT build the shared abstraction now (one consumer); extract on the second consumer.

### F-013 — Steering gap: strengthen `35-sam-module-architecture-sam.md` so F-012 can't recur
- **Category:** process / steering (not a code bug — prevents recurrence for events/webshop)
- **Requirement:** steering `35-sam-module-architecture-sam.md`, `20-platform-architecture.md`
- **Where:** `.kiro/steering/35-sam-module-architecture-sam.md`
- **Description:** The steering **already** states the principles F-012 violated (SAM modules
  persist to DynamoDB; the repository is the only persistence touch-point; each module owns its
  table; React never talks to another plane's store). So F-012 was a failure to **follow**
  existing steering, not a missing rule. However, two targeted additions would close the gaps that
  let the shortcut through and guide the planned events/webshop migrations:
  1. **Explicit cross-plane-storage prohibition.** The current rules 4–5 imply it, but never name
     the specific anti-pattern that occurred: a SAM-module feature persisting its data via a
     **Flask/MySQL endpoint** (the `pivot_models` store) to reuse an existing table. Add a sentence
     making it explicit — e.g. *"A SAM module's data, including feature/config data such as saved
     analytics sets, is persisted by its own repository in its own DynamoDB table and reached
     through its own Lambda. It must NEVER be stored via a Flask/MySQL endpoint, even to reuse an
     existing table — reuse the client/engine CODE, never the other plane's STORAGE."*
  2. **Shared SAM application-capability pattern.** The "Why generic" section covers reusing the
     edge/tenancy and `sam/shared` for auth, but not a generic **application capability** shared
     across modules (analytics: adapter, saved-set CRUD, result/export). Add a short subsection:
     a generic capability's CODE may be shared via a `sam/shared/<capability>/` library, but each
     module owns its DATA (its own DynamoDB table, `tenant_id` tenancy) — never a shared
     cross-module table with a module discriminator. Build per-module first; extract to
     `sam/shared/` on the SECOND consumer (rule of three).
- **Fix:** make the two additions above to `35-sam-module-architecture-sam.md`. Scoped additions,
  not a rewrite — the core layering is already correct.
- **Note:** do this as part of the fix batch (it informs how F-012 is built), but it is a steering
  edit, not feature code.

---

## Design note — SAM analytics as a future shared capability (NOT built now)

Events and webshop (currently single-tenant in the h-dcn package) are planned to migrate to the
myAdmin SAM plane **after** the Members module is production-ready. They will want the same
analytics machinery (saved sets, pivot/list adapter, violins, CSV/PDF/mail). To avoid
re-implementing it per module:

- **Generic engine (reuse target):** saved-set shape + CRUD pattern, the client-side pivot/list
  adapter (`memberPivotAdapter`), the result shape + `PivotResultTable` usage, CSV export, the
  extracted `ViolinChart` + `violinStats`. None of this is members-specific.
- **Module binding (stays per-module):** the field config / resolver, the predefined presets
  (jubilees/clubblad are members-only), the DynamoDB table + `tenant_id` tenancy, scope rules.
- **Sequencing (rule-of-three, pragmatic):** build member analytics now with the generic engine in
  **module-agnostic files with a clean seam** (no `members`-specific logic in the adapter / set
  CRUD / result / export). Do **not** build a `sam/shared/analytics/` abstraction yet — there is
  one consumer. When the **second** SAM module (events) needs it, **extract** the engine into a
  shared SAM library and have both modules consume it. Recorded here so the member build is
  structured for that extraction and the next module reuses rather than re-implements.
- **Storage shape (Shape 1 — per-module ownership):** each module owns its own saved-set storage
  in its own DynamoDB table, keyed by `tenant_id` — NOT a single shared `sam-analytics` table with
  a module discriminator (that would recreate the cross-cutting coupling this finding corrects).
  The *code* is shared; the *data* stays module-owned.

---

### F-014 — Not all 8 promised presets appear in the Pivot Views dropdown
- **Category:** functional (needs one observation to split blocker vs. expected-degradation)
- **Requirement:** R4.2 (the 8 predefined sets), R4.3 (role-backed sets offered only when their
  role resolves — "hidden/disabled with a clear reason")
- **Where:** `memberPivotPresets.ts` (`getAvailablePresets` / `presetFieldsPresent` /
  `materializePreset`) + the tenant's analytics `field_roles` config (authored in
  `MembersConfigEditor` Analytics tab)
- **Promised sets (R4.2):** Membership types · Birthday/birth-month · Jubilees · New members ·
  Cancellations · Clubblad paper/country · Clubblad digital · Referral source.
- **Context (confirmed by code read):** the analytics config authoring path IS built —
  `FieldConfig.analytics` is served (`field_resolver.py`), projected
  (`projection_config_reader.py`), and the configurator has the Analytics tab (jubilee rule /
  field roles / address mapping). So role resolution works; the question is availability.
- **Two causes, split by observation (NEED: which presets show now?):**
  - **(a) Expected degradation — the 4 role-backed sets are hidden** (Cancellations, Clubblad
    paper, Clubblad digital, Referral source) because the tenant has not yet mapped their
    `field_roles` in the Analytics config tab. Per R4.3 this is correct behavior, BUT R4.3 says
    "hidden/**disabled with a clear reason**" — the current `getAvailablePresets` OMITS them
    entirely (no reason shown), so the user can't tell they exist-but-need-config. **Finding:**
    surface unavailable role-backed presets as disabled entries with a reason ("needs the
    cancellation-date field mapped in Members config → Analytics"), rather than silently omitting
    them.
  - **(b) Real bug — one of the 4 always-available sets is missing** (Membership types /
    Birthday-birth-month / Jubilees / New members). These depend only on fixed/calculated keys
    (`membership_type`, `birth_month`, `years_member`, `joined_date`). If any is missing,
    `presetFieldsPresent` isn't finding the key in `fieldConfig.fields` — either the key isn't in
    the served config, or a key-name mismatch (e.g. the calculated field is `birth_month` vs. the
    preset expecting another key). **Finding:** confirm the served `fieldConfig.fields` contains
    these keys; fix the preset key or the field config so the 4 base sets always resolve.
- **Action needed from reviewer:** list exactly which presets appear in the dropdown now. That
  determines whether this is (a) only (config/UX), (b) only (bug), or both.
- **Fix:**
  1. (always) implement R4.3's "disabled with a reason" for unavailable role-backed presets
     instead of omitting them — so all 8 are discoverable, with the 4 role-backed ones showing
     what config they need.
  2. (if any base set missing) fix the field-key resolution / preset key mismatch so the 4
     fixed/calculated sets always appear.
  3. document that mapping the 4 roles in Members config → Analytics is what enables the role-backed
     sets (ties to F-012: once saved sets + config are on the module/DynamoDB plane).

---

## Root cause summary

| Root cause | Findings | Fix |
| --- | --- | --- |
| Flat key read misses nested calculated fields — need `valueFor(row, group, key)` | F-003, F-005 | Use `valueFor` with `groupForKey(fieldConfig, key)` wherever a calculated/fixed field is read |
| List-kind presets have no column spec → raw dump with system cols + [object Object] | F-006, F-009 | Add `listColumns` per preset; adapter projects through them via `valueFor` |
| "Export underlying data" calls the server SQL path which doesn't know `members` | F-008 | Remove/hide that button for member analytics |
| Saved sets on Flask `pivot_models` — plane violation; also forced the aggregate-only validation | F-011, F-012 | **Option A:** move saved-set CRUD to the Members Lambda / DynamoDB (`tenant_id`); frontend uses the Members API. Fixes F-011 as a consequence. |
| Analytics page not in the Members function-block nav | F-002 | Wire the route into the Members nav group |
| No date-range filter on the new-members preset | F-010 | Add a date/year-month filter control |
| Overview doesn't show membership-type breakdown | F-004 | Add per-type count (R2.1 MAY) |
| Pivot result table filters only on some columns | F-007 | Configure filterable columns for member list results |

---

## Fix log

| Finding | Fix summary | Verified |
| --- | --- | --- |
| F-001 | `getCurrentUserTenants` (`authService.ts`) now gates `JSON.parse` on a JSON-looking value (starts with `[`/`{`): a plain single-tenant string ("h-dcn") takes a quiet fast path returning `[value]` with NO `console.warn`; a genuinely malformed JSON-looking value still warns (worth surfacing). Return values unchanged for every input. Added 6 paired tests to `authService.test.ts` (9/9 pass). Frontend-only (local). | ☑ |
| F-002 | **Already resolved in the working tree** (verified, no change needed). `MainMenu.tsx` renders the "📊 Analyse" nav button (`setCurrentPage('member-analytics')`, label `members:analytics.navLabel`) as a sibling directly below the "Leden Overzicht" button in the Members function block, gated by `hasMEMBERS` + `Members_Read`/`Members_CRUD`. Route `case 'member-analytics'` is in `App.tsx` with the same roles as the table; `member-analytics` is in the `PageType` union, lazy-imported, and deep-linked at `/leden/analyse`. The finding reflected a pre-wiring state. | ☑ (already wired) |
| F-003 | `MemberOverviewStats` now reads `age`/`years_member` via the shared `valueFor(row, field.group, key)` nested-first accessor instead of flat `row['age']`. Added `groupForKey(fieldConfig, key)` to `fieldValue.ts`. Avg-age + avg-years-member cards now resolve from the nested buckets (`personal.age`, `membership.years_member`); new nested-row regression test. Frontend-only (local). | ☑ |
| F-004 | Added a per-membership-type breakdown to `MemberOverviewStats` (R2.1 MAY): counts members grouped by the resolved `membership_type` value (read via `valueFor`/`groupForKey`, nested-first), sorted count-desc/label-asc, rendered as a type→count card below the stat cards with a bilingual heading (`analytics.overview.stats.membersPerType`). Omitted when the field is absent (R2.5). New component tests. Frontend-only (local). | ☑ |
| F-005 | `MemberDistributions.buildMetricData` now takes `fieldConfig` and reads the metric + group-by value via `valueFor(row, groupForKey(fieldConfig, key), key)` instead of flat `row[metricKey]`. The age/years-member violins now get their nested calculated values (no more false "not enough data"); new nested-row + nested-group-by regression tests. Frontend-only (local). | ☑ |
| F-006 | Adapter's filtered-list no longer raw-dumps `{...row}`. New precedence: `config.listColumns` → measure columns → `meaningfulFieldKeys(fieldConfig)` fallback (visible, non-system fields only, projected via `valueFor`). `SYSTEM_LIST_KEYS` excludes `overlay`/`personal`/`membership`/`tenant_id`/`sk`/`member_id`/… so no system columns and no `[object Object]`. Added `listColumns` to `PivotConfig` + round-trip in `pivotService` converters (additive; SQL framework ignores it). New adapter regression tests. Frontend-only (local). | ☑ |
| F-007 | Root cause: `useColumnFilters` seeds its filter-key state via a one-time lazy initializer and never re-synced, so when the same mounted `PivotResultTable` is reused across Executes with different columns, columns absent from the stale `filters` got `filterValue===undefined` → `FilterableHeader` rendered no input ("only Membership type has a filter"). Fix: added a key-set reconcile effect to `useColumnFilters` (adds new keys, drops removed, preserves surviving values; no-op when keys unchanged). Shared-framework fix — benefits every filterable table; FIN/STR/ZZP unaffected (stable columns). 3 new regression tests; full filter-framework + PivotResultTable suites green. Frontend-only (local). | ☑ |
| F-008 | Added opt-in `hideExportMenu` prop to the framework `PivotResultTable` (default false → FIN/STR unchanged); `MemberPivotViews` sets it, so the framework's built-in two-option menu (incl. the broken "Export underlying data" → Flask SQL `exportUnderlying`, which fails for the client-side members adapter) is suppressed. Member Analytics now shows ONE output-action group (CSV / PDF labels / mail) in the `pivot-result-actions` slot. New `PivotResultTable` suppression test. Frontend-only (local). | ☑ |
| F-009 | Each list-kind preset now carries curated `listColumns`: birthday→(name,email,birthday,birth_month,region,+address); jubilees→(…years_member,joined_date,age,…); new-members→(…joined_date,membership_type,…); cancellations→(…cancellation_date,joined_date,region); clubblad-digital→(…role field,…). `materializePreset` substitutes role placeholders inside `listColumns` too (cancellation_date/clubblad_digital → tenant key). Address columns read via `valueFor` so an unmapped key renders blank, not a crash. New preset tests. Frontend-only (local). | ☑ |
| F-010 | Added a "joined since <year>" selector to the New-members preset, mirroring the jubilee year selector: new `analyticsConfig` helpers (`candidateJoinedYears` = current year back ~15, `selectedJoinedAfterYear`, `applyJoinedAfterFilter` — keeps members whose `joined_date` year ≥ chosen year, read via `valueFor`, inclusive); `usesJoinedAfterFilter` flag on the preset; `MemberPivotViews` shows the selector for new-members and writes the year into the set's definition filters (travels with a saved set, R4.4). i18n keys `joinedAfter`/`joinedAfterPlaceholder` (nl+en). New config + component tests. Frontend-only (local). | ☑ |
| F-011 | Resolved by F-012's module-side store: the Members-module analytics-set validation ACCEPTS empty `group_columns`/`aggregate_measures`, so filtered-list sets are first-class (the Flask aggregate-only gate is out of the path entirely). Backend `test_analytics_set_routes.py` asserts a list set with empty group+measures saves OK; frontend `MemberFieldPicker.test.tsx` asserts a no-group-column set saves with `kind:'list'`. | ☑ |
| F-012 | **Spec corrected** (R4/R4.1/R4.4/R4.4b, design C4 + decision table + component map). **Backend (DONE + tested):** new DynamoDB item type (`sk=analyticsset#<id>`, `tenant_id` tenancy) + Members Lambda CRUD (`POST/GET/GET{id}/PUT/DELETE /members/analytics-sets`) mirroring the membership-type catalog — entity `analytics_set.py`, `AnalyticsSetsMixin`, repository Protocol+Dynamo+stub, routes (before `/members/{member_id}`), dispatch, app exception mapping, error codes. 32 new tests + catalog/repository/tenant-invariant regression green. No `sam/shared/analytics/` built (rule of three). **Frontend (DONE + tested):** `membersApiService` analytics-set methods (`list/get/save/update/delete`, reusing `toBackendConfig`/`fromBackendConfig`, backend `set_id`→string `id`); `MemberPivotViews` + `MemberFieldPicker` switched off `pivotService` onto the Members API (string ids, no `data_source` filter — the Lambda returns only this tenant's member sets). tsc clean; 39 component tests pass. **Deployed:** pushed to `test` (commit `ea6f3fd1`) → `Deploy SAM Members` workflow `completed success`; `test-sam-members` stack live with `/members/analytics-sets`. Frontend `.env.local` already targets the test Members API, so `npm start` exercises it end-to-end. | ☑ (live in test) |
| F-013 | Added rule 5a (SAM data never persisted via another plane's storage endpoint — the F-012 anti-pattern named explicitly) + "Shared SAM application-capability pattern" subsection (CODE shareable via `sam/shared/<capability>/`, DATA stays per-module, extract on 2nd consumer) to `35-sam-module-architecture-sam.md`. | ☑ |
| F-014 | **Reframed after reviewer observation — NOT a blocker.** Only the 4 always-available presets show (Membership types, Birthday/birth-month, Jubilees, New members); the 4 role-backed ones are hidden. BUT this is cosmetic: in **"New pivot set"** EVERY field — fixed ⊕ overlay (incl. `clubblad`) ⊕ calculated — is already selectable (`MemberFieldPicker.pickableFields` reads `fieldConfig.fields` directly, no role indirection), so a user can build + save a `clubblad == Papier` list TODAY with no mapping. The 4 role-backed **presets** are just pre-canned shortcuts for pivots the user can already build by hand; they stay hidden only because the generic preset code resolves its column via `fieldConfig.analytics.field_roles[role]`, which is empty (the field itself IS present/usable). Jubilees confirms the pattern: backed by calculated `years_member`, it shows + works with no mapping (the role mapping is optional sugar). **So:** (a) OPTIONAL UX — show the 4 role-backed presets disabled-with-reason (R4.3) so the shortcut is discoverable (`getPresetsWithAvailability` started). (b) The projection-writer gap (Flask→DynamoDB drops the `analytics` slice) only matters to light up those 4 shortcut buttons — it does NOT block any user-built pivot. Neither is required for the core use case. **NOT solved by, and not needed for, R11.** | ☐ optional (core use case already works via New pivot set) |

## Recommended fix order (by impact)

1. **F-003 + F-005** (same root cause: flat-key read) — fixes the Overview and Distributions, the
   two most visible areas. Small, targeted change.
2. **F-006 + F-009** (same root cause: list presets have no columns) — fixes the pivot list results
   from dumping raw rows. Requires adding `listColumns` to presets + adapter change.
3. **F-012 (+ F-011)** (saved-set storage) — the architectural correction: move saved-set CRUD to
   the Members Lambda / DynamoDB (Option A). This unblocks user-defined sets (F-011 falls out of
   it, since the module store defines its own validation that accepts filtered-list sets). Bigger
   than a bug fix — it adds module routes + a DynamoDB item type and switches the frontend from
   `pivotService` to the Members API for save/load/list/delete. Build the engine extractable (see
   Design note) but do not build the shared library yet.
4. **F-008** (export underlying data fails) — remove/hide the broken button.
5. **F-002** (nav wiring) — makes the page reachable from the Members function block.
6. **F-007** (filter-framework columns) — improves the result table UX.
7. **F-010** (date filter on new-members) — enhancement.
8. **F-004** (membership-type breakdown) — enhancement (MAY clause).
9. **F-001** (console noise) — cosmetic, pre-existing.



The pivot view if now rather confusing

There are 3 views to initiate a pivot
1) the origibal drop down (Select a set)

2) My preferred list showing the items I ahve selected and at each row a run button. However the run button does not ecxecute anything as before already reported. The arrows to up or down a row in my preferred list is a nice option

3) All sets in a similar table as 2) only sorted on pivot name and an indicator if it is in your preferred lsiut and the option to add the non-selected ones

Preferred solution:
- Put the my preferred list pivots (now in 2) in the 1) the origibal drop down
- Remove 2) from the pane
- The function all sets should be a button when clicked on shows all sets as is now and the button should be on the same row as Select a set (1)

please read .kiro\steering\41-shell-environment.md

Sorry you are  not accurate.  
Forgetting key elements, YES we are on npm start for the local changes. Only the sam plane requires a push to test. Yes we need to update all code to github as a fall back. 
From a functional req point of view:
a) my preferred pivots should be in the main Select a set dropdown pivot, without the prefab items (unless I have selected them)  Now they are both in
b) The total list of pivots (prfab and custiom made should be a button and use a modal (keeps the main pane clean) and the itenms in the long list of pivots should have a sderach column to filter, the pivots mst be alphabetically sorted


When a csv is exported the column names are the english ones and not the ones of tghe language of the user. This happened befor with tabke columns and that i solved now for the csbv export
