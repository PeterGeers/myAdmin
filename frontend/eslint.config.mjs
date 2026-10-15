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
  // Components / pages / hooks / utils MUST route backend calls through
  // `services/apiService` (or a sibling service in `services/`). They must NOT
  // (a) call `fetch(...)` directly against the API, (b) call `axios.*(...)`
  // directly, nor (c) hand-build a base URL from `import.meta.env.VITE_API_URL`
  // / a bare `API_URL`.
  //
  // Scope: everything OUTSIDE `src/services/`. The apiService migration dropped
  // the direct-fetch bypass from 33 -> 2 sites; this guard locks in the win so
  // new components can't reintroduce a raw fetch/axios call. The `services/`
  // layer legitimately owns the one real `fetch`/`axios`/base-URL construction,
  // so it is NOT in `files` below and stays exempt.
  //
  // Allow-list (NOT in `files` / in `ignores`): `src/services/**`,
  // `*.example.{ts,tsx}` demo files, and test files
  // (`**/*.test.{ts,tsx}`, `src/tests/**`, `**/__tests__/**`, mocks).
  // `pages/public/PublicLandingPage.tsx` is no longer excluded: its one real
  // `fetch` was migrated into `services/publicLandingService.ts` (task 3), so
  // it is now clean under this rule.
  // ---------------------------------------------------------------------------
  {
    files: [
      "src/components/**/*.{ts,tsx}",
      "src/pages/**/*.{ts,tsx}",
      "src/hooks/**/*.{ts,tsx}",
      "src/utils/**/*.{ts,tsx}",
    ],
    ignores: [
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
