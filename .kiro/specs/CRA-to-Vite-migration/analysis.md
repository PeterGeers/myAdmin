# CRA to Vite Migration — Scope Summary

**Status**: Draft — input for spec session  
**Created**: 2026-04-28  
**Trigger**: `t.d.ts` parse errors from TS 4.9.5 incompatibility + CRA end-of-life

---

## Problem Statement

CRA 5.0.1 bundles TypeScript 4.9.5, which cannot parse `const` type parameters (TS 5.0+ syntax) used in modern library `.d.ts` files. This currently affects:

- **fast-check 4.x** — property-based testing library
- **i18next 25.x** — internationalization runtime
- **react-i18next 16.x** — React i18n bindings

`skipLibCheck` does not help because these are **parse errors**, not semantic errors. The errors are cosmetic (Problems panel only — builds and runtime are unaffected), but they pollute the developer experience and will worsen as more libraries adopt TS 5.x syntax.

Downgrading these libraries to TS 4.9-compatible versions was investigated and rejected — it causes cascading API/type mismatches throughout the codebase (see `still todo.md`, 2026-04-27 notes).

**The real fix is upgrading TypeScript to 5.x, which requires migrating off CRA 5.**

### Why not just upgrade TS within CRA?

CRA's `react-scripts` hardcodes its TypeScript version and webpack/Babel pipeline. Overriding it breaks the build toolchain. CRA is effectively dead (last meaningful release: February 2022, no longer recommended by React docs).

---

## Proposed Solution

Migrate the frontend build toolchain from **Create React App 5** to **Vite 6.x** with:

- **TypeScript 5.x** — resolves all `.d.ts` parse errors
- **Vitest** — replaces Jest as the unit test runner (API-compatible)
- **ESLint standalone** — replaces CRA's built-in eslint-config-react-app

Additionally, leverage the migration to introduce improvements that are impractical on CRA but natural on Vite.

---

## Migration Surface Analysis

### Environment Variables (mechanical, ~20 references)

| What                           | Count                                                                   | Change                                                  |
| ------------------------------ | ----------------------------------------------------------------------- | ------------------------------------------------------- |
| `REACT_APP_*` in source files  | ~18 refs across 10 files                                                | Rename to `VITE_*`, access via `import.meta.env.VITE_*` |
| `REACT_APP_*` in `.env` files  | 4 env files (`.env`, `.env.production`, `.env.railway`, `.env.example`) | Rename prefix to `VITE_`                                |
| `process.env.PUBLIC_URL`       | 2 refs (`Login.tsx`, `apiService.ts`)                                   | Replace with `import.meta.env.BASE_URL`                 |
| `%PUBLIC_URL%` in `index.html` | 4 refs                                                                  | Remove (Vite resolves `/` paths automatically)          |

### Build Configuration

| CRA artifact                                                    | Vite equivalent                                           |
| --------------------------------------------------------------- | --------------------------------------------------------- |
| `react-scripts` (start/build/test)                              | `vite`, `vite build`, `vitest`                            |
| `package.json` proxy field (`"proxy": "http://localhost:5000"`) | `vite.config.ts` → `server.proxy`                         |
| `public/index.html` (CRA injects scripts)                       | `index.html` at project root (Vite entry point)           |
| `tsconfig.json` (target: es5, module: esnext)                   | Update target to `ES2020+`, moduleResolution to `bundler` |
| `browserslist` in package.json                                  | Vite uses `build.target` in config                        |
| `homepage` field (GitHub Pages)                                 | `base` in `vite.config.ts`                                |

### TypeScript Configuration

| Setting            | Current (CRA) | Target (Vite)          |
| ------------------ | ------------- | ---------------------- |
| `typescript`       | 4.9.5         | 5.7+                   |
| `target`           | es5           | ES2020                 |
| `module`           | esnext        | ESNext                 |
| `moduleResolution` | node          | bundler                |
| `skipLibCheck`     | true          | true (can relax later) |

### Test Migration (109 test files)

| Aspect                      | Current (Jest via CRA)                     | Target (Vitest)                                   |
| --------------------------- | ------------------------------------------ | ------------------------------------------------- |
| Runner                      | `react-scripts test` (Jest 27)             | `vitest`                                          |
| API                         | `jest.fn()`, `jest.mock()`, `jest.spyOn()` | `vi.fn()`, `vi.mock()`, `vi.spyOn()`              |
| Config                      | `jest` block in package.json               | `vitest.config.ts` or `vite.config.ts` test block |
| `@testing-library/jest-dom` | Works as-is                                | Works as-is (compatible with Vitest)              |
| `@fast-check/jest`          | Current                                    | Replace with `@fast-check/vitest`                 |
| `msw`                       | Works as-is                                | Works as-is                                       |
| `jest-axe`                  | Current                                    | Needs vitest-axe or adapter                       |
| `transformIgnorePatterns`   | Custom for fast-check, date-fns            | Not needed (Vite handles ESM natively)            |
| `moduleNameMapper` (Chakra) | Custom CRA workaround                      | Likely not needed with Vite's ESM resolution      |
| **Playwright e2e tests**    | **Unaffected**                             | **No changes needed**                             |

### Auth Test Failures (13 tests, 2 files)

Pre-existing failures in:

- `frontend/src/tests/authentication-flow.test.tsx` — 13 test cases across Login Flow, Protected Routes, Role-Based Access, Logout Flow, Token Management
- `frontend/src/__tests__/authentication.integration.test.tsx` — 20 test cases across Login Flow, Protected Routes, RBAC, Logout, Token Expiration, UX

Root cause: Login component render issues with React 19. Both files heavily mock `@chakra-ui/react` with manual component stubs and mock `aws-amplify/auth` + `authService`. The mocks are extensive but fragile — they replicate Chakra component APIs by hand, which breaks when the Login component's JSX changes.

Fix approach during migration:

- Migrate `jest.mock()` → `vi.mock()` and `jest.fn()` → `vi.fn()` (part of Phase 3)
- Debug and fix the actual render failures — likely caused by incomplete Chakra mocks missing props that Login.tsx now uses (e.g., `InputGroup`, `InputRightElement`, `IconButton` not mocked)
- Consider replacing manual Chakra mocks with a lighter approach (e.g., mock at the module level with auto-mock, or render with real ChakraProvider in jsdom)

### Files That Need Changes

**Config files (create/replace)**:

- `vite.config.ts` — new (proxy, base path, plugins, test config)
- `tsconfig.json` — update compiler options
- `tsconfig.node.json` — new (for vite config itself)
- `index.html` — move from `public/` to root, update entry point
- `package.json` — update scripts, dependencies
- `.eslintrc.js` or `eslint.config.js` — new standalone ESLint config

**Source files (find-and-replace)**:

- 10 files with `process.env.REACT_APP_*` → `import.meta.env.VITE_*`
- 2 files with `process.env.PUBLIC_URL` → `import.meta.env.BASE_URL`
- 109 test files: `jest.*` → `vi.*` imports and calls
- `react-app-env.d.ts` → replace with `env.d.ts` (Vite types)
- `reportWebVitals.ts` → remove (CRA boilerplate, not wired to analytics)

**Environment files**:

- 4 `.env` files: rename `REACT_APP_` prefix to `VITE_`

---

## Risks and Considerations

### Medium Risk

- **109 test files need `jest` → `vi` migration** — mechanical but high volume. Some tests may have subtle Jest-specific behavior.
- **`jest-axe` compatibility** — may need `vitest-axe` or a shim. Verify before migrating accessibility tests.
- **Chakra UI moduleNameMapper workaround** — currently needed for CRA's CJS resolution. Vite's native ESM handling may resolve this, but needs verification.
- **Auth test fixes** — the 13 failures stem from incomplete Chakra UI mocks. Fixing them requires understanding what Login.tsx renders and ensuring mocks cover all used components. Risk: Login component may have evolved since mocks were written.

### Low Risk

- **Env variable rename** — purely mechanical, well-scoped.
- **Proxy config** — simple `package.json` proxy → `vite.config.ts` server.proxy. No custom setupProxy middleware exists.
- **GitHub Pages deployment** — `homepage` field → `base` in vite config. `gh-pages` package still works.
- **MSW (Mock Service Worker)** — compatible with Vite, no changes expected.
- **Playwright e2e tests** — completely unaffected (they test the running app, not the build tool).
- **Code splitting** — `React.lazy` is well-supported in Vite; the switch statement in App.tsx maps cleanly to lazy imports.

---

## Proposed Phases

### Phase 1 — Vite + TypeScript Setup (~2h)

- Install `vite`, `@vitejs/plugin-react`, TypeScript 5.x
- Create `vite.config.ts` with proxy, base path, and plugins
- Move `index.html` from `public/` to project root, update entry point
- Update `tsconfig.json` for Vite/TS 5.x
- Update `package.json` scripts (`start`, `build`, `build:ci`)
- **CRA removal**: uninstall `react-scripts` from dependencies; remove `"proxy"` field from `package.json` (replaced by `server.proxy` in `vite.config.ts`); remove `"homepage"` field (replaced by `base` in `vite.config.ts`); remove `"browserslist"` block (replaced by `build.target` in `vite.config.ts`)
- **Verify**: app starts with `vite dev`, production build succeeds, no `react-scripts` references remain in `package.json`

### Phase 2 — Environment Variables (~1h)

- Rename `REACT_APP_*` → `VITE_*` in all 4 `.env` files
- Replace `process.env.REACT_APP_*` → `import.meta.env.VITE_*` in source (10 files)
- Replace `process.env.PUBLIC_URL` → `import.meta.env.BASE_URL` (2 files)
- Add `env.d.ts` type declarations for `ImportMetaEnv`
- **CRA removal**: delete `react-app-env.d.ts` (contains only `/// <reference types="react-scripts" />`); remove the `REACT_APP_` comment/documentation in `.env` files explaining the CRA prefix convention
- **Verify**: app runs correctly with env vars, Cognito auth works, no `REACT_APP_` or `process.env.REACT_APP_` references remain in source

### Phase 3 — Test Migration: Jest → Vitest (~4h)

- Install `vitest`, `@vitest/coverage-v8`, `jsdom`
- Replace `@fast-check/jest` with `@fast-check/vitest`
- Resolve `jest-axe` → vitest-compatible alternative
- Configure Vitest in `vite.config.ts` (test block)
- Create new `setupTests.ts` for Vitest (migrate polyfills, global mocks from current Jest setup)
- Migrate test files: `jest.fn()` → `vi.fn()`, `jest.mock()` → `vi.mock()`, `jest.spyOn()` → `vi.spyOn()` (bulk find-replace + manual review across 109 files)
- **Jest removal**: uninstall `@types/jest` from devDependencies; remove entire `"jest"` config block from `package.json` (contains `transformIgnorePatterns` and `moduleNameMapper`); remove `"react-app/jest"` from `"eslintConfig"` extends array; remove CRA boilerplate file `reportWebVitals.ts` and its import in `index.tsx`
- **Verify**: test suite passes (baseline against current pass/fail counts), no `jest.` calls remain in test files (only `vi.`), no Jest config remains in `package.json`

### Phase 4 — Fix Auth Test Failures (~2h)

- Audit `Login.tsx` current JSX against mocked Chakra components in both test files
- Add missing Chakra component mocks (likely `InputGroup`, `InputRightElement`, `IconButton`, etc.)
- Alternatively: refactor to use real `ChakraProvider` with jsdom instead of manual mocks
- Fix mock setup for `aws-amplify/auth` and `authService` to match current API signatures
- Verify all 13 previously-failing tests pass
- **Verify**: both `authentication-flow.test.tsx` and `authentication.integration.test.tsx` pass completely
- **Files**: `frontend/src/tests/authentication-flow.test.tsx`, `frontend/src/__tests__/authentication.integration.test.tsx`

### Phase 5 — Route-Based Code Splitting (~3h)

- Convert all 15+ page imports in `App.tsx` to `React.lazy()` with dynamic imports
- Add `<Suspense>` boundaries with appropriate loading fallbacks (Chakra Spinner or skeleton)
- Group chunks logically: FIN pages, STR pages, ZZP pages, Admin pages
- Keep Login and Menu eagerly loaded (critical path)
- **Verify**: each page loads on demand (check network tab), no flash of loading state on fast connections
- **Impact**: users only download code for modules they access; Plotly (~3MB) only loads when STR reports are opened

### Phase 6 — Path Aliases (~1h)

- Configure `resolve.alias` in `vite.config.ts`: `@/` → `./src/`
- Add matching `paths` in `tsconfig.json`: `"@/*": ["./src/*"]`
- Optionally migrate existing deep relative imports (e.g., `../../services/authService` → `@/services/authService`)
- **Note**: can be adopted incrementally — new code uses aliases, existing code migrated over time
- **Verify**: build succeeds, imports resolve correctly

### Phase 7 — ESLint Standalone + Flat Config (~1h)

- Create `eslint.config.js` (flat config format)
- Configure: TypeScript-aware rules, React plugin, import ordering, unused import auto-removal
- **CRA removal**: remove entire `"eslintConfig"` block from `package.json` (currently extends `react-app` and `react-app/jest`); uninstall `eslint-config-react-app` if it's a direct dependency
- **Verify**: `npm run lint` works, no new false positives, no CRA ESLint config remains

### Phase 8 — Final Cleanup, Bundle Analysis & Verification (~1.5h)

- **Final CRA/Jest sweep**: confirm no remaining references to `react-scripts`, `react-app`, `REACT_APP_`, `jest.fn`, `jest.mock`, `@types/jest`, `reportWebVitals`, `react-app-env.d.ts` anywhere in the codebase
- Install `rollup-plugin-visualizer`, generate bundle treemap
- Review bundle composition — identify optimization opportunities (e.g., `lodash` → `lodash-es`, MUI tree-shaking)
- Add `vite preview` script for local production testing
- Verify GitHub Pages deployment pipeline
- Verify Railway deployment (if applicable)
- Confirm `.d.ts` parse errors are resolved in Problems panel
- Update documentation / README if needed

---

## Success Criteria

1. **Primary**: `.d.ts` parse errors from fast-check, i18next, react-i18next are gone
2. App builds and runs identically to current CRA build
3. All currently-passing tests continue to pass under Vitest
4. **All 13 previously-failing auth tests now pass**
5. Dev server starts in under 5 seconds (vs current 30-60s)
6. Cognito authentication flow works end-to-end
7. GitHub Pages deployment works
8. Route-based code splitting produces separate chunks per module
9. No runtime regressions

---

## Estimated Effort

| Phase                                             | Estimate        |
| ------------------------------------------------- | --------------- |
| Phase 1 — Vite + TS setup                         | ~2 hours        |
| Phase 2 — Env variables                           | ~1 hour         |
| Phase 3 — Test migration (Jest → Vitest)          | ~4 hours        |
| Phase 4 — Fix auth test failures                  | ~2 hours        |
| Phase 5 — Route-based code splitting              | ~3 hours        |
| Phase 6 — Path aliases                            | ~1 hour         |
| Phase 7 — ESLint standalone + flat config         | ~1 hour         |
| Phase 8 — Cleanup, bundle analysis & verification | ~1.5 hours      |
| **Total**                                         | **~15.5 hours** |

Phases 1–3 are the **core migration** (~7h). Phases 4–8 are **improvements enabled by the migration** (~8.5h). The phases are sequential — each builds on the previous — but Phases 5–7 could be deferred to a follow-up if needed.

---

## References

- Root cause analysis: `.kiro/Issues and bug fixes/still todo.md` (2026-04-27 entries)
- Current frontend config: `frontend/package.json`, `frontend/tsconfig.json`
- Auth test files: `frontend/src/tests/authentication-flow.test.tsx`, `frontend/src/__tests__/authentication.integration.test.tsx`
- App routing: `frontend/src/App.tsx` (15+ eagerly imported page components)
- Vite migration guide: https://vite.dev/guide/
- Vitest migration from Jest: https://vitest.dev/guide/migration.html
