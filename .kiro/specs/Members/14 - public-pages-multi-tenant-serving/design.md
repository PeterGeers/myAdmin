# Design — 14. Public-Pages Multi-Tenant Serving (page-as-unit)

- Status: **Draft** (design phase — review before tasks). Implements `requirements.md` (R1–R7),
  which encode the locked decisions D1–D7 from `13 - .../next-steps.md`.
- **The four design open questions (OQ1–OQ4) are resolved below as PROPOSALS for review** — each
  marked `PROPOSAL`. Change any before tasks are executed.
- **Prerequisite:** `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit` (now has a
  `tasks.md`). Its completion gates ONLY this spec's *live-publish + nonprofit publish IAM* tasks.
  All account-agnostic work proceeds in parallel.

## Overview

Generalize public-page addressing from **tenant** to **page** so a tenant can own N public pages
(landing, application-form, future kinds), each at `{slug}.jabaki.nl` with optional per-page
custom domains (CNAME, URL preserved). Both planes publish into the SAME dumb shared infra (S3
bucket + stateless CloudFront rewrite + the two KVS); neither reads the other's datastore. The SAM
application form becomes one page *producer* among several.

```mermaid
graph TB
  subgraph Flask["Flask plane (landing pages)"]
    LReg["tenant_pages (MySQL) — page registry"]
    LDyn["myadmin-landing-pages (DynamoDB)<br/>SK=PAGE#{page_id}"]
    LPub["LandingPagePublishService<br/>render + put_object + invalidate"]
  end
  subgraph SAM["SAM plane (application form)"]
    SCfg["config#fields (DynamoDB)<br/>slug + publish-state"]
    SPub["publish route<br/>render + put_object + invalidate"]
    SPubGet["public GET {slug} (schema)"]
    SPost["public POST {slug} (submit)"]
  end
  subgraph SharedLib["Shared rendering LIBRARY (imported, not called)"]
    Shell["page_shell: render_page(head, body, css)"]
    Styles["LandingPageStyles (plane-neutral)"]
  end
  subgraph Dumb["Shared DUMB infra (nonprofit after migration)"]
    S3["S3 myadmin-public-pages-{env}<br/>{slug}/index.html [+ data.json]<br/>_slugs/{slug} marker"]
    CF["*.jabaki.nl CloudFront + url-rewrite fn"]
    KVS1["domain_mapping KVS (host→slug)"]
    KVS2["application_embed_origins KVS"]
  end
  LPub --> Shell
  SPub --> Shell
  Shell --> Styles
  LPub -->|put_object + invalidate| S3
  SPub -->|put_object + invalidate + claim slug| S3
  LPub -.->|invalidate| CF
  SPub -.->|invalidate| CF
  CF --> S3
  CF --> KVS1
  CF --> KVS2
  Applicant -->|GET {slug}.jabaki.nl| CF
  Applicant -->|GET/POST public API| SPubGet
  SPost --> SCfg
  LReg -. owns .- LDyn
```

## Resolved open questions (PROPOSALS)

> **Registry scope (review 2026-10-31):** `tenant_pages` below is the **Flask LANDING-page
> registry only**. SAM application-form pages are registered on the SAM-owned `config#fields` row
> (spec 12), NOT in `tenant_pages`. There is no shared cross-plane registry table. The shared slug
> NAMESPACE is the `_slugs/{slug}` marker (OQ3). "Page is the unit" is realized per plane.

### OQ1 — Page-registry MySQL shape → **PROPOSAL: a NEW `tenant_pages` table** (Flask landing only; do not overload `tenant_slugs`)

A new table owns page identity; `tenant_slugs` is migrated into it and then retired (or kept as a
read view for back-compat during migration).

```sql
CREATE TABLE tenant_pages (
  page_id        CHAR(26) PRIMARY KEY,              -- ULID/UUID, stable page identity
  administration VARCHAR(50) NOT NULL,              -- tenant (steering 31: own column + index)
  kind           ENUM('landing','application_form') NOT NULL,
  slug           VARCHAR(100) NOT NULL UNIQUE,      -- globally unique (served path + host)
  jabaki_enabled BOOLEAN DEFAULT FALSE,
  published_at   TIMESTAMP NULL,
  created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_administration (administration),
  INDEX idx_admin_kind (administration, kind),
  INDEX idx_slug (slug),
  FOREIGN KEY (administration) REFERENCES tenants(administration)
);
```

- **No `administration UNIQUE`** → N pages per tenant (R1.2). `slug` stays globally UNIQUE.
- A tenant's landing page migrates to a `tenant_pages` row (`kind='landing'`, its existing slug).
- Rationale over "relax `tenant_slugs` in place": `tenant_slugs` is 1 row/tenant by its whole
  shape and every `get_slug(tenant)` caller assumes it; a clean `tenant_pages` + a bounded
  migration is less error-prone than mutating a table the publish/rename/domain code all read as
  1:1. `tenant_custom_domains` already carries `slug`, so it points at a page by slug unchanged.
- **Compat:** keep `tenant_slugs` as a VIEW (`SELECT administration, slug … WHERE kind='landing'`)
  during migration so un-migrated callers keep working; cut callers over, then drop the view.

### OQ1b — Tenant public prefix (R2): one tenant identity across all planes

A tenant has ONE short public prefix (`SLUG_PATTERN`, ~3–20 chars, globally unique), its single
public identity across every plane/app. Storage + projection:

- **Authored in MySQL** as a column on the tenant record (the tenant system-of-record, steering
  20) — e.g. `tenants.public_prefix VARCHAR(20) UNIQUE`. Chosen once (onboarding); a default MAY
  be suggested from the administration name but the tenant can set a short brandable value
  (`vandenheuvelhoveniers` → `vdh`).
- **Projected READ-ONLY to SAM** as an ADDITIVE attribute on the ALREADY-PROJECTED `tenant` row
  (`SK="tenant"`, `services/projection_schema.py`) — NOT a new table, NOT a new sync. The sync's
  item builder adds `public_prefix` to the `tenant` record; SAM reads it from its own projected row
  to validate a form slug's prefix WITHOUT calling Flask (plane rule intact, steering 20/35).
- **Validation (both planes):** a new page slug must be `{prefix}` or `{prefix}-{suffix}` and start
  with the AUTHENTICATED tenant's prefix; cannot borrow another tenant's prefix. Live slugs
  grandfathered (incl. uppercase legacy that fails new `SLUG_PATTERN`).
- **Dependency flag:** confirm the projection sync (`s3-claims-and-projection` builder) picks up the
  new `tenant` attribute — small additive change to an existing one-directional sync, called out in
  tasks. Uniqueness of the prefix itself is a MySQL `UNIQUE` column (tenant-record authoring is
  Flask-side), so no cross-plane claim is needed for the prefix (only for page SLUGS, OQ3).

### OQ2 — DynamoDB per-page SK → **PROPOSAL: `SK=PAGE#{page_id}`** (kind as an attribute)

`myadmin-landing-pages` moves from `SK=LANDING#HOME` (constant → 1 page) to `SK=PAGE#{page_id}`;
versions become `SK=PAGE#{page_id}#VERSION#{n}`. `kind` is an item attribute. `get_draft`,
`save_draft`, `delete_draft`, `migrate_slug`, `list_versions`, `prune_old_versions` take a
`page_id` instead of assuming the constant SK.

- Rationale over `{kind}#{slug}`: keying on the STABLE `page_id` (not the mutable `slug`) means a
  slug rename does NOT rewrite the DynamoDB PK/SK — it only updates the `tenant_pages.slug` + the
  S3 artifact + KVS, shrinking the rename blast radius. (The design keeps `PK=TENANT#{slug}` today;
  consider moving PK to `administration`/`page_id` as part of the migration — called out as a
  sub-decision in tasks.)
- **Migration:** each existing `LANDING#HOME` item is copied to `PAGE#{new_page_id}` (+ its
  versions), preserving content; verified against the live rows (R1.3/R1.6).

### OQ3 — Slug uniqueness + resolution → **PROPOSAL: the S3 `_slugs/{slug}` marker as the atomic cross-plane gate** (keep spec 12's mechanism)

**Uniqueness (the authoritative gate):** an ATOMIC conditional `put_object _slugs/{slug}` with
`If-None-Match: *`. It succeeds only if the object does not exist; a racing claimer from EITHER
plane gets `412 PreconditionFailed` → `SlugTaken`. The condition IS the check, so there is no
check-then-write race — this is what makes cross-plane uniqueness true without a shared database.

```python
def claim(slug, owner):             # owner = {owner_plane, kind, tenant_id, resource_ref}
    try:
        s3.put_object(Bucket=B, Key=f"_slugs/{slug}",
                      Body=json(owner), IfNoneMatch="*")
    except PreconditionFailed:      # 412
        raise SlugTaken(slug)
```

**Resolution + backing:** the marker BODY (`{owner_plane, kind, tenant_id, resource_ref}`) is the
source of truth for who owns a slug. The submit/schema edge does `get_object _slugs/{slug}` and
decides ownership by READING THE BODY (`owner_plane`/`kind`), NEVER by parsing the slug string.
A Flask-owned slug resolved via the SAM edge → clean non-probeable 404. Scan-free; keeps the SAM
`tenant_id`-PK governance invariant intact (no slug-partitioned item, no GSI backfill).

**Layering:** per-plane `UNIQUE`/validation (Flask `tenant_pages.slug UNIQUE`; SAM config-row
check) is a FAST-FAIL UX check only; idempotent same-owner re-publish allowed (body matches);
rename claims-new-before-releasing-old; publish won't clobber a foreign artifact (owner-tag
backstop).

- **⚠ Verify-before-lock:** confirm S3 `If-None-Match: *` is supported for the target bucket/region
  (it is now broadly GA, but confirm). If not, the sanctioned fallback is a DynamoDB conditional
  `PutItem(attribute_not_exists(pk))` on a dedicated slug-claim table — S3 conditional put preferred
  (no "which account / plane rule" question). This verification is an early task.
- Rationale over a slug GSI: no DynamoDB schema change, no eventual-consistency window, consistent
  with spec 12. (A slug GSI remains the documented fallback if a future need makes the marker
  awkward — noted, not built.)

### OQ4 — Shared rendering library → **PROPOSAL: A2a, extract a plane-neutral `page_shell` + reuse `LandingPageStyles`** (VERIFIED extractable)

Confirmed by reading the code: `LandingPageStyles` imports only `re` + `typing` — **no Flask,
no boto3, no DB** — so it is already a plane-neutral static CSS/HTML-fragment generator and can be
shared as-is. The HTML shell (the `<!DOCTYPE>…SEO/OG/CSS/header/footer` scaffold in
`generate_index_html`) is a pure f-string over a `published_data`-shaped dict; extract it into a
dependency-free `page_shell.render_page(head_meta, body_html, css)` module both planes import.

- Flask's `generate_index_html` is refactored to call `page_shell.render_page` (landing body =
  its sections HTML). SAM calls the same `render_page` (form body = `ApplicationFormRenderer`
  output shell). One shell + one CSS system, maintained once.
- **Sharing is as a LIBRARY (pure functions), never a runtime call or a shared store** (R5.2 /
  steering 35 "share the mechanism, not the store"). Packaging: a small plane-neutral module
  vendored where both planes can import it (e.g. a shared package / `sam/shared`-style vendor) —
  exact packaging decided in tasks.
- If extraction surfaces a hidden coupling at implementation time, fall back to SAM-renders-own-
  shell for v1 and defer the shared shell (R5.1 — noted, not silently dropped).

## Components and Interfaces

### C1 — Page registry (Flask/MySQL) [R1]
`tenant_pages` (OQ1) + a `PageRegistryService` exposing `list_pages(tenant)`,
`get_page(page_id)` / `resolve_slug(slug)→(tenant,page_id,kind)`, `create_page`, `rename_slug`
(per-page), `attach/detach_custom_domain(page_id, domain)`. Generalizes `TenantSlugService`:
`get_slug(tenant)` 1:1 callers become page-scoped. `tenant_custom_domains` rows reference a page
by its `slug` (already its key); the domain lifecycle (ACM → CloudFront alias → `domain_mapping`
KVS) via `CloudFrontDomainService` is unchanged, just per-page.

### C2 — Landing publish (Flask) refactor [R2/R5]
`LandingPagePublishService` keyed by `page_id` (OQ2); renders via the shared `page_shell` (OQ4);
writes `{slug}/index.html` [+ `{slug}/landing.json`] to the shared bucket; invalidates. No
behaviour change for a tenant's existing landing page beyond the registry/SK indirection.

### C3 — SAM application-form producer [R2/R3]
- **Publish** (members:admin, readiness-gated): render the form via `get_public_field_config` +
  shared `page_shell`, `put_object {slug}/index.html` + `{slug}/form.json`, conditional-claim
  `_slugs/{slug}`, invalidate. Same-account (nonprofit) IAM — **gated on the migration**.
- **Public `GET {slug}`** (no auth): resolve slug via `_slugs/{slug}` marker → tenant/form,
  publication-gate (unpublished → non-probeable 404), return the applicant schema through an
  EXPLICIT whitelist (R3.2). No `extract_user_credentials`.
- **Public `POST {slug}`** (no auth): resolve slug AS DATA → `create_application`; token-less,
  non-probeable; Lambda role needs PutItem on the applications table (verify — R3.5).
- API has **no default authorizer**; public functions carry **no `Auth` block** (h-dcn pattern).

### C4 — Shared rendering library [R5]
`page_shell.render_page(head_meta, body_html, css)` + the shared `LandingPageStyles`, plane-neutral
and dependency-free, imported by C2 and C3.

### C5 — Serving + custom domains [R4]
Existing `*.jabaki.nl` distribution + stateless slug-path rewrite (no new per-tenant infra, no
request-time lookup). Custom domains per page via `tenant_custom_domains` + ACM + CloudFront alias
+ `domain_mapping` KVS, URL preserved (no redirect). CSP `frame-ancestors` from
`application_embed_origins` KVS (deny `'none'` when absent). All of this lives in **nonprofit after
the migration** — the gated dependency.

## Data Models

```
tenant_pages (MySQL)         — OQ1 (page identity; N per tenant; slug globally unique)
tenant_custom_domains (MySQL)— unchanged shape; a row references a page via its slug
myadmin-landing-pages (DDB)  — OQ2: SK=PAGE#{page_id}, versions PAGE#{page_id}#VERSION#{n}
config#fields (SAM DDB)      — slug + published_at/version (spec 12), the form's addressing
S3 myadmin-public-pages-{env}:
  {slug}/index.html          — rendered page (landing OR form), via shared page_shell
  {slug}/landing.json|form.json
  _slugs/{slug}              — slug→owner marker (OQ3), control-plane, never served
```

## Migration / Rollout

**Parallel track (account-agnostic — proceeds now, NOT gated on the hosting migration):**
1. `tenant_pages` + `PageRegistryService`; migrate landing rows; `tenant_slugs` → compat view.
2. DynamoDB SK `LANDING#HOME` → `PAGE#{page_id}` migration (content-preserving, verified live).
3. Generalize `get_slug(tenant)` 1:1 callers to page-scoped; per-page rename/custom-domain.
4. Extract `page_shell`; refactor `generate_index_html` to use it; share `LandingPageStyles`.
5. SAM public `GET {slug}` + `POST {slug}` (slug via `_slugs` marker, whitelist, no-auth);
   confirm submit IAM.
6. Author the NEW public-pages ADR; REVIEW ADR 0003/0005; document the Flask-owns-DynamoDB
   exception (R6).

**Gated track (needs the hosting migration complete — nonprofit owns the bucket/dist/KVS):**
7. SAM publish route live-wires `put_object` + invalidate against the **nonprofit** bucket/dist.
8. SAM bucket/CloudFront publish IAM (same-account nonprofit, least-privilege) — Terraform
   plan-first (steering 43).
9. Live end-to-end verify on a real tenant: publish a form slug, load `{slug}.jabaki.nl`, submit.

## Testing Strategy
- MySQL migration tests: `tenant_pages` accepts N slugs/tenant, `slug` globally unique, live
  landing rows preserved (real-data fixture).
- DynamoDB migration tests: `LANDING#HOME` → `PAGE#{page_id}` preserves content for live tenants.
- SAM tests: public `GET/POST {slug}` no-auth, whitelist-filtered, marker-resolved (not scan),
  publication-gated, non-probeable 404.
- Frontend tests: published shell fetches + renders via `ApplicationFormRenderer`.
- Shared-lib tests: `page_shell`/`LandingPageStyles` output parity for a landing fixture
  (no regression vs today's `generate_index_html`).
- Change-with-tests, both planes (steering 30/34/33).

## Non-goals / risks
- No shared cross-plane database; no Flask↔SAM runtime call (steering 35 rule 5a).
- No `*.{tenant-id}.jabaki.nl` host reshape (parked in the hosting backlog).
- Risk: the DynamoDB PK question (keep `TENANT#{slug}` vs move to `page_id`) — resolve in tasks;
  a slug-rename touching the PK is the thing OQ2 is trying to avoid.
- Risk: the compat `tenant_slugs` view must not mask a missed 1:1 caller — grep + fail-loud.
- Spec 13 R3 dropdown color = final cosmetic step in the one renderer AFTER serving settles.
