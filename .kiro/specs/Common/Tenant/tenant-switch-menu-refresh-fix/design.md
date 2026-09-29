# Design — Tenant switch doesn't refresh the module menu without a page reload

## 1. Summary

The tenant-switch → module-menu chain is wired correctly in principle: state flows through
React context, the modules hook refetches on a `[currentTenant]` effect, and the menu component
is not memoized. Yet the menu only updates after a full page reload. This design pins the defect
to **request-freshness**, not to broken React wiring, and fixes it by (a) making the module
refetch carry the just-selected tenant explicitly, (b) preventing a stale cached response from
being replayed, and (c) guarding against out-of-order responses. It also resolves the open
question of whether roles must be refreshed on a switch, so the compound module+role gating in
`MainMenu` cannot look stale.

## 2. Current behavior (as-is, verified in code)

The chain, file by file (all under `frontend/src/`):

1. **`components/TenantSelector.tsx`** — `onChange={(e) => setCurrentTenant(e.target.value)}`.
   Calls the context setter with the raw option value. Renders only for multi-tenant users.
   *No defect here.*

2. **`context/TenantContext.tsx`** — `setCurrentTenant(tenant)` runs synchronously:
   ```
   setCurrentTenantState(tenant);                     // React state
   localStorage.setItem('selectedTenant', tenant);    // persistence
   ```
   guarded by `availableTenants.includes(tenant)`. The init effect is keyed on `[user]` only
   (correct — it must not re-run on every switch). State and storage are updated together, so
   there is no "state updated but storage didn't" bug.

3. **`hooks/useTenantModules.ts`** — reads `const { currentTenant } = useTenant()`. The fetch
   effect has deps `[currentTenant]`, so it *does* re-run on a switch. It calls
   `authenticatedGet('/api/tenant/modules')` **without** passing a `tenant` option, parses
   `available_modules`, and derives `hasFIN/hasSTR/hasZZP/hasMEMBERS` from the `modules` array.
   *There is no caching in the hook and no cache-busting on the request, and no explicit tenant
   is passed to the request layer.*

4. **`services/apiService.ts`** — `authenticatedRequest` resolves the header at request time:
   ```
   const currentTenant = tenant || getCurrentTenant();   // getCurrentTenant() = localStorage.getItem('selectedTenant')
   if (currentTenant) headers['X-Tenant'] = currentTenant;
   ```
   The URL is identical for every tenant (`/api/tenant/modules`); the tenant is carried **only**
   in the `X-Tenant` request header. The GET is issued with `credentials: 'include'` but with no
   `cache: 'no-store'`. The 401-retry path repeats the same header resolution.

5. **`App.tsx`** — `const { hasFIN, hasSTR, hasZZP, hasMEMBERS, loading: modulesLoading } =
   useTenantModules();` then passes those as plain props to `<MainMenu ... />`. Also runs a
   redirect effect keyed on `[hasSTR, hasFIN, hasZZP, modulesLoading, isAuthenticated,
   currentPage]` that bounces the user to the menu when they lose access to the current page's
   module — confirming the flags are meant to change live.

6. **`components/MainMenu.tsx`** — a **plain function component** (not `React.memo`). Each module
   block is gated on BOTH the flag AND a role match, e.g.
   `{hasFIN && user?.roles?.some(r => ['Finance_CRUD','Finance_Read','Finance_Export'].includes(r)) && (...)}`.
   Same pattern for STR (`STR_CRUD/Read/Export`), ZZP (`ZZP_Read/CRUD`), MEMBERS
   (`Members_Read/CRUD`).

7. **`context/AuthContext.tsx`** — `user.roles` is populated by `checkAuthState()` (from Cognito
   via `getCurrentUserRoles()`). `refreshUserRoles()` just calls `checkAuthState()` and is only
   invoked on login. **Roles are not refreshed on a tenant switch.**

## 3. Root-cause analysis

The React reactivity is sound (state changes, effect deps are correct, the menu is not
memoized), so "the refetch never fires" and "the component can't re-render" are unlikely. The
failure is that the refetch **resolves against stale data**. Ranked by likelihood:

### Cause A (primary): stale response served from cache
`/api/tenant/modules` is requested with a URL that is identical for every tenant — the tenant
lives only in the `X-Tenant` header. The GET has no `cache: 'no-store'` and no per-tenant
variation in the URL. A browser HTTP cache or any intermediary keyed on URL (ignoring the
custom header) can replay the **previous** tenant's response body. After a hard reload the
cache/entry state differs, which is exactly why "reload fixes it." This is the most consistent
explanation for a reload-only fix.

### Cause B (secondary): tenant carried implicitly via localStorage timing
The hook does not pass `{ tenant: currentTenant }`; the header is derived from
`getCurrentTenant()` (a localStorage read) at `fetch` time. In the common path localStorage is
written synchronously before the effect runs, so the header is usually correct — but relying on
an out-of-band read instead of the value that triggered the effect is fragile and makes the
request layer's tenant potentially disagree with the React state that drove the fetch. Passing
the tenant explicitly removes this ambiguity and is a precondition for Cause C.

### Cause C (ordering): out-of-order responses
With rapid switching, an earlier tenant's slow response can resolve after a later switch and
overwrite `modules` with stale data. The hook has no request-supersession guard.

### Cause D (compound gating): roles not refreshed on switch
Even with correct flags, each `MainMenu` block also requires a matching `user.roles` entry.
`user.roles` is not refreshed on a tenant switch. **Whether this actually causes staleness
depends on whether roles are tenant-scoped in this system** — an open question resolved in
§6. If roles are global, this is a no-op; if tenant-scoped, the menu can look stale/empty even
when flags update.

Re-render is **not** the cause: `MainMenu` is a plain component and `App` consumes the hook
directly, so a flag change propagates.

## 4. Design goals

- Make the module refetch unambiguously about the just-selected tenant (Req 2).
- Guarantee the response is fresh, never a replayed prior-tenant body (Req 3).
- Guard against out-of-order responses (Req 2.2, 2.3).
- Keep the menu re-rendering correctly (Req 4) — verify, don't over-engineer.
- Resolve the roles question so compound gating is correct (Req 5), without adding an
  unnecessary refetch if roles are global (Req 5.3).
- No regressions for single-tenant users or unrelated `X-Tenant` calls (Req 6).

## 5. Proposed changes

### 5.1 Pass the current tenant explicitly from the hook (Req 2.1, Cause B)
In `useTenantModules.ts`, pass the tenant that triggered the effect into the request so the
`X-Tenant` header comes from the effect's `currentTenant`, not an independent storage read:
```ts
const response = await authenticatedGet('/api/tenant/modules', { tenant: currentTenant });
```
`authenticatedRequest` already prefers the passed `tenant` over `getCurrentTenant()`
(`tenant || getCurrentTenant()`), so no signature change is needed — this just uses the
existing option. This makes the header provably match the effect's tenant.

### 5.2 Make the modules GET non-cacheable / per-tenant (Req 3, Cause A)
Ensure the modules request cannot be served from a stale cache. Two complementary options; pick
the minimal set that the app's fetch layer supports cleanly:
- Add `cache: 'no-store'` to this GET (preferred, targeted). This can be done by threading a
  `cache` option through `authenticatedRequest`/`authenticatedGet` (they spread
  `...fetchOptions` into `fetch`, so a `cache` field flows through), OR
- Vary the request per tenant with a cache-busting query param, e.g.
  `/api/tenant/modules?tenant=${encodeURIComponent(currentTenant)}` (belt-and-suspenders; also
  helps any URL-keyed intermediary). The backend already resolves tenant from `X-Tenant`, so a
  query param is advisory only — confirm it is ignored server-side before relying on it.

Prefer `cache: 'no-store'` as the primary mechanism because it is explicit and does not depend
on backend query-param handling. Use the param only if a URL-keyed intermediary is confirmed to
be in play.

### 5.3 Guard against out-of-order responses (Req 2.2, 2.3, Cause C)
Add a supersession guard in the fetch effect so a stale in-flight response cannot overwrite
newer state:
```ts
useEffect(() => {
  if (!currentTenant) { setModules([]); setLoading(false); return; }
  let cancelled = false;
  const tenantAtStart = currentTenant;
  (async () => {
    try {
      setLoading(true); setError(null);
      const res = await authenticatedGet('/api/tenant/modules', { tenant: tenantAtStart });
      const data = await res.json();
      if (!cancelled && tenantAtStart === currentTenant) {
        setModules(data.available_modules || []);
      }
    } catch (err) {
      if (!cancelled) { setError('Failed to load available modules'); setModules([]); }
    } finally {
      if (!cancelled) setLoading(false);
    }
  })();
  return () => { cancelled = true; };
}, [currentTenant]);
```
The `cancelled` cleanup flag is the standard React pattern for discarding a superseded async
result.

### 5.4 Verify (do not blindly add) menu re-render (Req 4)
`MainMenu` is a plain component and `App` consumes the hook directly, so no change should be
needed. Explicitly confirm during verification that no `React.memo` was added on the menu path
without the flags in its comparison. If a memo is later introduced, its inputs must include
`hasFIN/hasSTR/hasZZP/hasMEMBERS`.

### 5.5 Resolve the roles question (Req 5)
Determine whether roles are tenant-scoped:
- **If roles are global** (same across tenants): no role refetch is needed; document this in the
  spec and rely on module-flag freshness (Req 5.3). This is the expected finding given
  `getCurrentUserRoles()` reads Cognito group claims that are not tenant-partitioned.
- **If roles are tenant-scoped**: call the existing `refreshUserRoles()` when the tenant changes
  (e.g. a small effect that reacts to `currentTenant`), so `user.roles` matches the active
  tenant before the compound gating evaluates. Reuse the existing `checkAuthState()` path;
  do not build a parallel role-fetch.

The implementation must confirm which case holds (via the roles/Cognito claim source) and only
add the refresh in the tenant-scoped case.

## 6. Open question to resolve during implementation — RESOLVED

**Are Cognito role claims tenant-scoped or global for this app?**

**RESOLVED: roles are GLOBAL, not tenant-scoped → no role refetch needed.**

Verified in `frontend/src/services/authService.ts`:
- `getCurrentUserRoles()` returns `payload['cognito:groups']` — a flat list of Cognito groups
  read from the current JWT id token.
- `getCurrentUserTenants()` returns `payload['custom:tenants']` — the user's tenant membership,
  read from the SAME JWT.

Switching the active tenant in the UI does not re-issue the token, so `cognito:groups` (and
therefore `user.roles`) is unchanged by a switch. The role side of `MainMenu`'s
`flag && role` gating is constant across a switch; once the module flags refresh correctly the
menu is correct. Per Req 5.3, this requirement is satisfied by module-flag freshness alone, and
we deliberately do NOT add a `refreshUserRoles()` on tenant switch (it would refetch an
unchanged token). Task 5 therefore takes the "global" branch of §5.5 with no code change.

## 7. Alternatives considered
- **Force a full reload on switch** — matches the current workaround but defeats the SPA UX and
  the existing live-redirect effect. Rejected.
- **Cache modules per tenant in the context** — a larger change; premature. The bug is
  freshness, not missing caching. Rejected for this scope.
- **Move tenant selection out of localStorage** — out of scope (Req 6.3, Out of scope list).

## 8. Testing strategy
- **Reproduction**: with a multi-tenant user whose tenants have different module sets, switch
  tenant and assert the menu updates without reload. Capture the failing behavior first.
- **Freshness**: assert the modules request for the second tenant is not served from cache
  (verify `no-store` / per-tenant request and that the parsed `available_modules` matches the
  new tenant).
- **Out-of-order**: simulate a slow first response resolving after a second switch; assert final
  `modules` matches the last tenant.
- **Compound gating**: assert a module the new tenant lacks disappears, and one it has (with a
  matching role) appears.
- **Regression**: single-tenant user unaffected; unrelated `X-Tenant` requests unchanged; the
  `App.tsx` module-loss redirect still fires.
- Prefer streaming test output over log files per the workspace shell rules; frontend tests run
  under the frontend toolchain (confirm the runner from `frontend/package.json` before running).

## 9. Traceability
| Requirement | Addressed by |
|---|---|
| 1 (menu updates without reload) | 5.1 + 5.2 + 5.3 (fresh, correct, ordered refetch) |
| 2 (targets selected tenant) | 5.1 (explicit tenant), 5.3 (supersession guard) |
| 3 (no stale cache) | 5.2 (`no-store` / per-tenant request) |
| 4 (menu re-renders) | 5.4 (verify non-memoized path) |
| 5 (role-gated consistency) | 5.5 + §6 (resolve tenant-scoping, refresh only if needed) |
| 6 (no regressions) | 5.1–5.5 scoped to the modules path; §8 regression tests |
