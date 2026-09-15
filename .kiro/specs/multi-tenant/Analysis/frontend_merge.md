# Frontend Merge — Combining Both SPAs into One

> Can the two React/TypeScript SPAs (H-DCN portal and myAdmin) be combined into
> one SPA? Companion to `myadmin_as_base.md` and `migration_plan.md`. Based on a
> read-only comparison of both `frontend/package.json` files. Analysis only — no
> code changed.

## Short answer

Yes — and more easily than expected. The two frontends are effectively the **same
stack** (strong evidence of shared lineage). The only real obstacles are **React
18 vs 19** and **build tooling (CRA/webpack vs Vite)** — and both are simply
"bring H-DCN up to where myAdmin already is," not a two-way reconciliation.

## Dependency comparison (verified)

| Library | H-DCN | myAdmin | Merge impact |
| --- | --- | --- | --- |
| React / react-dom | ^18.2.0 | ^19.2.0 | **Obstacle** — one SPA runs one React; upgrade H-DCN to 19 |
| Build tool | react-scripts 5 (webpack/CRA) | Vite ^8 | **Obstacle** — one pipeline; migrate H-DCN to Vite |
| `@chakra-ui/react` | ^2.8.2 | ^2.8.2 | **Identical** — no UI reconciliation |
| `@chakra-ui/icons` | ^2.2.4 | ^2.2.4 | Identical |
| `@emotion/react` / `styled` | ^11.11 | ^11.11 | Identical |
| framer-motion | ^10.16 | ^12.23 | Minor peer bump only |
| aws-amplify | ^6.15 | ^6.16 | Same major — one login/token |
| Formik / Yup | 2.4 / 1.3 | 2.4 / 1.7 | Same major |
| i18next / react-i18next | 23 / 14 | 25 / 16 | Same family, minor bumps |
| axios | ^1.13 | ^1.12 | Same major |
| recharts | ^3.6 | ^3.3 | Same major |
| TypeScript | ^4.9 | ^5.9 | Bump with the React 19 work |

Takeaway: **auth, UI library, theme/styling, forms, i18n, HTTP, and charts all
match or nearly match.** The scariest unknown (different UI libraries) is
resolved — both are Chakra v2 + Emotion 11, so components and theme drop in
together cleanly.

## The two real obstacles (both one-directional)

1. **React 18 → 19.** A single SPA runs one React version. Combining means
   upgrading H-DCN from 18.2 to 19.2 to match myAdmin. Major-version upgrade with
   breaking changes → needs regression testing, but **Chakra v2 runs on both React
   18 and 19**, so the UI layer will not fight the upgrade.

2. **CRA/webpack → Vite.** A single SPA has one build. Direction: migrate H-DCN
   off react-scripts onto Vite (myAdmin already uses it — the modern choice).
   Mostly mechanical; the main effort is env-var handling
   (`process.env.REACT_APP_*` → `import.meta.env.*`), which per the guardrails
   must stay **fail-fast** (throw on missing critical vars, no dangerous
   fallbacks).

Both obstacles are "upgrade H-DCN to where myAdmin already is" — a consistent,
one-way move, not reconciling two divergent decisions.

## Options

### Option 1 — One true unified SPA (single build, single React)
Standardize on **React 19 + Vite + Chakra v2**, upgrade H-DCN to match, merge into
one app with routing between the two domains' screens.
- **Pro:** one deploy, one bundle, seamless navigation, shared components; with
  Chakra/Emotion/Amplify already aligned, this is mostly routing + folder
  integration rather than a rewrite.
- **Con:** requires the React 19 upgrade + Vite migration on H-DCN first. A real
  project, but well-scoped and low on unknowns now.

### Option 2 — Micro-frontends / Module Federation (two builds, one shell)
Compose two separately-built apps at runtime under one shell + one login.
- **Pro:** avoids a big-bang upgrade; domains stay independent.
- **Con:** added architectural complexity; sharing one React instance across
  federated apps is finicky. Given how aligned the stacks already are, this buys
  little over just doing Option 1 eventually.

### Option 3 — Two SPAs, one login, unified by navigation (lightest)
Keep two deployed SPAs that share the one Cognito pool/token (already the plan),
stitched with a shared top nav so it *feels* like one product.
- **Pro:** by far the least work; no React/Vite reconciliation; ships now. Token
  flows between them because it is the same pool.
- **Con:** two bundles; a full page transition when crossing domains; some
  duplicated shell/nav code.

## Recommendation (staged)

1. **Now — Option 3: shared Cognito login + shared top nav.** Low-risk, ships
   fast, delivers most of the "one product" feel. Depends only on the unified pool
   already in `migration_plan.md` / `myadmin_as_base.md`.
2. **Next — upgrade H-DCN to React 19 + Vite as its own step.** Independently
   valuable (modernizes H-DCN's tooling) and it is the pivotal enabler for a clean
   merge. Doing it standalone de-risks the merge.
3. **Then — Option 1: merge into one SPA.** Once both apps are on
   React 19 + Vite + Chakra v2, combining is about as smooth as a two-app merge
   gets: routing + folder integration, shared theme and components, one login.

## Why the end state is now low-risk

Because the two apps already share Amplify v6, **Chakra v2 + Emotion 11**, Formik,
Yup, i18next, axios, and recharts, a full merge has **no UI-library or auth
reconciliation** — the classic hard parts of merging two frontends. The entire
remaining cost is concentrated in two well-understood, independently-valuable
upgrades to H-DCN (React 19, Vite). That is an unusually favorable position for a
frontend merge.

## Open items to confirm before Option 1

- H-DCN React 19 upgrade: audit for React-18-only patterns / deprecated APIs.
- Vite migration: enumerate all `process.env.REACT_APP_*` uses (guardrails note
  they are scattered) and map to `import.meta.env` with fail-fast checks.
- Theme reconciliation: both use Chakra v2, but confirm the two custom themes
  merge (or namespace) without clashing.
- Routing: pick one router and a top-level route split by domain
  (portal vs admin).
