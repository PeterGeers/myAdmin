# Design Document

## S5f — SAM Members edge: active-tenant resolution — Design

- Requirements: `./requirements.md` (R1–R8).
- Governing steering: `20-platform-architecture`, `22-authentication`,
  `35-sam-module-architecture-sam`, `34-backend-testing`, `40-spec-workflow`.
- Proven pattern to mirror: `backend/src/auth/tenant_context.py`
  (`get_current_tenant` / `validate_tenant_access`).
- Deploy pipeline (from s5e): `sam/members/samconfig.toml` + `deploy-sam-members.yml`.

## Overview

Replace the SAM edge's over-strict single-tenant gate with a per-request **active-tenant
selection**: read `X-Tenant`, validate it against the verified `entitlement.tenant_keys`, and
scope the request to that one tenant. The header **selects among verified tenants**; it never
grants one. The change is confined to the tenant-selection seam in
`sam/members/handler/app.py` (`_establish_tenant_context` + its call site) plus a tiny
case-insensitive header helper — capability and scope resolution are untouched (R8.1).

Current (bug) vs target:

| Case | `X-Tenant` | `tenant_keys` | today | target |
|---|---|---|---|---|
| single tenant, no header | — | `[t]` | ✅ `t` | ✅ `t` (R2.1, unchanged) |
| single tenant, header=t | `t` | `[t]` | ✅ `t` (len==1) | ✅ `t` (R2.2) |
| **multi, header=allowed** | `h-dcn` | `[a, h-dcn]` | ❌ **403** | ✅ `h-dcn` (R1.1) |
| multi, header not allowed | `x` | `[a, h-dcn]` | ❌ 403 | ❌ 403 (R1.2) |
| **multi, no header** | — | `[a, h-dcn]` | ❌ 403 | ❌ deny "specify tenant" (R3 / OD1) |
| fallback / overflow | any | — | ❌ 403 | ❌ 403 (R4, unchanged) |
| empty entitlement | any | `[]` | ❌ 403 | ❌ 403 (R4.2, unchanged) |

The only behaviour that CHANGES is the two **multi-tenant** rows; every single-tenant and
fail-safe row is preserved bit-for-bit.

## Design decisions

### D1 — Signature: `_establish_tenant_context(entitlement, requested_tenant)`

Today `_establish_tenant_context(entitlement) -> str` receives only the decoded entitlement,
by design (the pilot's "never read a header" stance). The minimal, faithful change is to add
the **already-extracted** requested tenant as a second parameter:

```python
def _establish_tenant_context(
    entitlement: DecodedEntitlements,
    requested_tenant: Optional[str],
) -> str:
    # 1. Non-answering token → deny (unchanged, R4).
    if entitlement.fallback_required or entitlement.is_overflow:
        raise TenantResolutionError("Token does not carry a usable tenant entitlement")

    tenant_keys = entitlement.tenant_keys
    if not tenant_keys:
        # empty entitlement (valid, handled) → no verified tenant to select (R4.2)
        raise TenantResolutionError("Verified entitlement lists no tenant")

    # 2. Header present → it MUST be a verified tenant (selector, never grant) (R1).
    if requested_tenant:
        if requested_tenant in tenant_keys:
            return requested_tenant
        raise TenantResolutionError("Selected tenant is not in the verified entitlement")

    # 3. No header → single-tenant back-compat; multi is ambiguous → deny (R2 / R3).
    if len(tenant_keys) == 1:
        return tenant_keys[0]
    raise TenantResolutionError("No tenant selected; specify X-Tenant")  # OD1 → 403
```

- The function stays **pure** (no I/O, no header parsing inside) — the header is extracted at
  the call site and passed in, matching how `claims`/`entitlement` are already prepared there.
  This keeps it trivially unit-testable and preserves the verify-before-trust boundary (the
  function only ever *validates* the selector against the verified list).
- `requested_tenant` is `Optional[str]`: `None`/empty means "no selection".
- Rejected: reading `event["headers"]` INSIDE `_establish_tenant_context` — it would couple
  the pure resolver to the API-GW event shape and duplicate the header parsing the edge
  already does. The call site is the right place to read the header.

### D2 — Case-insensitive header extraction (helper)

API Gateway REST v1 preserves the client casing (`X-Tenant`); HTTP API v2 lowercases
(`x-tenant`). The edge already parses headers into `request.headers` (verbatim, no
normalization). Add a small helper mirroring `_bearer_token_from_event` in
`sam/shared/auth_utils.py` (which does `name.lower() == "authorization"`):

```python
def _requested_tenant_from_request(request: ParsedRequest) -> Optional[str]:
    """The client's selected active tenant from the X-Tenant header (case-insensitive
    NAME lookup), or None. A SELECTOR, not an authorization — validated downstream."""
    for name, value in (request.headers or {}).items():
        if name.lower() == "x-tenant":
            v = (value or "").strip()
            return v or None
    return None
```

- Header **name** is matched case-insensitively; the **value** (a tenant id) is returned
  verbatim and matched EXACTLY against `tenant_keys` (tenant ids are case-sensitive) (R1.3).
- Empty/whitespace header value → `None` (treated as "no selection"), so an empty header can't
  masquerade as a selection.

### D3 — Call-site wiring (in `_authenticate_and_authorize`)

At the existing call site, `request` (with `.headers`), `event`, `claims`, and `entitlement`
are all in scope. Change:

```python
entitlement = get_entitlements_from_claims(claims)
requested_tenant = _requested_tenant_from_request(request)          # D2
tenant_id = _establish_tenant_context(entitlement, requested_tenant)  # D1
```

Everything downstream (`has_capability`, `_resolve_scope_access`, the `RequestContext`, the
domain dispatch) already consumes `tenant_id` — so the SELECTED tenant automatically scopes
the whole request (R1.4) with no further change.

### D4 — Validate against `tenant_keys`, NOT `custom:tenants` (R5.3, glossary)

The verified allow-list for the Members API is `entitlement.tenant_keys` — the tenants the
user has member-module capabilities for (from `custom:entitlements`). This is a
**capability-scoped subset** of the broad `custom:tenants`. Validating the header against
`tenant_keys` means: a tenant the user can log into but has NO members capability for is
correctly denied at the tenant-selection step (it isn't in `tenant_keys`), rather than
passing tenant-selection and later failing the capability check. Both deny; validating
against `tenant_keys` denies earlier and for the right reason. (It also means the capability
gate that follows is always evaluated for a tenant the user provably has entitlements in.)

### D5 — OD1 RESOLVED: all deny paths → 403 (the active tenant bounds capability)

**Framing (user, settled): the tenant a user is working in LIMITS their capabilities.**
The active tenant is the lens through which capability is evaluated — if the user is in a
tenant that grants them no members capability, the Members API is simply not theirs to use
*in that context*, and the correct response is a **deny (403 Forbidden)**. This is why
validation is against `entitlement.tenant_keys` (D4): a tenant with no MEMBERS module yields
no members entitlement for the user, so it is **not in `tenant_keys`**, so selecting it →
403. Two layers enforce this, belt-and-suspenders:
- **UI (already built):** the SPA gates the Members menu/route on the ACTIVE tenant's modules
  via `useTenantModules().hasMEMBERS` (`frontend/src/components/MainMenu.tsx`,
  `TenantAdminDashboard.tsx`). A tenant without MEMBERS never offers the Members app — "there
  should never be the option to switch." No frontend change is needed for this in s5f.
- **API edge (this fix):** if the Members API is hit anyway (stale UI, direct call), the edge
  denies because the active tenant is not in the user's members `tenant_keys`.

**OD1 (the absent-header + multiple-tenants ambiguity) → 403, uniform with every other tenant
deny.** No default-to-first. The Flask plane defaults to `tenant_keys[0]`; this design does
NOT, because:
- The Members API returns/mutates **one tenant's member records per request**. Defaulting to
  `tenant_keys[0]` for a multi-tenant user with no selection would silently return the WRONG
  tenant's members — a data-exposure footgun, not just a UX annoyance.
- The client ALWAYS sends `X-Tenant` (the SPA sets it from `localStorage['selectedTenant']`);
  an absent header on a multi-tenant request is therefore an anomaly worth surfacing, not a
  routine case to paper over with a guess.

**Decision (OD1 = 403, RESOLVED):** every failure to establish a valid active-tenant context
— header not in `tenant_keys`, absent header with multiple tenants, fallback/overflow, empty
entitlement — denies with **403** via the existing `TenantResolutionError`. NO new exception
class, NO 400 path, NO default-to-first. All tenant-context failures stay on one status,
matching the settled principle: the active tenant bounds capability, so when it grants no
members access, a deny is the proper mode.

- The response body MAY carry a machine-readable marker on the absent-header-multi branch
  (e.g. `{"error": "...", "code": "tenant_selection_required"}`) so the SPA can tell "pick a
  tenant" apart from a hard denial — WITHOUT changing the status (still 403) and without
  leaking tenants the caller doesn't already hold. Optional polish, not required.
- `TenantResolutionError` already maps to 403 in `handler()`; no `handler()` change and no
  new exception class are needed.

### D6 — Verify-before-trust preserved (the safety argument)

The relaxation is provably safe: `_establish_tenant_context` returns a tenant ONLY if it is a
member of `entitlement.tenant_keys` (the verified list). The header can never introduce a
tenant the verified token does not carry. So Property 2 (no unverified authority) holds
exactly as before — the pilot's "exactly one" was *sufficient* for safety but not *necessary*;
"in the verified set" is the correct necessary-and-sufficient condition. The module docstrings
that say `X-Tenant` "is never consulted" are updated to "selects among verified tenants, never
grants".

## Components touched

- `sam/members/handler/app.py`:
  - `_establish_tenant_context` — new `requested_tenant` param + validation (D1).
  - `_requested_tenant_from_request` — new case-insensitive header helper (D2).
  - `_authenticate_and_authorize` — extract header, pass to resolver (D3).
  - (optional) add a `code: tenant_selection_required` marker to the R3-branch 403 body — no
    new exception class, no status change (OD1 = 403).
  - Docstring updates on the tenant seam (D6).
- `sam/tests/test_members_auth_edge.py` — new multi-tenant tests (R6).
- `docs/decisions/0007-active-tenant-resolution-sam-edge.md` — new ADR (R7).
- `35-sam-module-architecture-sam.md` — one-line pointer to the ADR (R7.2).
- NO change to: router, repository, domain, `has_capability`, `_resolve_scope_access`,
  the frontend (it already sends `X-Tenant`).

## Correctness properties

- **P1 — Header selects, never grants.** `_establish_tenant_context` returns a tenant only if
  `requested_tenant in entitlement.tenant_keys`; an out-of-set header → 403. _(R1.2, D6)_
- **P2 — Verified-only authority preserved.** No tenant is ever operated under that is absent
  from the verified entitlement (Property 2 of the pilot, unchanged). _(R1, R4, D6)_
- **P3 — Single-tenant unchanged.** Absent header + one tenant → that tenant; matches pilot
  behaviour exactly (no regression). _(R2.1)_
- **P4 — No silent wrong-tenant.** Absent header + multiple tenants never returns data; it
  denies asking for a selection. _(R3.1, D5)_
- **P5 — Fail-safe unchanged.** `fallback_required` / `is_overflow` / empty `tenant_keys` deny
  regardless of the header. _(R4)_
- **P6 — No fallback introduced.** Active tenant derives only from the validated header or the
  single-tenant degenerate case; grep-clean guards still pass. _(R5)_
- **P7 — Selected tenant scopes the whole request.** Capability + scope + domain all run under
  the selected `tenant_id`. _(R1.4)_

## Open decisions

- **OD1 — RESOLVED (user, 2026-09-23): 403 for all deny paths.** Explicit deny, no
  default-to-first, no 400/`TenantSelectionRequired` class — via the existing
  `TenantResolutionError` → 403. Rationale: the active tenant bounds capability; a tenant
  that grants no members access is a deny, uniform with every other tenant-context failure.
  (Optional: a `code: tenant_selection_required` body marker on the no-header-multi branch,
  status still 403.)
- **OD2 (noted, likely no-op): SPA behaviour on the R3 deny.** The SPA already sends
  `X-Tenant`, so the ambiguous case should be rare in practice. IF a client omits it, the
  `code: tenant_selection_required` marker lets the SPA prompt. No frontend change is in scope
  for s5f; a follow-up may harden the SPA to guarantee the header is always set.
