# Security Assessment — 2026-09-26

Defensive security assessment of myAdmin across **both planes** (Flask/MySQL and SAM/DynamoDB), executed per `.kiro/specs/code-quality-maintenance/prompt-security.md`. This is a **code-grounded** review: findings are tied to actual files/lines, not the prompt's architecture summary.

> **Headline:** the prior **`security-hardening-2026-06-28`** spec (all tasks `[x]`) already remediated the nine Flask-plane vulnerabilities the security prompt was originally written against. Cryptographic JWT verification, the CORS allowlist, always-on security middleware, per-tenant encryption keys, rate limiting, and log sanitization are **implemented and confirmed in code**. So the prompt's legacy claims — "JWT not verified", "CORS wildcard", "middleware disabled in debug" — are **no longer true**. The real current risk surface is a small set of **residual trust boundaries** and **one SAM defense-in-depth gap**, documented below.

## Severity counts

| Severity | Count | Items |
| -------- | ----- | ----- |
| Critical | 0     | — |
| High     | 1     | F1 (base64 auth fallback in a misconfigured prod) |
| Medium   | 2     | F2 (SysAdmin unvalidated tenant), S1 (LeadingKeys not deployed) |
| Low      | 3     | F3 (Lambda-path CORS `*`+no-creds), F4 (upload name collision), S2 (OIDC trust unverifiable from repo) |
| Info     | 1     | Cross-account / deploy posture (verified good) |

Per plane: **Flask** — 1 High, 1 Medium, 2 Low. **SAM** — 1 Medium, 1 Low. **Cross-cutting** — 1 Info.

---

## 1. Security Architect — assessment by domain

Status legend: 🟢 good · 🟡 adequate-with-caveat · 🔴 weak.

### Flask / MySQL plane

| Domain | Status | Notes |
| ------ | :----: | ----- |
| Authentication (JWT) | 🟡 | **Cryptographically verified** — `auth/jwt_verifier.py::verify_token` does real RS256 against the pool's JWKS, checks `iss`, `aud`/`client_id`, `exp` (30s leeway), rejects non-RS256 (algorithm-confusion blocked). Caveat = **F1**: an unverified base64 fallback (`cognito_utils._extract_with_base64`) is used when no Cognito env vars are configured; safe for local dev, dangerous if prod ever runs unconfigured. |
| Authorization (RBAC) | 🟢 | `cognito_required` splits global roles (from verified `cognito:groups`) vs per-tenant roles (from DB `get_tenant_roles`), enforces role/permission. Wildcard `*` only for `Administrators`/`System_CRUD`. |
| Multi-tenant isolation | 🟡 | `X-Tenant` is a **selector validated** against the verified `custom:tenants` (`validate_tenant_access` → 403 on mismatch) — not a trust source. `add_tenant_filter` binds `administration = %s` (parameterized). Caveat = **F2**: `tenant_required(allow_sysadmin=True)` skips validation and injects an **unvalidated** tenant for SysAdmin callers. |
| API security (CORS) | 🟢 | Flask-CORS uses an **env-driven allowlist** (`ALLOWED_ORIGINS`), `supports_credentials=True`, `Vary: Origin`, localhost only off-prod. No wildcard+credentials. (**F3**: a separate Lambda-style `cors_headers()` helper hardcodes `ACAO:*` but with `ACAC:false` — not the Flask path; Low.) |
| Data security (crypto) | 🟢 | Per-tenant Fernet keys derived via PBKDF2-HMAC-SHA256 (100k iters, salt = tenant). Master key (static salt) is explicitly backward-compat only. `CREDENTIALS_ENCRYPTION_KEY` required (raises if absent). Decryption errors carry no key material. |
| Data security (SQL) | 🟢 | Parameterized `%s` throughout; the only f-string/`+` in SQL are safe placeholder-generation (`",".join(["%s"]*n)` + bound params) or hardcoded-table identifiers — no user-controlled interpolation. |
| File uploads | 🟡 | 100MB cap, extension whitelist, `secure_filename`. **F4**: `str_routes.py` doesn't always UUID-prefix, so same-name concurrent uploads can collide (availability/overwrite, not traversal). |
| Security middleware | 🟢 | Suspicious-pattern detection (SQLi/XSS/traversal/scanner UA) + security headers run on **all** requests — no `FLASK_DEBUG`/`TEST_MODE` bypass (the old bypass was removed). |
| Logging & auditing | 🟢 | `log_successful_access` audit trail; sensitive-value masking; API-key logging removed (prior spec task 10). |

### SAM / module plane

| Domain | Status | Notes |
| ------ | :----: | ----- |
| SAM edge (verified JWT) | 🟢 | `sam/shared/auth_utils.py` — RS256 + JWKS + fail-fast pool registry (`PoolRegistryError` on missing env). `get_verified_claims` prefers the API-GW Cognito authorizer, else full in-handler verification. **No base64 path** (stronger than the Flask plane). |
| SAM authorization (entitlements) | 🟢 | `has_capability` is **three-state** — `True`/`False`/`None`; `None` ("token doesn't answer") is never a silent allow. Capability sourced solely from the verified `custom:entitlements` (no `cognito:groups` fallback). |
| SAM active-tenant (ADR 0007) | 🟢 | `_establish_tenant_context` — `X-Tenant` **selects, never grants**: a tenant not in `tenant_keys` → 403; no default-to-first; no `MEMBERS_LOCAL_TENANT_ID`/hardcoded tenant. |
| PreTokenGen mint | 🟢 | Builds `custom:entitlements` from the DynamoDB governance projection; **fail-safe omit** on a runtime blip (login not broken, no silent wrong claim), **fail-fast re-raise** on `DynamoDBConfigError` (deploy misconfig surfaces loudly). Tenants only from the verified `custom:tenants` → cannot mint another tenant's entitlement. |
| SAM tenancy (DynamoDB) | 🟡 | The repository is the **sole** DynamoDB touch-point; every op is `tenant_id`-PK scoped via `_query_prefix`; **no `.scan()`**; `_require_tenant` guard. Isolation is structural. Caveat = **S1**: `dynamodb:LeadingKeys` is only a documented *plan* (`table_design.LEADING_KEYS_IAM_POLICY_PLAN`), **not** in the deployed IAM — the defense-in-depth layer the design intends is absent. |
| SAM IAM least-privilege | 🟢 | `members/template.yaml` scopes DynamoDB to the exact table ARNs (`governance_projection` read-only; `sam-members` CRUD), same account/region, **no** `Resource:'*'`, **no** `dynamodb:*`. `MembersTableName` `AllowedPattern: ^sam-members.*$`. |
| SAM deploy / cross-account | 🟡 | Deploy via OIDC + `--config-env` (no inline `--parameter-overrides`/`--stack-name`); pinned distinct stack names; identity account (`personal` 344561557829) vs infra (`nonprofit-deploy` 506221081911) cleanly split. **S2**: the `NonprofitDeployRole` trust policy JSON lives outside the repo, so its trust conditions could not be verified here. |
| SAM secrets/config | 🟢 | No secrets in `sam/`. Table names via fail-fast env vars (no defaults). `samconfig.toml` holds only **public** Cognito identifiers (annotated). |

---

## 2. Red Team — attack paths (with current-code reality)

Each path notes whether it is **open**, **blocked**, or **conditional** given the current code.

### Flask plane

- **AP-F1 — Downgrade auth to unsigned tokens (CONDITIONAL, → F1).** If the Flask app is deployed **without** `COGNITO_POOL_KEYS` or the legacy trio, `_get_jwt_verifier()` returns `None` and `_extract_with_base64` trusts an unsigned JWT payload — an attacker could forge `cognito:groups: ["Administrators"]`. **Precondition:** production running mis/unconfigured. **Impact:** full authz bypass. **Detection:** a warning log ("cryptographic verification disabled…") is emitted at startup — but nothing blocks. **Mitigation:** see task **H1** (fail-closed in prod).
- **AP-F2 — SysAdmin arbitrary-tenant via X-Tenant (CONDITIONAL, → F2).** On a route decorated `tenant_required(allow_sysadmin=True)`, a SysAdmin's `X-Tenant` is injected unvalidated — they can act on any tenant, including ones not in their token. **Precondition:** attacker holds SysAdmin. **Impact:** intended for system ops, but it is a real cross-tenant capability granted by a client header. **Mitigation:** task **M1** (inventory routes, log the injected tenant, prefer explicit allow-listing).
- **AP-F3 — Spoof X-Tenant for a non-entitled tenant (BLOCKED).** `validate_tenant_access` rejects a tenant not in the verified `custom:tenants` with 403. Blocked on all non-`allow_sysadmin` routes.
- **AP-F4 — SQLi via banking/CSV import fields (BLOCKED).** All queries parameterized; import values are bound, never interpolated.
- **AP-F5 — Upload filter bypass / overwrite (LOW, → F4).** Extension whitelist + `secure_filename` block traversal and double-extension; residual is same-name overwrite in `str_routes.py` (availability). **Mitigation:** task **L1**.
- **AP-F6 — Scanner / injection probes (BLOCKED).** Middleware flags SQLi/XSS/traversal patterns and scanner user-agents on all requests → 403.

### SAM plane

- **AP-S1 — Force tenant selection past `tenant_keys` (BLOCKED).** `_establish_tenant_context` 403s a selected tenant absent from the verified entitlement; no default-to-first.
- **AP-S2 — Bypass the repository to skip tenant scoping (BLOCKED, structural).** Handlers/routers hold no boto3; the repository is the sole DynamoDB caller and every op is `tenant_id`-PK scoped. A future handler that added a direct DynamoDB call would reintroduce risk — guard with a lint/review rule (task **L3**).
- **AP-S3 — Cross-tenant read via Scan/GSI (BLOCKED).** No `.scan()` in production; the only `.query()` pins `tenant_id`.
- **AP-S4 — Mint another tenant's entitlement via PreTokenGen (BLOCKED).** Tenants derive only from the user's verified `custom:tenants`; a runtime failure omits the claim (fail-closed), a config error fails the login loudly.
- **AP-S5 — Lateral movement if the Lambda role were over-broad (BLOCKED today; → S1 for depth).** IAM is table-scoped with no wildcards. But because `dynamodb:LeadingKeys` is **not** deployed, a *bug above the repository* that omitted the `tenant_id` key condition would not be caught by an IAM backstop — isolation rests on the code being correct. Task **M2** adds the intended defense-in-depth.
- **AP-S6 — Compromise the deploy chain (CONDITIONAL, → S2).** Deploy is OIDC + pinned config; the residual unknown is the `NonprofitDeployRole` trust policy (not in repo). If its trust condition is too broad (e.g. not pinned to `repo:PeterGeers/myAdmin:ref:refs/heads/main`), a fork/branch could assume it. **Mitigation:** task **L2** (verify + document the trust policy).

---

## 3. Risk Manager — register

Impact (I) × Likelihood (L), score = I×L. Zones: 🔴 ≥ 15 · 🟠 8–14 · 🟢 ≤ 7.

| # | Risk | Plane | Category | I | L | Score | Zone | Mitigation task |
| - | ---- | ----- | -------- | - | - | ----- | ---- | --------------- |
| F1 | Prod misconfig → unsigned-token trust (base64 fallback) | Flask | Authentication | 5 | 2 | 10 | 🟠 | H1 |
| F2 | SysAdmin injects unvalidated tenant via `allow_sysadmin` | Flask | Authorization | 3 | 3 | 9 | 🟠 | M1 |
| S1 | `LeadingKeys` defense-in-depth not deployed (isolation = code-only) | SAM | Multi-tenant | 4 | 2 | 8 | 🟠 | M2 |
| F4 | Upload same-name overwrite (`str_routes`) | Flask | Availability | 2 | 2 | 4 | 🟢 | L1 |
| S2 | OIDC deploy-role trust policy unverifiable from repo | SAM | Supply chain | 4 | 1 | 4 | 🟢 | L2 |
| F3 | Lambda-path `cors_headers()` hardcodes `ACAO:*` (creds off) | Flask | API security | 1 | 2 | 2 | 🟢 | L4 |
| S3 | Future handler could bypass the repository (no lint guard) | SAM | Multi-tenant | 4 | 1 | 4 | 🟢 | L3 |

**5×5 matrix (by score):** 🔴 none. 🟠 F1 (10), F2 (9), S1 (8). 🟢 F4 (4), S2 (4), S3 (4), F3 (2).

### KPIs for continuous security health
- % of Flask routes returning tenant data that carry `@tenant_required` (target 100%; sentinel `_tenant_required` is introspectable).
- % of `allow_sysadmin=True` routes with an audit log of the injected tenant (target 100%).
- Verifier-required-in-prod guard present (boolean; target true — H1).
- SAM: 0 `.scan()` and 0 direct-DynamoDB-in-handler occurrences (enforce via L3).
- Deploy-role trust policy documented + reviewed (boolean; target true — L2).

### Re-assessment triggers
- A new SAM module (Events/Webshop) — re-run the tenancy/IAM/edge checks.
- Any change to `cognito_utils` auth path, `tenant_context` decorators, or `pretokengen`.
- A dependency bump to PyJWT / cryptography / boto3, or a ruff/CI policy change.

---

## Lessons / Recurring Issues

1. **The 2026-06 hardening held.** All nine areas from `security-hardening-2026-06-28/` remain implemented — no regressions found. This assessment did **not** re-open closed items; it found the *next* layer of (mostly Medium/Low) residual risk. Future security runs should likewise diff against the prior assessment rather than re-litigating fixed issues.
2. **Config-dependent security is the recurring theme.** The single High (F1) is not a code bug — it's a fail-open *fallback* that is safe in dev and dangerous only if prod runs unconfigured. The durable fix is to make the environment itself fail-closed (require a verifier when `RAILWAY_ENVIRONMENT=production`), so security no longer depends on remembering to set env vars.
3. **The SAM plane is strong-by-design but leans on code-correctness for tenant isolation.** Structural `tenant_id`-PK scoping is good, but the intended IAM `LeadingKeys` backstop (S1) is only a plan. Deploying it converts "isolated because the repository is correct" into "isolated even if a future bug isn't" — the defense-in-depth the design already describes.
4. **`allow_sysadmin` is a standing trust boundary (F2).** It's legitimate for system ops, but it grants a client header (`X-Tenant`) authority for SysAdmin callers. Keep the set of such routes small, inventoried, and audit-logged.
5. **Two things could not be verified from the repo** (S2, and the exact `allow_sysadmin` route inventory) — flagged honestly rather than assumed safe. Verifying them is cheap and belongs in the task list.
