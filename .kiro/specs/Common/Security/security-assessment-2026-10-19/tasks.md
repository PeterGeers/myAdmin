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

- [-] 11. **Verification gate — confirm the mitigations landed** (depends on 1–8)
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