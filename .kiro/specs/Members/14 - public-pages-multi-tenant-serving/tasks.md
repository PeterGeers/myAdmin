# Implementation Plan — 14. SAM Public-Pages Platform (application-form-first)

## Overview

Implements `design.md`. **Reframed 2026-11-01**: builds a SAM-plane public-pages platform with the
application form as the first producer. The old Flask-reshape tasks (new `tenant_pages` table,
landing DynamoDB re-key, `get_slug`/`rename_slug` generalization) are **REMOVED** — the live Flask
landing module is NOT touched (old OQ1/OQ2 withdrawn; see requirements Scope decision + the ADR in
Task 7). Each task updates its paired test in the SAME change (steering 30/34/33). Two tracks:

- **PARALLEL** = account-agnostic; proceeds now, NOT blocked by the hosting migration.
- **GATED** = requires `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit` COMPLETE
  (nonprofit owns the public-pages bucket / `*.jabaki.nl` distribution / KVS) before it runs.

> **⛔ PREREQUISITE (separate spec):** the hosting migration (`jabaki-hosting-migration-to-nonprofit/
> tasks.md`) must be done before the GATED live-write step. It is owner-run per that spec's model;
> do NOT start the GATED step until it is verified complete.

> **🚫 DO NOT TOUCH THE FLASK LANDING MODULE** anywhere in this spec: `landing_page_service.py`,
> `tenant_slugs`, the `myadmin-landing-pages` key shape, `get_slug`/`rename_slug`/`migrate_slug`.
> Landing is a FUTURE producer that migrates INTO this platform in a later spec.

## Task Dependency Graph

- Task 1 (slug marker) and Task 2 (shared shell) are the platform spine — independent, run first.
- Task 3 (`GET {slug}`) and Task 4 (`POST {slug}` → members) each depend on Task 1 (marker resolve).
- Task 5 (published shell) depends on Task 2 + Task 3.
- Task 6 (public prefix) and Task 7 (ADR/governance) are independent and run any time.
- Task 8 (publish claims slug, live write dormant) depends on Tasks 1, 2, 5.
- Task 9 (GATED live wiring + IAM + e2e) depends on Task 8 AND the hosting migration being complete.
- Task 10 (edge throttle / CAPTCHA / WAF — new infra scope) pairs with Task 9's live public API.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "6", "7"], "dependsOn": [] },
    { "wave": 2, "tasks": ["3", "4"], "dependsOn": ["1"] },
    { "wave": 3, "tasks": ["5"], "dependsOn": ["2", "3"] },
    { "wave": 4, "tasks": ["8"], "dependsOn": ["1", "2", "5"] },
    { "wave": 5, "tasks": ["9", "10"], "dependsOn": ["8"] }
  ]
}
```

## Tasks

### PARALLEL TRACK (account-agnostic)

- [x] 1. Slug marker store + contract — the platform spine [R4, D-SLUG]
  - [x] 1.1 ⚠ VERIFY S3 `If-None-Match: *` support on the target bucket/region FIRST. If
    unavailable, switch to the DynamoDB conditional-`PutItem(attribute_not_exists(pk))` fallback
    and RECORD the decision.
  - [x] 1.2 `slug_marker_store` (in `sam/shared`): `claim(slug, owner)` = conditional
    `put_object _slugs/{slug}` (`If-None-Match:*`) → `SlugTaken` on 412; `resolve(slug)` =
    `get_object` → marker body `{owner_plane, kind, tenant_id, resource_ref}`; `release(slug)`.
    Ownership decided from the BODY, never the slug string. Document `kind` as an OPEN set —
    `application_form` live; `webshop`/`event_calendar`/`landing` named as expected future kinds,
    INCLUDING BUT NOT LIMITED TO these.
  - [x] 1.3 Per-producer fast-fail validation hook (SAM config-row slug check runs first as UX);
    idempotent same-owner re-publish (body matches `owner_plane`+`kind`+`tenant_id`); clobber
    backstop; rename claims-new-before-releasing-old.
  - [x] 1.4 Paired tests T1–T8: same-plane dup, **cross-plane/kind dup**, **concurrency race →
    exactly one winner**, idempotent re-publish, resolve-by-body-not-name, safe rename,
    format/reserved, clobber backstop. **T2 + T3 run against REAL S3 (or a conditional-honouring
    emulator), NEVER a mock** (HC6).
  - _Requirements: R4.1–R4.6, R3.4, R3.5_

- [x] 2. Shared rendering library [R7, D-RENDER]
  - [x] 2.1 Extract `page_shell.render_page(head_meta, body_html, css)` as a plane-neutral,
    dependency-free module (from a COPY of the shell logic); keep `LandingPageStyles` as the shared
    CSS source (already `re`/`typing`-only — verified). Decide packaging (shared package vs
    `sam/shared`-style vendor) and record.
  - [x] 2.2 Wire the SAM form to render its shell via `page_shell`. **Do NOT refactor Flask
    `generate_index_html`** (landing-module change — out of scope). Note the future opportunity to
    share the library back into the landing plane.
  - [x] 2.3 Paired tests: `page_shell`/`LandingPageStyles` output parity against a fixture.
  - [x] 2.4 If a hidden Flask coupling blocks clean extraction, STOP and fall back to
    SAM-renders-own-shell for v1 (record the deferral; do not silently drop R7).
  - _Requirements: R7.1, R7.2, R7.3_

- [x] 3. SAM public read path — `GET {slug}` [R5, R10, D-SLUG]
  - [x] 3.1 Public `GET {slug}` (no auth, no `Auth` block, no `extract_user_credentials`): resolve
    slug via the `_slugs/{slug}` marker (Task 1) → tenant/form; publication-gate (unpublished →
    non-probeable 404); return the applicant schema via an EXPLICIT whitelist
    (reuse `get_public_field_config`). NEVER a table scan.
  - [x] 3.2 **SEC-1 (fail-closed whitelist):** the whitelist is an allowlist; an unknown/new field
    defaults HIDDEN; secrets at most a boolean existence flag. **SEC-5 (enumeration-safe):**
    unpublished and unknown return an IDENTICAL, timing-insensitive 404.
  - [x] 3.3 Paired SAM tests: no-auth; whitelist filter + **no un-whitelisted field escapes**
    (SEC-1, fail-closed); marker resolution (not scan); publication-gate; unknown/unpublished →
    non-probeable **and indistinguishable** 404 (SEC-5; T5 resolve-by-body applies).
  - _Requirements: R5.1, R5.2, R5.3, R10.1, R10.5_

- [x] 4. SAM public submit path — `POST {slug}` → members write [R5, R10]
  - [x] 4.1 Public `POST {slug}` (no auth): resolve slug AS DATA (marker body) → `create_application`
    into the MEMBERS MODULE's own `tenant_id`-partitioned store via its own Lambda; token-less,
    non-probeable. **SEC-3:** resolve tenant ONLY from the marker body, write scoped to that
    `tenant_id`, REJECT a foreign/cross-plane slug (body `owner_plane`/`kind` mismatch).
  - [x] 4.2 **SEC-2 (input validation):** before the write — strict server-side schema, payload
    SIZE CAP, and PER-FIELD type / allowed-value checks (email is an email, enum within published
    options, required present, unexpected fields rejected). (Edge throttle + CAPTCHA are Task 10.)
  - [x] 4.3 **SEC-9 (applicant PII):** persist only the form's declared fields, scoped to
    `tenant_id`; record the retention + deletion path (GDPR for EU tenants). **SEC-10
    (stored-XSS):** sanitize/encode applicant free-text at the trust boundary so it cannot execute
    when re-displayed in the admin review UI.
  - [x] 4.4 CONFIRM the Lambda role has least-privilege PutItem on the applications table; add it
    if missing (SAM template, same-account nonprofit).
  - [x] 4.5 Paired SAM tests: no-auth submit routes to the CORRECT tenant's members store via the
    marker body (SEC-3, REAL behaviour not a mock); foreign/cross-plane slug rejected; oversized /
    bad-type / unexpected-field payloads rejected (SEC-2); a `<script>` free-text value is
    neutralised on admin re-display (SEC-10); missing-IAM failure surfaced.
  - _Requirements: R5.1, R5.5, R3.2, R10.2, R10.3, R10.9, R10.10_

- [x] 5. Published shell renders the form [R5]
  - [x] 5.1 Published `{slug}/index.html` = thin self-contained shell that fetches `GET {slug}`
    (Task 3) and renders with the existing `ApplicationFormRenderer`, wrapped by the shared
    `page_shell` (Task 2).
  - [x] 5.2 Paired frontend tests: the published shell fetches + renders via
    `ApplicationFormRenderer`.
  - _Requirements: R5.4_

- [x] 6. Tenant public prefix + SAM slug-prefix validation [R2]
  - [x] 6.1 Add `tenants.public_prefix VARCHAR(20) UNIQUE` (slug-safe) via migration; backfill a
    prefix for existing tenants (suggest-from-name, confirm short values e.g.
    `vandenheuvelhoveniers`→`vdh`). Authored Flask-side (tenant system-of-record). **This is a
    tenant-record attribute — NOT a landing-module change** (Scope decision holds).
  - [x] 6.2 Add `public_prefix` as an ADDITIVE attribute on the already-projected `tenant` row
    (`SK="tenant"`) in the `s3-claims-and-projection` sync item builder. CONFIRM the sync picks it
    up (small additive change to the existing one-directional sync — flag if the builder needs a
    touch). SAM reads it from its own projected `tenant` row; no call to Flask.
  - [x] 6.3 Slug-prefix validation (SAM claim path): a new slug must be `{prefix}` or
    `{prefix}-{suffix}` and start with the AUTHENTICATED tenant's prefix; reject borrowing another
    tenant's prefix. Grandfather live slugs (incl. uppercase legacy). Format/reserved runs before
    the claim. **SEC-4:** enforce this prefix rule on EVERY claim path — the uniqueness gate alone
    (Task 1) is tenant-agnostic and does NOT prevent squatting.
  - [x] 6.4 Paired tests: T9 (prefix required), T10 (can't borrow another prefix — SEC-4), T11
    (grandfathering), plus the projected-`tenant`-row carries `public_prefix` (SAM reads it).
  - _Requirements: R2.1–R2.6, R10.4_

- [x] 7. ADR + governance + reconcile + spec hygiene [R8]
  - [x] 7.1 Author the NEW ADR "SAM Public-Pages Platform": page-as-unit realized PER PLANE; the
    application form as the first producer; the FOUR producer contracts; the OPEN `kind` set
    (webshop, event_calendar, landing named as expected future kinds, NOT limiting); the
    no-shared-DB rule (5a); and that old OQ1/OQ2 (Flask `tenant_pages` + landing DynamoDB re-key)
    are WITHDRAWN, with the reason (future landing migration belongs on the SAM platform).
  - [x] 7.2 REVIEW ADR 0003 (platform base) + ADR 0005 (MySQL SoR + projection) for consistency
    with the platform framing.
  - [x] 7.3 Cross-reference the hosting backlog; confirm no parallel slug store / bucket / CF path
    is introduced (D7 reconciliation).
  - _Requirements: R8.1, R8.2, R8.3_

- [x] 8. Publish route claims the slug (live write still dormant) [R3, R4]
  - [x] 8.1 Wire the existing `POST /members/application-form/publish` to claim its slug via
    Task 1 (idempotent same-owner re-publish; clobber backstop) and render the shell (Task 2/5).
    The LIVE S3 put + CloudFront invalidate stay GATED (Task 9); everything up to the write runs
    now (dry-run/local).
  - [x] 8.2 Paired tests: publish claims the slug; re-publish is idempotent; publish won't clobber
    a foreign-owned slug.
  - _Requirements: R3.1, R3.2, R4.4, R4.5_

---

### GATED TRACK (needs the hosting migration COMPLETE)

- [ ] 9. SAM publish route — live wiring + IAM + end-to-end [R3, R5, R6, R10]
  - [x] 9.1 Live-wire the publish route's `put_object {slug}/index.html` + `{slug}/form.json` +
    CloudFront invalidation against the **nonprofit** bucket/distribution (lift the dormant write
    from Task 8).
  - [x] 9.2 **SEC-8 (least-privilege, prefix-scoped publish IAM):** Terraform grants the publish
    role `s3:PutObject`/`DeleteObject` SCOPED to its own `{slug}/*` artifacts + the `_slugs/{slug}`
    markers it owns — never bucket-wide — plus `cloudfront:CreateInvalidation` on the distribution,
    in nonprofit. Plan-first, reviewed in the same PR; confirm the plan ADDS IAM and does NOT
    force-replace the distribution/bucket/KVS (steering 43 — a replacement there is a STOP).
  - [x] 9.3 **SEC-7 (framing defaults closed):** confirm the `application_embed_origins` KVS +
    viewer-response function deny framing (`'none'`) for a host with no entry, and that
    tenant-authored embed origins are input-validated before write.
  - [x] 9.4 Live end-to-end on TEST: author a form slug, publish, load `{slug}.jabaki.nl`, submit
    an application; confirm the artifact serves and the submit resolves the tenant from data +
    lands in the members store. Confirm a per-page custom domain serves URL-preserved (no redirect)
    and CSP `frame-ancestors` behaves (allowed origin vs `'none'`, SEC-7).
  - _Requirements: R3.1, R5.1, R5.4, R5.5, R6.2, R6.3, R10.7, R10.8_

- [ ] 10. Public-endpoint edge hardening — throttle / CAPTCHA / WAF [R10]
  - [x] 10.1 **SEC-2 (edge abuse controls):** add a per-source rate limit / throttle on the public
    `GET/POST {slug}` routes, and a CAPTCHA or equivalent challenge on `POST {slug}`. (The
    server-side payload/field validation half of SEC-2 is Task 4.2.) These MUST be in place before
    the public submit is exposed.
  - [x] 10.2 **SEC-6 (DoS-bounded):** front the public API with WAF / throttling; confirm slug
    resolution stays O(1) keyed lookup (never a scan) so `GET {random-slug}` floods cannot amplify
    cost or exhaust the datastore.
  - [x] 10.3 Paired tests / verification: throttle trips at the configured rate; a challenge is
    required on submit; a burst of unknown-slug GETs is rate-limited, not amplified.
    (`task-10.3-verification-battery-mapping.md`: item 1 = the 10.1 stack contract + the live
    429 deferred to 9.4; item 2 = the honeypot edge tests; item 3 = the 10.2 no-scan tests +
    one added consolidating `..._burst_resolves_by_one_keyed_lookup_and_is_not_amplified`
    test. 83 passed across both focused files.)
  - _Requirements: R10.2, R10.6_
  - _Note:_ this is NEW infra/edge scope (API Gateway throttling / WAF / a CAPTCHA provider). It
    pairs with the live public API; sequence it alongside Task 9's live wiring (the controls are
    meaningless until the endpoints are publicly reachable).

## Notes

- Tasks 1–8 (PARALLEL) have no account dependency — do them now. Dependency order: Task 1 (marker)
  and Task 2 (shell) first; Task 3 depends on 1; Task 4 depends on 1; Task 5 depends on 2+3;
  Task 8 depends on 1+2+5; Tasks 6 and 7 are independent.
- Tasks 9 and 10 (GATED / edge) start once the hosting migration is complete and the public API is
  reachable — Task 10's throttle/CAPTCHA/WAF are meaningless until the endpoints are live.
- Security controls (R10 / SEC-1…SEC-10): SEC-1/5 in Task 3; SEC-2 (validation) + SEC-3 + SEC-9/10
  in Task 4; SEC-4 in Task 6; SEC-7/8 in Task 9; SEC-2 (edge) + SEC-6 in Task 10. The critical trio
  (SEC-1/2/3) and SEC-4 are proven against REAL behaviour, never mocks (HC6).
- The live Flask landing module is NOT modified in ANY task (landing-plane non-regression, R9.5).
- Spec 13 R3 dropdown color is applied in the one renderer AFTER serving settles — tracked in
  spec 13, not here.
