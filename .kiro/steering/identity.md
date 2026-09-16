---
inclusion: auto
---

# Identity — Platform Identity Model

> Active-rules summary. Full reasoning:
> `.kiro/specs/multi-tenant/Analysis/second_thoughts.md` and `myadmin_as_base.md`.
> Decision of record: ADR 0003 (myAdmin is the platform base; evolve in place;
> import apps as SAM-backed modules).

myAdmin is the multi-tenant platform base. Identity is shared across the Flask/MySQL
plane (myAdmin) and any SAM-backed module plane, and is split by **audience**, not by
app or tenant.

## Two Cognito pools by audience

- **Pool A — Admin / staff.** People who operate tenants: tenant admins, sysadmins,
  finance staff, webmaster. Small, high-privilege. Carries roles (`cognito:groups`) +
  tenant access (`custom:tenants`, a list) + projected entitlement. Present for every
  tenant.
  - Tier: **Plus** (threat protection worthwhile for privileged users; tiny
    population, cost negligible).
  - **"Pool A" is an audience-role label, not the pool's name.** It is the existing
    Cognito pool **named `myAdmin`** — pool id `eu-west-1_Hdp40eWmu`, app client
    `myAdmin-client` (see `infrastructure/cognito.tf`), identity (personal) account —
    kept in place, not migrated.
- **Pool B — End-users.** Members / webshop customers of a tenant that enables them.
  Large, low-privilege. Carries a single `tenant_id` claim, no roles, no entitlement
  projection. **Optional per tenant** — enabled via a tenant module (`tenant_modules`).
  - Tier: **Essentials** (WebAuthn/passkeys included — not a Plus-only feature;
    10,000 free MAU; cheap at member scale).
  - A new, clean pool (greenfield — create it right, no migration).

**Guardrail:** split by audience only. Never split per-tenant or per-app.

**Pool A is the platform core; Pool B is a per-tenant option.** Admin-only tenants
(e.g. finance tenants) use only Pool A.

## Verification

Every backend — Flask plane and any SAM-backed module — verifies the JWT signature
against the originating pool's JWKS and reads claims **only** from the verified token.
Both pools live in the identity (personal) account; each backend knows which pool a
token is from (via `iss`) and applies that pool's claim interpretation. Never trust
unverified headers (`X-Tenant`, `X-Enhanced-Groups`) as a source of truth.

## Tenant relationships

- **Pool A (rich):** many-to-many with roles. `custom:tenants` (list) on the token;
  `user_tenant_roles` in MySQL is the system of record. Roles are tied to positions,
  not people — reallocation changes the assignment, never orphaning a tenant (always
  ≥1 tenant admin + a platform sysadmin break-glass path).
- **Pool B (simple):** one `tenant_id` on the token; the member/customer record in
  that tenant's module data (DynamoDB, carrying `tenant_id`) **is** the relationship.
  Established at registration by the portal/shop entered through (with admin approval
  where required, e.g. a `verzoek_lid` flow). Default one tenant per Pool B user.

## Deferred (do not build until a tenant needs it)

End-user↔tenant edge cases, not core to the platform:

- The "admin AND member" person — two linked accounts (Pool A + Pool B), linked by a
  shared `person_id` / verified email in MySQL. Cross-pool SSO for UX is later polish.
- Member → admin promotion (create/link a Pool A account for an existing Pool B
  member).
- Multi-tenant Pool B membership (same human, two tenants).

Adopt the `person_id` link concept in the data model early; build the flows later.
