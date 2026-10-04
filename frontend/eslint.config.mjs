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
  // (a) call `fetch(...)` directly against the API, nor (b) hand-build a base
  // URL from `import.meta.env.VITE_API_URL` / a bare `API_URL`.
  //
  // Scope: ONLY the app layers that regressed (Task H1 migrated 32 call sites).
  // The `services/` + `config/` layer legitimately owns the one real
  // `fetch`/base-URL construction, so it is NOT in `files` below and stays
  // exempt. Test files, mocks, and the `examples/` folder are excluded too.
  // `pages/public/PublicLandingPage.tsx` is excluded because its single
  // `fetch` reads a CloudFront static asset (landing.json), not an API call.
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
      "src/components/examples/**",
      "src/pages/public/PublicLandingPage.tsx",
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
