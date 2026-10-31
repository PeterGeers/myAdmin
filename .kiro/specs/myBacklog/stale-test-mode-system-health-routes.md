# Stale TEST_MODE / testfinance in system_health_routes.py (contradicts the APP_ENV model)
**Problem (found during test-environment Phase 6 Task 44 env-var audit, 2026-10-03):**
`backend/src/routes/system_health_routes.py` still reads the legacy `TEST_MODE` env var and
`TEST_DB_NAME` (default `testfinance`) to report the active database name in its health/environment
diagnostics (two spots: `use_test = os.getenv("TEST_MODE", "false").lower() == "true"` ->
`os.getenv("TEST_DB_NAME", "testfinance")`, plus a `"TEST_MODE": os.getenv("TEST_MODE", ...)` echo).
This contradicts the model the test-environment spec established and the rest of the backend already
follows: there is **no `test_mode` flag** and **no `finance`/`testfinance` schema split** -- the schema
is always `finance`, and TEST vs PRODUCTION is a resolved DB **target** selected by `APP_ENV`
(local Docker vs Railway). Phase 3 removed `test_mode` from the real DB path; this diagnostic route
is a leftover that was missed, so the health endpoint can report a `testfinance` DB name that does not
exist and does not reflect how the app actually resolves its target.

**Impact:** misleading diagnostics -- the environment/health report can show a stale `testfinance`
name and a `TEST_MODE` value that nothing else honours, which will confuse anyone debugging a TEST vs
PROD DB-target issue (the exact kind of confusion the APP_ENV model was meant to end). Low functional
risk (diagnostic-only), but it keeps a retired concept alive in a user-facing status endpoint and
re-introduces the `testfinance` term the steering/`#database` skill were updated (Phase 5 Task 29) to
remove.

**Proper fix:** make `system_health_routes.py` report the RESOLVED target instead of the legacy flag --
derive the environment + DB name from the Environment_Resolver / `ResolvedConfig` (schema `finance`,
target label TEST/PRODUCTION from `APP_ENV`), the same way `environment/health_report.py` already does.
Drop the `TEST_MODE` / `TEST_DB_NAME` / `testfinance` reads from this route. Add/adjust a test that the
health report names the resolved target and never emits `testfinance` or a `TEST_MODE` field.

**Scope:** `backend/src/routes/system_health_routes.py`; cross-check `environment/health_report.py`
(the canonical, already-correct implementation to mirror). Relates to the test-environment spec
(`.kiro/specs/Common/test-environment/`) Phase 3 `test_mode` removal + Phase 5 steering alignment, and
is recorded as finding #1 in that spec's `env-var-audit.md`.

Note (same audit, lower priority): the Google-Drive `TEST_MODE` folder toggle
(`TEST_FACTUREN_FOLDER_ID` in `google_drive_service.py` / `output_service.py` /
`missing_invoices_routes.py` / `folder_routes.py` / `seed_tenant_parameters.py`) is a SEPARATE,
still-legitimate flag (orthogonal to `APP_ENV`), but is a candidate to fold into the resolver later so
there is ONE environment selector. Not part of this bugfix.
