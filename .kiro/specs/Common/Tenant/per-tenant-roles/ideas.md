# Per-Tenant Roles — Ideas & Analysis

## Problem

A user with access to multiple tenants has the same permissions (read, CRUD, export) across all of them. It's not possible to give a user read-only access to TenantA and full CRUD access to TenantB.

## Current Model

Cognito groups are global to the user pool. When a user is added to a group like `Finance_CRUD`, that role applies to every tenant in their `custom:tenants` list.

```
User: peter@example.com
  custom:tenants: ["GoodwinSolutions", "PeterPrive"]
  Groups: [Finance_CRUD, STR_Read]
  → Finance_CRUD applies to BOTH tenants
  → STR_Read applies to BOTH tenants
```

## Desired Model

```
User: peter@example.com
  GoodwinSolutions: [Finance_CRUD, STR_CRUD]
  PeterPrive: [Finance_Read]
```

## Why Cognito Can't Do This Natively

Cognito groups are flat — a user is either in a group or not. There's no concept of "in group X for tenant Y." The `custom:tenants` attribute is a simple JSON array with no role mapping.

## Options

### Option A: Tenant-prefixed groups (simplest, Cognito-only)

Create groups like `GoodwinSolutions_Finance_CRUD`, `PeterPrive_Finance_Read`. The backend checks if the user is in the group matching `{currentTenant}_{permission}`.

- Pro: stays in Cognito, no database changes, works with existing JWT flow
- Con: group explosion (tenants × roles), harder to manage in Cognito console, group names get long

### Option B: Store roles in the database (most flexible)

Create a `user_tenant_roles` table:

```sql
user_tenant_roles:
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  administration VARCHAR(50) NOT NULL,
  role VARCHAR(100) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  created_by VARCHAR(255),
  UNIQUE KEY uk_user_tenant_role (email, administration, role)
```

Backend checks this table instead of (or in addition to) Cognito groups. Cognito still handles authentication, but authorization is database-driven.

- Pro: fully flexible, easy to query, supports any role model, standard SQL
- Con: requires changes to `@cognito_required` decorator and all permission checks, roles no longer in the JWT token (need DB lookup per request or cache)

#### B1: In-memory cache on the backend

After the first DB lookup, cache the user's per-tenant roles in a Python dict (keyed by `email:tenant`) with a short TTL (e.g., 5 minutes). The `@cognito_required` decorator checks the cache first, only hits the DB on cache miss or expiry. Invalidate the cache entry when a Tenant Admin changes roles.

- Performance: one DB query per user per 5 minutes. Effectively zero overhead.
- Role change delay: takes effect within 5 minutes (or immediately if cache is invalidated on role change).
- Complexity: low — a simple dict with TTL, ~30 lines of code.
- Trade-off: roles live in two places (DB + cache), but the cache is just a performance layer, not a source of truth.

#### B2: Roles in the JWT token (via Cognito attribute)

When a Tenant Admin changes roles, update a Cognito custom attribute (e.g., `custom:tenant_roles`) with the per-tenant role map. This attribute is included in the JWT token on next login or token refresh.

- Performance: zero DB lookups — roles come from the JWT, same as today.
- Role change delay: up to 60 minutes (current access token validity) for users who are already logged in. Immediate if the user logs out and back in, or if the frontend forces a token refresh after a role change notification.
- Complexity: medium — need to update Cognito attributes on every role change, parse the JSON from the JWT, and handle the 2048-char limit (same constraint as Option C).
- Trade-off: inherits Option C's character limit problem. Works at current scale but doesn't scale to many tenants/roles. Also, role changes are not instant for active sessions.

#### Recommendation

B1 (in-memory cache) is the better sub-option. It has no character limits, role changes propagate within minutes, and the implementation is simpler. B2 reintroduces the 2048-char constraint from Option C and adds the stale-token problem.

### Option C: Encode roles in custom:tenants attribute (no new infrastructure)

Change `custom:tenants` from a simple list to a role map:

```json
{
  "GoodwinSolutions": ["Finance_CRUD", "STR_CRUD"],
  "PeterPrive": ["Finance_Read"]
}
```

The backend parses this on each request to determine per-tenant permissions.

- Pro: no new tables, no new groups, stays in Cognito attributes
- Con: Cognito custom attributes have a 2048-character limit — could be tight with many tenants/roles. Requires changes to the `@cognito_required` decorator. JWT token includes this attribute (visible to frontend).

### Option D: Hybrid — Cognito for auth, database for per-tenant roles

Keep Cognito groups for "global" roles (SysAdmin, Tenant_Admin) and use a database table for per-tenant fine-grained permissions.

- Pro: minimal Cognito changes, SysAdmin/Tenant_Admin stay simple, per-tenant roles are flexible
- Con: two sources of truth for permissions

## Impact Assessment

### Code that needs to change (any option)

1. `backend/src/auth/cognito_utils.py` — `@cognito_required` decorator: currently reads groups from JWT token. Needs to resolve per-tenant permissions.
2. `backend/src/auth/tenant_context.py` — `@tenant_required` decorator: could be extended to inject per-tenant roles.
3. `backend/src/routes/tenant_admin_users.py` — user creation/deletion: needs to manage per-tenant role assignments instead of global groups.
4. `backend/src/services/cognito_service.py` — `assign_role`, `remove_role`, `list_user_groups`: need per-tenant variants.
5. `frontend/src/context/AuthContext` or equivalent — role-based UI rendering needs to be tenant-aware.
6. All route handlers using `@cognito_required(required_permissions=[...])` — no changes needed if the decorator is updated to resolve per-tenant roles transparently.

### Migration

Existing users need their current global roles mapped to per-tenant roles. Since all current users have the same roles across all their tenants, the migration is straightforward:

- For each user, for each tenant in their `custom:tenants`, create a role entry with their current groups.

## Recommendation

Option B with sub-option B1 (database + in-memory cache) is the best path forward:

- No character limits (unlike C and B2)
- Role changes propagate within minutes without user action
- Simple implementation (~30 lines for the cache, one new table, decorator update)
- Scales to any number of tenants and roles
- Standard SQL — easy to query, audit, and migrate

Option C works at current scale (3 tenants) but is a dead end. Option B2 reintroduces the same 2048-char limit. Option A (tenant-prefixed groups) creates group explosion in Cognito.

Only `SysAdmin` stays as a global Cognito group. `Tenant_Admin` moves to the DB alongside all other per-tenant roles — a user can be admin of TenantA but a regular user in TenantB.

## Decision Needed

- Which option to pursue
- Whether to keep backward compatibility with the current global groups model during transition
- Whether SysAdmin and Tenant_Admin roles should remain global (they arguably should — a SysAdmin is a SysAdmin everywhere)

## Status

🔵 Ideas phase — not yet started
