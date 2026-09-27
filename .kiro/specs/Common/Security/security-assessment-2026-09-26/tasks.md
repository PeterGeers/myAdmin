# Security Assessment 2026-09-26 — Mitigation Tasks

Prioritized by risk score (🔴 ≥ 15 first, then 🟠 8–14, then 🟢 ≤ 7). Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h. Every task is a DEFENSIVE hardening of myAdmin's own code/config.

> No Critical (🔴) items — the `security-hardening-2026-06-28` spec closed those. Start with the High/Medium below.
> Security-sensitive note: several tasks touch auth/IAM/tenancy. Each states what can and cannot be verified locally; changes here need review + a real deploy check, not just a green unit test.

---

## High

- [x] **H1. Fail closed on JWT verification in production (risk F1).** [M]
  - **File(s)**: `backend/src/auth/cognito_utils.py` (`_get_jwt_verifier` ~L36-127, `extract_user_credentials` ~L440-460, `_extract_with_base64` ~L530-600).
  - **Risk**: when neither `COGNITO_POOL_KEYS` nor the legacy trio (`COGNITO_USER_POOL_ID`/`COGNITO_REGION`/`COGNITO_APP_CLIENT_ID`) is configured, auth silently downgrades to trusting an **unsigned** base64 token payload (attacker can forge `cognito:groups`). Safe in dev; catastrophic if prod ever runs unconfigured.
  - **Action**: make the base64 fallback **impossible in production**: if `RAILWAY_ENVIRONMENT == "production"` (or an explicit `REQUIRE_JWT_VERIFICATION=true`) and `_get_jwt_verifier()` returns `None`, raise/return a hard 500 at startup or reject every request with 503 — never fall through to `_extract_with_base64`. Keep the fallback only for local dev / tests (verifier genuinely unconfigured AND not production). Log loudly at startup which mode is active.
  - **Verification**: unit test — with `RAILWAY_ENVIRONMENT=production` and no Cognito env vars, `extract_user_credentials` must NOT accept an unsigned token (expect 401/503, never a decoded identity); with a configured verifier, a validly-signed token still passes. `pytest backend/tests/ -k "jwt or verifier or cognito" -q`.

---

## Medium

- [x] **M1. Inventory + audit-log the `allow_sysadmin=True` routes (risk F2).** [M]
  - **File(s)**: `backend/src/auth/tenant_context.py` (`tenant_required` bypass ~L250-256); all routes decorated `@tenant_required(allow_sysadmin=True)` (grep `allow_sysadmin=True backend/src/routes`).
  - **Risk**: a SysAdmin's `X-Tenant` header is injected **unvalidated** on these routes — a client header grants cross-tenant reach for SysAdmin callers.
  - **Action**: (1) produce the definitive inventory of `allow_sysadmin=True` routes and confirm each genuinely needs system-wide scope. (2) In the bypass branch, emit a structured audit log of `{user_email, injected_tenant, route}` (today it's a `print`). (3) Where a route does NOT need arbitrary-tenant, drop `allow_sysadmin` so the normal membership check applies. (4) Consider validating that the injected tenant at least exists, even for SysAdmin.
  - **Verification**: a test asserting the bypass path logs the injected tenant; `grep -rn "allow_sysadmin=True" backend/src/routes` matches the documented inventory. `pytest backend/tests/ -k "tenant or sysadmin" -q`.

- [x] **M2. Deploy the `dynamodb:LeadingKeys` defense-in-depth for the SAM plane (risk S1).** [L]
  - **File(s)**: `sam/members/repository/table_design.py` (`LEADING_KEYS_IAM_POLICY_PLAN`, `leading_keys_iam_policy_json()`), `sam/members/template.yaml` (`MembersFunction.Policies`), and the deploy/tagging story for a per-tenant `PrincipalTag`.
  - **Risk**: tenant isolation currently rests entirely on the repository always pinning the `tenant_id` partition key. There is **no IAM backstop** — the `LeadingKeys` condition exists only as a code-level plan, and the Lambda runs as a single shared principal (no per-tenant `PrincipalTag`), so even adding the condition as-is would not constrain it.
  - **Action**: decide and implement the intended model: either (a) add the `dynamodb:LeadingKeys` condition scoped to a request/session `tenant_id` tag (requires per-request scoped credentials / session tagging — a larger design), or (b) if a single shared principal is accepted, document explicitly that isolation is structural-only and compensate with a strong invariant test that fails if any repository query omits the `tenant_id` key condition. Do NOT claim LeadingKeys enforcement in docs while it is undeployed.
  - **Verification**: if (a) — a deploy check that a cross-tenant `tenant_id` access is IAM-denied; if (b) — a repository test asserting every read/write includes the `tenant_id` PK condition. Confirm `template.yaml` and `table_design.py` docs agree with what is actually deployed.

---

## Low

- [x] **L1. UUID-prefix STR upload filenames (risk F4).** [S]
  - **File(s)**: `backend/src/routes/str_routes.py` (upload paths ~L93-96, ~L638-641).
  - **Action**: mirror `invoice_routes.py`'s `f"{tenant}_{uuid4()}_{secure_filename(name)}"` so concurrent same-name uploads cannot overwrite each other. Traversal is already handled by `secure_filename` + middleware; this is an overwrite/availability fix.
  - **Verification**: two uploads of the same filename produce two distinct stored paths. `pytest backend/tests/ -k "str_upload or str_routes" -q`.

- [x] **L2. Verify + document the SAM OIDC deploy-role trust policy (risk S2).** [S]
  - **File(s)**: the `NonprofitDeployRole` trust policy (account 506221081911 — managed outside the repo), referenced by `.github/workflows/deploy-sam-*.yml`.
  - **Action**: confirm the role's trust condition is pinned to `repo:PeterGeers/myAdmin:ref:refs/heads/main` (not a broad `repo:PeterGeers/myAdmin:*` that a fork/branch/PR could assume), and record the verified trust JSON in `.kiro/specs/Common/Security/` (or a `docs/decisions` note) so it is auditable. Confirm `permissions: id-token: write` scope is minimal.
  - **Verification**: `aws iam get-role --role-name NonprofitDeployRole` trust document shows the pinned `sub`/`ref` condition (run with the profile that can read it); documented in-repo.

- [x] **L3. Guard the SAM handler→repository boundary (risk S3).** [S] (prevents regression of AP-S2)
  - **File(s)**: `sam/members/handler/`, `sam/*/handler*` (any future module); a test or grep-based CI check.
  - **Action**: add a guard test asserting no `sam/**/handler*`/`router*` module imports `boto3` or calls DynamoDB directly (the repository must remain the sole touch-point). Fits the report-only SAM lint added to the Full Test Suite; can graduate to blocking.
  - **Verification**: the guard fails if a handler gains a direct `boto3`/`.Table(`/`.query(` reference; passes today.

- [x] **L4. Tidy the Lambda-path `cors_headers()` origin (risk F3).** [S]
  - **File(s)**: `backend/src/auth/cognito_utils.py` (`cors_headers` ~L284-293).
  - **Action**: it returns `Access-Control-Allow-Origin: *` with `Access-Control-Allow-Credentials: false` — not exploitable (no creds), and it's the response-dict/Lambda-style path, not the Flask-CORS layer. Optionally align it to the same env allowlist for consistency, or add a comment that this path is non-credentialed by design. Lowest priority.
  - **Verification**: responses from this path still carry `ACAC:false`; Flask routes continue to use the env allowlist. `pytest backend/tests/ -k "cors" -q`.

---

## Verification summary (after mitigations)

- Flask auth/tenancy tests: `cd backend && source .venv/bin/activate && pytest tests/ -k "jwt or verifier or cognito or tenant or cors" -q`
- SAM edge/repository tests: `pytest sam/tests -q`
- For IAM/deploy tasks (M2, L2): confirm on a real (non-prod first) deploy — unit tests cannot verify an IAM condition or an OIDC trust policy.
- Do NOT mark H1/M1/M2 done on a green unit test alone; each needs a config/deploy-level confirmation as noted.
