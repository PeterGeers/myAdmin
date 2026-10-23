# Requirements Document

> **NO-CREDENTIALS RULE (binding for this whole spec):** these files contain variable
> **names**, process, and status **only**. No secret value — not even a placeholder that
> is a real value — may appear in any file under this spec or any tracked/committed file.
> Commands shown here use placeholder tokens (e.g. `<OLD_ACCESS_KEY_ID>`); runnable
> commands with real values are given to the user in chat at execution time, and the user
> substitutes real values in their own shell.

## Introduction

On 2026-10-22 Railway disclosed a security incident: an unauthorized third party may have
accessed encrypted environment variables and, for some, obtained the **decrypted** contents.
Environment variables can hold API keys, database/registry credentials, and signing/encryption
keys. Every secret stored in the myAdmin Railway service must therefore be treated as
**compromised** and rotated at its source — this is a credential rotation, not a file rebuild.

Compounding constraint: the workspace is on Railway's **Hobby** tier, and Railway's
build/deploy service is degraded. Builds were restored for Pro/Enterprise first, then Hobby,
then Free/Trial — Hobby was **not yet restored** at the time this spec was written. A running
Railway container keeps the environment it loaded at its **last deploy**; setting a new Railway
variable does **not** affect the running container until a redeploy happens. This splits the
work into what can be done now (🟢) vs what must wait for the redeploy cutover (🔴).

## Glossary

- **System of record** — Railway holds the authoritative live secret values going forward.
- **Vault JSON** — `work-railway.json` / `work-railway - empty.json` in the OneDrive Personal
  Vault; a temporary working artifact, not a committed source of truth.
- **Schema reference** — `railway-vars.schema.json` (committed, secret-free): the non-secret key
  list + non-secret config values, with all secret keys blank. The non-Vault source for Tasks 8–9.
- **Data-at-rest secret** — a per-tenant secret stored encrypted in MySQL under
  `CREDENTIALS_ENCRYPTION_KEY` (not a Railway variable).
- **🟢 / 🔴** — doable now without a Railway build / blocked until Railway Hobby builds restored.

## Requirements

### Requirement 1 — Rotate every compromised Railway secret

**User Story:** As the operator, I want every secret exposed by the Railway breach rotated at its
source, so that the leaked values are no longer valid.

#### Acceptance Criteria

1. WHEN rotation is complete THEN every secret in the inventory (§ Secret inventory) SHALL have a
   new value issued at its source and the old value invalidated.
2. WHERE a secret cannot be invalidated without breaking running production during the Hobby
   outage, the system SHALL stage the new value and defer invalidation to the redeploy cutover (🔴).
3. THE rotation SHALL be a full rotation, never a reconstruct-from-old-values.

### Requirement 2 — Railway is the system of record; no credentials in tracked files

**User Story:** As the operator, I want Railway to hold the live values and no secret to live in
any committed file, so that the repo and spec are never a secret source.

#### Acceptance Criteria

1. THE Railway variable set SHALL be the system of record for live secret values.
2. THE spec files and any tracked/committed file SHALL contain zero secret values (names, process,
   status, and placeholder tokens only).
3. WHEN non-secret config is needed (Tasks 8–9) THEN the committed secret-free
   `railway-vars.schema.json` SHALL be the reference, not the Vault JSON.
4. THE Vault JSON plaintext secrets MAY be scrubbed early (once Railway holds the rotated values),
   not only at Task 11, because no task depends on the Vault JSON for non-secret config.
5. WHERE a `.env` backup is wanted, it SHALL go to the OneDrive Personal Vault, never the repo.

### Requirement 3 — Honor the Hobby-outage safe-now vs must-wait boundary

**User Story:** As the operator, I want rotations that would break the still-running production
container deferred, so that production keeps serving during the outage.

#### Acceptance Criteria

1. THE plan SHALL mark each task 🟢 (safe now) or 🔴 (needs the redeploy cutover).
2. THE `DB_PASSWORD` promotion at the MySQL server SHALL be deferred to the cutover (🔴).
3. WHEN a secret is staged as a Railway variable THEN the system SHALL treat it as inert until the
   next redeploy.

### Requirement 4 — Rotate CREDENTIALS_ENCRYPTION_KEY without data loss

**User Story:** As the operator, I want the data-at-rest master key rotated with a re-encryption
migration, so that existing encrypted rows remain decryptable.

#### Acceptance Criteria

1. THE key rotation SHALL decrypt with the OLD key and re-encrypt with the NEW key, in memory
   only, inside a single transaction, with no decryptable dump on disk.
2. THE safety net SHALL be a Railway MySQL snapshot (rollback point) plus transaction rollback.
3. WHEN re-encryption completes THEN all `tenant_credentials` rows and `is_secret` parameters SHALL
   decrypt correctly under the new key.
4. THE migration SHALL be run against a non-prod/copy target before Railway MySQL, and SHALL have
   paired tests per the change-with-tests contract.

### Requirement 5 — Rotate breach-exposed tenant-stored secrets

**User Story:** As tenant admin for all tenants, I want the per-tenant secrets that were
decryptable in the breach rotated at source, so that leaked tenant credentials are invalidated.

#### Acceptance Criteria

1. THE in-scope tenant-stored secrets SHALL be `stripe_secret_key`, `google_drive_oauth`,
   `google_drive_token`, `google_drive_credentials`, and `s3_credentials`.
2. WHEN rotating THEN each SHALL be re-issued at its own source and re-entered via Tenant Admin.
3. THE re-encryption (Requirement 4) SHALL NOT be treated as a substitute for value rotation — the
   plaintext values leaked, so they must be rotated regardless.

### Requirement 6 — Rebuild the three `.env` files per the current model

**User Story:** As the operator, I want the local `.env` files rebuilt correctly, so that local
dev works and no secret is tracked.

#### Acceptance Criteria

1. Root `.env` SHALL carry `RAILWAY_DB_*` + root-script needs only (the backend app does not load it).
2. `backend/.env` SHALL carry app config + rotated secrets, with static AWS keys kept OUT of the
   app load path (boto3 default chain / `AWS_PROFILE`).
3. `frontend/.env` SHALL carry `VITE_*` only.
4. `git ls-files` SHALL show no tracked `.env`/secret file before or after.

## Scope

**In scope** — the myAdmin Flask/Railway secret set:

- Root `.env`, `backend/.env`, `frontend/.env` (the "secrets files"; Requirement 6).
- The Railway variable set (system of record).
- **Tenant-stored secrets encrypted under `CREDENTIALS_ENCRYPTION_KEY`** (Stripe keys, Google Drive
  creds, per-tenant S3 creds) — not Railway variables, but decryptable in the breach (master key +
  DB access both exposed), so in scope for rotation (Requirement 5 / Task 13). Single-operator
  rotation (user is tenant admin for all tenants).

**Out of scope:**

- The `/h-dcn/` SSM parameters in account `506221081911` — belong to the phasing-out single-tenant
  **h-dcn** SAM workspace, not read by myAdmin, never stored in Railway. Recorded as a secondary
  exposure note (design.md §6, Task 12): reachable to a holder of the leaked AWS keys, so rotating
  the AWS keys (Task 2) closes that reachability.

## The three `.env` files (current steering model)

- **root `.env`** — Railway wrapper (`RAILWAY_DB_*` consumed by `backend/scripts/railway-db.sh`)
  + root-run scripts only. The backend app does **not** load this file.
- **`backend/.env`** — the single file the backend app + docker-compose load (DB_*, COGNITO_*,
  OPENROUTER_API_KEY, CREDENTIALS_ENCRYPTION_KEY, etc.). Static AWS keys kept OUT of this load path.
- **`frontend/.env`** — Vite `VITE_*` vars only.

> The older `Environment-Files-Strategy.md` in this folder is **partly stale** (PowerShell workflow
> + an "root `.env` holds all secrets" model that predates the WSL/Linux migration and the
> three-file separation). Follow the model above, not that doc.

## Secret inventory (by NAME only)

### Secrets to rotate (compromised)

| Variable name | Class | Rotatable now without breaking running prod? |
| ------------- | ----- | -------------------------------------------- |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | External (IAM user, static) | **Yes** — create 2nd key, both valid; delete old at cutover |
| `DB_PASSWORD` / `MYSQL_ROOT_PASSWORD` / `RAILWAY_DB_PASSWORD` | External (Railway MySQL) | **No** — changing at the server breaks the live pool; wait for redeploy |
| `COGNITO_CLIENT_SECRET` | External (Cognito app client) | **Yes** — no backend consumer; affects Hosted-UI login only |
| `OPENROUTER_API_KEY` | External (OpenRouter) | **Yes** (old already dead); prod AI down until redeploy |
| `CSRF_SECRET` | App signing (signup form) | **Yes** — signup form only |
| `SECRET_KEY` | App signing (**vestigial env var**) | **Retire** — unused in backend (NOT the same as `stripe_secret_key`, see below) |
| `CREDENTIALS_ENCRYPTION_KEY` | **Data-at-rest master key** | **Special** — needs in-memory re-encryption migration, not a swap |

### Tenant-stored secrets (data-at-rest) — breach-exposed, NOT Railway variables

These are per-tenant secrets encrypted in MySQL under `CREDENTIALS_ENCRYPTION_KEY`. Because the
breach exposed that master key **and** DB access (`DB_PASSWORD`) together, an attacker could decrypt
all of them → they must be rotated too (Requirement 5 / Task 13).

| Stored secret (type / name) | Storage | Code path |
| --------------------------- | ------- | --------- |
| `stripe_secret_key` (`is_secret` parameter, module `str`) | `parameters` (master cipher) | `routes/str_routes.py` → `str_stripe_enrichment.py` (dfDirect/**Guesty** import enrichment) |
| `google_drive_oauth` | `tenant_credentials` (per-tenant key) | `google_drive_service.py` |
| `google_drive_token` | `tenant_credentials` | `google_drive_service.py`, `services/google_oauth_service.py` |
| `google_drive_credentials` | `tenant_credentials` | `routes/tenant_admin_credentials.py` |
| `s3_credentials` | `tenant_credentials` | `storage/s3_tenant_storage.py` |

> **`SECRET_KEY` ≠ `stripe_secret_key`.** `SECRET_KEY` is a vestigial Flask **env var** (retire,
> Task 6). `stripe_secret_key` is a **live per-tenant DB parameter** driving the Stripe/Guesty
> dfDirect enrichment — deliberately per-tenant (a test asserts it is never read from a global
> `STRIPE_SECRET_KEY` env var). Different things; never conflate.

### Non-secret config (copied as-is, no rotation)

`AWS_REGION`, `SNS_TOPIC_ARN`, `COGNITO_CLIENT_ID`, `COGNITO_USER_POOL_ID`, `COGNITO_POOL_KEYS`,
`PROD_A_COGNITO_*`, `CLOUDFRONT_*`, `LANDING_PAGE_BASE_URL`, `LANDING_PAGES_BUCKET`,
`S3_SHARED_BUCKET`, `FACTUREN_FOLDER_ID`, `FACTUREN_FOLDER_NAME`, `FRONTEND_URL`,
`CONTACT_FORM_API_URL`, `ALLOWED_ORIGINS`, `ALLOW_MIGRATION`, `PROMO_DB_NAME`, `DB_HOST`,
`DB_NAME`, `DB_PORT`, `DB_USER`, `SES_SENDER_EMAIL`, `SIGNUP_ADMIN_EMAIL`,
`SIGNUP_COGNITO_APP_CLIENT_ID`, `SIGNUP_COGNITO_USER_POOL_ID`, `SIGNUP_REDIRECT_URL`, `APP_ENV`.

## AWS secret-store inventory (checked live during planning)

| Service / account | Result |
| ----------------- | ------ |
| Secrets Manager — `personal` (344561557829) | empty (`[]`) |
| Secrets Manager — `nonprofit-deploy` (506221081911) | **could not enumerate** — `NonprofitDeployRole` lacks `secretsmanager:ListSecrets` (gap; app does not use Secrets Manager) |
| SSM — `personal` | empty (`[]`) |
| SSM — `nonprofit-deploy` | six `/h-dcn/*` params (h-dcn workspace, out of scope) |

The myAdmin codebase uses **no** Secrets Manager / SSM at runtime (confirmed by repo grep + backlog
notes). Railway variables + SAM Lambda env vars are the only secret stores for the app.

## Confirmed decisions

| # | Decision |
| - | -------- |
| A | **Railway is the system of record.** The Vault JSON is a temporary working artifact. The committed secret-free `railway-vars.schema.json` (extracted in Task 1) means no task depends on the Vault JSON for non-secret config — it is needed only as a manual re-entry source for still-valid values while staging secrets (Tasks 2–7), and its plaintext may be scrubbed early. |
| B | **No `.secrets` file exists.** The "secrets files" are the three `.env` files. |
| C | **Mixed rotation:** CLI where clean (AWS IAM, Cognito, Railway), console where easier (OpenRouter). |
| D | **No-credentials-in-files** (see banner): placeholder tokens only; real values only in the user's own shell. |
| E | **Re-encryption safety net:** Railway MySQL snapshot + in-memory-only transform; no decryptable dump on disk. |
| F | **Full rotation** of every compromised secret. |
| G | **AWS keys rotated in place:** new pair for the SAME IAM user, deactivate then delete the old pair. |

## Success criteria

1. Every compromised secret rotated at source; Railway holds the new values; the three `.env` files
   rebuilt per the three-file model; no secret value in any tracked/committed file.
2. `CREDENTIALS_ENCRYPTION_KEY` rotated via an in-memory re-encryption migration with all existing
   `tenant_credentials` rows and `is_secret` parameters decrypting correctly afterward.
3. Tenant-stored secrets (Stripe/Google/S3) rotated at source and re-entered.
4. Production verified healthy after the Railway redeploy cutover; old credentials invalidated;
   OneDrive plaintext scrubbed.
5. `git ls-files` shows no tracked `.env`/secret file before or after.
