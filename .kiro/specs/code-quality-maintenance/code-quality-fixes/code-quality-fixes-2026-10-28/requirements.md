# Requirements Document

Code Quality Fixes — 2026-10-28 (local, source-level scan).

## Introduction

This spec captures the findings of a local, source-level code-quality scan (no CI, no
test execution) run on 2026-10-28, and the prioritized improvement tasks derived from them.
Each requirement below is a scan dimension with its findings, counts, and the delta vs the
previous run (`code-quality-fixes-2026-10-15`). The actionable work lives in `tasks.md`.

## Glossary

- **Plane** — one of the three code areas: `backend` (Flask/MySQL), `sam` (Lambda/DynamoDB), `frontend` (React).
- **Bypass** — hand-rolled code that re-implements a shared building block instead of using it.
- **Missing-test candidate** — a source file whose basename is referenced by no test file (filename heuristic).
- **Test-exempt-via-parent** — a private `_`-prefixed module exercised through its public parent module's tests.

## Requirements

Each numbered section below (1–8) is a scan-dimension requirement with its findings, counts, and delta vs the previous run.

## Summary

**Local, source-level** code-quality scan (no CI, no test execution) of the myAdmin repo,
2026-10-28. Covers file length, dead code, duplication, framework/reusable-block (non-)use,
type safety, mobile compliance, stale docs, and missing-test gaps. Compared against the previous
run `code-quality-fixes-2026-10-15`.

| Dimension                     | Count (this run)                                      | Δ vs 2026-10-15                               |
| ----------------------------- | ----------------------------------------------------- | --------------------------------------------- |
| Files 500–1000 lines          | ~45 be+fe · ~16 sam                                   | ≈ stable; sam share up                        |
| Files > 1000 lines (critical) | **9** (sam 7 / be 1 / fe 1)                           | ↑ from 8 — SAM regressed, frontend improved   |
| Dead code (vulture ≥ 80)      | be 0 · sam 0                                           | ↓ sam 4 → 0 (scope_filter finally resolved)   |
| Duplicate patterns            | **`resolveLabel` ×8 frontend copies** (real)          | ↑ from ×2 — duplication grew, worth a helper  |
| Framework bypasses            | fe 1 (an `.example.tsx` demo, exempt) · be/sam clean  | ↓ from 2 — effectively zero real bypasses     |
| Type safety                   | fe `any` ~123 raw (prod-filtered) · be/sam hint heuristic | ≈ stable                                  |
| Mobile not-optimized          | heuristic flags 229 tsx / 163 hover — ~5 real risks   | ≈ stable (same recurring table category)      |
| Stale docs                    | ~0 real                                               | stable                                        |
| Missing tests                 | be ~60 raw / sam 12 raw / fe ~80 raw (heuristic)      | ≈ stable; sam all `_`-private-module artifact |

**Headline:** Two wins and one regression since 2026-10-15.
WINS — (1) **dead code is now 0 on both planes**: the recurring SAM `scope_filter` tenant-scoping
dead variable (flagged three cycles running) no longer appears; (2) **frontend critical-length debt
dropped** — `MemberPivotViews.tsx` shrank 2007 → 1718 and `membersApiService.ts` / `MembersPage.tsx`
fell below 1000, so frontend went from 3 files > 1000 to **1**.
REGRESSION — **the SAM plane is now the critical-length leader with 7 files > 1000** (up from 4):
`_membership_writes.py` grew to 1940, and the config-fields CRUD arc added large new modules
(`config_fields_crud_service.py` 848, `config_write_service.py` 853, `projection_config_write_repository.py`
818 are < 1000 but several siblings crossed it). Separately, **`resolveLabel` duplication grew from 2
to 8 near-identical frontend copies** — the clearest new consolidation target.

---

## 1. File Length (split candidates)

Excludes test files, `.venv/`, `node_modules/`, `__pycache__/`, `build/`, `dist/`, `.aws-sam/`.

### Critical (> 1000 lines) — 9 source files (test files excluded)

| File                                                       | Lines | Plane   | What to extract                                                   |
| ---------------------------------------------------------- | ----- | ------- | ----------------------------------------------------------------- |
| `sam/members/domain/_membership_writes.py`                | 1940  | sam     | Now the largest source file — split create / update / lifecycle / analytics write paths. 🆕grew |
| `sam/members/migration/hdcn_backfill.py`                   | 1726  | sam     | One-off backfill — extract step helpers; lower risk.              |
| `frontend/src/components/members/analytics/MemberPivotViews.tsx` | 1718 | frontend | Split pivot builder / result rendering / preset+export into sub-components (shrank 2007→1718, still critical). |
| `sam/members/repository/members_repository.py`             | 1595  | sam     | Split read / write / scope-filter query builders.                 |
| `sam/members/handler/app.py`                               | 1480  | sam     | Router handler — extract per-route dispatch into modules.         |
| `sam/members/handler/_dispatch.py`                         | 1479  | sam     | Dispatch table — group by resource into sub-modules.              |
| `sam/members/worker/mail_send_worker.py`                   | 1236  | sam     | Split queue drain / render / send / audit stages.                 |
| `sam/members/repository/projection_config_reader.py`       | 1185  | sam     | Split overlay read / resolve / wire-shape helpers. 🆕crossed      |
| `backend/src/services/_projection_config_builders.py`      | 1099  | backend | Extract per-builder helpers; was flagged < 1000 last cycle. 🆕crossed |

Note: `sam/members/repository/table_design.py` (1172) and `sam/members/handler/routes.py` (1043)
also now exceed 1000 (SAM has 7 source files > 1000 total; the table lists the largest). Last cycle's
`frontend/src/services/membersApiService.ts` (1267) and `frontend/src/pages/MembersPage.tsx` (1161)
have both dropped below 1000 — frontend improved.

### Notable 500–1000 line files (opportunistic)

- **Backend:** `str_database.py` 926, `members_config_validation.py` 866, `routes/tenant_admin_users.py` 859,
  `services/media_asset/lifecycle.py` 852, `scalability_routes.py` 852, `routes/str_routes.py` 841,
  `services/cognito_service.py` 800, `pattern_analyzer.py` 793, `services/budget_mutation_service.py` 792,
  `services/projection_sync.py` 787, `routes/chart_of_accounts_routes.py` 787.
- **Frontend:** `services/members/membersResourceApi.ts` 994, `components/members/analytics/MemberTemplateManager.tsx` 793,
  `components/members/analytics/MemberMailCompose.tsx` 790, `types/members.ts` 761,
  `components/TenantAdmin/MembersConfig/MembersFieldModal.tsx` 737,
  `components/members/analytics/MemberFieldPicker.tsx` 736, `App.tsx` 645,
  `components/pivot/PivotResultTable.tsx` 643.
- **SAM:** `domain/config_write_service.py` 853, `domain/config_fields_crud_service.py` 848,
  `repository/projection_config_write_repository.py` 818, `domain/attribute_catalog.py` 811,
  `domain/fixed_fields.py` 732, `domain/template_service.py` 618, `domain/execute_and_deliver.py` 595.

Full scan saved at `.agent-output/cq-filelen.txt` during the run.

## 2. Dead Code

- **Backend (vulture ≥ 80): 0 findings.** Clean, consistent across cycles.
- **SAM (vulture ≥ 80, source only): 0 findings.** 🎉 The recurring `scope_filter` tenant-scoping dead
  variable (flagged 2026-10-04 and 2026-10-15, lines kept moving under refactor) no longer appears, and
  `mail_audit.py`'s `actor_roles` is gone too. A three-cycle recurring item is resolved — close out the
  "Recurring Issue" from the last two runs.

## 3. Duplicate / Near-Duplicate Code

The signature-frequency scan is dominated as always by expected OOP dunders (`def __init__` ×1093,
`__repr__`, `__eq__`, `__iter__`) and the vendored Chakra icon re-exports (`WarningIcon`, `ViewIcon`, …
×2 each) — both noise, not project duplication.

The one GENUINE and GROWING finding: **`resolveLabel` is now defined in 8 frontend locations** (was 2
last cycle):

- `pages/MemberAnalyticsPage.tsx:131` · `components/members/fieldForm.ts:97` ·
  `components/members/FieldChecklist.tsx:46` · `components/members/analytics/memberFieldPicker.helpers.ts:48` ·
  `components/members/analytics/MemberOverviewStats.tsx:75` ·
  `components/members/analytics/memberPivotViewsHelpers.ts:60` ·
  `components/members/overview/membersOverviewModel.ts:48` ·
  `components/public/application/applicationForm.model.ts:52`.

These are near-identical label-resolution helpers (pick a display label from a field/option record).
They should be collapsed into ONE shared util (e.g. `components/members/labelResolver.ts` or a shared
`utils/`), each call site updated in the same change. Verify any per-call-site nuance (fallback order,
locale handling) before merging so no behavior changes silently. This is the cycle's clearest code-
reduction target.

## 4. (Non-)use of Frameworks / Reusable Building Blocks ← primary focus

### Frontend data fetching — effectively zero real bypasses

Only ONE non-service `fetch()` site remains, and it is **exempt**:
`frontend/src/components/examples/TenantAwareComponent.example.tsx:137` — an `*.example.tsx` demo file
(illustrative, not shipped). The `PublicLandingPage.tsx` `fetch()` flagged last cycle is gone. The
apiService migration is fully landed. Recommend adding the ESLint guard (see Lessons) so it cannot
regress.

### Backend / SAM — clean

- **Backend DB:** 0 raw `mysql.connector` bypasses outside `database.py` / `scalability_manager.py`.
- **Backend auth:** the route modules without `@cognito_required`/`@tenant_required`
  (`static_routes`, `config_routes`, `signup_routes`, `sysadmin_routes`, `environment_routes`,
  `landing_page_routes/public_endpoints`, `service_accessors`, `tenant_admin_template_constants`,
  `error_responses`, `media_asset_routes/__init__`, `routes/__init__`) are the legitimately-public /
  aggregator / accessor / `__init__` files. Not real bypasses.
- **SAM:** 0 inline `boto3.resource('dynamodb')` outside `dynamodb_client.py`; 0 hand-rolled
  `jwt.decode`/`jose` outside `/shared/`. The DynamoDB grep hits are comments in
  `execute_and_deliver.py`, the sanctioned one-time migration `functional_groups_list_to_map.py`, and
  the legitimate injected-table reader `sam/pretokengen/projection_governance_reader.py:108` — not
  handler→repository boundary violations.

### SAM data-shape boundary (steering 39) — clean

All `field_overlay` / `overrides` / `fixed_overrides` / `functional_groups` grep hits are **docstrings,
comments, or the sanctioned repository/wire-contract code** (`config_fields_crud_service.py`'s
documented wire-key mapping, `_dispatch.py`'s stale-client rejection comments, the repository's own
`get_raw_fields_overlay` which is the sanctioned confined accessor). No raw store shape crosses into a
domain service, response, or DTO outside the repository boundary. No new leak.

### SAM foolproof-CRUD (ADR 0009 / steering 39) — clean

The raw `put_item`/`update_item`/`delete_item` hits are all in the **sanctioned writers**:
`members_repository.py` (member/analytics-set/template rows — not the governance `config#*` row) and the
one-time `functional_groups_list_to_map.py` migration. The governance-table Change-Op path
(`projection_config_write_repository.py`) is the only writer of `config#fields` and uses per-path
version-conditional `update_item` (no whole-record replace). The `functional_groups` assembly hits are
the seed overlay and the reader's documented empty-shape — not a whole-record client write. Frontend
`resolveWriteTarget` / `membersConfigApi` route per-identity Change-Ops (the retired whole-overlay
`saveMembersParameter('field_overlay', …)` path is explicitly rejected fail-closed). No violation.

### Frontend — minor (low priority)

- **Theme:** hardcoded hex colors remain in chart/legend config. Low priority.
- **Filters:** a few bespoke `useState`-filter / `.filter(..includes())` re-implementations where the
  shared `GenericFilter` framework exists. Low priority.

## 5. Type Safety

- **Frontend `any` (production): ~123 raw** (down-filtered from 237 by excluding tests/mocks/setup).
  Still inflated by comment lines containing the word "any" and `__mocks__` re-exports; the real
  production `any` is the same thin spread as prior cycles — public landing blocks (`AboutBlock`
  `properties as any`), `types/parameterSchemaTypes.ts`, zzp modals, reports, and the service-layer
  `Promise<any>` returns that persist. Low-to-medium priority; chip away in the service layer first.
- **Backend / SAM missing return hints (heuristic):** backend ~575, sam ~406 inline `def` lines with no
  `->`. This **overcounts** heavily (multi-line signatures whose `->` lands on the closing-paren line,
  plus `__init__`/dunders that legitimately return `None`). Rough indicator only; ANN rules are not
  enabled in ruff. Low priority.

## 6. Mobile Compliance (frontend)

Frontend remains **broadly mobile-ready**: `frontend/index.html` carries the correct
`<meta name="viewport" content="width=device-width, initial-scale=1" />`, **0 fixed 3-digit px
widths**, Chakra responsive patterns used widely, **0 `mobile-exempt` markers** present.

The heuristic flags are high (229 `.tsx` with no responsive token, 163 `_hover`/`:hover`), but these
over-flag massively — most are leaf/presentational components that render through responsive parents, and
`_hover` on a Chakra button is not a mobile defect (Chakra maps it sensibly on touch). The real
horizontal-overflow / no-mobile-fallback risks to confirm (data-dense tables on primary flows), carried
forward from last cycle:

| File                                              | Severity | Note                                   |
| ------------------------------------------------- | -------- | -------------------------------------- |
| `frontend/src/pages/CheckAccountsPage.tsx`        | Medium   | banking data table, user-facing        |
| `frontend/src/pages/CheckReferencePage.tsx`       | Medium   | banking data table, user-facing        |
| `frontend/src/pages/STRChannelRevenuePage.tsx`    | Medium   | revenue table, user-facing             |
| `frontend/src/pages/TransactionsPage.tsx`         | Low      | transactions table — verify wrapper    |

Each needs a `TableContainer`/`overflowX` wrapper or a stacked/card mobile fallback **confirmed** (the
heuristic can't tell a wrapped child apart). Recurring category — new data tables keep landing without
an explicit responsive wrapper (noted three cycles).

## 7. Stale Documentation (light pass)

Essentially clean. No doc references modules that were split/removed. Historical point-in-time status
artifacts (`*_COMPLETE.md`, `*_SUMMARY/*_PLAN/*_REPORT.md`) remain and could be archived — lowest
priority, no code contradiction.

## 8. Missing Tests (coverage gaps)

Filename-level heuristic (a source file is a candidate when no test file references its basename). Raw
counts this run: **backend ~60 · SAM 12 · frontend ~80**. Read the classification before treating as
regression — most SAM/backend candidates are test-exempt-via-parent or one-off scripts.

### SAM — 12 raw, all `_`-private refactor-split modules covered via parent

Every SAM candidate is a private `_`-prefixed module or a thin sub-module exercised through its public
parent, which the basename grep does not credit:

- `sam/shared/_verifier.py`, `_pool_registry.py`, `_auth_errors.py`, `_jwks.py` — internals of
  `sam/shared/auth_utils.py` (JWTVerifier / pool registry / JWKS); covered via `auth_utils` tests.
- `sam/members/domain/_membership_{reads,analytics,schedules,catalog}.py`, `_delivery_models.py` — the
  split internals of the former `membership_service.py`; covered via the public service + handler tests.
- `sam/members/domain/application_messages.py`, `repository/mail_send_queue.py`,
  `repository/template_body_store.py` — exercised via handler/worker tests.

**Action:** treat as test-exempt-via-parent, but spot-check that the parent tests drive the private
module's branches — especially `_membership_writes.py` (tenant-scoped writes, now the largest file).

### Backend — ~60 raw; genuine high-risk gaps (shortlist carried forward)

- **Test-exempt (not gaps):** 8 × `migrations/*` (one-off scripts), `wsgi.py`, `gunicorn.conf.py`, the
  `landing_page_renderers/*` (6) and `media_asset/*` (5) sub-modules (exercised via dispatch/parent —
  verify).
- **High risk (auth / DB / money / tenant-scoping / routes):** `admin_routes.py`, `audit_routes.py`
  (API routes), `routes/chart_of_accounts_io_routes.py`, `routes/duplicate_detection_routes.py`,
  `routes/system_health_routes.py`, `routes/members_analytics_audit.py`, `services/_projection_scopegrant.py`
  (tenant-scoping), `scalability_routes.py`.
- **Medium:** `services/zzp_invoice_delivery.py`, `services/zzp_invoice_numbering.py`,
  `services/zzp_invoice_factory.py`, `services/zzp_trip_calculation_service.py`,
  `services/zzp_trip_query_service.py`, `services/zzp_trip_crud_service.py`,
  `services/pivot_query_builder.py`, `services/chart_of_accounts_io_service.py`,
  `services/template_pdf_renderer.py`, `mutaties_cache_{loader,models,queries}.py`.
- **Low:** `xlsx_download_helpers.py`, `xlsx_styles.py`, `file_cleanup_actions.py`, `api_schemas.py`,
  `xlsx_report_generators.py`, `pdf_decision_handler.py`.

### Frontend — ~80 raw; mostly leaf/presentational, lowest priority

- **Services:** `services/members/membersResourceApi.ts`, `membersApiClient.ts`,
  `membersColumnPreferencesApi.ts`, `membersPageSize.ts` surface as candidates — likely covered via the
  `membersApiService.test.ts` aggregate (the resource modules were split out of it); verify the split
  modules' branches are actually driven, else add focused tests.
- The remaining candidates are predominantly **leaf/presentational** (public/blocks ×10, MediaAssetAdmin
  tabs ×6, zzp modals, budget/report panels) and **test-exempt** types/barrels — fill opportunistically.
- Genuine medium-value targets worth a direct test: `components/members/overview/useMembersSelection.ts`
  (selection hook with branches), `components/pivot/usePivotConfig.ts` (pivot config hook),
  `components/members/overview/membersOverviewModel.ts` (pure-logic model).

---

## Comparison with 2026-10-15

| Metric                        | 2026-10-15              | 2026-10-28              | Trend                                        |
| ----------------------------- | ----------------------- | ----------------------- | -------------------------------------------- |
| Files > 1000 lines            | 8 (fe 3 / be 1 / sam 4) | 9 (sam 7 / be 1 / fe 1) | ↑ total; SAM regressed, frontend improved    |
| Frontend `fetch()` bypasses   | 2 (1 real + 1 example)  | 1 (example only)        | ↓ effectively zero real                      |
| Dead code (sam vulture)       | 4                       | 0                       | ↓↓ scope_filter finally resolved (3-cycle)   |
| `resolveLabel` copies (fe)    | 2                       | 8                       | ↑↑ duplication grew — new consolidation task |
| Mobile table risks            | ~5                      | ~4 (verify)             | ≈ stable, recurring category                 |
| Frontend `any` (prod)         | ~94                     | ~123 raw (≈ same real)  | ≈ stable                                     |

### Recurring Issues

1. **New data tables land without a responsive wrapper** — fourth cycle this category appears. Make
   "no `TableContainer`/`overflowX`/card fallback" a review gate for any new `<Table>`.
2. **Service-layer `Promise<any>`** persists across cycles.
3. **SAM is the perennial file-length offender** — as one large module is split, the members arc grows
   another. Length debt migrates between planes rather than net-reducing.

### Resolved Since (previously recurring)

- 🎉 **SAM `scope_filter` dead variable** — flagged 2026-10-04 and 2026-10-15, now gone. Three-cycle
  recurring item closed.
- 🎉 **Frontend critical-length regression** from last cycle partially unwound: `MemberPivotViews.tsx`
  shrank, `membersApiService.ts` and `MembersPage.tsx` dropped below 1000.

### New Debt Introduced Since

- 🆕 **SAM `_membership_writes.py` grew 1134 → 1940** — now the single largest source file in the repo.
- 🆕 **`resolveLabel` duplication grew 2 → 8 copies** across the members/public frontend.
- 🆕 **`sam/members/repository/projection_config_reader.py` (1185)** and
  **`backend/src/services/_projection_config_builders.py` (1099)** crossed 1000 — the config-fields arc.

## Lessons / Recurring Issues

1. **The `scope_filter` close-out proves deliberate resolution beats re-flagging.** It took naming it a
   "Recurring Issue" two cycles to get it resolved. Do the same for `resolveLabel` now (8 copies) before
   it reaches double digits.
2. **Add the ESLint fetch/axios guard.** Raw `fetch(`/`axios.` outside `src/services/` is down to one
   exempt demo file — lock it in with a lint rule so the apiService discipline cannot regress.
3. **Length debt migrates; attack the growth driver.** Frontend length improved only because the members
   analytics work paused there and moved to SAM config-fields. Apply cohesion-seam splitting to
   `_membership_writes.py` (1940) and `_dispatch.py` (1479) — the active growth front.
4. **A table needs a mobile story at creation** — fourth cycle; enforce at review.
