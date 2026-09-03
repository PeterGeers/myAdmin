# Kiro Version Alignment — TASKS

Status: Complete

Align workspace `.kiro/` configuration with the current Kiro version's features and conventions.

---

## Phase 1: Steering Frontmatter (5 min)

- [x] Add `inclusion: auto` frontmatter to `.kiro/steering/product.md`
- [x] Add `inclusion: auto` frontmatter to `.kiro/steering/architecture.md`
- [x] Add `inclusion: auto` frontmatter to `.kiro/steering/structure.md`
- [x] Add `inclusion: auto` frontmatter to `.kiro/steering/tech.md`
- [x] Add `inclusion: auto` frontmatter to `.kiro/steering/shell-environment.md`
- [x] Add `inclusion: auto` frontmatter to `.kiro/steering/specs.md`

## Phase 2: Fix commands.md (10 min)

- [x] Replace `.\.venv\Scripts\Activate.ps1` with `source .venv/bin/activate`
- [x] Replace `.\powershell\start_backend.ps1` with inline bash command
- [x] Replace `.\powershell\run_tests.ps1` with inline pytest command
- [x] Add note to Railway section: PowerShell scripts are Windows-only, add bash alternatives

## Phase 3: Create Skills Directory & Migrate (5 min)

- [x] Create `.kiro/skills/` directory
- [x] Move `.kiro/steering/commands.md` → `.kiro/skills/commands.md`
- [x] Move `.kiro/steering/specs-reference.md` → `.kiro/skills/specs-reference.md`
- [x] Move `.kiro/steering/pr-checklist.md` → `.kiro/skills/pr-checklist.md`
- [x] Update frontmatter in each: change `inclusion: manual` → `inclusion: auto`

## Phase 4: Broaden Permissions (manual)

- [x] Replace narrow `fs_write` rules in `~/.kiro/settings/permissions.yaml` with workspace-wide pattern `/home/peter/projects/myAdmin/**`

> This file is protected by Kiro's internal scope rules and cannot be edited by the agent.
> **Manual edit required:** Open `C:\Users\peter\.kiro\settings\permissions.yaml` and replace the `fs_write` block with:
>
> ```yaml
> - capability: fs_write
>   effect: allow
>   match:
>     - /home/peter/projects/myAdmin/**
> ```

## Phase 5: Power Cleanup (manual) ✅

All powers uninstalled — clean slate. Re-install `terraform` on demand for infra sessions.

> Completed manually via Kiro Powers panel.

---

## Phase 6: Migrate Hooks to v2 JSON Format (15 min)

Migrate from `.kiro.hook` format to v2 `.json` format for future-proofing.

- [x] Migrate `ggshield-pre-commit.kiro.hook` → `ggshield-pre-commit.json`
  - Trigger: `PreToolUse`, matcher: `.*git_commit.*`
  - Action: `command` (same bash script)
- [x] Migrate `test-after-spec-task.kiro.hook` → `test-after-spec-task.json`
  - Trigger: `PostTaskExec`
  - Action: `agent` (same prompt)
- [x] Migrate `pre-task-design-review.kiro.hook` → `pre-task-design-review.json`
  - Trigger: `PreTaskExec`
  - Action: `agent` (same prompt)
- [x] Migrate `migration-safety-check.kiro.hook` → `migration-safety-check.json`
  - Trigger: `PostFileSave`, matcher: `\.sql$|migrations/.*\.py$`
  - Action: `agent` (same prompt)
- [x] Evaluate `commit-guard.kiro.hook` — `userTriggered` has no v2 equivalent
  - Option A: Convert to a skill/manual workflow
  - Option B: Keep as-is if backward compat remains
  - Option C: Make it a `PreToolUse` on git push
- [x] Delete old `.kiro.hook` files after confirming v2 hooks work

## Phase 7: Reduce Steering Overlap (10 min)

Fix duplicate context injection when editing frontend test files.

- [x] Narrow `testing-standards.md` fileMatchPattern from `**/test_*.py,**/*.test.ts,**/*.test.tsx` to `**/test_*.py` only
  - This file's frontend section duplicates `testing-frontend.md`
- [x] Remove the "Frontend (Vitest + React Testing Library)" section from `testing-standards.md`
  - `testing-frontend.md` already covers this in more detail
- [x] Verify: editing a `.test.tsx` file should only trigger `testing-frontend.md`, not both

## Phase 8: Narrow api-conventions.md Scope (5 min)

Reduce noise — API conventions only matter for route/service files, not utilities or scripts.

- [x] Change `api-conventions.md` fileMatchPattern from `backend/src/**/*.py` to `backend/src/routes/**/*.py,backend/src/services/**/*.py`
- [x] Verify: editing `backend/src/report_generators/*.py` no longer triggers this steering file

## Phase 9: Add Database Skill (10 min)

Create a dedicated on-demand skill for Railway DB operations and migration workflows.

- [x] Create `.kiro/skills/database.md` with:
  - Railway connection details (host, port, user, database)
  - Migration workflow (`DatabaseMigration.run_all_migrations()`)
  - Common queries (SHOW TABLES, check migration status)
  - MySQL 9.4 limitations (no IF NOT EXISTS on indexes)
  - Env var setup for Railway connections
- [x] Remove Railway DB connection details from `.kiro/skills/commands.md` (avoid duplication)
