# S4 — Staleness + Revocation Decision Record

- Status: **Decided** (settles S4 task **T17**; feeds **ADR 0006** (T20) + steering (T19))
- Spec: `.kiro/specs/multi-tenant/s4-token-entitlement-projection/`
- Design: **D4 — Staleness and revocation** (`design.md`)
- Requirements: **R4.1** (consistency), **R4.2** (bounded staleness), **R4.3** (revocation)
- Scope: Pool A only (`eu-west-1_Hdp40eWmu`). Pool B is deferred (no entitlement claim).
- Nature: a **decision document**, not code. It makes no live Cognito change. Applying the
  recommended token TTL to Pool A is a gated, pool-side change (see §4), like T18.

This record settles two questions S4 left "finalize at build" in D4: (1) how stale the
`custom:entitlements` token claim may become, and (2) how a security-critical downgrade is
honored **before** the token naturally expires. It is grounded in the pieces S4 actually
built — the versioned codec (T4), the T14 module-plane three-state reader, and the T15
Flask reader (token fast-path + DB fallback).

---

## 1. Staleness window (R4.2)

**Decision.** The entitlement claim is computed **once, at token issuance**, by the
Pre-Token-Generation Lambda (T11) from the MySQL system of record, and it **refreshes only
on token renewal** — a fresh login or a refresh-token exchange, both of which re-invoke the
PreTokenGen Lambda and recompute the claim from current MySQL state. There is no
in-place mutation of a live token.

**The staleness bound is exactly the access-token lifetime.** An access change — a role
grant/revoke in `user_tenant_roles`, or a module enable/disable in `tenant_modules` — takes
effect at the **next issuance**, and is therefore honored no later than one access-token
TTL after the change (sooner if the user re-authenticates or the client refreshes in the
interim). The window is **bounded and documented, never unbounded**, mirroring S3/R5.8's
"bounded, documented, never unbounded" rule.

**Concrete bound — current Pool A configuration (verified).** The Pool A app client
`myAdmin-client` (`infrastructure/cognito.tf`, pool `eu-west-1_Hdp40eWmu`) is currently:

| Token | Current validity | Source |
| --- | --- | --- |
| Access token | **60 minutes** | `access_token_validity = 60`, `access_token = "minutes"` |
| ID token | **60 minutes** | `id_token_validity = 60`, `id_token = "minutes"` |
| Refresh token | **30 days** | `refresh_token_validity = 30`, `refresh_token = "days"` |

So the entitlement staleness bound **today is 60 minutes** for the token the API path
verifies (the V2 PreTokenGen trigger stamps the claim into both the ID and access tokens).

**Recommendation.** Keep the **access/ID token TTL at 60 minutes** for Pool A. 60 minutes is
a reasonable staleness bound for role/module changes and is the value already configured, so
no change is required for the routine (non-urgent) case — the existing setting satisfies
R4.2. The **30-day refresh token** does not widen the entitlement staleness window: each
refresh re-invokes the PreTokenGen Lambda and recomputes the claim, so a refreshed access
token reflects MySQL **as of the refresh**, not as of the original login. The staleness
bound is the *access*-token TTL, not the refresh-token TTL.

> Caveat: this doc reads the **declared Terraform** for the app client. If the live Pool A
> app client has drifted from `cognito.tf`, the effective TTL must be confirmed against the
> deployed client before relying on the 60-minute bound. Any change to the TTL is a gated
> pool-side action (§4), never made silently.

---

## 2. Revocation policy for security-critical downgrades (R4.3)

The staleness bound in §1 is fine for ordinary changes but **too slow** for an urgent
downgrade — e.g. revoking a compromised or departing administrator, where waiting up to
60 minutes for the token to expire is unacceptable. S4 defines an explicit, layered policy.

### 2.1 The "sensitive capability subset"

We name a specific subset of capabilities as **security-critical**. For this subset the
token is **not** authoritative to expiry — a reader re-validates server-side against MySQL
(or the S3 projection). For everything else, the **token is authoritative until expiry**
(the fast path S4 exists to provide). The subset is defined by capability string (drawn from
`ROLE_PERMISSIONS` in `backend/src/auth/cognito_utils.py`):

- **Tenant administration / user management** — `tenant_admin`, `tenant_config`,
  `tenant_users`, `tenant_modules`, `tenant_settings` (the `Tenant_Admin` role). These
  govern who else can access a tenant and how it is configured; a revoked tenant admin must
  lose them promptly.
- **Global/system administration** — the wildcard-granting roles `Administrators` and
  `System_CRUD` (`"*"`), and `SysAdmin`. Highest blast radius.
- **Destructive data operations** — the delete/CRUD capabilities `*_delete` and `*_crud`
  (e.g. `finance_delete`, `invoices_delete`, `transactions_delete`, `str_delete`,
  `bookings_delete`, `zzp_crud`). These can irreversibly alter a business owner's data.

Everything **not** in this list — the read/list/export capabilities (`*_read`, `*_list`,
`*_export`) and ordinary create/update — is treated as **token-authoritative until expiry**:
the T14/T15 fast path answers directly with no server round-trip. This keeps S4's core value
(authorize from the verified token, no request-time MySQL) intact for the common case, while
tightening only the small, high-risk subset.

### 2.2 The three-layer policy

**Layer 1 — short natural window (baseline, all capabilities).** Keep the access-token TTL
short (the current 60 min, §1) so *every* downgrade — sensitive or not — is honored within
that window without any extra machinery. This is the floor.

**Layer 2 — server-side re-validation of the sensitive subset (the mechanism already
exists).** For a capability in §2.1, a reader must **not** trust the token to expiry. It
re-validates the answer server-side (against MySQL via `role_cache`/the T1 resolver on the
Flask plane, or the S3 DynamoDB projection on the module plane) at the moment of the
sensitive action. Crucially, **the mechanism is already built**:

- **Module plane (T14 reader).** `has_capability(claims, tenant, capability)` is
  deliberately **three-state**: `True` / `False` (authoritative token-backed decision) or
  **`None` = "the token does not answer this; consult server / S3 or deny."** The caller
  contract for a sensitive-subset capability is: **treat the token's `True` as
  provisional and re-check server-side** — i.e. route sensitive capabilities down the same
  `None`-handling path the reader already forces for absent/unknown-version/malformed claims
  and for the **overflow** signal (T4). No new reader surface is needed; the sensitive-subset
  policy reuses the existing "consult server" branch.
- **Flask plane (T15 reader).** The helper already prefers the token claim and **falls back
  to the DB path** (`role_cache.get_tenant_roles` → module gate → the same T1
  `resolve_entitlement`). For a sensitive-subset capability the caller forces the DB path
  (skip the token fast-path), which recomputes from live MySQL. Because both carriers run
  the identical T1 rule (T2/T6 equivalence), the re-validated answer is the same rule,
  just computed *now* instead of at issuance — see §3.

This ties directly to the two "token can't answer" signals S4 already surfaces: the T4
**overflow** signal and the T14 three-state **`None`** both mean "consult server," so the
sensitive-subset re-validation is a *third caller* of an existing branch, not new plumbing.

**Layer 3 — forced global sign-out / token revocation (highest severity).** For the
highest-severity cases — a compromised admin account, an urgent full revocation — use a
Cognito **global sign-out** for that user (`AdminUserGlobalSignOut`), which invalidates the
user's outstanding refresh tokens so no *new* access token can be minted for them; combined
with the short access-token TTL (Layer 1), their access is fully cut within one TTL, and
the sensitive-subset server-check (Layer 2) covers the residual window for the critical
capabilities. This is an operational action, invoked deliberately for severe cases — not the
per-request path.

### 2.3 Summary table

| Capability class | Token trust | How honored on downgrade |
| --- | --- | --- |
| Reads / lists / exports, ordinary create/update | **Authoritative until expiry** | Layer 1: next issuance / ≤ access-token TTL (60 min) |
| Sensitive subset (§2.1: tenant-admin, global-admin, destructive) | **Provisional — re-check server-side** | Layer 2: reader consults MySQL / S3 (T14 `None` path / T15 DB fallback) at action time |
| Compromised account / urgent full revocation | n/a | Layer 3: `AdminUserGlobalSignOut` + short TTL |

---

## 3. Consistency note (R4.1)

The token claim and the Flask plane's `role_cache.py` decision **cannot disagree for the
same MySQL state**, because both carriers run the **single T1 resolver**
(`backend/src/auth/entitlement_resolver.py`): the PreTokenGen Lambda (T11) encodes the
resolver's output into the claim, and the T15 Flask fallback recomputes it from
`role_cache.get_tenant_roles` + the module gate through the *same* `resolve_entitlement`.
This one-rule-two-carriers property is proven by the T2/T6 equivalence tests.

The **only** difference between the two answers is **when** each was computed: the token
reflects MySQL at issuance, the DB path reflects MySQL now. That temporal gap is exactly the
staleness window §1 bounds. So the Layer-2 server re-validation of the sensitive subset is
not a *different rule* that might contradict the token — it is the **same rule, recomputed
against fresher state**. Consistency (R4.1) and bounded staleness (R4.2) are therefore
complementary, not in tension.

---

## 4. Application + gating note

- **No live Cognito change is made by this document.** The current 60-minute access/ID token
  TTL already satisfies the recommended staleness bound, so no TTL change is required today.
- If a future decision shortens the Pool A access-token TTL further, that is a **gated,
  pool-side change** to the `myAdmin-client` app client in `infrastructure/cognito.tf`
  (`access_token_validity` / `token_validity_units`) — treated like other Pool A changes
  (human-gated, verify, rollback = restore the prior value), never applied silently.
- **Layer 2** is a *caller contract* on top of the already-shipped T14/T15 readers: readers
  route sensitive-subset capabilities down the existing "consult server" branch. No new
  reader code is mandated by S4; wiring specific sensitive actions to the server-check is a
  per-consumer concern (a real module gating in production is S5).
- **Layer 3** (`AdminUserGlobalSignOut`) is an operational runbook action, not request-path
  code.

---

## 5. Feeds

- **ADR 0006 (T20):** record "bounded staleness = access-token TTL (Pool A: 60 min); urgent
  downgrades handled by short TTL + server-side re-validation of a named sensitive
  capability subset + forced global sign-out for severe cases; one T1 resolver shared with
  `role_cache.py` so the carriers never disagree (R4.1)."
- **Steering (T19):** fold the bounded-staleness + revocation decision into
  `architecture.md` / `authentication.md` alongside "entitlement projected into the token at
  issuance, not read from MySQL per request."
