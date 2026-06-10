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

Use "Quick Plan" workflow. Name the spec with the current month (e.g., code-quality-fixes-2026-06).
