import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactPlugin from "eslint-plugin-react";
import reactHooksPlugin from "eslint-plugin-react-hooks";
import importPlugin from "eslint-plugin-import-x";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx,js,jsx}"],
    plugins: {
      react: reactPlugin,
      "react-hooks": reactHooksPlugin,
      "import-x": importPlugin,
    },
    languageOptions: {
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: "detect" },
    },
    rules: {
      // React and TypeScript baseline rules
      "react/react-in-jsx-scope": "off",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-require-imports": "off",
      // Rules from typescript-eslint/recommended not in CRA baseline
      "preserve-caught-error": "off",
      "@typescript-eslint/ban-ts-comment": "off",
      "@typescript-eslint/no-unused-expressions": "off",
      "no-useless-assignment": "off",
      "import-x/order": [
        "warn",
        {
          groups: [
            "builtin",
            "external",
            "internal",
            "parent",
            "sibling",
            "index",
          ],
          "newlines-between": "never",
        },
      ],
    },
  },

  // ---------------------------------------------------------------------------
  // Recurring-issue gate #1: frontend data-fetch bypass.
  //
  // Everything under `src/` except the service layer MUST route backend calls
  // through `services/apiService` (or a sibling service in `services/`). They
  // must NOT
  // (a) call `fetch(...)` directly against the API, (b) call `axios.*(...)`
  // directly, nor (c) hand-build a base URL from `import.meta.env.VITE_API_URL`
  // / a bare `API_URL`.
  //
  // Scope: everything under `src/**` OUTSIDE `src/services/`. The apiService
  // migration dropped the direct-fetch bypass from 33 -> 2 sites and is now
  // fully landed (2026-10-28 scan: the only remaining non-service `fetch` is an
  // exempt `*.example.tsx` demo). This guard locks in the win so no component,
  // page, hook, util, context, config, shared helper, or top-level `src/*`
  // module can reintroduce a raw fetch/axios/base-URL call. The `services/`
  // layer legitimately owns the one real `fetch`/`axios`/base-URL construction,
  // so it is excluded via `ignores` below and stays exempt.
  //
  // Allow-list (in `ignores`): `src/services/**`, `*.example.{ts,tsx}` demo
  // files, and test files (`**/*.test.{ts,tsx}`, `**/*.spec.{ts,tsx}`,
  // `src/tests/**`, `**/__tests__/**`, `**/__mocks__/**`).
  // `pages/public/PublicLandingPage.tsx` is NOT excluded: its one real `fetch`
  // was migrated into `services/publicLandingService.ts`, so it is clean here.
  //
  // Widened 2026-10-28 (code-quality-fixes-2026-10-28 task 2) from the original
  // four-folder scope (components/pages/hooks/utils) to all of `src/**` minus
  // the service layer, so the "no raw fetch outside src/services/" discipline
  // cannot be sidestepped by landing a fetch in src/context, src/config,
  // src/shared, or a top-level src/*.tsx.
  // ---------------------------------------------------------------------------
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [
      "src/services/**",
      "**/*.test.{ts,tsx}",
      "**/*.spec.{ts,tsx}",
      "**/__tests__/**",
      "**/__mocks__/**",
      "src/tests/**",
      "**/*.example.{ts,tsx}",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='fetch']",
          message:
            "Do not call fetch() directly here. Route backend calls through services/apiService (authenticatedGet/Post/Put/Delete) so auth headers, tenant scoping, and token refresh are handled consistently.",
        },
        {
          selector: "CallExpression[callee.object.name='axios']",
          message:
            "Do not call axios.*(...) directly here. Route backend calls through services/apiService; the HTTP client belongs to the services layer only.",
        },
        {
          selector:
            "MemberExpression[property.name='VITE_API_URL']",
          message:
            "Do not hand-build API URLs from import.meta.env.VITE_API_URL here. Use services/apiService / buildApiUrl; the base URL belongs to the services/config layer only.",
        },
      ],
    },
  },

  {
    ignores: ["build/**", "node_modules/**", "public/**"],
  }
);
