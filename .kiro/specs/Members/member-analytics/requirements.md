# Requirements Document

## Member Analytics — an analytics section in Members Overview (Leden Overzicht)

- Status: **Draft** (requirements phase — check in before design)
- Origin: `.kiro/specs/myBacklog/member-analyicts.md` (promoted to a proper spec).
- Parent / design reference (REUSE, do not rebuild): the Members module as built in
  `.kiro/specs/Members/s5c-members-runnable-in-spa/` (its `design.md` C-FIELDS, C-VIEW,
  C-SCOPE, C-SURFACE are the authoritative field/scope/view model this spec builds on).
- This spec **is** the work s5c explicitly deferred in its **R10.1** ("Reporting … MUST later
  live in the Members SAM module, leveraging myAdmin's existing reporting toolkit — graphs,
  violins, pivots — rather than rebuilding it"). s5c left it cleanly addable; this spec adds it.
- Reuses (does not rebuild):
  - the **violin / Plotly toolkit** behind STR BNB Violin Charts
    (`frontend/src/components/reports/BnbViolinsReport.tsx`,
    `frontend/src/components/PlotlyChart.tsx`);
  - the **Dynamic Pivot Views** framework (`.kiro/specs/dynamic-pivot-views/`;
    `frontend/src/components/pivot/*`, `frontend/src/services/pivotService.ts`,
    `frontend/src/types/pivot.ts`, `backend/src/services/pivot_query_builder.py`);
  - the **Members surface** (`frontend/src/pages/MembersPage.tsx` — the member table with
    view/add/edit/delete modals), its field config (`GET /members/field-config` → `FieldConfig`,
    `frontend/src/hooks/useMemberFieldConfig.ts`), and the **shared filter framework**
    (`frontend/src/hooks/useFilterableTable.ts`, `frontend/src/components/filters/FilterableHeader.tsx`).
  - the **Members field configurator** — the Tenant-Admin typed editor
    (`frontend/src/components/TenantAdmin/MembersConfig/MembersConfigEditor.tsx` +
    `MembersParamSubEditor.tsx`, `frontend/src/services/membersConfigService.ts`) that authors the
    `members.*` tenant parameters (`field_overlay`, `scope_dimensions`, `view_contexts`). This spec
    adds an **analytics config slice** here so the tenant-specific semantics (jubilee rule, which
    overlay fields drive which analytics set) are authored as config, not hardcoded.
- Governing steering: `20-platform-architecture`, `23-aws-accounts`, `31-backend-database-flask-mysql`,
  `32-frontend-ui`, `33/34` (testing), `35-sam-module-architecture-sam`, `40-spec-workflow`,
  `41-shell-environment`, `42-local-dynamodb`.
- Grounding code (cited throughout):
  - Members data path: `sam/members/handler/routes.py`, `sam/members/domain/_membership_reads.py`
    (`list_members` / `export_members` / `_enrich_calculated`), `sam/members/domain/scope_access.py`
    (`resolve_scope_access`), `frontend/src/services/membersApiService.ts` (`listMembers` /
    `getFieldConfig` / `exportMembers`).
  - Field model: `sam/members/domain/field_resolver.py` (`FieldResolver`, `ResolvedField`,
    `FieldConfig`), `sam/members/domain/calculated_fields.py` (`age`, `years_member`,
    `application_year`, `birthday`, `birth_month`, `birth_year`, `birth_quarter`),
    `sam/members/domain/fixed_fields.py` (`birth_date`, `gender`, `country`, `status`,
    `membership_type`, `joined_date`), `frontend/src/types/members.ts`.
  - Reuse targets: `frontend/src/components/reports/BnbViolinsReport.tsx` (bespoke `ViolinChart`
    + inline quartile stats, to be extracted), `frontend/src/components/PlotlyChart.tsx`
    (shared `Plot` factory), `frontend/src/components/pivot/PivotViewsTab.tsx`,
    `frontend/src/components/pivot/usePivotConfig.ts`.
- **Prior-art reference (behavioral, in the separate `h-dcn` workspace — read-only, NOT a myAdmin
  dependency):** the h-dcn members portal already ships this feature set, which this spec ports
  **generically + multi-tenant** onto the myAdmin Members module. Paths are relative to the `h-dcn`
  workspace root (`frontend/src/components/reporting/`):
  - `AnalyticsSection.tsx` — the analytics dashboard (Overview: total/active members, average age,
    average membership years, top regions, membership types; Regional; Violin visualizations;
    Trends) — the behavioral template for R2/R3.
  - `AddressLabelGenerator.tsx` + `services/AddressLabelService.ts` (+
    `AddressLabelGenerator.README.md`) — the Adreslabels Generator: **client-side jsPDF**, Avery
    formats, style/sort/start-position options, address validation — the template for R4.9/R4.10.
  - `ViolinPlotVisualization.tsx` + `services/AnalyticsService.ts` — age/membership-years violins
    grouped by region with a violin/box/histogram toggle. **Caveat:** h-dcn renders these with
    **Recharts/@visx**, but this spec reuses the **myAdmin STR BNB Plotly** violin (per the backlog).
    So h-dcn is the behavioral reference (what to show), NOT the charting library to port (R3.2).
- **myAdmin mail capability (Flask plane — the real reuse for sending):**
  `backend/src/services/ses_email_service.py` (`SESEmailService.send_email` /
  `send_email_with_attachments` via SES `send_raw_email`), as already used by
  `backend/src/services/invoice_email_service.py` and `backend/src/routes/tenant_admin_email.py`
  (`POST /api/tenant-admin/send-email`). This is the capability R4.12 reuses for server-side sends
  with attachments.

## Introduction

The Members module today has a member **table view with modals** (Leden Overzicht — a
scope-filtered, parameter-driven table with per-column filters, sort, a small live statistics
strip, and view/add/edit/delete modals). It has no analytical view: no distribution charts, no
pivots, no "members per membership type / per country / per join-year" breakdowns, and no
jubilee / birthday / new-member / cancellation lists that administrators actually run the club on.

Member Analytics adds an **Analytics page in the Members module, beside the member table** — a
sibling page/route to Leden Overzicht (not a stacked tab on the table page) — that turns the
scoped member set into insight:

1. a compact **overview** (member count, average age, average years-member);
2. **violin distributions** of the calculated `age` and `years_member` fields, reusing the same
   violin tooling STR BNB reports use;
3. **pivot views** over the member set using the existing Dynamic Pivot Views framework — a set of
   **predefined** sets (members per type; birthday / birth-month lists; jubilees with a year
   selector; new members by join date; cancellations by cancellation date; clubblad paper per
   country; clubblad digital; referral source by year) **plus user-defined, savable** pivot/list
   sets;
4. **output actions** on a (filtered-list) set: **CSV export**, **PDF address labels** (ported from
   the h-dcn generator), and a **mail function** (server-side SES send with optional CSV/PDF
   attachment) — all scope-respecting.

The headline constraints: every view is computed over **the filtered member dataset** (the
analytics page's own row selector / column filters, mirroring the table's filter behavior) and/or
the pivot's own filters; everything is **generic and multi-tenant** (no `if tenant == …`,
dimensions and tenant-specific analytics semantics discovered from tenant config / the resolved
field config, scope always enforced server-side); and the implementation **reuses** the violin and
pivot toolkits rather than reinventing them.

Multi-tenant principle made concrete: the two tenant-specific semantics this feature needs — what a
**jubilee year** means, and which **overlay fields** back the clubblad / referral / cancellation
sets — are **authored in the Members field configurator** (the `members.*` params), so a tenant
configures them once and analytics reads that config. Nothing tenant-specific is hardcoded.

## Glossary

- **Members Overview / Leden Overzicht** — `frontend/src/pages/MembersPage.tsx`, the scoped member
  **table with modals**. The analytics surface is a **separate page beside it** in the Members
  module, not a tab on this page.
- **Analytics page** — the new sibling page/route in the Members module hosting the Overview,
  Distributions, and Pivot Views areas. It fetches and filters the scoped member set itself
  (reusing the same filter framework the table uses).
- **Members field configurator** — the Tenant-Admin typed editor
  (`frontend/src/components/TenantAdmin/MembersConfig/MembersConfigEditor.tsx`,
  `MembersParamSubEditor.tsx`, `frontend/src/services/membersConfigService.ts`) authoring the
  `members.*` tenant parameters. This spec adds an **analytics config slice** to it.
- **Analytics config** — the tenant-authored analytics semantics added to the `members.*` params
  via the field configurator: the **jubilee rule** (what counts as a jubilee year) and the
  **analytics field roles** (which overlay/field keys back the clubblad-paper / clubblad-digital /
  referral-source / cancellation-date sets). Projected and served alongside the field config so
  analytics reads it like any other tenant config (R6.1).
- **Filtered dataset (Analytics page's own filter)** — the rows after the Analytics page's **own**
  filter controls (`useFilterableTable` → `processedData`): `GET /members` returns the user's
  **scope-authorized** member set (a region subset, or region-all, per the user's scope grant,
  enforced server-side — see Scope), and the Analytics page's own per-column filters narrow that set
  further, client-side. The Analytics page is a **separate page** from the member table, so it does
  **not** inherit the table page's filter — its figures reflect **the analytics filter the user set
  on the analytics page**, applied within what the user is already authorized to see. (Option A:
  self-contained analytics filter, no cross-page filter state.)
- **Resolved field config** — `GET /members/field-config` → `FieldConfig` = platform **fixed** base
  ⊕ tenant **overlay** (origin `variable`) ⊕ **calculated** (derived, read-only) fields, each with
  `{nl,en}` labels, a storage `group`, a `type`, and a `functional_group`. Analytics field choices
  are **discovered from this config**, never hardcoded.
- **Calculated field** — a derived, never-stored field (`sam/members/domain/calculated_fields.py`):
  `age` (from `birth_date`), `years_member` (from `joined_date`), `application_year`, `birthday`,
  `birth_month`, `birth_year`, `birth_quarter`, `display_name`. Enriched onto each record on read.
  **Note:** these are typed `string` today (int computed then stringified) — numeric analytics must
  parse them.
- **Overlay-only dimension** — a field that exists **only if a tenant authored it** as an overlay
  field: `cancellation_date`, **referral source**, **clubblad** (paper/digital), **country** detail
  beyond the fixed `country`. Analytics MUST discover these from the field config and degrade
  gracefully when a tenant has not authored them.
- **Violin toolkit** — the Plotly-backed distribution chart used by STR BNB
  (`BnbViolinsReport.tsx`), rendered through the shared `PlotlyChart.tsx` `Plot` factory. The
  violin component itself is currently **bespoke/local** to the BNB report and must be **extracted**
  into a shared component to be reused here.
- **Dynamic Pivot Views** — the existing pivot framework (`PivotViewsTab`, `usePivotConfig`,
  `pivotService`, `PivotConfig`/`PivotModel`), backed by **server-side SQL** over a registered
  MySQL **table/view** in the Flask/MySQL plane, with per-tenant **saved models** (predefined +
  user-defined). Members data lives in **DynamoDB** (`sam-members`), not a MySQL view — bridging
  that gap is the central design decision (resolved as D3 — client-side pivot adapter).
- **Scope** — within-tenant partitioning (e.g. region). Enforced **server-side** by
  `resolve_scope_access` / `_in_scope`; `GET /members` returns only in-scope rows, so client-side
  analytics over those rows inherits scope with no extra work.
- **Set** — a saved or predefined analytics view in the Pivot Views area, in one of two kinds: an
  **aggregate** (group-by + count/sum/avg/min/max) or a **filtered list** (chosen member columns +
  saved filter values, no group-by). "Pivot set", "pivot/list set", and "set" are used
  interchangeably; the filtered-list kind is not strictly a pivot but shares the same saved-model
  mechanism (R4.8). A set carries its own definition filters (R4.4), distinct from the page's live
  filter (R4.4a).

## Guiding principles (settled — requirements enforce them)

- **Reuse before rebuild.** The violin chart and the pivot framework already exist and are proven
  in FIN/STR; Member Analytics composes them. Net-new UI is limited to the analytics shell, the
  overview strip, and the small amount of glue each toolkit needs. (Steering 32; s5c R10.1.)
- **Filtered-dataset-driven (own filter).** Every figure/chart/pivot reflects the Analytics page's
  **own** filter over the user's scope-authorized member set (or the pivot's own filters), never a
  silent "all members" that disagrees with the filter shown on the analytics page. The analytics
  filter is self-contained (Option A); it does not depend on, and is not confused with, the separate
  table page's filter.
- **Generic + multi-tenant.** No tenant conditionals in the generic code. Analytical dimensions are
  **discovered** from the resolved field config; overlay-only dimensions degrade gracefully.
- **Scope is server-side and inherited.** Analytics never invents scope; it aggregates over the
  already-scoped rows. Any server-side aggregation added MUST apply the same `resolve_scope_access`
  / `_in_scope` gate as `list_members`.
- **Read-only.** Analytics only reads member data. It introduces no member mutation path.
- **Capability-gated.** The analytics surface requires at least `members:read`; export of an
  analytical result requires `members:export` (mirroring the table).

## Requirements

> Requirements are numbered R1–R10 (R8 = privacy/PII, added after the volume/performance section).
> The sequence is contiguous; earlier drafts folded an interim performance sub-section into R7.

### R1 — An Analytics page in the Members module, beside the member table

- **R1.1** The Members module SHALL present a **separate Analytics page** as a sibling to the
  member table-with-modals (its own route/entry in the Members navigation, beside Leden Overzicht —
  NOT a stacked tab on `MembersPage.tsx`), following the dark-theme, orange-primary, Chakra
  conventions in steering 32 and the FIN/STR report-group pattern
  (`frontend/src/components/reports/BnbReportsGroup.tsx`).
- **R1.2** The Analytics page SHALL be visible only to a caller holding **`members:read`** (the
  same capability as the table); it SHALL NOT introduce any member write/mutate action.
- **R1.3** The Analytics page SHALL be organized into clearly separated areas: **Overview**
  (R2), **Distributions / Violins** (R3), and **Pivot Views** (R4) — each independently loadable so
  a slow chart never blocks the others (heavy chart libraries lazy-loaded per the STR pattern).
- **R1.4** The page SHALL distinguish three non-happy states and render each distinctly, never a
  crash:
  - **Empty set** (no rows, or filtered to zero) → a neutral empty state per area.
  - **No analytics config** (tenant has not authored the R9 analytics config) → areas still render
    from fixed/calculated fields; config-dependent sets degrade with a reason (R4.3), not an error.
  - **Load failure** (`GET /members` or `GET /members/field-config` failed) → an explicit error
    state with a retry affordance, distinct from "empty".
- **R1.5** The Analytics page SHALL fetch the **scope-authorized** member set and field config
  itself (reusing `listMembers` / `getFieldConfig` and the shared filter framework), since it is a
  separate page from the table. It SHALL present **its own** row selector / column filters so
  analytics is driven by the Analytics page's own filtered dataset (R5.1). It SHALL NOT inherit or
  depend on the table page's filter state (Option A — self-contained analytics filter), avoiding the
  confusion of a hidden filter traveling from a different page. The starting set is always bounded by
  the user's scope grant (region subset or region-all), so the analytics filter only narrows further
  within what the user is authorized to see, never beyond it.
- **R1.6 (initial render + progressive disclosure — "Overview-first").** The three areas SHALL be
  presented as a view switch (one area visible at a time, following the h-dcn `AnalyticsSection`
  view-mode pattern), with the following load behavior:
  - **On open (immediate):** the page SHALL fetch the scope-authorized member set + field config,
    render the **filter bar** and the **Overview** summary (R2) as the **default landing area**.
    Overview is a cheap client-side aggregation over the loaded rows, so it SHALL render without any
    further click and without loading heavy chart libraries.
  - **On selecting "Distributions":** the **violin charts** (R3) SHALL be rendered then — the Plotly
    bundle lazy-loaded and the age / years-member distributions computed on entering the area
    (R1.3), not on page open.
  - **On selecting "Pivot Views":** the page SHALL show the list of predefined + saved sets;
    **running a set SHALL be an explicit action** (select a set → Execute → result table). Nothing is
    pivoted/listed, and no set runs, until the user chooses and executes one. The output actions
    (CSV / PDF labels / mail, R4.9/R4.12) act on a produced result.
  - **On a filter change:** only the **currently visible** area SHALL re-derive; areas not yet shown
    SHALL NOT be eagerly computed. The Overview recomputes live (R2.2); the Distributions re-derive
    while that area is shown; a pivot result reflects the filter/set in force at Execute time.

### R2 — Member overview summary

- **R2.1** The Overview area SHALL display, for the **Analytics page's own filtered dataset**
  (R5.1), the three figures the backlog names:
  - **Number of members** (count of the filtered rows);
  - **Average age** of the members (mean of the calculated `age`, parsed to a number);
  - **Average years-member** (mean of the calculated `years_member`, parsed to a number).
  It MAY additionally show the h-dcn-parity summary figures (active-member count, top regions,
  members-per-membership-type) that the h-dcn `AnalyticsSection` presents, as long as each is
  derived from the same filtered dataset and degrades gracefully when its field is absent (R2.5).
- **R2.2** Each figure SHALL recompute automatically when the user changes the **Analytics page's
  own** filter or sort — i.e. it SHALL be derived from the page's `processedData`, using the same
  filter-framework mechanism the table's live stats strip uses on its own page
  (`MembersPage.tsx`), but over the analytics page's own filtered dataset (Option A).
- **R2.3** Averages SHALL be computed only over rows where the input is present and parses to a
  valid number; rows with an absent/invalid `age` or `years_member` SHALL be excluded from that
  average (and SHOULD be surfaced as an excluded-count where it aids interpretation), never counted
  as zero.
- **R2.4** The Overview area SHALL present every figure with a bilingual (`nl`/`en`) label resolved
  the same way the table resolves field labels (localized `{nl,en}` → `label[language]`).
- **R2.5** The Overview area SHALL be generic: it SHALL source `age` / `years_member` from the
  resolved field config's calculated fields, and if a tenant's config does not expose one of them,
  that single figure SHALL be omitted gracefully (the others still render).

### R3 — Violin distributions (reusing the STR / BNB violin toolkit)

- **R3.1** The Distributions area SHALL render **violin charts** for the two calculated numeric
  fields the backlog names: **age** and **years-member**, each over the **Analytics page's own
  filtered dataset** (R5.1).
- **R3.2** The violin charts SHALL **reuse the existing violin tooling** used by STR BNB Violin
  Charts — the shared Plotly `Plot` factory (`frontend/src/components/PlotlyChart.tsx`) and the
  violin-trace + quartile-stats construction currently living in
  `frontend/src/components/reports/BnbViolinsReport.tsx`. The spec SHALL **extract** the bespoke
  `ViolinChart` (and its inline quartile-stats helper) into a **shared, reusable component** so both
  BNB and Member Analytics consume one implementation. STR BNB behavior MUST be unchanged by the
  extraction (verified by its existing render). **Charting-library note:** the h-dcn reference
  (`ViolinPlotVisualization.tsx`) renders violins with Recharts/@visx, but this spec deliberately
  reuses the **myAdmin Plotly** violin (per the backlog's "STR / BNB Violin Charts"); h-dcn is the
  behavioral reference for *what* to show (age + membership-years distributions, grouped by region,
  with a violin/box/histogram toggle), NOT the charting library to port.
- **R3.3** The extracted violin component SHALL accept a generic data shape — an array of
  `{ category, value: number }` (or equivalent) plus a metric/axis label — so it is domain-agnostic
  (not `{ listing, channel }`-specific). The Member Analytics caller SHALL feed the parsed numeric
  calculated-field values; a single ungrouped distribution is valid, and an optional **group-by**
  (e.g. by region / membership_type / gender, chosen from the resolved field config) MAY produce one
  violin per group.
- **R3.4** Each violin SHALL carry the same quartile summary the BNB stats table shows (count, min,
  Q1, median, mean, Q3, max, range) for its distribution, reusing the extracted stats helper.
- **R3.5** The violin charts SHALL be computed from parsed numeric values (R2.3 parsing rules);
  non-numeric/absent values SHALL be excluded from the distribution, not coerced to zero.
- **R3.6** The violin area SHALL recompute on filter/sort/context change (same filtered source as
  R2.2) and SHALL render a neutral empty state when fewer than the minimum points needed for a
  distribution are present.

### R4 — Pivot views over the member set (reusing the existing pivot framework)

The backlog asks for pivot views "using the existing pivot framework," with **predefined** sets and
**user-defined, savable** sets. A "set" here is either a **group-by aggregate** (count/sum/… per
group) or a **filtered list of member records** (chosen columns + saved filter values, no group-by);
both kinds are first-class and savable (R4.8). The existing framework is **server-side SQL over a
registered MySQL table/view**, while member records are in **DynamoDB** behind the Members Lambda.
R4 states the behavior required; the bridging mechanism is resolved as **D3 — Option 2 (client-side
pivot adapter)** over the member set the module returns, reusing the framework's config /
result-table layers but aggregating in the browser. The data-volume ceiling and its
detect-and-alert are specified in **R7** (bounded by the 6 MiB Lambda response limit). The
requirement below is behavior-first; the chosen mechanism is Option 2.

> **Correction (post-implementation, finding F-012 — saved-set STORAGE plane).** An earlier
> revision of R4 said saved member sets reuse the Flask **pivot framework's saved-model CRUD**
> (`pivotService` → `/api/pivot/models`, the MySQL `pivot_models` table). That is a **two-plane
> violation** (steering 20/35, R6.2): the Members module is a SAM/DynamoDB module and MUST own its
> data — including feature/config data such as saved analytics sets — in its own DynamoDB table,
> `tenant_id`-tenant-scoped, reached through its own Lambda; it must never persist via a Flask/MySQL
> endpoint, even to reuse an existing table. The framework's **config shape, result-table, and
> client adapter CODE** are still reused (presentation + types), but **saved-set STORAGE moves to the
> Members module** (Option A). R4.4 / R4.4b / R4.5 below are corrected accordingly; the framework's
> `pivotService` model CRUD is NOT the persistence path for member sets.

The headline value (your "Clubblad Papier" case): a user saves a set once — e.g. a filtered list
where `clubblad = Papier` with the columns they need — and **reruns it every month with no manual
intervention**. Saved filter values travel with the set (R4.4); the live page filter does not
(R4.4a).

- **R4.1** The Pivot Views area SHALL let a user pivot the member set reusing the **existing Dynamic
  Pivot Views framework's config shape and result table** (`PivotConfig` / `PivotResult` /
  `PivotResultTable`) — NOT a bespoke pivot engine, and NOT the framework's server-side SQL
  execution. Aggregation runs **client-side** over the scope-authorized member set the Members
  module returns (D3 — Option 2), and **saved sets persist on the Members module's own DynamoDB
  plane** (R4.4), not as registered Flask/MySQL pivot data sources (finding F-012). The reuse is of
  the framework's presentation + type layers, not its storage or SQL engine.
- **R4.2 (predefined sets).** The following **predefined** pivot/report sets SHALL be available
  out of the box for a Members-enabled tenant (each respecting the filtered dataset / its own
  filters, scope-safe, generic):
  - **Membership types** — number of members per membership type.
  - **Birthday / birth month** — a list of members by their birthday or birth-month
    (predefined, list-style set over the calculated `birthday` / `birth_month`).
  - **Jubilees (years-member)** — a list of members at jubilee years, with a **year selector**.
    What counts as a jubilee year SHALL be read from the tenant's **analytics config** (R9), not
    hardcoded (over the calculated `years_member`).
  - **New members (joined date)** — a list of members by join date / join year.
  - **Cancellations (cancellation date)** — a list of members by cancellation date.
  - **Clubblad: paper / country** — members per country among paper-clubblad recipients.
  - **Clubblad: digital** — members receiving the digital clubblad.
  - **Referral source** — number of members by referral source and by year.
- **R4.3 (graceful degradation of overlay-only sets, resolved via config).** The predefined sets
  that depend on **overlay-only** fields (`cancellation_date`, referral source, clubblad
  paper/digital, and any country detail not covered by the fixed `country`) SHALL resolve the field
  they use from the tenant's **analytics config field-role mapping** (R9) — because a tenant's own
  overlay keys are tenant-authored and need not match a platform convention. A set SHALL be
  **offered only when its configured field role maps to a field present in the resolved field
  config**, and SHALL be hidden/disabled with a clear reason otherwise — never shown as a broken or
  empty-forever set. The sets backed by fixed/calculated fields (membership types,
  birthday/birth-month, jubilees, new members) SHALL always be available. When a tenant has not
  configured a role, the set degrades (hidden) exactly as if the field were absent.
- **R4.4 (user-defined + saved sets, including saved filter values).** A user SHALL be able to
  define a set by selecting member data fields **and setting filter values**, and save it for future
  use. Saved member sets SHALL be persisted **by the Members module itself, in DynamoDB**
  (`tenant_id`-tenant-scoped, keyed by `tenant_id` + set id), via CRUD routes on the **Members
  Lambda** (`POST` / `GET` / `PUT` / `DELETE` member analytics-set endpoints) — reached from the
  frontend through the **Members API** (`membersApiService`), **NOT** the Flask `pivotService` /
  `/api/pivot/models` MySQL store (finding F-012: that would cross the plane boundary — steering
  20/35, R6.2). The saved set's shape reuses the framework's `PivotConfig` for its definition, but
  the **storage, tenancy, and validation** are the Members module's own (a filtered-list set with
  empty group-by / measures is first-class — the module store does not impose the SQL engine's
  aggregate-only validation). Saved member sets SHALL be **tenant-scoped** and selectable from a
  list alongside the predefined examples. The saved set SHALL persist **its definition filter
  values** as part of its stored `PivotConfig.filters` — so a user can save, for example, a set with
  `clubblad = Papier` and **rerun it every month with no manual change** (open the saved set → run →
  done). This is the primary value of saved sets: recurring reports without re-entering filters.
- **R4.4a (what is NOT saved into a set).** The Analytics page's **own live row/scope filter**
  (R5.1 — e.g. a region typed on the page that session) SHALL NOT be baked into a saved set; it is a
  live view control. Reopening a saved set SHALL restore the set's own definition filters only, and
  SHALL NOT silently re-apply a page filter from a previous session.
- **R4.4b (explicit save/update, never implicit).** Persisting or changing a saved set's filter
  values SHALL be an **explicit** Save / Save-as / Update action (via the Members API analytics-set
  create/update calls, R4.4), never an implicit write triggered by run-time filter tweaks —
  consistent with the save-once pattern used across Members config. Loading a saved set and tweaking
  a filter before running SHALL be ephemeral unless the user explicitly saves.
- **R4.5 (field picker from the resolved config).** The "select member data fields from a list"
  popup SHALL offer the fields the framework can group/aggregate on, sourced from the **resolved
  field config** (fixed ⊕ overlay ⊕ calculated), labeled bilingually. It SHALL NOT present a
  hardcoded member field list.
- **R4.6 (predefined-as-starting-points).** The predefined sets SHALL be selectable as **default
  prepared examples** a user can run directly or use as a starting point to save their own
  variant — matching the backlog's "can be selected from a list of default prepared examples."
- **R4.7 (pivot results).** Pivot results SHALL render using the framework's existing result table
  (`PivotResultTable`), including its count/sum/avg/min/max aggregates where applicable, with the
  framework's existing export path available for a result.
- **R4.8 (two output kinds: aggregate AND filtered list).** A set SHALL support being either:
  - an **aggregate** (group-by + count/sum/avg/min/max — e.g. "members per membership type"), or
  - a **filtered list of member records** (chosen columns + saved filter values, no group-by — e.g.
    "all members where `clubblad = Papier`, with name / address / member number").
  The filtered-list kind SHALL be a first-class, savable set (R4.4), so recurring row lists are run
  without manual intervention. The design SHALL NOT force every saved set to be a group-by
  aggregate. Both kinds SHALL be exportable (R4.9) and both SHALL respect scope (R5.3).

- **R4.9 (export: CSV and PDF labels).** A filtered-list set (R4.8) SHALL be exportable in two
  formats:
  - **CSV** — the chosen columns of the filtered list, reusing the existing CSV export the Members
    table and pivot result table already use (`frontend/src/utils/csvExport.ts`). This is the
    primary, always-available export for spreadsheets / mail-merge.
  - **PDF address labels** — the filtered list laid out as a printable **label sheet** (an N×M grid
    of labels per page, each label carrying the member's address lines — name, street, postal code +
    city, country), for printing and physically mailing (e.g. the paper clubblad). This SHALL
    **port the proven h-dcn "Adreslabels Generator"** (h-dcn workspace,
    `frontend/src/components/reporting/AddressLabelGenerator.tsx` +
    `services/AddressLabelService.ts`), which generates the PDF **client-side via jsPDF** — the same
    plane as the rest of Option 2, so **no Flask round-trip and no plane crossing** are needed. (The
    weasyprint `PDFGeneratorService` is the invoice/HTML-to-PDF path and is NOT reused for labels;
    labels are a client-side jsPDF grid, matching the h-dcn reference.) The port SHALL be generic +
    multi-tenant (no h-dcn literals): Dutch field names in the h-dcn source (`korte_naam`, `straat`,
    `postcode`, `woonplaats`, `land`, `regio`) SHALL be mapped to the tenant's resolved field keys
    via the analytics field-role / address mapping (R4.10 / R9), not hardcoded.
  Aggregate sets SHALL at minimum support CSV export; PDF-label export is meaningful only for the
  filtered-list (member-rows) kind.
- **R4.10 (label generator feature set — ported from h-dcn, generic + tenant-configurable).** The
  label generator SHALL provide the h-dcn reference's capabilities, generalized:
  - **Standard label formats** — ship the Avery stock the h-dcn generator defines (L7160 = 21/sheet,
    L7163 = 14, L7162 = 16, L7161 = 18, and a Custom Large = 8/sheet), each a `LabelFormat` record
    (columns, rows, label width/height, gaps/margins). A tenant MAY add/select formats; the standard
    set is the shipped default (no tenant must configure a format to get labels).
  - **Style options** — font size (8–12pt), text alignment (left/center/right), show/hide border,
    optional country line, and a **start position** (skip the first N labels, to reuse a partial
    sheet). These are per-run UI options (and savable with a set per R4.4).
  - **Sort order** — by name, postcode, or region (postcode supports bulk-mail ordering).
  - **Address composition + validation** — compose address lines from the tenant's resolved address
    fields (name / street / postal code + city / country), uppercase country for international
    addresses, and **drop members with incomplete address data**, reporting the filtered-out count
    (as the h-dcn generator does). A live **preview** and browser **print** SHALL be available.
  - **Field mapping is tenant config (multi-tenant).** Which resolved member fields fill the address
    lines (name / street / postcode / city / country / region) SHALL be a tenant mapping authored in
    the Members field configurator analytics config (R9) — because overlay/field keys are
    tenant-authored (the h-dcn `korte_naam`/`straat`/… are h-dcn's keys, not platform constants).
    Absent a configured address mapping, PDF-label export SHALL be unavailable (offered only when the
    required address fields resolve) with a clear reason (degradation per R4.3); CSV export remains
    available regardless. The **label formats themselves are shipped defaults**, not a per-tenant
    prerequisite — only the field→line mapping must resolve.
- **R4.11 (export respects scope + the live set).** Both exports SHALL emit exactly the rows the
  set resolves to **within the user's scope-authorized set** (R5.3) and the set's own saved filters
  (R4.4) — never a wider set. An export SHALL be subject to the `members:export` capability
  (consistent with the member table's export), while running/viewing a set requires `members:read`.
- **R4.12 (mail function — server-side SES send, in addition to CSV and PDF labels).** Beyond CSV
  and PDF-label export, a filtered-list set SHALL support a **mail function**: compose and send an
  email to the set's resolved members (or a BCC distribution), optionally **attaching the generated
  CSV / PDF labels**, reusing the existing **`SESEmailService`**
  (`backend/src/services/ses_email_service.py` — `send_email` / `send_email_with_attachments` via
  SES `send_raw_email`) and the established send pattern (`invoice_email_service.py`,
  `tenant-admin/send-email`). The recipient address SHALL be the tenant's resolved member email
  field; a subject/body (bilingual templates) SHALL be editable. Mail SHALL respect the same
  **scope** and the set's saved filters as export (R4.11) — it only ever reaches members within the
  user's scope-authorized set — and SHALL be gated by the **`members:export`** capability (the same
  capability as CSV/PDF export; no separate communication role is required). Which member field is
  the **email address** (and which members are mailable — e.g. only digital-clubblad recipients) SHALL
  be resolved from the field config / analytics field-role mapping (R9), not hardcoded. Bulk send
  volume / rate limits and bounce handling SHALL be noted in the design (SES has send-rate quotas).
  (The Google-Contacts / client-side distribution-list flavor is **NOT** part of this feature.)

### R5 — Driven by the filtered dataset and/or the pivot view selection

- **R5.1** The Overview (R2) and Violin (R3) areas SHALL be computed over the **Analytics page's
  own filtered dataset** — the rows after the page's own row selector / column filters
  (`processedData` from the shared filter framework), applied to the user's scope-authorized set —
  so they always agree with the filter shown on the analytics page. The analytics filter is
  self-contained and independent of the separate table page's filter (Option A).
- **R5.2** The Pivot Views area (R4) SHALL be driven by the **pivot view's own selection/filters**
  (the framework's model + filter controls); where technically feasible it SHOULD also honor the
  table's active filter as a pre-filter, but at minimum it MUST operate over the same **scope** as
  the table (never a wider set).
- **R5.3** No analytics view SHALL ever display members **outside the caller's scope**. Because
  `GET /members` is scope-narrowed server-side, client-side analytics inherits this; any server-side
  pivot/aggregation path added SHALL enforce the identical scope gate (`resolve_scope_access` /
  `_in_scope`) so a scoped user's pivot never leaks out-of-scope rows (steering 20/35).

### R6 — Generic, multi-tenant, steering-compliant implementation

- **R6.1** All analytics code SHALL be **generic**: no `if tenant == "…"` branches, no hardcoded
  tenant field lists or value lists. Dimensions, labels, and options SHALL be **discovered** from
  the resolved field config / membership-type catalog / scope dimensions, exactly as the table does.
- **R6.2** The implementation SHALL honor the two-plane architecture (steering 20/35): member
  business data stays in the **SAM Members module** (DynamoDB), and any Flask/MySQL involvement
  (e.g. a pivot projection/view, if the design chooses that path) SHALL be **one-directional and
  read-only** with respect to member data, never a second write path.
- **R6.3** The implementation SHALL follow steering 32 for the frontend (shared toolkit reuse, dark
  theme, lazy-loaded heavy charts, accessibility of controls) and SHALL reuse the shared filter
  framework rather than re-implementing filtering.
- **R6.4** Labels across the analytics surface SHALL be bilingual (`nl`/`en`), rendered via the
  existing localized-label resolution; added UI strings SHALL go through the existing i18n
  mechanism (e.g. a `members`/`reports` namespace), not hardcoded English.
- **R6.5** The feature SHALL be **testable and tested** (steering 33/34): the aggregation/parse
  helpers (counts, averages, numeric parsing of string-typed calculated fields, quartile stats) and
  the overlay-field discovery/degradation logic SHALL have unit tests; the violin-extraction SHALL
  be covered so STR BNB behavior is proven unchanged.
- **R6.6 (accessibility).** The analytics surface SHALL be accessible: all controls (view switch,
  filter inputs, set dropdown, Execute, export/mail actions) SHALL be keyboard-navigable with
  discernible labels; **color SHALL NOT be the sole signal** (e.g. the growth up/down and
  degradation states carry text/icon, not just hue); and every chart SHALL have a **non-visual
  alternative** — the violin's quartile summary table (R3.4) is that alternative and SHALL be
  present, not optional. (Full WCAG conformance requires manual assistive-technology testing; this
  requirement SHALL be verified by keyboard-walkthrough and the stats-table presence, not claimed as
  blanket WCAG compliance.)
- **R6.7 (responsiveness targets — non-functional).** Over a supported-size set (R7.2), the
  **Overview** SHALL render within ~1s of the member rows being loaded, and a **filter re-derive**
  of the visible area SHALL feel interactive (target < ~100ms beyond the filter framework's existing
  debounce). These are soft targets guiding the memoization in R7.6, verified informally, not hard
  gates.

### R7 — Performance, data-volume behavior, and the response-size limit (Option 2)

The chosen approach is **Option 2 — client-side aggregation** over the scope-authorized member set
the Members module returns (reusing the pivot framework's config / result-table / saved-model layers
but aggregating in the browser, not via the SQL engine). This has a hard upper bound set by the
Members Lambda's response size, which this spec treats as a first-class, monitored constraint rather
than something to design around silently.

- **R7.1 (binding response-size limit).** The Members module is Lambda-backed, so a single
  `GET /members` response is bounded by the **AWS Lambda synchronous invocation response limit of
  6 MiB (6,291,456 bytes)** — a hard AWS limit that cannot be raised by configuration or support
  request. (The API Gateway payload limit of 10 MB is higher and therefore not the binding
  constraint; the 6 MiB Lambda limit is reached first.) Option 2 is viable only while the scope-
  authorized set serializes comfortably within this ceiling.
- **R7.2 (supported volume — a MEASURED cap, not a fixed row count).** The supported Option-2
  volume SHALL be a **measured cap derived from the real serialized record size against the 6 MiB
  limit** — NOT a guessed row count. The design SHALL determine the cap by:
  - measuring the actual per-record JSON size for the **heaviest-overlay tenant** (which sets how
    many members fit under 6 MiB — a large overlay / long text fields reach the byte ceiling at
    fewer rows), and
  - establishing whether **`GET /members`** returns a single uncompressed blob or already
    **paginates / gzips** (which moves the effective cap substantially).
  A provisional working figure of **~3,000–5,000 members per scope-authorized set** MAY be assumed
  until measured, but the authoritative cap is **set-size-in-bytes vs. 6 MiB**, stated in the design
  once the two measurements above are known. The detect-and-alert threshold (R7.3) is defined
  against the byte limit, so it holds regardless of the final row figure.
- **R7.3 (detect-and-alert as the set approaches the limit).** The system SHALL **detect** when a
  `GET /members` response (or the member set the analytics page holds) approaches the 6 MiB limit —
  e.g. crossing a configurable **warning threshold (default ~80% of 6 MiB)** — and SHALL **raise an
  alert/issue** (a user-visible warning on the analytics page AND an operational signal — log/metric
  — so the team is notified), making clear that analytics is nearing its Option-2 ceiling and
  server-side aggregation (Option 1) is required. It SHALL NOT fail silently or render a truncated,
  misleading dataset: if the response is or would be truncated, analytics SHALL show an explicit
  "dataset too large / incomplete" state rather than compute figures over a partial set.
- **R7.4 (graceful behavior at/over the limit).** When the member set cannot be fully/safely loaded
  within the limit, the analytics areas SHALL render the explicit over-limit state (R7.3), never a
  crash and never a silently-partial aggregate (ties to R5.3 scope-safety and R1.4 empty/edge
  states).
- **R7.5 (future server-side path left open).** The design SHALL NOT preclude moving aggregation
  server-side later (Option 1 — a module-side pivot/aggregation action, or a paginated/streamed
  read); `POST /members/search` / `export_members` are the existing server hooks. Switching to
  Option 1 SHALL be possible without changing the reused config / result-table / saved-model layers.
- **R7.6 (memoization).** Analytics computations SHALL be memoized so typing in a column filter does
  not trigger a full recompute per keystroke beyond what the existing filter framework already
  debounces.

### R8 — Privacy / PII handling and audit (personal data leaves the system)

Analytics exports and mails **personal member data** (names, addresses, email) out of the system —
to CSV, PDF labels, and email — so it is a data-egress surface, not just a read view. This section
makes the handling explicit.

- **R8.1 (audit of egress).** Every **export** (CSV / PDF labels) and every **mail send** SHALL be
  **audit-logged**: who performed it, when, which set/filter was used, the resulting record count,
  and the output kind — reusing the platform's existing audit/logging mechanism rather than a
  bespoke log. The log SHALL record metadata, NOT the exported personal data itself.
- **R8.2 (scope on egress).** Export/mail SHALL only ever include members within the user's
  scope-authorized set and the set's saved filters (restates R4.11/R5.3 as a privacy guarantee): a
  scoped user cannot export or mail members outside their scope.
- **R8.3 (minimize PII in logs/telemetry).** Operational signals (R7.3 alert, performance logs,
  error reports) SHALL NOT contain member personal data — only counts, sizes, and identifiers that
  are not PII. Member names/addresses/emails SHALL NOT be written to logs or telemetry.
- **R8.4 (mail safety).** Bulk mail (R4.12) SHALL default to a safe recipient mode (e.g. BCC so
  recipients are not disclosed to one another), and SHALL surface the recipient count for
  confirmation before sending, to prevent accidental mass disclosure.
- **R8.5 (retention of generated artifacts).** Generated CSV/PDF artifacts SHALL NOT be persisted
  server-side beyond what the mail-send requires; if an artifact is stored transiently to attach it,
  it SHALL be removed after send (no silent accumulation of member-data files).

### R9 — Tenant-specific analytics semantics authored in the field configurator (multi-tenant)

The two tenant-specific semantics this feature needs are **authored as tenant config in the Members
field configurator** (`MembersConfigEditor.tsx` → the `members.*` params), so a tenant configures
them once and analytics reads the result — never a hardcoded rule and never a platform-forced
overlay key. This is the ideal multi-tenant resolution of what were otherwise open questions.

- **R9.1 (analytics config slice).** The Members field configurator SHALL gain an **Analytics**
  authoring area that writes an analytics-config slice through the same save-once / typed-editor /
  bilingual mechanism as the existing `field_overlay` / `scope_dimensions` / `view_contexts`
  editors (`MembersParamSubEditor`), persisted as part of the `members.*` tenant parameters and
  projected/served alongside the field config so analytics can read it.
- **R9.2 (jubilee rule).** The analytics config SHALL let a tenant define the **jubilee rule** —
  what counts as a jubilee year of `years_member` (e.g. a configured set like `{5,10,15,…}`, or a
  multiple-of-N rule) — and SHALL make the Jubilees set + its year selector (R4.2) read this rule.
  Absent config SHALL fall back to a documented sensible default (e.g. multiples of 5), never a
  crash.
- **R9.3 (analytics field-role mapping).** The analytics config SHALL let a tenant map each
  **analytics field role** — `cancellation_date`, `referral_source`, `clubblad_paper`,
  `clubblad_digital`, and (optionally) a `country`-detail role — to one of the tenant's own
  **resolved field keys** (fixed / overlay / calculated), chosen from a picker that offers only
  resolvable keys (mirroring the configurator's existing key pickers). The predefined sets (R4.2)
  SHALL resolve their field through this mapping (R4.3). A role left unmapped means its set is
  simply not offered (graceful degradation), with a clear reason.
- **R9.4 (authoring is generic + bilingual).** The analytics config editor SHALL be generic (no
  tenant literals), bilingual (`nl`/`en`), and SHALL validate references on Save the same way the
  existing sub-editors do (offer-only-resolvable at authoring; backend authoritative on Save).
- **R9.5 (consumption).** Analytics SHALL treat the analytics config as read-only tenant data,
  exactly like the field config and scope dimensions; it SHALL NOT write it (authoring is the
  configurator's job).

### R11 — Shared pivot/list library + per-user preferred lists (SAM-plane, member-independent)

> Added after post-implementation review (the F-012 saved-set work surfaced the real usage model).
> This REFINES R4.4 / R4.4a / R4.4b (saved sets) into a **two-layer** model and makes the ownership
> identity explicit. It supersedes the earlier implicit "saved sets are just tenant-scoped models"
> wording where they differ. Storage stays on the **SAM/DynamoDB plane** per F-012; nothing here
> touches the Flask admin-config plane (that remains the tenant admin's domain — R9).

- **R11.1 (user ≠ member — the identity principle).** The **owner/actor** of any analytics set or
  preferred list is the **authenticated user**, identified by the verified Cognito **`sub`**, and is
  **independent of whether that user is also a member** of the club. A user may be a member, both,
  or (e.g. `webmaster@…`) a user who is NOT a member. Ownership, listing, and personal preferences
  SHALL key on `sub` (+ `tenant_id`), NEVER on a `member_id` / member record. A member's record is
  data the user may query (subject to scope), never their identity. (This mirrors the F-012/F-013
  plane discipline: a durable principle, not an incidental detail.)

- **R11.2 (two layers: shared definitions + private preference).** Analytics sets SHALL be modeled
  in two distinct layers:
  1. **Set definitions = a TENANT-SHARED library.** Every pivot/list *definition* — predefined OR
     user-created — belongs to the **tenant** and is **visible to every user in that tenant**. A set
     a user creates joins the shared library so other users can find and reuse it (deliberately
     preventing duplicate near-identical sets). Set definitions are `tenant_id`-scoped (NOT
     per-user).
  2. **Preferred list = PRIVATE per user.** Each user curates **one** preferred list
     (`tenant_id` + `sub`) — an **ordered list of references** into the shared library (predefined
     and/or user-created). It stores REFERENCES, not copies, so there is exactly one definition per
     set and no duplication. Each user sees only their own preferred list.

- **R11.3 (capabilities — export OR CRUD, not admin).** The analytics set + preferred-list surface
  SHALL be usable by any user holding **`members:export` OR `members:write` (Members_CRUD)** — it is
  NOT restricted to tenant admins. Specifically:
  - **run/list/get** a set and **read my preferred list** → `members:read`;
  - **create** a (shared) set, and **edit my own preferred list** → `members:export` OR
    `members:write`;
  - **edit/delete a user-created shared set** → `members:write` (Members_CRUD) OR tenant admin
    (any CRUD-capable user or an admin may curate the shared library — not restricted to the set's
    creator). A `created_by` (`sub`) SHALL be stamped for attribution/audit, but it does NOT gate
    edit/delete.
  - **Predefined (code) sets** SHALL be **immutable** — never editable or deletable through this
    surface (R11.5).

- **R11.4 (scope inherited, member-independent).** A set definition SHALL NOT encode scope. When a
  set runs, it runs over the caller's **scope-authorized** member dataset (`GET /members`,
  server-narrowed by the caller's region grant), so the SAME shared definition yields all members
  for a `Regio_All`/wildcard user and only the caller's region for a region-limited user — with no
  cross-region leak (the out-of-scope rows never reach the client). Scope is resolved from
  roles/grants, NOT from membership, so a non-member user with a wildcard grant sees all members
  and a region-limited user sees their region (restates R5.3 for the shared library).

- **R11.5 (predefined sets stay as code, referenced by key).** The predefined presets SHALL remain
  **code/config** (`memberPivotPresets.ts`), not stored library items — they cannot be deleted, and
  a user simply does not add ones that add no value for them. A preferred list SHALL reference items
  with a **tagged reference** — `preset:<key>` for a predefined set, `set:<id>` for a shared
  user-created set — so one uniform reference space addresses both without migrating the presets.

- **R11.6 (graceful degradation of references).** A preferred list that references a set which no
  longer resolves (a deleted shared set, or a predefined/role-backed preset not currently available
  to the tenant) SHALL **skip the missing reference** and still render the rest — never crash, never
  show a broken entry (mirrors the preset-degradation rule R4.3).

- **R11.7 (storage plane).** Shared set definitions and per-user preferred lists SHALL be persisted
  by the **Members module on its own DynamoDB table** (`tenant_id` tenancy, reached through the
  Members Lambda), reusing the F-012 analytics-set store — NEVER the Flask/MySQL plane (steering 35
  rule 5a). The engine SHALL stay module-agnostic / extraction-friendly (no `sam/shared/analytics/`
  library until a second consumer — F-013 rule of three).

### R10 — Out of scope (explicitly excluded)

- **R10.1** **AI-command / natural-language analytics** over members — out of scope here (s5c R10.1
  mentions "AI commands" as a future reporting capability; this spec does graphs/violins/pivots).
- **R10.2** **Server-side member aggregation endpoints** in the SAM module — out of scope unless the
  design's pivot-bridge decision requires a minimal read-only projection; no general analytics API
  is built.
- **R10.3** **New charting libraries** — out of scope; reuse Plotly (violins/distributions) and the
  existing pivot result table. No recharts/d3 addition for this feature.
- **R10.4** **Member mutation from analytics** (bulk edits triggered from a chart/pivot) — out of
  scope; analytics is read-only.
- **R10.5** **Cross-tenant / platform-wide analytics** — out of scope; everything is within the
  caller's tenant and scope.
- **R10.6** **Authoring the overlay fields themselves** (`cancellation_date`, referral source,
  clubblad, country detail) is the s5c Members config path, **not** this spec. This spec adds the
  analytics **role mapping** that points at those fields (R9.3) and consumes/degrades (R4.3); it
  does not add the fields to the fixed base.

## Resolved design decisions (previously open questions)

- **D1 — Placement (was OQ2): a separate Analytics page in the Members module, beside the member
  table.** Per the user's direction, analytics is its own page (sibling to Leden Overzicht), not a
  tab on `MembersPage.tsx`. It fetches/filters the scoped member set itself (R1.5).
- **D2 — Tenant semantics (was OQ4 + the overlay-key question): authored in the field
  configurator** (R9). The jubilee rule and the analytics field-role mapping are tenant config, not
  hardcoded.
- **D3 — Pivot bridge (was OQ1): Option 2 — client-side pivot adapter** over the fetched,
  scope-authorized list, reusing the framework's config/types/result-table + per-tenant saved-model
  CRUD, not its SQL engine. This is bounded by the **6 MiB Lambda response limit** and that bound is
  monitored with detect-and-alert (R7). The alternatives — **Option 1** (aggregate inside the
  Members Lambda) and the MySQL-projection bridge — are the documented future paths if the set
  outgrows Option 2, switchable without changing the reused layers (R7.5). (See `design.md`.)
- **D4 — Numeric typing (was OQ3): parse string calculated values on the client** (`toNumber`), no
  module change, unless a future MySQL-projection bridge needs real numeric columns. (See
  `design.md`.)

## Acceptance criteria

The feature is "done" when all of the following hold (each is traceable to a requirement):

- **Page + placement:** a separate Analytics page exists in the Members module beside the table,
  gated by `members:read`, no member mutation path (R1.1/R1.2).
- **Overview-first render:** on open, the filter bar + Overview (count, average age, average
  years-member) render immediately with no heavy chart load; Distributions renders its violins only
  when that area is opened; a pivot/list set runs only on explicit Execute (R1.6).
- **Overview correctness:** averages exclude absent/invalid values (not counted as zero) and
  recompute live on the page's own filter change; a missing calculated field drops only its figure
  (R2.1–R2.5).
- **Violins reuse, BNB unchanged:** the age + years-member violins render via the **shared,
  extracted** Plotly `ViolinChart` + quartile-stats helper, and the existing STR BNB report still
  renders identically (R3.2/R3.4), proven by its test.
- **Predefined sets + degradation:** the named predefined sets are available; overlay-/role-backed
  sets appear only when their analytics-config role resolves to a present field, and are
  hidden-with-reason otherwise (R4.2/R4.3/R9.3).
- **Saved recurring set:** a user can build and save a filtered-list set with a filter value (e.g.
  `clubblad = Papier`), and reopening + running it next month reproduces the same list with no
  re-entry; the page's live filter is NOT baked in (R4.4/R4.4a/R4.8).
- **Outputs:** a filtered-list set exports to CSV and to PDF address labels (ported h-dcn generator,
  client-side jsPDF, shipped Avery formats), and can be mailed via SES with optional CSV/PDF
  attachment; all three respect scope + saved filters and are gated by `members:export`
  (R4.9–R4.12).
- **Scope safety:** no area/export/mail ever surfaces a member outside the caller's scope-authorized
  set (R5.3/R8.2).
- **Data-volume guard:** when the member set approaches the 6 MiB Lambda limit, the page shows the
  warning/over-limit state and emits an operational signal; it never computes over a silently
  truncated set (R7.1/R7.3/R7.4).
- **Multi-tenant config:** jubilee rule and analytics field-role mapping are authored in the Members
  field configurator and read by analytics; no hardcoded jubilee rule or overlay key (R9).
- **Privacy/audit:** every export and mail is audit-logged (actor, time, set, count, kind) with no
  PII in logs; bulk mail defaults to BCC and confirms the recipient count (R8).
- **Accessibility + i18n:** controls keyboard-navigable, color not the sole signal, violin stats
  table present as the non-visual alternative; all labels bilingual nl/en (R6.4/R6.6).

## Success metrics

- A recurring list that previously needed manual re-filtering each month (e.g. "Clubblad Papier"
  address labels) is produced in **one action from a saved set**, with zero manual filter entry.
- **Zero** out-of-scope members appear in any analytics figure, chart, pivot, export, or mail for a
  scoped user (verified against a scoped vs. all-scope user).
- The STR BNB violin report is **behaviorally unchanged** after the shared-component extraction
  (its tests pass unmodified).
- No tenant-specific literal (`if tenant == …`, hardcoded overlay key, hardcoded jubilee rule)
  exists in the analytics code — everything tenant-specific resolves from config (grep-clean).
- When a tenant's set approaches the 6 MiB ceiling, the team is **alerted before** it fails
  (the warning threshold fires), not after a user sees a broken dataset.

## Out of scope (summary)

AI/natural-language analytics; a general server-side member-aggregation API; new charting
libraries; member mutation from analytics; cross-tenant/platform-wide analytics; authoring the
overlay fields themselves (s5c config path); the Google-Contacts / client-side distribution-list
mail flavor. The MySQL-projection pivot bridge and module-side (Option 1) aggregation are deferred
scaling paths, not built now.
