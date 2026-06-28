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
