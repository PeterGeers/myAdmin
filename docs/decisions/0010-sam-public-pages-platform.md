# ADR 0010 — SAM Public-Pages Platform: page-as-unit realized per plane, the application form as the first producer on four shared contracts

- Status: Accepted
- Date: 2026-11-01
- Relates to: ADR 0003 (myAdmin is the platform base; apps as SAM-backed modules — this
  platform is the public-page face of a SAM module), ADR 0005 (MySQL system-of-record +
  one-directional MySQL→DynamoDB projection — the tenant `public_prefix` rides that projection,
  read-only, no new writer), ADR 0008 (public unauthenticated intake on the SAM edge — the
  token-less public-endpoint fence this platform's public `GET`/`POST {slug}` reuse). Introduced
  by spec `.kiro/specs/Members/14 - public-pages-multi-tenant-serving/`
  (`requirements.md` R1/R3/R4/R7/R8, `design.md` Overview + D-SLUG + D-RENDER, R8 governance task).

## Context

myAdmin must serve tenant-specific PUBLIC pages at `{slug}.jabaki.nl` — the member application
form first, with webshop, event calendar, and more to follow — and the form's submit must write an
application into the members module. The serving plumbing already exists and is generic: one
shared `*.jabaki.nl` CloudFront distribution + a stateless slug-path rewrite + the shared bucket,
with CNAME-without-redirect already working via `tenant_custom_domains` + the `domain_mapping` KVS.
The gap was never the serving layer; it was a SAM-plane PRODUCER (publish + the public read/submit
endpoints) and a shared slug NAMESPACE.

An earlier draft of the spec proposed delivering "page is the unit" by reshaping the live Flask
landing module: a new `tenant_pages` MySQL table (open question OQ1), re-keying the
`myadmin-landing-pages` DynamoDB store from `SK=LANDING#HOME` to a per-page SK (OQ2), relaxing
`tenant_slugs.administration UNIQUE`, generalizing `get_slug`/`rename_slug`/`migrate_slug`, and
migrating the 7 live landing tenants. That approach put live landing tenants at risk to build
machinery that would be discarded the moment tenant-specific websites moved to the SAM plane — the
sustainable home for application forms, webshops, calendars, and eventually landing itself.

This ADR records the reframed decision (2026-11-01): build a SAM-plane public-pages PLATFORM with
the application form as its first producer, leave the Flask landing module exactly as-is, and
withdraw OQ1/OQ2. It also records what tasks 1–6 of the spec actually built, so the decision is
anchored to shipped code, not just intent.

## Decision

**Build a SAM-plane public-pages platform in which a published page is the unit, realized per
plane; the application form is the first producer; every producer satisfies the same four shared
contracts; `kind` is an open extensible set; producers share no database; and the old Flask-reshape
open questions (OQ1/OQ2) are withdrawn.**

### 1. Page is the unit, realized PER PLANE — not via a shared cross-plane page store

The platform treats a published page — `(tenant_id, kind, slug, published_artifact, resource_ref)`
— as the unit of public addressing, with N pages per tenant and no hard-coded one-page-per-tenant
limit. Crucially this is realized PER PLANE: SAM page identity lives on the SAM-owned record for
that kind (the application form on its `config#fields` row under `tenant_id`), NOT in any shared
cross-plane registry table. The Flask landing plane keeps its current 1:1 shape UNCHANGED; it is a
FUTURE producer that migrates INTO this platform on the same four contracts in a later spec. There
is no single shared page-registry database — the only SHARED surface is the slug namespace,
enforced by the `_slugs/{slug}` marker, never a shared registry DB (steering 35 rule 5a).

### 2. The application form is the FIRST producer

The member application form is the first producer of the platform. Its existing readiness-gated
`POST /members/application-form/publish` route becomes the publish producer, and the NEW public
`GET {slug}` (schema) and `POST {slug}` (submit → members store) are its public data path. New page
kinds join by adding a producer, never a new serving path. The form proves the platform end-to-end;
subsequent kinds inherit it for free.

### 3. The FOUR producer contracts

Each producer satisfies exactly four contracts; nothing else reads its store or calls it at request
time:

1. **Owns its data** under its plane's own tenancy (`tenant_id` for SAM; the form on its
   `config#fields` row, spec 12). No producer reads another plane's store.
2. **Claims / resolves / releases its slug** via the shared `_slugs/{slug}` S3 marker — an atomic
   conditional `put_object` with `If-None-Match: *` for the claim (412 → `SlugTaken`),
   resolve-by-body for lookup, and a release on teardown. This is the authoritative cross-plane
   uniqueness gate, with ownership decided from the marker BODY, never by parsing the slug string.
3. **Renders** via the shared, dependency-free rendering LIBRARY (`page_shell.render_page` +
   `LandingPageStyles`) — a library import, never a cross-plane runtime call or a shared store.
4. **Publishes** its `{slug}/index.html` (+ optional data artifact) into the shared bucket, behind
   the shared `*.jabaki.nl` CloudFront distribution + stateless slug-path rewrite, with a
   CloudFront invalidation.

### 4. `kind` is an OPEN, extensible set — documentation, not an allow-list

The `kind` field in the marker body is an OPEN set, not a closed enum. `application_form` is live
now; `webshop`, `event_calendar`, and `landing` are named as EXPECTED future kinds — INCLUDING BUT
NOT LIMITED TO these. Adding a kind is a new `kind` value in the marker body + a new producer; the
`_slugs` resolver, the CloudFront function, and the rendering library do NOT change. The shipped
code encodes this precisely: `slug_marker_store.KNOWN_KINDS` is a documentation tuple a reader can
consult to recognise the kinds in play today, and the store NEVER gates a claim against it — a
paired test (`test_claim_allows_a_kind_not_in_known_kinds`) asserts an unlisted kind is claimable,
so the open-set design cannot silently regress into an enum.

### 5. No shared database between producers (steering 35 rule 5a)

Producers do not share a database. Each owns its own store under its own tenancy; a producer never
reads another plane's datastore, calls another plane's API, or depends on it at request time. The
one cross-plane coordination surface is the `_slugs/{slug}` marker — an S3 control-plane object
(never served), not a shared DB arbiter. The S3 conditional-put condition IS the uniqueness check,
so cross-plane uniqueness holds without any shared database. This is consistent with ADR 0005: the
tenant `public_prefix` the SAM claim path validates against is carried READ-ONLY on the
already-projected `tenant` governance row via the existing one-directional MySQL→DynamoDB
projection — an additive attribute, no new writer, no new projection mechanism, and no request-time
call back to Flask.

### 6. OQ1 and OQ2 are WITHDRAWN

The old open questions are withdrawn:

- **OQ1 — new Flask `tenant_pages` MySQL table: WITHDRAWN.** The Flask landing module is not
  reshaped. SAM page identity lives on the SAM `config#fields` row under `tenant_id`, not in any
  new Flask table.
- **OQ2 — re-key `myadmin-landing-pages` to a per-page SK: WITHDRAWN.** The landing DynamoDB key
  shape (`PK=TENANT#{slug}, SK=LANDING#HOME`) is left exactly as-is.

The reason: the future landing migration belongs ON this SAM public-pages platform — landing will
migrate INTO the platform on the same four contracts in a later spec, carrying it onto SAM's model.
Reshaping the live Flask store first is work discarded at that move and risks the live landing
tenants for no lasting gain. Accordingly the live Flask landing module (`landing_page_service.py`,
`tenant_slugs`, the `myadmin-landing-pages` key shape, `get_slug`/`rename_slug`/`migrate_slug`) is
NOT touched by this spec.

## Rationale

- **Page-as-unit per plane** gives the SAM plane N pages per tenant without inventing a shared
  cross-plane registry — the thing steering 35 rule 5a forbids. Each plane realizes the unit on its
  own store, and the only cross-plane thing is the slug namespace, which a dumb S3 marker can
  arbitrate atomically.
- **Four contracts** turn "add a public page kind" into "add a producer" — the resolver, serving
  layer, and rendering library are kind-agnostic, so the open `kind` set is safe to extend and a
  new kind carries no new serving path.
- **An open `kind` set encoded as documentation-not-allow-list** keeps the platform extensible by
  construction; gating claims on a fixed enum would defeat the design, so the store deliberately
  never does, and a test pins that.
- **No shared database** preserves the plane-isolation invariant by construction (the SAM plane has
  no Flask client; the marker is S3, not a DB), consistent with ADR 0005's single-writer,
  one-directional projection posture for the `public_prefix` the claim path reads.
- **Withdrawing OQ1/OQ2** avoids throwaway work and live-tenant risk: the durable home for
  tenant websites is SAM, so landing migrates there later rather than being reshaped in place now.

## Consequences

- **The SAM public-pages platform is the home for tenant public pages going forward.** New kinds
  (webshop, event calendar, …) plug into the four contracts and inherit the platform's security
  baseline (SEC-1…SEC-8); they do not add serving paths.
- **The live Flask landing module is untouched and non-regressing.** The 7 live landing slugs,
  custom domains, and artifacts keep serving identically; verification is "no diff in the landing
  plane." Landing's migration onto this platform is a FUTURE spec, not a prerequisite.
- **The slug marker is the single cross-plane coordination surface.** It is an S3 control-plane
  object, never served, resolved by body. Any future producer — a webshop, a calendar, a migrated
  landing page — claims and resolves through it without a shared database.
- **`public_prefix` governance follows ADR 0005.** It is authored in MySQL on the tenant record and
  projected read-only onto the existing `tenant` row; SAM validates slugs against its own projected
  copy, never by calling Flask. No new table, no new projection mechanism, no second writer.
- **The live-publish write stays gated.** All account-agnostic work (slug marker, shared library,
  public `GET`/`POST {slug}`, prefix validation, tests) proceeds now; the live S3 put + CloudFront
  invalidation against the nonprofit-owned bucket/distribution are gated on
  `jabaki-hosting-migration-to-nonprofit` and introduce NO parallel slug store, bucket, or
  CloudFront path (D7 reconciliation).
- **Future landing migration is a known, deliberate follow-up.** Because OQ1/OQ2 are withdrawn
  rather than deferred-in-place, the migration is framed as "bring landing onto the platform," not
  "reshape the Flask store" — a clean target for a later spec.

## Related

- **ADR 0003** (`0003-myadmin-is-platform-base-modules-as-sam-apps.md`) — the platform base and the
  SAM-backed module contract this public-pages platform sits on; reviewed for consistency with the
  platform framing (spec 14 task 7.2).
- **ADR 0005** (`0005-two-pool-identity-mysql-system-of-record-one-directional-projection.md`) —
  MySQL system-of-record + one-directional MySQL→DynamoDB projection; the tenant `public_prefix`
  rides that projection read-only, with no second writer. Reviewed for consistency (task 7.2).
- **ADR 0008** (`0008-public-unauthenticated-intake-sam-edge.md`) — the fenced, token-less public
  intake pattern on the SAM edge (separate no-authorizer API, slug allow-list resolver,
  compensating controls) that this platform's public `GET`/`POST {slug}` endpoints reuse and extend
  to the open `kind` set.
- **Steering:** `.kiro/steering/35-sam-module-architecture-sam.md` (rule 5a — no shared cross-plane
  store; share the mechanism, not the store), `.kiro/steering/20-platform-architecture.md`,
  `.kiro/steering/43-cicd-deploys.md` (Terraform plan-first, owner-run cutover — the gated live
  write).
- **Spec:** `.kiro/specs/Members/14 - public-pages-multi-tenant-serving/` — `requirements.md`
  R1 (page-as-unit per plane), R2 (tenant prefix), R3 (shared publish contract + open `kind` set),
  R4 (slug uniqueness gate), R7 (shared rendering library), R8 (this ADR + governance); `design.md`
  Overview (four contracts), the "Withdrawn open questions (were OQ1/OQ2)" section, D-SLUG, D-RENDER.
- **Code as built:** `sam/members/repository/slug_marker_store.py` (slug marker claim/resolve/
  release; `KNOWN_KINDS` documentation-not-allow-list), `sam/shared/page_shell.py` (plane-neutral
  rendering library), `sam/members/handler/public_app.py` (public `GET`/`POST {slug}` edge), the
  tenant `public_prefix` + SEC-4 prefix rule on every claim path.

> **Reconciliation reminder (spec 14 task 7.3):** this platform ADDS a SAM publish/serve path + a
> shared slug namespace INTO the hosting topology owned by
> `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit`. It MUST NOT invent a parallel slug
> store, bucket, or CloudFront path — the live write reuses the nonprofit-owned bucket/distribution
> once that migration is complete.
