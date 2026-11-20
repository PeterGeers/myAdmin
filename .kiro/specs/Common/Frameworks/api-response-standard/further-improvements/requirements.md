# API Response & Error Standard — Further Improvements

Closes the remaining CodeQL security findings on the Flask plane so that the two
myBacklog items (`error-exposure.md` and `stack-trace-exposure-sweep-remaining.md`)
can be closed as proven solved.

This is a **subset/follow-up spec** of the platform API response & error standard
v1.0 (`api-response-standard`). It is scoped to closing the open `py/stack-trace-exposure`
alerts and the two isolated CodeQL alerts (`clear-text-logging-sensitive-data`,
`missing-workflow-permissions`), not to rewriting the envelope.

## User Stories

### As an end user
**I want** to see a clear, localized (NL/EN) message when an action fails,
**so that** I understand what went wrong and can quote the `error_id` to support,
with no raw exception text or stack trace reaching my browser.

**Acceptance Criteria:**
- [ ] Every `except` catch-all path returns a generic, localized message
  (`{success: false, error: "...", error_id: "..."}`) — never `str(e)`.
- [ ] Validation/user-error branches keep clear author-written, caller-safe
  messages (Tier 1).
- [ ] The response always includes an `error_id` the user can reference.

### As a support engineer
**I want** an `error_id` that correlates to the full server-side traceback,
**so that** I can reproduce the user's error from logs without asking the user
for exception text.

**Acceptance Criteria:**
- [ ] `error_responses.error_response(...)` logs the full exception + stack
  server-side under `error_id`.
- [ ] No endpoint leaks exception text to the client.

### As a developer / operator
**I want** the `py/stack-trace-exposure` CodeQL count to be 0 on `main`,
**so that** the CI security gate is green.

**Acceptance Criteria:**
- [ ] O1: Zero open `py/stack-trace-exposure` alerts on `main` after the next CodeQL scan.
- [ ] O2: No catch-all `except` in the 10 flagged files returns exception text to the client.
- [ ] O3: No `str(e)` on validation branches leaks internals (generic message + `error_id`
  or author-safe Tier 1 message).
- [ ] O4: Paired tests updated per change-with-tests; backend suite green.
- [ ] O5: Stale CodeQL alerts #1249 and #1227 dismissed after re-scan (already fixed in code).
- [ ] O6: User-facing error is generic, localized (NL/EN), includes `error_id`, never raw text.

## Non-Functional Requirements
- **Security:** No information exposure through exceptions (`py/stack-trace-exposure` = 0).
- **i18n:** Client-visible failures use NL/EN localized messages; `fallbackLng: en`.
- **Observability:** Every failure logged server-side with `error_id` + traceback.

## Out of Scope
- Rewriting the Flask response envelope (handled by `api-response-standard`).
- SAM plane changes (SAM has its own error handling).
- Frontend changes (this spec is Flask-plane only; steering 30 fileMatch-scoped).
- A sysadmin error-log UI or queryable error store (explicitly deferred).
- Log-sink / 90-day retention for Flask logs (Railway ephemeral disk; deferred).

## Success Metrics
- CodeQL `py/stack-trace-exposure` count == 0 on `main`.
- No `str(e)` reachable by a client in any of the 10 flagged route files.
- Backend unit + route tests green (paired tests updated).
- Next CodeQL scan of `main` shows the 27 open alerts cleared; #1249/#1227 dismissed.

## Dependencies
- Steering `30-backend-api-flask-mysql.md` (already revised to generic-message + `error_id`).
- Helper `backend/src/routes/error_responses.py` (already exists).
- Steering `43-cicd-deploys.md` (CodeQL must be green; CI/CD gates).
