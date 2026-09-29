# Full Test Suite Status 2026-09-27 — Tasks

**The analyzed CI run is GREEN** (run `36298666527`, all planes pass). There are **no fix tasks** — the failures from `full-test-suite-fixes-2026-09-26/` are all resolved and confirmed in CI. Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h.

## Critical / High / Medium — none

No blocking test or lint failures on this run. Nothing to fix.

## Low — optional follow-ups (not from failures; from report-only backlogs + hygiene)

These are opportunistic; none block CI. Prefer running them via `prompt-code-quality.md` (the local code-quality scan) rather than this CI runbook.

- [ ] **L1. Burn down the SAM ruff report-only backlog (493 findings).** [M]
  - **File(s)**: `sam/**/*.py` (config `backend/ruff.toml`).
  - **Action**: `cd sam && ruff check . --config ../backend/ruff.toml --fix` clears the bulk (mostly auto-fixable); review the residual (ISC004/F811/C408 and any manual). Then consider flipping the SAM report-only lint step to blocking in `full-test-suite.yml`.
  - **Verification**: `ruff check sam/ --config backend/ruff.toml` → 0 findings; SAM tests still green (`pytest sam/tests -q`).

- [ ] **L2. Reduce the frontend ESLint backlog (1105 problems: 5 errors, 1100 warnings).** [L]
  - **File(s)**: `frontend/src/**`.
  - **Action**: `cd frontend && npx eslint src --fix` clears ~176 automatically (many `import-x/order`); triage the 5 errors first. Warnings can be reduced incrementally.
  - **Verification**: `npx eslint src` error count → 0 (then reduce warnings over time); frontend tests still green.

- [ ] **L3. Consider flipping the frontend `tsc --noEmit` check to blocking.** [S]
  - **File(s)**: `.github/workflows/full-test-suite.yml` (frontend-tests job, TypeScript typecheck step).
  - **Action**: `tsc --noEmit` is already **clean (0 errors)** on this run, so it is the safest report-only check to promote to blocking — do this only if the team wants the gate; keep report-only otherwise.
  - **Verification**: a deliberate type error fails the frontend job; a clean tree passes.

- [ ] **L4. Fix the stale cross-reference in the runbook.** [S]
  - **File(s)**: `.kiro/specs/code-quality-maintenance/prompt-test-suite-results.md` ("Lessons Learned Reference" section).
  - **Action**: it points at `prompt.md`, which was renamed to `prompt-code-quality.md` this session and refocused to drop the CI Lessons rules. Update the reference (or inline the two/three CI rules it actually depends on) so the runbook is self-contained.
  - **Verification**: the referenced path resolves; `grep -n "prompt.md" .kiro/specs/code-quality-maintenance/prompt-test-suite-results.md` returns nothing stale.

## Full-suite verification

The suite is already green in CI. To re-confirm locally or on demand:

- `gh run list --workflow=full-test-suite.yml --limit=1` → latest conclusion `success`
- Or dispatch a fresh run: `gh workflow run full-test-suite.yml --ref main -f scope=all`
