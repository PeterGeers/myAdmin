# Design Document

## Member Analytics — Design

- Requirements: `./requirements.md` (R1–R10, plus Acceptance Criteria / Success Metrics).
- Parent / field model (REUSE unchanged): `.kiro/specs/Members/s5c-members-runnable-in-spa/`
  (C-FIELDS, C-VIEW, C-SCOPE, C-SURFACE). This spec implements s5c's deferred **R10.1**.
- Steering: `20-platform-architecture`, `23-aws-accounts`, `31-backend-database-flask-mysql`,
  `32-frontend-ui`, `33/34` (testing), `35-sam-module-architecture-sam`, `42-local-dynamodb`.
- Grounding code (myAdmin, cited throughout):
  - Members data: `sam/members/handler/routes.py`, `sam/members/domain/_membership_reads.py`,
    `sam/members/domain/scope_access.py`, `frontend/src/services/membersApiService.ts`,
    `frontend/src/hooks/useMemberFieldConfig.ts`, `frontend/src/types/members.ts`.
  - Field model: `sam/members/domain/field_resolver.py`, `sam/members/domain/calculated_fields.py`,
    `sam/members/domain/fixed_fields.py`.
  - Violin reuse: `frontend/src/components/reports/BnbViolinsReport.tsx`,
    `frontend/src/components/PlotlyChart.tsx`.
  - Pivot reuse: `frontend/src/components/pivot/PivotViewsTab.tsx`,
    `frontend/src/components/pivot/usePivotConfig.ts`, `frontend/src/services/pivotService.ts`,
    `frontend/src/types/pivot.ts`.
  - Field configurator: `frontend/src/components/TenantAdmin/MembersConfig/MembersConfigEditor.tsx`,
    `frontend/src/services/membersConfigService.ts`.
  - CSV export: `frontend/src/utils/csvExport.ts`.
  - SES mail: `backend/src/services/ses_email_service.py`, `backend/src/services/invoice_email_service.py`,
    `backend/src/routes/tenant_admin_email.py`.
  - Filter framework: `frontend/src/hooks/useFilterableTable.ts`,
    `frontend/src/components/filters/FilterableHeader.tsx`.
- Prior-art reference (h-dcn workspace, read-only — paths relative to h-dcn root):
  - `frontend/src/components/reporting/AnalyticsSection.tsx` (overview + view-mode pattern).
  - `frontend/src/components/reporting/AddressLabelGenerator.tsx`,
    `frontend/src/services/AddressLabelService.ts` (jsPDF labels, Avery formats).
  - `frontend/src/components/reporting/ViolinPlotVisualization.tsx`,
    `frontend/src/services/AnalyticsService.ts` (behavioral ref for age/membership violins, NOT the
    charting library — see Charting-library caveat).

## Overview

Member Analytics is a **separate page** in the Members module, beside the member table-with-modals,
that fetches the scope-authorized member set, runs its **own filter**, and presents analytics across
three areas:

1. **Overview** — count, average age, average years-member (immediate on open).
2. **Distributions / Violins** — Plotly violins for age + years-member (lazy, on entering the area).
3. **Pivot Views** — predefined + user-saved sets (aggregate or filtered list), with three output
   actions: CSV, PDF labels, SES mail. A set runs on explicit Execute.

The design principle is **compose, don't rebuild**: the violin, pivot framework, field configurator,
filter framework, CSV export, and SES mail all exist; analytics composes them. New code is limited
to the analytics page/shell, the overview computation, a thin violin feeder, the client-side pivot
adapter, a small analytics-config slice in the field configurator, and the address-label generator
ported from h-dcn.

### Resolved decisions (from requirements)

| Decision | Choice | Requirement |
| --- | --- | --- |
| Placement | Separate page, sibling to Leden Overzicht (D1) | R1.1/R1.5 |
| Initial render | Overview-first; violins lazy; pivots on Execute (Model A) | R1.6 |
| Filter | Analytics page's own filter, self-contained (Option A) | R1.5/R5.1 |
| Pivot bridge | Option 2 — client-side adapter, reusing framework config/types/result-table (NOT the Flask saved-model CRUD — see C4 / F-012) | R4.1/D3 |
| Saved-set storage | **Option A — Members module owns it: DynamoDB, `tenant_id` tenancy, Members Lambda CRUD, reached via `membersApiService` (NOT Flask `pivotService`/`pivot_models`)** | R4.4/F-012 |
| Filtered-list sets | First-class; saved filter values travel with the set | R4.4/R4.8 |
| Exports | CSV (reuse `csvExport.ts`) + PDF labels (jsPDF, port h-dcn) + SES mail (reuse `SESEmailService`) | R4.9–R4.12 |
| Overlay-field semantics | Resolved via analytics config field-role mapping in the field configurator (D2) | R9.3/R4.3 |
| Jubilee rule | Tenant-configured in the field configurator (D2) | R9.2 |
| Data-volume ceiling | 6 MiB Lambda response limit; measured cap ≈ **3,700 members** (hard) / ≈ **2,970** (80% warning) for the heaviest-overlay tenant (h-dcn, ~1,692 B/record); detect-and-alert. `GET /members` is un-paginated + un-gzipped (task 10.3, see C8) | R7.1–R7.4 |
| Mail capability gate | `members:export` (same as CSV/PDF) | R4.12 |
| PII/audit | Exports/mail audit-logged; no PII in logs; BCC default for bulk mail | R8 |

### Scope and data flow

```
GET /members  (SAM module, scope-narrowed by resolve_scope_access/_in_scope)
   │  membersApiService.listMembers → flattenMember
   ▼
members: Member[]  ← the user's scope-authorized set (region subset or region-all)
   │  the Analytics PAGE fetches + builds memberRows itself (D1)
   ▼
useFilterableTable(memberRows)  →  processedData  ← the page's OWN filtered dataset (Option A)
   ├──► Overview stats       (R2 — count, avg age, avg years-member) [immediate]
   ├──► Violin distributions (R3 — age, years_member)                [lazy, on entering area]
   └──► Pivot/List adapter   (R4 — runs a set on Execute)            [explicit action]
         ├──► CSV export     (R4.9 — reuse csvExport.ts)
         ├──► PDF labels     (R4.9 — jsPDF, port h-dcn generator)
         └──► SES mail       (R4.12 — SESEmailService, optional attachment)

GET /members/field-config  →  FieldConfig  (+ analytics config: jubilee_rule, field_roles, address_mapping)
   └──► field/label/option discovery; preset degradation; address-line mapping
```

Every area reads from the same scope-authorized `members` (narrowed further by the page's own
filter). No area can surface an out-of-scope member (R5.3). The table page is a separate route and
shares no in-memory state with this page.

## Component map

| Piece | Verdict | Where |
| --- | --- | --- |
| Analytics page (route + shell) | **NEW** | `frontend/src/pages/MemberAnalyticsPage.tsx` |
| Members nav entry | **NEW (wiring)** | Members routing/nav, beside Leden Overzicht |
| Analytics panel (view switch, lazy areas) | **NEW** | `frontend/src/components/members/analytics/MemberAnalyticsPanel.tsx` |
| Overview stats | **NEW (small)** | `.../analytics/MemberOverviewStats.tsx` + `.../analytics/memberAggregations.ts` |
| Numeric parse helper (`toNumber`, `mean`) | **NEW (helper)** | `.../analytics/memberAggregations.ts` |
| Violin chart (generic, shared) | **EXTRACT + REUSE** | `frontend/src/components/charts/ViolinChart.tsx` (from `BnbViolinsReport.tsx`) |
| Violin stats helper | **EXTRACT + REUSE** | `frontend/src/components/charts/violinStats.ts` |
| Plotly `Plot` factory | **REUSE unchanged** | `frontend/src/components/PlotlyChart.tsx` |
| Pivot config types / result-table | **REUSE (presentation + types only)** | `frontend/src/types/pivot.ts`, `.../pivot/PivotResultTable.tsx` |
| Saved-set CRUD (storage) | **NEW — Members module (NOT Flask `pivotService`, F-012)** | Members Lambda `/members/analytics-sets` + DynamoDB `sam-members`; frontend `membersApiService` |
| Saved-set client calls | **NEW** | `membersApiService` analytics-set methods (replaces `pivotService` CRUD for members) |
| Client-side pivot/list adapter | **NEW** | `.../analytics/memberPivotAdapter.ts` |
| Predefined member sets (presets) | **NEW (config data)** | `.../analytics/memberPivotPresets.ts` |
| Field picker popup | **NEW (small)** | `.../analytics/MemberFieldPicker.tsx` |
| Address-label generator | **NEW (port from h-dcn)** | `.../analytics/AddressLabelGenerator.tsx` + `.../analytics/addressLabelService.ts` |
| Analytics config slice in configurator | **NEW (small)** | `MembersConfigEditor.tsx` (new Analytics tab) + param schema |
| Analytics config TS type on FieldConfig | **NEW (additive)** | `frontend/src/types/members.ts` |
| Analytics config in module param schema | **NEW (additive)** | SAM `members.*` param declaration + `GET /members/field-config` |
| CSV export | **REUSE unchanged** | `frontend/src/utils/csvExport.ts` |
| SES mail (send with attachment) | **REUSE** | `backend/src/services/ses_email_service.py`; new Flask route for member-mail |
| Audit logging of export/mail | **NEW (small)** | Flask audit trail (or extend existing logging) |
| Field config / `useMemberFieldConfig` | **REUSE unchanged** | `frontend/src/hooks/useMemberFieldConfig.ts` |
| Shared filter framework | **REUSE unchanged** | `frontend/src/hooks/useFilterableTable.ts` |
| Members read path + scope | **REUSE unchanged** | `sam/members/*` — no member read/write change |

### New dependency: jsPDF

The h-dcn label generator uses **jsPDF** for client-side PDF label generation. jsPDF is **not**
currently a myAdmin frontend dependency — it must be added (`npm install jspdf`, pinned version).
This is a PDF generation lib, NOT a charting library (R10.3 excludes new charting libraries, not PDF
generators), and it is the proven choice from the h-dcn reference (23 passing tests, handles 1500+
members). An exact-version pin goes in `frontend/package.json`.

## Components

### C1 — Analytics page + placement (R1, D1)

- **`MemberAnalyticsPage.tsx` (NEW page/route)** — a sibling to `MembersPage.tsx`, reached from its
  own Members nav entry. Dark-theme/orange Chakra per steering 32 and the `STRReports.tsx` /
  `FINReports.tsx` pattern.
- Fetches its own data (R1.5): `listMembers()` → `flattenMember` → `memberRows` and
  `getFieldConfig()` → `FieldConfig` (incl. analytics config). Mounts its own
  `useFilterableTable(memberRows)` with its own filter controls (Option A).
- Gate: `members:read` capability (R1.2).
- Three non-happy states rendered distinctly (R1.4): empty set → neutral; no analytics config →
  fixed/calculated areas work, config-dependent sets degrade with a reason; load failure → error
  with retry.
- **`MemberAnalyticsPanel.tsx`** — the view switch (one area visible at a time, h-dcn view-mode
  pattern). Receives `processedData`, full scoped `members`, `fieldConfig`, `language`,
  capabilities. Three lazy areas: Overview (default), Distributions, Pivot Views (R1.6).

### C2 — Overview stats (R2)

- **`memberAggregations.ts`** — pure, tested helpers:
  - `toNumber(value: unknown): number | null` — parses string-typed calculated fields (OQ3/D4).
  - `mean(values: number[]): number | null` — average over present values only.
  - `countExcluded(...)` — how many rows had absent/invalid input (R2.3).
- **`MemberOverviewStats.tsx`** — Chakra `Stat` cards (count, avg age, avg years-member) computed
  via `useMemo` over `processedData` (R2.2). Fields resolved from `fieldConfig` calculated entries;
  absent field → card omitted (R2.5). Labels bilingual (R2.4). MAY additionally show active count,
  top regions, members-per-type per the h-dcn parity (R2.1 MAY clause).
- Performance: < ~1s after rows loaded (R6.7).

### C3 — Violin distributions (R3) — extract then reuse

- **`frontend/src/components/charts/ViolinChart.tsx` (NEW, extracted from BNB):**
  ```ts
  export interface ViolinDatum { group: string; value: number }
  export interface ViolinChartProps {
    data: ViolinDatum[];
    metricLabel: string;
    groupLabel?: string;
    showStats?: boolean;  // quartile summary table (default true, R6.6 non-visual alternative)
  }
  ```
  Internals lifted verbatim from `BnbViolinsReport.tsx`: group into `Record<string, number[]>`,
  build Plotly `type: 'violin'` traces (box + meanline + KDE), lazy-load `Plot` via `<Suspense>`.
  **Charting-library caveat:** h-dcn uses Recharts/@visx; this spec reuses myAdmin's Plotly path
  per the backlog. h-dcn is the behavioral reference (age + years-member, grouped by region, with a
  violin/box/histogram toggle); the charting library is Plotly.
- **`frontend/src/components/charts/violinStats.ts` (NEW, extracted):**
  `violinStats(values: number[]): {count, min, q1, median, mean, q3, max, range}`.
- **`BnbViolinsReport.tsx` refactored** to import the shared `ViolinChart` + `violinStats`, mapping
  its `{listing, channel, value}` to `{group, value}`. Regression test proves BNB unchanged (R3.2).
- **`MemberDistributions.tsx`** — builds `ViolinDatum[]` for `age` and `years_member` from
  `processedData` via `toNumber` (R3.5), with optional group-by selector (region / membership_type /
  gender, from field config, R3.3). One `ViolinChart` per metric. Below-threshold → empty state
  (R3.6). Lazy: only renders when the Distributions area is visible (R1.6).

### C4 — Pivot/list views — client adapter reusing the framework (R4)

The pivot framework's **config / types / result-table** layers are reused; the **execution** is a
client adapter (D3, Option 2) and the **saved-set storage** is the Members module's own DynamoDB
plane (Option A, F-012 — NOT the Flask `pivot_models` CRUD).

**Reused unchanged (presentation + types only):**
- `PivotConfig`, `PivotModel`, `PivotModelSummary`, `AggregateMeasure`, `PivotResult`,
  `PivotColumnMeta` from `frontend/src/types/pivot.ts` (the `PivotConfig` shape is reused as the
  saved set's definition payload; it is persisted by the Members module, not the Flask store).
- `PivotResultTable` / `PivotResultTablePivoted` from `frontend/src/components/pivot/`.
- `csvExport.ts` for CSV export of results.

**NOT reused (F-012 — plane correction):** the Flask `pivotService` model CRUD
(`savePivotModel` / `listPivotModels` / `loadPivotModel` / `updatePivotModel` / `deletePivotModel`
on `/api/pivot/models`, MySQL `pivot_models`). Member saved-set CRUD lives on the Members module (see
below), because a SAM module must own its data in its own DynamoDB table (`tenant_id` tenancy),
reached through its own Lambda — never persisted via a Flask/MySQL endpoint even to reuse a table
(steering 35, R6.2).

**NEW — Members-module saved-set store (Option A, F-012/F-011):**
- **DynamoDB item** on the `sam-members` table: an analytics-set item keyed by `tenant_id` (PK
  partition) + a set sort key (e.g. `sk = ANALYTICS_SET#<setId>`), carrying `{ setId, name, kind,
  config: PivotConfig, created/updated metadata }`. Tenancy via the module's standard `tenant_id`
  partition + IAM `LeadingKeys` — the same enforcement every member item uses.
- **Members Lambda CRUD** (handler → domain service → repository, per steering 35):
  `POST /members/analytics-sets` (create), `GET /members/analytics-sets` (list for the active
  tenant), `GET /members/analytics-sets/{id}`, `PUT /members/analytics-sets/{id}` (update),
  `DELETE /members/analytics-sets/{id}`. The domain service owns validation — a **filtered-list set
  with empty `groupColumns` / `aggregateMeasures` is first-class** (no aggregate-only gate), which
  is what fixes F-011.
- **Frontend** reaches these through `membersApiService` (new
  `listAnalyticsSets` / `getAnalyticsSet` / `saveAnalyticsSet` / `updateAnalyticsSet` /
  `deleteAnalyticsSet`), NOT `pivotService`.
- **Extraction-friendly seam (Design note / F-012):** the saved-set shape, the CRUD service/repo
  pattern, the client adapter, and the result/export are written **module-agnostic** so they can be
  lifted into a shared `sam/shared/analytics/` library when the SECOND SAM module (events/webshop)
  needs them (rule of three). The shared library is **NOT built now** (one consumer); each module
  keeps owning its own DynamoDB table + `tenant_id` tenancy (data stays per-module; only code is
  shared later).

**NEW `memberPivotAdapter.ts`** — the client aggregation engine:
```ts
export function executeMemberPivot(
  rows: MemberRow[],
  config: PivotConfig,
  fieldConfig: FieldConfig,
): PivotResult;
```
Groups `rows` by `config.groupColumns` (keys resolved via field config, read with the existing
`valueFor(row, group, key)` accessor), computes each `aggregateMeasure` (COUNT / SUM / AVG / MIN /
MAX, parsing numeric strings via `toNumber`), emits `columns` as `PivotColumnMeta`. When
`groupColumns` is empty (a **filtered-list** set, R4.8), it returns the filtered rows as
`PivotResult.data` (column per chosen field, one row per member). Pure, unit-tested (R6.5).

**NEW `memberPivotPresets.ts`** — the predefined sets (R4.2). Each preset has:
```ts
interface MemberPivotPreset {
  key: string;
  label: LocalizedLabel;
  config: PivotConfig;               // dataSource 'members', groupColumns, measures, filters
  requiresFields?: string[];         // fixed/calculated keys
  requiresRoles?: AnalyticsRole[];   // resolved via fieldConfig.analytics.field_roles
  usesJubileeRule?: boolean;
  kind: 'count' | 'list';
}
```
A role-backed preset resolves its field via `fieldConfig.analytics.field_roles[role]`, then checks
presence in `fieldConfig.fields`. Unresolvable → hidden with reason (R4.3). Jubilee year selector
reads `fieldConfig.analytics.jubilee_rule` (default multiples-of-5).

| Preset | groupColumns | kind | field source |
| --- | --- | --- | --- |
| Members per type | `membership_type` | count | fixed — always |
| Birthday / birth month | `birth_month` | list | calculated — always |
| Jubilees | `years_member` | list | calculated + jubilee_rule |
| New members | `joined_date` year | list | fixed — always |
| Cancellations | role `cancellation_date` | list | role-mapped |
| Clubblad paper / country | `country` + role `clubblad_paper` | count | role-mapped |
| Clubblad digital | role `clubblad_digital` | list | role-mapped |
| Referral source | role `referral_source` × year | count | role-mapped |

**NEW `MemberFieldPicker.tsx`** — modal listing groupable/aggregatable fields from `fieldConfig`
(fixed ⊕ overlay ⊕ calculated), bilingual, for composing a user-defined `PivotConfig` (R4.5).
Predefined presets seed the picker as starting points (R4.6).

**NEW `MemberPivotViews.tsx`** — the sub-panel:
- Dropdown of [presets (R4.2)] + [saved member sets (from the Members API
  `listAnalyticsSets`, tenant-scoped)].
- Execute → `executeMemberPivot(processedData, config, fieldConfig)` → `PivotResultTable` (R4.7).
- Save / Save-as / Update / Delete (explicit, R4.4b) via `membersApiService` analytics-set calls —
  NOT `pivotService` (F-012).
- Saved sets persist their `PivotConfig.filters` (R4.4); the page's live filter is NOT baked in
  (R4.4a).

### C5 — Address-label generator (R4.9/R4.10) — port from h-dcn

Ports the h-dcn `AddressLabelGenerator.tsx` + `AddressLabelService.ts` (Avery-stock labels,
client-side jsPDF, 23 passing tests in h-dcn) into `frontend/src/components/members/analytics/`,
**generically + multi-tenant** (no h-dcn field literals).

- **`addressLabelService.ts`** — the ported service: PDF via jsPDF, label formats (Avery L7160/
  L7163/L7162/L7161 + Custom Large as shipped defaults), address formatting, member filtering
  (drops incomplete addresses, reports count), sorting (name/postcode/region), country handling
  (uppercase for international).
- **`AddressLabelGenerator.tsx`** — the ported component: format picker, style options (font 8–12pt,
  alignment, border, country toggle, start position), preview, PDF generate, CSV/XLSX export, print.
- **Multi-tenant field mapping:** h-dcn's `korte_naam`/`straat`/`postcode`/`woonplaats`/`land`/
  `regio` are replaced by **resolved field keys** from the tenant's `analytics.address_mapping` (R9
  / R4.10). Absent mapping → PDF-label export unavailable with a clear reason; CSV always available.
- **Accessibility:** preview is keyboard-navigable; label-count and page-count badges are text
  (R6.6).

### C6 — SES mail function (R4.12)

- **NEW Flask route** (e.g. `POST /api/members/mail-set`) — accepts the filtered member rows (or
  their IDs + a re-resolve), a subject/body, and optional attachment (CSV bytes / PDF bytes).
  Delegates to `SESEmailService.send_email_with_attachments`. Reuses the `tenant_admin_email.py`
  pattern.
- **Recipient resolution:** the member email field is resolved from `fieldConfig` /
  `analytics.field_roles` (R4.12), not hardcoded.
- **Safety (R8.4):** defaults to BCC; surfaces recipient count for confirmation before send.
- **Audit (R8.1):** every send is audit-logged (actor, time, set key, filter, recipient count,
  attachment kind). No PII in the log (R8.3).
- **Scope (R8.2):** the mail only reaches members in the rows the set resolved (scope-correct by
  construction since the rows came from the scope-narrowed `GET /members`).
- **SES quotas:** design notes the SES send-rate quotas and surfaces a clear error if rate-limited.
- **Transient artifacts (R8.5):** if a CSV/PDF is held server-side to attach, it is removed after
  send.

### C-CONFIG — Analytics config in the field configurator (R9, D2)

- **Authoring (frontend):** `MembersConfigEditor.tsx` gains a fifth tab ("Analytics") using the
  existing `MembersParamSubEditor` / `membersConfigService.ts` save-once path.
  - **`jubilee_rule`** — `{ years?: number[]; multiple_of?: number }`. Default when absent:
    `{ multiple_of: 5 }`.
  - **`field_roles`** — `Partial<Record<AnalyticsRole, string>>` mapping roles
    (`cancellation_date`, `referral_source`, `clubblad_paper`, `clubblad_digital`,
    `country_detail`) to resolvable field keys, via the configurator's existing
    `resolvableFieldKeys` picker.
  - **`address_mapping`** — which field keys fill name / street / postcode / city / country / region
    on a label. Picker offers only resolvable keys.
- **Serving (backend, additive):** declared on the `members.*` param schema, projected
  one-directionally, served on `GET /members/field-config` as `FieldConfig.analytics`:
  ```ts
  interface MemberAnalyticsConfig {
    jubilee_rule?: { years?: number[]; multiple_of?: number };
    field_roles?: Partial<Record<AnalyticsRole, string>>;
    address_mapping?: {
      name?: string; street?: string; postcode?: string;
      city?: string; country?: string; region?: string;
    };
  }
  ```
  This config block is additive (a new optional config block + its projection pass-through). It is
  one of **two** SAM-module touches in this feature; the other is the saved-set store (C4, F-012:
  the analytics-set item type + `/members/analytics-sets` CRUD on the Members Lambda). Both keep
  member data on the module's own DynamoDB plane rather than the Flask/MySQL plane.
- **Consumption (R9.5):** analytics reads the block as read-only tenant data. Absent → documented
  defaults (jubilee multiples-of-5; unmapped roles → their sets hidden; no address mapping → PDF
  labels unavailable; CSV always works).

### C7 — PII / privacy / audit (R8)

- **Audit logging (R8.1):** every CSV export, PDF-label generate, and SES mail send writes an audit
  record: `{ actor, timestamp, tenant, set_key, filter_summary, record_count, output_kind }`. The
  platform's existing audit/logging mechanism is reused (if available) or a lightweight member-
  analytics-audit table/log is created. Metadata only, no PII (R8.3).
- **BCC default + confirmation (R8.4):** the mail compose UI defaults to BCC and shows the recipient
  count; sending is a confirmed action (not a fire-and-forget click).
- **No artifact retention (R8.5):** a CSV/PDF held to attach to a mail is deleted after send; no
  silent accumulation.

### C8 — Data-volume guard (R7)

- The analytics page (or the `listMembers` call) measures the response size (e.g.
  `Content-Length` / `response.headers` or the serialized JSON byte length).
- At **≥ 80% of 6 MiB** → a user-visible warning banner + an operational log/metric (R7.3).
- At or over the limit (truncated / failed response) → the explicit "dataset too large" state; no
  partial aggregation (R7.4).
- Implemented in `frontend/src/components/members/analytics/dataVolumeGuard.ts` (task 10.2):
  `LIMIT_BYTES = 6 MiB = 6,291,456`, `WARNING_THRESHOLD_BYTES = 5,033,164` (80%), measured with
  `TextEncoder` (UTF-8) over the `JSON.stringify`'d member set.

#### Measured record cap (R7.2) — resolved (task 10.3)

The supported Option-2 volume is a **measured cap derived from the real serialized record size
against the 6 MiB limit** (R7.2), not a guessed row count. The two inputs R7.2 requires are now
established:

- **Per-record serialized JSON size — heaviest-overlay tenant.** The heaviest overlay in the
  codebase is **h-dcn** (`scripts/onboarding/members/h-dcn/members_config.json`): the fixed base
  (personal + membership) ⊕ **15 overlay fields** (`region`, `magazine_pref`, `newsletter_pref`,
  `referral_source`, `motor_brand`, `motor_type`, `build_year`, `license_plate`, `iban`,
  `payment_method`, `notes`, `additional_info`, `deregistration_date`, `termination_date`) ⊕ the
  calculated fields enriched on read ⊕ the frontend `flattenMember` top-level aliases
  (`name`/`email`/`status`/`membership_type`/`member_number`/`membership_id`/`region`). A synthetic
  **near-worst-case** record (every fixed field present, all calculated fields enriched, all 15
  overlay fields populated with generous realistic values incl. the free-text
  `referral_source` / `notes` / `additional_info`) serializes to **≈ 1,692 bytes** (compact
  `JSON.stringify` / `json.dumps`, UTF-8 — identical ASCII-escaped since the record carries little
  non-ASCII). Real records are typically smaller (many overlay fields unset; ~58 org/contact rows
  and ~66% of members carry no email). Measurement script (synthetic, no production data):
  `.agent-output/measure_member_record.py`.
- **Pagination / gzip of `GET /members` — established from the code.**
  - **No pagination.** `list_members` (`sam/members/domain/_membership_reads.py`) returns the
    **entire** scope-filtered list in one response; the `GET /members` route
    (`sam/members/handler/routes.py`) declares no `limit`/`offset`/cursor params, and the frontend
    `listMembers()` (`frontend/src/services/membersApiService.ts`) fetches `/members` once with no
    paging. The whole scope-authorized set rides in a single response — exactly the set the 6 MiB
    guard measures.
  - **No gzip at the module code level.** The response shaper
    (`sam/members/handler/_http.py::_response`) emits a plain `json.dumps(...)` body with only
    `Content-Type: application/json` + CORS headers — **no `Content-Encoding`/gzip**. The REST API
    (`AWS::Serverless::Api` `MembersApi` in `sam/members/template.yaml`) sets **no
    `MinimumCompressionSize`**, so API Gateway does not gzip the integration response either.
    **Caveat:** any gzip applied by a layer not in this repo (e.g. a CloudFront distribution or a
    gateway setting changed out-of-band) would compress the wire transfer but would **not** relax
    the ceiling — the 6 MiB Lambda limit is measured on the **uncompressed** Lambda→API-Gateway
    payload, which is what the client-side guard also measures (`JSON.stringify` bytes). So the cap
    below holds regardless of transport compression.

- **Resulting measured cap (against the 6 MiB ceiling), heaviest-overlay record ≈ 1,692 B:**
  - **Hard cap (at 6 MiB = `LIMIT_BYTES`): ≈ 3,700 members** (3,716 incl. the `{"success":true,
    "data":[…]}` envelope + inter-element commas) → the explicit "dataset too large" state (R7.4).
  - **Warning cap (at 80% = `WARNING_THRESHOLD_BYTES`, 5,033,164 B): ≈ 2,970 members** (2,972) →
    the user-visible warning banner + operational signal (R7.3).

  This confirms the R7.2 provisional working figure (**~3,000–5,000 members per scope-authorized
  set**): the measured hard cap (~3,700) sits inside it and the warning fires at ~2,970, so Option 2
  (client-side aggregation) is viable for the current heaviest tenant with the detect-and-alert
  guard as the safety net. The authoritative gate stays **set-size-in-bytes vs. 6 MiB** (the
  byte-measured guard in `dataVolumeGuard.ts`), so these row figures are the human-readable
  translation of the byte ceiling, not a hard-coded limit — a lighter-overlay tenant fits
  proportionally more. If a scope-authorized set grows past the warning cap, ODI-1 (server-side
  aggregation / a paginated read) is the documented escalation (R7.5).

## Error handling

- Missing/absent calculated or overlay field → excluded from aggregation (`toNumber` → `null`),
  never a crash.
- Empty or zero-filtered set → each area renders a neutral empty state (R1.4).
- Preset with unresolvable role → hidden with bilingual reason, not empty-forever.
- No analytics config → fixed/calculated areas work; config-dependent sets degrade; not an error
  state.
- Field-config or member-list load failure → error state with retry, distinct from "empty" (R1.4).
- Saved-set CRUD failure (Members API `/members/analytics-sets`) → toast surfacing the module's
  actual error; predefined presets still usable.
- SES rate limit → clear error on the mail compose UI; the set result is not lost.
- Over-6-MiB response → the explicit over-limit banner; no silent partial (R7.4).

## Testing strategy (R6.5; steering 33/34)

- **Unit (pure helpers):** `toNumber`, `mean`, `countExcluded`; `violinStats` quartiles;
  `executeMemberPivot` (COUNT/SUM/AVG/MIN/MAX, numeric-string parse, group-by on nested `valueFor`
  keys, filtered-list mode with empty `groupColumns`); preset resolution/degradation (unmapped role
  → hidden; role→absent-key → hidden; fixed/calculated always present); jubilee selection (configured
  set, multiple-of, default); address formatting and incomplete-address filtering.
- **Config:** the new Analytics sub-editor saves `jubilee_rule` / `field_roles` /
  `address_mapping` and reference-validates; `GET /members/field-config` serves the `analytics`
  block (SAM test).
- **Component:** `MemberOverviewStats` recomputes on processedData change; `MemberDistributions`
  lazy-loads and renders empty state below threshold; `MemberPivotViews` lists presets + saved
  models, honors saved filters, does not bake the page filter; `AddressLabelGenerator` renders
  preview and generates PDF with the correct Avery dimensions.
- **Regression (extraction):** the extracted `ViolinChart` + `violinStats` reproduce the BNB stats
  for a fixed dataset — BNB behavior unchanged (R3.2).
- **Scope safety:** a scoped `members` subset → no area/export/mail surfaces a row outside it.
- **Audit:** export/mail actions produce an audit record with the correct metadata and no PII.
- **Accessibility:** keyboard walkthrough of controls; violin stats table present; color-not-sole-
  signal check on degradation/warning states.

## Open design items (non-blocking)

- **ODI-1 (scaling / Option 1):** if member volume outgrows client aggregation, add a module-side
  `POST /members/pivot` action (or a MySQL projection + SQL engine). Switchable without changing
  the reused config/result-table layers or the module's own saved-set store (R7.5). **Headroom (measured, task 10.3):** the
  heaviest-overlay tenant fits ≈ 3,700 members per scope-authorized set under the 6 MiB ceiling,
  with the 80% warning firing at ≈ 2,970 (see C8). Option 1 becomes the escalation only once a
  real scope-authorized set approaches that warning cap.
- **ODI-2 (analytics config param shape):** whether the analytics block is a new `members.analytics`
  param or a slice of an existing `members.*` param — pick whichever fits `parameter_schema.py`
  cleanly and keep the served `FieldConfig.analytics` shape stable.
- **ODI-3 (list-style set presentation):** list-kind presets (birthday/jubilee/new/cancellations)
  are row-level projections rather than pure aggregates; decide per set whether they render via the
  pivot result table (grouped count + drill) or a simple filtered-list table. Non-blocking; pick
  per set during implementation.
- **ODI-4 (SES rate/bounce):** document the SES send-rate quota for the myAdmin SES identity, and
  decide the batch-send strategy for large recipient lists (sequential with back-off, or a
  queue-based send).
