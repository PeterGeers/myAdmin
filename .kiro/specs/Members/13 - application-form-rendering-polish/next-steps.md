# Next Steps — Unified Multi-Tenant Public-Pages Architecture (Decision Brief)

> Planning artifact. No code changed. Captures the analysis + architectural decisions to lock before a full design/spec is written. Grounded in live code reads (myAdmin Flask landing stack, SAM plane, h-dcn patterns) and the `jabaki-hosting-migration-to-nonprofit` runbook.
>
> **Filing note:** this is an ARCHITECTURAL brief, not spec-13 rendering polish. It is parked here for continuity but should be PROMOTED to a tracked home (e.g. `.kiro/specs/Members/public-pages-architecture/` or alongside `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit/`) before it drives work — per `root-cause-analysis.md`, a decision left in a per-spec scratch file (often gitignored) is a "lesson lost in a few clicks" root cause.

## ⚠️ ADR ACTION REQUIRED

Before these decisions drive implementation, the following MUST be reviewed or added as Architecture Decision Records (ADRs), so the choices are tracked, reviewable, and inherited by future specs rather than living only in this brief:

- **NEW ADR — "Multi-tenant public-pages addressing: page as the unit, not tenant."** Records D2 (lift the `tenant_slugs` 1:1 limit → a page registry), the shared dumb-infra hand-off (D3), and the no-shared-DB / no-cross-plane-runtime rule applied to publishing. This is the load-bearing decision and currently has no ADR.
- **REVIEW ADR 0003** (myAdmin as platform base) — confirm the page-registry model is consistent with the platform-base framing; amend if the public-pages plane changes module boundaries.
- **REVIEW ADR 0005** (MySQL system-of-record + MySQL→DynamoDB projection) — the page registry touches `tenant_slugs`/`tenant_custom_domains` (MySQL) and the landing DynamoDB store; confirm the system-of-record invariants still hold and document the Flask-owns-DynamoDB exception (see Verified Ground Truth).
- **NEW/REVIEW — Flask-owns-DynamoDB exception.** The landing JSON store (Flask reading/writing its own DynamoDB table) is NOT a plane-rule violation but IS an undocumented exception to "Flask = MySQL" and introduces a third tenancy shape (slug-partition, app-level isolation). Capture it in steering or an ADR so it does not read as drift.
- **RECONCILE with `jabaki-hosting-migration-to-nonprofit`** (D7) — any registry/KVS/bucket change must land in/with that backlog's topology, not fork it. If the hosting backlog gains a `tasks.md`, the page-registry prerequisites belong there.

Each decision below (D1–D7) is tagged with whether it needs a NEW ADR or a REVIEW of an existing one.

## Problem

1. The member application form must be publicly servable at a per-tenant address (`xxx.jabaki.nl`), with a tenant able to CNAME their own domain onto it WITHOUT the URL being overwritten (no redirect).
2. "Max 1 landing page per tenant" is too limiting. Can one slug/pages infrastructure serve BOTH landing pages and the application form?
3. What must the SAM-plane application form DELIVER to that shared infrastructure to become public, without violating the Flask↔SAM no-cross-plane-runtime-communication rule?

## Verified ground truth (from code)

- **The 1:1 limit is structural in three layers:** `tenant_slugs.administration UNIQUE` (one slug/tenant); the landing DynamoDB store keyed `PK=TENANT#{slug}, SK=LANDING#HOME` (constant SK → one page); S3/asset/invalidation all keyed on slug.
- **The serving layer is already shared + generic:** one `*.jabaki.nl` CloudFront distribution + a stateless viewer-request url-rewrite function (slug-path routing, bucket-agnostic) + the `myadmin-public-pages` bucket.
- **Custom-domain / CNAME-without-redirect already works** via `tenant_custom_domains` (keyed by `administration` AND `slug`, `domain_type ∈ {custom,jabaki}`, ACM tracking) + `CloudFrontDomainService`: on ACM ISSUED it adds the domain as a CloudFront alias and writes a `domain_mapping` KVS entry (host→slug), which the edge rewrite reads to resolve a custom host to its slug.
- **`tenant_custom_domains` is already per-slug** → the custom-domain layer is closer to "per page" than `tenant_slugs`. The real 1:1 bottleneck is only `tenant_slugs.administration UNIQUE` + the constant `SK=LANDING#HOME`.
- **Flask-owns-DynamoDB (landing JSON store) is NOT a rule violation** — the rule forbids a SAM module persisting via Flask/MySQL and a Lambda calling MySQL. Flask using its own DynamoDB table for its own feature is neither. (Caveat: third tenancy shape + undocumented exception → see ADR actions.)
- **A shared DynamoDB table between planes IS forbidden** (rule 5a: "not even to reuse an existing table" + tenancy-model mixing). Only shared surface allowed = dumb, stateless infra (S3 bucket + stateless CloudFront function/KVS).
- **h-dcn public-page pattern (confirmed):** public no-auth Lambda — API has NO default authorizer, public functions have NO `Auth` block, handler skips `extract_user_credentials`, response via an explicit public-field whitelist, publication-gate baked into the resolve filter. BUT h-dcn resolves slug via a FULL-TABLE SCAN (Events has no GSI) — an anti-pattern to avoid, not copy. h-dcn is single-tenant/single-domain → no host→slug/CNAME machinery (myAdmin-only).
- **`jabaki-hosting-migration-to-nonprofit`** owns the hosting topology (S3 + `*.jabaki.nl` CloudFront + ACM + rewrite fn + the two KVS + backend IAM), moving it personal→nonprofit. Design-only, no `tasks.md`, owner-run (high blast radius: live DNS, 7 tenants, production email). The parked `*.{tenant-id}.jabaki.nl` host model lives here.
- **mysaas** = a preliminary prototype that led to the current `sam/` plane in myAdmin. BUILD TARGET = myAdmin (this workspace). h-dcn = pattern source only.

## Decisions to lock (D1–D7)

### D1 — Serving model: Model 1 (slug-addressed artifact under `*.jabaki.nl`), NOT the h-dcn single-domain SPA model

Forced by the `xxx.jabaki.nl` + CNAME-without-redirect + multi-tenant requirement. **Recommended: YES.** ADR: covered by the NEW public-pages ADR.

### D2 — Addressing unit: generalize tenant→page (lift the 1:1 limit) [LOAD-BEARING]

DECISION: lift the ban. No limits in the code.

Make a PAGE the unit (slug + optional custom domains + published artifact + owner), N per tenant: relax `tenant_slugs.administration UNIQUE` → a page registry; landing store `SK=LANDING#HOME` → `SK=PAGE#{id}`; generalize `tenant_custom_domains` "tenant's one landing domain" → "a domain mapped to a page slug" (already slug-keyed). **Recommended: YES.** Alternative (two parallel 1:1 systems sharing only the bucket, per spec 12) is less work but does NOT lift the limit and leaves two silos. ADR: **NEW ADR required.**

### D3 — Hand-off boundary: dumb artifact in the shared bucket (Option A), never a shared DB record

Each plane publishes its OWN rendered artifact into the shared bucket + claims its slug/domain in the shared registry/KVS. SAM renders the form's `{slug}/index.html` (+ `form.json`); Flask renders landing HTML. No cross-plane DB read/write, no cross-plane trigger over a shared table. **Recommended: YES.** Rejected: SAM writing a JSON record into Flask's landing DynamoDB table (violates rule 5a; tenancy collision; two writers; cross-plane schema contract). ADR: covered by the NEW public-pages ADR.

### D4 — Maximize Flask reuse via a shared RENDERING LIBRARY (Option A2a), not a shared runtime

Extract the generic HTML shell + CSS/SEO/footer (`generate_index_html` scaffolding + `LandingPageStyles`) into a plane-neutral, dependency-free module both planes import. Share the mechanism, not the store or a runtime call. Alternative A1 (SAM emits Flask's section/block JSON for Flask to render) reintroduces a cross-plane schema contract + Flask-side trigger — rejected unless a single renderer is a hard requirement. **Recommended: A2a**, pending a check that the shell/`LandingPageStyles` extract cleanly (no hidden Flask deps). ADR: minor; note in the public-pages ADR.

### D5 — Data path: h-dcn-style public no-auth SAM `GET {slug}` (schema) + `POST {slug}` (submit)

No API default authorizer, no `Auth` on public functions, handler does no credential extraction, response via explicit public-field whitelist, publication-gate in the resolve. Published `{slug}/index.html` is a thin shell that fetches the schema and renders with the existing `ApplicationFormRenderer`. **Recommended: YES.** (Already aligns with spec 12 R7.) ADR: covered by existing spec 12 + the public-pages ADR.

### D6 — Slug→tenant resolution: GSI-on-slug OR the S3 `_slugs/{slug}` marker — NEVER a scan

Spec 12 chose the S3 `_slugs/{slug}` marker (keeps the `tenant_id`-PK invariant, no DynamoDB change). A slug GSI is the idiomatic house pattern. Pick one, be consistent; both beat h-dcn's scan. **Recommended: stay with spec 12's S3 marker** unless the page registry makes a GSI more natural. ADR: none (design-level, record in spec 12 / the design doc).

### D7 — Reconcile with `jabaki-hosting-migration-to-nonprofit`; do not fork it [LOAD-BEARING]

DECISION: YES NO Fork but jabaki-hosting-migration-to-nonprofit

The page-registry generalization + any KVS/bucket change land in/with that backlog's topology, not a parallel store. Live-publish + IAM gated on the owner-run migration; account-agnostic work (registry model, SAM public GET/POST, renderer extract) proceeds in parallel. **Recommended: YES.** ADR: **REVIEW** — reconcile scope with the hosting backlog; amend that spec rather than fork.

## Dependencies / open items

- Confirm `LandingPageStyles`/shell extracts cleanly for D4.
- Confirm the SAM submit handler's IAM already covers its target table write (h-dcn flagged this).
- Logo convergence (`tenant-branding-logo-single-source`) rides along separately.
- Spec 13 R3 dropdown color = last cosmetic step, applied in the one renderer AFTER serving settles.

## Non-goals

- No shared cross-plane database. No Flask publishing the SAM form. No reviving Flask config authoring. No `*.{tenant-id}.jabaki.nl` host reshape (parked in the hosting backlog).

## Immediate next step

Lock **D2** (page-registry vs two parallel systems) and **D7** (reconcile with hosting backlog) — everything else hangs off them. Open/review the ADRs listed above. Then expand this brief into a full design + task plan.
