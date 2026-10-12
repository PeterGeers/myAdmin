# Implementation Plan: load_dotenv clobbers AWS_PROFILE

## Overview

Fix the bug where static personal-account AWS keys in the `.env` files are re-injected by
`load_dotenv()` and silently override `AWS_PROFILE`, sending ops scripts to the wrong AWS account.
Read `analysis.md` (findings F1–F5) + `bugfix.md` (approach + risks) first.

Approach (user decision 2026-10-12): **(b) strip the static AWS keys from the committed env files
+ migrate the one code reader to ambient creds** (the actual cure, per finding F4), and **(a)
remove the import-time `load_dotenv` side-effect from the 8 modules** (hygiene). `app.py` keeps its
single startup load.

Ordering is deliberate. Wave 0 (the (a) hygiene edits + regression test) is safe, local, and has
no production impact. **Task 4 is a production gate**: the credential strip (tasks 5–6) must not
run until Railway's AWS credential source is confirmed, because removing the keys can break Railway
SNS/Cognito if the deployed app relies on the committed `.env`. This bugfix is the prerequisite
gate for the Members `Parameter redesign` Phase 0.

## Tasks

- [x] 1. Remove the import-time `load_dotenv` from the 8 modules. Delete the pinned
  `load_dotenv(dotenv_path=... / ".env")` call + its comment (and the now-unused `from dotenv
  import load_dotenv` / `from pathlib import Path` where Path is only used for that) from
  `backend/src/database.py`, `transaction_logic.py`, `actuals_routes.py`, `google_drive_service.py`,
  `image_ai_processor.py`, `hybrid_pricing_optimizer.py`, `ai_extractor.py`. Keep `app.py`'s
  startup load.
  - Verify: ruff clean (no unused imports); each module still imports.

- [x] 2. Add regression test `backend/tests/unit/test_env_import_safety.py`: set
  `AWS_PROFILE=nonprofit-deploy`, ensure the two static keys are unset, import `database` (and one
  other of the 8), assert the keys stay unset and `AWS_PROFILE` is unchanged.
  - Verify: passes now; would FAIL against pre-fix code.
  - Depends on: 1

- [x] 3. Smoke — import `app` (startup load still runs) and run the suites touching the 8 modules.
  - Verify: app imports; no new failures.
  - Depends on: 2

- [x] 4. GATE — confirm Railway's AWS credential source. Verify the deployed Flask app gets
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` from Railway service variables (or an IAM role),
  independent of the committed `.env`. If not confirmed, set the Railway service variables first.
  This task BLOCKS tasks 5 and 6.
  - Verify: written confirmation recorded here of how Railway supplies creds.

  ### GATE CONFIRMATION (recorded 2026-10-12, from repo evidence)

  **Verdict: CONFIRMED from repo evidence — Railway supplies the backend's AWS creds as
  service-level variables sourced from a dedicated IAM user, independent of the committed `.env`.
  The committed env files are structurally incapable of reaching the Railway runtime.**

  Evidence chain (all in-repo, verified):

  1. **Dedicated IAM user for Railway** — `infrastructure/iam-railway-backend.tf` defines
     `aws_iam_user.railway_backend` (`myadmin-railway-backend`, path `/service-accounts/`) with an
     `aws_iam_access_key`, scoped least-privilege policies (S3, DynamoDB landing-pages, Cognito
     admin, SNS publish, SES send, CloudFront). Terraform outputs
     `railway_backend_access_key_id` / `railway_backend_secret_access_key` (sensitive) exist
     expressly "to set as AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in Railway".

  2. **Deployment doc instructs service variables, not committed files** —
     `railway/backend-env-variables.md` tells the operator to set `AWS_ACCESS_KEY_ID` /
     `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION=eu-west-1` in the Railway **dashboard →
     backend service → Variables tab**, with values from `terraform output
     railway_backend_access_key_id` / `-raw railway_backend_secret_access_key`.

  3. **The committed `.env` never ships to Railway** — Railway builds the backend from
     `backend/Dockerfile` (`backend/railway.json` + `backend/railway.toml`,
     `builder = DOCKERFILE`). The Dockerfile does `COPY . .`, but **both** `.dockerignore` files
     exclude `.env`:
     - `/.dockerignore` → `.env`
     - `/backend/.dockerignore` → `.env` and `.env.example`
     So the key-bearing files are not baked into the image. They are also gitignored
     (`.gitignore:274 .env`; `git ls-files` tracks only `backend/.env.example`), so they are not
     in the repo Railway pulls either.

  4. **`app.py` startup load is a no-op on Railway** — `backend/src/app.py:101` does
     `load_dotenv(dotenv_path=backend/.env)`. Since `backend/.env` is excluded from the image,
     that call finds no file in the Railway runtime and injects nothing; the process runs purely
     on Railway-injected service variables. **Therefore removing the two key lines from the
     committed files (task 6) cannot change what Railway injects at runtime** — RISK-1 is retired
     by construction.

  **What this gate could NOT verify from the repo (and does not need to, to unblock):** I cannot
  open the live Railway dashboard, so I cannot visually confirm the two variables are *currently
  populated* in the running backend service. The repo proves the *design and mechanism* (service
  vars from the dedicated IAM user) and proves the committed files are not the source. The
  deployed app already exercises SNS/Cognito/SES successfully via this same ambient-cred path
  (`aws_notifications.py`, `routes/sysadmin_health.py` build clients with no static keys), which
  is indirect evidence the Railway vars are set.

  **Operator pre-strip check (recommended belt-and-suspenders before task 6 ships to prod):** in
  the Railway dashboard, backend service → Variables, confirm `AWS_ACCESS_KEY_ID` and
  `AWS_SECRET_ACCESS_KEY` are present (values from the `myadmin-railway-backend` terraform
  outputs). If absent, set them there first, then proceed. This does not block tasks 5/6 locally —
  the committed files never feed Railway — but it is the one live check that closes RISK-1 fully.

  **LIVE CONFIRMATION (recorded 2026-10-12 — RISK-1 now fully closed).** The operator ran the
  Railway CLI (`railway link` → workspace *Peter Geers's Projects*, project *my-admin*,
  environment *production*) and inspected the **backend service → Variables** in the Railway
  dashboard. All three AWS vars are present on the backend service: `AWS_REGION`,
  `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` (secret values not read). This is the live
  check the gate flagged as outstanding; the deployed backend therefore gets its AWS creds
  from Railway service variables, independent of the (now key-stripped) committed `.env`.
  Confirmed by TWO independent checks: the dashboard view AND `railway variables` against the
  backend service, which lists `AWS_ACCESS_KEY_ID`, `AWS_REGION` (= `eu-west-1`), and
  `AWS_SECRET_ACCESS_KEY` (secret values masked/not recorded). Note: the earlier empty
  `railway variables` grep was only because `railway link` had attached the dir to the *MySQL*
  service, not the backend one — a linking artifact, not an absence of the vars.

  **Gate decision: tasks 5 and 6 are UNBLOCKED.** The credential strip touches only committed,
  gitignored, image-excluded files; it has no path to the Railway runtime, whose creds come from
  service variables backed by the dedicated IAM user.

- [x] 5. Migrate the one code reader to ambient creds.
  `backend/src/services/user_language_service.py::get_cognito_client()` — drop the explicit
  `aws_access_key_id`/`aws_secret_access_key` kwargs, keep `region_name` (matches
  `aws_notifications.py` / `routes/sysadmin_health.py`).
  - Verify: client builds; language lookup works.
  - Depends on: 4

- [x] 6. Remove the static AWS keys from the committed env files. Delete ONLY these lines (keep
  `AWS_REGION`; keep `AWS_ENDPOINT_URL_DYNAMODB` in `backend/.env`): `.env` lines 41–42,
  `backend/.env` lines 36–37, `backend/.env.example` lines 28–29 (replace the example lines with a
  comment pointing to `AWS_PROFILE` / Railway service vars).
  - Verify: grep finds no `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in the committed files;
    nothing else changed.
  - Depends on: 4, 5

- [x] 7. Verify local DynamoDB unaffected. With `AWS_ENDPOINT_URL_DYNAMODB` set and no static keys,
  confirm `dynamodb_client` builds + talks to the local container (the `"local"` default).
  - Verify: a local DynamoDB read/write smoke works.
  - Depends on: 6

- [x] 8. Verify account resolution. With the steering-41 strip,
  `aws sts get-caller-identity --profile nonprofit-deploy` resolves 506221081911 in a process that
  imported `database`.
  - Verify: identity = 506221081911 (NonprofitDeployRole), not 344561557829.
  - Depends on: 6

- [x] 9. Update steering `41-shell-environment.md` — state the static keys were removed; profiles /
  Railway service vars are the single cred source.
  - Depends on: 8

- [x] 10. Update `backend/validate_env.py` — mark the two static keys not-required.
  - Depends on: 8

- [x] 11. (optional) Retire the `_restrip_aws_env()` crutch in
  `scripts/aws/project-config-to-prod.py` once tasks 1–8 are green.
  - Depends on: 8

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "4"] },
    { "id": 1, "tasks": ["2", "5"] },
    { "id": 2, "tasks": ["3", "6"] },
    { "id": 3, "tasks": ["7", "8"] },
    { "id": 4, "tasks": ["9", "10", "11"] }
  ]
}
```

Notes on the graph: tasks 1–3 (the safe (a) edits + tests) and task 4 (the prod gate) can start in
parallel. Task 4 BLOCKS tasks 5 and 6 — the credential strip must not proceed until the Railway
cred source is confirmed. Task 5 (migrate the reader) precedes task 6 (remove the keys). Tasks
7–8 verify after the strip; tasks 9–11 are docs + optional cleanup.

## Notes

- Done when acceptance 1–5 in `analysis.md` hold: imports inert, account resolves correctly after a
  strip, local DynamoDB works keyless, deployed SNS/Cognito still works via Railway creds, app
  boots + tests green.
- Scripts are intentionally not de-dotenv'd (finding F3 — ~30 of them, unbounded); (b) makes their
  `load_dotenv()` harmless, so they need no change.
- Rollback is local and trivial: re-add the two key lines to the env files and restore the removed
  `load_dotenv` lines. No migrations, no data changes.
- Secret hygiene: task 6 touches only the two AWS key lines per file; values are never echoed; the
  env files are gitignored.
