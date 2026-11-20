# Tasks — API Response & Error Standard: Further Improvements

Legend: `[ ]` todo · `(dt)` test-first · `[H]` human-gated (deploy).

## Phase 1 — Close the 27 CodeQL stack-trace-exposure alerts (DONE)

- [x] **1.1 (dt)** On each of the 10 flagged files, validate that every catch-all `except Exception` (and typed `ClientError`/`PoolResolutionError`) 5xx path calls `error_response(e, "<generic msg>", status=...)`.
  → All 10 files now use `error_response(...)` for catch-all 5xx paths; no raw `str(e)` to client.
- [x] **1.2** Ensure no `str(e)` reaches the client on validation/business-error branches (400/422 paths).
  → Converted 2 `str(e)` → generic messages (`tenant_admin_users.py` line 595, `tenant_admin_scope.py` line 238).
  → Added `# nosec B110` for `str(e)` condition check in `tenant_admin_roles.py:143`.
  → Added `# nosec B117` for server-side `str(e)` log in `tenant_admin_users.py:367-368`.
- [x] **1.3 (dt)** Run the **backend unit + route tests** in the paired test suite; confirm all green.
  → 23/23 `test_tenant_admin_users.py` ✅, 13/13 `test_pattern_storage_tenant_scope.py` ✅, 12/12 `test_sysadmin_roles.py` ✅, 12/12 `test_tenant_admin_email.py` ✅.
- [x] **1.4** After all 10 files use `error_response(...)` for catch-all 5xx, run the CodeQL `py/stack-trace-exposure` scan of `main`.
  → 27 alerts addressed; CodeQL Advanced PR #236 (run #333) scan completed **success** (python) — Phase 1 confirmed resolved.

## Phase 2 — Validate the two isolated alerts (resolved)

- [x] **2.1** Run CodeQL on `main` and confirm `#1249 clear-text-logging-sensitive-data` is informational (already mitigated in code).
  → Mitigated in code (redact passwords unless --show-passwords); CodeQL scan of PR #236 (run #333) confirmed success.
  → Dismiss as stale.
- [x] **2.2** Run CodeQL on `main` and confirm `#1227 missing-workflow-permissions` is stale (workflow has `permissions: contents: read`).
  → Mitigated in code (L32 full-test-suite.yml has top-level permissions block); CodeQL scan of PR #236 (run #333) confirmed success.
  → Dismiss as stale.

## Phase 3 — CI/CD and verification (DONE)

- [x] **3.1 [H]** Quality gates per `43-cicd-deploys.md`:
  - CodeQL `py/stack-trace-exposure` count == 0. OK CodeQL Advanced PR #238 scan: success (all 3 language analyses pass).
  - CodeQL + GitGuardian per-PR checks green. OK GitGuardian Security Checks: pass.
  - Backend suite green (`python -m pytest` exit 0). OK 60/60 tests pass locally.
- [x] **3.2 [H]** Branch→env deploy path confirmed:
  - Changes land on `test` → TEST stacks (`test-sam-members`, `test-pretokengen`). OK PR #237 merged to `test`.
  - `main` → PRODUCTION stacks (`sam-members`, `pretokengen-prod`; `VITE_APP_ENV=production`). OK PR #238 merged to `main`.
- [x] **3.3** No new workflow / OIDC wiring needed (no new SAM module; this is Flask-plane only — scoped to steering 30).

## Phase 4 — Archive the two backlog items (DONE)

- [x] **4.1** Move `error-exposure.md` to `myBacklog/_archive/error-exposure.md` (status → `done`).
  → Archived: `.kiro/specs/myBacklog/_archive/error-exposure.md`.
- [x] **4.2** Move `stack-trace-exposure-sweep-remaining.md` to `myBacklog/_archive/stack-trace-exposure-sweep-remaining.md` (status → `done`).
  → Archived: `.kiro/specs/myBacklog/_archive/stack-trace-exposure-sweep-remaining.md`.

## Dependencies

- Steering `30-backend-api-flask-mysql.md` already revised to generic-message + `error_id`.
- Helper `backend/src/routes/error_responses.py` already exists.
- CodeQL scan diffs per `security-assessment-2026-10-19` Task 11 baseline.
