# Per-Tenant Roles — Tasks

**Status:** Ready for Implementation  
**Approach:** Option B1 — Database + In-Memory Cache  
**Branch:** `feature/per-tenant-roles`

---

## Phase 1: Database & Cache Foundation (1 day)

- [x] 1.1 Create SQL migration `backend/src/migrations/create_user_tenant_roles.sql` with the `user_tenant_roles` table (schema from design.md)
- [x] 1.2 Run migration against test database, verify table created with correct indexes and FK
- [x] 1.3 Create `backend/src/auth/role_cache.py` — in-memory cache with 5-min TTL, `get_tenant_roles()` and `invalidate_cache()` functions
- [x] 1.4 Write unit tests for role_cache: cache hit, cache miss, TTL expiry, invalidation
- [x] 1.5 Run `pytest tests/unit/` — all existing + new tests pass
- [x] 1.6 Git commit: `feat(per-tenant-roles): Phase 1 — user_tenant_roles table + role cache`

## Phase 2: Decorator Change (1 day)

- [x] 2.1 Modify `cognito_required` in `backend/src/auth/cognito_utils.py`:
  - After `extract_user_credentials`, split roles into global (`SysAdmin`, `Administrators`, `System_CRUD`) from JWT and per-tenant from DB via cache
  - Use `get_current_tenant(request)` from `tenant_context.py` to resolve current tenant
  - Merge global + per-tenant roles into `user_roles`
- [x] 2.2 Unit test: user with `SysAdmin` in JWT keeps it regardless of tenant
- [x] 2.3 Unit test: user gets per-tenant roles from DB for current tenant
- [x] 2.4 Unit test: user with roles in TenantA does NOT get those roles when requesting TenantB
- [x] 2.5 Verify `ROLE_PERMISSIONS` mapping still works unchanged with merged role list
- [x] 2.6 Run `pytest tests/unit/` — all existing + new tests pass (989 passed)
- [x] 2.7 Git commit: `feat(per-tenant-roles): Phase 2 — decorator reads per-tenant roles from DB`

## Phase 3: Tenant Admin Routes — Role Management (1-2 days)

- [x] 3.1 Update `assign_user_group()` in `tenant_admin_users.py` to INSERT into `user_tenant_roles` + invalidate cache (instead of / in addition to Cognito group)
- [x] 3.2 Update `remove_user_group()` to DELETE from `user_tenant_roles` + invalidate cache
- [x] 3.3 Update `create_tenant_user()` to write selected roles to `user_tenant_roles` on user creation
- [x] 3.4 Update `delete_tenant_user()` to DELETE all roles from `user_tenant_roles` for that user+tenant + invalidate cache
- [x] 3.5 Update `list_tenant_users()` to read roles from `user_tenant_roles` instead of (or merged with) Cognito groups
- [x] 3.6 Update `get_available_roles()` to work with the DB-based model
- [x] 3.7 API test: assign Finance_CRUD to user in TenantA → user has it in TenantA, not in TenantB
- [x] 3.8 API test: remove role → cache invalidated, next request reflects change
- [x] 3.9 API test: delete user from tenant → all role entries cleaned up

## Phase 4: Frontend Changes (0.5-1 day)

- [x] 4.1 Update `UserManagement.tsx` — role display should come from API response (already does for list), verify no JWT-based role reading for per-tenant roles
- [x] 4.2 Verify Tenant Admin panel visibility: check DB for `Tenant_Admin` role in current tenant via API, not just JWT
- [x] 4.3 Verify SysAdmin panel visibility still works from JWT `cognito:groups` (no change needed)
- [x] 4.4 Test: user who is Tenant_Admin in TenantA but not TenantB sees admin panel only for TenantA

## Phase 5: Integration Testing (0.5 day)

- [x] 5.1 End-to-end test in Docker: create user → assign per-tenant roles → verify access → switch tenant → verify different access
- [x] 5.2 Test cache behavior under load: multiple requests within TTL window use cached roles
- [x] 5.3 Verify audit logging captures role changes

## Phase 6: Migration & Cleanup (0.5-1 day)

- [x] 6.1 Create `backend/scripts/migrate_roles_to_db.py`:
  - For each Cognito user, get their groups and tenants
  - For each non-global group × tenant combination, INSERT into `user_tenant_roles`
  - Skip global roles (`SysAdmin`, `Administrators`, `System_CRUD`)
  - Log all insertions for audit
  - Support dry-run mode (`--dry-run` flag)
- [x] 6.2 Test migration against test database with known users, verify correct row count
- [x] 6.3 Test idempotency — running migration twice should not fail (UNIQUE constraint handles duplicates)
- [x] 6.4 Run migration against production databases (Docker + Railway)
- [x] 6.5 Update design.md status to "Complete"
- [x] 6.6 Document the migration steps in `backend/docs/guides/` (how to run migration)
- [x] 6.7 Decide on Cognito group cleanup — leave per-tenant groups in place (harmless, serve as fallback)
- [ ] 6.8 Git commit: `feat(per-tenant-roles): Phase 6 — migration + cleanup`
- [ ] 6.9 Merge `feature/per-tenant-roles` into `main`

---

**Total estimate:** 5-6 days

**Dependencies:**

- Phase 2 depends on Phase 1 (cache must exist before decorator uses it)
- Phase 3 depends on Phase 1 (table must exist before routes write to it)
- Phase 4 depends on Phase 3 (API must return DB-based roles)
- Phase 5 depends on Phases 2-4
- Phase 6 depends on Phase 5 (migration runs after everything is tested)
