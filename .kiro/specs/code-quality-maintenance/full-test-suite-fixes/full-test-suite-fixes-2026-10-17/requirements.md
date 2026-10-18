# Requirements Document

# Full Test Suite Fixes — 2026-10-17 (run #74, dispatched on `test`)

## Introduction

CI-analysis spec (not a feature): captures the failures from one **Full Test Suite** run and defines the fix tasks, per the `prompt-test-suite-results.md` runbook. Outcomes below are what make the run green and safe to promote `test -> main`.

## Source

GitHub Actions **Full Test Suite** run **#74** (id `39072218600`), `workflow_dispatch` on branch **`test`** @ `c07927f44` (merge commit of PR #122, membership-type-catalog-admin-ui; the run also includes PR #121, members-config-projection-and-cleanup). Conclusion: FAILURE. Analyzed purely from downloaded CI artifacts (`backend-test-reports`, `sam-test-reports`, `frontend-test-reports`, `backend-lint-reports`) — no local scans.

Dispatched as the promotion gate before a `test -> main` release.

## Findings summary

| Suite | Result |
| --- | --- |
| **SAM Module-Plane** | GREEN — all tests pass (dots-only, 100%) |
| **Backend** | 1 failed / 7330 passed / 14 skipped (678.62s) |
| **Frontend** | 2 failed tests / 2 failed files; 3859 passed, 12 skipped (3873) |
| **Backend Ruff Format** | FAIL (CI-blocking) — 2 files would be reformatted |
| Backend Ruff Lint | PASS · Vulture PASS |
| Frontend tsc / ESLint | REPORT-ONLY — tsc 2 known pre-existing errors; ESLint all warnings |
| SAM ruff lint | REPORT-ONLY — 95 findings, SAM job green |

**Net: every red in this run traces to the two just-merged PRs (#121 projection content-gate + view_contexts retirement, #122 catalog UI).**

### Test failures

#### Backend — 1 (Hypothesis property, projection convergence)
- **Test**: `backend/tests/unit/test_projection_convergence_props.py::test_projection_converges_after_a_source_change` (line 368).
- **Error**: `ExceptionGroup: Hypothesis found 2 distinct failures`:
  - `assert item[VERSION_ATTR] == new_version` -> `AssertionError: assert 0 == 1` (line 440).
  - `assert item["is_active"] is expectation["value"]` -> `AssertionError: assert True is False` (line 439).
- **Root cause (to confirm in fix)**: the convergence property asserts the post-sync stored row reflects the new source `version`/`is_active` after a source change. PR #121 made the write decision **content-driven** and **dropped the strictly-greater version datastore gate** (design A3 option (a), last-writer-wins). The property test still encodes the OLD version-monotonic expectation (a source change always advances `version`; `is_active` flips deterministically). This is a **change-with-tests miss** in PR #121: a property test paired to `projection_sync` behaviour was not realigned to the content-gate semantics. Must align the property to the intended new behaviour (content drives the write; version is bookkeeping) WITHOUT weakening it — or, if it reveals a real convergence defect in the content gate, fix the gate. Decide from the counterexample.

#### Frontend — 2 (stale `view_contexts` status tests)
- **Tests**:
  - `src/components/TenantAdmin/MembersConfig/__tests__/MembersConfigEditor.test.tsx > MembersConfigEditor — status banner > renders the delivered/loaded status from the module config_status` — `Unable to find [data-testid="members-config-status-views-badge"]`.
  - `src/components/TenantAdmin/MembersConfig/__tests__/MembersConfigStatus.test.tsx > MembersConfigStatus > shows Not yet delivered for a null version` — `Unable to find [data-testid="members-config-status-views"]`.
- **Root cause**: PR #121 RETIRED `view_contexts`/`config#views`, so the projection-status banner no longer renders a `views` row/badge. These two tests still assert the retired `views` status element. A **change-with-tests miss** in PR #121: the `view_contexts` retirement updated the frontend key declaration + its service test but NOT these two status-banner tests. Fix = update/remove the `views` expectations to the retired reality (do not weaken the surviving `fields`/`scope`/`mail` assertions).

### Lint failures

#### Backend Ruff Format — CI-BLOCKING (the other reason the run is red)
2 files would be reformatted — **both from PR #121**:
- `backend/src/migrations/retire_members_view_contexts.py:125` — a `logger.info(...)` call ruff wants wrapped across lines.
- `backend/src/services/parameter_service.py:673` — an `if` comprehension clause ruff wants split across lines.
Auto-fixable with `ruff format`. Root cause: PR #121 landed functionally-correct but not `ruff format`-clean code; the pre-commit hook ran the DB-access guard but not `ruff format`, so the format drift reached CI. **CI-blocking** — treat with test-failure priority.

#### Report-only (non-blocking)
- Frontend **tsc**: 2 PRE-EXISTING unrelated errors — `PublicApplicationForm.axe.test.tsx` (`toHaveNoViolations` matcher typing) + `useApplicationsInbox.test.ts` (Mock assignability). Known/deferred (see Members specs); not introduced here.
- Frontend **ESLint**: all `warning`, no `error` (unused-vars, no-explicit-any, import-x/order across many files — standing debt).
- **SAM ruff lint**: 95 findings by rule (`25 I001, 13 RUF022, 11 UP037, 10 RUF100, 8 F401, ...`); SAM job green. Pre-existing SAM debt, out of scope for this gate.

## Comparison with the previous run (Step 5)

Prior comparable CI spec: `full-test-suite-fixes-2026-10-15b` (run #73, `test`, PR #115) — down to a single `MembersPage` async-settle flake; SAM green.

- **Direction**: run #74 has **more reds than #73** (0 -> 1 backend + 1 -> 2 frontend + a NEW CI-blocking ruff-format fail), all introduced by PRs #121/#122. This is a **regression spike from the two Members config merges**, not convergence.
- **Recurring pattern — change-with-tests misses on a Members config refactor**: 3 of the 4 reds (backend convergence property, 2 frontend status tests) are paired tests NOT realigned when PR #121 changed projection-write semantics + retired `view_contexts`. This is the same class the `30-backend-api-flask-mysql` "Change-With-Tests Contract" warns is the top recurring CI failure, and it recurred exactly as warned.
- **NEW failure introduced by the fix sprint**: the ruff-format fail is net-new, from PR #121's un-formatted lines. Did not exist in #73.
- **MembersPage async-settle flake (10-15b H1)**: did NOT recur in #74 (that test passed).

## Lessons / Recurring issues

1. **A behaviour change in `projection_sync` MUST realign its property/convergence tests in the SAME change.** PR #121 changed the write gate from version-monotonic to content-driven but left `test_projection_convergence_props` asserting the old version/`is_active` monotonic expectation. Change-with-tests covers PROPERTY tests too, not just example tests.
2. **A retirement (`view_contexts`) MUST sweep ALL paired tests, including status-banner/UI tests.** PR #121 updated the service test + key declaration but missed the two `MembersConfig` status-banner tests still asserting a `views` badge. Grep the whole test tree for the retired token (`views`, `config#views`, `members-config-status-views`) before calling a retirement done.
3. **`ruff format` is a CI-blocking gate and the pre-commit hook does NOT run it.** PR #121's committed code was not `ruff format`-clean (2 files) and reached CI red. Run `ruff format --check backend/ sam/` locally before pushing a backend change, or add it to the pre-commit hook.
4. **Batching two Members-config PRs onto `test` before a full-suite run concentrated the regressions.** Run the Full Test Suite (or at least the changed-plane paired tests incl. property tests) per-PR, not only after batching, so a change-with-tests miss is caught at its own PR.
