# ADR 0007 — Active-tenant resolution at the SAM module edge: X-Tenant selects among the verified entitlement's tenants

- Status: Accepted
- Date: 2026-09-23
- Relates to: ADR 0004 (verified-JWT-only), ADR 0006 (resolved entitlement in the token via
  PreTokenGen). Fixes the multi-tenant edge behaviour discovered during s5d PHASE CE and
  unblocks s5d PHASE D. Spec: `.kiro/specs/multi-tenant/s5f-sam-edge-active-tenant/`.

## Context

The SAM Members module edge (`sam/members/handler/app.py`, `_establish_tenant_context`)
derived the request's tenant SOLELY from the verified entitlement and required **exactly one**
tenant:

```python
tenant_keys = entitlement.tenant_keys
if len(tenant_keys) == 1:
    return tenant_keys[0]
raise TenantResolutionError(...)   # 0 or >1 → 403
```

This was the pilot's single-tenant fail-safe: with one tenant there is nothing to choose, so
the edge never had to read a selector, and it deliberately "never consulted" client headers
(the strongest reading of verify-before-trust, ADR 0004). But any user entitled to **more than
one** tenant (verified: `peter@pgeers.nl` = 7 tenants; `webmaster@h-dcn.nl` =
`["mytest3","h-dcn"]`) hit the `else` and got a **403** — even though their verified token
carried the correct `h-dcn:[members:...]` capabilities. In the SPA this surfaced as "no
members shown"; the deny was at the edge (~3.5ms), so app logs showed no error.

The active tenant is inherently a **per-request** choice: a multi-tenant user is working in ONE
tenant at a time, chosen in the UI. The SPA already sends that choice as the `X-Tenant` header
(`frontend/src/services/membersApiService.ts`, from `localStorage['selectedTenant']`), and the
Flask/UI plane already resolves tenant this way (`backend/src/auth/tenant_context.py`:
`get_current_tenant` reads `X-Tenant`; `validate_tenant_access` checks it against the verified
tenant list). Only the SAM edge was out of step.

## Decision

**The active tenant is resolved per-request: read the `X-Tenant` header and VALIDATE it against
the verified entitlement's `tenant_keys`. The header SELECTS among the caller's verified
tenants; it never GRANTS one.**

Resolution order in `_establish_tenant_context(entitlement, requested_tenant)`:

1. Non-answering token (`fallback_required` / `is_overflow`) → **403** (fail-safe; the header
   cannot rescue a token with no usable entitlement).
2. Empty `tenant_keys` (valid, handled empty entitlement) → **403** (no verified tenant to
   select from).
3. `X-Tenant` present → return it **iff it is in `tenant_keys`**, else **403**.
4. No `X-Tenant` + exactly one entitled tenant → that tenant (single-tenant back-compat, the
   pilot behaviour, unchanged).
5. No `X-Tenant` + multiple entitled tenants → **403** (ambiguous; never default-to-first —
   picking one could expose the wrong tenant's members).

Supporting choices:

- **Validate against `tenant_keys`, not `custom:tenants`.** `tenant_keys` is the tenants the
  user has MEMBER-module capabilities for (from `custom:entitlements`) — a capability-scoped
  subset. So a tenant the user can log into but which grants no members capability (e.g. it has
  no MEMBERS module) is not in `tenant_keys` and is correctly denied. **The active tenant bounds
  capability.**
- **Case-insensitive header NAME.** API Gateway REST v1 preserves `X-Tenant`; HTTP API v2
  lowercases to `x-tenant`. The lookup matches the name case-insensitively (mirroring the
  bearer-token lookup); the VALUE is matched exactly against `tenant_keys` (tenant ids are
  case-sensitive). An empty/whitespace header reads as "no selection".
- **All deny paths → 403** via the existing `TenantResolutionError`. No 400, no new exception
  class, no default-to-first (s5f OD1). A tenant that does not grant the capability is a
  Forbidden, uniform with every other tenant-context failure.
- **No hardcoded / env / default tenant.** No `h-dcn` default, no `MEMBERS_LOCAL_TENANT_ID`.
  The active tenant derives ONLY from the validated selector or the single-tenant degenerate
  case. The existing AST grep-clean guards enforce this.
- **Two layers enforce "the active tenant bounds capability":** the SPA already gates the
  Members menu/route on the active tenant's modules (`useTenantModules().hasMEMBERS`) so a
  no-members tenant never offers the app; the edge (this ADR) is the enforcement backstop if
  the API is hit anyway.

## Rationale

- **Verify-before-trust is preserved, not weakened.** `_establish_tenant_context` returns a
  tenant ONLY if it is in the verified `tenant_keys`; the header can never introduce an
  unverified tenant (Property 2 of ADR 0004 holds exactly). The pilot's "exactly one" was
  *sufficient* for safety but not *necessary*; "in the verified set" is the correct
  necessary-and-sufficient condition. The header is a selector, not an authority.
- **Mirrors a proven pattern.** The Flask plane has resolved tenant via `X-Tenant` validated
  against the verified tenant list since S2; the SAM edge now matches it, so the two planes
  agree on how the active tenant is chosen.
- **Consumes an existing client contract.** The SPA already sends `X-Tenant`; no frontend
  change is needed for the fix.
- **Explicit deny over silent guess.** The Members API returns one tenant's records per
  request; defaulting an ambiguous no-header multi-tenant request to `tenant_keys[0]` (as Flask
  does) would risk exposing the wrong tenant's members. The SAM edge denies instead — the SPA
  always sends the header, so this is an anomaly to surface, not a routine case.

## Consequences

- **Multi-tenant Members users work.** Selecting an entitled tenant via `X-Tenant` reaches the
  Members API (subject to capability + scope); s5d PHASE D is unblocked.
- **Single-tenant + fail-safe behaviour is unchanged** (bit-for-bit): absent header + one
  tenant → that tenant; fallback/overflow/empty entitlement → 403 regardless of the header.
- **This is the active-tenant contract for the module plane.** Future SAM modules
  (Events/Webshop) resolve the active tenant the same way — `X-Tenant` validated ∈ verified
  `tenant_keys`, header selects never grants, no fallback. Recorded in
  `35-sam-module-architecture-sam.md`.
- **Deployed via the codified pipeline** (ADR-adjacent to s5e): the change ships through
  `sam/members/samconfig.toml` + `deploy-sam-members.yml` (`sam deploy --config-env prod` on
  merge), not a hand-typed deploy. Unlike s5e this IS a Lambda code change, so it is a genuine
  function update.
- **Optional future polish (not done):** a `code: tenant_selection_required` marker in the
  no-header-multi 403 body so the SPA can distinguish "pick a tenant" from a hard deny (status
  stays 403).

## Related

- ADR 0004 (verified-JWT-only — the Property-2 invariant this preserves), ADR 0006 (the
  `custom:entitlements` claim + `tenant_keys` this validates against).
- Steering: `.kiro/steering/35-sam-module-architecture-sam.md` (the module-edge contract),
  `22-authentication.md`, `23-aws-accounts.md`.
- Proven prior art: `backend/src/auth/tenant_context.py`
  (`get_current_tenant` / `validate_tenant_access`) — the Flask analogue this mirrors.
- Spec `.kiro/specs/multi-tenant/s5f-sam-edge-active-tenant/`
  (`requirements.md`, `design.md`, `tasks.md`).
- Unblocks `.kiro/specs/multi-tenant/s5d-member-scope-assignment/` PHASE D.
