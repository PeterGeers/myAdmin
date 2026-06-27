# Code Quality Maintenance — Monthly Scan Prompt

Paste this prompt into Kiro to run a code quality scan and generate a task list for fixing findings.

---

## Prompt

Scan the myAdmin codebase for code quality issues and create a new spec with a tasks.md to fix the findings. Specifically:

1. **File length**: Find all `.py` files in `backend/src/` and `backend/src/routes/` and `backend/src/services/`, and all `.ts`/`.tsx` files in `frontend/src/` that exceed 500 lines. Flag errors for files over 1000 lines.

2. **Missing tests**: Find backend modules (`backend/src/*.py`, `backend/src/routes/*.py`, `backend/src/services/*.py`) without corresponding test files in `backend/tests/unit/` or `backend/tests/api/`. Find frontend components (`frontend/src/components/**/*.tsx`) and services (`frontend/src/services/*.ts`) without matching `.test.tsx`/`.test.ts` files.

3. **Dead code**: Run vulture on the backend Python code (`backend/src/`) and identify unused functions, imports, and variables. Check frontend for unused exports in `frontend/src/services/` and `frontend/src/utils/`.

4. **Type safety**: Check for Python functions in `backend/src/services/` and `backend/src/routes/` missing type hints on parameters or return values. Check for TypeScript `any` usage in `frontend/src/`.

5. **Stale documentation**: Check if `Manuals/` and `manualsSysAdm/` files are outdated relative to recent code changes. Check for outdated comments referencing removed functionality.

Exclude: test files, `.venv/`, `node_modules/`, `__pycache__/`, `build/`, `dist/`, `.hypothesis/`, `*.generated.*`, `mysql_data/`.

Then create a new spec at `.kiro/specs/code-quality-fixes-YYYY-MM/` with:

- requirements.md summarizing the findings with counts per category
- tasks.md with a structured, actionable task list to fix each finding, grouped by category (file length → dead code → missing tests → type safety → stale docs), with file paths and specific actions

Use "Quick Plan" workflow. Name the spec with the current month / day, code-quality-fixes-2026-06-29

---

## Full Test Suite Workflow

A manual-trigger GitHub Actions workflow (`full-test-suite.yml`) runs the complete test suites for frontend and backend, generates reports, and uploads them as downloadable artifacts.

### How to use

1. Go to GitHub → Actions → "Full Test Suite"
2. Click "Run workflow" → choose scope (both / backend / frontend)
3. Wait for completion (~3-5 minutes)
4. Download the artifact ZIP files (backend-test-reports, frontend-test-reports)
5. Review the reports: `SUMMARY.md`, `test-report.html` (backend), `junit-results.xml`, `test-output.txt`

### Process: Run → Analyze → Fix

1. **Run**: Trigger the workflow manually when you want a full health check
2. **Analyze**: Download artifacts, review SUMMARY.md for pass/fail counts, identify patterns in failures
3. **Define tasks**: Use the code-quality-maintenance scan prompt above to generate a spec with actionable fix tasks based on findings

### Reports included

| Report              | Description                                              |
| ------------------- | -------------------------------------------------------- |
| `SUMMARY.md`        | Quick pass/fail overview                                 |
| `test-output.txt`   | Full console output                                      |
| `junit-results.xml` | Machine-readable results (can import into CI dashboards) |
| `test-report.html`  | Interactive HTML report (backend only)                   |
| `coverage-html/`    | Line-by-line coverage report (backend only)              |
| `coverage.xml`      | Coverage data for tooling integration                    |

### Known issues to address

- **Backend**: broken test imports, missing module fixtures, tests depending on live DB
- **Frontend**: 24 component tests with stale selectors (TenantManagement, ChartOfAccounts, StorageTab, InvoiceTestTool, aws-exports)
- These are pre-existing issues exposed when CI added test execution
