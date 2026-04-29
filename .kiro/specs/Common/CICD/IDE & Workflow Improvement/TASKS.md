# Tasks — IDE & Workflow Improvements

## Already Implemented ✅

These hooks are live in `.kiro/hooks/`:

- [x] Backend unit tests on save (`backend-unit-tests` — pytest on `backend/**/*.py`)
- [x] Frontend lint & test on save (`frontend-lint-and-test` — ESLint + Jest combined in one hook)
- [x] Pre-write standards review (`pre-write-review` — agent checks code standards before writing, skips non-code files)
- [x] Test after spec task (`test-after-spec-task` — runs all tests after completing a spec task)
- [x] API Postman testing (`api-postman-testing` — was already in place)

## Phase 1: Remaining Hooks (1 hour)

- [ ] 1.1 Create backend lint on save hook (`ruff check` on `backend/**/*.py`)
- [x] 1.2 ~~Frontend type check on save~~ — SKIPPED: ESLint already catches most issues, adding `tsc` would mean 2 heavy processes per save
- [x] 1.3 Create commit guard hook (`commit-guard` — userTriggered, lint + test both stacks)
- [x] 1.4 Create migration safety check hook (`migration-safety-check` — askAgent on `.sql` / migration file edits)
- [x] 1.5 Create pre-task design review hook (`pre-task-design-review` — preTaskExecution, reads design docs)

## Phase 2: Steering Files (2-3 hours)

- [x] 2.1 Create `.kiro/steering/api-conventions.md` (auto inclusion)
- [x] 2.2 Create `.kiro/steering/database-patterns.md` (fileMatch on backend Python)
- [x] 2.3 Create `.kiro/steering/testing-standards.md` (fileMatch on test files)
- [x] 2.4 Create `.kiro/steering/pr-checklist.md` (manual inclusion)

## Phase 3: Spec Templates (1 hour)

- [x] 3.1 Create `.kiro/specs/Common/templates/spec-template/README.md`
- [x] 3.2 Create `.kiro/specs/Common/templates/spec-template/requirements.md`
- [x] 3.3 Create `.kiro/specs/Common/templates/spec-template/design.md`
- [x] 3.4 Create `.kiro/specs/Common/templates/spec-template/TASKS.md`

## Phase 4: IDE Configuration (1 hour)

- [x] 4.1 Create `.vscode/myAdmin.code-snippets` (flask-bp, react-chakra, pytest-fn, pytest-cls, flask-svc)
- [x] 4.2 Create `.vscode/tasks.json` (backend server, backend tests, frontend tests, E2E tests, docker up/down/rebuild)

## Notes

- Phases are independent — can be done in any order
- Total estimated time: 5-7 hours
- Each task is self-contained and can be implemented individually
- Ask Kiro to implement any task by referencing its number (e.g., "implement task 2.1")
