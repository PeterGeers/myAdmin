# Requirements — Tenant switch doesn't refresh the module menu without a page reload

## Introduction

Observed 2026-09-23. When a multi-tenant user switches tenant via the `TenantSelector`
dropdown, the main menu's module gating (FIN / STR / ZZP / MEMBERS) does **not** update
immediately — a full page refresh is required before the menu reflects the newly selected
tenant's modules.

This matters for the "active tenant bounds capability" concern (s5f): a stale menu could
briefly offer **Members** for a tenant that has no MEMBERS module until the user refreshes.
This is a **UI-freshness bug, not a security hole** — the backend (SAM edge) denies the
underlying request regardless of what the stale menu offers. The fix is about correctness and
trust of the UI, not about closing an authorization gap.

**Scope: FRONTEND only.** Small, self-contained task. No backend or infrastructure change is
in scope.

### Files in scope
- `frontend/src/components/TenantSelector.tsx`
- `frontend/src/context/TenantContext.tsx`
- `frontend/src/hooks/useTenantModules.ts`
- `frontend/src/services/apiService.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/MainMenu.tsx`

### What the investigation established (baseline, not the fix)
The reactive chain is structurally correct. `TenantSelector.onChange` calls the context
setter (not a raw localStorage write); `TenantContext.setCurrentTenant` updates React state
**and** localStorage synchronously; `useTenantModules` refetches on a `[currentTenant]`
effect; `App` passes the derived flags to `MainMenu`; `MainMenu` is a plain (non-memoized)
component so it is not blocked from re-rendering. The break is therefore a **runtime/timing
or freshness** issue, not the obvious "bypasses React state" bug. Requirement 1 is the
observable defect; Requirements 2–5 pin down the specific runtime failure modes that must be
eliminated and verified.

---

## Requirement 1 — Menu reflects the new tenant without a page reload

**User story:** As a multi-tenant user, I want the module menu to update as soon as I switch
tenant in the dropdown, so that I see the correct modules for the active tenant without having
to reload the page.

#### Acceptance criteria
1. WHEN a multi-tenant user selects a different tenant in `TenantSelector` THEN the main menu's
   module gating (FIN / STR / ZZP / MEMBERS) SHALL update to reflect the newly selected
   tenant's modules WITHOUT requiring a page reload.
2. WHEN the newly selected tenant does NOT have a given module THEN that module's menu entry
   SHALL be removed from the menu after the switch completes.
3. WHEN the newly selected tenant DOES have a given module (and the user holds a matching role)
   THEN that module's menu entry SHALL appear after the switch completes.
4. WHEN the module list is being refetched after a switch THEN the menu SHALL show its existing
   loading affordance (`modulesLoading`) rather than rendering a stale-but-final menu.

---

## Requirement 2 — The module refetch targets the tenant that was just selected

**User story:** As a user switching tenants quickly, I want the modules request to always be
resolved against the tenant I just selected, so that I never see another tenant's modules due
to a race or a lagging header.

#### Acceptance criteria
1. WHEN `useTenantModules` fetches `/api/tenant/modules` after a tenant change THEN the request
   SHALL carry the tenant identifier of the CURRENT tenant at request time (the value that
   triggered the effect), not a value read independently from storage that could lag.
2. WHEN the tenant is switched multiple times in quick succession THEN the module flags
   SHALL end in a state consistent with the LAST selected tenant (no earlier-tenant response
   overwriting a later one).
3. IF a fetch for a superseded tenant resolves after a newer switch THEN its result SHALL NOT
   overwrite the module state for the current tenant.

---

## Requirement 3 — The modules response must not be served stale from cache

**User story:** As a user, I want each tenant switch to fetch fresh module data, so that a
cached response from a previous tenant is never replayed.

#### Acceptance criteria
1. WHEN `/api/tenant/modules` is requested after a tenant switch THEN the response used to
   derive the module flags SHALL correspond to the currently selected tenant and SHALL NOT be a
   cached body from a previously selected tenant.
2. WHERE the request URL is otherwise identical across tenants (the tenant travels in a request
   header, not the path) THEN the request SHALL be made in a way that prevents a browser or
   intermediary HTTP cache from replaying a prior tenant's response (e.g. no-store semantics
   and/or a request that varies per tenant).

---

## Requirement 4 — The menu re-renders on the flag change

**User story:** As a user, I want the menu component to re-render when the module flags change,
so that the DOM actually reflects the new flags.

#### Acceptance criteria
1. WHEN the module flags (`hasFIN` / `hasSTR` / `hasZZP` / `hasMEMBERS`) change value THEN the
   component tree that renders the menu SHALL re-render and reflect the new flag values.
2. IF any memoization is introduced or already present on the menu path THEN it SHALL include
   the module flags in its inputs so that a flag change is never swallowed.

---

## Requirement 5 — Role-gated entries stay consistent with the active tenant

**User story:** As a multi-tenant user whose roles differ per tenant, I want menu entries that
depend on both a module and a role to be consistent with the tenant I switched to, so the menu
is neither falsely empty nor falsely populated.

#### Acceptance criteria
1. GIVEN each module block in `MainMenu` is gated on BOTH the module flag AND a matching entry
   in `user.roles` WHEN a tenant switch changes which modules apply THEN the resulting menu
   SHALL be consistent with the active tenant's module set.
2. IF a user's effective roles are tenant-scoped and can differ between tenants THEN the design
   SHALL determine whether `user.roles` needs to be refreshed on a tenant switch, and the menu
   SHALL NOT display a module entry whose role requirement is not met for the active tenant.
3. WHERE roles do NOT vary by tenant in the current system THEN this requirement SHALL be
   satisfied by module-flag freshness alone, and the design SHALL record that finding explicitly
   rather than adding an unnecessary role refetch.

---

## Requirement 6 — No regressions to unrelated behavior

**User story:** As a user, I want the tenant-switch fix to leave the rest of the app's behavior
unchanged, so nothing else breaks.

#### Acceptance criteria
1. WHEN a single-tenant user uses the app THEN behavior SHALL be unchanged (the selector does
   not render for single-tenant users and no extra fetches SHALL be introduced for them).
2. WHEN the app initializes THEN tenant restoration from `localStorage` (`selectedTenant`) and
   the `[user]`-keyed init effect SHALL continue to work as before.
3. WHEN the `X-Tenant` header is used by other authenticated requests THEN those requests SHALL
   continue to resolve the tenant as they do today (the fix SHALL NOT change tenant resolution
   for unrelated calls in a breaking way).
4. WHEN the existing "redirect to menu on module-access loss" effect in `App.tsx` runs after a
   switch THEN it SHALL continue to redirect a user off a page they no longer have access to.

---

## Out of scope
- Any backend change to `/api/tenant/modules` or SAM edge authorization.
- Changing the source of truth for tenant selection away from `TenantContext` + `localStorage`.
- Broader caching strategy for other endpoints beyond what Requirement 3 needs.
