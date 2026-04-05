# Design — IDE & Workflow Improvements

## 1. Hooks

### 1.1 Backend Lint on Save

- Hook type: `fileEdited` on `backend/**/*.py`
- Command: `cd backend && python -m ruff check --output-format=concise 2>&1 | tail -20`
- Fallback: `flake8 --max-line-length=120` if ruff not installed
- Install: `pip install ruff` (add to requirements.txt dev dependencies)

### 1.2 Frontend Type Check on Save

- Hook type: `fileEdited` on `frontend/**/*.ts, frontend/**/*.tsx`
- Command: `cd frontend && npx tsc --noEmit 2>&1 | tail -20`
- Uses existing tsconfig.json strict mode settings

### 1.3 Commit Guard

- Hook type: `userTriggered`
- Command sequence:
  1. `cd backend && python -m ruff check . && python -m pytest tests/unit/ -x -q`
  2. `cd frontend && npx eslint . && npx react-scripts test --watchAll=false --ci`
- Combined exit code determines pass/fail

### 1.4 Migration Safety Check

- Hook type: `fileEdited` on `backend/**/*.sql, backend/**/migrations/**/*.py`
- Action: `askAgent`
- Prompt: Review the SQL/migration for destructive operations

### 1.5 Pre-Task Design Review

- Hook type: `preTaskExecution`
- Action: `askAgent`
- Prompt: Review the spec's design.md and requirements.md before starting

## 2. Steering Files

### 2.1 API Conventions (`api-conventions.md`)

- Inclusion: `auto`
- URL pattern: `/api/v1/{resource}` (plural nouns)
- Methods: GET (list/detail), POST (create), PUT (update), DELETE (remove)
- Response format: `{ "success": bool, "data": ..., "error": { "code": str, "message": str } }`
- Auth: All endpoints require JWT via `@require_auth` decorator
- Pagination: `?page=1&per_page=25`
- Tenant isolation: All queries scoped by `tenant_id`

### 2.2 Database Patterns (`database-patterns.md`)

- Inclusion: `fileMatch` on `backend/src/**/*.py`
- Always include `tenant_id` in WHERE clauses
- Use parameterized queries (never string interpolation)
- Table naming: `snake_case`, plural
- Column naming: `snake_case`
- Foreign keys: `{table_singular}_id`

### 2.3 Testing Standards (`testing-standards.md`)

- Inclusion: `fileMatch` on `**/test_*.py, **/*.test.ts, **/*.test.tsx`
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.api`
- Naming: `test_{function}_{scenario}_{expected}`
- Coverage target: 80% for new code

### 2.4 PR Checklist (`pr-checklist.md`)

- Inclusion: `manual`
- Sections: security, performance, testing, documentation, accessibility

## 3. Spec Templates

Location: `.kiro/specs/Common/templates/spec-template/`

Files: README.md, requirements.md, design.md, TASKS.md — all with placeholders.

## 4. IDE Configuration

### 4.1 Snippets (`.vscode/myAdmin.code-snippets`)

- `flask-bp`: Flask blueprint with route, auth, error handling
- `react-chakra`: React component with Chakra UI
- `pytest-fn`: pytest function with marker and docstring

### 4.2 Tasks (`.vscode/tasks.json`)

- Start Backend, Run Backend Tests, Run Frontend Tests, Docker Up, Docker Down
