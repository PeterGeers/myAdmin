# Task 7.3 — Hosting-backlog reconciliation (D7): no parallel slug store / bucket / CF path

> **VERIFICATION / RECORD TASK** (R8.1/R8.2/R8.3, part of Task 7 — ADR + governance). This is the
> explicit D7 reconciliation the design and ADR 0010 call for: confirm spec 14 (the SAM
> public-pages PLATFORM) does **not** introduce a slug store, a bucket, or a CloudFront path that
> runs in PARALLEL to the ones owned by the hosting backlog
> (`.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit/`). Documentation review only — no
> product code, no Flask landing-module change, no AWS calls.

## What the hosting backlog OWNS (the resources spec 14 must reuse, never duplicate)

From `jabaki-hosting-migration-to-nonprofit/design.md` (its "Current State" + "Components"):

- **Bucket:** the public-pages S3 origin — `myadmin-public-pages-production` on personal today,
  migrating to a new globally-unique **nonprofit** bucket (D3; the verified name in use is
  `myadmin-public-pages-nonprofit-506221081911`, eu-west-1, account `506221081911`). Written by the
  backend via env **`LANDING_PAGES_BUCKET`**.
- **CloudFront:** the single `*.jabaki.nl` distribution (`E28OSWC7A9O9K2` on personal → a new
  nonprofit distribution after cutover) + the stateless viewer-request **url-rewrite** function
  (slug-path routing) + the `domain_mapping` / `application_embed_origins` KVS + the
  viewer-response frame-ancestors function.
- Invalidations keyed off `CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID`.

Spec 14 builds a PRODUCER (publish + the public `GET`/`POST {slug}` edge) + a shared slug NAMESPACE
on TOP of that topology; the live write is GATED on the migration (Tasks 8/9). It must add no
parallel copy of any of the three.

## Cross-check 1 — BUCKET: reuses the shared nonprofit bucket via env, introduces NO new bucket — **PASS**

Evidence (grepped/read):

- `sam/members/repository/slug_marker_store.py` resolves the bucket ONLY from the env var, never a
  literal:
  - `LANDING_PAGES_BUCKET_ENV_VAR = "LANDING_PAGES_BUCKET"` — the SAME var the hosting backlog's
    `landing_page_publish_service.py` writes through (design "Backend coupling" +
    "configuration contract").
  - `resolve_public_pages_bucket_name()` → `require_env(LANDING_PAGES_BUCKET_ENV_VAR)` (fail-fast,
    no default, steering 23). `S3SlugMarkerStore.bucket` resolves lazily from that; a test may inject
    a bucket but there is no hard-coded production bucket name in the code path.
  - Module docstring states it outright: *"the bucket resolves lazily + fail-fast from
    `LANDING_PAGES_BUCKET` (mirroring the landing publish path)"* and *"dormant until the owner-run
    hosting migration moves the public-pages bucket to nonprofit."*
- Grep for `myadmin-public-pages` in `sam/**/*.py` finds only (a) a docstring example
  `myadmin-public-pages-<env>`, (b) the DORMANT-write comments in `application_publish.py` /
  `application_form_render.py` describing the gated write to `myadmin-public-pages-{env}`, and
  (c) TEST files (`BUCKET = "myadmin-public-pages-test"`, and the opt-in real-S3 test naming
  `myadmin-public-pages-nonprofit-506221081911`). None of these create a bucket.
- The ONLY `AWS::S3::Bucket` resource in `sam/members/template.yaml` is **`SharedBucket`**
  (`BucketName: !Ref SharedBucketName` = `myadmin-shared` / `myadmin-shared-test`). That is the
  **mail-template bodies/logos** bucket (mail-spec correction C4), keyed `<tenant>/members/mail/*`,
  consumed via `S3_SHARED_BUCKET` — a DIFFERENT concern from public-pages, NOT a second public-pages
  bucket. No `PublicPages`/`LANDING_PAGES_BUCKET` bucket resource exists in the template.

**Finding:** spec 14 introduces no new/parallel bucket. The slug marker + the (gated) publish write
both resolve the SAME shared nonprofit public-pages bucket from `LANDING_PAGES_BUCKET`.

## Cross-check 2 — CLOUDFRONT: reuses the `*.jabaki.nl` distribution + rewrite, introduces NO new distribution/rewrite — **PASS**

Evidence:

- Grep for `AWS::CloudFront` in `sam/members/template.yaml` → **no match**. Spec 14 declares no
  CloudFront distribution, no CloudFront function, no KVS resource.
- Every CloudFront reference in spec-14 code is either (a) a comment marking the live
  invalidation DORMANT/GATED — `application_publish.py` / `application_form_render.py` /
  `_dispatch_services.py` / `routes.py` all say the live S3 write + "invalidate the `*.jabaki.nl`
  distribution" is Task 8/9, gated on the owner-run hosting migration — or (b) the embed/CSP
  enforcement that REUSES the hosting migration's `application_embed_origins` KVS: `public_app.py`
  and `config_write_service.py` read the ONE tenant-authored `application_embed_origins` list that
  "feeds BOTH the CloudFront `frame-ancestors` and the SAM public API CORS", explicitly so the two
  enforcement points "cannot drift" — i.e. the SAM edge CONSUMES the hosting migration's KVS rather
  than standing up a parallel one.
- `tenant_directory.py` records D19: the slug mechanism REUSES the landing-page slug mechanism
  (`<slug>.jabaki.nl` host-based + the existing custom-domain→slug CloudFront KeyValueStore
  `myadmin-domain-slug-mapping` from `infrastructure/landing-pages.tf`) — *"There is NO new
  `tenant-directory` store."*

**Finding:** spec 14 introduces no new CloudFront distribution and no parallel slug-path rewrite. It
reuses the hosting migration's `*.jabaki.nl` distribution, its url-rewrite function, and its
embed-origins KVS; the live put/invalidate is dormant until that migration completes.

## Cross-check 3 — SLUG STORE: exactly ONE namespace mechanism (`_slugs/{slug}` S3 marker), NO parallel registry — **PASS**

Evidence:

- `SLUG_MARKER_PREFIX = "_slugs/"` has a SINGLE definition (in `slug_marker_store.py`). There is no
  second marker prefix and no DynamoDB slug table anywhere in `sam/**`.
- `file_search slug_marker_store` returns exactly one source module —
  `sam/members/repository/slug_marker_store.py` (plus its generated `.aws-sam/build/…` copy, a build
  artifact, and the test files). There is **no** slug store under `sam/shared/` (that dir holds only
  `page_shell.py` + the auth/JWKS helpers).
- The spec-12 legacy reverse-lookup (`claim_slug`/`resolve_slug` → `tenant_id`) and the spec-14
  structured contract (`claim`/`resolve`/`release` over the JSON marker body) **write to the SAME
  `_slugs/{slug}` key with the same if-none-match gate** — the module docstring states this
  explicitly. The store was EXTENDED IN PLACE, not duplicated (matching the task-1.2 finding below).
- The SAM `tenant_id`-PK governance-projection table deliberately holds NO slug-keyed item
  (`_fields_overlay_reader.py`: the reverse lookup "deliberately does NOT live on this `tenant_id`-PK
  table … That is the `_slugs/{slug}` bucket marker"); slug UNIQUENESS is NOT re-checked in
  `config_write_service.py` (the config-row slug check is an advisory FORMAT/UX fast-fail only — the
  authoritative gate is the one `_slugs/{slug}` conditional put). So there is no second
  uniqueness/registry mechanism competing with the marker.

**Finding:** one slug namespace mechanism — the `_slugs/{slug}` marker in the shared bucket. No
parallel DynamoDB slug table, no second marker prefix, no Flask-side duplicate.

## Task-1.2 placement reconciliation — single store; `sam/shared` relocation is a NON-ISSUE (not a tracked follow-up)

- Some task text (tasks.md 1.2, and ADR 0010's "Code as built" line) refers to the store as "in
  `sam/shared`", while the code lives at **`sam/members/repository/slug_marker_store.py`**. This is a
  SINGLE store, not two — confirmed above (one source module; `sam/shared/` has no slug store).
- The physical location is **correct by steering 39** (Data & Service Access, SAM plane): the slug
  marker store is a REPOSITORY ADAPTER — it owns the boto3 S3 client and the `_slugs/{slug}` I/O —
  and steering 39 lists `slug_marker_store` explicitly among the SAM repository adapters ("one
  repository per external service"). `sam/shared/` is reserved for plane-neutral, dependency-free
  cross-cutting helpers (the JWKS fetch, `page_shell`) — a boto3-owning adapter does not belong
  there. So the repository-layer placement is the RIGHT home, and the "in `sam/shared`" phrasing in
  the earlier task/ADR text was aspirational wording, not a second location.
- **Disposition:** a relocation to `sam/shared` is a **NON-ISSUE**, deliberately NOT tracked as a
  follow-up — moving a boto3-owning repository adapter into the dependency-free shared dir would
  CONTRADICT steering 39. The single store stays in the repository layer. (The only genuinely shared,
  dependency-free piece — the rendering library — already lives at `sam/shared/page_shell.py`,
  correctly.) No code change is made by this task.

## Disposition — where this is recorded

- **This file IS the recorded D7 reconciliation outcome**, matching the spec-folder decision-record
  convention (`task-1.1-slug-marker-decision.md`, `task-2.1-page-shell-decision.md`,
  `task-7.2-adr-consistency-review.md`).
- **ADR 0010 NOT edited.** Its closing "Reconciliation reminder (spec 14 task 7.3)" already states
  the non-negotiable (the platform "MUST NOT invent a parallel slug store, bucket, or CloudFront
  path — the live write reuses the nonprofit-owned bucket/distribution once that migration is
  complete") and its Consequences bullet already records that the gated live write "introduce[s] NO
  parallel slug store, bucket, or CloudFront path (D7 reconciliation)." This record is the evidence
  behind that statement; re-asserting it inside the ADR would duplicate this file.
- **design.md D7 NOT edited** — the reconciliation it anticipated is satisfied and recorded here.

---

## Verdict — **PASS** (no parallel slug store / bucket / CF path)

All three cross-checks confirm spec 14 adds a PRODUCER + a shared slug namespace ON TOP of the
hosting backlog's topology and reuses its bucket (via `LANDING_PAGES_BUCKET`), its `*.jabaki.nl`
CloudFront distribution + url-rewrite + embed KVS, and the single `_slugs/{slug}` marker store — it
introduces **no** parallel bucket, **no** parallel CloudFront distribution/rewrite, and **no**
parallel slug registry. The task-1.2 placement note is reconciled: one store, correctly in the
repository layer per steering 39; no relocation follow-up. D7 reconciliation holds.
