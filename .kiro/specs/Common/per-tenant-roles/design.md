# Per-Tenant Roles — Technical Design

**Status:** Complete
**Date:** 2026-04-08
**Approach:** Option B1 — Database + In-Memory Cache
**Branch:** `feature/per-tenant-roles`

---

## Architecture Overview

```
Current:
  JWT token → cognito:groups [Finance_CRUD, STR_Read] → applies to ALL tenants

Target:
  JWT token → authentication only (who is this user?)
  DB table  → per-tenant authorization (what can they do in THIS tenant?)
  Cache     → avoid DB lookup on every request (5-min TTL)

  Global roles (SysAdmin) stay in Cognito groups — unchanged.
  Per-tenant roles (Tenant_Admin, Finance_CRUD, STR_Read, etc.) move to user_tenant_roles table.
```

## Database Schema

**New table:** `user_tenant_roles`

```sql
CREATE TABLE IF NOT EXISTS user_tenant_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    administration VARCHAR(50) NOT NULL,
    role VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    UNIQUE KEY uk_user_tenant_role (email, administration, role),
    INDEX idx_email (email),
    INDEX idx_administration (administration),
    FOREIGN KEY (administration) REFERENCES tenants(administration)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## In-Memory Role Cache

**File:** `backend/src/auth/role_cache.py`

```python
import time
from typing import Dict, List, Tuple

CACHE_TTL_SECONDS = 300  # 5 minutes
_role_cache: Dict[str, Tuple[List[str], float]] = {}

def get_tenant_roles(email: str, tenant: str, db) -> List[str]:
    key = f"{email}:{tenant}"
    now = time.time()
    if key in _role_cache:
        roles, ts = _role_cache[key]
        if now - ts < CACHE_TTL_SECONDS:
            return roles
    rows = db.execute_query(
        "SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s",
        (email, tenant), fetch=True
    )
    roles = [r['role'] if isinstance(r, dict) else r[0] for r in (rows or [])]
    _role_cache[key] = (roles, now)
    return roles

def invalidate_cache(email: str, tenant: str):
    _role_cache.pop(f"{email}:{tenant}", None)
```

## Changes to `@cognito_required` Decorator

**File:** `backend/src/auth/cognito_utils.py`

The decorator currently reads roles from `cognito:groups` in the JWT. The change:

1. Global roles (`SysAdmin`) still come from JWT — no change
2. Per-tenant roles (`Tenant_Admin`, `Finance_CRUD`, `STR_Read`, etc.) come from the DB via cache
3. The combined list is passed to the route as `user_roles` — existing routes don't need changes

```python
# In the decorated_function, after extracting user_email and user_roles from JWT:

# Global roles from JWT (SysAdmin only)
global_roles = [r for r in user_roles if r in ('SysAdmin', 'Administrators', 'System_CRUD')]

# Per-tenant roles from DB
tenant = get_current_tenant(request)
if tenant:
    tenant_roles = get_tenant_roles(user_email, tenant, db)
else:
    tenant_roles = []

# Merge: global + per-tenant
user_roles = list(set(global_roles + tenant_roles))
```

The `ROLE_PERMISSIONS` mapping stays unchanged — it still maps role names to permission lists. The only difference is where the role names come from.

## Changes to Tenant Admin User Management

**File:** `backend/src/routes/tenant_admin_users.py`

### Create user — assign per-tenant roles

When a Tenant Admin creates a user and assigns roles, write to `user_tenant_roles` instead of (or in addition to) Cognito groups:

```python
for role in selected_roles:
    db.execute_query(
        """INSERT INTO user_tenant_roles (email, administration, role, created_by)
           VALUES (%s, %s, %s, %s)""",
        (email, tenant, role, user_email), fetch=False, commit=True
    )
```

### Assign/remove role

Update `assign_user_group` and `remove_user_group` to write to the DB table and invalidate the cache:

```python
from auth.role_cache import invalidate_cache
# After inserting/deleting the role:
invalidate_cache(username, tenant)
```

### Delete user from tenant

`delete_tenant_user` already delegates to `cognito_service.remove_tenant_from_user()`. Add cleanup:

```python
db.execute_query(
    "DELETE FROM user_tenant_roles WHERE email = %s AND administration = %s",
    (email, tenant), fetch=False, commit=True
)
invalidate_cache(email, tenant)
```

## Migration Strategy

### Data migration

Existing users have global Cognito groups. The migration creates per-tenant role entries for each user × tenant combination:

```
Example: peter@pgeers.nl in groups [Tenant_Admin, Finance_CRUD, STR_Read], tenants [GoodwinSolutions, PeterPrive]
Creates 6 rows:
  peter@pgeers.nl | GoodwinSolutions | Tenant_Admin
  peter@pgeers.nl | GoodwinSolutions | Finance_CRUD
  peter@pgeers.nl | GoodwinSolutions | STR_Read
  peter@pgeers.nl | PeterPrive       | Tenant_Admin
  peter@pgeers.nl | PeterPrive       | Finance_CRUD
  peter@pgeers.nl | PeterPrive       | STR_Read
```

This preserves the current behavior — every user keeps the same roles they have today, just stored per-tenant.

### Rollback plan

If something goes wrong after migration: delete all rows from `user_tenant_roles` and revert the decorator change. The old Cognito groups are still in place and will work as before.

### Cognito group cleanup (post-migration)

After migration and testing, the per-tenant Cognito groups (`Finance_CRUD`, `STR_Read`, etc.) can be left in place or removed. They're no longer used for authorization but don't cause harm.

## Frontend Changes

### Tenant Admin — User Management

**File:** `frontend/src/components/TenantAdmin/UserManagement.tsx`

The role assignment UI stays the same — the Tenant Admin still picks roles from a dropdown. The API calls now write to the DB table instead of Cognito groups. The frontend doesn't need to know the difference.

### Role display

The frontend currently reads `cognito:groups` from the JWT to show the user's roles. After migration, per-tenant roles (including `Tenant_Admin`) come from the API (which reads from DB). The JWT still contains `SysAdmin` for UI routing decisions (show/hide SysAdmin panel). The Tenant Admin panel visibility is determined by checking the DB for `Tenant_Admin` role in the current tenant.

## API Changes

No new endpoints needed. Existing endpoints change behavior internally:

| Endpoint                                             | Current                               | After                                                |
| ---------------------------------------------------- | ------------------------------------- | ---------------------------------------------------- |
| `POST /api/tenant-admin/users`                       | Creates Cognito user + adds to groups | Creates user + inserts into `user_tenant_roles`      |
| `POST /api/tenant-admin/users/<id>/groups`           | Adds to Cognito group                 | Inserts into `user_tenant_roles` + invalidates cache |
| `DELETE /api/tenant-admin/users/<id>/groups/<group>` | Removes from Cognito group            | Deletes from `user_tenant_roles` + invalidates cache |
| `DELETE /api/tenant-admin/users/<id>`                | Removes tenant or deletes user        | Also deletes from `user_tenant_roles`                |
| `GET /api/tenant-admin/users`                        | Lists users with Cognito groups       | Lists users with roles from `user_tenant_roles`      |

## Security Considerations

- Per-tenant roles are enforced server-side in the `@cognito_required` decorator — the frontend cannot bypass them
- The `user_tenant_roles` table uses `administration` as FK to `tenants` — prevents orphaned entries
- Cache invalidation happens synchronously when roles change — no stale permissions window
- SysAdmin remains in Cognito groups — the only truly global role, cannot be tampered with via the DB
- Tenant_Admin is per-tenant — a user can be admin of TenantA but a regular user in TenantB

## Testing Plan

1. **Migration script** — run against test DB, verify all existing users get correct per-tenant entries
2. **Decorator** — unit test that per-tenant roles resolve correctly, cache works, fallback works
3. **Role assignment** — assign Finance_CRUD to user in TenantA, verify they have it in TenantA but not TenantB
4. **Tenant_Admin per-tenant** — assign Tenant_Admin to user in TenantA only, verify they can't admin TenantB
5. **Role removal** — remove role, verify cache invalidated and next request reflects the change
6. **User deletion** — delete user from tenant, verify role entries cleaned up
7. **Rollback** — verify reverting to Cognito groups works after deleting DB entries

## File Summary

| File                                                     | Change                                         |
| -------------------------------------------------------- | ---------------------------------------------- |
| `backend/src/migrations/create_user_tenant_roles.sql`    | New table                                      |
| `backend/src/auth/role_cache.py`                         | New — in-memory cache                          |
| `backend/src/auth/cognito_utils.py`                      | Decorator reads per-tenant roles from cache/DB |
| `backend/src/routes/tenant_admin_users.py`               | Write roles to DB instead of Cognito groups    |
| `backend/src/services/cognito_service.py`                | Optional — add role DB methods                 |
| `backend/scripts/migrate_roles_to_db.py`                 | New — one-time migration script                |
| `frontend/src/components/TenantAdmin/UserManagement.tsx` | Minor — role display from API instead of JWT   |

## Git Workflow

1. Create branch `feature/per-tenant-roles` from `main`
2. Implement in phases (see tasks.md)
3. Test in Docker with both databases
4. Merge to `main` after successful testing
