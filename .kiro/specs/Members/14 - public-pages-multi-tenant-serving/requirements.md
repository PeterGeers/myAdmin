# Requirements — 14. Public-Pages Multi-Tenant Serving (page-as-unit)

- Status: **Draft** (requirements phase — review before design).
- Origin: the decision brief in `13 - application-form-rendering-polish/next-steps.md`
  (decisions D1–D7, locked 2026-10-31). This spec turns that brief into reviewable
  requirements. It is the ARCHITECTURAL successor the brief asked to be promoted out of the
  spec-13 scratch file.
- **Reconcile-with (do NOT fork or duplicate):**
  `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit` owns the hosting TOPOLOGY
  (S3 `myadmin-public-pages-*` bucket + `*.jabaki.nl` CloudFront distribution + ACM + the
  url-rewrite function + the `domain_mapping` / `application_embed_origins` KVS + backend IAM),
  and the parked `*.{tenant-id}.jabaki.nl` host model. This spec ADDS a page-registry + a SAM
  publish/serve path INTO that topology (D7). It MUST NOT invent a parallel slug store, a
  parallel bucket, or a parallel CloudFront path.
- Governing steering: `20-platform-architecture`, `35-sam-module-architecture-sam`,
  `31-backend-database-flask-mysql`, `37-shared-building-blocks`, `43-cicd-deploys`
  (Terraform plan-first, owner-run cutover), `23-aws-accounts`, `34-backend-testing`,
  `33-frontend-testing`, `40-spec-workflow`.
- Supersedes nothing; spec 12's SAM publish/serve requirements are SUBSUMED here under the
  generalized page model (the form becomes one page kind among N).

## Context

Today a tenant can have at most ONE public page (a landing page), enforced structurally in
three layers (verified in code):

1. **MySQL** — `tenant_slugs.administration VARCHAR(50) NOT NULL UNIQUE` → one slug per tenant.
2. **DynamoDB landing store** — `PK=TENANT#{slug}, SK=LANDING#HOME` (constant SK) → one draft
   per slug.
3. **S3 / assets / CloudFront** — keyed on slug (`{slug}/index.html`,
   `s3_asset_references.entity_id = slug`, invalidation `/{slug}/*`).

The member application form (SAM plane) needs to be a SECOND public page per tenant, at its own
per-tenant address (`xxx.jabaki.nl`), optionally reached via a tenant-owned custom domain
(CNAME, URL preserved, no redirect). The 1:1 ceiling blocks this.

**Decision (brief D2): lift the ban — no 1:1 limit in the code.** The unit of public addressing
becomes a PAGE, not a tenant. A tenant may own N pages (landing, application-form, future kinds),
each with its own slug + optional custom domain(s) + published artifact.

The serving layer is ALREADY shared and generic (one `*.jabaki.nl` distribution + a stateless
slug-path rewrite + the shared bucket), and CNAME-without-redirect ALREADY works via
`tenant_custom_domains` + the `domain_mapping` KVS. So the gap is the ADDRESSING MODEL (lift 1:1)
and the SAM PRODUCER (publish + public data endpoints), not the serving plumbing.

## Guiding principles (from the brief, settled)

- **Page is the unit, not the tenant** (D2). No hard-coded one-page-per-tenant limit anywhere.
- **No runtime SAM↔Flask communication; shared DUMB infra only** (D3). Both planes independently
  publish artifacts into the shared bucket and claim slugs/domains in the shared registry/KVS.
  A shared cross-plane DATABASE TABLE is forbidden (steering 35 rule 5a). The only shared surface
  is the S3 bucket + the stateless CloudFront function + the KVS.
- **Each plane owns its page kind end-to-end** (D3). Flask owns landing pages; SAM owns the
  application form. Neither reads/writes the other's datastore.
- **Reuse the mechanism, not the store or a runtime call** (D4). A shared, dependency-free
  rendering library (HTML shell + CSS/SEO/footer) may be imported by both planes; this is NOT
  cross-plane communication.
- **Reconcile with the hosting backlog, do not fork** (D7).
- **Verify against reality** (steering, HC6 lineage from spec 13): the live landing tenants must
  keep working across the model change; prove migrations against real rows.

## Requirements

### R1 — Page is the unit of public addressing (lift the 1:1 limit) [D2]

**User story:** As a tenant admin, I want more than one public page (a landing page AND an
application form, and more later), each at its own address, so I am not limited to a single page.

#### Acceptance criteria
1. The platform SHALL model a PAGE as `(tenant, page_id, kind, slug, custom_domains[],
   published_artifact, owner/meta)`, allowing N pages per tenant. `kind ∈ {landing,
   application-form, …}` is extensible.
2. The MySQL `tenant_slugs.administration UNIQUE` constraint SHALL be relaxed so a tenant may own
   multiple slugs; `slug` SHALL remain globally unique. The migration SHALL preserve all existing
   landing rows (the live tenants keep their current slug).
3. The landing DynamoDB store SHALL move from the constant `SK=LANDING#HOME` to a per-page sort
   key (e.g. `SK=PAGE#{page_id}` or `{kind}#{slug}`), so multiple pages coexist under one tenant.
   Existing `LANDING#HOME` items SHALL migrate without content loss.
4. `tenant_custom_domains` SHALL map a domain to a specific PAGE'S slug (it is already slug-keyed)
   — generalized from "the tenant's one landing domain" to "a domain mapped to a page." A page
   MAY have zero, one, or more custom domains.
5. No code path SHALL assume one slug/page per tenant (`get_slug(tenant)` single-return callers
   SHALL be generalized or scoped to a page). Fail loud if a legacy single-slug assumption is hit.
6. The change SHALL NOT regress the 7 live landing tenants: each keeps its slug, custom domain,
   published artifact, and serves identically after the migration (verify against reality).

> **Registry scope clarification (per review 2026-10-31):** there is NO single shared page-registry
> table. Each plane registers its own pages in its own store: Flask landing pages in a MySQL page
> registry (`tenant_pages`, design OQ1); SAM application-form pages on the SAM-owned `config#fields`
> row (slug + publish-state, per spec 12). "Page is the unit" is realized PER PLANE. The only
> SHARED thing is the slug NAMESPACE, enforced by the `_slugs/{slug}` marker (R3a) — never a shared
> registry database (steering 35 rule 5a).

### R2 — Tenant public prefix + opaque slug model [business rule]

**User story:** As the platform, I want every public slug to carry the tenant's short public
prefix, so popular names (e.g. `aanmelden`) are not globally land-grabbed by the first tenant, and
each tenant owns its own slug sub-namespace across ALL planes/apps.

#### Acceptance criteria
1. Each tenant SHALL have ONE short **public prefix** — chosen once, globally unique, slug-safe
   (`SLUG_PATTERN`, ~3–20 chars) — that is the tenant's single public identity across ALL planes
   and apps (Flask landing, SAM members form, future apps). (`h-dcn` is `h-dcn`'s prefix for every
   kind: `h-dcn`, `h-dcn-aanmelden`, `h-dcn-clubdag`, …).
2. The prefix SHALL be authored in MySQL as an attribute on the tenant record (the tenant
   system-of-record, steering 20), and carried READ-ONLY to the SAM plane as an attribute on the
   ALREADY-PROJECTED `tenant` governance-projection row (`SK="tenant"`, `projection_schema.py`) —
   an ADDITIVE field on an existing projected record, NOT a new table or a new projection
   mechanism. SAM validates the prefix from its own projected `tenant` row, never by calling Flask.
3. A new page slug SHALL be `{prefix}` or `{prefix}-{suffix}` and SHALL be validated at claim time
   to start with the AUTHENTICATED tenant's prefix; a tenant SHALL NOT claim a slug under another
   tenant's prefix. Long administration names (e.g. `vandenheuvelhoveniers`) use their SHORT prefix,
   not the full name.
4. The slug string SHALL be an OPAQUE public address otherwise: it SHALL NOT encode plane/app type,
   and NO code SHALL infer tenant, plane, or kind by parsing the slug string — those are resolved
   from the `_slugs/{slug}` marker body + the plane's own record (R3a).
5. Existing live slugs SHALL be GRANDFATHERED: the 7 live landing slugs (including uppercase ones
   like `GoodwinSolutions`/`PeterPrive` that would FAIL new `SLUG_PATTERN`/prefix validation) keep
   working and SHALL NOT be force-renamed. The prefix rule applies to NEW claims only.
6. Format/reserved validation (`SLUG_PATTERN`, reserved words, length) SHALL run BEFORE the
   uniqueness claim; the prefix rule is additive on top of it.

### R3a — Slug uniqueness: one authoritative cross-plane gate

**User story:** As the platform, I want it to be impossible for two pages (even across planes) to
claim the same slug, so a public host resolves to exactly one page.

#### Acceptance criteria
1. The AUTHORITATIVE uniqueness gate SHALL be an ATOMIC conditional `put_object` on
   `_slugs/{slug}` with `If-None-Match: *` in the shared bucket: the write succeeds only if the
   object does not exist; a racing second claimer (EITHER plane) gets `412 PreconditionFailed` →
   `SlugTaken`. This is the cross-plane gate that needs no shared database.
   (If `If-None-Match: *` is not available for the target bucket/region, the sanctioned fallback is
   a DynamoDB conditional `PutItem(attribute_not_exists(pk))` on a dedicated slug-claim table — but
   S3 conditional put is preferred; VERIFY availability before locking, see design.)
2. The `_slugs/{slug}` marker BODY SHALL record the slug's backing — `{owner_plane, kind,
   tenant_id, resource_ref}` — and SHALL be the source of truth for ownership/resolution. The
   serving/submit edge SHALL decide ownership by READING THE MARKER BODY, never by parsing the slug.
3. Per-plane `UNIQUE`/validation (Flask `tenant_pages.slug UNIQUE`; SAM config-row slug check) MAY
   run first as a FAST-FAIL UX check, but SHALL NOT be relied on as the guarantee (it cannot see
   the other plane).
4. A re-publish by the SAME owner (marker body matches `owner_plane`+`tenant_id`) SHALL be
   idempotent (allowed); a claim whose body would not match SHALL be rejected as a conflict.
5. A publish SHALL NOT clobber a `{slug}/` artifact it did not author (owner-tag backstop, defense
   in depth).
6. A slug RENAME SHALL claim the new slug (conditional put) BEFORE releasing the old marker, so a
   crash mid-rename never leaves a slug double-owned or orphaned.

### R2c — Shared publish contract: each plane produces a page into the shared dumb infra [D3]

> _(Requirement IDs are intentionally non-contiguous after the 2026-10-31 review inserted R2 /
> R3a; the set below — R1, R2, R2c, R3, R3a, R4, R5, R6, R7 — is the full list.)_

**User story:** As the platform, I want both planes to publish pages through one shared
infrastructure without calling each other, so there is one serving story and no cross-plane
coupling.

#### Acceptance criteria
1. A published page SHALL consist of: a rendered `{slug}/index.html` in the shared
   `myadmin-public-pages-{env}` bucket; optionally a `{slug}/form.json` (or `landing.json`) data
   artifact; a claimed slug in the shared slug registry; optional custom-domain host→slug entries
   in the `domain_mapping` KVS; and a CloudFront invalidation for `/{slug}/*`.
2. SAM SHALL render + write the application-form artifact; Flask SHALL render + write the landing
   artifact. NEITHER plane SHALL read or write the other's datastore, call the other's API, or
   depend on the other at request time (steering 35 rule 5a; the no-runtime-comms principle).
3. A shared cross-plane DynamoDB table or record SHALL NOT be introduced. The shared surfaces are
   EXACTLY: the S3 bucket, the stateless CloudFront url-rewrite function, and the two KVS.
4. Slug/domain claiming SHALL enforce global slug uniqueness via a dumb-infra mechanism (the S3
   `_slugs/{slug}` marker, D6) — not a shared database arbiter.

### R3 — SAM application-form as a page producer (public data path) [D5/D6]

**User story:** As an applicant, I want to load and submit a tenant's application form at its
public address, with no login, seeing only applicant-safe fields.

#### Acceptance criteria
1. The SAM plane SHALL expose a PUBLIC, no-auth `GET {slug}` returning the applicant-facing form
   schema (reusing `get_public_field_config`), and a PUBLIC, no-auth `POST {slug}` to submit —
   mirroring the h-dcn public-endpoint pattern: API with no default authorizer, no `Auth` block on
   the public functions, handler does NOT call credential extraction.
2. The response SHALL go through an EXPLICIT public-field whitelist (allowlist, not blocklist) —
   never internal config/credentials; secrets at most as a boolean existence check.
3. Slug→tenant/form resolution SHALL be server-side with a publication gate in the resolve
   (unpublished → non-probeable 404), and SHALL NOT use a full-table scan. It SHALL use the S3
   `_slugs/{slug}` marker (spec 12's choice, D6) OR a slug GSI — never the h-dcn Events scan
   anti-pattern.
4. The published `{slug}/index.html` SHALL be a thin self-contained shell that fetches the schema
   from `GET {slug}` and renders it with the existing `ApplicationFormRenderer` (one renderer for
   preview, native block, and published artifact).
5. The submit `POST` SHALL resolve tenant from the slug AS DATA (never an env map), stay
   token-less and non-probeable, and its Lambda role SHALL have write IAM on the target
   applications table (verify this is already granted — brief open item).

### R4 — CNAME custom domains, URL preserved, per page [D1]

**User story:** As a tenant admin, I want to point my own domain at a page via CNAME and keep my
domain in the address bar (no redirect to `*.jabaki.nl`).

#### Acceptance criteria
1. A page's public address SHALL be `{slug}.jabaki.nl`, served by the existing shared CloudFront
   distribution + stateless slug-path rewrite (no new per-tenant infra, no request-time tenant
   lookup).
2. A tenant SHALL be able to attach a custom domain to a PAGE via the existing
   `tenant_custom_domains` + ACM + CloudFront-alias + `domain_mapping` KVS mechanism, generalized
   to per-page. The custom domain SHALL serve the page content WITHOUT a redirect (URL preserved).
3. CSP `frame-ancestors` for an application-form host SHALL come from the existing
   `application_embed_origins` KVS + viewer-response function; a host with no entry denies framing
   (`'none'`).

### R5 — Shared rendering library (reuse the mechanism) [D4]

**User story:** As a maintainer, I want the form and landing pages to share the generic HTML
shell/CSS without a cross-plane runtime call, so look-and-feel is consistent and maintained once.

#### Acceptance criteria
1. The generic HTML shell + CSS/SEO/footer scaffolding (from `generate_index_html` +
   `LandingPageStyles`) SHALL be extractable into a plane-neutral, dependency-free module both
   planes import — PENDING a verification that it extracts cleanly (no hidden Flask deps). If it
   does not extract cleanly, SAM renders its own shell and the shared library is deferred (noted,
   not silently dropped).
2. Sharing SHALL be as an imported LIBRARY (pure functions), never a runtime call or a shared
   store.

### R6 — ADR + governance actions [brief ⚠ section]

**User story:** As a maintainer, I want these architectural decisions tracked so future specs
inherit them and they are not lost in a scratch file.

#### Acceptance criteria
1. A NEW ADR "Multi-tenant public-pages addressing: page as the unit, not tenant" SHALL be
   authored (records D2 + the D3 dumb-infra hand-off + the no-shared-DB rule).
2. ADR 0003 (platform base) and ADR 0005 (MySQL system-of-record + projection) SHALL be REVIEWED
   for consistency; the Flask-owns-DynamoDB exception (third tenancy shape) SHALL be documented in
   steering or an ADR so it does not read as drift.
3. This spec SHALL cross-reference `jabaki-hosting-migration-to-nonprofit` and SHALL NOT duplicate
   its hosting cutover; registry/KVS/bucket changes reconcile with that backlog's topology (D7).

### R7 — Testing (change-with-tests, both planes)

#### Acceptance criteria
1. MySQL migration tests: the page registry accepts N slugs/tenant, keeps `slug` globally unique,
   and preserves the live rows (real-data fixture).
2. DynamoDB migration tests: `LANDING#HOME` → per-page SK migration preserves content for the
   live tenants.
3. SAM tests: public `GET {slug}`/`POST {slug}` are no-auth, whitelist-filtered, slug-resolved
   via marker/GSI (not scan), publication-gated, and 404 unknown/unpublished non-probeably.
4. Frontend tests: the published shell fetches + renders via `ApplicationFormRenderer`.
5. Paired tests land in the SAME change as the behavior (steering 30/34/33).

#### Slug-uniqueness + prefix test list (R2 / R3a) — T1–T11
> **Discipline (HC6 lineage):** T2 (cross-plane) and T3 (race) MUST run against REAL S3 (or an
> emulator that genuinely enforces `If-None-Match`), NEVER a mock that just returns success — the
> guarantee IS an S3 behaviour; a mock would go green while the guarantee is absent.

- **T1 — same-plane duplicate:** claim `h-dcn-x` twice (same plane) → 2nd → `SlugTaken`/412.
- **T2 — cross-plane duplicate:** claim a slug from Flask, then from SAM → 2nd → `SlugTaken`
  (the whole point — a per-table UNIQUE cannot give this). _Real S3._
- **T3 — concurrency race:** N concurrent claims for one slug → EXACTLY ONE succeeds, N−1 get 412
  (proves atomicity, not check-then-write). _Real S3._
- **T4 — idempotent re-publish:** same owner re-claims → allowed (marker body matches).
- **T5 — resolve by marker BODY, not name:** a slug whose marker says `owner_plane:flask` resolved
  via the SAM edge → clean non-probeable 404 (decided from the body, never by parsing the slug).
- **T6 — safe rename:** rename claims the new slug before releasing the old; crash mid-rename never
  double-owns or orphans; old marker gone + new present + artifact moved.
- **T7 — format/reserved:** `Acme!`, `admin`, 2-char slugs rejected BEFORE any claim.
- **T8 — clobber backstop:** publish into a `{slug}/` holding a different owner's artifact → refused.
- **T9 — prefix required:** `aanmelden` (no tenant prefix) rejected; `h-dcn-aanmelden` accepted.
- **T10 — can't borrow another prefix:** tenant `acme` claiming `h-dcn-foo` → rejected.
- **T11 — grandfathering:** an existing non-conforming live slug (incl. uppercase
  `GoodwinSolutions`) still resolves/serves and is NOT force-renamed by the migration.

## Non-goals (v1)

- No shared cross-plane database. No Flask publishing the SAM form; no SAM reading Flask's data.
- No reviving Flask config authoring for the form.
- The `*.{tenant-id}.jabaki.nl` host reshape (parked in the hosting backlog) — this spec stays on
  the flat `*.jabaki.nl` path and ADOPTS only the page-as-unit principle.
- The hosting account cutover itself (owner-run, `jabaki-hosting-migration-to-nonprofit`).
- Spec 13 R3 dropdown color — the final cosmetic step, applied in the one renderer AFTER serving
  settles; not in this spec.

## Open questions (to resolve in design)

1. Page-registry HOME: a generalized `tenant_slugs`/new `tenant_pages` table, or extend
   `tenant_slugs` with a page dimension? (MySQL shape + migration safety.)
2. DynamoDB per-page SK form (`PAGE#{page_id}` vs `{kind}#{slug}`) and the `migrate_slug`/draft
   rework.
3. D6 final: stay on the S3 `_slugs/{slug}` marker (spec 12) or introduce a slug GSI now that the
   page registry exists.
4. D4: does the shell/`LandingPageStyles` extract cleanly, or is SAM-renders-own-shell the v1?
5. Exact reconciliation seam with `jabaki-hosting-migration-to-nonprofit` (which changes land
   there vs here).
