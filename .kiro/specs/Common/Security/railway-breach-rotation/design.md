# Railway Breach — Secret Rotation & Env Rebuild (Design)

> NO-CREDENTIALS RULE applies (see `requirements.md`): names, process, status only. No secret
> values anywhere in this spec. Placeholder tokens in commands; real values only in the user's
> shell at execution time.

## Overview

This design governs rotating every secret exposed by the Railway breach, propagating new values to
Railway (system of record) and the three local `.env` files, re-encrypting the data-at-rest master
key in place, and rotating the tenant-stored secrets that were decryptable. The controlling
insight (§ Architecture) is that the backend is a JWT *verifier*, not a login server, so most
rotations do not touch the running request path — enabling a "stage now, cut over later" split
around the Railway Hobby build outage. Sections below cover the architecture, the per-secret
analysis, the re-encryption component, the data models touched, error handling, and testing.

## Architecture

### Controlling architectural fact: the backend is a JWT *verifier*, not a login server

The myAdmin Flask backend receives already-issued Cognito JWTs on the `Authorization: Bearer`
header and verifies their signature against the pool JWKS. It does **not** call Cognito login
APIs (no `initiate_auth` / `admin_initiate_auth`, no `SECRET_HASH`), and it has **no** Flask
session signing (`app.secret_key` / Flask-Session / `CSRFProtect` are absent). Interactive login
is the Cognito **Hosted UI**, outside this service.

Consequence: rotating most of these secrets does **not** touch the request path of the already-
running container. This is what makes the safe-now vs must-wait split in §3 possible.

### Hobby-outage gating model

A running Railway container keeps the environment from its **last deploy**. Setting a Railway
**variable** changes only the *desired* config for the *next* deploy; the live container does not
see it until a **redeploy**. Builds are degraded for the Hobby tier, so redeploy is currently
unavailable.

- 🟢 **Doable now:** anything that does not require the running container to pick up a new value —
  generating secrets, setting Railway variables (staging), updating/verifying local `.env`,
  and DB-side data operations via `railway-db.sh`.
- 🔴 **Blocked until Hobby builds restored:** anything that needs the live container to adopt a
  new value, and anything that invalidates a still-in-use credential — DB password promotion at
  the server, production redeploy/verify, deactivating/deleting old credentials, OneDrive scrub.

## Components and Interfaces

### Per-secret safe-now (🟢) vs must-wait (🔴) analysis (evidence from source)

| Secret (name) | Where read (file) | Running-prod impact of rotating | Verdict |
| ------------- | ----------------- | ------------------------------- | ------- |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | boto3 default chain — `services/cognito_service.py`, `services/signup_service.py`, `aws_notifications.py`, `services/email_verification_service.py`, `services/cloudfront_domain_service.py`; no key id pinned | Create a 2nd key → both valid; running container keeps using old | 🟢 rotate/stage now; 🔴 delete old at cutover |
| `COGNITO_CLIENT_SECRET` | `auth/pool_registry.py` `resolved_identity()` → `ResolvedIdentity.client_secret`; **no functional consumer**; `environment/_consistency_checks.py` `_check_client_secret` is a no-op in PRODUCTION | None on this backend; only Hosted-UI logins (done elsewhere) | 🟢 rotate now (verify Hosted-UI separately) |
| `SECRET_KEY` (env var) | not read in `backend/src` (confirmed: only unrelated `RECAPTCHA_SECRET_KEY` and the Flask-key-name list in `scripts/test_maintenance/drift_detector.py` / log-sanitizer tests) | None — vestigial | 🟢 **retire** (remove) |
| `stripe_secret_key` (per-tenant DB param — **distinct from `SECRET_KEY`**) | `routes/str_routes.py` `get_param("str","stripe_secret_key",tenant=...)` → `str_stripe_enrichment.py` (dfDirect/**Guesty** Stripe enrichment) | Live feature; encrypted at rest under the master key → decryptable in the breach | §4.1 tenant rotation (Task 13) |
| `CSRF_SECRET` | `services/signup_service.py` (`__init__` read; `validate_csrf_token`, fails open when empty) | Public signup form token match only | 🟢 rotate now (frontend must carry new value) |
| `CREDENTIALS_ENCRYPTION_KEY` | `services/credential_service.py` master key (PBKDF2→Fernet; per-tenant salt=tenant; master static salt `b"myAdmin_credential_salt"`); `services/parameter_service.py` delegates for `is_secret` params | Running container unaffected (key already in memory); **but a new key makes all stored data undecryptable** | Special — §4 re-encryption, not a swap |
| `DB_PASSWORD` / `MYSQL_ROOT_PASSWORD` | `database.py` `_resolve_mysql_config()` → baked into the pool at construction (legacy pool size 10 + scalability pool) | Changing at the server breaks the live pool on connection recycle | 🔴 promote only at redeploy cutover |

### `CREDENTIALS_ENCRYPTION_KEY` re-encryption component

The key is a **data-at-rest master key**. Swapping the env var alone leaves every
`tenant_credentials` row (per-tenant derived Fernet key) and every `is_secret` parameter (master
cipher) encrypted under the OLD key → `InvalidToken` on the next boot. Rotation therefore requires
a migration, not a swap.

**Approach (safety net = Railway MySQL snapshot + in-memory-only transform):**

1. Precondition: confirm DB connectivity is stable (post-incident) and a Railway MySQL **snapshot**
   exists as the external rollback point (Task 1).
2. Generate a new 64-hex key at run time (never written to a tracked file).
3. One-off, **single-transaction** migration:
   - Read each `tenant_credentials` row; decrypt with the OLD key (tenant-derived), re-encrypt with
     the NEW key (same tenant salt); write back.
   - Read each `is_secret` parameter; decrypt with the OLD master cipher, re-encrypt with the NEW
     master cipher; write back.
   - All plaintext exists **only in memory** during the run. On any failure, roll back the
     transaction (Railway snapshot is the external net). **No decryptable dump on disk.**
4. Run against a non-prod / copy target first, then Railway MySQL via `backend/scripts/railway-db.sh`.
5. Stage the new key as a Railway variable + update `backend/.env`. It becomes the effective app key
   only on the next **redeploy** (🔴 for prod effect).
6. Change-with-tests: add/adjust paired tests for the migration and `credential_service`; run
   `python -m pytest <paths> -q`.

## Data Models

### Tenant-stored secrets (data-at-rest) rotation — Task 13

The two MySQL stores touched by the encryption-key rotation (Task 8) and the tenant-secret
rotation (Task 13):

- **`tenant_credentials`** — columns `administration`, `credential_type`, `encrypted_value`
  (base64 Fernet ciphertext, per-tenant derived key, salt = `administration`).
- **`parameters`** (rows with `is_secret = 1`) — the `value` column holds
  `json.dumps(<base64 Fernet ciphertext>)` under the master cipher (static salt).

The per-tenant source-side rotation:

The breach exposed `CREDENTIALS_ENCRYPTION_KEY` **and** DB access together, so every per-tenant
secret encrypted in MySQL was decryptable. These are not Railway variables and are not fixed by
the Task 7 re-encryption (re-encrypting under a new master key does **not** make an
already-exposed plaintext secret safe — the *value* itself leaked). Each must be rotated at its
own source and re-entered. The user is tenant admin for all tenants, so this is a single-operator
sweep.

| Stored secret | Where | Rotation action (per tenant) |
| ------------- | ----- | ---------------------------- |
| `stripe_secret_key` (`is_secret` param, module `str`) | `parameters` | Roll the key in the tenant's Stripe dashboard; re-enter via Tenant Admin → Parameters |
| `google_drive_oauth` / `google_drive_token` / `google_drive_credentials` | `tenant_credentials` | Revoke/re-issue the Google OAuth client/token; re-upload |
| `s3_credentials` | `tenant_credentials` | Rotate the tenant's AWS key; re-upload |

Ordering: Task 13 can begin once Task 7 has re-encrypted the store (so new values are stored under
the new master key). Inventory which tenants actually have each secret set before rotating (no
blind assumptions, no values printed).

### Rotation order (dependency-aware)

1. **AWS keys first** — widest blast radius, zero-downtime, and closes `/h-dcn/` SSM reachability.
2. **Contain DB-proxy exposure** (restrict/disable the public TCP proxy if Railway allows) — the
   highest un-rotatable risk during the outage.
3. Stage Cognito, OpenRouter, CSRF; retire SECRET_KEY.
4. Re-encrypt + stage `CREDENTIALS_ENCRYPTION_KEY` (DB-stability gated).
5. Stage the full Railway variable set + rebuild the three `.env` files.
6. **Cutover (🔴):** promote DB password at the server in lockstep with the redeploy; verify prod.
7. **Invalidate** old credentials; scrub OneDrive plaintext.
8. **Tenant-stored secrets** (Task 13): after Task 7 re-encryption, rotate each tenant's Stripe /
   Google Drive / S3 credential at source and re-enter.

## Error Handling

- **Re-encryption (Task 8):** single transaction; any decrypt/re-encrypt failure rolls back every
  write. A row the OLD key cannot decrypt raises `ReencryptError` and aborts (no silent skip, no
  partial write). Railway MySQL snapshot is the external rollback net. `--dry-run` is the default;
  `--commit` only after a clean dry-run.
- **Staging vs running prod:** setting a Railway variable never affects the live container (no
  deploy), so a wrong staged value cannot break production before the cutover is validated.
- **DB password:** never promoted at the server until the redeploy is ready (promoting early breaks
  the live connection pool). This is the one rotation gated 🔴.
- **No-credentials rule:** generated/rotated values are never written to a tracked file; command
  output that could carry a value goes only to `.agent-output/` (gitignored) and is deleted after use.

## Testing Strategy

- **Migration unit tests** (`backend/tests/unit/test_maintenance/test_reencrypt_credentials_key_rotation.py`,
  4/4 passing): round-trip fidelity for the master cipher and the per-tenant derived cipher; a
  wrong-OLD-key blob raises `ReencryptError`; a fresh NEW-key `CredentialService` can read the
  re-encrypted output. DB-free (honors the unit-test isolation layer).
- **Dry-run before commit** against a non-prod/copy target, then Railway MySQL.
- **Post-cutover smoke test** (Task 11): live auth, a DB read, a secret-parameter read (confirms
  re-encryption), and an AI call.
- **Change-with-tests contract:** any behavioral edit to `credential_service` / the migration updates
  its paired test in the same change; `python -m pytest <paths> -q` run before marking done.

## Correctness Properties

Invariants the rotation must preserve end to end:

### Property 1: No secret in a tracked file

At every step, `git ls-files` shows no `.env`/secret file; spec and committed files contain
names/placeholders only. (Access key *IDs* are identifiers, not secrets, and may appear.)

**Validates: Requirements 2.2, 6.4**

### Property 2: Running production never breaks before cutover

No 🔴 action (DB password promotion, deleting an in-use credential) runs until the redeploy is
ready; staged variables are inert until deploy.

**Validates: Requirements 3.2, 3.3**

### Property 3: Re-encryption is lossless

After Task 8, every `tenant_credentials` row and `is_secret` parameter decrypts correctly under the
NEW key; a failure rolls back atomically with no partial writes and no plaintext on disk.

**Validates: Requirements 4.1, 4.3**

### Property 4: Rotation beats re-encryption for leaked values

Tenant-stored secrets whose plaintext leaked (Task 13) are rotated at source — re-encryption alone
is not treated as sufficient.

**Validates: Requirements 5.2, 5.3**

### Property 5: Old credentials stay valid until the new ones are live

Old AWS key / DB password / etc. are invalidated only after a healthy cutover (Phase D), never before.

**Validates: Requirements 1.2**

## Secondary exposure & gaps (Task 15 — recorded, not acted on here)

- **`/h-dcn/` SSM parameters** (account `506221081911`, profile `nonprofit-deploy`, eu-west-1):
  belong to the phasing-out single-tenant h-dcn SAM workspace; **not read by myAdmin**; never in
  Railway, so NOT in the Railway breach blast radius. Enumerated during planning (names only):
  `/h-dcn/gemini-api-key` (SecureString), `/h-dcn/google-photos-oauth` (SecureString),
  `/h-dcn/mollie-api-key` (String), `/h-dcn/prod/cognito/default-temp-password` (String),
  `/h-dcn/prod/google/client-id` (String), `/h-dcn/prod/google/client-secret` (String).
  A holder of the leaked myAdmin AWS keys *could* have read them (same account), so rotating the
  AWS keys (**Task 3**) closes that reachability. Rotating the h-dcn secrets themselves, if desired,
  is a separate effort on the phasing-out h-dcn track — out of scope for this spec.
- **Secrets Manager in `506221081911`** could not be enumerated (the `NonprofitDeployRole` lacks
  `secretsmanager:ListSecrets` → `AccessDeniedException`). Secrets Manager in `344561557829` was
  empty. The app uses NO Secrets Manager / SSM at runtime (code grep + backlog confirm), so this is
  recorded as an open enumeration gap, not a rotation target.

## Existing-doc reconciliation

- `Environment-Files-Strategy.md` (same folder) — **partly stale**; follow the three-file model in
  `requirements.md` §4 and bash tooling, not that doc's PowerShell/`sync-env-files.ps1` workflow.
- `ENCRYPTION_KEY_STORAGE.md` (same folder) — **empty**; no prior constraint on Task 7.
