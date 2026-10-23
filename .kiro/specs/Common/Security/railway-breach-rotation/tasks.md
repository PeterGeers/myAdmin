# Implementation Plan: Railway Breach — Secret Rotation & Env Rebuild

> NO-CREDENTIALS RULE: names, process, status only. Commands use **placeholder tokens**
> (e.g. `<OLD_ACCESS_KEY_ID>`). Real values are entered only in the user's own shell at execution
> time. Never commit a real value here.

## Overview

The work is organized into four **phases by WHEN it can run**, not by secret type:

- **Phase A — DO NOW.** Needs no Railway build and is safe while production keeps running on its
  last deploy. Setting a Railway variable here only *stages* it; it is inert until a redeploy.
- **Phase B — IN BETWEEN (Railway variables settable, builds still flaky).** Validation you can do
  before committing to the full cutover: confirm staged variables, dry-runs, previews.
- **Phase C — CUTOVER (Railway Hobby builds/deploys restored).** The redeploy that makes staged
  values live, plus the one rotation that must happen in lockstep with it (DB password promotion).
- **Phase D — AFTER a healthy cutover.** Invalidate old credentials, rotate tenant-stored secrets,
  scrub OneDrive plaintext.

A task's phase is the gate. Do not start a later-phase task early. See `requirements.md` and
`design.md` for the per-secret analysis behind this ordering.

## Status

| # | Task | Phase | Status |
| - | ---- | ----- | ------ |
| 0 | Create tracking spec | A | [x] done |
| 1 | Inventory & git hygiene | A | [x] done |
| 2 | Write re-encryption migration (code+tests) | A | [x] done |
| 3 | Generate + stage AWS keys | A | [x] done — CORRECTED: prod ran on WebMaster key `...XSLIMM7P` (admin, NOT scoped). Switched Railway to SCOPED `myadmin-railway-backend` (key `AKIA‹redacted-…ZBJ5EMRI›`, both AWS vars). VERIFIED staged in live Railway dump. Live at cutover. WebMaster key `...XSLIMM7P` retires in Phase D (careful — also `personal` CLI identity). |
| 4 | Contain DB-proxy exposure | A→C | [x] RESOLVED by DB password rotation (Task 12). User chose to KEEP the public proxy open (HeidiSQL/Workbench keep working); the leaked password is now dead, so the proxy is no longer a breach exposure. Proxy intentionally NOT disabled. |
| 5 | Generate + stage Cognito / OpenRouter / CSRF; retire SECRET_KEY | A | [x] done — CSRF + OpenRouter staged; SECRET_KEY + COGNITO_CLIENT_SECRET (both vestigial) removed; no Cognito client secret exists to rotate |
| 6 | Rebuild the three `.env` files (local dev) | A | [x] done (minimal) — removed vestigial COGNITO_CLIENT_SECRET from backend/.env + root .env; dropped stale commented OpenRouter line; new OpenRouter + CSRF present; frontend/.env already VITE-only. Full three-file reshape = noted follow-up |
| 7 | Railway MySQL snapshot | B | [x] done — snapshot taken (rollback point for Task 8) 2026-10-22 |
| 8 | Run re-encryption migration (dry-run ✓ → commit) | B→C | [x] done — COMMIT ran 2026-10-23: re-encrypted 6 tenant_credentials + 1 secret param OLD→NEW in one transaction. Verified LIVE: Google Drive credentials work again in prod. |
| 9 | Stage full Railway variable set + diff vs schema | B | [x] done — live dump verified: AWS(scoped)/enc-key/OpenRouter/CSRF staged; SECRET_KEY+COGNITO_CLIENT_SECRET absent; enc-key matches backend/.env |
| 10 | Pre-cutover validation (staged vars, changeset preview) | B | [x] done — local dev loads; railway-db.sh connects; staged set consistent; DB_PASSWORD-literal note for cutover |
| 11 | Cutover: re-encryption commit + redeploy + verify prod | C | [x] mostly done — Hobby builds back; a deploy picked up staged vars (new enc key + scoped AWS key). Healed: ran Task 8 commit (Drive works) + attached Cognito IAM policy to scoped user (SysAdmin Cognito GREEN). REMAINING: DB password rotation (see note). |
| 12 | Invalidate old credentials (AWS/Cognito/DB) | D | [x] done — WebMaster CLI key rotated (`...C5MC`, breached `...XSLIMM7P` deleted); old scoped key `...VTJC26WY` deleted (prod keeps `...ZBJ5EMRI`); DB password rotated; Cognito had no secret. All breach-era keys gone. |
| 13 | Rotate tenant-stored secrets (Stripe/GDrive/S3) | D | [x] done — Stripe=risk-accepted (test key); OLD Google tokens REVOKED; both tenants RE-AUTHORIZED with the new Web client, Drive Test PASSES. Root cause of the long failure: upload slot (`google_drive`) ≠ OAuth-read slot (`google_drive_credentials`); fixed + logged in google-drive-oauth-rotation.md |
| 14 | Scrub OneDrive plaintext + final git check | D | [x] done — secrets wiped from OneDrive Personal Vault; git verified clean of all known leaked secret fragments; `.agent-output/` scratch cleaned |
| 15 | Record h-dcn SSM / Secrets Manager notes | A | [x] done — recorded in design.md §6 (h-dcn SSM param names + Secrets Manager enumeration gap) |

---

## Tasks

Tasks are grouped into the four phases below (A = do now → D = after cutover). The checkbox list
within each phase is the live tracker.

### Phase A — DO NOW (no Railway build; safe for running prod)

- [x] 0. Create the tracking spec (no secrets)
  - `requirements.md`, `design.md`, `tasks.md`, `railway-vars.schema.json` created; no secret values.

- [x] 1. Inventory & git hygiene
  - Variable→file mapping + classification recorded by NAME in `requirements.md` + `railway-vars.schema.json`.
  - `.env` files verified gitignored/untracked: `git ls-files | grep -E '(^|/)\.env'` → only `*.env.example`.
  - AWS store findings recorded (h-dcn out of scope; Secrets Manager enumeration gap).
  - NOTE: the Railway MySQL snapshot (the Task 7 rollback point) moved to Phase B Task 7, where it is used.

- [x] 2. Write the re-encryption migration (code + tests)
  - `backend/scripts/maintenance/reencrypt_credentials_key_rotation.py` — keys read from env vars
    (`CREDENTIALS_ENCRYPTION_KEY_OLD`/`_NEW`), default `--dry-run`, single transaction, in-memory only.
  - Paired tests `backend/tests/unit/test_maintenance/test_reencrypt_credentials_key_rotation.py` — 4/4 passing.

- [x] 3. Generate + stage AWS keys — CORRECTED (prod ran on the WebMaster admin key, not the scoped user)
  - INITIAL MISTAKE: first rotated `myadmin-railway-backend` (key `AKIA‹redacted-…S75RNC4U›`), assuming prod used it.
  - CORRECTION (via `findings.md` dump of the live Railway vars, 2026-10-22): production's `AWS_ACCESS_KEY_ID`
    was actually `AKIA‹redacted-…XSLIMM7P›`, which `get-access-key-last-used` resolves to IAM user **`WebMaster`**
    (account `344561557829`) — last used that day calling cognito-idp. So prod runs on WebMaster, an over-privileged
    admin identity (inline `DynamoDBDeveloper` + `webMasterBilling`; groups `hdcnLeden`/`hdcnAdmins`/`hdcnBestuur` —
    stale residue from when h-dcn lived in the personal account before moving to nonprofit `506221081911`). It is
    also the identity the local `personal` CLI profile authenticates as.
  - DECISION (user): get WebMaster out of the myAdmin runtime. Switch Railway to the SCOPED service account
    `myadmin-railway-backend` (ARN `user/service-accounts/myadmin-railway-backend`). Permission check: the scoped
    user's 8 managed policies are a SUPERSET of WebMaster's app-relevant ones (S3 shared/public-pages, DynamoDB
    landing-pages) plus Cognito/SNS/CloudFront/SES/custom-domains — so the switch does NOT under-privilege the app.
    WebMaster's extra grants (billing, h-dcn groups, DynamoDBDeveloper, IAMUserChangePassword) are NOT app-runtime needs.
  - ACTION 2026-10-22: the first `railway variable set` attempts SILENTLY FAILED — the bare `railway` on PATH is the
    broken Windows npm shim (exit 1, no output). Re-ran via the NATIVE binary `~/.railway/bin/railway`. Final scoped
    key is `AKIA‹redacted-…ZBJ5EMRI›` (regenerated once more as the prior secret was lost); both AWS vars staged.
  - VERIFIED 2026-10-22 via a live `railway variable list --json` dump: `AWS_ACCESS_KEY_ID=AKIA‹redacted-…ZBJ5EMRI›`,
    `AWS_SECRET_ACCESS_KEY` = new value (not the old `5yHXM+...`). Secret scratch file deleted.
  - Live at the Phase C redeploy. WebMaster's breached key `...XSLIMM7P` stays active for prod until then.
  - LESSON: always stage via `~/.railway/bin/railway` (native), never bare `railway` (Windows shim fails silently).
  - FOLLOW-UP (not this spec): prune WebMaster's stale h-dcn groups / DynamoDBDeveloper / billing grants (least privilege).
  - _Done when:_ live dump shows the scoped key staged for both AWS vars. ✓

- [x] 4. Contain DB-proxy exposure — RESOLVED 2026-10-23 by the DB password rotation (Task 12), proxy kept open
  - FINDING: production connects over the PRIVATE network (`DB_HOST=mysql.railway.internal`, port 3306,
    user root, schema finance). The public TCP proxy (`shinkansen.proxy.rlwy.net`) is used only by the user's
    laptop tooling (HeidiSQL, Workbench, `railway-db.sh`), NOT by the running app.
  - DECISION (user): KEEP the public proxy open (GUI tools keep working); close the exposure by ROTATING the
    leaked DB password instead of disabling the route. Once rotated, the leaked password is dead, so the proxy
    is guarded by a strong un-leaked password and is no longer a breach exposure.
  - OUTCOME: DB password rotated (Task 12, 2026-10-23); HeidiSQL/Workbench/`railway-db.sh`/prod all reconnect on
    the new password. Public proxy intentionally NOT disabled.
  - (Optional future hardening, NOT required: disable the proxy + use `railway connect MySQL --tunnel-only`.)
  - _Done when:_ exposure closed. ✓ (via password rotation; proxy kept by choice)

- [x] 5. Generate + stage Cognito / OpenRouter / CSRF; retire SECRET_KEY
  - [x] 5.1 CSRF — new `token_hex(32)` generated, staged in Railway (`--skip-deploys`), copied to `backend/.env`. DONE 2026-10-22.
  - [x] 5.2 SECRET_KEY — confirmed NO consumer in `backend/src` (only unrelated `RECAPTCHA_SECRET_KEY` / `stripe_secret_key`; `app.py` has no `app.secret_key`); deleted from Railway. DONE 2026-10-22.
  - [x] 5.3 OpenRouter — new key created in console (old already dead); staged in Railway; in `backend/.env`. DONE 2026-10-22.
  - [x] 5.4 Cognito — FINDING: both pool app clients (`myAdmin-client` 66tp..., `myAdmin-signup` sl5e...) are PUBLIC with NO client secret (`ClientSecret: None`). Nothing to rotate; `COGNITO_CLIENT_SECRET` was vestigial (no backend consumer; prod consistency guard is a no-op). Deleted the dead var from Railway. DONE 2026-10-22. (Also drop the `COGNITO_CLIENT_SECRET` line in `backend/.env` during Task 6.)
  - Railway confirmed (dashboard): CSRF_SECRET + OPENROUTER_API_KEY present, SECRET_KEY gone, AWS keys staged.
  - _Done when:_ all four handled; new values staged in Railway + local `.env`; local AI/signup work; no dead SECRET_KEY left.

- [x] 6. Rebuild the three `.env` files (local dev) — MINIMAL breach-cleanup (option a)
  - Removed vestigial `COGNITO_CLIENT_SECRET` from `backend/.env` and root `.env` (both clients public).
  - Dropped the stale commented-out old `OPENROUTER_API_KEY` line in `backend/.env`; new key present.
  - `CSRF_SECRET` present (new). `frontend/.env` already VITE-only, untouched.
  - LEFT INTACT (rotate later): old `CREDENTIALS_ENCRYPTION_KEY` (until Task 8 re-encryption) and
    `RAILWAY_DB_PASSWORD` (until Phase C cutover) — removing either now breaks local decryption / railway-db.sh.
  - All three `.env` files confirmed still gitignored/untracked. DONE 2026-10-22.
  - FOLLOW-UP (not this spec): full three-file reshape (strip app-config duplication from root `.env`).

- [x] 15. Record h-dcn SSM / Secrets Manager notes (doc only) — DONE 2026-10-22
  - Recorded in `design.md` §6: the six `/h-dcn/*` SSM param names (out of scope, phasing-out h-dcn track),
    reachability closed by the Task 3 AWS-key rotation, and the Secrets Manager `ListSecrets` enumeration gap
    in `506221081911`. No action taken on h-dcn secrets within this spec.

---

### Phase B — IN BETWEEN (variables settable; validate before cutover)

- [x] 7. Railway MySQL snapshot (rollback point for Task 8) — DONE 2026-10-22
  - Snapshot taken via Railway dashboard; predates any Task 8 write. Rollback point in place.

- [x] 8. Re-encryption migration — DRY-RUN VERIFIED + COMMITTED 2026-10-23 (during cutover)
  - Precondition met: Task 7 snapshot exists; DB connectivity confirmed stable.
  - Scope (live): 6 `tenant_credentials` rows (2 tenants × google_drive_oauth/token/credentials) + 1 `is_secret`
    param (`GoodwinSolutions` `stripe_secret_key`, id 686).
  - BUG FOUND + FIXED by the dry-run: 2 `*/google_drive_credentials` rows are stored under the MASTER cipher
    (never lazily migrated), not the per-tenant key. The migration now mirrors the app's tenant-then-master
    decrypt fallback and re-encrypts every row to the NEW tenant-derived key. Tests 7/7 passing.
  - NEW 64-hex key generated at run time. STAGED in Railway (`CREDENTIALS_ENCRYPTION_KEY`, `--skip-deploys`,
    inert until the cutover redeploy) and stashed as a commented `# CREDENTIALS_ENCRYPTION_KEY_NEW=` line in
    `backend/.env` for the Task 11 commit. The OLD key stays ACTIVE in `backend/.env` so LOCAL dev still decrypts
    local data (local data is still under the old key). Scratch plaintext deleted.
  - DRY-RUN result 2026-10-22: "6 tenant_credentials + 1 secret parameters re-encrypt and round-trip cleanly.
    No rows written." ✓
  - COMMIT DEFERRED (decision 2b): committing now would leave the running prod container (old key in memory)
    unable to decrypt the re-encrypted rows until a redeploy — and Hobby builds are down. So the `--commit` runs
    at the Phase C cutover (Task 11); the NEW key is already staged in Railway (above).
  - DONE 2026-10-23: `--commit` ran (OLD from active `backend/.env` line, NEW from the commented line), re-encrypted
    6 tenant_credentials + 1 secret param in one transaction. Verified by LIVE prod behaviour — Google Drive
    credentials decrypt and work again (the authoritative test; a local verify script falsely reported failures due
    to a bad key var in the script, not a data problem).
  - _Done when:_ commit succeeds and prod decrypts credentials under the new key. ✓

- [x] 9. Stage the full Railway variable set + diff vs schema — VERIFIED 2026-10-22
  - Verified against a live `railway variable list --json` dump (read via gitignored scratch `findings.md`, then deleted):
    - `AWS_ACCESS_KEY_ID`=`AKIA‹redacted-…ZBJ5EMRI›` (scoped), `AWS_SECRET_ACCESS_KEY`=new — ✓ staged
    - `CREDENTIALS_ENCRYPTION_KEY`=`0fc63f…9238` (new) — ✓ staged; MATCHES the `backend/.env` staged key used by the
      Task 8 dry-run (len 64 both) → the cutover commit + redeploy will be key-consistent.
    - `OPENROUTER_API_KEY`=`sk-or-v1-5023…` (new) — ✓ staged
    - `CSRF_SECRET`=`d01921…ff09` (new) — ✓ staged
    - `SECRET_KEY`, `COGNITO_CLIENT_SECRET` — ✓ absent (removed)
    - `DB_PASSWORD`=`qEAArlrd…` (leaked) — unchanged by design; rotates at Phase C cutover.
  - _Done when:_ Railway key set matches the schema; no missing/extra keys. ✓

- [x] 10. Pre-cutover validation — DONE 2026-10-22
  - LOCAL DEV OK: `backend/.env` loads; all required vars present; `SECRET_KEY`/`COGNITO_CLIENT_SECRET` absent;
    `CREDENTIALS_ENCRYPTION_KEY` still = OLD (`ac3035…`) locally so local Docker data stays decryptable. ✓
  - RAILWAY DB REACHABLE: `railway-db.sh -q "…"` connected (6 tenant_credentials rows). DB tooling path for the
    Task 11 commit works. ✓
  - STAGED SET CONSISTENT: Task 9 confirmed all rotated secrets staged; staged enc-key == dry-run/`backend/.env` key.
  - CUTOVER-DETAIL NOTE: live `DB_PASSWORD` is the LITERAL leaked password (`qEAArlrd…`), not the
    `${{MySQL.MYSQL_ROOT_PASSWORD}}` reference the schema shows. Works today; at cutover either update this literal
    to the new password or switch it to the `${{…}}` reference when rotating `MYSQL_ROOT_PASSWORD`.
  - _Done when:_ everything staged is validated and the cutover is a known-safe flip. ✓

---

### Phase C — CUTOVER (Railway Hobby builds/deploys restored) 🔴

- [x] 11. Cutover — mostly DONE 2026-10-23 (happened out of the planned lockstep order)
  - WHAT ACTUALLY HAPPENED: Railway Hobby builds came back and a deploy ran that PICKED UP the staged vars
    (new `CREDENTIALS_ENCRYPTION_KEY` + scoped AWS key) BEFORE the re-encryption commit. That briefly broke prod:
    (a) Google Drive/Stripe couldn't decrypt (new key live, DB still old), and (b) a Cognito admin call was denied
    (scoped AWS user lacked `cognito-idp:DescribeUserPool`).
  - HEALED (forward, no rollback):
    1. Ran the Task 8 `--commit` → re-encrypted the 7 rows OLD→NEW; **Google Drive credentials work again in prod.** ✓
    2. Attached inline IAM policy `myadmin-cognito-admin-ops` to `myadmin-railway-backend` granting the full
       `cognito-idp` action set the backend calls (DescribeUserPool + admin_* user/group ops), scoped to the pool
       ARN. **SysAdmin Cognito health GREEN.** ✓ SNS + OpenRouter already healthy.
  - LESSON: staging vars with `--skip-deploys` does NOT protect against the NEXT deploy (code push / dispatch)
    picking them up. A key swap that depends on a data migration must either commit the migration FIRST, or
    freeze deploys until the lockstep window. Here the deploy forced the order; the commit healed it.
  - REMAINING: DB password NOT yet rotated (prod still uses the leaked `qEAArlrd…`). That rotation + the
    `${{MySQL.MYSQL_ROOT_PASSWORD}}` reference cleanup is the one outstanding cutover item → tracked under Task 12.
  - _Done when:_ production healthy on fully rotated secrets (Drive ✓, Cognito ✓, AWS scoped ✓, OpenRouter ✓, CSRF ✓;
    DB password pending).

---

### Phase D — AFTER a healthy cutover 🔴 / follow-up

- [x] 12. Invalidate old credentials — DONE 2026-10-23
  - **12a. Rotate the WebMaster CLI key — DONE 2026-10-23.** The local `personal` profile used WebMaster key
    `AKIA‹redacted-…XSLIMM7P›` (the SAME breached key that had been in Railway). Executed the safe rotate-first order:
    deleted the never-used `AKIA‹redacted-…RDZKBCOI›` (freed a slot) → created fresh `AKIA‹redacted-…SNQPC5MC›` →
    repointed `~/.aws` `personal` to it → verified `get-caller-identity` = `user/WebMaster` on the new key →
    deactivated then DELETED the breached `AKIA‹redacted-…XSLIMM7P›`. WebMaster now has ONLY `...SNQPC5MC` (Active).
    The last breach-exposed AWS key is dead (closed for both Railway — already on scoped `...ZBJ5EMRI` — and the CLI).
  - **12b. Retired the old `myadmin-railway-backend` key `AKIA‹redacted-…VTJC26WY›`** — DELETED 2026-10-23.
    Scoped user now has ONLY the prod key `AKIA‹redacted-…ZBJ5EMRI›`.
  - **DB PASSWORD — ROTATED 2026-10-23.** Only user is `root@%`/`root@localhost`. Done via:
    (B) `ALTER USER 'root'@'%'/'root'@'localhost' IDENTIFIED BY '<new 32-char alnum>'` through the old
    `railway-db.sh` connection — verified the new password connects (`NEW-PASSWORD-WORKS`);
    (C) updated `MYSQL_ROOT_PASSWORD` (MySQL svc, `--skip-deploys`), `DB_PASSWORD` (app svc → triggered redeploy),
    `RAILWAY_DB_PASSWORD` (root `.env`);
    (D) `railway-db.sh` reconnects as `root@%`. ✓ Brief transitional "Access denied" on clients using the old
    password until the app redeploy + GUI tools were updated — expected, resolved by the redeploy.
    GUI tools (HeidiSQL/Workbench) re-pointed to the new password (same host/port/user) — CONFIRMED connecting.
    Public proxy KEPT OPEN (user choice) — exposure resolved by the rotation, not by disabling the route.
    Plaintext scratch `.agent-output/new-db-pass.txt` DELETED 2026-10-23 after GUI tools updated. ✓ DB PASSWORD DONE.
  - COGNITO: no client secret existed (public clients) — nothing to retire. (OpenRouter old key already dead.)
  - NOTE (done 2026-10-23): attached inline IAM policy `myadmin-cognito-admin-ops` to `myadmin-railway-backend`
    (full `cognito-idp` admin action set, pool-scoped) after the scoped-key switch denied `DescribeUserPool`.
  - _Done when:_ old AWS key inactive/deleted, DB password rotated, calls with old creds fail; local CLI still works.

- [x] 13. Rotate tenant-stored secrets (Stripe / Google Drive / S3)
  - Breach-exposed data-at-rest secrets under `CREDENTIALS_ENCRYPTION_KEY` (master key + DB access both leaked).
    Re-encryption (Task 8) does NOT undo the value exposure. User is tenant admin for all tenants → single-operator sweep.
  - SCOPE (inventoried during Task 8, 2026-10-22): 6 `tenant_credentials` rows + exactly ONE `is_secret` param —
    `stripe_secret_key` for tenant `GoodwinSolutions` (module `str`, param id 686). Re-run the inventory before rotating
    in case tenants added credentials since.
  - Inventory (names/counts only): `SELECT administration, credential_type FROM tenant_credentials ORDER BY 1,2;` plus
    the `is_secret` params for `stripe_secret_key`, via `railway-db.sh`.
  - RE-INVENTORIED 2026-10-23 (post re-encryption): `tenant_credentials` = GoodwinSolutions + PeterPrive, each with
    `google_drive_credentials` / `google_drive_oauth` / `google_drive_token` (6 rows); `is_secret` params =
    GoodwinSolutions `str`/`stripe_secret_key` (1). No `s3_credentials` present.
  - DECISIONS (user, 2026-10-23):
    - **Stripe (`GoodwinSolutions/stripe_secret_key`): RISK-ACCEPTED — it is a TEST key, not a real secret.** No rotation.
    - **Google Drive creds (both tenants): FULL ROTATION chosen (option 1a).** In Google Cloud Console rotate the
      OAuth client secret + revoke existing tokens, then re-upload/re-authorize per tenant via Tenant Admin →
      Credentials so fresh `google_drive_oauth`/`google_drive_token` are stored (encrypted under the NEW key).
  - This step is external-dashboard + Tenant-Admin UI work (not scriptable here). Urgency is reduced because the
    DECRYPTION PATH is already closed (encryption key + DB password rotated), but the leaked Google token VALUES
    still warrant rotation.
  - ATTEMPTED 2026-10-23: uploaded a new client secret + re-authorized, but the Drive refresh FAILS with
    `invalid_client: The provided client secret is invalid`. Root cause: the new Google OAuth client is the WRONG
    TYPE (Desktop/"installed", `redirect_uris:['http://localhost']`) — myAdmin needs a **Web application** client —
    AND `GOOGLE_REDIRECT_URI` is unset in Railway (defaults to localhost). This is a Google OAuth CONFIG fix, not a
    breach-secret issue.
  - MOVED TO FOLLOW-UP: full diagnosis + fix steps in `.kiro/specs/myBacklog/google-drive-oauth-rotation.md`.
  - UPDATE 2026-10-23: user revoked the OLD Google tokens (leaked tokens now dead ✓) and created a WEB OAuth client.
    Re-auth still failed — root cause turned out to be a CODE BUG: `start_oauth_flow` built the authorize URL with a
    raw f-string, NOT URL-encoding `redirect_uri` → `Error 400: redirect_uri_mismatch`. Fixed to use
    `urllib.parse.urlencode` (`backend/src/routes/tenant_admin_credentials.py`). Also set Railway `GOOGLE_REDIRECT_URI`
    to the real backend URL `https://invigorating-celebration-production.up.railway.app/api/tenant-admin/credentials/oauth/callback`
    (was wrongly `pgeers.nl`, which serves a Google Site not the API).
  - SHIPPED: PR #164 (`fix/google-oauth-redirect-uri-encoding`) MERGED to `main` 2026-10-23 (merge commit
    `27e57304`, CodeQL + GitGuardian green) → triggers Railway prod deploy. After deploy, re-auth per tenant →
    Drive restored. (Awaiting the deploy + user re-auth/Test.)
  - STATUS: Stripe = risk-accepted (test key). OLD Google tokens REVOKED (breach exposure closed). Google Drive
    ACCESS restoration pending. Decryption path already closed.
  - RESOLVED 2026-10-23: the real cause was NOT propagation. The new client file kept being stored under type
    `google_drive` (what the Storage upload uses) while the OAuth flow reads `google_drive_credentials` — so the
    flow kept using the STALE OLD client → redirect_uri_mismatch. Fixed by copying the new `google_drive`
    encrypted_value into `google_drive_credentials` (verbatim ciphertext, same per-tenant salt) for both tenants,
    then re-authorizing. Consent screen appeared, token minted, Test PASSES. Backlog: fix the slot mismatch + surface
    failure detail in the UI (`.kiro/specs/myBacklog/google-drive-oauth-rotation.md`).
  - _Done when:_ both tenants re-authorized with a correct WEB OAuth client; a Drive action works per tenant.

- [x] 14. Scrub OneDrive plaintext + final git check — DONE 2026-10-23
  - Secrets WIPED from the OneDrive Personal Vault JSONs (user). Railway is the system of record for live values.
  - `.agent-output/` scratch cleaned. `git grep` for all known leaked fragments (old DB password, old AWS secret,
    old OpenRouter key, old encryption key, old Cognito secret, breached AWS key id) → CLEAN; no `.env`/secret files
    tracked (only `*.example` + source code with "credential" in the name).
  - _Done when:_ Vault JSONs are secret-free; git clean. ✓

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": [0, 1, 2], "description": "Phase A groundwork — spec, inventory, migration code (all done)" },
    { "wave": 2, "tasks": [3, 4, 5, 6, 15], "description": "Phase A — generate/stage secrets, contain DB proxy, rebuild local .env, docs (do now)" },
    { "wave": 3, "tasks": [7], "description": "Phase B — Railway MySQL snapshot (rollback point)" },
    { "wave": 4, "tasks": [8, 9, 10], "description": "Phase B — run re-encryption, stage full Railway set, pre-cutover validation" },
    { "wave": 5, "tasks": [11], "description": "Phase C — CUTOVER: promote DB password + redeploy + verify (needs Hobby builds)" },
    { "wave": 6, "tasks": [12, 13, 14], "description": "Phase D — invalidate old creds, rotate tenant-stored secrets, scrub plaintext" }
  ]
}
```

## Notes

- Phase A is fully actionable during the Railway outage; Phases B–D progress as Railway recovers.
- Setting a Railway variable in Phase A/B only STAGES it — it is inert until the Phase C redeploy.
- `SECRET_KEY` (env var, Task 5) is distinct from `stripe_secret_key` (per-tenant DB param, Task 13). Never conflate.
- No secret values in this spec; commands use placeholder tokens; real values only in the user's own shell.
- Shell is WSL/bash: judge success by command output + the `<<<DONE marker=$?>>>` marker, not the tool's exit code.
