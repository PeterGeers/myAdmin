# Frontend UI Standards — Reconciling the Two Design Systems

> Companion to `frontend_merge.md`. That doc covers **tooling convergence** (React
> 18→19, CRA→Vite, matching package versions). This doc covers what it does not:
> the **generic UI standards** the merged product should follow — component
> conventions, theming/design tokens, accessibility, i18n, type-safety, and
> frontend testing. Analysis only; no code changed. Based on a read-only comparison
> of both repos' `.kiro/steering/` UI files (h-dcn: `look-and-feel.md`, `i18n.md`,
> `table-framework.md`, `type-safety.md`, `testing-frontend.md`; myAdmin:
> `ui-patterns.md`, `testing-frontend.md`).

## Why this needs its own attention

The merge is a genuine *design-system reconciliation*, not a blank page. Both
frontends descend from the same lineage, so their UI standards are already close —
but "close" across two separately-shipped apps still means one merged bundle that
looks and behaves like two apps unless the standards are deliberately unified. The
good news: most conventions already agree and can be adopted nearly intact. The
work is (a) picking a winner where they diverge, and (b) making H-DCN-specific
brand/vocabulary **tenant-neutral**, because this is a multi-tenant platform where
no single tenant's colors or status words should be hardcoded.

Pattern we follow (as elsewhere in this analysis set): **this doc = reasoning +
open decisions; steering = the settled rules.** Once the decisions below are made,
distil the settled parts into `ui-standards.md` (+ likely `i18n.md`) steering,
scoped `inclusion: fileMatch` to the frontend subtree.

## Shared baseline (both repos already agree — adopt nearly intact)

These are near-identical in both `look-and-feel.md`/`ui-patterns.md`, so they carry
into the platform with little more than tenant-neutralizing the wording:

- **Component library:** Chakra UI v2 + Emotion 11 (confirmed aligned in
  `frontend_merge.md`). Use Chakra components and theme tokens — no custom CSS.
- **Action buttons:** no action buttons in table rows; row click opens a modal for
  edit/delete/detail; primary actions (Add, Export, Import) in the page header row,
  right-aligned; `colorScheme="orange"` primary, `variant="ghost"` secondary.
- **Tables:** Chakra `Table variant="simple"` on dark background; sortable headers;
  hover-highlighted rows (`_hover={{ bg: 'gray.700', cursor: 'pointer' }}`); status
  as `Badge`, read-only data in cells; `overflowX="auto"` wrapper; hide
  non-essential columns on mobile (`display={{ base: 'none', md: 'table-cell' }}`).
- **Modals:** Chakra `Modal` for all CRUD; Formik + Yup inside; Cancel (left, ghost)
  + Save/Submit (right, orange solid); loading state on submit;
  `closeOnOverlayClick={false}` for edit modals, `true` for read-only detail.
- **Filters:** the shared Table Filter Framework — `FilterableHeader` (text search
  in column headers) + `FilterPanel` + `GenericFilter` (dropdowns above table), with
  `useTableSort` (asc → desc → none, nulls sort to end) and a reset/clear-all
  control. Both repos already standardize on this; do not hand-roll filter/sort.
- **Responsive:** Chakra responsive props (`{{ base, md }}`); touch targets ≥ 44px;
  16px minimum input font on mobile (prevents iOS zoom); headers use
  `Flex wrap="wrap"` rather than rigid `HStack`.
- **Forms:** Formik + Yup for form UI/validation; visual field-state cues
  (editable vs read-only) rather than text badges; help via placeholder/tooltip,
  not persistent text under fields.

h-dcn's `look-and-feel.md` is the richer of the two (it adds a typography scale,
icon-color-per-action vocabulary, and explicit WCAG AA). Take h-dcn's depth as the
base and fold myAdmin's `ui-patterns.md` into it — they do not conflict on any of
the above.

## Decisions to make (where the two diverge, or where multi-tenancy intervenes)

### D1 — Tenant-neutral theming + per-tenant branding (DECIDED)

h-dcn's design system hardcodes **H-DCN Orange `#f56500`** as the primary brand
color and a **club-specific status vocabulary** (member states Actief/Aangemeld/
Opgezegd; membership types Erelid/Donateur/Sponsor with fixed colors). On a
multi-tenant platform this cannot be a platform default.

**Decision:** a **tenant-neutral base**, with **per-tenant branding (theme + logo)
applied when a tenant is active.**

- Brand color(s) and semantic status palettes are **theme tokens resolved per
  tenant** — a tenant theme layer over a neutral Chakra base — never literals in
  components. Keep the *structure* of the design system (token names, scale,
  contrast rules); make the *values* tenant-supplied with a neutral default.
- **Tenant logo in the header when a tenant is active.** The header shows the
  active tenant's logo; the same per-tenant theme layer drives it (logo is just
  another branding asset alongside the color tokens). One mechanism, not a separate
  feature.
- Domain-specific status vocabularies (member/membership badges) belong to the
  portal domain and its tenants, not to the platform-wide standard. The standard
  defines *how* a status badge looks and behaves (colors from tokens, WCAG AA), not
  the specific words/colors of one club.

**How "active tenant" resolves (differs by pool):**

- **Pool A (admin/staff)** users may belong to several tenants, so active tenant is
  a *selection* (myAdmin already has a `TenantSelector`). Switching tenant switches
  the header logo + theme. Before selection / on cross-tenant sysadmin views, render
  the neutral base with no tenant logo.
- **Pool B (end-users)** have a single `tenant_id`, so branding is *fixed* to their
  one tenant — resolved at login, no selector.
- **Platform / pre-tenant screens** (login before tenant is known, platform admin):
  neutral base, no tenant logo.

**Where branding data lives:** as tenant metadata, reusing what already exists — a
**logo asset** in the tenant's S3/branding area (myAdmin's shared bucket already
holds branding; `migration_plan.md`) and a small **theme-token set** on the tenant
record (alongside `tenant_template_config` / tenant metadata in MySQL, projected to
the portal side as needed). No new datastore.

**Guardrails / remaining sub-questions:**

- **Accessibility is non-negotiable regardless of tenant colors** — WCAG AA contrast
  must hold for any tenant palette. This argues for **constrained presets or
  validated palettes** rather than arbitrary free-form tenant color input.
  (Sub-decision: presets vs validated-custom.)
- Logo constraints: allowed formats, max dimensions, light/dark variants, and a
  neutral placeholder when a tenant has not uploaded one.

### D2 — i18n key conventions (DECIDED)

The two repos looked like a head-to-head conflict, but they actually decide on
**three separable axes** — naming, structure, and access ergonomics — and the
"conflict" only exists on the first two:

- **h-dcn** (`i18n.md`, enforced by tests): `snake_case`, **max nesting depth 2**,
  `nl` is reference/fallback, 8 locales, dual-location files (`src/locales` +
  `public/locales` kept byte-identical).
- **myAdmin** (`ui-patterns.md`): category dot-notation like `common:buttons.save`
  (`buttons`/`labels`/`messages`/`titles`), accessed via a `useTypedTranslation`
  typed wrapper.

**Decision:** adopt **h-dcn's key convention** (naming + structure) **AND myAdmin's
typed wrapper** (ergonomics). They compose — the wrapper sits on top of whatever key
space is chosen, so it is not a rival to the naming/structure choice.

- **Naming / structure → h-dcn.** snake_case, max depth 2 (`group.key`), `nl` as
  reference/fallback, dual-location byte-identical sync — all **test-enforced**
  (`translationFileConventions.test.ts`, `localeSync.property.test.ts`).
- **Ergonomics → myAdmin.** Adopt `useTypedTranslation` over the h-dcn key space for
  compile-time safety (typos / missing namespaces become TS errors, not silent
  runtime fallbacks).

**Why h-dcn wins naming/structure:**

1. **Enforced, not aspirational.** h-dcn's rules are backed by tests; myAdmin's live
   only in prose. Evidence it matters: myAdmin's own `workflows` namespace drifted to
   camelCase + depth-3 — exactly the drift h-dcn's test catches. Enforced beats
   documented.
2. **Depth-2 is a feature.** Flat `group.key` files stay diffable, make the
   reference-locale completeness check trivial, and avoid the "where does this key
   live" hunt. Deep nesting rots across 8 locales.
3. **snake_case is the lower-friction default for i18n JSON** (keys are data, not
   code identifiers) and is what the h-dcn tooling already validates.

**Cost (asymmetric, accepted):** h-dcn keys already conform and drop in.
**myAdmin's keys must be conformed on lift** — rename any camelCase, flatten any
depth-3 (the `workflows`-style cases), and update the `t(...)` call sites — done as
part of lifting the admin frontend. Do **not** inherit h-dcn's known `workflows`
violation. The alternative (adopt myAdmin's convention) would flip the cost to
h-dcn *and* discard h-dcn's test enforcement — strictly worse.

### D3 — Admin-plane translation scope (DECIDED)

h-dcn's rule is **"Admin panel stays Dutch-only"** (language selector hidden there).

**Decision: the entire platform is translatable — the admin plane included. There
is no Dutch-only plane.**

Rationale: "admin stays Dutch-only" was a **tenant-specific artifact** of H-DCN
being a single Dutch club, not a platform principle. A multi-tenant SaaS serving
tenants beyond one Dutch club (e.g. myAdmin's finance tenants) can never bake one
tenant's language into a whole plane. Language is a **per-user / per-tenant
setting** (D4 preference resolution), never a plane-level constant. The i18n
standard applies uniformly to both planes.

**Cost (accepted) — verified state of each repo:**

- **myAdmin (→ admin plane) is already internationalized.** Verified: its frontend
  configures **`nl` + `en`** (i18next, language detection, localStorage
  persistence), uses `useTypedTranslation`, and already has an externalized
  **`admin`** namespace (`admin.json` in both locales) plus translation property
  tests. So admin strings are **already keys, not hardcoded Dutch.** Its cost is the
  **D2 conform pass** (align to snake_case/depth-2 where it differs) and extending
  from 2 locales to the platform locale set (D4) — not a from-scratch
  externalization.
- **h-dcn is the one with the Dutch-only rule** — but scoped to its **admin-panel
  pages** (its member-facing portal is fully translated across 8 locales). The
  un-externalized strings live in h-dcn's admin-panel screens. If/when those screens
  land in the translatable platform, **those** are what need externalizing +
  conforming (D2) + adding to the reference locale.

Net: the externalization work is smaller and differently located than first stated
— myAdmin's admin frontend does not need externalizing (only conforming), and the
real externalization debt is h-dcn's admin-panel screens. Both are handled during
their respective lifts, in the same pass as D2.

### D4 — Locale set and formatting (DECIDED)

**Decision: separate two kinds of "language" and treat them differently.** The trap
is conflating platform UI chrome with tenant content — a single tenant's one-time
foreign-language workshop must never force a new platform-wide locale.

**1. Platform UI chrome** — buttons, menus, form labels, validation, the shared
shell (the app itself; the layer the i18n conventions in D2 govern).

- **Chrome locale set: `nl` + `en` for now** (`nl` reference, `en` fallback).
  Narrow and fixed. Every chrome string must exist in every supported chrome locale,
  so adding one is real work (translate the whole app).
- **Not frozen — grows deliberately on real demand.** If tenants flow in from, e.g.,
  Germany or Sweden, the chrome set is **extended as a considered platform decision**
  (`de`, `sv`, …). This is low-risk: h-dcn already ran the full 8-locale set
  (`nl, en, de, fr, es, it, da, sv`), so those are known-good additions — extending
  chrome is "translate the app into a proven locale," not new architecture.
- The trigger for extension is **aggregate demand across tenants**, never a single
  tenant's one-off need.

**2. Tenant content** — a workshop's title/description/agenda/emails, strings a
tenant authored for their own event. This is **data, not app chrome.**

- Content is **multilingual per item, in the tenant's own data**, independent of the
  chrome set. A record carries translatable fields as a locale→value map, e.g.:

  ```json
  {
    "workshop_id": "...", "tenant_id": "...",
    "content_locales": ["it", "pl", "en"],
    "title":       { "it": "...", "pl": "...", "en": "..." },
    "description": { "it": "...", "pl": "...", "en": "..." }
  }
  ```

- Tenants add **content locales freely, self-service** — no platform code change, no
  new chrome locale, no touching shared translation files. When the workshop ends,
  the data (and its languages) simply go away.
- Fits existing mechanisms: **myAdmin's `tenant_template_config`** (per-tenant JSON
  config) and the **tenant-field overlay** (`tenant_field_config.md`) are the same
  "tenant defines their own fields" shape; portal **DynamoDB** stores a locale→value
  map natively with no schema migration.

**Runtime combination:** page chrome renders in the user's chrome locale (nl/en);
item content renders in the best available *content* locale for that item (attendee
preference if the tenant authored it, else the item's own fallback). A Polish
attendee sees Polish workshop text inside an English UI shell — normal and expected.

**The hard wall (guardrail):** a tenant can add **content** locales freely (their
data); a tenant **cannot** add platform **chrome** locales (platform-wide cost →
platform decision). Promote a chrome locale only when it is broadly demanded.

**Future escape hatch (noted, not built now):** per-tenant *chrome overrides* — a
tenant supplies a partial translation map overlaying the platform chrome for their
users only, falling back to `en`. Covers a tenant wanting some chrome localization
without the platform adopting a full new locale. The content-vs-chrome split already
handles the workshop case without it.

**Formatting (uncontroversial, adopt platform-wide):** `Intl`-based date / number /
currency formatting with the active locale, never hand-rolled; null/unparseable →
empty string (from h-dcn's `i18n.md`).

### D5 — Type-safety + the basic/tenant-specific field model (DECIDED)

*Terminology: `zod` / `io-ts` are TypeScript **runtime** validation libraries —
define a schema once, get a runtime check plus an inferred type. `Yup` (used by both
repos) does the same runtime job but is form-validation-focused and pairs with
Formik. h-dcn's "Yup-only, no zod/io-ts" rule exists to avoid stacking multiple
overlapping validators, not because of any technical limit.*

**Decision:** keep **Yup-only** (no zod/io-ts) and align frontend type-safety with
the **Field Registry + tenant overlay** model already designed in
`tenant_field_config.md`. That model *is* the "basic fields + tenant-specific
fields" flexibility being asked for — it is already the platform's design, not a new
idea.

**How basic vs tenant-specific fields resolve (from `tenant_field_config.md`):**

- **Field Registry = single source of truth** for field names, types, validation,
  permissions (h-dcn already has this: `MEMBER_FIELDS` assembled from group
  partials, with a `FieldDefinition` interface). Keep and extend it — never replace.
- **Base fields** stay static in code and keep h-dcn's strong compile-time types.
  Some are marked `platformCritical` (a tenant may not hide/rename them).
- **Tenant-specific fields** come from a **tenant overlay** that can add / hide
  (non-critical) / override fields. A pure resolver merges `base + overlay →
  resolved registry`; components only ever render the resolved registry.
- **Custom values namespaced** under a single `custom_fields` Map on the record —
  never free-floating top-level attributes.
- For self-service SaaS this is **Option B**: overlay stored as data in a
  `TenantConfig` table, resolved per request; the frontend fetches the resolved
  registry (+ branding, which is where D1's tenant theme/logo also ride) on login.

**What this means for type-safety (the Yup-only rule holds):**

- **Basic fields:** static TS types + Yup — unchanged, fully compiler-checked. Yup
  rule holds.
- **Tenant fields:** cannot be static types (unknown at build time — the platform
  compiles once, serves all tenants). They are described by the overlay's
  `FieldDefinition` metadata at runtime, and their **Yup schema is generated
  programmatically from each field's `validation` metadata** when the form loads.
  Still Yup — no second validator needed.
- **No zod/io-ts.** The registry already carries type + validation metadata, so a
  runtime-schema library would duplicate it. Escape hatch unchanged from
  `type-safety.md`: revisit only if dynamic-schema handling in Yup becomes genuinely
  unreadable.
- Backend always re-validates (base fields vs base `UPDATABLE_FIELDS`;
  `custom_fields` vs the tenant overlay) — the frontend is never trusted to define
  which fields exist.

**Field Registry question — resolved:** yes, the Field Registry carries into the
platform as a first-class concept; it is the mechanism that delivers the
basic/tenant-specific split and stays the single source of truth for both types and
validation. See `tenant_field_config.md` for the full overlay/resolver design and
the Option A vs B storage choice.

### D6 — Frontend testing stack (DECIDED — Vitest)

The repos differ today, but the roadmap already picks the winner:

- **h-dcn:** react-scripts/Jest (`--watchAll=false`, `--testPathPattern`, known
  full-suite Babel issues; use `tsc --noEmit` for fast type checks).
- **myAdmin:** **Vitest 4.x** + jsdom + React Testing Library + fast-check, with a
  centralized Chakra mock and `render` from `@/test-utils`.

Because roadmap **S7** moves h-dcn from CRA to **Vite**, the target testing stack is
myAdmin's **Vitest** setup. **DECIDED — Vitest.** Standardize on Vitest 4.x + jsdom +
React Testing Library + fast-check for the merged frontend; carry over myAdmin's
centralized Chakra-mock / `render`-from-`@/test-utils` pattern and MSW-handler
discipline (`vi.*` not `jest.*`). h-dcn's react-scripts/Jest guidance applies only to
h-dcn's live workspace until S7, then retires.

## Suggested shape of the settled standards (once decided)

- **`ui-standards.md`** (steering, `fileMatch` frontend subtree): component
  conventions (tables, modals, buttons, filters, forms), the tenant-neutral theming
  model + token names, accessibility (WCAG AA, aria-labels, touch targets, contrast),
  responsive rules, icon vocabulary. Mostly the shared baseline above, tenant-
  neutralized.
- **`i18n.md`** (steering, `fileMatch`): the key convention (D2: h-dcn keys +
  typed wrapper), locale set + fallback (D4), the rule that the whole platform is
  translatable incl. the admin plane (D3 — no Dutch-only plane), `Intl` formatting,
  and the file-location/sync discipline. Large enough to stand alone rather than
  living inside `ui-standards.md`.
- **`testing-frontend.md`** (steering, `fileMatch`): the Vitest/RTL/fast-check stack
  (D6) and the mock/`test-utils`/MSW discipline.
- **`type-safety.md`** (steering): the frontend validation-layer rules (D5); may
  merge with a broader tech/type-safety file.

## Open items (decide before writing the steering)

1. **D1** — DECIDED: tenant-neutral base + per-tenant theme & header logo when a
   tenant is active. Residual sub-questions only: (a) presets vs validated-custom
   palettes (accessibility driver), (b) logo format/size/variants + placeholder.
2. **D2** — DECIDED: h-dcn key convention (snake_case, depth-2, test-enforced) +
   myAdmin's `useTypedTranslation` wrapper. Cost: conform myAdmin's keys on lift.
3. **D3** — DECIDED: whole platform translatable, no Dutch-only plane. Cost
   (verified): myAdmin's admin frontend is already i18n'd (nl+en) — only D2-conform
   + extend locales; the real externalization debt is h-dcn's admin-panel screens.
4. **D4** — DECIDED: chrome = `nl`+`en` now, extended deliberately on aggregate
   demand (e.g. `de`/`sv`); tenant content = per-item multilingual in tenant data,
   unlimited locales, self-service; hard wall between chrome and content; `Intl`
   formatting platform-wide; per-tenant chrome override noted as future.
5. **D5** — DECIDED: Yup-only (no zod/io-ts); Field Registry carries over as the
   base+tenant-overlay model (`tenant_field_config.md`) — basic fields static+typed,
   tenant fields from the overlay with Yup schemas generated at runtime.
6. **D6** — DECIDED: Vitest 4.x + jsdom + RTL + fast-check; myAdmin's Chakra-mock /
   `test-utils` / MSW discipline. h-dcn's react-scripts/Jest retires at S7.
7. Ownership: which tenant/plane owns domain-specific status vocabularies (they
   should NOT sit in the platform-wide standard).

## Relation to the roadmap

- These standards are part of the **frontend track** and should be settled around
  **S7–S9** (React 19+Vite upgrade → shared login/nav → unified SPA). The unified
  SPA (S9) is where a single, reconciled design system actually matters.
- D6 depends on **S7** (Vite migration) for the testing-stack convergence.
- Recording the decisions above as an ADR ("unified frontend design system;
  tenant-neutral theming") fits the keep-governance-current rule when the SPA merge
  lands.
