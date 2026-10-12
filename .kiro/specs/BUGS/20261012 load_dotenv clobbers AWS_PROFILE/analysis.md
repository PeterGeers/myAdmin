# BUGFIX — ANALYSIS: `load_dotenv()` re-injects static AWS creds over `AWS_PROFILE`

> **Doc 1 of 3** in this bugfix folder: `analysis.md` (the problem, grounded in code),
> `bugfix.md` (chosen approach + decisions + risks), `tasks.md` (ordered work + gates).
> Prerequisite gate for the Members `Parameter redesign` Phase 0. Promoted from `backlog.md`
> 2026-10-12.

## The bug (one paragraph)
Static personal-account AWS keys live in the `.env` files. Many code paths call `load_dotenv()`
(at module import time AND inside scripts), which re-injects those keys into the process env.
boto3 ranks static env keys ABOVE `AWS_PROFILE`, so any attempt to target a different account
(`nonprofit-deploy`) is silently overridden back to `personal` (344561557829) — surfacing as
`ResourceNotFoundException` on tables that only exist in `nonprofit-deploy` (506221081911), or as
the local DynamoDB emulator when `AWS_ENDPOINT_URL_DYNAMODB` is also present. Confusing because a
boto3 call in a process that never triggered the load succeeds.

## Grounded findings (verified in code 2026-10-12 — these corrected the stale backlog item)

### F1 — the earlier `backend/.env` pin only MOVED the clobber
`database.py` was changed to `load_dotenv(dotenv_path=backend/.env)` to avoid the repo-root `.env`.
But `backend/.env` **also** exports the static keys, so the clobber still happens — just from a
different file. **Verified:** both `.env` and `backend/.env` export `AWS_ACCESS_KEY_ID` +
`AWS_SECRET_ACCESS_KEY`; `backend/.env` additionally exports `AWS_ENDPOINT_URL_DYNAMODB`.

### F2 — the import-time `load_dotenv` side-effect is in EIGHT modules, not one
`database.py`, `transaction_logic.py`, `actuals_routes.py`, `google_drive_service.py`,
`image_ai_processor.py`, `hybrid_pricing_optimizer.py`, `ai_extractor.py` each do
`load_dotenv(backend/.env)` at import; `app.py` does the legitimate startup load (line ~101).
Fixing only `database.py` is cosmetic — importing any of the other seven re-arms the trap.

### F3 — ~30 scripts call `load_dotenv()` themselves BEFORE importing `database`
`backend/scripts/**` overwhelmingly do their own `load_dotenv()` (plain, or pinned to
`backend/.env`) ahead of importing backend modules. **Consequence:** removing the module-level
loads does NOT stop the clobber for scripts — the scripts' OWN `load_dotenv()` of a key-bearing
file re-injects the keys. Chasing (a) across every script is unbounded.

### F4 — therefore (b) is the real cure; (a) is cleanup
If the static AWS keys are not IN the `.env` files, then NO `load_dotenv()` anywhere — module or
script — has anything to re-inject. **(b) disarms the landmine globally in one change.** (a)
(removing the 8 import side-effects) is correct hygiene (no import side-effects, deterministic
config) but, once (b) lands, is no longer what fixes the AWS bug.

### F5 — (b) blast radius is small for local, but has a PROD dependency
- **Local DynamoDB already works without real keys:** `services/dynamodb_client.py` overrides the
  endpoint only when `AWS_ENDPOINT_URL_DYNAMODB` is set and defaults creds to the literal
  `"local"`. So stripping the keys does not break local DynamoDB.
- **SNS/Cognito clients mostly use ambient creds already:** `aws_notifications.py` and
  `routes/sysadmin_health.py` build `boto3.client(..., region_name=...)` with NO static keys.
- **The one code reader of the static keys** is `services/user_language_service.py` (passes
  `aws_access_key_id`/`aws_secret_access_key` explicitly) — migrate it to ambient/profile.
- **⚠ PROD (Railway) dependency — the open risk:** the deployed Flask app has no
  `~/.aws` profile. If Railway relies on these as process env for SNS/Cognito, removing them from
  the *committed* files is fine ONLY IF Railway supplies them as **service-level variables**
  independent of the committed `.env`. This MUST be confirmed before the prod-affecting step
  (see `tasks.md` T-GATE).

## Why this is now a documented bugfix (not an inline checklist)
The scope grew under investigation: 8 modules + ~30 scripts + a production credential dependency.
That is enough moving parts and enough prod risk to warrant a written approach (`bugfix.md`) and a
gated task list (`tasks.md`) rather than editing on the fly.

## Acceptance (what "fixed and forgotten" means)
1. Importing any backend module does NOT mutate pre-set `AWS_*` env (regression test).
2. After the steering-41 strip, `aws sts get-caller-identity --profile nonprofit-deploy` resolves
   **506221081911** even in a process that imported `database`.
3. Local DynamoDB still works with no real keys (the `"local"` default).
4. The deployed Flask app still has working SNS/Cognito (Railway supplies creds another way).
5. App boots; related tests green.
