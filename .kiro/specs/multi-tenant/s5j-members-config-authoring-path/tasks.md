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
- [~] **4.3 [H] Browser re-test** — FIRST DEPLOY (PR #22) STILL 502'd. RCA: the DOMAIN fix was
  correct but the PRODUCTION WIRING was missing — `app.py` `_get_membership_service()` built
  `MembershipService` WITHOUT `scope_config_provider`, so `_scope_vocab` was empty in prod and
  region was still rejected (CloudWatch confirmed the OverlayError now raised at the NEW
  `_reject_invalid_overlay(overlay, scope_vocab=vocab)` line — i.e. new code ran, empty vocab).
  My Phase-1 tests injected a provider directly, so they never exercised the app wiring — the
  gap slipped through. FIX (branch `s5j-wire-scope-config-provider`): added
  `_ProjectionScopeConfigProvider` (fresh-reader indirection, mirrors `_ProjectionOverlayProvider`,
  honours `_SCOPE_CONFIG_PROVIDER_OVERRIDE`) and passed it as `scope_config_provider=` in the
  service construction; ADDED an app-wiring test (`TestAppWiresScopeConfigProviderIntoService`)
  that drives the real `_SCOPE_CONFIG_PROVIDER_FOR_SERVICE` so the gap can't regress. Affected
  suites 60 passed / 0 failed. Awaiting re-deploy + browser re-test.
- [ ] **4.4 Record** — mark s5d PHASE D field-config item resolved; close the backlog "region
  overlay choices" entry; note s5j in the rollout plan.

## Done criteria
- field-config returns 200 for h-dcn; `region` renders as a dropdown sourced from
  `scope_dimensions.values` (single source of truth; no stored duplication; no data migration).
- Change-gated validation (accept unchanged/legacy, enforce on change/create) proven for region.
- The Tenant-Admin Members editor loads (URL bug fixed + regression-tested).
- Scope/access filter unchanged. All tests green; verified in the browser.
