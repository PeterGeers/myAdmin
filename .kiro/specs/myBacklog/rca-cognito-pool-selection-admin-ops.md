# RCA — Cognito admin operations target the wrong pool (single-pool var vs. registry)

Status: findings + recommendations (no code changes yet)
Author: RCA session 2026-09-28
Related solved bug: `.kiro/specs/BUGS solved/20260407 Onboarding/rca.md`
Governing contract: `backend/src/auth/pool_registry.py` ("config-not-code, select pool by `iss`")

---

## 1. Presenting symptom

On `localhost:3000`, login as `peter@pgeers.nl` fails with "Incorrect email or
password", even though a password reset from the same UI reported success. Repeated
attempts and a fresh reset did not help. The user reports this class of problem has
recurred several times.

## 2. What was verified (evidence, not inference)

| # | Fact | How verified |
|---|------|--------------|
| 1 | Frontend on localhost signs in against the **test pool** `eu-west-1_xyrlzfqbl`. | read `frontend/src/aws-exports.ts` (hostname-based pool selection prefers `VITE_TEST_COGNITO_*`) |
| 2 | `peter@pgeers.nl` did NOT exist in the test pool (only 8 synthetic `@example.com` / `webmaster@h-dcn.nl` users). | `aws cognito-idp list-users` on `eu-west-1_xyrlzfqbl` |
| 3 | `peter@pgeers.nl` DOES exist in the prod pool `eu-west-1_Hdp40eWmu` (CONFIRMED, enabled). | `aws cognito-idp admin-get-user` on `eu-west-1_Hdp40eWmu` |
| 4 | Backend TOKEN VALIDATION in the dev container uses `COGNITO_POOL_KEYS=TEST`. | read `docker-compose.yml` (explicit `environment:` override, takes precedence over `backend/.env`) |
| 5 | Backend PASSWORD RESET writes/reads via `USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")` = **prod** `eu-west-1_Hdp40eWmu`. | read `backend/src/routes/auth_routes.py` |
| 6 | The test-pool app client `43s15cm8qcgg8an85udt0e087u` allows `USER_SRP_AUTH`, no client secret. | `aws cognito-idp describe-user-pool-client` |

## 3. Root cause

There are **two independent Cognito code paths in the backend that resolve the pool
differently**:

- **Token validation** goes through the multi-pool issuer->pool registry
  (`auth/pool_registry.py` + `auth/cognito_utils.py`), selected by the token's `iss`.
  In dev/test this is the **test** pool (`COGNITO_POOL_KEYS=TEST`); in prod it is
  Pool A (`COGNITO_POOL_KEYS=PROD_A`). This path is correct and environment-aware.

- **Admin operations** (password reset, create/enable/disable/delete user, group
  membership, attribute updates, language) read the **legacy single-pool var**
  `COGNITO_USER_POOL_ID` directly. In every environment that var is currently the
  **prod** pool, so these operations always hit prod regardless of environment.

Therefore, in the dev container: a user logs in against the **test** pool, but a
password reset (and every other admin op) silently acts on the **prod** pool. The
reset "succeeded" because `peter@pgeers.nl` exists in prod — it updated the prod
account. Login then failed because the test-pool account has no matching password
(only the temporary one created during this session).

This is a **contract violation**: multiple specs (s5c, s5d) state the pool registry
is the single source of truth and pool selection is "config-not-code, by `iss`". The
admin paths predate the registry (created by the "Consistent email system" fix in the
20260407 Onboarding RCA, which introduced `auth_routes.py` with the hardcoded
`USER_POOL_ID`) and were never migrated onto it.

## 4. Blast radius — every backend site on the legacy single-pool var

All of the following resolve the pool via `os.getenv("COGNITO_USER_POOL_ID")` and thus
target prod in all environments:

- `backend/src/routes/auth_routes.py` — password reset: `admin_get_user`, `admin_set_user_password`
- `backend/src/tenant_admin_routes.py` — `admin_list_groups_for_user`
- `backend/src/services/cognito_service.py` — create/get/update/delete user, add/remove group, create/delete group, list users in group, add/remove tenant (`admin_update_user_attributes`)
- `backend/src/admin_routes.py` — list/create/enable/disable/delete user, groups, attribute updates
- `backend/src/services/user_language_service.py` — get/set `custom:preferred_language`
- `backend/src/services/signup_service.py` — self-service signup (needs full read to confirm exact calls)

(Non-exhaustive until a full `grep` sweep is re-run at fix time; the search was
truncated. The pattern is systemic, not isolated to reset.)

## 5. Why it keeps recurring

- The correct pattern (registry) and the legacy pattern (`COGNITO_USER_POOL_ID`)
  coexist. New admin code copies the nearest existing example, which is the legacy one.
- The dev container makes validation env-aware but leaves `COGNITO_USER_POOL_ID`
  pointing at prod, so the split is invisible until an admin op is exercised in dev.
- Each incident is patched at the symptom (reset a password, add a user to a pool)
  rather than at the shared root (pool resolution), so it returns.

## 6. Contributing / adjacent factors (not the root cause)

- **Frontend pool selection by `window.location` hostname** (`aws-exports.ts`) rather
  than an explicit environment flag. Not the cause of THIS failure, but the same
  "pool chosen implicitly" fragility on the frontend side.
- **Reset path anti-enumeration** returns success even when the user is absent from
  the target pool, which HID the mismatch (no "user not found" surfaced).
- **Future Pool B (tenant-scoped webshop users)** will make the backend genuinely
  multi-pool in prod, so any fix MUST resolve the pool *per user*, not per environment.

## 7. Recommendations

Ordered; R1 is the true fix.

- **R1 (root fix) — Route all admin Cognito operations through a single pool-resolution
  helper backed by the registry, keyed by the user (issuer/pool), not by
  `COGNITO_USER_POOL_ID`.** One code path, mirroring how validation already resolves by
  `iss`. Must support N pools (TEST, PROD_A, future PROD_B). For admin ops that start
  from an email (not a token), define a deterministic "which pool is this user in"
  resolution (e.g. look up across registered pools, or a stored user->pool mapping).
- **R2 — Consolidate the duplicated admin-Cognito logic** in `cognito_service.py`,
  `admin_routes.py`, `tenant_admin_routes.py`, `auth_routes.py`,
  `user_language_service.py`, `signup_service.py` onto that one helper. Remove direct
  `os.getenv("COGNITO_USER_POOL_ID")` reads from these paths.
- **R3 — Frontend: replace hostname-based pool selection with an explicit
  `VITE_APP_ENV`** (development/test/production) that chooses the pool block, so
  frontend and backend cannot silently diverge.
- **R4 — Decide the Pool B model now** (email uniqueness across pools? same or
  different reset UX for webshop vs. staff users?) and encode it in the resolution
  rule so R1 is forward-compatible.
- **R5 — Guardrail test/lint**: fail CI if a non-registry file reads
  `COGNITO_USER_POOL_ID` for an admin op (mirrors the existing SAM/JWT lint in
  `.kiro/specs/code-quality-maintenance/prompt-code-quality.md`).

## 8. Immediate unblock (tactical, not the fix)

`peter@pgeers.nl` was created in the test pool this session (status
FORCE_CHANGE_PASSWORD). To log in on localhost now: set a permanent password directly
on the **test** pool (`eu-west-1_xyrlzfqbl`) via `admin-set-user-password`. This does
NOT fix the root cause; it only unblocks local login.

## 9. Proposed next step

Open a **bugfix spec** ("cognito-admin-pool-resolution") scoped to R1+R2 (root fix +
consolidation), with R3/R4/R5 referenced. Anchor requirements to the pool_registry
contract. Do NOT quick-patch individual endpoints again.
