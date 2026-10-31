# CodeQL — the 30 open alerts, grouped by rule

## The 30 open alerts, grouped by rule

**1) `py/stack-trace-exposure` — 27 alerts (raw exception/stack text returned to the client).**
A route returns the exception/stack trace in the HTTP response, leaking internal detail to callers.
Files (alert #s):
- `backend/src/admin_routes.py` — #1228–#1236 (9)
- `backend/src/routes/tenant_admin_users.py` — #1245–#1248 (4)
- `backend/src/routes/sysadmin_roles.py` — #1237–#1240 (4)
- `backend/src/routes/str_routes.py` — #1250–#1253 (4)
- `backend/src/routes/tenant_admin_roles.py` — #1242–#1243 (2)
- `backend/src/routes/tenant_admin_credentials.py` — #1258 (1)
- `backend/src/routes/tenant_admin_scope.py` — #1244 (1)
- `backend/src/routes/tenant_admin_email.py` — #1241 (1)
- `backend/src/reporting_routes.py` — #1257 (1)
- `backend/src/routes/aangifte_ib_routes.py` — #1256 (1)
**Proper fix:** return a generic error body to the client (e.g. `{"error": "internal error"}` + a
correlation id) and log the detail server-side only. This is a cross-cutting error-handling pattern,
not 27 independent edits — ideally one shared error handler / Flask `errorhandler` so the fix is
systemic and future routes inherit it. Candidate for its own small security-hardening spec.

**2) `py/clear-text-logging-sensitive-data` — 1 alert.**
- `scripts/onboarding/members/_generic/load-cognito-users.py` — #1249. A sensitive value (likely a
  password/credential) is logged in clear text. Same class as the already-fixed provisioner finding;
  apply the same remedy: never print/log the secret (require it as input, don't echo it).

**3) `actions/missing-workflow-permissions` — 1 alert.**
- `.github/workflows/full-test-suite.yml` — #1227. The workflow has no explicit least-privilege
  `permissions:` block, so it inherits broad default token perms. **Proper fix:** add a top-level
  `permissions: { contents: read }` (tighten per-job if any job needs more). Quick, isolated win.
  (Cross-check the other workflows while here — only this one was flagged, but a repo-wide default is
  good hygiene. Relates to the "main branch isn't protected" item above — both are CI/supply-chain
  hardening.)

**Scope / recommendation:** the 27 stack-trace-exposure findings want ONE systemic fix (shared error
handler) — spec it rather than patch piecemeal. The 2 isolated ones (workflow permissions block;
load-cognito-users clear-text log) are quick wins that could be done independently. Relates to steering
`43-cicd-deploys.md` (CI security gates: "CodeQL must be green") — these pre-date that gate.
