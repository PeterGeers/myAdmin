# Requirements Document

## S5f — SAM Members edge: resolve an active tenant for multi-tenant users — Requirements

- Status: **Draft** (requirements phase — check in before design)
- Discovered during: **s5d PHASE CE / CE.7** (2026-09-23). **BLOCKS s5d PHASE D.** See
  `myBacklog/backlog.md` ("SAM Members edge can't resolve an active tenant…").
- This is **#1 of 3** s5d-remediation specs and the only one that blocks s5d. The others are
  #2 (projection `role#`/`module#` reconcile) and #3 (codify SAM deploys — **DONE**, s5e).
  Because #3 shipped, this fix can now deploy through the codified `sam/members` pipeline
  (committed `samconfig.toml` + `deploy-sam-members.yml`, OIDC) — one reviewed command, no
  hand-typed deploy.
- Governing steering: `20-platform-architecture`, `21-identity`, `22-authentication`
  (verified-JWT), `35-sam-module-architecture-sam`, `34-backend-testing`, `40-spec-workflow`.

## Introduction

The SAM Members API edge rejects **every multi-tenant user with a 403**, even when their
verified token carries the correct capabilities for the tenant they are working in. The
cause is a single check in `sam/members/handler/app.py`:

```python
def _establish_tenant_context(entitlement: DecodedEntitlements) -> str:
    if entitlement.fallback_required or entitlement.is_overflow:
        raise TenantResolutionError("Token does not carry a usable tenant entitlement")
    tenant_keys = entitlement.tenant_keys
    if len(tenant_keys) == 1:
        return tenant_keys[0]
    raise TenantResolutionError("Verified entitlement does not resolve a single tenant context")
```

`len(tenant_keys) == 1` was the **pilot's** single-tenant fail-safe: with one tenant there is
nothing to choose, so the edge never had to read a selector. But any user entitled to **more
than one** tenant (verified this session: `peter@pgeers.nl` = 7 tenants;
`webmaster@h-dcn.nl` = `["mytest3","h-dcn"]`) falls into the `else` and gets a 403 — an early
edge deny (~3.5ms), so `members-prod` app logs show no error. In the UI this surfaces as
"no members shown" despite a token that correctly lists `h-dcn:[members:admin/export/read/write]`.

This is **not** the intended model. The **active tenant is a per-request selection**:
- the client sends the chosen tenant via the **`X-Tenant`** header,
- the edge validates that the selected tenant is one the caller is **verified** to hold (it
  must be in the token's entitlement), and
- the request proceeds scoped to that **single active tenant**.
A single-tenant user is just the degenerate case (one allowed tenant, no ambiguity).

This exact pattern is **already proven** on the Flask/UI plane of myAdmin
(`backend/src/auth/tenant_context.py`: `get_current_tenant` reads `X-Tenant`;
`validate_tenant_access` checks it against the verified tenant list;
`@tenant_required` enforces it). And the **client already sends it**:
`frontend/src/services/membersApiService.ts` sets `X-Tenant` from
`localStorage['selectedTenant']` on every Members API call. So the fix consumes an existing
client contract and mirrors an existing, proven server pattern — it does not invent a new one.

**Crucial safety framing (verify-before-trust is preserved).** `X-Tenant` is a **selector
among already-verified tenants**, never a grant. The header **cannot** authorize a tenant the
token does not carry: the edge validates the header against the verified entitlement and
denies (403) if the selected tenant is not in it. So this relaxes the pilot's over-strict
"exactly one" gate WITHOUT weakening the "no unverified authority" property (ADR 0004/0006).

## Glossary

- **Active tenant** — the single tenant a given request operates under, chosen per-request by
  the client and validated by the edge. Not a user attribute; a request attribute.
- **`X-Tenant`** — the request header carrying the client's chosen active tenant (the SPA's
  `localStorage['selectedTenant']`). A **selector**, not an authorization.
- **`entitlement.tenant_keys`** — the tenants the **verified** `custom:entitlements` claim
  lists for the user (for a normal claim, `sorted(tenants.keys())` — the tenants the user has
  member-module capabilities for). This is the **verified allow-list** `X-Tenant` is checked
  against. NOTE: it is a **capability-scoped subset**, not necessarily the same as the broad
  `custom:tenants` list — validating against `tenant_keys` correctly denies a selected tenant
  the user has no members capability for.
- **`DecodedEntitlements`** — the frozen result of `decode_entitlements` (`sam/shared/
  entitlement_claim.py`): `tenants`, `tenant_keys`, `is_overflow`, `fallback_required`.
- **`TenantResolutionError`** — the edge's 403 raised when no valid active tenant can be
  established (subclass of `AuthorizationError`).
- **Verify-before-trust** — authority derives ONLY from the verified token; a client header
  may *select* among verified options but may never *grant* (ADR 0004/0006).

## Guiding principles (settled — requirements enforce them)

- **Active tenant is per-request, selected via `X-Tenant`, validated against the verified
  entitlement.** Mirror the proven Flask `get_current_tenant` / `validate_tenant_access`.
- **The header selects, never grants.** A selected tenant not in `entitlement.tenant_keys` is
  a 403. No unverified tenant is ever operated under (Property 2 preserved).
- **Single-tenant is the degenerate case, kept working.** A user with exactly one entitled
  tenant and no header resolves to that tenant (back-compat — the pilot behaviour).
- **No hardcoded / env / default tenant.** The fix introduces NO `h-dcn` default and NO
  `MEMBERS_LOCAL_TENANT_ID`-style fallback. The existing grep-clean guards
  (`test_tenant_fallback_symbols_removed_from_live_code`) MUST still pass.
- **Fail-safe on a non-answering token unchanged.** `fallback_required` / `is_overflow`
  (and an empty entitlement = zero tenants) still deny by default — the header cannot rescue
  a token that carries no usable entitlement.
- **Thin edge, no new authority.** The change is confined to tenant *selection* at the edge;
  capability and scope resolution (`has_capability`, `_resolve_scope_access`) are untouched.
- **Validate against `tenant_keys`, not `custom:tenants`.** The Members API's verified
  allow-list is the capability-bearing tenant set.
- **The active tenant BOUNDS capability (settled).** A user's capabilities are evaluated
  through the tenant they are working in. If the active tenant grants them no members
  capability (e.g. the tenant has no MEMBERS module), the Members API is not theirs to use in
  that context → **deny (403)**. Two layers enforce this: (1) the SPA already gates the
  Members menu on the active tenant's modules (`useTenantModules().hasMEMBERS` in
  `MainMenu.tsx` / `TenantAdminDashboard.tsx`) so a no-members tenant never offers the app —
  "there should never be the option to switch"; (2) the API edge (this fix) denies if hit
  anyway. The edge is the enforcement backstop to the UI gate.
- **A deny is the proper mode for every failed active-tenant resolution → 403.** No 400, no
  default-to-first, no new exception class (OD1 resolved).

## Requirements

### R1 — Resolve the active tenant from `X-Tenant`, validated against the verified entitlement

**User story:** As a multi-tenant Members user, I want the tenant I selected in the SPA to be
honoured by the Members API so that I can see and manage the members of the tenant I'm working
in, instead of being blanket-denied.

#### Acceptance criteria
1. WHEN the request carries an `X-Tenant` header AND its value is in
   `entitlement.tenant_keys` THEN the edge SHALL establish that value as the active
   `tenant_id` and proceed (200-path, subject to capability + scope).
2. WHEN the request carries an `X-Tenant` header AND its value is NOT in
   `entitlement.tenant_keys` THEN the edge SHALL deny with a 403
   (`TenantResolutionError`) — the header never grants an unverified tenant (Property 2).
   This is exactly the "active tenant grants no members capability" case (e.g. the selected
   tenant has no MEMBERS module → no members entitlement → not in `tenant_keys`): the active
   tenant bounds capability, so the deny is correct. (The SPA already prevents offering the
   Members app for such a tenant; this is the edge backstop.)
3. The `X-Tenant` lookup SHALL be **case-insensitive on the header NAME** (API Gateway REST
   v1 preserves the client casing `X-Tenant`; HTTP API v2 lowercases to `x-tenant`), mirroring
   the bearer-token lookup in `sam/shared/auth_utils.py`. The header VALUE is matched exactly
   against `tenant_keys` (tenant ids are case-sensitive).
4. The selected active tenant SHALL scope the ENTIRE rest of the request (capability check,
   scope resolution, and domain reads/writes) — exactly as the single resolved tenant does
   today. No code path may operate under a different tenant than the validated selection.

### R2 — Single-tenant back-compat (absent header, one entitled tenant)

**User story:** As a single-tenant Members user, I want the API to keep working without any
client change so that the fix is backward-compatible.

#### Acceptance criteria
1. WHEN no `X-Tenant` header is present AND `entitlement.tenant_keys` has exactly ONE tenant
   THEN the edge SHALL establish that tenant as the active `tenant_id` (unchanged pilot
   behaviour — no regression).
2. WHEN an `X-Tenant` header IS present, is in `tenant_keys`, and the user has exactly one
   tenant THEN R1.1 applies (the header agrees with the only option) — still a 200-path.

### R3 — Absent header with multiple entitled tenants (the ambiguity case)

**User story:** As the platform, I want an unambiguous, safe behaviour when a multi-tenant
user's request arrives without a tenant selection so that the edge never silently picks the
wrong tenant's data.

#### Acceptance criteria
1. WHEN no `X-Tenant` header is present AND `entitlement.tenant_keys` has MORE THAN ONE tenant
   THEN the edge SHALL NOT silently pick one; it SHALL **deny with a 403**
   (`TenantResolutionError`) — no default-to-first (**OD1 RESOLVED: 403**, D5). Picking the
   wrong tenant would silently expose the wrong tenant's members.
2. The response body MAY carry a machine-readable marker (e.g.
   `{"code": "tenant_selection_required"}`) so the SPA can tell "pick a tenant" apart from a
   hard denial and prompt — WITHOUT changing the status (still 403) and without leaking
   tenants the caller doesn't already hold. Optional polish, not required.
3. This deliberately **deviates from the Flask default-to-`tenant_keys[0]`**: the SAM Members
   API deals in one tenant's member records per request, so defaulting risks the wrong
   tenant's data. In practice the SPA always sends `X-Tenant`, so an absent header on a
   multi-tenant request is an anomaly to deny, not a routine case to guess. The spec records
   this deviation (design D5).

### R4 — Fail-safe on a non-answering token is unchanged

**User story:** As the platform, I want a token that carries no usable entitlement to keep
being denied so that the header cannot rescue an un-authenticatable/un-entitled caller.

#### Acceptance criteria
1. WHEN `entitlement.fallback_required` OR `entitlement.is_overflow` is true THEN the edge
   SHALL deny with 403 REGARDLESS of any `X-Tenant` header (the header cannot substitute for
   a missing/overflow entitlement).
2. WHEN `entitlement.tenant_keys` is EMPTY (a valid, handled empty entitlement) THEN the edge
   SHALL deny with 403 regardless of the header (there is no verified tenant to select from).
3. The existing fail-safe tests (`test_no_entitlement_token_denied_honestly_at_tenant_step`,
   `…_403s_with_no_env_set`, overflow/malformed 403 tests) SHALL still pass unchanged.

### R5 — No hardcoded / env / default tenant (grep-clean preserved)

**User story:** As a reviewer, I want assurance the fix adds no silent tenant fallback so that
"the header selects among verified tenants" cannot degrade into "the edge guesses a tenant".

#### Acceptance criteria
1. The fix SHALL introduce NO hardcoded tenant (no `h-dcn` default), NO
   `MEMBERS_LOCAL_TENANT_ID`-style env fallback, and NO default-to-first for the ambiguous
   case (per R3, unless OD1 explicitly chooses Flask-style default with a recorded rationale).
2. The existing AST-based grep-clean guards
   (`test_tenant_fallback_symbols_removed_from_live_code`, the `MEMBERS_LOCAL_TENANT_ID`
   live-reference guard) SHALL still pass.
3. The active tenant SHALL derive ONLY from (a) the `X-Tenant` selector validated against (b)
   the verified `entitlement.tenant_keys` — no third source.

### R6 — Tests: multi-tenant selection is pinned

**User story:** As a maintainer, I want the multi-tenant contract covered by tests so that the
"exactly one" regression can never silently return.

#### Acceptance criteria
1. New tests in `sam/tests/test_members_auth_edge.py` (extending `_authorizer_event`'s
   `extra_headers` + a multi-tenant `custom:entitlements` helper) SHALL cover: (a) `X-Tenant`
   selecting an allowed tenant among many → 200-path; (b) `X-Tenant` not in `tenant_keys`
   → 403; (c) absent header + multiple tenants → the R3 deny; (d) absent header + single
   tenant → 200-path (R2); (e) case-insensitive header name (`x-tenant`) → resolves.
2. The tests SHALL assert the request actually operates under the SELECTED tenant (not merely
   that it returns 200) — e.g. the capability/scope decision is made for the selected tenant.
3. All existing `test_members_auth_edge.py` tests (401/403/503, fail-safe, grep-clean) SHALL
   remain green.

### R7 — ADR: the active-tenant resolution contract

**User story:** As the platform, I want the active-tenant contract recorded as an ADR so that
future SAM modules (Events/Webshop) resolve tenant identically.

#### Acceptance criteria
1. An ADR (under `docs/adr/` alongside 0004/0006) SHALL record: active tenant = per-request
   `X-Tenant` validated against the verified entitlement's `tenant_keys`; header selects,
   never grants; single-tenant degenerate case; no fallback; the ambiguous-case decision
   (OD1). It SHALL note this is the module-plane analogue of the Flask
   `get_current_tenant`/`validate_tenant_access` pattern.
2. The ADR SHALL be referenced from the design and from
   `35-sam-module-architecture-sam.md` so the next module inherits the contract.

### R8 — Scope discipline & deploy

**User story:** As a reviewer, I want the change tightly scoped and shipped through the
codified pipeline so that unblocking s5d Phase D carries minimal risk.

#### Acceptance criteria
1. The change SHALL be confined to the tenant-**selection** seam:
   `_establish_tenant_context` (+ a small case-insensitive header helper) and its call site in
   `_authenticate_and_authorize` (`sam/members/handler/app.py`), plus tests, the ADR, and doc
   pointers. Capability resolution (`has_capability`), scope resolution
   (`_resolve_scope_access`), the router, the repository, and the domain layer SHALL be
   untouched.
2. The fix SHALL deploy via the codified `sam/members` pipeline delivered in s5e
   (`sam deploy --config-env prod` / `deploy-sam-members.yml`), NOT a hand-typed deploy.
3. AFTER deploy, s5d PHASE D SHALL be re-tested: a multi-tenant user (e.g. `peter@pgeers.nl`
   with `X-Tenant: h-dcn`) SHALL see h-dcn members via the SPA (the original blocked
   outcome), and existing single-tenant flows SHALL be unaffected.
