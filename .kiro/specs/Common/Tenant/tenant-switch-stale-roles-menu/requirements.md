# Bugfix Requirements Document

## Introduction

In this multi-tenant React app, per-tenant authorization is the system-of-record in the
MySQL `user_tenant_roles` table. `SysAdmin` is the single global exception; every other role
(e.g. `Tenant_Admin`, `Finance_CRUD`, `STR_CRUD`, `ZZP_CRUD`, `Members_CRUD`/`Members_Read`)
is tenant-scoped. The backend `GET /api/auth/me` (`backend/src/routes/auth_routes.py`), via
the `@cognito_required()` decorator, returns the authoritative **effective** role set for the
active tenant by merging the global JWT `cognito:groups` claim with the per-tenant rows from
`user_tenant_roles`, resolved against the `X-Tenant` request header.

The frontend, however, populates `user.roles` in `AuthContext`
(`frontend/src/context/AuthContext.tsx`) only from `getCurrentUserRoles()`
(`frontend/src/services/authService.ts`), and `refreshUserRoles()` merely re-runs
`checkAuthState()`, which is only invoked on mount/login. `MainMenu`
(`frontend/src/components/MainMenu.tsx`) gates each module and admin entry on BOTH a module
flag AND a match in `user.roles`. Because `user.roles` is never re-resolved for the newly
selected tenant when the user switches tenants via the `TenantSelector` dropdown (only
`localStorage`/`currentTenant` in `frontend/src/context/TenantContext.tsx` change), the menu
keeps showing entries gated on roles the user does not hold for the new tenant, and omits
entries for tenant-scoped roles they DO hold there. A full page reload re-resolves roles for
the active tenant, which is why reload masks the defect.

Concrete report: user `peter@pgeers.nl` holds global roles `Tenant_Admin`, `SysAdmin`,
`ZZP_CRUD`, `Finance_CRUD`, `STR_CRUD`, but does NOT hold `Tenant_Admin` on tenant `h-dcn`.
After switching to `h-dcn` without a reload, the menu still shows `Tenantbeheer`
(`Tenant_Admin`) and `Systeembeheer` entries — clicking them yields "access not allowed"
(backend 403) — while the correct `h-dcn` entry `Leden Overzicht` (Members) is missing.

**Related spec:** `.kiro/specs/Common/tenant-switch-menu-refresh-fix` fixed module-flag
freshness on tenant switch but concluded "roles are global, no role refetch needed." That
conclusion is the gap that left this bug open: roles ARE tenant-scoped. This fix corrects that
assumption. The scope of this bug is **frontend only** — `GET /api/auth/me` already returns
tenant-merged roles, so no backend change is required.

## Bug Analysis

### Current Behavior (Defect)

When the active tenant is switched via the `TenantSelector` dropdown without a page reload,
`user.roles` remains the value resolved at login/mount and does not reflect the effective
(merged global + per-tenant) roles for the just-selected tenant.

1.1 WHEN the user switches the active tenant via the `TenantSelector` dropdown without a page reload THEN the system continues to gate `MainMenu` entries on the previous tenant's `user.roles` instead of the newly selected tenant's effective roles
1.2 WHEN the user switches to a tenant on which they do NOT hold a role that is only present in their global JWT groups (e.g. `Tenant_Admin` on `h-dcn`) THEN the system continues to display the menu entries gated on that role (e.g. `Tenantbeheer`/`Tenant_Admin`), and clicking them results in a backend 403 "access not allowed"
1.3 WHEN the user switches to a tenant on which they hold a tenant-scoped role that is NOT present in their global JWT groups (e.g. Members role on `h-dcn`) THEN the system fails to display the corresponding menu entry (e.g. `Leden Overzicht`)
1.4 WHEN the user switches the active tenant THEN the system does not re-invoke `GET /api/auth/me` with the newly selected tenant's `X-Tenant`, so `user.roles` is only corrected by a full page reload

### Expected Behavior (Correct)

2.1 WHEN the user switches the active tenant via the `TenantSelector` dropdown without a page reload THEN the system SHALL gate `MainMenu` entries on the newly selected tenant's effective (merged global + per-tenant) roles
2.2 WHEN the user switches to a tenant on which they do NOT hold a role present only in their global JWT groups (e.g. `Tenant_Admin` on `h-dcn`) THEN the system SHALL hide the menu entries gated on that role so that clicking a 403-yielding entry is no longer possible
2.3 WHEN the user switches to a tenant on which they hold a tenant-scoped role not present in their global JWT groups (e.g. Members role on `h-dcn`) THEN the system SHALL display the corresponding menu entry (e.g. `Leden Overzicht`)
2.4 WHEN the user switches the active tenant THEN the system SHALL re-resolve `user.roles` by calling `GET /api/auth/me` with the `X-Tenant` header set to the just-selected tenant, following the established precedent in `frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`
2.5 WHEN the role re-resolution response for the newly selected tenant is received THEN the system SHALL use the fresh response body (no stale/cached body) and reflect only that tenant's effective roles
2.6 WHEN the user performs rapid successive tenant switches THEN the system SHALL guard against out-of-order responses so that `user.roles` reflects the most recently selected tenant rather than a late-arriving response for a previously selected tenant
2.7 WHEN `SysAdmin` is present in the user's global JWT groups THEN the system SHALL keep `SysAdmin`-gated entries (e.g. `Systeembeheer`) available regardless of the active tenant, as `SysAdmin` is the single global exception
2.8 WHEN the `GET /api/auth/me` role re-resolution fails (network error or non-OK response) THEN the system SHALL fall back gracefully to the global JWT `cognito:groups` roles rather than clearing the menu or crashing

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user has only a single tenant THEN the system SHALL CONTINUE TO resolve roles and render the menu as it does today, with no behavioral change from the tenant-switch role refresh
3.2 WHEN the user logs in THEN the system SHALL CONTINUE TO resolve `user.roles` on mount/login exactly as it does today (initial `checkAuthState()` behavior preserved)
3.3 WHEN the active tenant is switched THEN the system SHALL CONTINUE TO refresh module flags (`hasFIN`, `hasSTR`, `hasZZP`, `hasMEMBERS`, `hasFunction`) per the existing `tenant-switch-menu-refresh-fix`, and SHALL CONTINUE TO honor the compound module-flag-AND-role gating in `MainMenu`
3.4 WHEN the active tenant is switched THEN the system SHALL CONTINUE TO persist the selection to `localStorage` and update `currentTenant` in `TenantContext` as it does today
3.5 WHEN the user is on a tenant where their effective roles are unchanged by the switch THEN the system SHALL CONTINUE TO display the same menu entries with no flicker-induced loss of valid entries
3.6 WHEN the App's existing module-loss redirect effect (`frontend/src/App.tsx`) applies THEN the system SHALL CONTINUE TO behave as it does today for pages the user can no longer access

## Bug Condition and Property Specification

### Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type TenantSwitchEvent { fromTenant, toTenant, globalRoles, effectiveRolesForToTenant, reloaded }
  OUTPUT: boolean

  // The bug manifests on an in-app tenant switch (no reload) where the newly
  // selected tenant's effective roles differ from the currently held user.roles.
  RETURN X.reloaded = FALSE
     AND X.effectiveRolesForToTenant <> currentUserRoles()
END FUNCTION
```

Concrete counterexample: switching from a tenant where the user holds `Tenant_Admin` to
`h-dcn` (where they do not) without a reload — `Tenantbeheer` stays visible and clicking it
returns 403, while `Leden Overzicht` is missing.

### Property: Fix Checking

```pascal
// For every in-app tenant switch that changes the effective role set,
// the resolved roles must equal the active tenant's effective roles.
FOR ALL X WHERE isBugCondition(X) DO
  result ← resolveRolesOnSwitch'(X)   // F' = fixed behavior
  ASSERT result = effectiveRolesFor(X.toTenant)          // merged global + per-tenant via /api/auth/me
     AND ('SysAdmin' IN X.globalRoles) IMPLIES ('SysAdmin' IN result)
     AND menuEntriesGatedBy(result) = expectedEntriesFor(X.toTenant)
END FOR
```

### Property: Preservation Checking

```pascal
// For all inputs that do NOT trigger the bug (single-tenant users, login/mount
// resolution, switches that do not change the effective role set), the fixed
// code behaves identically to the original.
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```

Where **F** is the original (unfixed) frontend role-resolution/menu-gating behavior and
**F'** is the fixed behavior after re-resolving roles for the active tenant on switch.
