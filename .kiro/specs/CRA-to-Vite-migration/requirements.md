# Requirements Document

## Introduction

Migrate the myAdmin frontend build toolchain from Create React App (CRA) 5.0.1 to Vite 6.x. CRA bundles TypeScript 4.9.5, which cannot parse `const` type parameters (TS 5.0+ syntax) found in modern library `.d.ts` files (fast-check 4.x, i18next 25.x, react-i18next 16.x). These are parse errors that `skipLibCheck` cannot suppress. CRA is end-of-life (last meaningful release: February 2022) and no longer recommended by React docs. The migration replaces the entire CRA toolchain — build system, test runner, linter configuration — with Vite 6.x, Vitest, and standalone ESLint, while also introducing route-based code splitting and path aliases that are impractical under CRA.

## Glossary

- **Build_System**: The frontend build toolchain responsible for development server, production bundling, and TypeScript compilation. Currently CRA 5.0.1 with webpack; target is Vite 6.x with Rollup.
- **Test_Runner**: The unit and integration test execution framework. Currently Jest 27 via `react-scripts test`; target is Vitest.
- **Linter**: The static analysis tool for code quality. Currently ESLint configured via CRA's `eslint-config-react-app`; target is standalone ESLint with flat config.
- **Env_Loader**: The mechanism that exposes environment variables to frontend source code. Currently `process.env.REACT_APP_*` via CRA's webpack DefinePlugin; target is `import.meta.env.VITE_*` via Vite's built-in env handling.
- **Type_Checker**: The TypeScript compiler used for type checking. Currently TypeScript 4.9.5 bundled by CRA; target is TypeScript 5.7+.
- **Code_Splitter**: The mechanism that splits the application bundle into smaller chunks loaded on demand. Target is `React.lazy()` with dynamic imports, producing per-route chunks via Vite's Rollup-based bundling.
- **Path_Resolver**: The module resolution configuration that maps import aliases to filesystem paths. Target is `@/` mapped to `./src/` via `resolve.alias` in Vite config and `paths` in `tsconfig.json`.
- **Dev_Server**: The local development server used during development. Currently CRA's webpack-dev-server on port 3000; target is Vite's dev server.
- **Auth_Test_Suite**: The two test files covering authentication flows: `authentication-flow.test.tsx` (13 tests) and `authentication.integration.test.tsx` (20 tests). Currently 13 tests fail due to incomplete Chakra UI mocks.
- **Proxy_Config**: The development server configuration that forwards API requests to the backend. Currently the `"proxy"` field in `package.json`; target is `server.proxy` in `vite.config.ts`.

## Requirements

### Requirement 1: Vite Build System Setup

**User Story:** As a developer, I want the frontend to build and serve using Vite 6.x with TypeScript 5.7+, so that `.d.ts` parse errors from modern libraries are resolved and the development experience improves.

#### Acceptance Criteria

1. WHEN the developer runs the dev server start command, THE Build_System SHALL start a Vite development server that serves the application with hot module replacement.
2. WHEN the developer runs the production build command, THE Build_System SHALL produce an optimized production bundle in the output directory.
3. THE Build_System SHALL use TypeScript 5.7 or higher for type checking and compilation.
4. WHEN the Type_Checker processes `.d.ts` files from fast-check 4.x, i18next 25.x, and react-i18next 16.x, THE Type_Checker SHALL parse them without errors in the IDE Problems panel.
5. THE Build_System SHALL configure the `tsconfig.json` with `target` set to `ES2020`, `moduleResolution` set to `bundler`, and `module` set to `ESNext`.
6. WHEN the application is built for production, THE Build_System SHALL use `vite.config.ts` as the sole build configuration, with no dependency on `react-scripts`.
7. THE Build_System SHALL move `index.html` from the `public/` directory to the project root as the Vite entry point, with a `<script type="module">` tag referencing `src/index.tsx`.
8. IF the `react-scripts` package is referenced anywhere in `package.json` dependencies or scripts, THEN THE Build_System SHALL report a configuration error during the migration verification step.

### Requirement 2: CRA Artifact Removal

**User Story:** As a developer, I want all CRA-specific artifacts removed from the project, so that there is no ambiguity about which build system is active and no stale configuration causes confusion.

#### Acceptance Criteria

1. THE Build_System SHALL remove `react-scripts` from `package.json` dependencies.
2. THE Build_System SHALL remove the `"proxy"` field from `package.json` (replaced by `server.proxy` in `vite.config.ts`).
3. THE Build_System SHALL remove the `"homepage"` field from `package.json` (replaced by `base` in `vite.config.ts`).
4. THE Build_System SHALL remove the `"browserslist"` block from `package.json` (replaced by `build.target` in `vite.config.ts`).
5. THE Build_System SHALL remove the `"eslintConfig"` block from `package.json` (replaced by standalone ESLint config file).
6. THE Build_System SHALL remove the `"jest"` configuration block from `package.json` (replaced by Vitest config in `vite.config.ts`).
7. THE Build_System SHALL delete the file `react-app-env.d.ts` (contains only CRA type reference).
8. THE Build_System SHALL delete the file `reportWebVitals.ts` and remove its import from `index.tsx`.
9. THE Build_System SHALL remove `@types/jest` from `devDependencies`.
10. WHEN a codebase-wide search is performed for `react-scripts`, `react-app`, `REACT_APP_`, or `reportWebVitals`, THE Build_System SHALL return zero matches in source files, configuration files, and `package.json`.

### Requirement 3: Development Server Proxy Configuration

**User Story:** As a developer, I want API requests proxied to the backend during local development, so that the frontend can communicate with the Flask backend without CORS issues.

#### Acceptance Criteria

1. WHILE the Dev_Server is running in development mode, THE Proxy_Config SHALL forward requests matching `/api/*` to `http://localhost:5000`.
2. THE Proxy_Config SHALL be defined in `vite.config.ts` under the `server.proxy` configuration key.
3. WHEN the Dev_Server proxies a request to the backend, THE Proxy_Config SHALL preserve the original request path, headers, and body.

### Requirement 4: Environment Variable Migration

**User Story:** As a developer, I want all environment variables migrated from the CRA `REACT_APP_` convention to Vite's `VITE_` convention, so that the application can read configuration values at runtime.

#### Acceptance Criteria

1. THE Env*Loader SHALL rename all `REACT_APP*`prefixed variables to`VITE\_`prefixed variables in the`.env`, `.env.production`, `.env.railway`, and `.env.example` files.
2. THE Env*Loader SHALL replace all `process.env.REACT_APP*\_`references in source files with`import.meta.env.VITE\_\_` equivalents.
3. THE Env_Loader SHALL replace all `process.env.PUBLIC_URL` references with `import.meta.env.BASE_URL`.
4. THE Env_Loader SHALL remove all `%PUBLIC_URL%` references from `index.html` (Vite resolves `/` paths automatically).
5. THE Env*Loader SHALL provide an `env.d.ts` type declaration file that defines the `ImportMetaEnv` interface with all `VITE*` variables used by the application.
6. WHEN a codebase-wide search is performed for `process.env.REACT_APP_` or `REACT_APP_` in `.env` files, THE Env_Loader SHALL return zero matches.
7. WHEN the application starts with the migrated environment variables, THE Env_Loader SHALL make Cognito configuration (user pool ID, client ID, region, domain), API URL, OAuth redirect URLs, and docs URL available to the application at runtime.

### Requirement 5: Test Runner Migration (Jest to Vitest)

**User Story:** As a developer, I want the test suite migrated from Jest to Vitest, so that tests run natively within the Vite ecosystem without separate transpilation configuration.

#### Acceptance Criteria

1. THE Test_Runner SHALL execute all unit and integration tests using Vitest.
2. THE Test_Runner SHALL replace all `jest.fn()` calls with `vi.fn()`, all `jest.mock()` calls with `vi.mock()`, and all `jest.spyOn()` calls with `vi.spyOn()` across all 109 test files.
3. THE Test_Runner SHALL replace the `@fast-check/jest` dependency with `@fast-check/vitest` and update all related imports.
4. THE Test_Runner SHALL replace `jest-axe` with a Vitest-compatible accessibility testing alternative (such as `vitest-axe` or an adapter).
5. THE Test_Runner SHALL configure a `setupTests.ts` file for Vitest that includes all polyfills and global mocks currently in the Jest setup.
6. THE Test_Runner SHALL configure `jsdom` as the test environment in the Vitest configuration.
7. WHEN the full test suite is executed, THE Test_Runner SHALL produce pass/fail counts equal to or better than the baseline counts from the Jest-based suite (all previously passing tests continue to pass).
8. WHEN a codebase-wide search is performed for `jest.fn`, `jest.mock`, `jest.spyOn`, or `@types/jest`, THE Test_Runner SHALL return zero matches in test files and configuration.
9. THE Test_Runner SHALL not require `transformIgnorePatterns` or `moduleNameMapper` workarounds for fast-check, date-fns, or Chakra UI packages (Vite handles ESM natively).

### Requirement 6: Authentication Test Repair

**User Story:** As a developer, I want the 13 previously-failing authentication tests fixed, so that the auth test suite provides reliable regression coverage.

#### Acceptance Criteria

1. WHEN the Auth_Test_Suite is executed, THE Test_Runner SHALL pass all tests in `authentication-flow.test.tsx` (Login Flow, Protected Routes, Role-Based Access, Logout Flow, Token Management).
2. WHEN the Auth_Test_Suite is executed, THE Test_Runner SHALL pass all tests in `authentication.integration.test.tsx` (Login Flow, Protected Routes, RBAC, Logout, Token Expiration, UX).
3. THE Auth_Test_Suite SHALL mock all Chakra UI components that `Login.tsx` currently renders, including but not limited to `InputGroup`, `InputRightElement`, and `IconButton`.
4. THE Auth_Test_Suite SHALL mock `aws-amplify/auth` and `authService` with signatures matching the current API.
5. IF a Chakra UI component mock is missing a prop or sub-component that `Login.tsx` uses, THEN THE Auth_Test_Suite SHALL fail with a descriptive error identifying the missing mock rather than a generic render error.

### Requirement 7: Route-Based Code Splitting

**User Story:** As a developer, I want page components loaded on demand via route-based code splitting, so that users only download code for the modules they access and the initial bundle size is reduced.

#### Acceptance Criteria

1. THE Code_Splitter SHALL convert all page-level component imports in `App.tsx` to `React.lazy()` with dynamic `import()` expressions.
2. THE Code_Splitter SHALL wrap lazy-loaded components in `<Suspense>` boundaries with a loading fallback (Chakra UI Spinner or skeleton component).
3. THE Code_Splitter SHALL keep `Login` and the main menu eagerly loaded (critical path — no lazy loading).
4. WHEN a user navigates to a page, THE Code_Splitter SHALL load only the JavaScript chunk for that page and its dependencies.
5. WHEN the production build is generated, THE Code_Splitter SHALL produce separate chunks for FIN pages, STR pages, ZZP pages, and Admin pages.
6. WHEN the STR Reports page is loaded, THE Code_Splitter SHALL load the Plotly.js dependency only at that point (not in the initial bundle).

### Requirement 8: Path Alias Configuration

**User Story:** As a developer, I want a `@/` path alias that maps to `./src/`, so that deep relative imports are replaced with clean absolute-style imports.

#### Acceptance Criteria

1. THE Path_Resolver SHALL configure `resolve.alias` in `vite.config.ts` to map `@/` to `./src/`.
2. THE Path_Resolver SHALL configure matching `paths` in `tsconfig.json` with `"@/*": ["./src/*"]`.
3. WHEN a source file uses an import starting with `@/`, THE Build_System SHALL resolve the import to the corresponding file under `./src/`.
4. WHEN the production build is generated with `@/` imports, THE Build_System SHALL resolve all aliased imports and produce a successful build.

### Requirement 9: Standalone ESLint Configuration

**User Story:** As a developer, I want ESLint configured as a standalone tool with flat config format, so that linting is decoupled from CRA and uses current ESLint best practices.

#### Acceptance Criteria

1. THE Linter SHALL use an `eslint.config.js` file in flat config format as the sole ESLint configuration.
2. THE Linter SHALL include TypeScript-aware rules, React plugin rules, and import ordering rules.
3. WHEN `npm run lint` is executed, THE Linter SHALL analyze all `.ts`, `.tsx`, `.js`, and `.jsx` files in the `src/` directory.
4. THE Linter SHALL not depend on `eslint-config-react-app` or any CRA-specific ESLint configuration.
5. WHEN the Linter is executed against the migrated codebase, THE Linter SHALL produce no new false-positive warnings compared to the CRA ESLint baseline.

### Requirement 10: Deployment Compatibility

**User Story:** As a developer, I want the migrated build to deploy correctly to GitHub Pages and Railway, so that existing deployment pipelines continue to work.

#### Acceptance Criteria

1. THE Build_System SHALL configure the `base` option in `vite.config.ts` to match the current GitHub Pages deployment path (`/myAdmin`).
2. WHEN the production build is deployed to GitHub Pages using `gh-pages`, THE Build_System SHALL serve the application correctly with all assets loading from the correct base path.
3. WHEN the production build is deployed to Railway, THE Build_System SHALL serve the application correctly with environment-specific configuration.
4. THE Build_System SHALL provide a `vite preview` script in `package.json` for local production build testing.

### Requirement 11: Functional Parity Verification

**User Story:** As a developer, I want to verify that the migrated application behaves identically to the CRA build, so that no runtime regressions are introduced.

#### Acceptance Criteria

1. WHEN the application is built and served, THE Build_System SHALL render all pages identically to the CRA build (no visual regressions).
2. WHEN a user authenticates via AWS Cognito, THE Build_System SHALL complete the full authentication flow (login, token refresh, logout) without errors.
3. WHEN the application makes API requests through the proxy, THE Build_System SHALL deliver requests to the backend and return responses to the frontend without modification.
4. THE Build_System SHALL preserve all existing Playwright end-to-end tests without modification (Playwright tests are build-tool agnostic).
5. WHEN the production bundle is analyzed, THE Build_System SHALL produce a bundle treemap via `rollup-plugin-visualizer` for size inspection.

### Requirement 12: Bundle Analysis and Optimization

**User Story:** As a developer, I want visibility into the production bundle composition, so that I can identify optimization opportunities after migration.

#### Acceptance Criteria

1. THE Build_System SHALL include `rollup-plugin-visualizer` as a dev dependency for bundle analysis.
2. WHEN a production build is generated with the visualizer enabled, THE Build_System SHALL produce an HTML treemap showing bundle composition by module.
3. WHEN route-based code splitting is active, THE Build_System SHALL produce separate chunks visible in the bundle treemap for each lazy-loaded route group.
