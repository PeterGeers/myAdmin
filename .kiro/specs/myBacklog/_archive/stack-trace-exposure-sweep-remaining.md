# Complete py/stack-trace-exposure sweep — remaining ~44 route files / ~180 sites

**Source:** `security-assessment-2026-10-19` Task 4 was SCOPED (orchestrator decision) to the
spec-named files only. The real `'error': str(e)` anti-pattern spans **259 sites across 54
route files** — far more than the 79 the CodeQL seed reported. Task 4 converted the spec-named
files (**117 sites**): `str_routes.py`, `financial_reporting_routes.py`, `aangifte_ib_routes.py`,
`sysadmin_roles.py`, the whole `landing_page_routes/` package, the whole `media_asset_routes/`
package, and the `tenant_admin_*` files.

**Remaining:** ~44 route files / ~**142** `'error': str(e)` sites NOT yet converted (259 total −
117 converted). Convert each `except … return jsonify({... 'error': str(e)}), 5xx` to the shared
`error_responses` helper.

**This is a mechanical follow-up — the convention and helper already exist:**
- Convention: steering `30-backend-api-flask-mysql.md` → "Response Format" / "Error Handling"
  already revised to the generic-message + `error_id` contract (no `str(e)` to client).
- Helper: `backend/src/routes/error_responses.py` — `error_response(e, "<generic msg>", status=…,
  include_success=<bool>, log_context=…)` returns `(jsonify(body), status)` and logs the full
  exception (with stack) server-side under the `error_id`. `error_payload(...)` returns the raw
  dict for SSE generators / embedded-in-data error fields.

**Per-file recipe (same as Task 4):**
1. `from routes.error_responses import error_response` (add `error_payload` if the file has SSE
   `json.dumps({'type':'error',...})` frames or embeds `'error': str(e)` inside a data structure).
2. Replace the `except Exception` (and typed `ClientError` / `PoolResolutionError`) 5xx paths with
   `error_response(...)`. Keep the bare `{'error': ...}` shape via `include_success=False`.
3. Deliberate validation errors (`ValueError` / `ScopeValidationError` → 400) KEEP their explicit
   caller-safe message — assign `msg = str(e)` to a local; do NOT route them through the helper.
4. Change-With-Tests: update any paired test that asserts the raw exception text in `['error']` to
   assert the generic message + presence of `error_id` instead (most route tests only assert the
   500 status + `success is False`, which the helper preserves — those need no change).

**Note:** a `.agent-output/convert_errors.py` + `convert_errors2.py` regex converter handled the
bulk of Task 4's uniform `logger.error(...)` + `jsonify({...'error': str(e)}), 500` blocks; a
similar pass can bootstrap the remaining files (hand-check SSE yields, tuple-wrapped returns, and
dict-literal error fields, which the regex does not cover).

**Verification gate:** the `py/stack-trace-exposure` count only drops on the next CodeQL scan of
`main` (security-assessment Task 11). Do NOT claim closure before that scan diffs the per-rule
count against the `requirements.md` baseline.
