# S5 — Members-first migration plan (h-dcn → myAdmin platform)

- Status: Draft (the plan; each step becomes tasks when executed)
- Companion: `members-wireframe.md` (current-state scope of the app being migrated).
- Decision of record: ADR 0003 (platform base + SAM-backed modules), ADR 0004
  (verified-JWT-only), ADR 0005 (two-pool identity + MySQL SoR + projection), ADR 0006
  (entitlement-in-token; functions available for adoption).
- Governing user directions (this plan implements them):
  1. **Members is the first app to migrate**, done in independently-deployable steps.
  2. **New tables** for the migrated app so the **existing h-dcn keeps running** in
     parallel — no big-bang, no breaking the live app.
  3. Use **myAdmin's proper app tooling** (module registry, `tenant_modules` entitlement,
     the `sam/shared` verified-auth + entitlement toolkit, the S3 projection, `LeadingKeys`).
  4. The AWS-footprint consolidation (S3/SNS/SES/DynamoDB → shared portal account) is
     **deferred until AFTER this first migration** proves the pattern.
  5. The first migration ends at an explicit **Go / No-Go** decision point for further
     migrations, plus a **lessons-learned** capture.

## Principle: parallel-run, additive, reversible

The migrated Members app is built **alongside** the live h-dcn Members app, reading/writing
**new tenant-scoped tables**, entitled through myAdmin's module system. The live h-dcn app
is untouched and keeps serving members throughout. At each step we can stop and still have a
working live app. Nothing is cut over until the Go/No-Go gate says so.

## Design target (best practice from the start — no double steps)

h-dcn's Members backend is ~18 one-Lambda-per-action handlers. That granularity is a
learning-curve artifact (h-dcn was the first Kiro/TS/Python/AWS project), **not** a design
to preserve. The migration goes **straight to the best-practice shape** — we do not port
18 handlers 1:1 and then refactor (that would be double work). The target:

- **Members is ONE module.** A single SAM-backed deployable — a thin Members API Lambda
  with **internal routing** by method/path (create/get/list/update/delete/export,
  memberships, transitions, delegates, payments) — mirroring how myAdmin's Flask modules
  already work (one app, many routes). The verified-auth + entitlement toolkit is adopted
  **once**, not 18 times; the auth→validate→CORS→response boilerplate exists in one place.
- **Reuse** h-dcn's *business* logic (regional access, membership workflow rules,
  response shapes) — that is real domain value. **Replace** the structure (18 Lambdas →
  one module) and the auth layer (unverified `extract_user_credentials` → myAdmin verified
  `sam/shared`).
- **New tenant-scoped tables** so live h-dcn keeps running unchanged; nothing cut over
  until the Go/No-Go gate.

## The steps (each independently deployable)

### Step 1 — Design the consolidated Members module + its tenant-scoped data model
- Define the single Members module: its internal routes (the union of the 18 handlers'
  behaviours), the reused business rules (regional access, workflow), and the new
  tenant-scoped DynamoDB table design (PK `tenant_id`, SK member/membership id; counters
  + member-payments as needed), `LeadingKeys` IAM. One deployable unit, myAdmin module
  tooling. This is design/spec, deployable as the module skeleton.
- **Fixed vs. variable fields (data-model principle — see `members-wireframe.md`).** Design
  the member data model in two layers from day one:
  - **Fixed (platform base registry):** **personal data** + **membership data** — the same
    for every tenant, first-class attributes of the tenant-scoped `members` table, with
    canonical field keys/validation from the base registry.
  - **Variable (per-tenant overlay):** **club details** (h-dcn's Motor/region/club-specific
    fields) resolved per `tenant_id` via the per-tenant field-config mechanism
    (myAdmin `tenant_template_config` / `FieldConfigMixin` + h-dcn's hybrid field registry),
    applied over the fixed core — so a second tenant later needs a new overlay, **not** a
    schema change.
  - Split h-dcn's existing member fields accordingly (personal+membership → fixed base;
    club/Motor/region-specific → variable overlay). **Tenant `h-dcn`** is the first overlay.
- **Lidmaatschap Beheer (membership-type catalog) — new coupling (see
  `generic-membership-design.md`).** Add a tenant-scoped **managed catalog of membership
  types** as a fixed-domain entity (`tenant_id` PK + `LeadingKeys`; entries carry
  `code`/`label`(i18n)/`active`/order). The member record's **`membership_type` field
  references this catalog**, so the member-type input is a **dropdown listing only that
  tenant's Lidmaatschap Beheer entries** — not the free/hardcoded value h-dcn uses today.
  h-dcn seeds its own types as data; the domain layer authoritatively validates the
  reference (soft-delete via `active=false` to avoid orphaning historical members). Catalog
  CRUD routes follow the same read/write split as the member routes (read in Step 3, write
  in Step 5).

### Step 2 — Register Members as a myAdmin module (entitlement plumbing)
- `members` entry in `MODULE_REGISTRY` (backing: sam) + entitle the pilot tenant via
  `tenant_modules`; confirm the S3 projection carries the tenant's `members` module +
  roles and `get_entitlements`/`has_capability` answer for `members`. **Deployable/reversible.**

### Step 3 — Stand up the Members module (read path) on myAdmin tooling
- Build the single Members Lambda with internal routing for the READ routes
  (`get_member*`, lists, export), using the vendored `sam/shared` verified-auth +
  entitlement toolkit **once**, reusing h-dcn's regional-access business logic, reading
  the new tenant-scoped tables (`tenant_id` partition + `LeadingKeys`). API contract the
  frontend expects is preserved. **Deployable** (read module + pilot/shadow route);
  **reversible** (pilot route only; live h-dcn untouched).

### Step 4 — New tenant-scoped tables + backfill (parallel to h-dcn's)
- Create the new tables (data account, PAY_PER_REQUEST, outside-CFN/retain per
  `aws-accounts.md`). Backfill existing member records stamped with the pilot `tenant_id`
  (dry-run first; the h-dcn `migrationHDCNLedenbestand` import is prior art). The live
  h-dcn `MembersTable` is untouched. **Deployable/reversible** (new tables are a copy).

### Step 5 — Members module write path + workflow
- Add the WRITE/lifecycle routes to the module (create/update/transition/delegates/
  memberships) on the tenant-scoped tables + verified auth, reusing h-dcn's workflow
  rules. **Deployable per route group; reversible.**
- **No dual-write / no read-replica-until-cutover needed.** h-dcn Members is **not** a live
  production system — it runs for **demo purposes only**, and the real member data lives in
  a **Google Sheet** (the SoR outside both apps). There is no production traffic to keep in
  sync and no live app to fall back to, so the migrated module can write directly to the
  tenant-scoped tables without a parallel-write or replica strategy.

### Step 6 — Exercise the migrated module (workflow + look & feel review)
- Use the migrated Members module end-to-end for the pilot tenant to see **how the app
  works** and evaluate the **look and feel** — walk the read + write/lifecycle routes,
  confirm authz (incl. regional), data, API contract, and workflow behave as intended.
- This is **not** a production cutover with a soak against live traffic (h-dcn Members is
  demo-only; real data stays in the Google Sheet). It is a hands-on validation of the
  migrated app's behaviour and UX to inform the Go/No-Go review.
  **Deployable; reversible.**

## The Go / No-Go decision point (end of the first migration)

After Step 6's hands-on validation, hold an explicit **Go / No-Go** review for migrating further apps
(Events, Webshop). Decide against concrete criteria captured during the pilot:

- **Parity:** migrated Members reproduces h-dcn's behaviour (authz incl. regional, data, API
  contract, workflow) for the pilot tenant — verified via the Step 6 hands-on review, not a
  live-traffic soak.
- **The toolkit held:** the myAdmin verified-auth + entitlement + projection + tenant-scoping
  tooling was sufficient — what was reusable as-is, what needed change (feeds the roadmap).
- **Look & feel / UX:** the migrated app behaves and presents as intended during the
  hands-on walkthrough (Step 6).
- **Operational:** deploy/rollback per step worked; the auth path (incl. the cross-account
  Pool A PreTokenGen trigger, if wired for the pilot) behaved and logins were not broken.
  Latency/cold-start are noted as observations, not a production budget — there is no live
  traffic to soak against.
- **Effort/ROI:** actual effort per step vs. estimate → is app-by-app migration worth
  continuing, or should the approach change?

Outcome is recorded (Go → proceed to the next app with the refined tooling; No-Go →
document why + what would change the decision) in `go-no-go.md` (a deliverable of the
pilot), with **lessons learned** feeding a roadmap revision.

## The steps after the gate

### Step 7 — (Conditional) wire the live Pool A PreTokenGen trigger
- **Only if the pilot needs live-token entitlement.** Otherwise the module uses its
  authoritative fallback and runs auth against the test pool — skip this step. The
  entitlement functions (resolver, codec, PreTokenGen Lambda) are already built + tested;
  this step is integration, not new build.
- **Prerequisite:** widen the S3 projection to carry h-dcn's governance (today gated to
  SAM-backed tenants); empty projection → empty entitlement stays a valid handled outcome.
- Attach the Lambda **cross-account** to live Pool A, **validated on the test pool first**,
  with **detach-to-rollback** and no broken logins. Highest blast radius (production login)
  — hence done **after** the gate. **Reversible** (detach).

### Step 8 — Governance update on completion
- Record the generic membership model, the scope-dimension generalization, the
  fixed/variable field model, and the **Lidmaatschap Beheer membership-type catalog
  coupling** in steering + an ADR — the next-app migration template. **Additive** (docs).

## What this migration deliberately defers

- **AWS-footprint consolidation** (move myAdmin's S3/SNS/SES/local-DynamoDB + shared
  services into the shared portal/data account) — **after** this first migration, informed
  by it. Not a prerequisite.
- **Production Pool A PreTokenGen trigger** (S4 T18) — **not** deferred indefinitely but
  **conditional**: it is **Step 7** above, run only if/when the pilot needs live token
  entitlement. The functions are already built + tested; the pilot can run against the test
  pool first.
- **Events / Webshop** migrations — gated behind the Go/No-Go.
- **Frontend consolidation** — the pilot is backend-first; UI stays on h-dcn until parity.

## Tooling this reuses (myAdmin, already built)

- `sam/shared/auth_utils.py` — verified JWT + `get_verified_claims`/`get_groups` +
  `get_entitlements`/`has_capability` (S2 + S4).
- `sam/shared/entitlement_claim.py` — the vendored claim decoder (S4).
- `services/module_registry.py` + `tenant_modules` — module entitlement (S1/S3).
- The S3 one-directional projection + `projection_schema` + `LeadingKeys` plan (S3).
- The S4 entitlement resolver/codec + PreTokenGen Lambda (built + tested; trigger wired in
  the conditional Step 7).

### Frontend + UI framework (reuse, don't rebuild)

The migrated Members UI is composed from myAdmin's existing frontend building blocks
(React 19 + TypeScript + Vite, Chakra UI). Nothing here needs to be rebuilt for Members —
it is adopted the same way any other module does:

- **Filter / table / sort framework** — `frontend/src/hooks/useFilterableTable.ts`
  (composes `useColumnFilters` + `useTableSort`, generic over `T`), plus the filter UI in
  `frontend/src/components/filters/` (`GenericFilter<T>`, `YearFilter`, `FilterPanel`,
  `FilterableHeader`, `types.ts`). Documented in `components/filters/README.md`; spec
  `.kiro/specs/table-filter-framework-v2/design.md`. Member lists/exports use this rather
  than a bespoke table. `FilterErrorBoundary` scopes filter failures.
- **Standard header + generic user/session UI** — `frontend/src/components/MainMenu.tsx`
  (top header bar) composing `UserMenu.tsx` (logged-in user: name/email, roles, tenants,
  environment-mode badge, Settings + Logout), `TenantSelector.tsx`, `LanguageSelector.tsx`,
  and `HelpButton`. Driven by `context/AuthContext.tsx` (`useAuth()`: `user`, role helpers)
  and `context/TenantContext.tsx` (`useTenant()`: current/available tenants). Route
  protection via `components/ProtectedRoute.tsx`; user settings under `components/settings/`.
- **Authenticated API client** — `frontend/src/services/apiService.ts`
  (`authenticatedRequest` + `authenticatedGet/Post/Put/Delete/FormData`). Auto-injects the
  Cognito JWT (`Authorization: Bearer`), `X-Tenant`, `X-Language`, `X-Frontend-URL`; handles
  401 refresh-and-retry. `config/api.ts` holds `API_BASE_URL`. The Members frontend service
  is built on this, not raw `fetch`. (Usage: `services/API_USAGE_GUIDE.md`.)
- **Forms, theming, notifications, errors** — Formik + Yup for forms/validation; Chakra UI
  as the component library with the app theme in `frontend/src/theme.js` (dark + orange
  accent convention); Chakra `useToast()` for notifications (app-wide convention, no custom
  wrapper); `components/ErrorBoundary.tsx` for generic error boundaries. Shared table/CSV
  utilities in `frontend/src/utils/` (`csvExport.ts`, `formatting.ts`).

### i18n (internationalization) standard

- **i18next + react-i18next + i18next-browser-languagedetector**, configured in
  `frontend/src/i18n.ts` (nl/en, `fallbackLng: 'en'`, `defaultNS: 'common'`, detection
  order `['localStorage','navigator']`, key `i18nextLng`).
- Locale files under `frontend/src/locales/{nl,en}/*.json` organized by **namespace**
  (`common, auth, reports, str, banking, admin, finance, errors, validation, zzp, budget`);
  Members adds its own `members` namespace following the same layout.
- Components consume the typed wrapper `hooks/useTypedTranslation.ts`
  (`useTypedTranslation('namespace')`). The API client forwards the active language as the
  `X-Language` header, so backend responses localize too (the Members module honours it).

### Documentation standard (MkDocs)

- End-user docs use **Material for MkDocs**, config `docs/mkdocs.yml` (default language `nl`,
  red palette, nav tabs/sections), with `search` (nl+en), the `i18n` plugin (bilingual
  nl/en builds) and `print-site`. Markdown source in `docs/docs/` organized per module;
  ADRs in `docs/decisions/`; deployed to GitHub Pages.
- Members follows the same standard: a new per-module docs section under `docs/docs/`,
  bilingual, matching the existing module docs. Standards/spec:
  `.kiro/specs/Common/end-user-documentation/`.

### Per-tenant field config (fixed vs. variable overlay — Step 1)

- Backend `backend/src/services/field_config_mixin.py` (`FieldConfigMixin`:
  `get_field_config` / `validate_fields` / `strip_hidden_fields`, levels
  required/optional/hidden; resolution `ParameterService` tenant override →
  `MODULE_REGISTRY` default) + the `tenant_template_config` mechanism. Frontend counterparts
  `services/fieldConfigService.ts` + `hooks/useFieldConfig.ts` (`isVisible`/`isRequired`).
  This is the mechanism behind Step 1's variable per-tenant **club details** overlay over
  the fixed personal+membership core.
