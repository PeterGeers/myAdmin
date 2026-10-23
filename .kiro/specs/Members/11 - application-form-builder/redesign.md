# Application Form Builder — Redesign notes (pick up from here)

> Status: **design agreed, formalized as a spec.** These notes are now written up as a reviewable
> spec at **`.kiro/specs/Members/12 - application-form-serving-redesign/`** (requirements + design +
> tasks). Spec 12 SUPERSEDES the parts of spec 11 named in its "Relationship to spec 11" section
> (the toggle-list/panel authoring UX, the `POST /members/application-preview` endpoint, and the
> `PUBLIC_TENANT_SLUG_MAP` env-map serving) and reuses the rest. This file remains the verified
> evidence trail behind spec 12 — keep it for the "why", build from spec 12's tasks.
>
> This file captures what we VERIFIED (by running
> code / reading the live TEST environment) and the DESIGN DECISIONS the product owner made, so
> the next session starts from facts, not guesses. Nothing here is speculation unless marked.

---

## 1. What is actually broken (verified, not guessed)

The builder was merged to `test` (PR #162) and the application form appeared completely dead
(empty/white, fields saved-but-not-shown, choice selectors never visible, clicking a selected
field did nothing). We ran this to ground. There are **three independent problems**, each proven:

### 1a. Serving / slug resolution — the form is EMPTY in TEST (config-as-infra bug)
- The public form resolves its tenant from a slug via the SAM public Lambda's env var
  `PUBLIC_TENANT_SLUG_MAP`. **On the deployed TEST stack that env var is EMPTY** (verified:
  `aws lambda get-function-configuration members-public-test` → `PUBLIC_TENANT_SLUG_MAP=""`,
  `PUBLIC_FORM_ALLOWED_ORIGINS=""`).
- The value IS correct in source (`sam/members/samconfig.toml [test.deploy.parameters]` sets
  `PublicTenantSlugMap=hdcn:h-dcn`), but the deployed CloudFormation stack parameter is `""`
  (verified via `describe-stacks`).
- **Root cause of the empty deploy:** `deploy-sam-members.yml` line ~115 runs
  `sam deploy --config-env <env> ... $OVERRIDE`, where `$OVERRIDE` (when an OpenRouter key is
  present) is a bare `--parameter-overrides OpenRouterApiKey=...`. A CLI `--parameter-overrides`
  **REPLACES** the whole `samconfig.toml` param set — it does NOT merge — so every other param
  (incl. `PublicTenantSlugMap`) falls back to the template `Default: ""`. Same footgun family as
  the Cognito `update-user-pool` partial-config trap (steering 23).
- Net: slug `hdcn` never resolves → public edge returns non-probeable 404 → empty form.

### 1b. The overlay round-trip is NOT the bug — the data + code are correct (verified)
We nearly "fixed" the wrong thing twice. Proven by execution:
- The stored `config#fields` row for `h-dcn` (read live from `test_governance_projection`,
  keys `tenant_id` + **`sk`**) is CORRECT: every selected base field is under
  `overrides."personal.first_name" = {application_visible: true}` (correct dotted key), tenant
  fields under `fields.{key}`. 15 base overrides + several variable fields, all flags set.
- A SAM repro feeding THAT real row through `MembersProjectionReader.get_overlay` →
  `get_public_field_config` returned **11 fields** correctly. So reader + resolver + filter are
  fine with real data.
- A frontend repro (once the fixture used the REAL server key shape — **bare `key` + separate
  `group`**, NOT a pre-dotted key) showed `ApplicationFieldList` + `overlayModel.upsertField`
  writes a CLEAN overlay with correct dotted override keys + flags. So the write path is fine too.
- **Lesson:** my first repro "found a bug" that was only my wrong fixture (I assumed `key` was
  dotted; the server emits bare `key` + `group`, see `_membership_writes.py` `_serialize_field`
  ~line 1788). The test caught my bad assumption — trust runs, not inference.

### 1c. The authoring UX is genuinely wrong (product-owner judgement, valid)
- Attributes (required / format / enum-subset) are a cramped panel buried under a ~100-field
  list. Should be a **modal on the field**.
- The enum-subset "choice selector" renders for fields that have no choices (e.g. a string field
  like `first_name`) — it must only exist for enum/reference/scope fields.
- The current interaction is "click a boolean to toggle on-form" — but on-form is only half the
  info; clicking a field should open a modal to define ALL its on-form attributes together.

---

## 2. Why option 1 works and option 2 fails (the key insight)

Both the **Field-configuration editor** and the **Application-form builder** author the SAME
record (`config#fields`, same `field_overlay`, same `saveMembersParameter('field_overlay', …)`).

- **Option 1 = `MembersFieldModal`** (737 lines, verified): a mature, CORRECT modal. Writes the
  overlay via `buildField` / `resolveWriteTarget` / `upsertField`. Edits base attributes only
  (`type`, `label`, `order`, `required`, `visible`, `read_only`, `choices` via `EnumOptionsEditor`,
  `scope`). It has **NO** `application_*` attributes today.
- **Option 2 = the Application-form builder** (`ApplicationFieldList` + a bespoke attributes
  panel): REIMPLEMENTED authoring with a boolean-toggle list + panel, and that forked code is
  where the UX bugs live. The backend it writes to is fine.

**Conclusion:** "get option 2 working" = **build option 2's per-field editing on option 1's
proven modal engine**, not on the forked list/panel. Same write logic that already works, plus an
application-form attribute section.

---

## 3. Serving model decision — mirror the landing page (verified pattern)

The landing page works with ZERO request-time slug→tenant lookup (verified):
- Slug stored in Flask/MySQL `tenant_slugs` (Flask-owned); on publish Flask writes
  `landing.json` + `index.html` to `s3://myadmin-public-pages/{slug}/` and invalidates CloudFront.
- The CloudFront url-rewrite function routes `{slug}.jabaki.nl` → `/{slug}/index.html` by pure
  string manipulation. The slug IS the S3 folder. `*.jabaki.nl` is unlimited, no per-tenant infra.

The application form should use the SAME logic instead of the bespoke public-API + env slug-map:
- **Edit → preview → publish → replaces previous version** (the product owner's model, and it is
  the landing-page lifecycle).
- **Preview is in-browser** — the admin is editing the draft in memory, so the preview renders
  that draft directly. This DELETES the fragile `POST /members/application-preview` endpoint, its
  debounce, and the server-filter round-trip.
- **Publish** writes the resolved form config as a static artifact per slug (like `landing.json`),
  served slug-addressed under `*.jabaki.nl`. Retires `PUBLIC_TENANT_SLUG_MAP` and the public-read
  API.
- **Submit (applicant write)** is the ONE irreducible live endpoint: a `POST` to a Lambda that
  resolves the tenant from the slug (from data, not an env map) and stores the application.

A static SPA fully supports enum data entry + POST-to-Lambda — "static" is about serving, not
capability (the existing `ContactBlock` already is a static-served form that submits).

### RESOLVED — application-form slug (was the open question)
The live URL `hdcn-application-form.jabaki.nl` is a **SEPARATE slug** from the landing-page slug
(`hdcn`). This is a deliberate divergence from the landing model, and it CANNOT reuse the
landing `tenant_slugs` table: that table's one-slug-per-tenant limit is a **hard DB constraint**
(`administration VARCHAR(50) NOT NULL UNIQUE`, verified in `backend/sql/create_tenant_slugs_table.sql`),
so a second slug for the same tenant would collide on the unique key and `TenantSlugService.set_slug`
would treat it as a *rename* of the landing slug, not an additional slug. (The slug *string* is free
to differ from the tenant *name* — `slug` and `administration` are independent columns — so a
hyphenated `hdcn-application-form` is a valid slug per `SLUG_PATTERN`; the only problem is *where*
it is stored.)

**Product-owner decisions (agreed):**
- **[1=a] The form slug is stored on the SAM `config#fields` record** (DynamoDB
  `*_governance_projection`, key `tenant_id` + `sk=config#fields`), NOT in Flask `tenant_slugs`.
  That record is a free-form tenant-scoped projection row, so a `slug` field drops in cleanly, the
  form owns its own addressing, and the landing 1-per-tenant limit never applies. Do NOT create a
  parallel slug store — reconcile with `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit`
  (it already owns the slug/KVS projection + hosting story).
- **[2=a] The SAM plane publishes the static form artifact** to the shared public bucket
  (`myadmin-public-pages-{env}/{slug}/index.html` + any `form.json`), because SAM owns the form
  config. This keeps the "no runtime SAM↔Flask communication" constraint clean: Flask owns landing
  pages end-to-end, SAM owns the application form end-to-end, and the two planes share ONLY dumb
  infrastructure — the static S3 bucket and the stateless CloudFront url-rewrite function
  (`public_pages_url_rewrite`, `infrastructure/landing-pages.tf`), neither of which is
  "communication." SAM needs write + CloudFront-invalidate IAM on the public-pages bucket
  (the Flask Railway backend already has the equivalent grant; add the SAM counterpart).

**Why the serve path needs no new infra and no cross-plane traffic (verified):** the landing serve
path is a single `*.jabaki.nl` CloudFront distribution + a stateless string-rewrite function that
maps `{slug}.jabaki.nl/` → `/{slug}/index.html` with NO request-time tenant lookup. The moment SAM
writes `hdcn-application-form/index.html` into `myadmin-public-pages`, that host serves it — same
function, same distribution, zero new per-tenant infrastructure.

**Submit (the one live endpoint) resolves tenant from the slug AS DATA.** The current public edge
(`sam/members/handler/public_app.py`) resolves slug→`tenant_id` via `EnvTenantSlugReader`
(`PUBLIC_TENANT_SLUG_MAP`). The migration target is to swap that env-map reader for a data-backed
resolver that reads the slug off the `config#fields` record — isolated behind the
`TenantSlugReader` protocol, so the swap is localized to `tenant_slug_reader.py` and does not
ripple into the resolver or the edge. Still no call back into Flask.

---

## 4. The agreed redesign (three decisions, each retires a specific bug class)

- **A. Authoring = field-modal UX (reuse option 1's engine).** Keep the Application-form builder
  as its own surface (group ▸ field), but clicking a field opens a MODAL built on
  `MembersFieldModal`'s correct write logic, with an **application-form attributes section** shown
  only when a form is in scope. Retire the boolean-toggle list + bespoke panel.
  → fixes 1c (buried panel, choice-on-string, half-configured boolean) and the forked-write bugs.

  Application-form attributes in the modal (per field):
  - on-the-form (the boolean, now with full context);
  - which enum values are shown — subset picker whose SOURCE adapts to the field kind
    (reference → live catalog e.g. membership_type; scope → the scope dimension's values;
    enum/choices → the field's own options);
  - sequence number of the field within its group;
  - required / filter — only for filterable fields; format checks (IBAN / email) on applicable
    fields;
  - (future) display attributes — explicitly OUT of scope now.

- **B. Frontend works in functional-groups + fields; backend owns storage placement.** The UI
  must stop reasoning about `overlay` / `fixed_overrides` / `writeTarget` / provenance. Reuse the
  proven `upsertField` write (no new bespoke overlay code). Preferred end-state: the server
  accepts a write keyed by field identity and does the storage placement, so the frontend never
  constructs the overlay shape.
  → removes the class of seam-mismatch bugs underneath A.

- **C. Serving = landing-page model (edit → in-browser preview → publish-replaces-live,
  slug-addressed static artifact).** Retire the public-read API slug→tenant env-map and the
  server preview endpoint. Keep one submit endpoint (applicant write), resolving tenant from the
  slug via DATA, never an env/CFN parameter.
  → fixes 1a (empty form) and the preview fragility.

  **Serving ownership (resolved, see §3):** the form slug is a SEPARATE slug stored on the SAM
  `config#fields` record [1=a], and the **SAM plane** publishes the static artifact to
  `myadmin-public-pages-{env}/{slug}/` [2=a] — Flask is NOT involved, preserving "no runtime
  SAM↔Flask communication." Reuse the shared, dumb infra only: the `*.jabaki.nl` CloudFront
  distribution + the stateless `public_pages_url_rewrite` function (no new per-tenant infra, no
  request-time tenant lookup). SAM gains write + CloudFront-invalidate IAM on the public-pages
  bucket (mirror of the Flask Railway grant). Submit swaps `EnvTenantSlugReader`
  (`PUBLIC_TENANT_SLUG_MAP`) for a data-backed resolver reading the slug off `config#fields`,
  localized behind the `TenantSlugReader` protocol.

---

## 5. Immediate vs structural (so the next session scopes correctly)

- **Immediate unblock (optional, NOT the real fix):** the TEST form is empty purely because of
  the CI `--parameter-overrides` replace-not-merge bug (1a). Fixing that workflow so the
  `samconfig.toml` params survive a secret override would make the CURRENT design deploy
  correctly. This is a legitimate CI bug fix regardless of the redesign, and prod has the same
  latent bug (`PublicTenantSlugMap=hdcn:h-dcn` would also deploy empty on any override-carrying
  deploy).
- **Structural fix:** decisions A + B + C above. Overlaps the
  `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit` backlog (it already owns the
  slug/KVS projection + hosting story) — reconcile, do NOT create a parallel slug store.

---

## 6. What is already correct and should be KEPT / REUSED

- The `config#fields` record + the SAM read/resolve/filter (`get_public_field_config`) — verified
  correct with real data; do not rewrite.
- `MembersFieldModal` + `overlayModel.upsertField` / `resolveWriteTarget` — the proven authoring
  engine to reuse for A.
- `ApplicationFormRenderer` (spec 10) — the shared renderer for the preview + the public form.
- The landing-page publish/serve pattern (`landing_page_publish_service.py` + the CloudFront
  url-rewrite function) — the model for C.

## 7. What to DELETE / retire in the redesign

- The Application-form builder's bespoke `ApplicationFieldList` toggle-list + the buried
  attributes panel (replace with the field-modal, decision A).
- `POST /members/application-preview` + its frontend debounce/caller (preview is in-browser, C).
- `PUBLIC_TENANT_SLUG_MAP` env-map slug resolution — NOT a bare deletion but a SWAP: replace
  `EnvTenantSlugReader` with a data-backed reader that resolves the slug off the `config#fields`
  record ([1=a], C). Keep the `TenantSlugReader` protocol seam so the edge/resolver are untouched;
  the env-map param can then be removed from `template.yaml` / `samconfig.toml` once nothing reads it.

---

## 8. Session audit trail (evidence pointers)

- Stored row: `aws dynamodb get-item test_governance_projection tenant_id=h-dcn sk=config#fields`
  → overrides carry `application_visible:true` under correct dotted keys.
- SAM repro (since removed): real row → `get_public_field_config` → 11 fields. Code is correct.
- Frontend repro (since removed): correct overlay write once the fixture used bare `key`+`group`.
- Deployed env: `members-public-test` `PUBLIC_TENANT_SLUG_MAP=""` (the empty-form cause).
- CI: `deploy-sam-members.yml` bare `--parameter-overrides` replaces samconfig params.
- Server key shape: `_membership_writes.py::_serialize_field` emits bare `key` + separate `group`.
