# Tasks — 14. Public-Pages Multi-Tenant Serving (page-as-unit)

Implements `design.md` (OQ1–OQ4 as proposed). Each task updates its paired test in the SAME change
(steering 30/34/33). Two tracks:

- **PARALLEL** = account-agnostic; proceeds now, NOT blocked by the hosting migration.
- **GATED** = requires `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit` COMPLETE
  (nonprofit owns the public-pages bucket / `*.jabaki.nl` distribution / KVS) before it runs.

> **⛔ PREREQUISITE (separate spec):** the hosting migration (`jabaki-hosting-migration-to-nonprofit/
> tasks.md`) must be done before the GATED tasks (7–9). It is agent-run with per-step approval per
> that spec's execution model; do NOT start GATED tasks until it is verified complete.

---

## PARALLEL TRACK (account-agnostic)

- [ ] 1. Page registry (MySQL) — lift the 1:1 limit [R1, OQ1]
  - [ ] 1.1 Add migration creating `tenant_pages` (page_id PK, administration, kind, slug UNIQUE,
    jabaki_enabled, published_at, indexes, FK) per design OQ1. NO `administration UNIQUE`.
  - [ ] 1.2 Backfill: insert one `tenant_pages` row per existing `tenant_slugs` row
    (`kind='landing'`, same slug, same jabaki_enabled). Verify against the live rows.
  - [ ] 1.3 Replace `tenant_slugs` with a compat VIEW (`administration, slug … WHERE kind='landing'`)
    OR keep the table and dual-write during cutover — choose in 1.3 and record. Un-migrated
    callers keep working.
  - [ ] 1.4 `PageRegistryService`: `list_pages(tenant)`, `resolve_slug(slug)`, `get_page(page_id)`,
    `create_page`, `rename_slug(page_id,…)`, `attach/detach_custom_domain(page_id, domain)`.
  - [ ] 1.5 Paired migration + service tests: N slugs/tenant accepted; `slug` globally unique;
    live landing rows preserved (real-data fixture).
  - _Requirements: R1.1, R1.2, R1.4, R1.5, R1.6_

- [ ] 1b. Tenant public prefix (MySQL + projection) [R2, OQ1b]
  - [ ] 1b.1 Add `tenants.public_prefix VARCHAR(20) UNIQUE` (slug-safe) via migration; backfill a
    prefix for existing tenants (suggest-from-name, confirm short values e.g.
    `vandenheuvelhoveniers`→`vdh`). Authored Flask-side (tenant system-of-record).
  - [ ] 1b.2 Add `public_prefix` as an ADDITIVE attribute on the already-projected `tenant` row
    (`SK="tenant"`) in the `s3-claims-and-projection` sync item builder. CONFIRM the sync picks it
    up (small additive change to the existing one-directional sync — flag if the builder needs a
    touch). SAM reads it from its own projected `tenant` row; no call to Flask.
  - [ ] 1b.3 Slug-prefix validation (both planes): a new slug must be `{prefix}` or
    `{prefix}-{suffix}` and start with the AUTHENTICATED tenant's prefix; reject borrowing another
    tenant's prefix. Grandfather live slugs (incl. uppercase legacy).
  - [ ] 1b.4 Paired tests: T9 (prefix required), T10 (can't borrow another prefix), T11
    (grandfathering), plus the projected-`tenant`-row carries `public_prefix` (SAM reads it).
  - _Requirements: R2.1–R2.6_

- [ ] 1c. Slug uniqueness — atomic `_slugs/{slug}` claim [R3a, OQ3]
  - [ ] 1c.1 ⚠ VERIFY S3 `If-None-Match: *` support on the target bucket/region FIRST. If
    unavailable, switch to the DynamoDB conditional-`PutItem` fallback (record the decision).
  - [ ] 1c.2 `slug_marker_store` repository (SAM `sam/shared` + a Flask equivalent): `claim(slug,
    owner)` = conditional `put_object _slugs/{slug}` (`If-None-Match:*`) → `SlugTaken` on 412;
    `resolve(slug)` = `get_object` → marker body `{owner_plane, kind, tenant_id, resource_ref}`;
    `release(slug)`. Ownership decided from the BODY, never the slug string.
  - [ ] 1c.3 Wire both planes' publish paths to claim via 1c.2; per-plane UNIQUE/validation as
    fast-fail first; idempotent same-owner re-publish; clobber backstop.
  - [ ] 1c.4 Paired tests T1–T8 (see requirements R7 list): same-plane dup, **cross-plane dup**,
    **concurrency race → exactly one winner**, idempotent re-publish, resolve-by-body-not-name,
    safe rename, format/reserved, clobber backstop. **T2 + T3 run against REAL S3 (or a
    conditional-honouring emulator), NEVER a mock** (HC6).
  - _Requirements: R3a.1–R3a.6_

- [ ] 2. DynamoDB per-page sort key [R1, OQ2]
  - [ ] 2.1 Move `myadmin-landing-pages` draft SK `LANDING#HOME` → `PAGE#{page_id}`; versions →
    `PAGE#{page_id}#VERSION#{n}`. Decide + record the PK sub-question (keep `TENANT#{slug}` vs move
    to `administration`/`page_id`) — prefer page_id-stable so a slug rename doesn't rewrite keys.
  - [ ] 2.2 Rework `get_draft`/`save_draft`/`delete_draft`/`migrate_slug`/`list_versions`/
    `prune_old_versions` to take `page_id`; `kind` as an attribute.
  - [ ] 2.3 Content-preserving migration of each live `LANDING#HOME` item (+ versions) to the new
    SK. Verify content parity against live rows.
  - [ ] 2.4 Paired tests: migration preserves content; the page-scoped CRUD round-trips.
  - _Requirements: R1.3, R1.6_

- [ ] 3. Generalize 1:1 callers + per-page rename/custom-domain [R1, R4]
  - [ ] 3.1 Grep every `get_slug(tenant)` / single-slug assumption (publish service, rename,
    domain endpoints); make page-scoped. Fail loud on any residual 1:1 assumption.
  - [ ] 3.2 `rename_slug` becomes per-page (update `tenant_pages.slug` + DynamoDB stays on page_id
    + S3 artifact move + `domain_mapping` KVS + CloudFront invalidation); mirror the landing rename
    steps that still apply.
  - [ ] 3.3 `tenant_custom_domains` lifecycle (ACM → CloudFront alias → `domain_mapping` KVS) wired
    per page (row already slug-keyed → references a page). URL preserved, no redirect.
  - [ ] 3.4 Paired tests: a tenant with 2 pages renames/attaches-domain to one without touching the
    other; no 1:1 regression for the live tenants.
  - _Requirements: R1.5, R4.1, R4.2, R4.3_

- [ ] 4. Shared rendering library [R5, OQ4]
  - [ ] 4.1 Extract `page_shell.render_page(head_meta, body_html, css)` from
    `generate_index_html` into a plane-neutral, dependency-free module; keep `LandingPageStyles`
    as the shared CSS source (already `re`/`typing`-only — verified). Decide packaging (shared
    package vs `sam/shared`-style vendor) and record.
  - [ ] 4.2 Refactor Flask `generate_index_html` to call `page_shell.render_page` (landing body =
    its sections HTML). No visual regression.
  - [ ] 4.3 Paired tests: `page_shell`/`LandingPageStyles` output parity vs today's
    `generate_index_html` for a landing fixture (snapshot/parity test).
  - [ ] 4.4 If a hidden Flask coupling blocks clean extraction, STOP and fall back to
    SAM-renders-own-shell for v1 (record the deferral; do not silently drop R5).
  - _Requirements: R5.1, R5.2_

- [ ] 5. SAM public data path [R3, OQ3]
  - [ ] 5.1 Public `GET {slug}` (no auth, no `Auth` block, no `extract_user_credentials`):
    resolve slug via the `_slugs/{slug}` S3 marker → tenant/form; publication-gate (unpublished →
    non-probeable 404); return the applicant schema via an EXPLICIT whitelist
    (reuse `get_public_field_config`). NEVER a table scan.
  - [ ] 5.2 Public `POST {slug}` (no auth): resolve slug AS DATA → `create_application`;
    token-less, non-probeable. CONFIRM the Lambda role has PutItem on the applications table
    (brief open item); add least-privilege if missing.
  - [ ] 5.3 Published `{slug}/index.html` = thin shell that fetches `GET {slug}` and renders with
    the existing `ApplicationFormRenderer` (shared `page_shell` wrap).
  - [ ] 5.4 Paired SAM tests: no-auth; whitelist filter; marker resolution (not scan);
    publication-gate; unknown/unpublished → non-probeable 404.
  - _Requirements: R3.1, R3.2, R3.3, R3.4, R3.5_

- [ ] 6. ADR + governance actions [R6]
  - [ ] 6.1 Author NEW ADR "Multi-tenant public-pages addressing: page as the unit, not tenant"
    (records D2 + D3 dumb-infra hand-off + no-shared-DB rule).
  - [ ] 6.2 REVIEW ADR 0003 (platform base) + ADR 0005 (MySQL SoR + projection) for consistency.
  - [ ] 6.3 Document the Flask-owns-DynamoDB exception (third tenancy shape) in steering or an ADR.
  - [ ] 6.4 Cross-reference the hosting backlog; confirm no parallel slug store / bucket / CF path
    is introduced (D7 reconciliation).
  - _Requirements: R6.1, R6.2, R6.3_

## GATED TRACK (needs the hosting migration COMPLETE)

- [ ] 7. SAM publish route — live wiring [R2, R3]
  - [ ] 7.1 members:admin, readiness-gated publish: render form via `get_public_field_config` +
    shared `page_shell`; `put_object {slug}/index.html` + `{slug}/form.json`; conditional-claim
    `_slugs/{slug}`; invalidate — against the **nonprofit** bucket/distribution.
  - [ ] 7.2 Paired tests: renders via the single filter authority (parity), writes expected S3
    keys, invalidates, is members:admin + readiness gated, replaces prior version.
  - _Requirements: R2.1, R2.2, R3.4_

- [ ] 8. SAM publish IAM (nonprofit, same-account) [R2]
  - [ ] 8.1 Terraform: least-privilege `s3:PutObject`/`DeleteObject` on the public-pages bucket `/*`
    + `cloudfront:CreateInvalidation` on the distribution, in nonprofit. Plan-first, reviewed in
    the same PR; confirm the plan ADDS IAM and does NOT force-replace the distribution/bucket/KVS
    (steering 43 — a replacement there is a STOP).
  - _Requirements: R2.1_

- [ ] 9. Live end-to-end verification [R2, R3, R4]
  - [ ] 9.1 On live TEST: author a form slug, publish, load `{slug}.jabaki.nl`, submit an
    application; confirm the artifact serves and the submit resolves the tenant from data.
  - [ ] 9.2 Confirm a per-page custom domain serves the page with the URL preserved (no redirect)
    and CSP `frame-ancestors` behaves (allowed origin vs `'none'`).
  - _Requirements: R2.1, R3.1, R3.4, R4.2, R4.3_

## Sequencing

- Tasks 1–6 (PARALLEL) have no account dependency — do them now, any order within dependency
  (1→2→3 are registry-ordered; 4, 5, 6 independent).
- Tasks 7–9 (GATED) start ONLY after the hosting migration spec is verified complete.
- Spec 13 R3 dropdown color is applied in the one renderer AFTER serving settles — tracked in
  spec 13, not here.
