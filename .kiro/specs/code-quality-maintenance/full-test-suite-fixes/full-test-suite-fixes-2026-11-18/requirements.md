# Requirements Document

# Full Test Suite Fixes — 2026-11-18 (run 44199159239)

## Introduction

CI-analysis spec (not a feature): captures the failures of one **Full Test Suite** run and
records the fix tasks, per the `prompt-test-suite-results.md` runbook. This run is a
**feature-branch dispatch** (`workflow_dispatch`), not the nightly on `main`: it was dispatched
to prove the Option B migration branch green before promotion.

## Glossary

- **Full_Test_Suite**: the `full-test-suite.yml` GitHub Actions workflow (backend + SAM +
  frontend suites + backend lint/static analysis).
- **Option B**: the migration that retired the frontend-written Flask
  `members.scope_dimensions` mirror; three Flask readers now resolve the vocabulary from the
  projected `config#scope` row via `backend/src/services/scope_vocabulary.py`, and
  `MembersProjectionReader.get_scope_config` takes an injectable `ProjectionSync.reader`.
- **FakeParameterService**: the SAM test double that stands in for the parameter service inside
  `sam/tests/test_scope_e2e.py`.
- **Change-with-tests miss**: a behaviour change whose paired/related tests were not realigned in
  the same change, so the suite only goes red later.
- **Run 44199159239**: the analyzed Full_Test_Suite run (id `44199159239`), event
  `workflow_dispatch`, branch `spec/admin-surface-registry-fts`, head `a26e3561a`. FAILURE.

## Source

GitHub Actions **Full Test Suite** run **44199159239**, event **`workflow_dispatch`**, branch
**`spec/admin-surface-registry-fts`** @ **`a26e3561a`** (the Option B code commit; the branch tip
has since advanced by one docs-only commit, `b99d94e44`). Conclusion: **FAILURE**.
Analyzed purely from downloaded CI artifacts (`backend-test-reports`, `sam-test-reports`,
`frontend-test-reports`, `backend-lint-reports`). Local re-runs were not used as evidence.

### Result matrix

| Job | Result | Evidence |
|-----|--------|----------|
| Frontend Full Test Suite | PASS | 365 files, 4534 passed / 12 skipped |
| SAM Module-Plane Test Suite | FAIL | 4 failed, all `AttributeError: 'FakeParameterService' object has no attribute 'get_item'` |
| Backend Full Test Suite | FAIL | 9 failed, 7694 passed / 14 skipped — all `assert 400 == 200` |
| Backend Lint & Static Analysis | FAIL | 1 ruff error (`RUF059`); ruff format PASS; vulture PASS |

## Requirements

### Requirement 1: The Option B branch is green again

**User Story:** As a maintainer, I want `spec/admin-surface-registry-fts` to pass the Full Test
Suite, so that the Option B migration can be promoted without carrying known reds.

#### Acceptance Criteria

1. WHEN the Full_Test_Suite runs after the fix, THE backend suite SHALL report 0 failed tests
   (the 9 `assert 400 == 200` failures pass).
2. WHEN the Full_Test_Suite runs after the fix, THE SAM suite SHALL report 0 failed tests
   (the 4 `get_item` failures pass).
3. THE backend lint checks SHALL be green again (0 ruff errors).
4. THE frontend suite SHALL remain at 0 failures (it is already green; no regression).
5. THE fix SHALL NOT restore the retired mirror: the option-B end-state (one authoritative
   `config#scope` writer, readers resolving through `scope_vocabulary.py`) SHALL be preserved.

### Requirement 2: The test doubles track the reader contract

**User Story:** As a maintainer, I want the SAM test doubles to implement the reader contract, so
that a reader refactor does not silently invalidate the e2e suite.

#### Acceptance Criteria

1. THE `FakeParameterService` used by `sam/tests/test_scope_e2e.py` SHALL implement `get_item`
   with the same shape the production reader exposes.
2. WHEN `scope_vocabulary.load_scope_dimensions` is called with any test double, THE call SHALL
   either succeed or fail with a domain error — never with `AttributeError`.

### Requirement 3: The red suite is triaged by root cause, not by symptom

**User Story:** As a maintainer, I want each failure assigned to a root cause, so that fixes target
causes and the dependency order is explicit.

#### Acceptance Criteria

1. THE 4 SAM failures SHALL be attributed to the reader-contract gap in the test double.
2. THE 9 backend failures SHALL be attributed either to a genuine 400 regression or to stale
   expectations in the two trigger suites, and the chosen attribution recorded before fixing.
3. THE 1 backend lint error SHALL be attributed to the unused `conn` unpack in
   `src/tenant_module_routes.py:304`.

## Lessons / Recurring Issues

1. **A reader refactor invalidates test doubles, not just tests.** Option B changed *how* the
   vocabulary is fetched (injected reader + `get_item`) while every assertion stayed valid. The
   SAM suite went red purely in its fake. When changing a collaborator contract, grep for test
   doubles implementing that collaborator, in the same change.
2. **Status-code assertions hide the reason.** All 9 backend failures read `assert 400 == 200`
   with no further detail in the summary. Triage must open the captured response body before
   choosing between "fix the route" and "re-align the test".
3. **Lint stays in the same job as the suite.** One `RUF059` red-lined the whole lint job while
   ruff format and vulture were green; treat lint findings as CI-blocking, never as cosmetic.
4. **Comparative note.** The previous FTS spec (2026-10-28) was a nightly on `main` about two
   frontend `AnalyticsStateNotice` tests — a different class entirely. Nothing here is a
   recurrence; all four red groups are new and originate in the Option B change itself.
5. **Run-vs-branch drift.** The run analysed `a26e3561a`; the branch tip is now `b99d94e44`
   (docs only, 5 files under `.kiro/`). Fixes land on the tip; the re-verification must dispatch
   on the tip, and the code delta is provably zero.
