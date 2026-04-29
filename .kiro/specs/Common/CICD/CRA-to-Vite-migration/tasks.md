# Implementation Plan: CRA-to-Vite Migration

## Overview

Migrate the myAdmin frontend from Create React App 5.0.1 to Vite 6.x in 8 sequential phases. Each phase builds on the previous — the core migration (Phases 1–3) replaces the build system, env vars, and test runner; the remaining phases (4–8) introduce improvements enabled by the migration. All code is TypeScript/React.

## Tasks

- [x] 1. Phase 1 — Vite + TypeScript Setup
  - [x] 1.1 Install Vite dependencies and remove CRA
    - Install `vite`, `@vitejs/plugin-react`, `typescript@^5.7`
    - Uninstall `react-scripts` from dependencies
    - Remove `"proxy"`, `"homepage"`, `"browserslist"`, `"eslintConfig"`, and `"jest"` blocks from `package.json`
    - _Requirements: 1.1, 1.6, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 1.2 Create `vite.config.ts` with proxy, base path, and plugins
    - Configure `base: '/myAdmin'` (replaces `homepage`)
    - Configure `server.proxy` for `/api` → `http://localhost:5000` (replaces `proxy` field)
    - Configure `server.port: 3000`
    - Configure `build.outDir: 'build'` and `build.target: 'es2020'`
    - Add `@vitejs/plugin-react` plugin
    - _Requirements: 1.6, 3.1, 3.2, 3.3, 10.1_

  - [x] 1.3 Update `tsconfig.json` for Vite and TypeScript 5.7+
    - Set `target` to `ES2020`, `moduleResolution` to `bundler`, `module` to `ESNext`
    - Add `baseUrl: "."` and `paths: { "@/*": ["./src/*"] }` (used in Phase 6)
    - _Requirements: 1.3, 1.5, 8.2_

  - [x] 1.4 Move `index.html` to project root as Vite entry point
    - Move `public/index.html` to project root
    - Remove all `%PUBLIC_URL%` references (Vite resolves `/` paths automatically)
    - Add `<script type="module" src="/src/index.tsx"></script>`
    - Update meta tags and preserve `config.js` script reference
    - _Requirements: 1.7, 4.4_

  - [x] 1.5 Update `package.json` scripts
    - `start`: `react-scripts start` → `vite`
    - `build`: `react-scripts build` → `tsc -b && vite build`
    - `build:ci`: → `vite build`
    - Add `preview`: `vite preview`
    - Remove `eject` script
    - _Requirements: 1.1, 1.6, 10.4_

  - [x] 1.6 Verify Phase 1 — dev server starts and production build succeeds
    - Run `vite dev` and confirm the app starts without errors on port 3000
    - Run `vite build` and confirm output in `build/` directory
    - Confirm `tsc --version` reports 5.7+
    - Grep for `react-scripts` in `package.json` — expect zero matches
    - _Requirements: 1.1, 1.2, 1.3, 1.8_

- [x] 2. Phase 2 — Environment Variable Migration
  - [x] 2.1 Rename env vars in `.env` files
    - Rename `REACT_APP_*` → `VITE_*` in `.env`, `.env.production`, `.env.railway`, `.env.example`
    - _Requirements: 4.1_

  - [x] 2.2 Replace `process.env.REACT_APP_*` in source files
    - Update `aws-exports.ts`: 6 env var references
    - Update `authService.ts`, `chartOfAccountsService.ts`, `tenantAdminApi.ts`: `REACT_APP_API_URL` → `VITE_API_URL`
    - Update `MigrationTool.tsx`, `CredentialsManagement.tsx`, `TenantAdminDashboard.tsx`, `StorageTab.tsx`: `REACT_APP_API_URL` → `VITE_API_URL`
    - Update `helpLinks.ts`: `REACT_APP_API_URL` and `REACT_APP_DOCS_URL`
    - Replace `process.env.PUBLIC_URL` → `import.meta.env.BASE_URL` in `Login.tsx` and `apiService.ts`
    - _Requirements: 4.2, 4.3_

  - [x] 2.3 Create `src/env.d.ts` type declarations
    - Define `ImportMetaEnv` interface with all `VITE_*` variables
    - Add `/// <reference types="vite/client" />`
    - Delete `src/react-app-env.d.ts`
    - _Requirements: 4.5, 2.7_

  - [x] 2.4 Verify Phase 2 — env vars resolve correctly
    - Grep for `REACT_APP_` in source and `.env` files — expect zero matches
    - Grep for `process.env.REACT_APP_` — expect zero matches
    - Grep for `%PUBLIC_URL%` in `index.html` — expect zero matches
    - Confirm app starts and Cognito auth flow completes
    - _Requirements: 4.6, 4.7_

- [x] 3. Phase 3 — Test Migration (Jest → Vitest)
  - [x] 3.1 Install Vitest and configure test environment
    - Install `vitest`, `@vitest/coverage-v8`, `jsdom`, `@testing-library/jest-dom`
    - Replace `@fast-check/jest` with `@fast-check/vitest`
    - Replace `jest-axe` with `vitest-axe`
    - Remove `@types/jest` from devDependencies
    - Add Vitest `test` block to `vite.config.ts` (globals, jsdom, setupFiles, css, include patterns)
    - _Requirements: 5.1, 5.3, 5.4, 5.6, 5.9_

  - [x] 3.2 Migrate `setupTests.ts` for Vitest
    - Replace `jest.fn()` → `vi.fn()` and `jest.mock()` → `vi.mock()`
    - Add `import { vi } from 'vitest'`
    - Preserve all polyfills (TextEncoder, BroadcastChannel, fetch mock)
    - Preserve global `aws-amplify/auth` mock
    - _Requirements: 5.5_

  - [x] 3.3 Bulk-migrate 109 test files from Jest to Vitest API
    - Replace all `jest.fn()` → `vi.fn()`, `jest.mock()` → `vi.mock()`, `jest.spyOn()` → `vi.spyOn()`
    - Replace `jest.clearAllMocks()` → `vi.clearAllMocks()`, `jest.resetAllMocks()` → `vi.resetAllMocks()`
    - Update imports: remove `@jest/globals` imports, add `import { vi } from 'vitest'` where explicit imports are used
    - Replace `@fast-check/jest` imports with `@fast-check/vitest`
    - Replace `jest-axe` imports with `vitest-axe`
    - _Requirements: 5.2, 5.3, 5.4_

  - [x] 3.4 Remove remaining Jest/CRA artifacts
    - Remove `"jest"` config block from `package.json` (transformIgnorePatterns, moduleNameMapper)
    - Remove `"react-app/jest"` from eslintConfig extends
    - Delete `src/reportWebVitals.ts` and remove its import from `src/index.tsx`
    - Update `package.json` test script: `react-scripts test` → `vitest`
    - Add `test:run` script: `vitest run` (single execution for CI)
    - _Requirements: 2.6, 2.8, 2.9, 5.8_

  - [x] 3.5 Verify Phase 3 — test suite passes under Vitest
    - Run `vitest run` and confirm all previously-passing tests still pass
    - Grep for `jest.fn`, `jest.mock`, `jest.spyOn` in test files — expect zero matches
    - Grep for `@types/jest` in `package.json` — expect zero matches
    - Confirm fast-check property tests run via `@fast-check/vitest`
    - Confirm accessibility tests run via `vitest-axe`
    - _Requirements: 5.7, 5.8, 5.9_

- [x] 4. Checkpoint — Core migration complete
  - Ensure dev server starts, production build succeeds, and test suite passes under Vitest.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Phase 4 — Authentication Test Repair
  - [x] 5.1 Audit Login.tsx against existing Chakra UI mocks
    - Compare current `Login.tsx` JSX with mocked components in `authentication-flow.test.tsx` and `authentication.integration.test.tsx`
    - Identify missing Chakra component mocks (e.g., `InputGroup`, `InputRightElement`, `IconButton`)
    - _Requirements: 6.3_

  - [x] 5.2 Fix Chakra UI mocks and auth service mocks
    - Add missing Chakra component mocks to both test files
    - Ensure `aws-amplify/auth` mock signatures match current API
    - Ensure `authService` mock matches current exports
    - _Requirements: 6.3, 6.4_

  - [x] 5.3 Verify Phase 4 — all auth tests pass
    - Run `authentication-flow.test.tsx` — all 13 tests pass (Login Flow, Protected Routes, Role-Based Access, Logout Flow, Token Management)
    - Run `authentication.integration.test.tsx` — all 20 tests pass
    - _Requirements: 6.1, 6.2, 6.5_

- [x] 6. Phase 5 — Route-Based Code Splitting
  - [x] 6.1 Convert page imports in `App.tsx` to `React.lazy()`
    - Convert all 15+ page component imports to lazy dynamic imports
    - Keep `Login` and main menu components eagerly loaded (critical path)
    - Group logically: FIN pages, STR pages, ZZP pages, Admin pages
    - Handle named exports (e.g., `SysAdminDashboard`, `TenantAdminDashboard`) with `.then(m => ({ default: m.X }))` pattern
    - _Requirements: 7.1, 7.3_

  - [x] 6.2 Add Suspense boundaries with loading fallback
    - Wrap lazy-loaded route output in `<Suspense>` with Chakra UI `Spinner` fallback
    - Style fallback to match app theme (dark background, orange spinner)
    - _Requirements: 7.2_

  - [x] 6.3 Swap `plotly.js` with `plotly.js-dist-min` for STR Reports
    - Replace the full `plotly.js` package (~3MB) with `plotly.js-dist-min` (smaller, pre-bundled)
    - Ensure STR Reports page still renders charts correctly
    - _Requirements: 7.6_

  - [x] 6.4 Verify Phase 5 — code splitting produces separate chunks
    - Run production build and confirm multiple chunk files are generated
    - Confirm Plotly.js chunk only loads when STR Reports page is accessed
    - Confirm Login and menu render without lazy loading delay
    - _Requirements: 7.4, 7.5, 7.6_

- [x] 7. Phase 6 — Path Aliases
  - [x] 7.1 Configure `@/` path alias in Vite and TypeScript
    - Add `resolve.alias` in `vite.config.ts`: `'@': path.resolve(__dirname, './src')`
    - Confirm `tsconfig.json` already has `paths` from Phase 1 task 1.3
    - _Requirements: 8.1, 8.2_

  - [x] 7.2 Verify Phase 6 — aliased imports resolve correctly
    - Create a test import using `@/services/authService` and confirm it resolves
    - Run production build and confirm no resolution errors
    - _Requirements: 8.3, 8.4_

- [x] 8. Phase 7 — ESLint Standalone Flat Config
  - [x] 8.1 Create `eslint.config.js` with flat config format
    - Install `@eslint/js`, `typescript-eslint`, `eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-plugin-import`
    - Configure TypeScript-aware rules, React plugin, React Hooks plugin, import ordering
    - Set `react-in-jsx-scope: off`, `no-unused-vars: warn`, `no-explicit-any: warn`
    - Add ignores for `build/`, `node_modules/`, `public/`
    - _Requirements: 9.1, 9.2, 9.4_

  - [x] 8.2 Update lint script and remove CRA ESLint config
    - Update `package.json` lint script: `eslint src`
    - Remove `eslint-config-react-app` dependency if present
    - Remove any remaining `"eslintConfig"` block from `package.json`
    - _Requirements: 9.3, 9.4_

  - [x] 8.3 Verify Phase 7 — lint runs without errors
    - Run `npm run lint` and confirm it executes without configuration errors
    - Confirm no new false-positive warnings compared to CRA ESLint baseline
    - _Requirements: 9.3, 9.5_

- [x] 9. Checkpoint — All improvements complete
  - Ensure all tests pass, ask the user if questions arise.
    - Review and or Fix in line with thius migration all files in
      - .kiro\steering\
    - Add a task 12 to push to main

- [x] 10. Phase 8 — Final Cleanup & Bundle Analysis
  - [x] 10.1 Final CRA/Jest artifact sweep
    - Grep for `react-scripts`, `react-app`, `REACT_APP_`, `jest.fn`, `jest.mock`, `@types/jest`, `reportWebVitals`, `react-app-env.d.ts` — expect zero matches across entire codebase
    - Remove any stale CRA-related comments or documentation references
    - _Requirements: 2.10, 5.8_

  - [x] 10.2 Install and configure bundle visualizer
    - Install `rollup-plugin-visualizer` as dev dependency
    - Add conditional visualizer plugin to `vite.config.ts` (enabled via `ANALYZE=true`)
    - Run `ANALYZE=true npm run build` and confirm `build/stats.html` is generated
    - _Requirements: 12.1, 12.2_

  - [x] 10.3 Verify deployment compatibility
    - Run `vite preview` and confirm production build serves correctly locally
    - Confirm `base: '/myAdmin'` produces correct asset paths for GitHub Pages
    - Confirm bundle treemap shows separate chunks for lazy-loaded route groups
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 11.5, 12.3_

  - [x] 10.4 Verify functional parity
    - Confirm `.d.ts` parse errors from fast-check 4.x, i18next 25.x, react-i18next 16.x are resolved in IDE Problems panel
    - Confirm Playwright e2e tests pass without modification
    - Confirm authentication flow works end-to-end (login, token refresh, logout)
    - _Requirements: 1.4, 11.1, 11.2, 11.3, 11.4_

- [x] 11. Final checkpoint — Migration complete
  - Ensure all tests pass, ask the user if questions arise.
  - Confirm the full migration is complete and no CRA artifacts remain.

- [x] 12. Push to main
  - Create a new branch for the CRA-to-Vite migration
  - Stage all migration changes
  - Commit with descriptive message summarizing the migration
  - Push branch and create a pull request to main

## Notes

- No property-based tests are included — this is a build toolchain migration with no pure functions to property-test.
- Each phase builds on the previous; they must be executed in order.
- Checkpoints ensure incremental validation between the core migration and improvement phases.
- The `@/` path alias is configured early (Phase 1) but only verified/used starting in Phase 6 — existing imports can be migrated incrementally over time.
- Playwright e2e tests are build-tool agnostic and should pass without modification after migration.
- Railway deployment requires `VITE_*` environment variables (not `REACT_APP_*`) to be set in the Railway dashboard since Vite embeds env vars at build time.
