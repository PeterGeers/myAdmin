# Implementation Plan — Member Analytics

## Overview

A member-analytics surface for the Members module: an Overview summary, violin
distributions (extracted into a shared chart), and configurable pivot/list views with
CSV/PDF-label/SES-mail exports — all scope-authorized and tenant-isolated.

- Spec: `./requirements.md` (R1–R10 + Acceptance Criteria), `./design.md` (C1–C8 + C-CONFIG).
- Convention: each task is small, testable, and leaves the app building. Requirement and design-
  component refs in parentheses. Follow steering 32 (frontend), 33/34 (testing), 41 (shell/WSL).
- Ordering: pure helpers are built and tested before UI; the shared violin is extracted with no
  behavior change before new consumers use it; verification runs last.

## Tasks

### Phase 0 — Scaffolding + new dependency

- [x] 0.1 Create `frontend/src/components/members/analytics/` with a barrel `index.ts`, and
  `frontend/src/components/charts/` for the extracted violin. Create `frontend/src/pages/` entry
  for the new page.
  - _Requirements: R1.1 | Design: C1_

- [x] 0.2 Add **jsPDF** to the frontend (`npm install jspdf`, pin exact version in
  `package.json`). Confirm the build succeeds with the new dependency.
  - _Requirements: R4.9 | Design: C5, "New dependency: jsPDF"_

- [x] 0.3 Add i18n keys for the analytics surface to the existing `members` / `reports` namespace
  — bilingual `nl`/`en`: section titles (Overview / Distributions / Pivot Views), stat labels
  (count / avg age / avg years-member), empty states, preset names, export/mail labels,
  degradation reasons, over-limit warning. No hardcoded English.
  - _Requirements: R6.4 | Design: all components_

### Phase 1 — Pure helpers (tested first, no UI)

- [x] 1.1 `analytics/memberAggregations.ts`: `toNumber`, `mean`, `countExcluded`. Unit-test
  parsing of valid/absent/non-numeric, mean over present-only, excluded count.
  - _Requirements: R2.1, R2.3, R3.5 | Design: C2_

- [x] 1.2 `charts/violinStats.ts`: `violinStats(values) → {count, min, q1, median, mean, q3, max,
  range}`, lifted verbatim from BNB. Unit-test against a fixed dataset with known expected
  quartiles.
  - _Requirements: R3.4 | Design: C3_

### Phase 2 — Extract violin into shared component (no behavior change)

- [x] 2.1 Create `charts/ViolinChart.tsx` with generic props (`data: ViolinDatum[]`, `metricLabel`,
  `groupLabel?`, `showStats?`). Lift the Plotly violin-trace construction from
  `BnbViolinsReport.tsx`; render through the shared `PlotlyChart.tsx` `Plot` factory
  (lazy + `<Suspense>`). Use `violinStats` from 1.2 for the summary table. The stats table is the
  non-visual chart alternative (R6.6) and SHALL always be present when `showStats !== false`.
  - _Requirements: R3.2, R3.3, R3.4, R6.6 | Design: C3_

- [x] 2.2 Refactor `BnbViolinsReport.tsx` to import the shared `ViolinChart` + `violinStats`,
  mapping its `{listing, channel, value}` to `{group, value}` via `groupBy`. Add a regression
  test asserting the extracted path reproduces BNB stats for a fixed dataset.
  **STR BNB behavior must be unchanged.**
  - _Requirements: R3.2, R6.5 | Design: C3_

### Phase 3 — Analytics page beside the member table

- [x] 3.1 Create `MemberAnalyticsPage.tsx` as a **separate page/route** in the Members module.
  Add the Members nav entry beside Leden Overzicht. Gate the route behind `members:read`.
  Dark theme + orange primary per steering 32, `STRReports.tsx`/`FINReports.tsx` pattern.
  - _Requirements: R1.1, R1.2 | Design: C1_

- [x] 3.2 In the page, fetch the scope-authorized set: `listMembers()` → `memberRows` + 
  `getFieldConfig()` → `FieldConfig` (incl. analytics config). Mount **its own**
  `useFilterableTable(memberRows)` and render its own filter controls (Option A, self-contained).
  - _Requirements: R1.5, R5.1 | Design: C1_

- [x] 3.3 Create `analytics/MemberAnalyticsPanel.tsx` — the view switch (one area visible at a
  time, h-dcn view-mode pattern). Three lazy areas: Overview (default landing), Distributions,
  Pivot Views. Receives `processedData`, `members`, `fieldConfig`, `language`, capabilities.
  - _Requirements: R1.3, R1.6 | Design: C1_

- [x] 3.4 Implement the three non-happy states distinctly (R1.4): empty set → neutral; no analytics
  config → fixed/calculated areas work, config-dependent sets degrade with reason; load failure →
  error with retry affordance.
  - _Requirements: R1.4 | Design: C1_

### Phase 4 — Overview summary

- [x] 4.1 Create `analytics/MemberOverviewStats.tsx`: Chakra `Stat` cards (count, avg age, avg
  years-member) via `useMemo` over `processedData` using 1.1 helpers. Resolve fields from
  `fieldConfig` calculated entries; absent field → card omitted. Bilingual labels via
  `resolveLabel`. Optionally include active count, top regions, members-per-type (R2.1 MAY).
  - _Requirements: R2.1, R2.2, R2.4, R2.5, R6.7 | Design: C2_

- [x] 4.2 Surface excluded-count (rows with absent/invalid age/years-member) where it aids
  interpretation. Verify figures recompute live on filter/sort change.
  - _Requirements: R2.3, R2.2 | Design: C2_

### Phase 5 — Violin distributions

- [x] 5.1 Create `analytics/MemberDistributions.tsx`: build `ViolinDatum[]` for `age` and
  `years_member` from `processedData` via `toNumber`. Render one shared `ViolinChart` per metric
  with bilingual metric label. Neutral empty state below minimum-point threshold.
  **Lazy:** only mounts when the Distributions area is visible (R1.6).
  - _Requirements: R3.1, R3.5, R3.6 | Design: C3_

- [x] 5.2 Add optional **group-by** selector (region / membership_type / gender, discovered from
  `fieldConfig`), defaulting to a single ungrouped distribution.
  - _Requirements: R3.3, R6.1 | Design: C3_

### Phase 6 — Analytics config in the field configurator

- [x] 6.1 Declare the analytics config on the `members.*` param schema in the SAM module
  (additive: `jubilee_rule`, `field_roles`, `address_mapping`). Project one-directionally and
  serve on `GET /members/field-config` as `FieldConfig.analytics`. SAM test for the endpoint.
  - _Requirements: R9.1, R9.5, R6.2 | Design: C-CONFIG_

- [x] 6.2 Extend `frontend/src/types/members.ts` `FieldConfig` with
  `analytics?: MemberAnalyticsConfig` (jubilee_rule, field_roles, address_mapping).
  - _Requirements: R9.1 | Design: C-CONFIG_

- [x] 6.3 Add an **Analytics** tab to `MembersConfigEditor.tsx` (new `MembersParamSubEditor`
  slice): author `jubilee_rule` (configured set or multiple-of), `field_roles` (role → resolvable
  field key using the existing `resolvableFieldKeys` picker), and `address_mapping` (name / street
  / postcode / city / country / region → resolvable keys). Bilingual, save-once,
  reference-validated on Save.
  - _Requirements: R9.1, R9.2, R9.3, R9.4, R4.10 | Design: C-CONFIG_

- [x] 6.4 Unit-test config consumption helpers: resolve a role → key via `analytics.field_roles`
  + check presence in `fieldConfig.fields`; evaluate `jubilee_rule` (set vs. multiple-of vs.
  default multiples-of-5); resolve `address_mapping` fields.
  - _Requirements: R9.2, R9.3, R6.5 | Design: C-CONFIG_

### Phase 7 — Pivot/list views: client adapter + presets

- [x] 7.1 Implement `analytics/memberPivotAdapter.ts`:
  `executeMemberPivot(rows, config, fieldConfig) → PivotResult`. Group by `groupColumns` (via
  `valueFor`), compute COUNT/SUM/AVG/MIN/MAX (numeric via `toNumber`), emit `PivotColumnMeta`.
  When `groupColumns` is empty → filtered-list mode (one row per member, R4.8). Pure + unit-tested
  (grouping, each aggregate, filtered-list mode, numeric-string parse, nested-key read).
  - _Requirements: R4.1, R4.7, R4.8, R5.3, R6.5 | Design: C4_

- [x] 7.2 Implement `analytics/memberPivotPresets.ts`: predefined sets (members-per-type,
  birthday/birth-month, jubilees, new-members, cancellations, clubblad paper/country, clubblad
  digital, referral source) with bilingual labels, `requiresFields`, `requiresRoles`,
  `usesJubileeRule`. Materialize role-backed configs by substituting tenant key. Unit-test:
  role-backed presets hidden when unmapped/unresolvable; fixed/calculated always present.
  - _Requirements: R4.2, R4.3, R9.3, R6.1, R6.5 | Design: C4_

- [x] 7.3 Create `analytics/MemberPivotViews.tsx`: dropdown of [presets] + [saved member models
  from `pivotService.listPivotModels` filtered to `data_source === 'members'`]. Execute button →
  `executeMemberPivot` → reuse `PivotResultTable`. Shows on the Pivot Views area; nothing runs
  until explicit Execute (R1.6).
  - _Requirements: R4.1, R4.6, R4.7, R5.2 | Design: C4_

- [x] 7.4 Create `analytics/MemberFieldPicker.tsx`: modal listing groupable/aggregatable fields
  from `fieldConfig.fields` (fixed ⊕ overlay ⊕ calculated), bilingual. Compose a `PivotConfig`
  and save via `pivotService.savePivotModel` (`data_source: 'members'`). Presets seed the picker
  as starting points.
  - _Requirements: R4.4, R4.5, R4.6, R6.1 | Design: C4_

- [x] 7.5 Wire save / save-as / update / delete of member sets through the unchanged
  `/api/pivot/models` CRUD. Saved sets persist their `PivotConfig.filters` (R4.4); page's live
  filter NOT baked in (R4.4a); save is explicit (R4.4b). Confirm saved sets reappear next session,
  tenant-scoped.
  - _Requirements: R4.4, R4.4a, R4.4b | Design: C4_

- [x] 7.6 Jubilee year selector: reads `analytics.jubilee_rule`, renders a year filter on the
  Jubilees preset, and is savable as a definition filter (R4.4). Unit-test jubilee selection
  (configured set, multiple-of rule, default).
  - _Requirements: R4.2, R9.2, R6.5 | Design: C4_

### Phase 8 — Exports: CSV + PDF labels

- [x] 8.1 Wire CSV export on a pivot/list result: reuse `csvExport.ts`, gated by
  `members:export`. Available for both aggregate and filtered-list results.
  - _Requirements: R4.9, R4.11 | Design: C4_

- [x] 8.2 Port `AddressLabelGenerator.tsx` + `addressLabelService.ts` from h-dcn
  (`frontend/src/components/reporting/` + `frontend/src/services/`) into
  `frontend/src/components/members/analytics/`, generically + multi-tenant. Replace h-dcn
  field literals (`korte_naam`, `straat`, etc.) with resolved keys from
  `analytics.address_mapping`. Ship the five standard Avery formats as defaults. Gated by
  `members:export`.
  - _Requirements: R4.9, R4.10, R4.11, R6.1 | Design: C5_

- [x] 8.3 Address-label tests: label-format grid calculations, address formatting from resolved
  field keys, incomplete-address filtering + count, jsPDF output (smoke test), start-position /
  sort-order. Verify the generator is unavailable (with reason) when `address_mapping` is absent.
  - _Requirements: R4.10, R6.5 | Design: C5_

### Phase 9 — SES mail function

- [x] 9.1 Create a Flask route (e.g. `POST /api/members/mail-set`) that accepts filtered member
  rows (or IDs + re-resolve), subject/body, optional CSV/PDF attachment bytes. Delegate to
  `SESEmailService.send_email_with_attachments`. Tenant-isolated, capability-gated by
  `members:export`. Pattern from `tenant_admin_email.py`.
  - _Requirements: R4.12 | Design: C6_

- [x] 9.2 Frontend mail compose UI on a filtered-list result: editable subject/body (bilingual
  template), optional attach CSV / attach PDF labels, BCC by default, recipient count shown for
  confirmation before send. Resolve the email field from `fieldConfig` / `analytics.field_roles`.
  - _Requirements: R4.12, R8.4 | Design: C6_

- [x] 9.3 Surface a clear error if SES rate-limits the send. Ensure transient artifacts (CSV/PDF
  held to attach) are removed after send (R8.5).
  - _Requirements: R4.12, R8.5 | Design: C6, ODI-4_

### Phase 10 — PII / audit + data-volume guard

- [x] 10.1 Implement audit logging for every CSV export, PDF-label generate, and SES mail send:
  `{ actor, timestamp, tenant, set_key, filter_summary, record_count, output_kind }`. Metadata
  only, no PII in logs. Reuse the platform's existing audit mechanism or create a lightweight
  analytics-audit log.
  - _Requirements: R8.1, R8.3 | Design: C7_

- [x] 10.2 Implement the data-volume guard: measure `GET /members` response size (byte length);
  at ≥ 80% of 6 MiB → user-visible warning banner + operational log/metric; at/over limit →
  explicit "dataset too large" state, no partial aggregation. Verify on a synthetic large payload.
  - _Requirements: R7.1, R7.3, R7.4 | Design: C8_

- [x] 10.3 Measure the actual per-record JSON size for the heaviest-overlay tenant; establish
  whether `GET /members` paginates/gzips; document the resulting measured cap (R7.2) in the
  design.
  - _Requirements: R7.2 | Design: C8_

### Phase 11 — Cross-cutting verification

- [x] 11.1 Scope-safety test: feed a scoped `members` subset → assert no analytics area, export,
  or mail surfaces a row outside it.
  - _Requirements: R5.3, R8.2 | Design: all_

- [x] 11.2 Memoization / perf pass: confirm Overview renders < ~1s after rows loaded; filter
  re-derive < ~100ms (beyond debounce); only the visible area recomputes on filter change (R1.6).
  - _Requirements: R6.7, R7.6 | Design: C2, C3, C4_

- [x] 11.3 Accessibility pass: controls keyboard-navigable (view switch, filters, set dropdown,
  Execute, export/mail buttons); color not the sole signal on degradation/warning states; violin
  stats table present as non-visual alternative.
  - _Requirements: R6.6 | Design: all_

- [x] 11.4 BNB regression: confirm the STR BNB violin report renders identically after the
  extraction (Phase 2) — its existing tests pass unmodified.
  - _Requirements: R3.2, R6.5 | Design: C3_

- [x] 11.5 Run the full frontend test suite and type-check; fix any regressions. Confirm the
  build is green.
  - _Requirements: R6.5 | Design: all_

### Phase 12 — Shared pivot library + per-user preferred lists (R11 / C9)

> Added post-review. Supersedes the Phase 7 "saved models via the Flask `pivotService`" approach:
> F-012 moved saved-set storage to the Members module's DynamoDB plane (the analytics-set CRUD is
> already built + deployed to `test`). This phase refines that into the two-layer model R11 settles
> — a tenant-shared set LIBRARY + a per-user PREFERRED LIST — keyed on the authenticated `sub`
> (user ≠ member, R11.1). SAM plane only; the Flask admin-config plane is untouched. Build the
> store/CRUD module-agnostic (extraction-friendly, no `sam/shared/analytics/` yet — F-013).

- [ ] 12.1 **Backend — set item `origin`/`created_by`.** Extend the `AnalyticsSetEntry` entity +
  the create/update domain service so a stored set carries `origin: 'user'` and `created_by`
  (the verified `sub`, attribution/audit only — NOT an access gate). Update
  `test_analytics_set_entity.py` / `test_analytics_set_routes.py`.
  - _Requirements: R11.2, R11.3 | Design: C9_

- [ ] 12.2 **Backend — any-of capability gate.** Add an optional `capabilities_any: tuple[str, ...]`
  to `RouteSpec`; the edge authorize step (`_authenticate_and_authorize`) passes when the caller
  holds ANY listed capability. Keep the single `capability` for existing routes. Unit-test the
  edge: a caller with only `members:export` passes an `export|write` route; a caller with neither
  is 403.
  - _Requirements: R11.3 | Design: C9_

- [ ] 12.3 **Backend — widen the set-CRUD gates.** `create_analytics_set` →
  `capabilities_any = (members:export, members:write)`; `update`/`delete_analytics_set` →
  `capabilities_any = (members:write, members:admin)`. Reads stay `members:read`. Route-level
  tests for each matrix cell (export-only create OK; read-only create 403; CRUD delete OK).
  - _Requirements: R11.3 | Design: C9_

- [ ] 12.4 **Backend — preferred-list item + CRUD.** New `PREFLIST#<sub>` DynamoDB item (one per
  user): ordered `refs: string[]` of tagged references (`preset:<key>` / `set:<id>`). New routes
  `GET /members/analytics-sets/preferred` + `PUT /members/analytics-sets/preferred`, keyed on
  `ctx.sub` (body carries no owner), declared BEFORE the `{set_id}` routes. Entity +
  repository + domain service + dispatch + app wiring, mirroring the analytics-set pattern. Gate:
  read = `members:read`; write = `capabilities_any (members:export, members:write)`. Tests:
  per-user isolation (one sub's list never returns another's), empty-when-unset, replace semantics.
  - _Requirements: R11.1, R11.2, R11.3, R11.7 | Design: C9_

- [ ] 12.5 **Frontend — preferred-list service.** Add `getPreferredList()` / `savePreferredList(refs)`
  to `membersApiService` (unwrap envelope; refs are tagged-ref strings). Types on
  `types/members.ts`.
  - _Requirements: R11.2, R11.5 | Design: C9_

- [ ] 12.6 **Frontend — preferred-list UI + shared library.** In `MemberPivotViews`: the set
  dropdown already lists the shared library (code presets + all tenant user sets — now visible to
  every user). Add a "my preferred sets" control (add / remove / reorder tagged refs), resolving
  `preset:<key>` via `getAvailablePresets` and `set:<id>` via the shared sets; skip refs that no
  longer resolve (R11.6). Show create per `canExport || canWrite`; show delete-shared-set per
  `canWrite || isAdmin`. Component tests for the capability gating + ref degradation.
  - _Requirements: R11.2, R11.3, R11.5, R11.6 | Design: C9_

- [ ] 12.7 **Verify + deploy.** Full SAM suite + ruff + `sam build` green; frontend tsc + affected
  vitest green. Commit the SAM-plane changes (+ `.kiro` docs) and push to `test` → the
  `Deploy SAM Members` workflow deploys `test-sam-members`. Frontend stays local (`npm start`
  against the test Members API). Confirm the deploy run concludes `success`.
  - _Requirements: R11.7 | Design: C9; steering 43-cicd-deploys, 35-sam-module-architecture-sam_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2", "0.3"] },
    { "id": 1, "tasks": ["1.1", "1.2", "6.1", "6.2"] },
    { "id": 2, "tasks": ["2.1", "6.3", "6.4"] },
    { "id": 3, "tasks": ["2.2", "3.1"] },
    { "id": 4, "tasks": ["3.2"] },
    { "id": 5, "tasks": ["3.3", "3.4"] },
    { "id": 6, "tasks": ["4.1", "4.2", "5.1", "7.1", "7.2"] },
    { "id": 7, "tasks": ["5.2", "7.3", "7.4", "7.6"] },
    { "id": 8, "tasks": ["7.5", "8.1", "8.2"] },
    { "id": 9, "tasks": ["8.3", "9.1"] },
    { "id": 10, "tasks": ["9.2", "9.3", "10.1", "10.2", "10.3"] },
    { "id": 11, "tasks": ["11.1", "11.2", "11.3", "11.4", "11.5"] },
    { "id": 12, "tasks": ["12.1", "12.2"] },
    { "id": 13, "tasks": ["12.3", "12.4"] },
    { "id": 14, "tasks": ["12.5", "12.6"] },
    { "id": 15, "tasks": ["12.7"] }
  ]
}
```

## Notes

### Open design items (non-blocking)

These are deferred *decisions*, not excluded work — each is resolved during the phase noted and
does not block the plan.

- **ODI-1 (scaling / Option 1):** a future module-side `POST /members/pivot` (or MySQL projection +
  SQL engine) — added only if member volume outgrows client-side (Option 2) aggregation. The
  config / result-table / saved-model layers stay switchable so it can be adopted later without
  rework (R7.5).
- **ODI-2 (analytics config param shape):** whether the analytics block is its own `members.analytics`
  param or a slice of an existing `members.*` param — pick whichever fits `parameter_schema.py`
  cleanly during Phase 6; keep the served `FieldConfig.analytics` shape stable.
- **ODI-3 (list-style set presentation):** list-kind presets are row-level projections, not pure
  aggregates — decide per set (during Phase 7) whether each renders via the pivot result table
  (grouped count + drill) or a simple filtered-list table.
- **ODI-4 (SES rate/bounce):** document the SES send-rate quota for the myAdmin SES identity and
  decide the batch-send strategy for large recipient lists (sequential with back-off, or
  queue-based) during Phase 9. Referenced by task 9.3.

### Out of scope

- AI analytics, server-side aggregation API, new charting libraries, member mutation from
  analytics, cross-tenant analytics, Google-Contacts mail flavor, authoring overlay fields (R10).
