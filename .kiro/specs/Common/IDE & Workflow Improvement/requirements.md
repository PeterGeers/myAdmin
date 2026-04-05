# Requirements — IDE & Workflow Improvements

## 1. Hooks

### 1.1 Backend Lint on Save

**As a** backend developer, **I want** Python files to be linted automatically when saved, **so that** style issues are caught immediately.

**Acceptance Criteria:**

- Runs `ruff check` or `flake8` on saved `.py` files under `backend/`
- Output is concise (last 20 lines)
- Timeout of 60 seconds

### 1.2 Frontend Type Check on Save

**As a** frontend developer, **I want** TypeScript type checking to run when I save, **so that** type errors don't accumulate.

**Acceptance Criteria:**

- Runs `tsc --noEmit` on save of `.ts`/`.tsx` files under `frontend/`
- Reports errors clearly
- Timeout of 60 seconds

### 1.3 Commit Guard

**As a** developer, **I want** a manual trigger that runs linting + tests before I push, **so that** I don't push broken code.

**Acceptance Criteria:**

- `userTriggered` hook
- Runs backend lint + tests, then frontend lint + tests
- Clear pass/fail output

### 1.4 Migration Safety Check

**As a** developer, **I want** SQL/migration file changes to be validated, **so that** destructive operations are flagged.

**Acceptance Criteria:**

- Triggers on `.sql` file edits or files in `migrations/`
- Agent reviews for destructive operations (DROP, TRUNCATE, DELETE without WHERE)
- Warns before proceeding

### 1.5 Pre-Task Design Review

**As a** developer using specs, **I want** the agent to read the relevant design doc before starting a spec task, **so that** implementation follows the design.

**Acceptance Criteria:**

- `preTaskExecution` hook
- Agent is reminded to review design.md and requirements.md
- Applies to all spec tasks

## 2. Steering Files

### 2.1 API Conventions

**As a** developer, **I want** consistent API patterns, **so that** all endpoints follow the same structure.

**Acceptance Criteria:**

- Documents REST conventions (URL patterns, HTTP methods, status codes)
- Error response format (standard JSON structure)
- Authentication requirements per endpoint type
- Pagination patterns
- Located in `.kiro/steering/api-conventions.md`

### 2.2 Database Patterns

**As a** developer, **I want** documented database query patterns, **so that** multi-tenant isolation is always maintained.

**Acceptance Criteria:**

- Multi-tenant query patterns (always filter by tenant_id)
- Common join patterns
- Naming conventions for tables/columns
- Index recommendations
- Located in `.kiro/steering/database-patterns.md`

### 2.3 Testing Standards

**As a** developer, **I want** clear testing guidelines, **so that** tests are consistent and meaningful.

**Acceptance Criteria:**

- Required fixtures and markers
- Coverage expectations
- Test naming conventions
- What to test vs what not to test
- Located in `.kiro/steering/testing-standards.md`

### 2.4 PR Checklist

**As a** developer, **I want** a review checklist I can pull into context, **so that** code reviews are thorough.

**Acceptance Criteria:**

- Manual inclusion steering file
- Covers: security, performance, testing, documentation, accessibility
- Located in `.kiro/steering/pr-checklist.md`

## 3. Specs Workflow

### 3.1 Spec Templates

**As a** developer, **I want** template spec folders, **so that** starting new features is faster.

**Acceptance Criteria:**

- Template folder with pre-filled README, requirements, design, TASKS
- Placeholders for common sections
- Located in `.kiro/specs/Common/templates/spec-template/`

## 4. IDE Configuration

### 4.1 VS Code Snippets

**As a** developer, **I want** code snippets for common patterns, **so that** boilerplate is quick to write.

**Acceptance Criteria:**

- Flask blueprint snippet
- React component with Chakra UI snippet
- pytest test function snippet
- Located in `.vscode/*.code-snippets`

### 4.2 VS Code Tasks

**As a** developer, **I want** common commands as VS Code tasks, **so that** they're one shortcut away.

**Acceptance Criteria:**

- Start backend server
- Run backend tests
- Run frontend tests
- Docker compose up/down
- Located in `.vscode/tasks.json`
