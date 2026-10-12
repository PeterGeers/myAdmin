# BUGFIX — APPROACH: `load_dotenv()` clobbers `AWS_PROFILE`

> **Doc 2 of 3.** Read `analysis.md` first (the grounded findings F1–F5). This doc records the
> chosen fix, the decisions, the risks + mitigations, and the rollback. Work items are in
> `tasks.md`.

## Chosen approach: (b) full + (a) full — "fix it and forget it" (user decision 2026-10-12)
- **(b) — remove the static personal-account AWS keys from the committed env files** (`.env`,
  `backend/.env`, `backend/.env.example`) and migrate the one code reader to ambient/profile
  creds. This is what actually kills the bug — once the keys aren't in the files, no
  `load_dotenv()` (module or script, per F3) can re-inject them.
- **(a) — remove the import-time `load_dotenv` side-effect from the 8 modules** (F2); keep the
  single legitimate startup load in `app.py`. This is hygiene (no import side-effects,
  deterministic config), done because the user chose the thorough "forget it" fix — not because
  it is what fixes the AWS bug (F4).

Rejected: **(c) a shared `ops_env` helper** — only protects callers that remember to use it;
leaves the trap armed for the next unaware script.

## Credential model AFTER the fix (the important part)
Static long-lived keys stop being the mechanism anywhere. Creds resolve by context:
- **Local dev / ops scripts:** `AWS_PROFILE` (`personal` by default; `nonprofit-deploy` with the
  steering-41 strip). No static keys in files to override the profile.
- **Local DynamoDB:** unchanged — `dynamodb_client.py` uses the literal `"local"` creds when
  `AWS_ENDPOINT_URL_DYNAMODB` is set. `AWS_ENDPOINT_URL_DYNAMODB` stays in `backend/.env`.
- **Deployed Flask (Railway):** creds come from **Railway service variables** (set in the Railway
  project, NOT the committed repo files) or an IAM role — see RISK-1. The committed `.env` losing
  the keys must not change what Railway injects at runtime.
- **SAM/Lambda:** unaffected (uses the Lambda execution role).

## Decisions
- **D1.** `AWS_REGION` stays in the env files (not a credential; harmless, widely read).
- **D2.** `AWS_ENDPOINT_URL_DYNAMODB` stays in `backend/.env` (local DynamoDB switch; needs no real
  keys per F5).
- **D3.** `user_language_service.get_cognito_client()` drops the explicit
  `aws_access_key_id`/`aws_secret_access_key` kwargs and lets boto3 resolve ambient/profile creds —
  matching `aws_notifications.py` / `sysadmin_health.py`.
- **D4.** `app.py` keeps its startup `load_dotenv(backend/.env)`; the 8 modules do not reload.
- **D5.** Scripts are NOT individually de-dotenv'd (F3 unbounded); (b) makes their `load_dotenv()`
  harmless, so they are left as-is.

## Risks + mitigations
- **RISK-1 (PROD, blocking) — Railway credential source.** If the deployed app reads the committed
  `.env` for AWS creds, stripping them breaks SNS/Cognito in production. **Mitigation:** confirm
  Railway supplies `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` as **service variables** (or an IAM
  role) BEFORE the strip. This is `tasks.md` **T-GATE** and blocks T4/T5. If unconfirmed, do NOT
  strip the deployed source — only the committed files, and set Railway service vars first.
- **RISK-2 — a module relied on the import-time load for NON-AWS config** (e.g. `OPENROUTER_API_KEY`,
  DB vars) when imported outside `app.py` (a script that did NOT call `load_dotenv` first).
  **Mitigation:** F3 shows scripts load env themselves; verify the test suite + a smoke import.
  Keep `app.py`'s startup load intact so the web path is unchanged.
- **RISK-3 — `user_language_service` ambient creds differ from the old explicit keys** in some
  environment. **Mitigation:** it now matches the already-working SNS/Cognito pattern; covered by
  the same Railway cred source as RISK-1.
- **RISK-4 — secret hygiene.** The `.env` files may hold other live secrets. **Mitigation:** touch
  ONLY the two AWS key lines per file; never echo values; files are gitignored (local-tree change).

## Rollback
All edits are small and local. Revert = re-add the two key lines to the env files and restore the
removed `load_dotenv` lines. No migrations, no data changes, no deploy required to revert local.

## Out of scope
- The Members config/version-bump work (its own spec).
- Converging the broader secret/config management across planes (separate backlog spec).
- Retiring `_restrip_aws_env()` in `project-config-to-prod.py` — optional cleanup once green.
