# Requirements Document

**Spec 14 — SAM Public-Pages Platform (application-form-first)**

## Introduction

This spec defines a **SAM-plane public-pages platform** that serves tenant-specific public pages
(the member application form first; webshop, event calendar, and more to follow) at
`{slug}.jabaki.nl`, with the form's submit writing into the members module. It explicitly does NOT
reshape the live Flask landing module; "page is the unit" is realized in the SAM plane, and the
landing page is a FUTURE producer that migrates onto the same contracts later. The full rationale,
scope boundary, and the four producer contracts are detailed in the sections below; the numbered
requirements (R1–R9) follow the Glossary.

- Status: **Draft** (requirements phase — review before design). **Reframed 2026-11-01**: this
  spec is no longer a generalization of the Flask landing-page registry. It is a **SAM-plane
  public-pages platform**, with the member application form as the FIRST producer, designed so
  additional page kinds (webshop, event calendar, …) and a FUTURE landing-page migration plug into
  the same contracts.
- Origin: the decision brief in `13 - application-form-rendering-polish/next-steps.md`
  (decisions D1–D7, locked 2026-10-31), **as amended by the 2026-11-01 scope decision** that the
  live Flask landing module is NOT reshaped by this spec (see "Scope decision" below).
- **Reconcile-with (do NOT fork or duplicate):**
  `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit` owns the hosting TOPOLOGY
  (S3 `myadmin-public-pages-*` bucket + `*.jabaki.nl` CloudFront distribution + ACM + the
  url-rewrite function + the `domain_mapping` / `application_embed_origins` KVS + backend IAM),
  and the parked `*.{tenant-id}.jabaki.nl` host model. This spec ADDS a SAM publish/serve path +
  a shared slug namespace INTO that topology (D7). It MUST NOT invent a parallel slug store, a
  parallel bucket, or a parallel CloudFront path.
- Governing steering: `20-platform-architecture`, `35-sam-module-architecture-sam`,
  `31-backend-database-flask-mysql`, `37-shared-building-blocks`, `43-cicd-deploys`
  (Terraform plan-first, owner-run cutover), `23-aws-accounts`, `34-backend-testing`,
  `33-frontend-testing`, `40-spec-workflow`.
- Supersedes nothing; spec 12's SAM publish/serve requirements are SUBSUMED here under the
  generalized page-producer model (the form becomes the first page kind among N).

## Glossary

- **Producer** — a page kind that owns its own data (under its plane's tenancy), claims/resolves
  its slug via the shared `_slugs/{slug}` marker, renders via the shared library, and publishes an
  artifact into the shared dumb infra. The application form is the first producer.
- **`kind`** — the page type recorded in the slug marker body. An OPEN set: `application_form`
  (now); `webshop`, `event_calendar`, `landing` (expected future kinds, not limiting).
- **Slug marker (`_slugs/{slug}`)** — a control-plane S3 object whose body
  `{owner_plane, kind, tenant_id, resource_ref}` is the authoritative owner/resolution record and
  the atomic cross-plane uniqueness gate (conditional `put_object`).
- **Shared dumb infra** — the S3 public-pages bucket + the `*.jabaki.nl` CloudFront distribution +
  the stateless url-rewrite function + the `domain_mapping` / `application_embed_origins` KVS.
  Owned by the hosting-migration backlog; shared by all producers (mechanism, not store).
- **Plane** — `sam` (the module plane, `tenant_id` tenancy) or `flask` (the landing plane,
  untouched here).

## Scope decision (2026-11-01) — the Flask landing module is NOT touched

The earlier draft of this spec delivered "page is the unit" by **reshaping the live Flask landing
module**: a new `tenant_pages` MySQL table (old OQ1), re-keying the `myadmin-landing-pages`
DynamoDB store from `SK=LANDING#HOME` to a per-page SK (old OQ2), relaxing
`tenant_slugs.administration UNIQUE`, generalizing `get_slug(tenant)`/`rename_slug`/`migrate_slug`,
and migrating the 7 live landing tenants. **That approach is dropped.**

Rationale: the sustainable future for tenant-specific websites — application form now, then
webshop, event calendar, and eventually the landing page itself — is on the **SAM plane** (its
own `tenant_id` tenancy, own Lambda, own store). Reshaping the Flask landing store first would be
work discarded at the eventual SAM move, and it risks the live landing tenants for no lasting gain.
So:

- **The current Flask landing module is LEFT EXACTLY AS-IS.** No change to
  `landing_page_service.py`, `tenant_slugs`, the `myadmin-landing-pages` key shape, or
  `get_slug`/`rename_slug`/`migrate_slug`. Old OQ1 and OQ2 are **withdrawn** (recorded in the ADR,
  R8).
- **"Page is the unit, N pages per tenant" is realized IN THE SAM PLANE** — the form (and future
  SAM kinds) carry their own addressing on their own `tenant_id`-partitioned records. Landing is a
  FUTURE producer that migrates INTO this platform on the same contracts; it is NOT a prerequisite
  and is NOT done here.

## Context

The member application form (SAM plane) must be served as a PUBLIC, per-tenant page at
`{slug}.jabaki.nl`, optionally reached via a tenant-owned custom domain (CNAME, URL preserved, no
redirect), and its submit must write an application into the members module. More page kinds
(webshop, event calendar, …) are coming on the same plane. There is no lasting value in reshaping
the Flask landing store to achieve this; the value is in a **sustainable SAM page-producer
platform** that any kind — and a migrated landing page later — can join.

Verified in code:
- The Flask landing store `landing_page_service.py` (`PK=TENANT#{slug}, SK=LANDING#HOME`, 5-store
  `rename_slug`) is the module this spec must NOT touch.
- The SAM members module already has the form config surface (`config#fields`, disjoint
  `set_field` / `set_field_application` ops) and a readiness-gated
  `POST /members/application-form/publish` route whose live S3 write is "dormant until the hosting
  migration." The publish CONTROL exists; the public read/submit path and the slug marker are the
  NEW work.
- The serving layer is ALREADY shared and generic (one `*.jabaki.nl` distribution + a stateless
  slug-path rewrite + the shared bucket), and CNAME-without-redirect ALREADY works via
  `tenant_custom_domains` + the `domain_mapping` KVS. So the gap is the SAM PRODUCER (publish +
  public data endpoints) + the shared slug NAMESPACE, not the serving plumbing.

## Guiding principles (from the brief, as amended)

- **Page is the unit, realized per plane** (D2, amended). No hard-coded one-page-per-tenant limit
  in the SAM plane. The Flask landing plane keeps its current 1:1 shape UNCHANGED (its
  generalization is a future migration, not this spec).
- **Each page kind is a PRODUCER on four shared contracts** (D3, D5/D6, D4): a producer (1) owns
  its data under `tenant_id` in its own store/Lambda, (2) claims/resolves its slug via the shared
  `_slugs/{slug}` marker, (3) renders via the shared rendering LIBRARY, and (4) publishes its
  artifact into the shared dumb infra. The application form is the first producer; new kinds add a
  producer, not a new serving path.
- **No runtime SAM↔Flask communication; shared DUMB infra only** (D3). The only shared surfaces
  are the S3 bucket, the stateless CloudFront function, and the two KVS. A shared cross-plane
  DATABASE table is forbidden (steering 35 rule 5a).
- **Reuse the mechanism, not the store or a runtime call** (D4). A shared, dependency-free
  rendering library may be imported by any producer; this is NOT cross-plane communication.
- **Reconcile with the hosting backlog, do not fork** (D7).
- **Do not regress the live landing tenants** — by leaving the landing module untouched, the 7
  live landing slugs/domains/artifacts keep serving identically; verification is that nothing in
  the landing plane changed.

## Requirements

> **Requirement IDs (contiguous, renumbered 2026-11-01):** R1 … R10, in document order below.
> An earlier draft used non-contiguous IDs (`R2c`, `R3a`) inherited from the 2026-10-31 review;
> they have been renumbered to a clean sequence. Mapping from the old IDs, for anyone following a
> stale reference: old `R2c` → **R3**; old `R3a` → **R4**; old `R3` → **R5**; old `R4` → **R6**;
> old `R5` → **R7**; old `R6` → **R8**; old `R7` → **R9** (R1, R2 unchanged). **R10** (security) was
> added 2026-11-01 to make the design's SEC-1…SEC-10 controls testable obligations.

### R1 — Page is the unit of public addressing in the SAM plane [D2, amended]

**User story:** As a tenant admin, I want the application form (and later webshop, event calendar,
and more) served as its own public page at its own address, with a tenant able to own N such pages,
without being limited to one page and without my current landing page being affected.

#### Acceptance criteria
1. The SAM platform SHALL model a PAGE as `(tenant_id, kind, slug, published_artifact,
   resource_ref)`, allowing N pages per tenant. `kind` is an OPEN, extensible set (R3.5).
2. SAM page identity SHALL live on the SAM-owned record for that kind (the application form on its
   `config#fields` row per spec 12 — slug + publish-state), under the module's `tenant_id`
   tenancy. There SHALL be NO shared cross-plane registry table and NO new Flask table.
3. No SAM code path SHALL assume one page per tenant; a tenant MAY own multiple SAM pages across
   kinds.
4. The current Flask landing module SHALL NOT be modified by this spec (Scope decision). Any
   landing-plane generalization is explicitly a FUTURE migration into this platform, out of scope
   here.
5. The live landing tenants SHALL be unaffected: because the landing module is untouched, the 7
   live landing slugs, custom domains, and published artifacts continue to serve identically.
   Verification = no diff in the landing plane.

> **Registry scope clarification:** there is NO single shared page-registry table. Each producer
> registers its own pages in its own store (SAM form on `config#fields`; a future landing producer
> on its own SAM store after migration). The only SHARED thing is the slug NAMESPACE, enforced by
> the `_slugs/{slug}` marker (R4) — never a shared registry database (steering 35 rule 5a).

### R2 — Tenant public prefix + opaque slug model [business rule]

**User story:** As the platform, I want every public slug to carry the tenant's short public
prefix, so popular names (e.g. `aanmelden`) are not globally land-grabbed by the first tenant, and
each tenant owns its own slug sub-namespace across ALL planes/apps.

#### Acceptance criteria
1. Each tenant SHALL have ONE short **public prefix** — chosen once, globally unique, slug-safe
   (`SLUG_PATTERN`, ~3–20 chars) — that is the tenant's single public identity across ALL planes
   and apps (future landing, SAM members form, future SAM kinds). (`h-dcn` is `h-dcn`'s prefix for
   every kind: `h-dcn`, `h-dcn-aanmelden`, `h-dcn-clubdag`, …).
2. The prefix SHALL be authored in MySQL as an attribute on the tenant record (the tenant
   system-of-record, steering 20), and carried READ-ONLY to the SAM plane as an attribute on the
   ALREADY-PROJECTED `tenant` governance-projection row (`SK="tenant"`, `projection_schema.py`) —
   an ADDITIVE field on an existing projected record, NOT a new table or a new projection
   mechanism. SAM validates the prefix from its own projected `tenant` row, never by calling Flask.
   This touches the tenant record + the projection builder ONLY — NOT the landing module (the Scope
   decision holds: `tenants.public_prefix` is a tenant-record attribute, independent of landing).
3. A new page slug SHALL be `{prefix}` or `{prefix}-{suffix}` and SHALL be validated at claim time
   to start with the AUTHENTICATED tenant's prefix; a tenant SHALL NOT claim a slug under another
   tenant's prefix. Long administration names (e.g. `vandenheuvelhoveniers`) use their SHORT prefix,
   not the full name.
4. The slug string SHALL be an OPAQUE public address otherwise: it SHALL NOT encode plane/app type,
   and NO code SHALL infer tenant, plane, or kind by parsing the slug string — those are resolved
   from the `_slugs/{slug}` marker body + the producer's own record (R4).
5. Existing live slugs SHALL be GRANDFATHERED: the live landing slugs (including uppercase ones
   like `GoodwinSolutions`/`PeterPrive` that would FAIL new `SLUG_PATTERN`/prefix validation) keep
   working and SHALL NOT be force-renamed. The prefix rule applies to NEW claims only.
6. Format/reserved validation (`SLUG_PATTERN`, reserved words, length) SHALL run BEFORE the
   uniqueness claim; the prefix rule is additive on top of it.

### R3 — Shared publish contract: each producer publishes a page into the shared dumb infra [D3]

**User story:** As the platform, I want every page producer to publish through one shared
infrastructure without calling any other plane, so there is one serving story and no cross-plane
coupling.

#### Acceptance criteria
1. A published page SHALL consist of: a rendered `{slug}/index.html` in the shared
   `myadmin-public-pages-{env}` bucket; optionally a `{slug}/form.json` (or kind-specific) data
   artifact; a claimed slug in the shared slug registry (the `_slugs/{slug}` marker); optional
   custom-domain host→slug entries in the `domain_mapping` KVS; and a CloudFront invalidation for
   `/{slug}/*`.
2. SAM SHALL render + write the application-form artifact. A producer SHALL NOT read or write
   another plane's datastore, call another plane's API, or depend on it at request time (steering
   35 rule 5a; the no-runtime-comms principle). The UNTOUCHED Flask landing plane continues to
   publish its own landing artifact exactly as it does today.
3. A shared cross-plane DynamoDB table or record SHALL NOT be introduced. The shared surfaces are
   EXACTLY: the S3 bucket, the stateless CloudFront url-rewrite function, and the two KVS.
4. Slug/domain claiming SHALL enforce global slug uniqueness via a dumb-infra mechanism (the S3
   `_slugs/{slug}` marker, D6) — not a shared database arbiter.
5. **`kind` is an OPEN, extensible set, not a closed enum.** `application_form` is the kind
   implemented now. `webshop`, `event_calendar`, and `landing` are named as EXPECTED FUTURE kinds
   — **including but not limited to these**. Adding a kind SHALL be a new producer writing a new
   `kind` value into the marker body + the shared infra; it SHALL NOT require a change to the
   `_slugs` resolver, the CloudFront function, or the shared rendering library.

### R4 — Slug uniqueness: one authoritative cross-plane gate

**User story:** As the platform, I want it to be impossible for two pages (even across planes or
kinds) to claim the same slug, so a public host resolves to exactly one page.

#### Acceptance criteria
1. The AUTHORITATIVE uniqueness gate SHALL be an ATOMIC conditional `put_object` on
   `_slugs/{slug}` with `If-None-Match: *` in the shared bucket: the write succeeds only if the
   object does not exist; a racing second claimer (ANY plane/kind) gets `412 PreconditionFailed` →
   `SlugTaken`. This is the cross-plane gate that needs no shared database.
   (If `If-None-Match: *` is not available for the target bucket/region, the sanctioned fallback is
   a DynamoDB conditional `PutItem(attribute_not_exists(pk))` on a dedicated slug-claim table — but
   S3 conditional put is preferred; VERIFY availability before locking, see design.)
2. The `_slugs/{slug}` marker BODY SHALL record the slug's backing — `{owner_plane, kind,
   tenant_id, resource_ref}` — and SHALL be the source of truth for ownership/resolution. The
   serving/submit edge SHALL decide ownership by READING THE MARKER BODY, never by parsing the slug.
   `kind` is an OPEN set (R3.5).
3. Per-plane `UNIQUE`/validation (SAM config-row slug check; a future landing producer's own check)
   MAY run first as a FAST-FAIL UX check, but SHALL NOT be relied on as the guarantee (it cannot
   see the other plane/kind).
4. A re-publish by the SAME owner (marker body matches `owner_plane`+`kind`+`tenant_id`) SHALL be
   idempotent (allowed); a claim whose body would not match SHALL be rejected as a conflict.
5. A publish SHALL NOT clobber a `{slug}/` artifact it did not author (owner-tag backstop, defense
   in depth).
6. A slug RENAME SHALL claim the new slug (conditional put) BEFORE releasing the old marker, so a
   crash mid-rename never leaves a slug double-owned or orphaned.

### R5 — SAM application-form as the first page producer (public data path) [D5/D6]

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
   `_slugs/{slug}` marker (spec 12's choice, D6) — never the h-dcn Events scan anti-pattern.
4. The published `{slug}/index.html` SHALL be a thin self-contained shell that fetches the schema
   from `GET {slug}` and renders it with the existing `ApplicationFormRenderer` (one renderer for
   preview, native block, and published artifact).
5. The submit `POST` SHALL resolve tenant from the slug AS DATA (never an env map), stay
   token-less and non-probeable, and SHALL write the application into the MEMBERS MODULE's own
   `tenant_id`-partitioned store via its own Lambda (never Flask's store). Its Lambda role SHALL
   have write IAM on the target applications table (verify this is already granted — brief open
   item; add least-privilege if missing).

### R6 — CNAME custom domains, URL preserved, per page [D1]

**User story:** As a tenant admin, I want to point my own domain at a page via CNAME and keep my
domain in the address bar (no redirect to `*.jabaki.nl`).

#### Acceptance criteria
1. A page's public address SHALL be `{slug}.jabaki.nl`, served by the existing shared CloudFront
   distribution + stateless slug-path rewrite (no new per-tenant infra, no request-time tenant
   lookup).
2. A tenant SHALL be able to attach a custom domain to a PAGE via the existing
   `tenant_custom_domains` + ACM + CloudFront-alias + `domain_mapping` KVS mechanism. The custom
   domain SHALL serve the page content WITHOUT a redirect (URL preserved). (This reuses the shared
   mechanism; it does not require reshaping the landing module.)
3. CSP `frame-ancestors` for an application-form host SHALL come from the existing
   `application_embed_origins` KVS + viewer-response function; a host with no entry denies framing
   (`'none'`).

### R7 — Shared rendering library (reuse the mechanism) [D4]

**User story:** As a maintainer, I want the form (and future kinds) to share the generic HTML
shell/CSS without a cross-plane runtime call, so look-and-feel is consistent and maintained once.

#### Acceptance criteria
1. The generic HTML shell + CSS/SEO/footer scaffolding SHALL be extracted into a plane-neutral,
   dependency-free module (`page_shell` + the shared `LandingPageStyles`, verified `re`/`typing`-
   only) that any producer imports. The SAM form SHALL render its shell via `page_shell`.
2. The Flask `generate_index_html` SHALL NOT be refactored by this spec (that is a landing-module
   change — Scope decision). Sharing the library with the landing plane is a FUTURE opportunity,
   noted, not done here. If clean extraction surfaces a hidden coupling, SAM renders its own shell
   for v1 and the shared library is deferred (noted, not silently dropped).
3. Sharing SHALL be as an imported LIBRARY (pure functions), never a runtime call or a shared
   store.

### R8 — ADR + governance actions [brief ⚠ section]

**User story:** As a maintainer, I want these architectural decisions tracked so future specs
inherit them and they are not lost in a scratch file.

#### Acceptance criteria
1. A NEW ADR "SAM Public-Pages Platform" SHALL be authored, recording: page-as-unit realized PER
   PLANE; the application form as the first producer; the FOUR producer contracts; the OPEN `kind`
   set (webshop, event_calendar, landing named as expected future kinds, NOT limiting); the
   no-shared-DB rule (5a); and that the Flask reshape (old OQ1/OQ2 — `tenant_pages`, landing
   DynamoDB re-key) is WITHDRAWN, with the reason (future landing migration belongs on the SAM
   platform, not a discarded Flask reshape).
2. ADR 0003 (platform base) and ADR 0005 (MySQL system-of-record + projection) SHALL be REVIEWED
   for consistency with the platform framing.
3. This spec SHALL cross-reference `jabaki-hosting-migration-to-nonprofit` and SHALL NOT duplicate
   its hosting cutover; slug/KVS/bucket usage reconciles with that backlog's topology (D7) and
   introduces NO parallel slug store, bucket, or CloudFront path.

### R9 — Testing (change-with-tests)

#### Acceptance criteria
1. SAM tests: public `GET {slug}`/`POST {slug}` are no-auth, whitelist-filtered, slug-resolved via
   the marker (not scan), publication-gated, and 404 unknown/unpublished non-probeably.
2. SAM submit test: a public `POST {slug}` routes the application to the correct tenant's members
   store (resolved from the marker body as data), and a foreign/cross-plane slug is rejected.
3. Shared-lib tests: `page_shell`/`LandingPageStyles` output parity against a fixture.
4. Frontend tests: the published shell fetches + renders via `ApplicationFormRenderer`.
5. Landing-plane NON-regression: assert (by scope, not by migration) that no landing-module file,
   table, or key shape is changed by this spec.
6. Paired tests land in the SAME change as the behavior (steering 30/34/33).

#### Slug-uniqueness + prefix test list (R2 / R4) — T1–T11
> **Discipline (HC6 lineage):** T2 (cross-plane) and T3 (race) MUST run against REAL S3 (or an
> emulator that genuinely enforces `If-None-Match`), NEVER a mock that just returns success — the
> guarantee IS an S3 behaviour; a mock would go green while the guarantee is absent.

- **T1 — same-plane duplicate:** claim `h-dcn-x` twice (same producer) → 2nd → `SlugTaken`/412.
- **T2 — cross-plane/kind duplicate:** claim a slug as one kind, then as another → 2nd →
  `SlugTaken` (the whole point — a per-record UNIQUE cannot give this). _Real S3._
- **T3 — concurrency race:** N concurrent claims for one slug → EXACTLY ONE succeeds, N−1 get 412
  (proves atomicity, not check-then-write). _Real S3._
- **T4 — idempotent re-publish:** same owner re-claims → allowed (marker body matches).
- **T5 — resolve by marker BODY, not name:** a slug whose marker says a different `owner_plane`/
  `kind` resolved via the SAM edge → clean non-probeable 404 (decided from the body, never by
  parsing the slug).
- **T6 — safe rename:** rename claims the new slug before releasing the old; crash mid-rename never
  double-owns or orphans; old marker gone + new present + artifact moved.
- **T7 — format/reserved:** `Acme!`, `admin`, 2-char slugs rejected BEFORE any claim.
- **T8 — clobber backstop:** publish into a `{slug}/` holding a different owner's artifact → refused.
- **T9 — prefix required:** `aanmelden` (no tenant prefix) rejected; `h-dcn-aanmelden` accepted.
- **T10 — can't borrow another prefix:** tenant `acme` claiming `h-dcn-foo` → rejected.
- **T11 — grandfathering:** an existing non-conforming live slug (incl. uppercase
  `GoodwinSolutions`) still resolves/serves and is NOT force-renamed.

### R10 — Security of the public, unauthenticated, multi-tenant surface

**User story:** As the platform owner, I want the public page endpoints to be safe to expose to the
open internet, so that unauthenticated traffic cannot leak tenant data, abuse the write path,
cross tenant boundaries, or be used for phishing/clickjacking.

> This requirement makes the design's `## Security Considerations` controls (SEC-1 … SEC-10)
> TESTABLE OBLIGATIONS. Each AC below carries its SEC-id; the design section owns the mechanism,
> this requirement owns the obligation + its paired test. SEC-1…SEC-8 are the PLATFORM BASELINE
> (every page kind inherits them); SEC-9/SEC-10 are APPLICATION-FORM specific. Kind-specific
> security for other kinds (e.g. webshop commerce controls) is OUT OF SCOPE here (see Non-goals).

#### Acceptance criteria
1. **(SEC-1) Public read is fail-closed.** `GET {slug}` SHALL return applicant fields via an
   ALLOWLIST; a field not on the allowlist SHALL be omitted (unknown/new attributes default
   HIDDEN), and secrets SHALL appear at most as a boolean existence flag. A paired test SHALL
   assert no un-whitelisted field escapes into the response.
2. **(SEC-2) Unauthenticated write is abuse-resistant.** `POST {slug}` SHALL enforce, BEFORE the
   write and before going live: a per-source rate limit / throttle; a CAPTCHA or equivalent
   challenge; a payload SIZE CAP; and PER-FIELD type / allowed-value validation (email is an email,
   enum within published options, required present, unexpected fields rejected).
3. **(SEC-3) No cross-tenant write.** `POST {slug}` SHALL resolve the tenant ONLY from the marker
   body (never by parsing the slug) and write solely to that `tenant_id`; a foreign/cross-plane
   slug SHALL be rejected. The paired tests (T5 + the cross-tenant rejection test) SHALL run
   against REAL behaviour, never a mock (HC6).
4. **(SEC-4) No slug squatting under another tenant.** Every claim path SHALL enforce the
   tenant-prefix rule (R2.3); the uniqueness gate alone (R4.1) SHALL NOT be relied on for this. A
   paired test SHALL assert a claim outside the authenticated tenant's prefix is rejected.
5. **(SEC-5) Enumeration-safe.** Unpublished and unknown slugs SHALL return an IDENTICAL,
   timing-insensitive 404 (status + body), so existence cannot be enumerated.
6. **(SEC-6) DoS-bounded.** The public `GET/POST {slug}` functions SHALL sit behind edge
   throttling / WAF, and slug resolution SHALL be O(1) keyed lookup (never a scan, R5.3), so flood
   traffic cannot amplify cost or exhaust the datastore.
7. **(SEC-7) Framing defaults closed.** CSP `frame-ancestors` SHALL default to `'none'` when a host
   has no `application_embed_origins` entry; tenant-authored embed origins SHALL be input-validated
   (well-formed origin, no wildcard-all, no injection) before being written to the KVS.
8. **(SEC-8) Least-privilege publish IAM.** The publish role SHALL be PREFIX-SCOPED to its own
   `{slug}/*` artifacts and the `_slugs/{slug}` markers it owns — never bucket-wide `s3:PutObject`;
   reviewed Terraform-plan-first (gated Task 9).
9. **(SEC-9) Applicant PII handling.** A submission SHALL be treated as personal data: minimized to
   the form's declared fields, scoped to the owning `tenant_id`, and subject to the tenant's
   retention + a deletion path; for EU tenants, GDPR lawful-basis/minimization/erasure obligations
   apply.
10. **(SEC-10) No stored-XSS on admin re-display.** Applicant-supplied free-text SHALL be
    sanitized/encoded at the trust boundary so a submitted value cannot execute script when
    re-displayed in the authenticated admin review UI. A paired test SHALL assert a `<script>`
    payload is neutralised on output.
11. Each of R10.1–R10.10 SHALL have a paired test landing in the SAME change as the control
    (steering 30/34/33); the critical trio (SEC-1/2/3) and SEC-4 SHALL be proven against real
    behaviour, never a success-returning mock.

## Non-goals (v1)

- **Any change to the Flask landing module** — `landing_page_service.py`, `tenant_slugs`, the
  `myadmin-landing-pages` key shape, `get_slug`/`rename_slug`/`migrate_slug`. (Scope decision; old
  OQ1/OQ2 withdrawn.)
- A shared cross-plane database. No Flask publishing the SAM form; no SAM reading Flask's data.
- No reviving Flask config authoring for the form.
- The landing-page migration INTO this platform (a future spec, on these same four contracts).
- The `*.{tenant-id}.jabaki.nl` host reshape (parked in the hosting backlog) — this spec stays on
  the flat `*.jabaki.nl` path.
- The hosting account cutover itself (owner-run, `jabaki-hosting-migration-to-nonprofit`).
- Spec 13 R3 dropdown color — the final cosmetic step, applied in the one renderer AFTER serving
  settles; not in this spec.

## Resolved scope questions (were "open questions")

1. **Flask page-registry shape (old OQ1):** WITHDRAWN — the Flask landing module is not reshaped;
   SAM page identity lives on the SAM `config#fields` row.
2. **Landing DynamoDB per-page SK (old OQ2):** WITHDRAWN — `myadmin-landing-pages` key shape is
   left as-is.
3. **Slug mechanism (D6):** the shared S3 `_slugs/{slug}` marker (NOT a slug GSI), verified for
   `If-None-Match` support before locking (design).
4. **Shared shell (D4):** extract `page_shell` for SAM; do NOT refactor Flask `generate_index_html`
   (Scope decision); SAM-renders-own-shell is the fallback if extraction snags.
5. **Reconciliation seam with the hosting backlog:** the live S3 write + invalidation are GATED on
   that backlog; everything up to the write (claim, render, tests) proceeds now.
