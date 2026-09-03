# Code Quality Maintenance Prompt

## add item to add code reduction, dead code and duplicate code prevention

Paste this into Kiro to run the full analysis and generate fix tasks automatically.

---

## Prompt

Run the "Full Test Suite" GitHub Actions workflow for both backend and frontend. While it runs, perform a local code quality scan. Then combine all findings into an actionable spec.

### Step 1: Trigger the Full Test Suite

```bash
cd /home/peter/projects/myAdmin
gh workflow run "Full Test Suite" --field scope=both --ref $(git branch --show-current)
```

Wait for completion:

```bash
# Poll until completed
gh run list --workflow=full-test-suite.yml --limit=1 --json status,conclusion,databaseId 2>&1 | head -5
```

Download the artifacts:

```bash
RUN_ID=$(gh run list --workflow=full-test-suite.yml --limit=1 --json databaseId --jq '.[0].databaseId' 2>&1 | head -1)
gh run download $RUN_ID --dir /tmp/test-reports
```

### Step 2: Analyze test failures from downloaded reports

Read the actual report files — do NOT parse log streams or use `--log`:

```bash
# Backend test summary
cat /tmp/test-reports/backend-test-reports/test-output.txt | grep -E "(FAILED|PASSED|ERROR|passed|failed)" | tail -20

# Frontend test summary
cat /tmp/test-reports/frontend-test-reports/SUMMARY.md

# Backend failures detail
cat /tmp/test-reports/backend-test-reports/test-output.txt | grep "FAILED"
```

Extract:

- Total tests passed / failed / errored per suite
- List of each failing test with error type (Flaky, AssertionError, ImportError, etc.)
- Group failures by root cause

### Step 3: Analyze Backend Lint & Static Analysis

The CI now generates a downloadable `backend-lint-reports` artifact. Read it:

```bash
# Reports are in /tmp/test-reports/backend-lint-reports/
cat /tmp/test-reports/backend-lint-reports/SUMMARY.md
cat /tmp/test-reports/backend-lint-reports/ruff-lint.md
cat /tmp/test-reports/backend-lint-reports/ruff-format.md
cat /tmp/test-reports/backend-lint-reports/vulture.md
```

If the lint artifact is missing (older workflow version), fall back to log parsing:

```bash
LINT_JOB_ID=$(gh run view $RUN_ID --json jobs --jq '.jobs[] | select(.name=="Backend Lint & Static Analysis") | .databaseId' 2>&1 | head -1)
gh run view $RUN_ID --log --job=$LINT_JOB_ID 2>&1 | grep "##\[error\]" | sed 's/.*##\[error\]//' | cut -d: -f4 | sort | uniq -c | sort -rn > /tmp/test-reports/ruff-summary.txt
cat /tmp/test-reports/ruff-summary.txt
```

Include in the spec:

- Total ruff errors by rule code
- Which rules are auto-fixable vs manual
- Whether it's a version mismatch (local vs CI ruff version)

### Step 4: Local code quality scan

Run these locally and capture output:

1. **File length**: Find all `.py` files in `backend/src/`, `backend/src/routes/`, `backend/src/services/` and all `.ts`/`.tsx` files in `frontend/src/` exceeding 500 lines. Flag files over 1000 lines as critical.

2. **Dead code**: Run `vulture backend/src/ backend/vulture_whitelist.py --min-confidence 80 --exclude validate_pattern/` and capture findings.

3. **Missing tests**: Find backend modules (`backend/src/*.py`, `backend/src/routes/*.py`, `backend/src/services/*.py`) without corresponding test files. Find frontend components without matching test files.

4. **Type safety**: Check for Python functions in services/routes missing type hints. Check for TypeScript `any` usage in `frontend/src/`.

5. **Ruff version alignment**: Compare local `ruff --version` with CI version (check workflow file or CI logs). If mismatched, note in findings.

6. **Mobile compliance**: Verify that all frontend functions/components are optimized for mobile devices unless a component is explicitly marked as not requiring it. Treat any function/component that renders UI, handles user interaction, or affects layout as requiring mobile optimization. Flag violations where:

   - Fixed pixel widths/heights that don't adapt to small viewports (e.g. `width: 1200px`, non-responsive `min-width`) instead of responsive units (`%`, `rem`, `vw`, `clamp()`) or responsive breakpoints.
   - Missing responsive breakpoints — components with desktop-only layouts and no mobile/tablet handling (no media queries, no responsive Tailwind/MUI breakpoints like `sm:`/`md:` or `xs`/`sm` props).
   - Touch targets smaller than 44x44px (buttons, links, icons meant to be tapped).
   - Horizontal overflow risks — wide tables, grids, or flex rows without `overflow-x` handling or a mobile stacked/card fallback.
   - Hover-only interactions with no touch/tap equivalent (e.g. tooltips or menus that only appear on `:hover`).
   - Non-responsive font sizes or spacing hardcoded for desktop.
   - Viewport/meta issues — check `index.html` has `<meta name="viewport" content="width=device-width, initial-scale=1">`.

   A function/component is **exempt** only if it carries an explicit marker that it is not required to be mobile-optimized — e.g. a `// mobile-exempt:` comment, a `data-mobile-exempt` attribute, or an entry in a documented exemption list. Record exempt items separately (do not count them as violations) so reviewers can audit the exemptions.

   Suggested scan:

   ```bash
   # Fixed pixel widths (heuristic — review matches)
   grep -rn "width:\s*[0-9]\{3,\}px\|minWidth:\s*[0-9]\{3,\}\|min-width:\s*[0-9]\{3,\}px" frontend/src/ --include="*.ts" --include="*.tsx" --include="*.css" | grep -vi "mobile-exempt"

   # Components with no responsive breakpoints (no media queries / no responsive props)
   grep -rLn "@media\|sm:\|md:\|lg:\|breakpoints\|useMediaQuery" frontend/src/ --include="*.tsx" | grep -vi "mobile-exempt"

   # Hover-only interactions
   grep -rn ":hover" frontend/src/ --include="*.css" --include="*.tsx" | grep -vi "mobile-exempt"

   # Explicitly exempt items (record separately, do not flag)
   grep -rn "mobile-exempt" frontend/src/
   ```

Exclude: test files, `.venv/`, `node_modules/`, `__pycache__/`, `build/`, `dist/`, `.hypothesis/`, `mysql_data/`.

### Step 5: Generate the spec

Create a new spec at `.kiro/specs/code-quality-maintenance/code-quality-fixes-YYYY-MM-DD/` (use today's date) containing:

**requirements.md**: Summary of all findings with counts:

- Test failures: X backend, Y frontend (grouped by root cause)
- Lint failures: N ruff errors (grouped by rule code, auto-fixable vs manual)
- File length violations: N files over 500 lines, M over 1000
- Dead code: N items
- Missing test coverage: N modules without tests
- Type safety: N issues
- Mobile compliance: N components/functions not mobile-optimized (plus M explicitly exempt, listed separately)
- Stale documentation: N outdated files

**tasks.md**: Actionable fix tasks grouped by priority:

1. **Critical** — test import errors and broken fixtures (tests that can't even collect)
2. **High** — test assertion failures (tests that run but fail), ruff lint errors (CI-blocking)
3. **Medium** — file length violations over 1000 lines, dead code removal
4. **Low** — missing test coverage, type hints, stale documentation, files 500-1000 lines

Mobile compliance violations should be prioritized by user impact: **High** for components that are unusable on mobile (horizontal overflow, touch targets too small, no responsive layout on primary user flows), **Medium** for degraded-but-usable issues (hover-only interactions with keyboard/tap fallback missing, non-responsive spacing), **Low** for cosmetic issues on secondary/admin-only screens.

Each task should have: file path, specific action, estimated effort (S/M/L).

Do NOT fix the issues — only generate the spec with the analysis and task list.

### Step 6: Compare with previous run

Check `.kiro/specs/code-quality-maintenance/` for the most recent previous spec (e.g. `code-quality-fixes-YYYY-MM-DD/`). If one exists:

1. Compare failure counts — are they going down?
2. Identify **recurring failures** that were "fixed" last time but reappear. Flag these prominently.
3. Identify **new failures introduced by the previous fix sprint** (regression from refactoring).
4. Add a "Lessons / Recurring Issues" section to requirements.md noting patterns that keep coming back.

### Step 7: Clean up downloaded reports

After generating the spec, remove temporary files:

```bash
rm -rf /tmp/test-reports
```

---

## Terminal Rules

**CRITICAL: All terminal commands must use bash/Linux syntax.**

- The workspace runs on WSL Ubuntu at `/home/peter/projects/myAdmin`
- Use `cat`, `grep`, `wc -l`, `head`, `tail`, `sed`, `find`, `sort`, `uniq` — standard Linux tools
- Use `2>&1 | head -N` or `2>&1 | tail -N` to limit output (avoids pager issues)
- NEVER use PowerShell cmdlets, Windows paths, or `Get-Content`
- Always pipe through `head`/`tail` to prevent `less`/pager from blocking the terminal
- Set `GH_PAGER=""` if `gh` commands hang on output

---

## Lessons Learned (from 2026-06-27 → 2026-06-29 → 2026-08-03 cycles)

These rules must be followed when executing the generated tasks:

### Rule 1: Delete tests for removed modules — don't plan workarounds

When a source module is deleted/renamed and tests fail on `ModuleNotFoundError` or `ImportError`, the correct action is to **delete or rewrite the test file**. Do not mark the task done with "move to PYTHONPATH" or "will fix later."

### Rule 2: Run affected tests after each refactoring task

Every file split or structural change must be followed by running the tests that reference the changed module. A task is not done until those tests pass. The task description should include: "Verify: `pytest tests/unit/test_<module>.py -v` passes."

### Rule 3: Update test fixtures when adding guards/decorators

When adding auth decorators, module guards, or function guards to a route, search for existing tests on that endpoint (`grep -r "route_path" backend/tests/`) and update their fixtures in the same commit. Otherwise the tests will silently break.

### Rule 4: Grep all tests when changing defaults

When changing a default value (e.g. storage provider, API endpoint, response format), grep the **entire test suite** for the old value — not just the obvious test file. Use: `grep -r "old_value" backend/tests/ frontend/src/` to find all dependents.

### Rule 5: Never mark the spec complete until CI is green

The final implicit task of any quality spec is: "Full Test Suite passes with 0 failures." If CI still shows failures after all tasks are checked off, the spec is not done. Add a verification step:

```bash
gh workflow run "Full Test Suite" --field scope=both --ref $(git branch --show-current)
# Wait for completion, then verify:
# Backend: 0 failures
# Frontend: 0 failures
# Lint: 0 errors
```

Only then close the spec.

### Rule 6: Tasks.md must include verification commands

Each task in tasks.md should end with a concrete verification command, e.g.:

```
Verify: pytest backend/tests/unit/test_storage_resolver.py -v (expect 4 pass)
Verify: npx vitest run src/components/TenantAdmin/ChartOfAccounts.test.tsx (expect 8 pass)
```

This prevents marking tasks done without confirming the fix works.

### Rule 7: Always run the Full Test Suite on the feature branch — not main

When triggering `gh workflow run`, always specify `--ref <feature-branch>`. Running on main tests code that doesn't include your changes.

### Rule 8: Pin ruff version — or check CI version first

The CI installs ruff via `pip install ruff` (latest). Before running local lint checks, verify your local ruff version matches CI. If there's a mismatch:

```bash
# Check CI version from workflow logs or install the same:
pip install ruff==<ci-version>
```

A ruff version upgrade can introduce hundreds of new rules. The fix strategy is:

1. `ruff check src/ --fix --unsafe-fixes` (auto-fix what's possible)
2. `ruff check src/ --add-noqa` (suppress intentional patterns)
3. `ruff format src/` (fix formatting)
4. Manually fix remaining misplaced `noqa` comments

### Rule 9: Read CI artifacts (zip reports) — don't scrape log streams

The CI generates downloadable report artifacts (test-output.txt, SUMMARY.md, junit-results.xml). Always download and read these with `cat`/`grep` rather than parsing raw log output with `gh run view --log`. Log streams are noisy, paginated, and unreliable.

### Rule 10: Commit and push before triggering CI

The Full Test Suite runs against committed code on GitHub. Local changes that haven't been pushed will NOT be tested. Always:

1. Fix the issues locally
2. Verify locally (ruff check, pytest, etc.)
3. `git add -A && git commit && git push`
4. THEN trigger the workflow on the feature branch

### Rule 11: Hypothesis flaky tests are chronic — fix aggressively

Every Hypothesis property test in CI should have `@settings(derandomize=True, deadline=None)`. CI timing variability means:

- `deadline=200ms` will fail randomly (tests take 300-600ms on CI runners)
- Without `derandomize=True`, tests falsify non-deterministically

When a Hypothesis test fails as "Flaky", add BOTH `derandomize=True` AND `deadline=None` — not just one.

### Rule 12: Clean up junk files before committing

After terminal issues or pager problems, check for garbage files in the repo root:

```bash
find . -maxdepth 1 -name "*2>*" -o -name "*cat*" | grep -v .git
```

Remove them before committing to avoid pre-push hook failures (gitguardian scans all staged files).

### Rule 13: Include Lint & Static Analysis as a blocking task

Ruff lint failures block the CI workflow just like test failures. The tasks.md must include a task for "Ruff lint passes" with the same priority as test failures. The verification is:

```bash
ruff check src/ --exclude src/validate_pattern/
ruff format --check src/ --exclude src/validate_pattern/
vulture src/ vulture_whitelist.py --min-confidence 80 --exclude validate_pattern/
```

### Rule 14: Mobile-first is the default — desktop-only is the exception

Every frontend function/component that renders UI or handles interaction must be mobile-optimized unless it carries an explicit exemption marker (`// mobile-exempt: <reason>`, `data-mobile-exempt`, or a documented exemption list entry). When adding or refactoring a component:

1. Use responsive units and breakpoints (`%`, `rem`, `vw`, `clamp()`, Tailwind `sm:`/`md:`, MUI `useMediaQuery`/breakpoint props) instead of fixed pixel dimensions.
2. Ensure tap targets are at least 44x44px.
3. Give wide tables/grids a mobile fallback (horizontal scroll container or stacked card layout).
4. Provide a touch/tap equivalent for any hover-only interaction.

If a component genuinely does not need mobile support (e.g. an internal desktop-only admin tool), add the exemption marker with a reason so it is recorded — never silently skip it. The mobile compliance scan (Step 4, item 6) must run every cycle, and violations must appear in tasks.md prioritized by user impact.
