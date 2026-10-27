# Design Document

## Application Form Serving Redesign — Design

- Status: **Draft** (design phase — review before tasks are executed).
- Follows `requirements.md` (R1–R9) and spec 11 `redesign.md` (decisions A/B/C + the 1=a/2=a
  resolution). Supersedes the spec 11 parts named in "Relationship to spec 11"; reuses the rest.
- Planes: **frontend** (field-modal authoring, in-browser preview, slug display/embed) + **SAM**
  (slug on `config#fields`, data-backed slug resolver, publish action, bucket/CloudFront IAM) +
  a **Terraform** IAM change (manual, plan-first, steering 43). **No Flask runtime involvement.**

## Overview

Three agreed redesign decisions, each retiring a specific spec-11 bug class, plus the slug+publish
resolution:

- **A — authoring = field-modal** (reuse `MembersFieldModal`), retiring the bespoke toggle-list/panel.
- **B — frontend reasons in groups+fields**, server owns storage placement; reuse `upsertField`.
- **C — serving = landing-page model**: in-browser preview (retire the server preview endpoint),
  publish a slug-addressed static artifact, served by the existing `*.jabaki.nl` CloudFront path.
- **1=a** form slug is data on `config#fields`; **2=a** SAM publishes the static artifact.

The non-negotiable constraint shaping the whole design: **no runtime SAM↔Flask communication.** The
two planes share only the dumb static bucket + the stateless CloudFront rewrite function.

## Architecture

```mermaid
graph TB
  subgraph Admin["Tenant Admin (browser) — frontend"]
    Builder["Application Form Builder<br/>(group ▸ field surface)"]
    Modal["Field modal (reuse MembersFieldModal)<br/>+ application-form attrs section"]
    Preview["In-browser preview<br/>(ApplicationFormRenderer over working draft)"]
    Builder --> Modal
    Builder --> Preview
  end

  subgraph SAM["SAM Members plane (DynamoDB + Lambda)"]
    CfgWrite["PUT /members/config/fields|mail<br/>(members:admin, R8 hardening)"]
    Cfg["config#fields / config#mail<br/>(tenant_id + sk)  ← slug stored here [1=a]"]
    Publish["POST /members/application-form/publish<br/>(members:admin, readiness-gated) [2=a]"]
    Resolve["get_public_field_config<br/>(single filter authority)"]
    SubmitEdge["public_app.py submit edge<br/>data-backed TenantSlugReader"]
    CfgWrite --> Cfg
    Publish --> Resolve --> Cfg
    SubmitEdge --> Cfg
  end

  subgraph Shared["Shared dumb infra (no plane calls the other)"]
    S3["S3 myadmin-public-pages-{env}/{slug}/<br/>index.html [+ form.json]"]
    CF["CloudFront *.jabaki.nl<br/>public_pages_url_rewrite (stateless)"]
    CSP["viewer-response application_form_frame_ancestors<br/>+ application_embed_origins KVS"]
  end

  Modal -->|one field_overlay, one save| CfgWrite
  Publish -->|boto3 put_object + invalidate| S3
  Publish -.->|invalidate| CF
  CF --> S3
  CF --> CSP
  Applicant["Applicant (browser)"] -->|GET {slug}.jabaki.nl| CF
  Applicant -->|POST /public/members/{slug}/applications| SubmitEdge

  Flask["Flask plane (landing pages)"]
  Flask -. "ONLY shares the bucket + CF function — NO runtime call" .- Shared
```

**Request flows:**
- **Authoring:** builder → field modal (reuse `upsertField`) → one `PUT /members/config/fields`.
- **Preview:** entirely in-browser; the working draft is filtered client-side (parity-pinned to
  `get_public_field_config`) and rendered by `ApplicationFormRenderer`. No server call.
- **Publish:** builder → `POST /members/application-form/publish` → SAM renders via
  `get_public_field_config` → boto3 writes `{slug}/index.html` to the public bucket → CloudFront
  invalidation. Flask not involved.
- **Serve:** `{slug}.jabaki.nl` → CloudFront → `public_pages_url_rewrite` (string → `/{slug}/index.html`)
  → OAC → S3. No request-time tenant lookup. Viewer-response sets CSP `frame-ancestors` from the KVS.
- **Submit:** `POST /public/members/{slug}/applications` → `public_app.py` → data-backed slug resolver
  reads `config#fields` → `tenant_id` → `create_application`. SAM-only.

## Components and Interfaces

### C1 — Field modal authoring (frontend, redesign A / R1)
- Reuse `MembersFieldModal`'s engine (`buildField`, `resolveWriteTarget`, `upsertField`). Add an
  **application-form attributes section** rendered only when a form is in scope.
- The enum-subset picker SOURCE adapts to field kind: reference → live catalog (e.g. membership_type);
  scope → the scope dimension values; enum/choices → the field's own options. It renders ONLY for
  choice-bearing fields (R1.3). Interface: reads the resolved field list (`GET /members/field-config`),
  writes onto the single working `field_overlay`, commits via `saveMembersParameter('field_overlay', …)`
  → `PUT /members/config/fields`.
- Retire `ApplicationFieldList` toggle-list + the buried attributes panel (spec 11).

### C2 — In-browser preview (frontend, redesign C / R3)
- `ApplicationFormRenderer` (spec 10) fed by the WORKING draft in memory. A small pure client filter
  reproduces `get_public_field_config`'s applicant-facing selection (visible fields, subset, required,
  format, consent notice). Interface: pure function `draft → applicant schema`, parity-pinned by a test
  fixture against the server filter (R3.2). No `POST /members/application-preview`, no debounce.

### C3 — Slug on `config#fields` (SAM, 1=a / R4)
- Add `slug: string` (+ publish-state metadata, e.g. `published_at`, `published_version`) to the
  `config#fields` row. Authored via the existing `members:admin` `PUT /members/config/fields` write
  (`ConfigWriteService`), validated for format + uniqueness (see §Uniqueness / OQ4).
- `MembersProjectionReader` gains a forward reader for the slug (tenant→slug via the normal
  `tenant_id`-pinned `get_item`). The REVERSE slug→tenant lookup for C5 does NOT live on this
  tenant-partitioned table as a slug-keyed item (that breaks the `tenant_id`-PK invariant — verified);
  its mechanism is OQ4 (§Uniqueness).

### C4 — Publish action (SAM, 2=a / R5)
- **Mechanism RESOLVED (OQ1, option 1, 2026-10-23): an EXPLICIT publish route**, not save-triggered.
  Editing/saving the draft (`PUT /members/config/fields|mail`) NEVER republishes the live form; the
  live artifact changes ONLY on a deliberate publish action (matches the landing-page "Publish" button
  lifecycle; deterministic; cleanly readiness-gated; the in-browser preview (C2) covers "see before
  commit" so there is no need to publish just to check). Rejected: save-triggered auto-publish — it
  would push half-finished edits live, is harder to readiness-gate, and couples an S3 write +
  CloudFront invalidation to every config save.
- New `members:admin` route `POST /members/application-form/publish` (self_service=False) in
  `routes.py` + `_dispatch`. Handler: load `config#fields`/`config#mail`, enforce readiness
  (slug + certified sender + ≥1 on-form field), render via `get_public_field_config` → a self-contained,
  responsive HTML (reusing the renderer's output contract + the `postMessage` resize script), write
  `{slug}/index.html` [+ `{slug}/form.json`] to `myadmin-public-pages-{env}` via boto3, invalidate the
  `*.jabaki.nl` distribution for `/{slug}*`. Replaces the prior version. Interface env (mirrors landing):
  `LANDING_PAGES_BUCKET`, `CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID`. **No Flask call.**

### C5 — Data-backed slug resolver (SAM, R7)
- Replace `EnvTenantSlugReader` (`PUBLIC_TENANT_SLUG_MAP`) with `ConfigFieldsSlugReader` resolving
  slug → `tenant_id` from the form slug (C3/C4-stored), behind the EXISTING `TenantSlugReader` Protocol
  so `TenantDirectory` + the edge are untouched. Verify-before-trust: unknown slug → `None` →
  non-probeable 404.
- VERIFIED (2026-10-23): the `TenantSlugReader` Protocol exists in
  `sam/members/domain/tenant_directory.py`; `EnvTenantSlugReader.resolve_slug` satisfies it by
  duck-typing, and that file's docstring states swapping the backing store is a change localized to it —
  so the swap does not ripple into the resolver or the edge. The "localized swap" claim is confirmed.
- The reverse lookup the reader performs depends on OQ4's mechanism (GSI / directory artifact / bucket
  marker) — see §Uniqueness / D6.

### C6 — Shared serving infra + SAM IAM (Terraform, R6)
- Reuse `aws_cloudfront_distribution.public_pages` + `public_pages_url_rewrite` + the viewer-response
  `application_form_frame_ancestors` + `application_embed_origins` KVS — all already in
  `infrastructure/landing-pages.tf` / `application-form.tf`. NEW: an IAM policy granting the SAM publish
  principal `s3:PutObject`/`s3:DeleteObject` on the public-pages bucket `/*` and
  `cloudfront:CreateInvalidation` on the distribution — a least-privilege mirror of the Flask Railway
  grant. **Same-account in nonprofit** (migration-first, option a), so NO cross-account bucket policy or
  cross-account invalidation role is built. Applied manually, plan-first, same release window
  (steering 43). **Gated on the hosting migration having cut over** (prerequisite).

## Data Models

### `config#fields` (extended)
```
{ functional_groups, fields, overrides,            # existing (unchanged)
  slug: "<form-slug>"|null,                         # NEW [1=a] — the form's public slug
  published_at: "<iso8601>"|null,                   # NEW — last successful publish
  published_version: <int>|null }                   # NEW — monotonically increments per publish
```
Validation on write (R4.2/R4.3): slug format = landing `SLUG_PATTERN` rules; slug unique among
application-form slugs (and disjoint from in-use landing-host slugs — §Uniqueness); a NAME ≠ tenant is
allowed.

### Published static artifact (S3)
```
myadmin-public-pages-{env}/
  <form-slug>/index.html     # self-contained, responsive, postMessage-resize, renderer output
  <form-slug>/form.json      # applicant-facing schema + consent notice (optional, for the SPA/renderer)
```
Served by the existing CloudFront path; same per-slug prefix convention as landing pages, so the rewrite
function is UNCHANGED (routes purely on slug path, bucket-agnostic).

### Slug reverse lookup (slug → tenant) — RESOLVED (OQ4): `_slugs/{slug}` bucket marker
The submit edge maps a public slug to its tenant via a control-plane marker object in the shared
public-pages bucket:
- **Write (on slug claim):** conditional `put_object` `_slugs/{slug}` (if-none-match) with the owning
  `tenant_id` in the body/metadata → within-tenant uniqueness + the mapping, atomically.
- **Read (submit edge):** `get_object` `_slugs/{slug}` → `tenant_id`, scan-free; miss → `None` →
  non-probeable 404 (verify-before-trust preserved).
- **Reserved prefix:** `_slugs/` is reserved — a real page slug may never be `_slugs` or begin `_slugs/`,
  and marker objects live OUTSIDE any served `{slug}/` prefix (control plane, never CloudFront-served).
Chosen over a GSI-on-slug or a separate directory table because it needs NO DynamoDB change (keeps the
`tenant_id`-PK governance-projection table's structural-isolation invariant intact — `template.yaml`),
reuses infra SAM already writes to for publish, and is the lowest-investment option for a lookup the
parked `*.{tenant-id}.jabaki.nl` host model will remove entirely. The form-vs-landing publish-time S3
`{slug}/landing.json` backstop is independent and stands.

## Key Decisions

### D1 — Slug lives on `config#fields`, NOT `tenant_slugs` (1=a)
`tenant_slugs.administration` is `UNIQUE` (hard DB constraint, `create_tenant_slugs_table.sql`), so a
tenant cannot own a second slug there, and `TenantSlugService.set_slug` would treat a second slug as a
*rename* of the landing slug. Storing the form slug on the SAM-owned `config#fields` record keeps the
form's addressing on the plane that owns its data and sidesteps the 1:1 limit. The slug STRING is free to
differ from the tenant NAME (independent columns/attributes).

### D2 — SAM publishes; Flask is never in the loop (2=a)
The plane that owns the config publishes it. Reuse the landing PATTERN (render → `put_object` → CloudFront
invalidation) but on the SAM plane. Rejected alternative: Flask publishes (mirrors landing exactly) — it
would force Flask to read the SAM-owned form config, i.e. a cross-plane read, violating the no-comms
constraint. The only shared surface is the dumb bucket + stateless CloudFront function, which is
infrastructure, not communication.

**Account (option a, migration-first):** the jabaki hosting migration moves the bucket/distribution to
nonprofit (`506221081911`) BEFORE this publish path is wired. Since SAM runs in nonprofit, publish IAM is
then **same-account** — the simplest, least-privilege end-state, with no cross-account grant ever built.
Rejected alternative: build spec 12 now against the personal bucket with a cross-account grant and
migrate later — that is throwaway IAM and more moving parts during the migration. The account-agnostic
parts of this spec (C1/C2/C3/C5) do not depend on the migration and proceed in parallel; only C4's live
publish + C6's IAM are gated on the cutover.

### D3 — Serving reuses the one `*.jabaki.nl` distribution + stateless rewrite (R6)
No new distribution/cert/per-tenant infra. The function maps `{slug}.jabaki.nl` → `/{slug}/index.html` by
string ops with no request-time lookup; the moment SAM writes `{slug}/index.html`, the host serves it.
CSP `frame-ancestors` for the form host comes from the existing viewer-response function + embed-origins
KVS (spec 11 E4b); a host without an entry denies framing (`'none'`).

### D4 — Preview is in-browser; the server preview endpoint is deleted (redesign C / R3)
Retire `POST /members/application-preview` + its debounce + caller. Reproduce its applicant-facing filter
in the browser and PIN parity to `get_public_field_config` with a fixture test, so deleting the endpoint
does not reintroduce drift. (The spec 11 `findings.md` observed the endpoint returning empty `fields: []`
for working drafts — the in-browser path removes that whole fragile round-trip.)

### D5 — Submit resolves slug from data behind the existing protocol (R7)
Swap `EnvTenantSlugReader` → a `ConfigFieldsSlugReader` implementing the SAME `TenantSlugReader` protocol,
so `TenantDirectory`/`_dispatch_public`/the edge are untouched (localized change, `tenant_slug_reader.py`).
Then remove `PUBLIC_TENANT_SLUG_MAP` from `template.yaml`/`samconfig.toml` AFTER the swap — swap first,
delete second, so the edge never breaks mid-change. This also removes the dependency on the CI
`--parameter-overrides` footgun that blanked the param (1a).

### D6 — Uniqueness + reverse lookup — RESOLVED (OQ2, 2026-10-23; verified against the live bucket)

**Two facts settled it (verified live on the personal bucket `myadmin-public-pages-production`, the
current hosting account):**

1. **The `*.jabaki.nl` host is NOT stored anywhere** — the CloudFront `public_pages_url_rewrite` function
   is pure string manipulation (`host.replace('.jabaki.nl','')` → `/{slug}/index.html`); there is no
   stored list of jabaki URLs to consult. The only CloudFront KVS (`domain_mapping`) holds CUSTOM apex
   domains only (e.g. `www.acme.nl`), never `*.jabaki.nl`. And the Flask landing slug is `{slug}.jabaki.nl`
   only when the tenant's `tenant_slugs.jabaki_enabled` flag is set (else it serves at `/p/{slug}`). So the
   real shared namespace is NOT the subdomain — it is **the `{slug}/` prefix (specifically the single
   `{slug}/index.html` object) in the one shared S3 bucket**, which both planes would write.
2. **"Folder exists" is NOT a reliable collision signal.** The 7 live slugs come in TWO shapes:
   - 4 (`mytest`, `peter`, `thecategorystudio`, `vandenheuvelhoveniers`) have the CDN-served pair at the
     slug root: `{slug}/index.html` + `{slug}/landing.json`.
   - 3 (`GoodwinSolutions`, `PeterPrive`, `kimgeers`) have NO root `index.html` — only tracked assets under
     `{slug}/landing-pages/ast_<id>_{index.html,landing.json}` (the `MediaAssetService` write without the
     root CDN copy). `vandenheuvelhoveniers` has BOTH shapes.
   A guard that refused on "any object under `{slug}/`" would false-positive on the asset-tracking subfolder.

**Resolution — uniqueness is TENANT-scoped; no global registry is built:**
- **Uniqueness is a per-tenant concern, not a platform-wide namespace the platform polices (OQ2).** The
  platform enforces only within-tenant uniqueness (a tenant can't have two forms with the same slug;
  today = the tenant owns its one form slug). Cross-tenant / cross-function global uniqueness is a
  BUSINESS matter, made structural by the parked `*.{tenant-id}.jabaki.nl` model (see "Parked future
  addressing" below). So NO global slug registry, NO GSI-on-slug, NO shared cross-plane arbiter is built —
  those were over-engineering a problem we have reframed out of the platform's scope.
- **Reverse lookup (slug → `tenant_id`) — RESOLVED (OQ4): a `_slugs/{slug}` marker object in the shared
  bucket** (conditional `put_object` to claim + for within-tenant uniqueness; `get_object` to resolve on
  the submit edge; `_slugs/` reserved, outside any served `{slug}/` prefix). Keeps the lookup off the
  `tenant_id`-PK governance-projection table (STRUCTURAL-ONLY isolation — repo pins `tenant_id`, no
  `.scan()`, `LeadingKeys` future-only, `template.yaml`), needs NO DynamoDB change, reuses publish infra,
  and is disposable under the parked host model. See §Reverse-lookup for the full contract.
- **Parked future addressing (`*.{tenant-id}.jabaki.nl`).** The target model puts the globally-unique
  tenant-id in the HOST (`apply.h-dcn.jabaki.nl`), giving each tenant its own sub-namespace, making
  uniqueness structurally per-tenant and letting the submit edge parse the tenant from the hostname (no
  lookup at all). DEFERRED — needs a two-level wildcard cert + S3-layout/rewrite reshape owned by
  `jabaki-hosting-migration-to-nonprofit`. This spec adopts the PRINCIPLE (uniqueness is a tenant
  concern) now, on the existing flat `*.jabaki.nl` path, not the host structure.
- **Form-vs-landing collision (defensive backstop only, NOT a uniqueness mechanism):** a **publish-time
  S3 guard keyed on the ROOT marker
  `{slug}/landing.json`** (the reliable landing signal — present on every genuinely CDN-served landing,
  absent from a form's prefix). SAM refuses to publish a form to `{slug}/` if a root `landing.json` it did
  not author is present, so a form can never overwrite a landing page's `index.html`. The `landing-pages/`
  asset subfolder is explicitly IGNORED by the guard (it is tracking noise, not a serving artifact).
- The application form writes a DISTINGUISHABLE marker — `{slug}/form.json` + an owner tag — so the guard
  can tell "a form lives here (mine, republish is fine)" from "a landing lives here (refuse)".
- Naming convention (not a uniqueness mechanism): form slugs reasonably carry a short distinguishing
  marker (e.g. `hdcn-application-form`) so a tenant's form and landing addresses read as related and are
  unlikely to collide in the flat namespace today. This is hygiene + the backstop above; it is NOT how
  uniqueness is guaranteed (that is tenant-scoped, OQ2) and it is superseded by the parked
  `*.{tenant-id}.jabaki.nl` host model, which makes the separation structural.

### D7 — CI `--parameter-overrides` footgun (R7.4; 1a root cause)
Making the slug data-resolved removes the runtime dependency on `PublicTenantSlugMap`. Independently, the
deploy workflow's bare `--parameter-overrides OpenRouterApiKey=…` REPLACES the whole samconfig param set.
This spec closes the application-form blast radius (no longer depends on that param) and NOTES the latent
risk for any OTHER samconfig param; the general workflow fix (merge, not replace — e.g. pass ALL params or
use a param file) is recommended as a small CI follow-up (steering 43), flagged not silently carried.

### D8 — Rename (R4.5; §Rename)
A form-slug rename mirrors the applicable landing `rename_slug` steps ON THE SAM PLANE: update the
`config#fields` slug (conditional-put for uniqueness) + the slug reverse-lookup index (whatever OQ4
settles on), delete the old `{old-slug}/` S3 artifact, publish under the new slug, invalidate CloudFront
for both. Non-atomic best-effort with warnings (like landing), but the `config#fields` update is the
authoritative step.

## Error Handling
- Authoring/publish errors use the standard SAM envelope (steering 37) with a stable `code` + caller-safe
  message; never leak config/sender internals (spec 11 R8.3 / NFR).
- Submit stays non-probeable: unknown/forged slug → uniform 404 (`PublicTenantNotFound`), logged
  server-side only.
- Publish is readiness-gated: missing slug/sender/field → a clear `members:admin`-facing error, NOT a
  broken live artifact (R5.4 / spec 11 R6 show-don't-block).

## Testing Strategy
- **Frontend** (`33-frontend-testing`): field-modal writes (subset only on choice fields; no-relax; known
  tokens); one-object/one-save; in-browser preview parity + unsaved-edit reflection; slug display + link;
  external embed snippet + `postMessage` resize in a Google Sites iframe; axe. Fixtures MUST use the bare
  `key` + `group` server shape (R2.3).
- **SAM** (`34-backend-testing`, `sam/tests/`): slug store/validate/uniqueness on `config#fields`;
  `ConfigFieldsSlugReader` resolves known / 404s unknown (verify-before-trust); publish renders via
  `get_public_field_config` (filter parity), writes expected S3 keys, invalidates CloudFront, is
  `members:admin` + readiness gated, replaces prior version; `POST /members/application-preview` removed
  and unreferenced. Reuse the spec 11 real-data fixture (`config#fields` for `h-dcn`) rather than a
  hand-built one.
- **Terraform:** the SAM IAM change is reviewed in the same PR; apply is manual, plan-first; confirm the
  plan only ADDS the IAM and does NOT force-replace the `public_pages` distribution / bucket / KVS
  (a replacement there is a STOP, steering 43).

## Migration / Rollout
0. **PREREQUISITE (option a):** execute `jabaki-hosting-migration-to-nonprofit` so the public-pages
   bucket + `*.jabaki.nl` distribution + KVS live in nonprofit (`506221081911`). The account-agnostic
   steps (1, 3, 4 below) MAY proceed in parallel with the migration; the publish steps (2, 5) are gated
   on the cutover being verified.
1. Land the SAM slug-on-`config#fields` + `ConfigFieldsSlugReader` (swap behind the protocol) + the
   publish route (code + tests; live-write path dormant until step 0 lands), on `test`.
2. ⟂(needs step 0) Apply the SAM bucket/CloudFront IAM Terraform (plan-first, manual) in nonprofit,
   same-account, same window as the publish wiring.
3. Land the frontend field-modal + in-browser preview + slug display; delete the server preview endpoint
   and its caller in the SAME change. (Account-agnostic — parallel to step 0.)
4. Remove `PUBLIC_TENANT_SLUG_MAP` from `template.yaml`/`samconfig.toml` after the resolver swap is live.
   (Account-agnostic.)
5. ⟂(needs step 0+2) Verify end-to-end on live TEST (publish `hdcn-application-form`, load
   `hdcn-application-form.jabaki.nl`, submit) — exercised live, not just units (steering 43 runbook).
6. Promote `test → main` via one reviewed PR (a merge to `main` is a production deploy).

## Open Questions (carried from requirements)
1. ~~Publish mechanism~~ **RESOLVED (OQ1, option 1, 2026-10-23): an explicit `POST …/publish` route**,
   not save-triggered. Save ≠ publish; the live form changes only on a deliberate, readiness-gated
   publish. → §C4.
2. **Slug uniqueness SCOPE — RESOLVED (OQ2, 2026-10-23):** uniqueness is TENANT-scoped, not a
   platform-wide global namespace. Platform enforces within-tenant only; cross-tenant/cross-function is a
   business matter, made structural by the parked `*.{tenant-id}.jabaki.nl` host model. No global
   registry / GSI / shared arbiter. The publish-time root `{slug}/landing.json` check remains only as a
   defensive backstop against clobbering a landing page. → D6.
3. ~~Account reconciliation~~ **RESOLVED (option a, 2026-10-23):** hosting migrates to nonprofit FIRST;
   SAM publish IAM + target are same-account nonprofit. The migration is a prerequisite of C4/C6 only.
4. ~~Slug→`tenant_id` reverse-lookup MECHANISM~~ **RESOLVED (OQ4, 2026-10-23): a `_slugs/{slug}` marker
   object in the shared bucket** (conditional `put_object` to claim + for within-tenant uniqueness;
   `get_object` to resolve; `_slugs/` reserved, outside served prefixes). No DynamoDB change; keeps the
   `tenant_id`-PK invariant; disposable under the parked host model. → D6 / §Reverse-lookup.
