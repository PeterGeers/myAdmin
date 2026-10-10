# S5j — Tasks

Legend: `[ ]` todo · `[H]` human-run/gated (deploy / browser re-test) · `(dt)` test-first.
Execution per steering 34 (SAM tests via `sam/pytest.ini`), 41 (WSL paths; `<<<DONE marker=$?>>>`;
no sleep; strip `.env` AWS keys for nonprofit-deploy), frontend build via `frontend/`.

## Phase 1 — SAM: source scope-dimension choices at resolve time (R1/R2)

- [x] **1.1 (dt) Red test** DONE — `sam/tests/test_members_scope_dimension_choices.py`; 10 tests
  RED for the right reason (`MembershipService.__init__() got an unexpected keyword argument
  'scope_config_provider'`), collection clean. Covers: region choiceless-enum resolves + gets
  values; `.field` ≠ `.key`; two dimensions fill two fields; non-dimension control still raises;
  disabled dimension does not source; plus the Phase-2 change-gate matrix.
  Original: resolve a tenant whose overlay has `region`
  (`type: enum`, no choices) AND whose scope config has a `region` dimension with values.
  Assert (currently failing): field-config resolves without raising, and the resolved `region`
  field carries the dimension's values as `choices`. Add these matrix cases too:
  (a) a dimension whose `.field` DIFFERS from its `.key` — the choices land on the field named
  by `.field`, not `.key` (R1.1); (b) TWO enabled dimensions binding two different overlay enum
  fields — BOTH get their choices filled (R1.2); (c) CONTROL: a non-dimension enum with no
  choices STILL raises (R1.4); (d) a DISABLED dimension does NOT source choices.
- [x] **1.2 Implement D1a** DONE — added `scope_config_provider` to `MembershipService` +
  `_scope_vocab(tenant_id)` (builds `{dimension.field: values}` over ENABLED dimensions, keyed
  by `.field`). `FieldResolver.resolve` gained an optional `scope_vocab`: a choiceless overlay
  `enum` whose key is in the map sources its `choices` from it, and `_reject_invalid_overlay`
  no longer flags such a field (genuine choiceless non-dimension enums still rejected). Threaded
  the vocab through ALL four resolve call-sites (get_field_config + the create/update validators
  + `_validate_member_record`) so region validation is consistent. Files: `field_resolver.py`,
  `membership_service.py`.
- [x] **1.3 Confirm green** DONE — new file 10/10 green; the 4 most-affected suites
  (field_config, resolved_field_surface, write_dispatch, scope_dimension_choices) = **91 passed,
  0 failed**; full `sam/tests` run reached 100% all-dots (no F/E). Controls hold: non-dimension
  choiceless enum still raises; disabled dimension does not source.

## Phase 2 — SAM: verify the change-gated validation fires for region (R3)

- [x] **2.1 (dt) Test** DONE — `TestRegionChangeGatedValidation` (5 cases) in the new file:
  (a) CREATE region ∈ values → OK; (b) CREATE region ∉ values → error; (c) UPDATE change to ∉
  values → error; (d) UPDATE unchanged LEGACY value (∉ values) → OK (tolerate legacy);
  (e) UPDATE legacy → corrected valid value → OK. Literal change comparison (R3.3). No logic
  change — proves the EXISTING `_reject_invalid_overlay_enum_values` now activates for region
  once it has resolved (scope-sourced) choices.
- [x] **2.2 Confirm green** DONE — all 5 pass (part of the 10/10 + 91-passed runs above).

## Phase 3 — Frontend: fix the editor-load URL bug (R4)

- [x] **3.1 (dt) Test** DONE — added a URL-contract test to
  `frontend/src/services/membersConfigService.test.ts`: asserts `getMembersParameterDefinitions()`
  calls `authenticatedGet` with the RELATIVE path `/api/config/members-parameters` (no scheme,
  no doubled host) + `skipAuth: true`. Guards the exact double-prepend regression. File: 6 passed.
- [x] **3.2 Apply the fix** DONE — `getMembersParameterDefinitions()` passes the relative
  endpoint to `authenticatedGet` (base applied once); removed the unused `buildApiUrl` import.
- [x] **3.3 Type-check/build** DONE — `frontend` `tsc -b` clean (TSC_EXIT=0, no errors); the
  6 service tests green.

## Phase 4 — Ship + verify end-to-end (R5)

- [x] **4.1 Commit + PR** DONE — branch `s5j-members-config-authoring-path` off `main`, commit
  `b6bba57` (9 files), pushed (secret scan clean). **Combined PR #22** (SAM + frontend in one
  review): https://github.com/PeterGeers/myAdmin/pull/22 . On merge, SAM deploys via
  `deploy-sam-members.yml`; frontend via the GitHub Pages deploy.
- [x] **4.2 [H] Merge + deploy** DONE — PR #22 merged (merge commit `4244c0c`). BOTH pipelines
  green: `Deploy SAM Members` run 35998187250 success → `sam-members` **UPDATE_COMPLETE**
  @ 12:18:43; `Deploy Frontend to GitHub Pages` run 35998187141 **success**. (CodeQL on main
  post-merge scan non-blocking.)
- [x] **4.3 [H] Browser re-test** DONE 2026-09-24 — VERIFIED from prod: `GET /members/field-config`
  = **200** (user-confirmed in the Network tab); `members-prod` CloudWatch shows **zero
  OverlayError** since the wiring re-deploy (stack UPDATE_COMPLETE @ 12:31:32). 
  RCA of the first-deploy miss: the s5j DOMAIN fix (PR #22) was correct but the PRODUCTION WIRING
  was missing — `app.py` `_get_membership_service()` built `MembershipService` WITHOUT
  `scope_config_provider`, so `_scope_vocab()` returned `{}` in prod and region was still rejected
  (CloudWatch confirmed the OverlayError raised at the NEW `_reject_invalid_overlay(overlay,
  scope_vocab=vocab)` line — new code ran, empty vocab). My Phase-1 tests injected a provider
  directly, so they never exercised the app wiring — the gap slipped through. FIX (PR #23, merge
  `27e6449`): `_ProjectionScopeConfigProvider` (fresh-reader indirection mirroring
  `_ProjectionOverlayProvider`, honouring `_SCOPE_CONFIG_PROVIDER_OVERRIDE`) passed as
  `scope_config_provider=`; added `TestAppWiresScopeConfigProviderIntoService` so the wiring gap
  can't regress. LESSON: unit-testing a domain seam is not enough — test the production wiring
  that supplies it.
- [x] **4.4 Record** DONE — s5d rollout plan PHASE D field-config item marked RESOLVED (s5j);
  backlog "field-config 502 / region overlay choices" entry marked RESOLVED with the chosen
  option (b) + PR #22/#23 + prod verification; this tasks.md reflects the RCA + lesson.

## Phase 5 — Follow-up: empty Regio COLUMN in the table (post-deploy browser finding)

- [x] **5.1 RCA + fix** DONE 2026-09-24 — after field-config 200, the modal showed region but the
  TABLE (compact) Regio column was still empty. RCA (frontend-only, stale-refactor drift): s5d
  moved region from a retired `scope_values.region` ARRAY into the `overlay.region` SCALAR. The
  modal reads it correctly via the nested-first `valueFor()` accessor, but the table depends on a
  flat `member.region` alias that `flattenMember()` (frontend/src/services/membersApiService.ts)
  still derived from `scope_values.region` → always `undefined` → `region_display=''` → blank cell.
  FIX: `flattenMember` now derives the flat `region` from `overlay.region` (legacy `scope_values`
  kept only as a fallback); `NestedMemberRecord` gained the `overlay` bucket. HARDENING: the
  table's overlay-column cells (`MembersPage.tsx`) now resolve via the shared nested-first
  `valueFor(row, f.group, f.key)` instead of flat `row[f.key]`, so EVERY overlay column renders in
  the table exactly as in the modal (not just region).
- [x] **5.2 Tests** DONE — updated the stale `membersApiService.test.ts` cases (they asserted the
  retired `scope_values` shape + legacy `personal.name/contact` keys) to the current
  `overlay.region` + real personal keys; ADDED regressions: derive flat region from
  `overlay.region`; legacy `scope_values` fallback; undefined when neither present. 28 passed.
  (These stale tests are WHY the bug shipped — they encoded the old shape.)
- [x] **5.3 Field-mapping fixes (user remarks, frontend-only)** DONE 2026-09-24 —
  (1) **Lidnummer column**: the compact table showed no member number. Added `member_number`
  as the FIRST default compact column (filterable + sortable, standard pattern) — prepended to
  `COMPACT_FIELD_KEYS`, added `INITIAL_FILTERS.member_number`, header + cell, `columns.memberNumber`
  i18n (nl "Lidnummer" / en "Member no."), and excluded it from the overlay-column set so it isn't
  double-rendered. (2) **Modal duplicate/UUID**: the modal's top row was labeled "Lidnummer" (nl)
  but rendered the internal `member_id` UUID, while the real Lidnummer already shows in the
  Membership/Lidmaatschap group — removed that top UUID row entirely (the UUID is internal, not
  user-facing). Tests: `membersApiService` + `membersConfigService` 34 passed; get_diagnostics
  clean on all changed files.
- [x] **5.4 [H] Ship + browser re-verify** DONE 2026-09-24 — shipped via **PR #24** (merge
  `bfb1690`: region column populates, Lidnummer column added, modal UUID row removed, edit-mode
  dropdowns keep the current value visible/selected) and **PR #25** (merge `2f70912`: region cell
  rendered as a plain field, not a purple Badge — user preference). Both frontend GitHub Pages
  deploys succeeded. User-VERIFIED in the browser: the table shows the real Lidnummer (M00000…,
  not the UUID) and the Regio value; the region no longer uses the badge styling.

## Done criteria
- field-config returns 200 for h-dcn; `region` renders as a dropdown sourced from
  `scope_dimensions.values` (single source of truth; no stored duplication; no data migration).
- Change-gated validation (accept unchanged/legacy, enforce on change/create) proven for region.
- The Tenant-Admin Members editor loads (URL bug fixed + regression-tested).
- Scope/access filter unchanged. All tests green; verified in the browser.


# Use of the member table to store Sponsolrs, clubs, etc
The use of the member lidnummer check did block the storage for empty member.lidnummers. As member.lidnummer is justb a field managed by CRUD there should be no reason to block it regio fields should have Overig