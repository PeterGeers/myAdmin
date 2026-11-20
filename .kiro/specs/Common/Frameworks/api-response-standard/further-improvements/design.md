# Design — API Response & Error Standard: Further Improvements

## Overview

This spec follows the v1.0 platform API response & error standard (see
`api-response-standard`) but is scoped to the **further improvements** that close the
remaining CodeQL security findings and make user-facing error messaging unambiguous.

The systemic fix (the v1.0 "shared error handler") already exists:

- `backend/src/routes/error_responses.py` — `error_response(...)` / `error_payload(...)`.
- `backend/src/error_handlers.py` — global error handlers via `register_error_handlers`.
- `backend/src/app.py` — registers handlers and the `@app.errorhandler(500)`.
- Steering `30-backend-api-flask-mysql.md` — revised to the generic-message + `error_id` contract.

This design therefore focuses on:

1. Ensuring **no `except` catch-all returns exception text** to the client.
2. Converting remaining **validation/business-error branches** (`str(e)`) that leak
   internals, on the 10 flagged files, to safe responses.
3. Confirming user-facing errors are **clear, localized (NL/EN), generic, and carry
   `error_id`**.
4. Re-running CodeQL and dismissing the two stale isolated alerts.

## Architecture / Design Decisions

- **Decision 1 (keep):** Use the existing `error_responses` helper — do not rewrite.
  - Catch-all: `return error_response(e, "<generic msg>", status=500, ...)` →
    `{success: false, error: "<generic>", error_id: "<uuid>"}`.
  - Global fallback: `@app.errorhandler(500)` → bodied 500, logged server-side.
- **Decision 2 (convert):** On the 10 flagged files, ensure **validation/business-error
  branches** no longer place raw exception text into the client response. Either:
  - Convert to a generic message + `error_id` via `error_response`, or
  - Keep author-written, caller-safe Tier-1 messages (e.g. `ValueError("amountGross is required")`)
    — these do not leak, but CodeQL may still flag the `str(e)`-style construction; dismiss
    with justification.
- **Decision 3 (confirm):** `full-test-suite.yml` has `permissions: { contents: read }` (L32).
- **Decision 4 (confirm):** `load-cognito-users.py` redacts passwords unless `--show-passwords`.

## Error Handling (final state)

- Tier 1 — anticipated / user errors: author-controlled, localized, clear messages
  (NL/EN). Not a leak.
- Tier 2 — unanticipated: generic message + `error_id`; full traceback logged server-side
  under `error_id`; never raw text to client.

## API Contracts (error)

```json
{
  "success": false,
  "error": "<generic localized message>",
  "error_id": "<uuid>"
}
```

(Bare `{error, error_id}` shape via `include_success=False` for legacy routes.)

## Testing Strategy
- Change-with-tests: update paired tests asserting raw exception text in `['error']` to
  assert generic message + `error_id`.
- Run backend suite (`python -m pytest ...`).
- CodeQL re-scan of `main`; confirm 0 open alerts; dismiss #1249 / #1227.

## Key Decisions

| Decision | Options Considered | Chosen | Rationale |
| --- | --- | --- | --- |
| Error helper | Per-route `str(e)` vs shared `error_responses` | Shared helper | Systemic; already exists; one place for logging. |
| Validation branches | Generic vs author-safe Tier 1 | Generic OR author-safe | Generic for arbitrary exceptions; author-safe for authored messages. |
| User message | Raw vs generic + error_id | Generic + error_id | Clear for user, diagnosable via error_id. |
