# Hooks Review & Cleanup Plan

## Current State: 10 hooks

| Hook                          | Enabled | Trigger                         | Action                   | Issue                                                           |
| ----------------------------- | ------- | ------------------------------- | ------------------------ | --------------------------------------------------------------- |
| api-postman-testing           | no      | fileEdited (\*.py)              | askAgent                 | Disabled, can't automate Postman. Remove.                       |
| backend-unit-tests            | no      | fileEdited (\*.py)              | runCommand (pytest)      | Disabled. Overlaps with test-after-spec-task. Remove.           |
| code-standards-review         | yes     | fileEdited (code files)         | askAgent                 | Active. Fires on every save — noisy during refactors.           |
| commit-guard                  | yes     | userTriggered                   | runCommand (lint+test)   | Good. Manual CI gate. Keep.                                     |
| frontend-lint-and-test        | no      | fileEdited (\*.ts/tsx)          | runCommand (eslint+jest) | Disabled. Overlaps with frontend-test-after-spec-task. Remove.  |
| frontend-test-after-spec-task | yes     | postTaskExecution               | runCommand (jest)        | Active. No cwd set — runs from root, may fail.                  |
| migration-safety-check        | yes     | fileEdited (\*.sql, migrations) | askAgent                 | Good. Catches destructive SQL. Keep.                            |
| pre-task-design-review        | yes     | preTaskExecution                | askAgent                 | Good. Ensures spec alignment. Keep.                             |
| pre-write-review              | no      | preToolUse (write)              | askAgent                 | Deprecated. Still fires "Deprecated" message on writes. Remove. |
| test-after-spec-task          | yes     | postTaskExecution               | runCommand (pytest)      | Active. No cwd set — runs from root, may fail.                  |

## Problems Found

### 1. Overlap: code-standards-review fires on every save

This hook fires every time any code file is saved. During a refactor session (like today's 90-file commit), it triggers dozens of times, slowing work. The same standards are already in steering files (tech.md has file size limits, testing-standards.md has conventions).

Recommendation: Disable code-standards-review. Steering already covers standards. If you want a check, make it userTriggered instead.

### 2. Overlap: test-after-spec-task vs frontend-test-after-spec-task

Both fire on postTaskExecution. One runs pytest, the other runs jest. Both run on every spec task completion regardless of whether the task touched backend or frontend code.

Recommendation: Merge into one hook that runs both, or make commit-guard the single test gate.

### 3. Disabled hooks should be removed

api-postman-testing, backend-unit-tests, frontend-lint-and-test, pre-write-review are all disabled. They add clutter and confusion. The deprecated pre-write-review still fires its "Deprecated" message on every write tool call, adding noise.

### 4. Missing cwd in runCommand hooks

test-after-spec-task runs "python -m pytest tests/unit/" without specifying cwd. If the working directory is not backend/, it fails silently. Same for frontend-test-after-spec-task running "npx react-scripts test" without cwd frontend/.

### 5. No file size check on code changes

The steering file tech.md says max 1000 lines, target 500. But no hook enforces this. The code-standards-review mentions it in its prompt but fires too often to be useful.

## Steering vs Hooks: When to Use What

| Concern                        | Use Steering                  | Use Hook                     |
| ------------------------------ | ----------------------------- | ---------------------------- |
| Code style, naming conventions | yes (always included)         | no (too noisy on every save) |
| File size limits               | yes (in tech.md)              | no (unless userTriggered)    |
| Testing standards              | yes (in testing-standards.md) | no (standards are guidance)  |
| Run tests after task           | no (can't run commands)       | yes (postTaskExecution)      |
| Run tests before push          | no (can't run commands)       | yes (userTriggered)          |
| Review SQL migrations          | no (not event-driven)         | yes (fileEdited on \*.sql)   |
| Review spec before coding      | no (not event-driven)         | yes (preTaskExecution)       |

Rule of thumb: Steering = guidance that shapes how the agent thinks. Hooks = automated actions triggered by events.

## Recommended Final State: 5 hooks

| Hook                   | Trigger             | Action     | Purpose                                 |
| ---------------------- | ------------------- | ---------- | --------------------------------------- |
| commit-guard           | userTriggered       | runCommand | Manual CI gate: lint + test both stacks |
| pre-task-design-review | preTaskExecution    | askAgent   | Review spec before starting task        |
| test-after-spec-task   | postTaskExecution   | runCommand | Run backend + frontend tests after task |
| migration-safety-check | fileEdited (\*.sql) | askAgent   | Flag destructive SQL                    |
| file-size-check        | userTriggered       | askAgent   | Check all changed files for >500 LOC    |

### Changes needed

1. Delete: api-postman-testing, backend-unit-tests, frontend-lint-and-test, pre-write-review
2. Disable: code-standards-review (or convert to userTriggered)
3. Merge: test-after-spec-task + frontend-test-after-spec-task into one hook with proper cwd
4. Optional: Add file-size-check as userTriggered hook
