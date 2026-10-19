# Implementation Plan: Security Mitigation — 2026-10-19

## Overview

Derived from `requirements.md` (CodeQL Step 0 seed + the three manual perspectives). The
seed surfaced **100 open code-scanning alerts on `main` (17 high, 83 medium)**. This plan
turns those into actionable, file-specific mitigation tasks, grouped by priority
(red-zone / high score first). Effort: **S** ≤ 30 min, **M** ≤ 2 h, **L** > 2 h.

> **Analysis + task list only — do NOT fix in this run.** Execute as a separate step, under
> the Change-With-Tests Contract (`30-backend-api-flask-mysql`): any behavioral change to a
> route/service updates its paired test in the same change. Security-sensitive changes (error
> contract, path handling, XSS sanitization) MUST note what is and isn't locally verifiable.

## Tasks

### Priority 1 — Red zone (high severity, exploitable)

- [x] 1. **ReDoS on public contact form** — `backend/src/routes/landing_page_routes/public_endpoints.py:61,65`
  - Action: replace the backtracking tag-strip regexes with a linear approach (bounded parser or `html.parser`/`bleach`), on this **unauthenticated** endpoint.
  - Effort: M. Verify: unit test with a pathological input completes in <50ms; paired test for the sanitizer updated. `py/polynomial-redos` alerts resolve on next CodeQL run.
  - **Security note:** public endpoint — verify the fix still strips the same tags the existing tests assert.

- [x] 2. **DOM XSS in mail preview** — `frontend/src/components/members/analytics/MemberMailCompose.tsx:610,741`
  - Action: sanitize `previewBodyHtml` with DOMPurify before `dangerouslySetInnerHTML`; sanitize/structure the body before SEND too, not just preview.
  - Effort: M. Verify: vitest asserting a `<script>`/`onerror` payload is stripped from the rendered preview; paired component test updated. `js/xss-through-dom` resolves.

- [x] 3. **Path injection in file cleanup** — `backend/src/file_cleanup_manager.py:238,239,245`
  - Action: canonicalize `local_path` (`os.path.realpath`) and assert it stays within an allowed base dir before `os.path.exists`/`os.access`/`os.chmod`; reject otherwise.
  - Effort: M. Verify: unit test that a `../`-traversal `file_url` is rejected; existing cleanup tests still pass. `py/path-injection` resolves.

### Priority 2 — High (info-leak at scale) + staged fix

- [x] 4. **Revise the error-response convention FIRST, then sweep `str(e)` (×79)** — steering `30-backend-api-flask-mysql` + all `py/stack-trace-exposure` sites.
  - Action (a): change the documented error contract to log full exception server-side and return a generic message + error id (no `str(e)` to client).
  - Action (b): sweep the 79 sites (`admin_routes.py`, `str_routes.py`, `landing_page_routes/*`, `media_asset_routes/*`, `tenant_admin_*`, `sysadmin_roles.py`, `reporting_routes.py`, `aangifte_ib_routes.py`) to the new helper.
  - Effort: L. Verify: route tests updated to assert the generic shape (Change-With-Tests); grep shows no `'error': str(e)` in routes; `py/stack-trace-exposure` count drops to ~0.
  - **Do (a) before (b)** or the sweep regresses against the old convention.

- [x] 5. **Commit the staged insecure-randomness fix** — `frontend/src/components/public/application/ApplicationFormPage.tsx:138`
  - Action: the `Math.random()` → `crypto.getRandomValues()` change is already in the working tree; run `tsc -b` + `eslint` and the 13 paired tests **locally** (Frontend CI is `disabled_manually` per `43-cicd-deploys` — CI will not run them on the PR), commit, and **push to a feature branch → open a PR into `test`** (never push to `main`; a merge to `main` is a production deploy).
  - Effort: S. Verify: 13 paired tests green locally; `js/insecure-randomness` resolves after merge to `main`.

### Priority 3 — Medium

- [x] 6. **Cleartext password logging** — `scripts/onboarding/members/_generic/load-cognito-users.py:519`
  - Action: gate the generated-password print behind an explicit `--show-passwords` flag (default off), or write to a 0600 file.
  - Effort: S. Verify: default run no longer prints secrets; `py/clear-text-logging-sensitive-data` resolves.

- [x] 7. **CI workflow least-privilege permissions** — `.github/workflows/full-test-suite.yml:27,168,232,330`
  - Action: add an explicit `permissions:` block (default `contents: read`, widen per job only as needed).
  - Effort: S. Verify: workflow still runs green; `actions/missing-workflow-permissions` resolves.

- [x] 8. **URL-substring sanitization in tests (×8)** — `test_invoice_service_s3_upload.py:222`, `test_landing_page_publish_service.py:1490-1542`, `test_landing_page_styles.py:314`, `test_dynamodb_client.py:99`
  - Action: fix the `in`-substring URL checks to parse + compare host properly; **first confirm** the product helpers under test don't share the anti-pattern (if they do, fix those too — that's a real exposure, not test-only).
  - Effort: M. Verify: tests pass with the stricter check; `py/incomplete-url-substring-sanitization` resolves.

### Priority 4 — Carried architectural items (no CodeQL hit, from prior reviews)

- [ ] 9. [decision] **Flask-plane JWT signature verification (E1)** — decode-only today; evaluate verifying against Cognito JWKS like the SAM edge. Effort: L. Architecture decision requiring sign-off — not autonomously dispatchable.
- [ ] 10. [decision] **Role-cache staleness (5 min)** and **SysAdmin bypass audit** — confirm no privilege-escalation path. Effort: M. Architecture decision requiring sign-off — not autonomously dispatchable.

### Priority 5 — Verification gate

- [ ] 11. **Verification gate — confirm the mitigations landed** (depends on 1–8)
  - Run the paired test(s) for each changed file. After the Task 4 ×79 sweep ONLY, run the full backend suite locally (`cd backend && source .venv/bin/activate && pytest -q`) — blast-radius justified per the `43-cicd-deploys` scope note — then dispatch `full-test-suite.yml` as the authoritative CI gate.
  - Frontend touches (Tasks 2, 5): `tsc -b` + `eslint`.
  - Trigger a fresh scan: `gh workflow run "CodeQL Advanced" --ref <branch>`; diff per-rule counts against the `requirements.md` baseline (**100 open: 17 high / 83 medium**). Expect `py/stack-trace-exposure` ~79→~0, plus the 3 highs (ReDoS/XSS/path), 4 CI-perms, and 1 cleartext resolved.
  - Effort: M. Any residual alert judged intentional must be dismissed **on GitHub with a reason** and recorded in Notes.

## Notes

- **Dismissals (none this run).** No alert was dismissed as a false positive. If any of the
  test-file URL alerts (task 8) are judged intentional, dismiss them **on GitHub with a
  reason** and record it here — do not silently drop them.
- **Verification reality.** Tasks 1–3, 6–8 resolve the matching CodeQL rule on the next
  `main` scan — confirm by re-running `prompt-security.md` Step 0 and diffing counts against
  `requirements.md`. Tasks 9–10 are architecture decisions and cannot be closed on a green
  unit test alone.
- **Fix order matters for task 4:** revise the error-contract convention before sweeping the
  79 sites, or the sweep regresses against the documented pattern.

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3", "4", "5", "6", "7", "8"] },
    { "wave": 2, "tasks": ["11"] }
  ],
  "dependencies": {
    "1": [],
    "2": [],
    "3": [],
    "4": [],
    "5": [],
    "6": [],
    "7": [],
    "8": [],
    "11": ["1", "2", "3", "4", "5", "6", "7", "8"]
  },
  "decisions": ["9", "10"]
}
```

# Note
str(e) is partly done
Task 4 is bigger than the spec says — the real scope is 259 'error': str(e) sites across 54 route files, not 79 across ~10. How should I run the sweep?

The approach is unchanged either way: first revise the error-contract convention in steering 30-backend-api-flask-mysql (log full exception server-side, return a generic message + error id), add a shared helper, then convert the call sites and update paired route tests. The question is how to stage the conversion given the larger blast radius.

Convention + helper + the ~10 spec-named files now; backlog the rest
Good call — smaller blast radius, resolves the alerts the seed actually flagged, and the remaining sites get tracked rather than silently dropped. Dispatching Task 4 scoped that way, with the backlog follow-up spelled out.

# second note:
Still open, needing you:

Tasks 9 & 10 — architecture decisions (Flask JWT JWKS verification; role-cache staleness + SysAdmin bypass audit), deferred to a separate session as agreed.

CodeQL count-diff — once the two runs finish (a few minutes), confirming the targeted rules actually dropped. I can check gh run list / the PR checks and report the diff when they complete.

Backlog — the remaining ~142 str(e) sites across ~44 route files (convention + helper already in place) and a unit test for the error_responses helper.
---

## Execution record & decisions (appended during run)

> This spec was executed once (branch `spec/security-assessment-2026-10-19`, PR #124 into
> `test`, commit `2c6206e37`). The notes below record what actually happened so a
> **regenerated** spec can start from the true current state. The original task list was
> written against the *sampled* `main` CodeQL baseline (100 open: 17 high / 83 medium); the
> first full feature-branch scan reports a different, more complete set — a naive count-diff
> is therefore misleading.

### Task 9 (E1 — Flask JWKS JWT verification): CLOSED — already implemented
The premise ("decode-only today") is **stale**. The Flask plane already does full JWKS RS256
verification wired into `@cognito_required`:
- `backend/src/auth/jwt_verifier.py` `JWTVerifier.verify_token()` — RS256 signature + iss +
  aud/client_id + exp, keys from `backend/src/auth/jwks_cache.py` (per-issuer cache, rotation).
- `backend/src/auth/cognito_utils.py` resolves the verifier and calls it; the only
  `verify_signature:false` decode is the header read for `kid`/`iss` before real verification
  (same shape as the SAM `sam/shared` edge).
- The base64 fallback **already fails closed** via `_jwt_verification_required()` → 503 when
  `RAILWAY_ENVIRONMENT=production` or `REQUIRE_JWT_VERIFICATION=true`.
- **Residual (config, not code):** TEST (local Docker, non-production) is not auto-covered by
  the fail-closed gate unless `REQUIRE_JWT_VERIFICATION=true` is set there. Defensible, but set
  the flag in TEST if it ever faces untrusted input. No code change required to close E1.

### Task 10: NOT yet decided (deferred).

### CodeQL rescan result (branch vs. sampled baseline) — honest diff
Resolved to 0 (fixes CodeQL can verify): `js/xss-through-dom` (2→0), `js/insecure-randomness`
(1→0), `actions/missing-workflow-permissions` (4→0). `py/polynomial-redos` 2→1.

Still flagged though runtime-correct (static analysis can't prove the guard):
- `py/path-injection` 3→**13** — the 3 original `file_cleanup_manager` lines are resolved by the
  realpath guard; the increase is CodeQL now tracing the **same taint into pre-existing sinks**
  it previously under-sampled: `file_cleanup_actions.py` (196–259, the weaker `is_safe_path`
  deletion path), `sysadmin_test_tool.py:154`, `str_invoice_routes.py:274`, `app.py:251`.
- `py/clear-text-logging-sensitive-data` 1→4 — `load-cognito-users.py:548,557` are inside the
  `--show-passwords` branch (safe by default; CodeQL flags the source regardless);
  `verify_dynamodb_access.py:65`, `banking_service.py:91` are pre-existing & unrelated.
- `py/stack-trace-exposure` 79→**72** — Task 4 swept 117 sites but was scoped to spec-named
  files; the ~142 backlogged sites + sampling keep the count high.

Newly-surfaced PRE-EXISTING highs (NOT caused by this changeset — Task 4 only touched the
`str(e)` lines in these files): `py/reflective-xss` at `tenant_admin_credentials.py:438` (OAuth
callback interpolates `request.args` into an HTML f-string) and `py/regex-injection` at
`folder_routes.py:125` (`re.compile` on user input). Both backlogged.

**No dismissals made.** Decide per item whether to dismiss-on-GitHub-with-reason vs. fix.

### Task 10 (role-cache staleness + SysAdmin bypass audit): CLOSED — no escalation path
Grounded in `backend/src/auth/role_cache.py` and `backend/src/auth/tenant_context.py`.

**Role cache (5-min TTL):** `CACHE_TTL_SECONDS = 300`, keyed `email:tenant`. Already mitigated:
- Invalidates on every app-driven role change — `invalidate_cache(email, tenant)` is called from
  `tenant_admin_roles.py` (grant + revoke) and `tenant_admin_users.py` (assign/update/delete). No
  5-min window for changes made through the app.
- Never caches a negative (empty) result, so an out-of-band grant is picked up next request.
- **Residual (accepted):** an out-of-band *demotion/revoke* (direct SQL, bypassing the routes) can
  leave stale elevated roles for ≤5 min, since only the routes call `invalidate_cache`. This is
  privilege *retention*, not escalation, and a narrow admin path.

**SysAdmin bypass:** fires only on `allow_sysadmin and "SysAdmin" in user_roles`, where `user_roles`
comes from the cryptographically verified `cognito:groups` claim (Task 9) — **not** client-supplied.
No path lets a non-SysAdmin reach the bypass. The capability it grants (a verified SysAdmin injects
an arbitrary `X-Tenant` without membership validation — F2 from assessment-2026-09-26) is an accepted,
**audit-logged** cross-tenant capability (`_log_sysadmin_bypass()` with a print fallback).

**Verdict:** no privilege-escalation path in either mechanism. Residuals documented and accepted; no
code change required to close E-role-cache / E-sysadmin.

### Task 4 `str(e)` sweep — COMPLETED (waves 1–4b)
The remaining py/stack-trace-exposure sweep (originally backlogged) is now DONE. Converted in
four waves on branch spec/security-assessment-2026-10-19:
- Wave 1 (30c8d84): banking/pivot/budget/asset — 45 sites
- Wave 2 (65064b5): year-end/cache/parameter/tax — 36 sites
- Wave 3 (707e4ca): sysadmin/validation/budget-ai — 25 sites (incl. 1 SSE frame)
- Wave 4a (d28ee3f): 14 long-tail route files — 26 sites
- Wave 4b (4e83907): details/message leaks (tenant_admin_*, user_routes, static) — 22 sites
Total this sweep: ~154 sites, on top of Wave-0's 117 = the full ~259 route-level str(e) set.

**Intentionally preserved (NOT leaks):** deliberate caller-safe messages on 400/403/404/429
validation & business paths (ValueError, ClosedPeriodError, PermissionError, InvalidCodeError,
ResendRateLimitError), pivot's RuntimeError guidance 500s (pivot_routes.py:139,417), and
tenant_admin_credentials file-parse 400 messages. Per the convention, deliberate errors keep
their explicit message; only caught-generic-Exception paths were made generic + error_id.

**Verification:** every wave ruff-clean + paired tests run; new test-contract breaks fixed in the
same commit (banking, tax, verification, invoice); all other suite failures confirmed PRE-EXISTING
via git stash baseline (filter-options, folder fr.flag, template blueprint-registration, etc.).
py/stack-trace-exposure should drop to ~0 on the next CodeQL scan (confirm via a fresh run).
