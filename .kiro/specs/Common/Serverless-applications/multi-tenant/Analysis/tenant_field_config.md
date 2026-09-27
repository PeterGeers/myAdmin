# Tenant-Specific Field Configuration — Best Approach per Option

> Companion to `first_thoughts.md` and `rewrite_vs_refactor.md`. This document
> defines how to support tenant-specific table fields under each multi-tenancy
> model: **Option A (silo / stack-per-tenant)** and **Option B (pooled / shared
> tables with a tenant key)**. Analysis only — no application code has been
> changed.

## Background: the existing field registry

Each DynamoDB table has a Field Registry that is the single source of truth for
field names, types, validation, and permissions (per the schema-driven rule).
Today these registries are static, compile-time objects in code:

- `frontend/src/config/memberFields/` (assembled `MEMBER_FIELDS` from group
  partials: personal, address, membership, motor, financial, administrative)
- `frontend/src/config/productFields/`, `eventFields/`, `orderFields/`

The `FieldDefinition` interface (`memberFields/types.ts`) already carries `key`,
`dataType`, `inputType`, `group`, `validation`, `permissions`, and UI/display
metadata. Any tenant-field design MUST extend this registry, not replace it, so
the "never invent new field names" and "validation lives in the registry" rules
still hold.

## Shared design core (applies to both options)

Regardless of tenancy model, the same conceptual model is used:

**Base registry + tenant overlay → resolved registry.**

- **Base fields** stay in code — the shared, stable fields the platform depends
  on (`member_id`, `tenant_id`, status, financial fields). Some are marked
  `platformCritical` and can never be hidden or renamed by a tenant.
- **Tenant overlay** can (a) add custom fields, (b) hide non-critical base
  fields, (c) override presentation/validation of base fields.
- **Resolver** merges them into the registry a component actually consumes.
  Components only ever see the resolved registry, so where the overlay is
  *stored* can change later without touching consumers.

### Type additions (shared)

```typescript
// memberFields/types.ts — additions
export interface FieldDefinition {
  // ...existing fields...
  origin?: 'base' | 'tenant';   // set by the resolver, not authored
  platformCritical?: boolean;   // base field a tenant may NOT hide/override
  tenantScoped?: boolean;       // custom field, stored under a namespace
}

export interface TenantFieldOverlay {
  tenantId: string;
  table: 'Members' | 'Producten' | 'Events' | 'Orders';
  version: number;              // bump on change; enables cache invalidation
  addFields?: Record<string, FieldDefinition>;
  hideFields?: string[];        // base keys to hide (non-critical only)
  overrideFields?: Record<string, Partial<FieldDefinition>>;
}
```

### Resolver (shared, pure)

```typescript
export function resolveFields(
  base: Record<string, FieldDefinition>,
  overlay?: TenantFieldOverlay
): Record<string, FieldDefinition> {
  if (!overlay) return base;
  const result: Record<string, FieldDefinition> = {};

  for (const [key, def] of Object.entries(base)) {
    if (overlay.hideFields?.includes(key)) {
      if (def.platformCritical) {
        throw new Error(
          `Tenant ${overlay.tenantId} cannot hide platform-critical field "${key}"`
        );
      }
      continue;
    }
    const override = overlay.overrideFields?.[key];
    result[key] = { ...def, ...(override ?? {}), origin: 'base' };
  }

  for (const [key, def] of Object.entries(overlay.addFields ?? {})) {
    if (key in base) {
      throw new Error(`Tenant field "${key}" collides with a base field`);
    }
    result[key] = { ...def, origin: 'tenant', tenantScoped: true };
  }
  return result;
}
```

The backend re-implements the same rules in Python against the same overlay
data. The frontend is NEVER trusted to define which fields exist — it only
renders the resolved registry.

---

## Option A — Silo / stack-per-tenant

Each tenant gets its own SAM stack, its own Cognito pool, its own DynamoDB
tables, and its own frontend build. There is no `tenant_id` on records — each
deployment stays effectively single-tenant.

### Best approach: overlay in code, selected at build/deploy time

- **Base registry**: unchanged, in code (shared across all tenant builds).
- **Tenant overlay**: authored in code, one folder per tenant:

  ```
  frontend/src/config/tenants/<tenantId>/
    ├── memberFields.overlay.ts
    ├── productFields.overlay.ts
    └── branding.ts        // logo, org name, colors, emails
  ```

- **Selection**: the active tenant is fixed at build time via an env var
  (e.g. `REACT_APP_TENANT_ID`), consistent with the current build-time config
  model (buckets, pool IDs already come from CI env vars). The build imports the
  matching overlay and resolves it against the base registry once.
- **Backend**: the overlay for that tenant ships in the stack (a Python module
  or a JSON asset in the auth layer), selected by a stack parameter. Handlers
  resolve fields against it the same way.

### Storage of custom field values

Because tables are per-tenant, there is more freedom, but **still store tenant
custom fields under a single reserved `custom_fields` Map attribute** rather than
as free-floating top-level attributes. This keeps `UPDATABLE_FIELDS` whitelists
closed, keeps validation enforceable, and — critically — keeps the item shape
identical to Option B so a future silo→pooled migration is mechanical.

### Why this fits Option A

- No runtime config fetch; overlays are type-checked and reviewed in git.
- Matches the existing build-time-config reality (no new infra).
- Strong isolation "for free" — a tenant literally cannot see another's config
  because it is not in their build or their stack.

### Tradeoffs

- Adding a tenant or changing a field requires a deploy of that tenant's stack.
- N stacks to build/monitor/migrate (the known operational cost of silo).
- Config drift risk across stacks — mitigate by keeping the base registry the
  single shared source and overlays small.

### Definition-of-done additions (Option A)

- Overlay files type-check (`npx tsc --noEmit`) and pass ESLint.
- Resolver unit + property tests cover collision, hide-critical, and override.
- Translations for tenant field labels exist in all 8 locales (per i18n rule).
- No hardcoded fallbacks — tenant selection env var throws if missing (guardrail:
  no dangerous fallbacks).

---

## Option B — Pooled / shared tables with a tenant key

All tenants share the same tables. Every record carries `tenant_id`
(`PK = tenant_id`, `SK = <existing id>`). Tenant config is resolved per request
from the caller's verified tenant claim.

### Best approach: overlay in a `TenantConfig` DynamoDB table, loaded at runtime

- **Base registry**: unchanged, in code (shared by all tenants).
- **Tenant overlay**: stored as data, not code, so tenants can be added/edited
  without a deploy:

  ```
  TenantConfig table
    PK = tenant_id
    SK = "fields#<table>"     e.g. "fields#Members"
    attributes: version, addFields (Map), hideFields (List),
                overrideFields (Map), branding (Map)
  ```

- **Resolution flow (per request)**:
  1. Backend derives `tenant_id` from the **verified** JWT claim (see
     prerequisite below) — never from a client header.
  2. Loads the tenant's overlay for the table (cached in Lambda memory keyed by
     `tenant_id + version`; invalidated when `version` bumps).
  3. Resolves base + overlay, validates the request body against the resolved
     registry, then reads/writes with `tenant_id` in the key.
  - Frontend fetches the resolved registry + branding from an API endpoint on
    login and renders from it.

### Storage of custom field values (mandatory here)

Tenant custom fields MUST live under a single reserved `custom_fields` Map
attribute on the shared item — never as top-level attributes:

```
Members item:
  { tenant_id, member_id, ...base attributes..., custom_fields: { <key>: value } }
```

- Base attributes stay a stable, closed set that platform code and IAM policies
  rely on.
- Tenant extensibility is contained in one namespaced attribute — no cross-tenant
  attribute-name collisions, no schema surprises.
- Backend validation: base fields validate against base `UPDATABLE_FIELDS`;
  `custom_fields` entries validate against that tenant's overlay. Financial-field
  rules (Number type, `Decimal` coercion) still apply per `dataType`.
- `custom_fields` is an optional Map → follows the existing DynamoDB REMOVE
  pattern (empty/null → REMOVE, not SET).

### Isolation

- **Key-level**: every query/update is scoped by `tenant_id` partition key —
  replaces today's full-table `scan()` + in-memory `regio` filter (cheaper and
  safer).
- **IAM-level (defense in depth)**: use `dynamodb:LeadingKeys` conditions so a
  policy restricts items to the caller's tenant partition, enforced by AWS, not
  just app code.
- **Cognito groups**: tenant-scope the group namespace (e.g. prefix or
  custom claim) so roles cannot collide across tenants.

### Why this fits Option B

- Add a tenant / change fields with no deploy — required for self-service SaaS.
- On-demand DynamoDB cost with no per-tenant floor (per `rewrite_vs_refactor.md`,
  "Multi-tenancy on DynamoDB").
- One codebase and one stack to operate.

### Tradeoffs

- Config is now runtime data → needs write-time validation, versioning, and
  caching (all specified above).
- Tenant isolation is enforced in code + IAM rather than by physical separation —
  correctness is critical (see prerequisite).

### Definition-of-done additions (Option B)

- `TenantConfig` table added to the field-registry system (`tenantConfigFields/`)
  and documented as a registry.
- Overlay write path validates: types, no base-key collision, no hiding
  `platformCritical`, financial fields numeric. Rejects invalid overlays with 400.
- Migration script (per migration rule, `--dry-run` + `--profile`) to add
  `tenant_id` to existing records and move any ad-hoc fields into `custom_fields`.
- Lambda overlay cache keyed on `tenant_id + version`; verified to invalidate on
  version bump.
- Translations for tenant field labels in all 8 locales.

---

## Hard prerequisite for Option B (and any pooled model)

Fix the auth layer first. `extract_user_credentials` currently base64-decodes the
JWT without signature verification and trusts a client-supplied
`X-Enhanced-Groups` header for group membership (see `first_thoughts.md` §1). In a
pooled model, `tenant_id` and roles come from the token, so a spoofed claim is a
cross-tenant data breach. Before pooling:

1. Verify the JWT signature against the Cognito pool JWKS.
2. Drop trust in `X-Enhanced-Groups`; read groups only from the verified token.
3. Derive `tenant_id` only from a verified claim.

Option A does not strictly require this fix for isolation (separation is
physical), but the fix is good hygiene regardless.

## Recommendation

- **2-5 known orgs** → Option A: overlay-in-code per tenant, values under
  `custom_fields`. Smallest, safest change; keeps registry discipline; item shape
  matches Option B for a clean future migration.
- **Self-service SaaS** → Option B: overlay in a `TenantConfig` table, values
  under `custom_fields`, key + IAM isolation — after the auth-layer fix.

In both cases the base registry stays the shared source of truth, the resolver is
the single merge point, and custom values are namespaced under `custom_fields`.
Designing Option A's item shape to match Option B means the storage layer does not
have to change if the tenancy model is upgraded later.
