# Requirements — Make the Full Test Suite Trustworthy and Green

## Purpose

The `feature/s2-jwt-verification` branch (PR #14) carries the S3/S4/S5 platform work plus a
steering refactor. When the Full Test Suite ran on it, the CI job reported **success**, but
the downloaded artifacts showed:

- **Backend:** 13 failed, 6278 passed, 10 skipped
- **Frontend:** 2386 passed, 0 failed
- **Lint:** Ruff lint + Ruff format failed (already fixed locally)

Two problems, then: (1) real test failures exist, and (2) CI reported green anyway, which is
worse than red because it hides the failures. This spec fixes **all** failures — regardless
of which branch or person introduced them — and fixes the CI reporting so a failing suite can
never again look green.

## Background — the failures, grouped (from artifact analysis)

| Group | Count | What | Origin (verified) |
| --- | --- | --- | --- |
| **G1 — Lint / format** | (fixed) | Ruff lint (52) + format (5 files) on new S3/S4 files | This branch; already auto-fixed + verified locally |
| **G2 — Dead MySQL reader in `sam/`** | 1 | `test_s3_system_of_record_scope::test_no_sam_source_reads_governance_tables_directly` | This branch (S4) |
| **G3 — Guard test false-positives** | (part of G2) | Same guard trips on docstring prose in 2 valid files | This branch (S4) |
| **G4 — `test_security_audit` endpoints return 401** | 9 | Endpoint tests expect 200/400, get 401 | **Pre-existing on `main`** (reproduced) |
| **G5 — Hypothesis flaky deadline** | 3 | Property tests exceed 200ms on first run, pass on retry | **Pre-existing on `main`** (files identical) |
| **G6 — CI reports green despite failures** | — | `pytest ... || true` swallows the failure exit code | Pre-existing CI workflow |

## Requirements

### R1 — Lint and format are clean (G1)
- **R1.1** `ruff check src/ --exclude src/validate_pattern/` exits 0 (from `backend/`).
- **R1.2** `ruff format --check src/ --exclude src/validate_pattern/` exits 0.
- **R1.3** No behavior change — only style/format edits; the touched files' tests still pass.

### R2 — The module plane holds no MySQL governance reader (G2)
- **R2.1** No file under `sam/` opens a MySQL connection or issues SQL against the governance
  tables (`user_tenant_roles`, `tenant_modules`). This is the S1/S3 contract (R3.3): a module
  Lambda gets governance facts from the token (S4) or the read-only DynamoDB projection, never
  a request-time MySQL read.
- **R2.2** The obsolete MySQL reader `sam/pretokengen/governance_reader.py` (superseded by
  `projection_governance_reader.py` under Design Amendment A) is removed, along with its test
  and any handler references to it.
- **R2.3** The PreTokenGen handler continues to work via the DynamoDB projection reader only;
  its existing tests still pass.

### R3 — The system-of-record guard test is precise (G3)
- **R3.1** `test_no_sam_source_reads_governance_tables_directly` passes.
- **R3.2** The guard must catch a **real** MySQL/SQL access to a governance table, and must
  **not** fail on a governance table name that appears only in a comment or docstring
  (documentation prose is allowed; SQL access is not).
- **R3.3** The valid DynamoDB-backed reader (`projection_governance_reader.py`) and the handler
  keep their explanatory docstrings that reference the governance tables by name.

### R4 — Security-audit endpoint tests pass (G4)
- **R4.1** The `TestSecurityEndpointsIntegration` tests in `test_security_audit.py` pass.
- **R4.2** The tests reflect the endpoints' real auth behavior: either the test harness provides
  the authentication the endpoints require, or the tests assert the correct authenticated
  behavior. The fix must not weaken real auth on the endpoints themselves.
- **R4.3** No production auth is removed or bypassed to make a test pass.

### R5 — Property-based tests are not flaky on CI timing (G5)
- **R5.1** The three Hypothesis property tests that failed with `DeadlineExceeded` no longer
  fail due to first-run timing jitter on CI.
- **R5.2** The fix preserves the property being tested (the assertion/coverage is unchanged);
  only the timing deadline is adjusted for these specific tests (e.g. `deadline=None` or a
  suitable per-test setting), consistent with Hypothesis's own guidance in the failure output.
- **R5.3** Prefer a targeted per-test/per-class setting over a global deadline change, so other
  property tests keep their timing guard.

### R6 — CI fails when tests fail (G6) — highest value
- **R6.1** The Full Test Suite backend and frontend jobs **fail** (non-zero) when any test
  fails. Remove the `|| true` (or otherwise propagate the real exit code) from the test steps
  so a red suite can never report green again.
- **R6.2** Report artifacts (SUMMARY, junit, coverage, html) are still uploaded on failure
  (keep `if: always()` on the upload/summary steps).
- **R6.3** The pass/fail summary line in the artifact still reflects the true counts.

### R7 — Verified green end-to-end
- **R7.1** Locally (matching CI scope/commands): backend `pytest tests/unit/` passes with 0
  failures; ruff lint + format clean; the SAM suite (`sam/pytest.ini`) passes; frontend tests
  pass.
- **R7.2** A fresh Full Test Suite run on the branch reports **success for the right reason**
  (all green), and — as a deliberate check — the CI change is proven to fail when a test fails.

## Out of scope

- The broader S3/S4/S5 feature work itself (already specced under `multi-tenant/`).
- The steering refactor (already committed).
- Merging PR #14 to `main` — that happens only after R7 is satisfied.

## Success criteria

All of R1–R7 met: one clean, all-green Full Test Suite run on the branch, with CI that will
actually go red on a future failure. Then PR #14 is safe to merge.
