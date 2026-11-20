# SPEC: No information leakage through exceptions — two-tier error contract (Flask + SAM + Frontend)

**Make a spec of this.** Raised 2026-10-12 from a GitHub CodeQL finding
*"Information exposure through an exception"* on the Members routes
(`.kiro/specs/myBacklog/melding.md`). The flagged lines return raw exception text to
the client (`"message": str(e)` / `"error": str(e)` on the 500 branch). The finding is
LEGITIMATE and NOT tied to the 500 status — a 400 that returns `str(e)` leaks just as
much. The leak is codebase-wide because current steering *endorses* it (see below), so
this needs a design pass + a steering change, not a one-off patch.

## The problem (evidence, not speculation)
- CodeQL flagged four PR-diff routes: `members_analytics_audit.py`,
  `members_sender_identity_routes.py` (×2 — GET + POST), and `members_mail.py` (the
  last file has since been DELETED — only stale `.pyc` remain under
  `backend/src/routes/__pycache__/`, so that alert is already resolved by deletion).
- The three live routes were fixed on 2026-10-12 as an interim measure (raw `str(e)`
  removed, detail kept via `logger.error`/`logger.exception`). These four are the
  reference cases; the pattern is everywhere else too.
- **The same `str(e)` / `message: str(e)` leak exists across dozens of routes** —
  `tax_routes.py`, `banking_routes.py`, `pivot_routes.py`, `parameter_admin_routes.py`,
  `financial_reporting_routes.py`, `sysadmin_*`, `tenant_admin_*`, `auth_routes.py`,
  `system_health_routes.py`, and more. CodeQL only flags lines touched in a PR diff, so
  alerts will keep reappearing until the convention changes.
- **Steering currently DOCUMENTS the anti-pattern.** `30-backend-api-flask-mysql.md`
  (auto-applies to `backend/src/routes/**` + `backend/src/services/**`) shows
  `return jsonify({'success': False, 'error': str(e)}), 500` in BOTH its "Response
  Format → Error" and "Error Handling" examples, and uses `print(..., flush=True)` for
  logging. Developers followed steering — this is why the leak is pervasive, not drift.

## Why "just return a generic message" is wrong (user requirements, 2026-10-12)
The user pushed back on bland generic messages, and rightly:
1. **Anticipated / user errors must be as clear as possible, localized** (nl + en — the
   two i18n languages today; `fallbackLng: 'en'`). A vague "something went wrong" for a
   knowable cause is a bad experience.
2. **Logging is for whoever is allowed + willing to read it (the sysadmin).** Full
   technical detail belongs server-side, not in the browser.
3. The real worry with dropping `str(e)`: an unanticipated error like
   `1146 "Table 'finance.foo' doesn't exist"` leaves a broken app AND, if the detail is
   discarded, is hard to reproduce. The detail is diagnostically valuable — it must be
   PRESERVED, just not EXPOSED in the response.

## Agreed design — a two-tier error contract
**Tier 1 — anticipated / user errors (the message is author-controlled):**
- Backend returns a stable `code` (an `errors.*` i18n key, e.g.
  `errors.members.senderInvalid`) + a safe English `error` fallback string. NEVER
  `str(e)` of an arbitrary exception. Narrow domain excepts (`ValueError`,
  `ClosedPeriodError`, …) whose message YOU authored for the user are fine here.
- Frontend resolves `code` via `t(code)` to the user's language, falling back to the
  backend `error`, then a generic default. This GENERALIZES the pattern that already
  exists in exactly one place: `surfaceSendPreviewError(resp.code, resp.error)` in
  `frontend/src/pages/ZZPInvoiceDetail.tsx`.

**Tier 2 — unanticipated errors (catch-all `except Exception`):**
- Generate a per-plane **random `ref`** (8 hex chars — per-plane is fine, no
  cross-plane correlation needed).
- Log full detail + traceback server-side via `logger.exception`, prefixed with the
  ref, and INCLUDING the context that answers "which module / tenant?": tenant
  (`administration` on Flask / `tenant_id` on SAM — both already injected by
  `@tenant_required()` / the verified JWT), module (from the `/api/{module}/...` route
  / blueprint name), route, HTTP method, `user_email`, exception type.
- Response carries ONLY `{success: false, error: "<honest message>", ref}` — no
  `str(e)`, no `repr(e)`, no `type(e).__name__`, no traceback.

**Storage / retention / UI (decided — keep it minimal for now):**
- **A1-strict: logs only. NO local store, NO sysadmin UI.** The ref id is for the user
  to quote and for KIRO + the user to grep in the logs. Explicitly rejected: a MySQL
  `error_log` table / DynamoDB-with-TTL registry and a System Administration "Error Log"
  page (that was option A2 — revisit later if self-service lookup is wanted).
- **Retention 90 days**, enforced by the log backend, not code: CloudWatch Logs
  retention on the SAM plane; Railway log retention on the Flask plane. NOTE: Flask logs
  today go to a `RotatingFileHandler` at `logs/app.log` (10MB×10) on Railway's EPHEMERAL
  disk — that will NOT hold 90 days and is wiped on redeploy. The spec must decide the
  Flask log sink (e.g. ship Flask logs to CloudWatch / a drain) so the 90-day grep
  actually works; otherwise A1 only reliably delivers 90 days on the SAM/CloudWatch side.

## Deliverables (what the spec produces)

### 1. Shared error helpers (one per plane)
- **Flask** — new `backend/src/error_support.py` with `make_ref()`,
  `client_error(code, message, status)` (Tier 1), and
  `server_error(exc, *, tenant, module, message)` (Tier 2 — logs via `logger.exception`
  under a ref, returns `{error, ref}`). Reads request context (route/method/user) when
  present.
- **SAM** — new `sam/shared/error_support.py` (next to `_auth_errors.py`), same two
  functions but returning the API-Gateway proxy dict the SAM handlers use (confirm the
  exact response shape against a real `sam/members` handler before writing) and reading
  `tenant_id`. Logs → CloudWatch.
- **Frontend** — new `frontend/src/utils/apiError.ts` exporting
  `resolveApiError(payload)`: localize `code` via `t(code)` → backend `error` →
  generic + `(ref: …)`. Call sites simplify to
  `toast({ title: resolveApiError(resp), status: 'error' })`.
- Add two i18n keys: `errors.generic` in `frontend/src/locales/{nl,en}/errors.json`
  ("Er is iets misgegaan" / "Something went wrong").

### 2. Steering change (the root cause)
- Amend `30-backend-api-flask-mysql.md`: replace the `str(e)` examples in "Response
  Format → Error" and "Error Handling" with the two-tier contract; switch documented
  logging from `print(..., flush=True)` to `logger.exception`; add a new **"Error
  Exposure (REQ — no information leakage)"** section (raw exception text must never reach
  the client; narrow authored domain messages allowed, catch-all must not; how to find a
  logged error by `ref`; retention note; "supersedes any older `str(e)` example").
- Add a short cross-reference in `35-sam-module-architecture-sam.md` pointing at
  `sam/shared/error_support.py`.

### 3. Flask log sink for 90-day retention (see Storage note)
- Decide + implement where Flask logs land so a 90-day grep-by-ref is real on Railway
  (ship to CloudWatch / a log drain), since the current ephemeral `logs/app.log`
  RotatingFileHandler cannot satisfy it. (SAM/CloudWatch already can.)

### 4. Codebase sweep (gradual, against the new rule)
- Replace the dozens of `str(e)` / `message: str(e)` / `print(..., flush=True)` route
  branches with `client_error` / `server_error`. The four CodeQL-flagged routes become
  the reference implementation (refit the three already-fixed ones onto `server_error`).
- Keep DELIBERATE author-written domain messages on narrow excepts (e.g.
  `ClosedPeriodError`, `ValueError("email is required")`) — those are Tier 1, not leaks.
- Honor the Change-With-Tests contract (steering 30): update paired tests/fixtures that
  assert on the old `error: str(e)` response shape in the same change.

### Out of scope / dependencies
- NO sysadmin error-log UI and NO queryable error store (A2) — explicitly deferred.
- Does not change the SAM edge authorization contract or tenant-selection storage.
- Relates to steering 30 (API conventions), 32 (frontend UI / i18n), 35 (SAM plane),
  and the CodeQL config in `.github/`.

## Interim state already in place (2026-10-12)
- `members_analytics_audit.py`, `members_sender_identity_routes.py` (GET + POST): raw
  `str(e)` removed from the 500 responses; detail retained via
  `logger.error`/`logger.exception`. These will be refit onto `server_error` once the
  helper exists. `members_mail.py` no longer exists (resolved by deletion; stale `.pyc`
  can be cleaned up).
