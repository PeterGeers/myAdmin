# Requirements Document

## Application Form Serving Redesign (modal authoring · in-browser preview · static slug-addressed serve) — Requirements

- Status: **Draft** (requirements phase — review before design).
- Spec home: `Members/12 - application-form-serving-redesign/` is the **course-correction** to
  `Members/11 - application-form-builder/`. Spec 11 shipped the authoring surface, the server-side
  preview endpoint, and the env-slug-map public edge. Running it against live TEST (PR #162) proved
  three independent problems and produced an agreed redesign (see spec 11 `redesign.md`). This spec
  turns that redesign into reviewable requirements + design + tasks. It **supersedes** the parts of
  spec 11 listed in "Relationship to spec 11" below and leaves the rest of spec 11 intact.
- Governing steering: `20-platform-architecture`, `35-sam-module-architecture-sam`,
  `38-sam-module-field-config`, `37-shared-building-blocks`, `43-cicd-deploys` (Terraform is manual +
  plan-first; a merge to `main` is a production deploy), `23-aws-accounts` (two-account split),
  `34-backend-testing`, `33-frontend-testing`, `40-spec-workflow`.
- Reconcile-with (do NOT duplicate): `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit`
  owns the S3/CloudFront/`*.jabaki.nl` hosting topology + the slug/KVS projection. This spec adds a
  SAM publish path INTO that hosting; it must not invent a parallel slug store or a parallel bucket.
- **PREREQUISITE (decided 2026-10-23, option a):** the jabaki hosting migration to the **nonprofit**
  account (`506221081911`) is a **hard prerequisite** of this spec's publish path. The rationale: SAM
  runs in nonprofit, so once hosting is in nonprofit the publish IAM is **same-account** and
  least-privilege — no cross-account bucket policy / CloudFront-invalidation grant is ever built (and
  then thrown away by the migration). Account reconciliation (former Open Question 3 / R6.4) is
  therefore **RESOLVED: nonprofit, migration-first.** The account-agnostic parts of this spec
  (field-modal authoring, in-browser preview, slug-on-`config#fields`, data-backed submit resolver)
  do NOT depend on the migration and MAY proceed in parallel; only the live publish (R5) + its IAM
  (R6.2) are gated on the migration having cut over.

## Introduction

Spec 11's application form, when deployed to TEST, was empty/dead. The root causes (verified, not
guessed — spec 11 `redesign.md` §1) were:

1. **Serving (1a):** the public form resolved its tenant from the SAM public Lambda env var
   `PUBLIC_TENANT_SLUG_MAP`, which deployed **empty** because the CI `--parameter-overrides` on an
   OpenRouter-key deploy **replaces** (not merges) the whole `samconfig.toml` param set, so
   `PublicTenantSlugMap` fell back to the template default `""`. Slug `hdcn` never resolved → empty form.
2. **Overlay round-trip (1b):** NOT a bug — the stored `config#fields` data, the SAM read/resolve/filter,
   and the frontend overlay write are all correct with real data. Do not "fix" this.
3. **Authoring UX (1c):** genuinely wrong — a cramped attributes panel buried under a ~100-field list; a
   choice selector rendering for fields with no choices; a half-informative boolean toggle.

The product owner agreed a redesign of three decisions (spec 11 `redesign.md` §4), and then resolved
the one open question (the application-form slug) on 2026-10-23:

- **[1=a]** the application-form slug is a **SEPARATE slug stored on the SAM `config#fields` record**
  (not in Flask `tenant_slugs`, whose one-slug-per-tenant limit is a hard DB `UNIQUE` constraint);
- **[2=a]** the **SAM plane publishes** the static form artifact to the shared public bucket, so there
  is **no runtime SAM↔Flask communication**.

This spec encodes those decisions.

## Relationship to spec 11 (what this supersedes vs keeps)

**Supersedes (replaces) in spec 11:**
- **Authoring UX** — spec 11's bespoke `ApplicationFieldList` toggle-list + buried attributes panel is
  replaced by a per-field **modal** built on the proven `MembersFieldModal` write engine (redesign A).
- **Preview** — spec 11 R7.2 / tasks 0.1 & 1.4's server endpoint `POST /members/application-preview`
  is **retired**; preview becomes **in-browser** over the working draft (redesign C). The endpoint,
  its debounce, and its caller are deleted.
- **Serving** — spec 11's `PUBLIC_TENANT_SLUG_MAP` env-map slug resolution is **retired** in favour of
  slug-as-data on `config#fields` + a static slug-addressed artifact served by the landing-page
  CloudFront path (redesign C + decisions 1a/2a).

**Keeps (unchanged, reuse) from spec 11 / spec 10:**
- The `config#fields` record + the SAM read/resolve/filter (`get_public_field_config`,
  `MembersProjectionReader.get_overlay`) — verified correct; do not rewrite.
- `MembersFieldModal` + `overlayModel.upsertField` / `resolveWriteTarget` — the authoring engine to reuse.
- `ApplicationFormRenderer` (spec 10) — the shared renderer for BOTH the in-browser preview and the
  published static form.
- Spec 11 R8 (SAM write-path validation hardening) and R3/R4 (per-field attributes, membership-type
  subset) — still in force; this spec does not weaken them.
- The landing-page publish/serve PATTERN (`landing_page_publish_service.py` + the CloudFront
  `public_pages_url_rewrite` function) — the model for C, reused, not copied into Flask.

## Terminology / Glossary

- **Form slug** — the application form's OWN public slug (e.g. `hdcn-application-form`), stored on the
  SAM `config#fields` record. Distinct from, and independent of, the tenant's landing-page slug (e.g.
  `hdcn`) in Flask `tenant_slugs`. The slug STRING may differ from the tenant NAME.
- **`config#fields`** — the SAM-owned field-config row (DynamoDB `*_governance_projection`, key
  `tenant_id` + `sk=config#fields`). This spec adds a `slug` (and publish-state) attribute to it.
- **Static form artifact** — the published, slug-addressed output written to
  `s3://myadmin-public-pages-{env}/{slug}/` (`index.html` [+ a `form.json` config), served by the
  existing `*.jabaki.nl` CloudFront distribution + `public_pages_url_rewrite` function.
- **Publish** — a SAM-plane action that renders the current `config#fields`/`config#mail` into the
  static artifact, writes it to the shared bucket, and invalidates CloudFront. Replaces the previous
  published version (landing-page lifecycle).
- **In-browser preview** — the builder renders the WORKING draft directly with `ApplicationFormRenderer`
  in memory; no server round-trip, no preview endpoint.
- **Submit** — the ONE irreducible live endpoint: `POST /public/members/{slug}/applications` (spec 10
  D27), resolving tenant from the slug AS DATA (off `config#fields`), never from an env map or a token.

## Guiding principles (settled)

- **No runtime communication between SAM and Flask — but shared AWS infrastructure is fine.** This is
  THE load-bearing principle of the spec, and the distinction matters:
  - **FORBIDDEN (communication):** one plane calling the other's API, reading the other's database, or
    synchronously depending on the other at request time. Flask never calls SAM; SAM never calls Flask;
    neither reads the other's data store.
  - **ALLOWED (shared infrastructure):** both planes INDEPENDENTLY using the same dumb AWS resources —
    the one S3 public-pages bucket, the one `*.jabaki.nl` CloudFront distribution, the stateless
    url-rewrite function. Flask writes landing artifacts to the bucket; SAM writes form artifacts to the
    SAME bucket; neither is aware of or waits on the other. Sharing storage/CDN is not communication, any
    more than two apps sharing a database engine or DNS is.
  - Consequence: do NOT "fix" the shared bucket into two buckets or duplicate the CloudFront function to
    enforce separation — the shared infra is correct and intended. The rule bans a runtime call path, not
    shared plumbing. Flask owns landing pages end-to-end; SAM owns the application form end-to-end.
- **Slug is data on the form record, not a second row in `tenant_slugs`.** The landing table's
  `administration UNIQUE` constraint forbids a tenant owning two slugs; the form owns its addressing.
- **Reuse the proven engines.** Authoring reuses `MembersFieldModal`; rendering (preview AND published)
  reuses `ApplicationFormRenderer`; serving reuses the landing CloudFront path. No new per-tenant infra,
  no forked write code, no client-side filter mirror.
- **The server stays authoritative** (spec 11 R8 unchanged). Publish renders through the SAME resolve +
  filter the submit edge uses, so the published form and the live read never drift.
- **Gated as administrative.** Authoring + publish require `members:admin` (Tenant_Admin), tenant from
  the verified JWT, never the body.
- **Change-with-tests, both planes** (steering 30/34/33): paired tests land in the same change.

## Requirements

### R1 — Field-modal authoring UX (redesign A; supersedes spec 11's toggle-list)

**User story:** As a Tenant Admin, I want to click a field and configure ALL its on-form attributes in
one modal, so authoring is coherent and not a cramped panel under a long list.

#### Acceptance criteria
1. The builder SHALL keep its group ▸ field surface, but clicking a field SHALL open a **modal built on
   `MembersFieldModal`'s write logic** (`buildField` / `resolveWriteTarget` / `upsertField`) — not the
   bespoke `ApplicationFieldList` toggle-list + panel, which SHALL be retired.
2. The modal SHALL show an **application-form attributes section** ONLY when a form is in scope, carrying
   the FOUR persisted per-field attributes (spec 11: `application_visible` — on-the-form, with full field
   context; `application_required`; `application_choices` — the enum subset; `format`) PLUS the field's
   display sequence within its group (authored via the field's `order`, NOT a fifth `application_*`
   attribute). The enum-subset picker SOURCE adapts to the field kind (reference → live catalog e.g.
   membership_type; scope → the scope dimension's values; enum/choices → the field's own options);
   `application_required`/filter applies only to filterable fields; `format` (IBAN/email) only to
   applicable fields.
3. The enum-subset / "choice selector" SHALL render ONLY for fields that actually have choices
   (enum/reference/scope) — never for a plain string field (fixes the spec 11 choice-on-string bug).
4. The modal SHALL write all attributes onto the SAME single `field_overlay` object and commit via the
   SAME `PUT /members/config/fields` call (one object, one save) — reusing `upsertField`, no forked write.
5. Display attributes are explicitly OUT of scope now.

### R2 — Frontend reasons in groups + fields; the server owns storage placement (redesign B)

**User story:** As a maintainer, I want the builder to stop reasoning about overlay internals, so the
class of seam-mismatch bugs underneath the authoring UX disappears.

#### Acceptance criteria
1. The builder UI SHALL work in functional-groups + fields and SHALL NOT reason about
   `overlay` / `fixed_overrides` / `writeTarget` / provenance; it reuses the proven `upsertField` write.
2. Preferred end-state: the server accepts a write keyed by **field identity** and performs the storage
   placement, so the frontend never constructs the overlay shape. **This end-state is DEFERRED in this
   spec** (it is not a task below): the builder reuses the proven `upsertField` write, which already
   keeps the frontend off bespoke overlay construction, so no NEW seam is introduced and no server-side
   placement change is required here. Server-owned placement is a future enhancement, explicitly out of
   scope (see Out of scope).
3. The server key shape is authoritative: fields are emitted as **bare `key` + separate `group`** (not a
   pre-dotted key) per `_membership_writes.py::_serialize_field`; any fixture/test SHALL use that shape
   (the spec 11 session proved a wrong fixture — pre-dotted key — created a phantom bug).

### R3 — In-browser preview (redesign C; retires the server preview endpoint)

**User story:** As a Tenant Admin, I want the preview to reflect my unsaved edits instantly, without a
server round-trip, so authoring and the public render never drift and there is no fragile endpoint.

#### Acceptance criteria
1. The builder SHALL render a **live, in-browser preview** by feeding its WORKING (in-memory) draft
   directly to spec 10's `ApplicationFormRenderer`. It SHALL reflect unsaved edits with no save and no
   server round-trip.
2. The server preview endpoint `POST /members/application-preview` (spec 11 R7.2 / tasks 0.1 & 1.4), its
   frontend debounce, and its caller SHALL be **deleted**. The applicant-facing filtering that the
   endpoint performed SHALL be reproduced in the browser by reusing the SAME filter logic the renderer/
   resolver already embodies — with a paired test pinning parity against the server
   `get_public_field_config` for an equivalent config, so retiring the endpoint does not reintroduce drift.
3. An **"open live form" link** to the real published form SHALL remain the authoritative check (R6);
   the in-browser preview is for authoring, the link is for confirming the published artifact.

### R4 — Form slug stored on `config#fields` (decision 1=a)

**User story:** As a Tenant Admin, I want the application form to have its own public address that is
independent of my landing-page slug and may differ from my tenant name.

#### Acceptance criteria
1. The application-form slug SHALL be stored as an attribute on the SAM `config#fields` record
   (`tenant_id` + `sk=config#fields`), authored via the SAM `members:admin` config-write path — NOT in
   the Flask `tenant_slugs` table.
2. The slug SHALL be validated for format with the SAME rules the landing slug uses (lowercase;
   letters/numbers/hyphens; 3–100 chars; no leading/trailing hyphen; no consecutive hyphens; not a
   reserved slug) so `hdcn-application-form` is valid and collisions/garbage are rejected fail-loud.
3. **Slug uniqueness is a TENANT-scoped concern, NOT a platform-wide global-namespace problem
   (RESOLVED, OQ2).** The platform does NOT police a global slug registry across tenants or across the
   two planes. The only uniqueness the platform enforces is WITHIN a single tenant: a tenant cannot have
   two application forms with the same slug (and, with one application form per tenant today, this is
   effectively "the tenant owns its one form slug"). Cross-tenant and cross-function global uniqueness
   are explicitly out of the platform's enforcement scope — they are a BUSINESS matter, and the parked
   future addressing model (R4.6) makes them structural.
   - Consequence: NO global slug registry, NO GSI-on-slug, NO shared cross-plane arbiter is built. The
     earlier "two SAM-side guards keyed on the slug" framing is withdrawn as over-engineered.
   - The publish-time S3 check on a root `{slug}/landing.json` SAM did not author REMAINS, but ONLY as a
     cheap defensive backstop so a form publish cannot clobber a landing page's files — it is NOT a
     global-uniqueness mechanism (it never could be; it is one-directional and publish-time).
3a. **Reverse lookup (slug → `tenant_id`) — RESOLVED (OQ4): a `_slugs/{slug}` marker object in the
   shared bucket.** The submit edge resolves the public slug to its owning tenant via a `get_object` on
   `_slugs/{slug}` (scan-free); within-tenant uniqueness is a conditional `put_object`. This keeps the
   lookup off the `tenant_id`-PK governance-projection table (whose STRUCTURAL-ONLY isolation — repo pins
   `tenant_id`, no `.scan()`, `LeadingKeys` future-only, `template.yaml` — forbids a slug-partitioned
   item) and needs NO DynamoDB change. The `_slugs/` prefix is reserved and sits outside any served
   `{slug}/` prefix. The parked `*.{tenant-id}.jabaki.nl` model (R4.6) removes this lookup entirely. → OQ4.
4. A slug whose NAME differs from the tenant NAME SHALL be allowed (the slug string and `tenant_id` are
   independent). The builder SHALL display the resolved public URL (`{slug}.jabaki.nl`) once a slug is set.
5. Renaming the form slug SHALL be handled coherently (old artifact cleaned up / new one published);
   the rename workflow scope is a design decision (design §Rename), mirroring — not reusing — the landing
   `rename_slug` steps that apply (S3 cleanup, republish, CloudFront invalidation), on the SAM plane.
6. **PARKED FUTURE DIRECTION (not built in this spec):** the target addressing model is
   `*.{tenant-id}.jabaki.nl` — the tenant-id as a mandatory HOST segment, giving each tenant its own
   sub-namespace (`apply.h-dcn.jabaki.nl`, `landing.h-dcn.jabaki.nl`, etc.), with tenants free to CNAME
   their own domains onto it. Because the tenant-id is globally unique and lives IN THE HOST, this makes
   uniqueness structurally per-tenant and lets the submit edge parse the tenant straight from the
   hostname (no slug→tenant lookup at all). It is DEFERRED because it needs a two-level wildcard
   cert/CloudFront setup and an S3-layout + rewrite-function reshape — platform-wide infra that belongs
   to `jabaki-hosting-migration-to-nonprofit`, not this form-feature spec. This spec uses the existing
   flat single-level `*.jabaki.nl` path; it only ADOPTS the PRINCIPLE (uniqueness is a tenant concern,
   R4.3) now, not the host structure.

### R5 — SAM publishes the static artifact (decision 2=a; redesign C)

**User story:** As the platform, I want the plane that owns the form config (SAM) to publish the static
form, so there is no runtime SAM↔Flask communication.

#### Acceptance criteria
1. A SAM-plane **EXPLICIT publish action** — a `members:admin`-gated route
   `POST /members/application-form/publish` (OQ1 RESOLVED: option 1, explicit route, NOT
   save-triggered) — SHALL render the tenant's current `config#fields`/`config#mail` into the static
   artifact and write it to `s3://myadmin-public-pages-{env}/{slug}/` (`index.html` [+ `form.json`]),
   then invalidate the `*.jabaki.nl` CloudFront distribution for that slug. Publish SHALL REPLACE the
   previous version.
1a. Saving the draft (`PUT /members/config/fields|mail`) SHALL NOT republish the live form — editing and
   going-live are distinct steps. The live artifact changes ONLY on an explicit publish; the in-browser
   preview (R3) covers "see before commit," so no publish is needed merely to check work.
2. Publish SHALL render through the SAME resolve + filter the submit edge uses (reuse
   `get_public_field_config`), so the published form equals what an applicant would get — single
   filtering authority, no drift.
3. Flask SHALL NOT be involved in application-form publish at any point (no cross-plane call, no Flask
   read of the SAM form config). The landing-page publish path (`landing_page_publish_service.py`) is the
   reused PATTERN only; the application-form publish code lives on the SAM plane.
4. Publish SHALL be gated by readiness (spec 10 D15 / spec 11 R6): a form MUST have a stored slug (R4)
   AND a certified sender AND ≥1 on-form field before publish writes an artifact — any missing
   precondition SHALL refuse the publish with a clear `members:admin`-facing error (no partial/broken
   artifact); the builder SHALL surface why (show, don't silently block). The slug precondition is the
   SAME slug R4 stores on `config#fields`, so "no slug" means the admin has not yet authored one.
5. The static artifact SHALL be self-contained and responsive, SHALL post its content height to a parent
   frame (the `postMessage` resize handshake, spec 11 R5.2b/E4b) so it renders inside a sandboxed iframe,
   and SHALL carry the applicant-facing schema + consent notice the renderer needs.

### R6 — Serving reuses the landing CloudFront path (no new infra, no request-time lookup)

**User story:** As the platform, I want the form served by the existing `*.jabaki.nl` pipeline so there
is no new per-tenant infrastructure and no request-time tenant lookup.

#### Acceptance criteria
1. `{form-slug}.jabaki.nl/` SHALL be served by the EXISTING `aws_cloudfront_distribution.public_pages`
   (`aliases = ["*.jabaki.nl"]`) + the stateless `public_pages_url_rewrite` function
   (`infrastructure/landing-pages.tf`), which maps the host to `/{slug}/index.html` by pure string
   manipulation. No new distribution, no new cert, no per-tenant infra, no request-time tenant lookup.
2. SAM SHALL be granted **write + CloudFront-invalidate IAM** on the public-pages bucket / distribution
   (a mirror of the Flask Railway grant). Because hosting is migrated to nonprofit FIRST (prerequisite,
   option a), this is a **same-account** grant in `506221081911` — least-privilege, NO cross-account
   bucket policy or cross-account invalidation. This IAM is a Terraform change applied **plan-first,
   manually, in the same release window** as the code (steering 43); it SHALL NOT reference the other
   plane's resources by hard-coded id.
3. The CSP `frame-ancestors` enforcement for the form (spec 11 E4b: the `application_embed_origins` KVS
   + the `viewer-response` `application_form_frame_ancestors` function, `infrastructure/application-form.tf`)
   SHALL apply to the published form host; a host with no embed-origins entry SHALL fall back to
   `frame-ancestors 'none'` (deny external framing).
4. This spec reconciles with `jabaki-hosting-migration-to-nonprofit` as a **prerequisite** (option a):
   the migration moves the bucket/distribution to nonprofit FIRST, then the SAM IAM + publish target
   point at the **nonprofit** resources. The live publish (R5) SHALL NOT be wired against the personal
   bucket; if for any reason the migration is not yet cut over, the publish task stays blocked (the
   account-agnostic parts of this spec still proceed). The two specs SHALL NOT create parallel hosting.

### R7 — Submit resolves tenant from the slug AS DATA (retires the env map)

**User story:** As the platform, I want the one live applicant endpoint to resolve the tenant from the
slug stored in data, so the empty-env-map deploy failure (1a) cannot recur.

#### Acceptance criteria
1. The public submit/field-config edge (`sam/members/handler/public_app.py`) SHALL resolve
   slug → `tenant_id` from DATA — the slug stored on `config#fields` (R4) — NOT from
   `PUBLIC_TENANT_SLUG_MAP`. The `EnvTenantSlugReader` SHALL be replaced by a data-backed reader
   (named `ConfigFieldsSlugReader` in design §C5/D5) satisfying the EXISTING `TenantSlugReader` Protocol
   (`sam/members/domain/tenant_directory.py`), so the resolver (`TenantDirectory`) and edge are
   untouched. (VERIFIED 2026-10-23: that Protocol exists and `EnvTenantSlugReader.resolve_slug` already
   satisfies it by duck-typing; the reader's own docstring states swapping the backing store is a
   localized change to that file — so the "localized swap" claim holds.)
2. Resolution SHALL remain verify-before-trust: an unknown/forged/blank/oversized slug SHALL yield the
   SAME non-probeable 404 (`PublicTenantNotFound`); the slug SHALL select among known tenants only, and
   the resolved `tenant_id` SHALL be the ONLY source of the record's tenant (spec 10 R2.2/R2.4).
3. The `PUBLIC_TENANT_SLUG_MAP` parameter SHALL be removed from `template.yaml` / `samconfig.toml` once
   nothing reads it; its removal SHALL NOT be a bare deletion that breaks the edge mid-change (swap first,
   then remove).
4. The CI `--parameter-overrides` replace-not-merge footgun (1a root cause) SHALL be addressed so a
   secret-carrying deploy cannot blank other `samconfig.toml` params again — EITHER by this change making
   the slug data-resolved (removing the dependency on that param) AND a note/guard on the deploy workflow,
   so the latent prod risk is closed (design §CI-footgun).

### R8 — Readiness, embedding, consent, hardening carry forward unchanged

**User story:** As a maintainer, I want the redesign to preserve spec 11's settled behavior it does not
explicitly change.

#### Acceptance criteria
1. The readiness panel (spec 11 R6), the two embed modes (R5.2 E4a native block + E4b external iframe +
   `application_embed_origins`), the versioned bilingual consent notice (R5.3), and the SAM write-path
   hardening (R8) SHALL remain in force, re-targeted only where serving/preview/slug changed here.
2. The native landing-page block (E4a) renders the form same-origin via `ApplicationFormRenderer`; this
   spec SHALL keep it consistent with the new in-browser-preview rendering path (one renderer, one code
   path for preview + native block + published artifact).

### R9 — Testing (change-with-tests, both planes)

**User story:** As a maintainer, I want the redesigned paths covered so a change can't silently break the
nightly suite.

#### Acceptance criteria
1. **Frontend** (`33-frontend-testing`): the field-modal authoring writes the FOUR `application_*`
   attributes (+ the field `order` for sequence, R1.2) into the ONE `field_overlay` (subset only on
   choice-bearing fields; required-no-relax; known format tokens);
   one-object/one-save preserved; the IN-BROWSER preview reflects unsaved edits and matches server-filter
   parity via a pinned fixture; the slug display + "open live form" link; the external-embed snippet +
   `postMessage` resize inside a Google Sites iframe; axe over the builder + modal.
2. **SAM** (`34-backend-testing`, `sam/tests/`): slug stored/validated on `config#fields` (format +
   uniqueness); the data-backed `TenantSlugReader` resolves a known slug and 404s an unknown one
   (verify-before-trust); publish renders the artifact through `get_public_field_config` (filter parity),
   writes the expected S3 keys, invalidates CloudFront, is `members:admin`-gated and readiness-gated, and
   replaces the prior version; the retired `POST /members/application-preview` is removed and nothing
   references it.
3. Paired tests land in the SAME change as the behavior they cover (steering 30/34/33). A behavioral edit
   that leaves a paired test on old behavior is incomplete.

## Non-functional requirements

- **Security:** every authoring/publish write `members:admin`-gated, tenant from the verified JWT, body
  never trusted for tenant. The submit edge stays token-less, slug-as-selector only, non-probeable 404.
  No secret or config internals in any public-facing error. SAM's new bucket/CloudFront IAM is
  least-privilege (write + invalidate scoped to the public-pages resources).
- **No cross-plane runtime coupling:** verified by design — serving is CloudFront+S3+stateless function;
  publish is SAM→S3/CloudFront via boto3; submit is SAM-only. No path calls Flask.
- **Accessibility:** WCAG 2.2 AA for the builder + modal (Chakra `FormControl`, keyboard, focus, nl/en),
  consistent with spec 10 D14 / spec 11.
- **Infra discipline (steering 43):** the SAM IAM Terraform is plan-first, manually applied in the same
  release window as the code, reviewed in the same PR; no `tfstate` committed; destroy/replace on a
  stateful resource (the `public_pages` distribution, a KVS, the bucket) is a STOP.

## Out of scope (v1)

- Re-introducing Flask authoring/projection of `config#*` or a Flask publish of the application form
  (explicitly retired; do not revive).
- Changing the landing-page slug mechanism or `tenant_slugs`. *(Called out because it is the tempting
  wrong path: the landing feature already has a slug table, so "just add the form slug there" is the
  obvious first instinct — but `tenant_slugs.administration UNIQUE` forbids a second slug per tenant
  (D1). This spec REUSES landing's `SLUG_PATTERN` validation rules and the publish PATTERN without
  modifying either; it does not read, write, or alter `tenant_slugs`.)*
- The jabaki hosting account migration itself (owned by the backlog spec); this spec only ADDS a SAM
  publish path into whichever account currently owns the bucket/distribution, and reconciles targets.
- Display/style attributes per field (future), a JS web-component embed (future), WAF/CAPTCHA on the
  public edge (spec 10 D17, deferred), per-scope Reply-To (spec 11 R5.4, future).
- Any change to the applicant submission flow, de-dup, duplicate flag, or notifications (shipped in
  spec 10) beyond the slug-resolution swap (R7).

## Open questions (to resolve in design)

1. **Publish mechanism (R5.1) — RESOLVED (option 1, 2026-10-23):** an explicit `members:admin` route
   `POST /members/application-form/publish` invoked from the builder's "Publish" button, NOT an
   event/trigger on `config#fields` save. Save ≠ publish; the live form changes only on a deliberate,
   readiness-gated publish (matches the landing "publish" lifecycle; deterministic; cleanly gated).
2. **Slug uniqueness SCOPE (R4.3) — RESOLVED (OQ2, 2026-10-23):** uniqueness is a TENANT-scoped concern,
   NOT a platform-wide global namespace the platform must police. The platform enforces only
   within-tenant uniqueness (one tenant can't have two forms with the same slug; today that's "the tenant
   owns its one form slug"). Cross-tenant / cross-function global uniqueness is a BUSINESS matter, made
   structural by the parked `*.{tenant-id}.jabaki.nl` model (R4.6). NO global registry / GSI / shared
   arbiter is built. The publish-time S3 `{slug}/landing.json` check stays ONLY as a cheap backstop
   against clobbering a landing page's files (not a uniqueness mechanism). The `landing-pages/` asset
   subfolder is NOT a collision signal (verified live). → D6.
3. **Account reconciliation (R6.4) — RESOLVED (option a, 2026-10-23):** the jabaki hosting migration to
   nonprofit is a **prerequisite**; SAM IAM + publish target the **nonprofit** bucket/distribution,
   same-account, no cross-account grant. The account-agnostic work (authoring/preview/slug/resolver)
   proceeds independently; only the live publish + its IAM are gated on the migration.
4. **Slug→`tenant_id` reverse-lookup MECHANISM (R4.3a) — RESOLVED (OQ4, 2026-10-23): a `_slugs/{slug}`
   marker object in the shared public-pages bucket.** SAM stores the mapping as a small control-plane
   object `_slugs/{slug}` (body/metadata = owning `tenant_id`) in `myadmin-public-pages-{env}`. The
   submit edge resolves slug → `tenant_id` by a `get_object` on that key (scan-free); within-tenant
   uniqueness is a conditional `put_object` (if-none-match). Chosen because it needs NO DynamoDB change
   (no GSI, no owner sign-off, no slug-keyed item on the `tenant_id`-PK table), reuses infra SAM already
   writes to for publish, and is the lowest-investment option for a lookup the parked R4.6 host model
   will remove entirely. Constraints: the `_slugs/` prefix is RESERVED (a real page slug may never be
   `_slugs` or start `_slugs/`) and marker objects live OUTSIDE any `{slug}/` serving prefix (control
   plane, never served by CloudFront). (design D6 / §Reverse-lookup.)
