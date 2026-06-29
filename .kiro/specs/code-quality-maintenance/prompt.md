# Code Quality Maintenance Prompt

Paste this into Kiro to run the full analysis and generate fix tasks automatically.

---

## Prompt

Run the "Full Test Suite" GitHub Actions workflow for both backend and frontend. While it runs, perform a local code quality scan. Then combine all findings into an actionable spec.

### Step 1: Trigger the Full Test Suite

```bash
cd /home/peter/projects/myAdmin
gh workflow run "Full Test Suite" --field scope=both
```

Wait for completion and download the reports:

```bash
gh run list --workflow="Full Test Suite" --limit 1 --json databaseId -q ".[0].databaseId" | xargs -I{} gh run download {} --dir /tmp/test-reports
```

### Step 2: Analyze test failures

Read the downloaded reports (`/tmp/test-reports/backend-test-reports/test-output.txt` and `/tmp/test-reports/frontend-test-reports/test-output.txt`). Extract:

- Total tests passed / failed / errored per suite
- List of each failing test file with the error type (import error, assertion failure, missing fixture, env var)
- Group failures by root cause

### Step 3: Local code quality scan

Run these locally and capture output:

1. **File length**: Find all `.py` files in `backend/src/`, `backend/src/routes/`, `backend/src/services/` and all `.ts`/`.tsx` files in `frontend/src/` exceeding 500 lines. Flag files over 1000 lines as critical.

2. **Dead code**: Run `vulture backend/src/ --min-confidence 80 --exclude validate_pattern/` and capture findings.

3. **Missing tests**: Find backend modules (`backend/src/*.py`, `backend/src/routes/*.py`, `backend/src/services/*.py`) without corresponding test files. Find frontend components without matching test files.

4. **Type safety**: Check for Python functions in services/routes missing type hints. Check for TypeScript `any` usage in `frontend/src/`.

5. **Stale documentation**: Check if `Manuals/` and `manualsSysAdm/` files reference removed features or outdated workflows. Check for code comments referencing removed functionality or old file paths.

Exclude: test files, `.venv/`, `node_modules/`, `__pycache__/`, `build/`, `dist/`, `.hypothesis/`, `mysql_data/`.

### Step 4: Generate the spec

Create a new spec at `.kiro/specs/code-quality-fixes-YYYY-MM-DD/` (use today's date) containing:

**requirements.md**: Summary of all findings with counts:

- Test failures: X backend, Y frontend (grouped by root cause)
- File length violations: N files over 500 lines, M over 1000
- Dead code: N items
- Missing test coverage: N modules without tests
- Type safety: N issues
- Stale documentation: N outdated files

**tasks.md**: Actionable fix tasks grouped by priority:

1. **Critical** — test import errors and broken fixtures (tests that can't even collect)
2. **High** — test assertion failures (tests that run but fail)
3. **Medium** — file length violations over 1000 lines, dead code removal
4. **Low** — missing test coverage, type hints, stale documentation, files 500-1000 lines

Each task should have: file path, specific action, estimated effort (S/M/L).

Do NOT fix the issues — only generate the spec with the analysis and task list.

### Step 5: Compare with previous run

Check `.kiro/specs/code-quality-maintenance/` for the most recent previous spec (e.g. `code-quality-fixes-YYYY-MM-DD/`). If one exists:

1. Compare failure counts — are they going down?
2. Identify **recurring failures** that were "fixed" last time but reappear. Flag these prominently.
3. Identify **new failures introduced by the previous fix sprint** (regression from refactoring).
4. Add a "Lessons / Recurring Issues" section to requirements.md noting patterns that keep coming back.

---

## Lessons Learned (from 2026-06-27 → 2026-06-29 cycle)

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
gh workflow run "Full Test Suite" --field scope=both
# Wait for completion, then verify:
# Backend: 0 failures
# Frontend: 0 failures
```

Only then close the spec.

### Rule 6: Tasks.md must include verification commands

Each task in tasks.md should end with a concrete verification command, e.g.:

```
Verify: pytest backend/tests/unit/test_storage_resolver.py -v (expect 4 pass)
Verify: npx vitest run src/components/TenantAdmin/ChartOfAccounts.test.tsx (expect 8 pass)
```

This prevents marking tasks done without confirming the fix works.
