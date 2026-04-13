# Hooks Approach

## Active Hooks

| Hook                          | Enabled | Trigger                         | Action     | Purpose                                                        |
| ----------------------------- | ------- | ------------------------------- | ---------- | -------------------------------------------------------------- |
| commit-guard                  | yes     | userTriggered                   | runCommand | Manual CI gate: lint + test both stacks before push            |
| pre-task-design-review        | yes     | preTaskExecution                | askAgent   | Review spec design.md + requirements.md before starting a task |
| test-after-spec-task          | yes     | postTaskExecution               | runCommand | Run backend pytest after task completion                       |
| frontend-test-after-spec-task | yes     | postTaskExecution               | runCommand | Run frontend jest after task completion                        |
| migration-safety-check        | yes     | fileEdited (\*.sql, migrations) | askAgent   | Flag destructive SQL (DROP, TRUNCATE, DELETE without WHERE)    |
| code-standards-review         | no      | fileEdited (code)               | askAgent   | Disabled — too noisy on every save. Enable on demand.          |

## How to Invoke

### commit-guard

Trigger: `userTriggered` — never runs automatically. To run it: click the Kiro icon in the left icon panel → Agent Hooks → find "Commit Guard" → click the run icon. Runs lint + tests for both backend and frontend. Use before `git push`.

### code-standards-review

Currently disabled to avoid noise during active development. To use it:

1. Open `.kiro/hooks/code-standards-review.kiro.hook`
2. Change `"enabled": false` to `"enabled": true`
3. Save — it will now fire on every code file save
4. Disable again when done reviewing

Alternatively, ask the agent directly: "Review this file against project standards" — the steering files (tech.md, testing-standards.md) already guide the agent on standards without needing the hook.

### pre-task-design-review / test-after-spec-task

These fire automatically during spec-driven development. No manual action needed.

### migration-safety-check

Fires automatically when you edit `.sql` files or migration scripts. No manual action needed.

## Steering vs Hooks

Steering files shape how the agent thinks. Hooks trigger automated actions on events.

| What                                 | Steering                                      | Hook                   |
| ------------------------------------ | --------------------------------------------- | ---------------------- |
| Code style, naming, file size limits | tech.md (always loaded)                       | Not needed             |
| Testing conventions                  | testing-standards.md (loaded with test files) | Not needed             |
| Database patterns, tenant isolation  | database-patterns.md (always loaded)          | Not needed             |
| Run tests after completing work      | Can't run commands                            | test-after-spec-task   |
| Run tests before pushing             | Can't run commands                            | commit-guard           |
| Catch destructive SQL                | Not event-driven                              | migration-safety-check |
| Review spec before coding            | Not event-driven                              | pre-task-design-review |

Rule: if it's guidance about how to write code, put it in steering. If it's an action that should run when something happens, make it a hook.

## History

Cleaned up from 10 hooks to 6 on April 13, 2026. See `issues.md` for the full audit.

Removed: api-postman-testing, backend-unit-tests, frontend-lint-and-test, pre-write-review, frontend-test-after-spec-task.
Merged: test-after-spec-task + frontend-test-after-spec-task into one combined hook.
Disabled: code-standards-review (steering handles standards).
