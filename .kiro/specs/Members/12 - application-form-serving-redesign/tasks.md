# Implementation Plan — Application Form Serving Redesign

- Status: **Draft** (tasks phase — build gated on user approval of requirements + design).

## Overview

- Follows `requirements.md` (R1–R9) and `design.md` (C1–C6, D1–D8, §Uniqueness, §Rename).
- Supersedes the spec 11 parts named in `requirements.md` → "Relationship to spec 11"; reuses the rest.
- Plane split: **SAM** (slug on `config#fields`, data-backed resolver, publish route, IAM),
  **frontend** (field-modal authoring, in-browser preview, slug/embed surface), **Terraform** (SAM
  bucket/CloudFront IAM — manual, plan-first, steering 43). **No Flask runtime work.**
- Tests are paired INTO each phase (change-with-tests, steering 30/34/33) — never deferred. Reuse the
  spec 11 real-data fixture (`config#fields` for `h-dcn`); fixtures use the bare `key` + `group` server
  shape (R2.3).
- Checkbox vocabulary: `[ ]` not started · `[x]` done · `❌` blocked/failed.
- **Non-negotiable throughout:** no runtime SAM↔Flask call; the slug is data on `config#fields`; SAM
  publishes; serving reuses the one `*.jabaki.nl` distribution + stateless rewrite (no new infra).

---

## Tasks

### Phase 0 — Prerequisite migration + confirm two open questions — ~0.5 day (+ the migration itself)

- [ ] 0.1 **⛔ OWNER-RUN PREREQUISITE — NOT agent-runnable (steering 43).** Execute
  `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit` so `myadmin-public-pages-{env}` + the
  `*.jabaki.nl` distribution + KVS are owned by nonprofit (`506221081911`). This is a CROSS-ACCOUNT
  cutover of LIVE PRODUCTION hosting (S3 + CloudFront + KVS) — a high-blast-radius / destroy-capable
  infra op that steering 43 reserves for the owner; an agent/task-runner MUST NOT attempt it and MUST
  hand off here. It GATES only Phase 2 (live publish), Phase 3 (IAM), and Phase 7 (live verify/promote);
  the account-agnostic phases (1, 4, 5, 6) + task 2.1 proceed in PARALLEL and do NOT wait on it (see the
  Task Dependency Graph — 0.1 is isolated in its own gate wave so it never blocks the agent-runnable
  track). Do NOT wire the live publish against the personal bucket. Owner verifies cutover via that
  spec's acceptance checks before the task runner resumes with Phase 2.2+/3.
- [x] 0.2 Slug uniqueness SCOPE + landing-collision guard — **RESOLVED (OQ2, 2026-10-23, verified
  against the live `myadmin-public-pages-production` bucket).** Collision namespace = the
  `{slug}/index.html` object in the one bucket (the `*.jabaki.nl` host stores nothing — pure string
  rewrite). Form-vs-landing guard = a publish-time S3 check on the ROOT `{slug}/landing.json` marker.
  Verified: 3 of 7 live slugs have NO root `index.html` (only a `landing-pages/` asset subfolder), so
  "folder exists" is NOT a valid signal — the guard keys on root `landing.json`, ignoring the
  `landing-pages/` subfolder. (design D6.) NOTE: the form-vs-form reverse-LOOKUP mechanism is NOT settled
  here — that is 0.4 (OQ4).
  - [ ] 0.2a BEFORE Phase 2 wiring, RE-VERIFY the marker against the NONPROFIT bucket after the migration
    (the live check was on personal; re-confirm root `landing.json` is the marker post-copy).
- [x] 0.3 Publish mechanism — **RESOLVED (OQ1, option 1, 2026-10-23): explicit
  `POST /members/application-form/publish` route**, NOT save-triggered. Save ≠ publish; the live form
  changes only on a deliberate, readiness-gated publish. (design §C4.)
- [x] 0.4 Slug→`tenant_id` reverse-lookup MECHANISM — **RESOLVED (OQ4, 2026-10-23): a `_slugs/{slug}`
  marker object in the shared public-pages bucket.** Claim/uniqueness = conditional `put_object`
  (if-none-match); resolve = `get_object` (scan-free); `_slugs/` is a RESERVED prefix, OUTSIDE any served
  `{slug}/` prefix. No DynamoDB change (keeps the `tenant_id`-PK governance-projection table's
  structural-isolation invariant — `template.yaml`); reuses publish infra; disposable under the parked
  `*.{tenant-id}.jabaki.nl` host model (R4.6). (design D6 / §Reverse-lookup.)

### Phase 1 — SAM: slug on `config#fields` + data-backed resolver (R4, R7) — ~2 days · ACCOUNT-AGNOSTIC (parallel to the migration)

- [x] 1.1 Extend `config#fields` with `slug` + `published_at` + `published_version` (design §Data Models).
  `ConfigWriteService._validate_fields_body`: validate slug format (landing `SLUG_PATTERN` rules) and
  reject a malformed slug fail-loud with the standard envelope (R4.2, R8 unchanged).
- [x] 1.2 Implement the `_slugs/{slug}` bucket-marker claim (OQ4): a conditional `put_object`
  (if-none-match) writing the owning `tenant_id`, giving TENANT-scoped slug uniqueness (within-tenant
  only — NO global registry) AND the slug→tenant mapping in one step. Reserve the `_slugs/` prefix
  (reject a page slug named `_slugs` or starting `_slugs/`); keep markers OUTSIDE any served `{slug}/`
  prefix. The form-vs-landing publish-time S3 backstop (root `{slug}/landing.json` marker — defensive,
  not a uniqueness mechanism) is implemented in Phase 2.2 where the S3 write lives (R4.3 / D6).
- [x] 1.3 Forward slug reader (tenant→slug via the normal `tenant_id`-pinned read) on
  `MembersProjectionReader`; the reverse slug→tenant lookup is a `get_object` on `_slugs/{slug}` (OQ4),
  NOT a slug-keyed item on the governance-projection table (C3/C5).
- [x] 1.4 Add `ConfigFieldsSlugReader` implementing the EXISTING `TenantSlugReader` Protocol
  (`sam/members/domain/tenant_directory.py` — VERIFIED present; `EnvTenantSlugReader.resolve_slug`
  already satisfies it by duck-typing). Wire `TenantDirectory`/`public_app.py` to it IN PLACE OF
  `EnvTenantSlugReader` — no change to the resolver or edge (R7.1, verify-before-trust preserved, R7.2).
- [x] 1.5 Tests (`sam/tests/`): slug format accept/reject; uniqueness conditional-put collision;
  `ConfigFieldsSlugReader` resolves a known slug and 404s unknown/forged/blank/oversized
  (non-probeable, R7.2); the edge still 501/404s correctly through the new reader.

### Phase 2 — SAM: publish action (R5) — ~2 days  (depends Phase 1, 0.3; LIVE-WRITE gated on 0.1 migration)

- [x] 2.1 New `members:admin` route `POST /members/application-form/publish` (self_service=False) in
  `routes.py` + `_dispatch` (design §C4, OQ1=option 1 — EXPLICIT route, save never republishes).
  Readiness-gate it (slug + certified sender + ≥1 on-form field, spec 11 R6 / spec 10 D15) — refuse with
  a clear envelope, do not emit a broken artifact (R5.4).
- [ ] 2.2 Publish handler: render the artifact THROUGH `get_public_field_config` (single filter authority,
  R5.2) into self-contained, responsive HTML that reuses the `ApplicationFormRenderer` output contract +
  the `postMessage` resize script (R5.5); write `{slug}/index.html` + `{slug}/form.json` (+ an owner
  marker) to `myadmin-public-pages-{env}` via boto3; invalidate the `*.jabaki.nl` distribution for
  `/{slug}*`; replace the prior version + bump `published_version`/`published_at` (R5.1). NO Flask call
  (R5.3). **Form-vs-landing collision guard (D6):** BEFORE writing, refuse if a ROOT `{slug}/landing.json`
  SAM did not author is present (a landing page lives here); IGNORE the `{slug}/landing-pages/` asset
  subfolder (not a serving artifact, verified live). Republishing over SAM's own prior form artifact is
  fine.
- [ ] 2.3 Form-slug rename (design §Rename / D8): on a slug change, delete the old `{old-slug}/` artifact,
  publish under the new slug, invalidate both; `config#fields` update is the authoritative step; others
  best-effort with warnings.
- [ ] 2.4 Tests (`sam/tests/`): publish renders filter-parity output (reuse the `h-dcn` real-data
  fixture), writes the expected S3 keys, invalidates CloudFront, is `members:admin` + readiness gated,
  replaces the prior version; rename cleans the old prefix + republishes; unreadiness refuses cleanly;
  the form-vs-landing guard REFUSES when a root `{slug}/landing.json` (not SAM-authored) is present but
  ALLOWS when only a `{slug}/landing-pages/` asset subfolder exists (the two live bucket shapes, D6) and
  ALLOWS republish over SAM's own prior form artifact.

### Phase 3 — Terraform: SAM bucket/CloudFront IAM (R6) — ~0.5 day  (manual, plan-first; GATED on 0.1 migration)

- [ ] 3.1 Add a least-privilege IAM policy (new `.tf`) granting the SAM publish principal
  `s3:PutObject`/`s3:DeleteObject` on `myadmin-public-pages-{env}/*` + `cloudfront:CreateInvalidation` on
  the distribution — a mirror of the Flask Railway grant (R6.2). **Same-account in nonprofit** (option a,
  migration-first) — NO cross-account bucket policy or invalidation role. Do NOT reference the other
  plane's resources by hard-coded id (R6 / steering 43).
- [ ] 3.2 Confirm the published form host gets CSP `frame-ancestors` from the existing viewer-response
  function + `application_embed_origins` KVS (R6.3) — no new function; verify a no-entry host denies
  framing (`'none'`).
- [ ] 3.3 `terraform plan -out=tf.plan`, READ it: confirm it ONLY ADDS the IAM and does NOT force-replace
  the `public_pages` distribution / bucket / KVS (a replacement there is a STOP). Apply the saved plan in
  the SAME release window as the code (steering 43); record the plan summary on the PR. (Owner-run apply.)

### Phase 4 — Frontend: field-modal authoring (R1, R2) — ~2.5 days · ACCOUNT-AGNOSTIC (parallel to the migration)

- [x] 4.1 Replace the bespoke `ApplicationFieldList` toggle-list + buried panel: clicking a field opens a
  MODAL built on `MembersFieldModal`'s engine (`buildField`/`resolveWriteTarget`/`upsertField`), with an
  application-form attributes section shown only when a form is in scope (R1.1/R1.2).
- [x] 4.2 Enum-subset picker SOURCE adapts to field kind (reference→catalog, scope→dimension,
  enum→own options) and renders ONLY for choice-bearing fields — never a plain string field (R1.3).
- [x] 4.3 All attributes write onto the ONE `field_overlay`, commit via the SAME
  `PUT /members/config/fields` (one object, one save); reuse `upsertField`, add no forked overlay code;
  the UI reasons in groups+fields only (R1.4, R2.1/R2.2).
- [x] 4.4 Tests (`frontend/`): modal writes the four attributes correctly (subset only on choice fields;
  required-no-relax for platform-required; known format tokens); one-object/one-save; axe over builder +
  modal. Fixtures use the bare `key` + `group` server shape (R2.3).

### Phase 5 — Frontend: in-browser preview + retire the server endpoint (R3) — ~1.5 days · ACCOUNT-AGNOSTIC

- [x] 5.1 Render the preview IN-BROWSER: feed the WORKING draft to `ApplicationFormRenderer`; a pure
  client filter reproduces `get_public_field_config`'s applicant-facing selection (R3.1).
- [x] 5.2 DELETE `POST /members/application-preview` (SAM route + `_dispatch`) and its frontend debounce +
  caller (R3.2). Remove spec 11 tasks 1.4's endpoint; update/remove its tests.
- [x] 5.3 Pin client-filter parity to the server `get_public_field_config` via a shared fixture test, so
  retiring the endpoint introduces no drift (R3.2).
- [x] 5.4 Tests (`frontend/`): preview reflects unsaved edits live; parity fixture matches; the native
  landing-page block (E4a) and the preview share the ONE renderer code path (R8.2).

### Phase 6 — Frontend: slug surface + embedding carry-forward (R4, R8) — ~1 day · ACCOUNT-AGNOSTIC

- [x] 6.1 Display the resolved public URL (`{slug}.jabaki.nl`) + an "open live form" link once a slug is
  set; when no slug, state the form has no public address yet (R4.4 / R3.3). Author the slug via the SAM
  config-write (Phase 1) — a NAME ≠ tenant is allowed.
- [x] 6.2 **Explicit "Publish" button** (OQ1=option 1): a deliberate control that calls
  `POST /members/application-form/publish` (Phase 2). Saving the draft NEVER republishes — surface the
  save/publish distinction in the UI (e.g. a "draft has unpublished changes" hint). Disable/explain
  Publish when readiness fails (slug + certified sender + ≥1 on-form field, R5.4 / spec 11 R6). The
  live-publish CALL is dormant until the migration (0.1) + IAM (Phase 3) land; the button + readiness
  wiring are account-agnostic and can land now.
- [x] 6.3 Keep the external-embed snippet + `application_embed_origins` authoring + `postMessage` resize
  (spec 11 E4b) consistent with the published artifact (R8.1); verify inside a Google Sites iframe.
- [x] 6.4 Tests (`frontend/`): slug display/link states; the Publish button calls the publish route and a
  plain save does NOT (save ≠ publish); Publish disabled/explained when not ready; embed snippet + resize
  behavior.

### Phase 7 — CI footgun note + end-to-end verification + promote (R7.4) — ~0.5 day

- [x] 7.1 Remove `PUBLIC_TENANT_SLUG_MAP` from `template.yaml`/`samconfig.toml` AFTER the resolver swap is
  live (swap first, delete second — R7.3). Add a note/guard on `deploy-sam-members.yml` that a bare
  `--parameter-overrides` replaces the whole samconfig param set (D7 / R7.4) — flag the latent risk for
  other params; recommend passing all params / a param file as a small CI follow-up.
- [ ] 7.2 Verify end-to-end on live TEST (steering 43): publish `hdcn-application-form`, load
  `hdcn-application-form.jabaki.nl`, submit an application — exercised live, not just units.
- [ ] 7.3 Promote `test → main` via ONE reviewed PR (a merge to `main` IS a production deploy); confirm
  the SAM deploy settles and the Terraform IAM is applied in the same window (owner-run). Update end-user
  docs + mark the superseded spec 11 sections as retired-by-spec-12 in the SAME change (steering 40 DoD).

---

## Task Dependency Graph

Waves execute in order; tasks within a wave may run in parallel. 0.2/0.3/0.4 are resolved decisions
(no work). The account-agnostic tasks (Phases 1, 4, 5, 6) do NOT wait on the Phase-0.1 migration; the
migration-gated tasks (Phase 2 live-write, Phase 3 IAM, Phase 7 live verify/promote) do.

The graph is ordered so the **account-agnostic track (waves 0–5) runs FIRST and is NOT gated by the
owner-run migration.** Task 0.1 (the migration) is an OWNER-RUN prerequisite — it is deliberately placed
in its own gate wave (wave 6) that sits BETWEEN the agent-runnable account-agnostic work and the
migration-gated tail, so the scheduler never blocks the 85% behind it. 0.2/0.3/0.4 are resolved
decisions (no work) and are omitted from the graph.

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "4.2"] },
    { "id": 2, "tasks": ["1.4", "4.3"] },
    { "id": 3, "tasks": ["1.5", "4.4", "5.1", "5.2", "6.1", "6.2", "6.3"] },
    { "id": 4, "tasks": ["5.3", "6.4", "7.1"] },
    { "id": 5, "tasks": ["5.4", "2.1"] },
    { "id": 6, "tasks": ["0.1"] },
    { "id": 7, "tasks": ["0.2a"] },
    { "id": 8, "tasks": ["2.2", "2.3"] },
    { "id": 9, "tasks": ["2.4", "3.1"] },
    { "id": 10, "tasks": ["3.2", "3.3"] },
    { "id": 11, "tasks": ["7.2"] },
    { "id": 12, "tasks": ["7.3"] }
  ]
}
```

Reading the graph:
- **Waves 0–5 = the account-agnostic track (agent-runnable now).** Phases 1/4/5/6 plus Phase 2's
  code-only scaffold (2.1, route + readiness gate, live-write path dormant) and 7.1 (param removal, after
  the 1.4 resolver swap). None of this touches the personal/nonprofit hosting accounts, so none of it
  waits on the migration.
- **Wave 6 = `0.1`, the OWNER-RUN migration gate.** `jabaki-hosting-migration-to-nonprofit` is a
  cross-account cutover of live production hosting (S3 + `*.jabaki.nl` CloudFront + KVS). Per steering 43
  this is **owner-run only, never agent-run**. The task runner MUST stop here and hand off to the owner;
  it is intentionally isolated in its own wave so it blocks ONLY the migration-dependent tail below, not
  the account-agnostic work above.
- **Waves 7–12 = the migration-gated tail** (agent-runnable AFTER the owner completes wave 6): 0.2a
  re-verifies the landing marker on the nonprofit bucket; 2.2/2.3/2.4 wire the live publish + rename;
  3.x applies the same-account IAM (its `terraform apply` is itself owner-run, steering 43); 7.2/7.3 do
  the live-TEST verify and the `test→main` promotion (a production deploy).

- **Phase 0.1 (the nonprofit hosting migration) is a hard prerequisite of Phase 2 (live publish) and
  Phase 3 (IAM) ONLY.** The account-agnostic work (Phases 1, 4, 5, 6) proceeds in parallel and does not
  wait on it — the point of option a's split: ship ~85% of spec 12 regardless, gate only the live
  publish + IAM on the cutover.
- Task 0.4 (OQ4 — slug reverse-lookup mechanism) is RESOLVED (`_slugs/{slug}` bucket marker), so tasks
  1.2/1.3 are unblocked and account-agnostic.
- Phase 1 before Phase 2 (publish needs the slug) and before Phase 5's parity fixture.
- Phase 3 (IAM) + Phase 2's live-write path both need Phase 0.1 cut over; Phase 2's code+tests can land
  first with the write path dormant.
- Phase 5's endpoint deletion and the in-browser preview land together (don't delete before the browser
  path works).
- Phase 7.1's param removal only AFTER Phase 1.4's resolver swap is live.

## Notes

**Definition of Done (steering 40):**
- All paired tests green on both planes; live TEST exercised (not just units).
- No runtime SAM↔Flask call introduced; serving uses the existing `*.jabaki.nl` infra; slug is data on
  `config#fields`; SAM publishes; the slug→tenant reverse lookup is the `_slugs/{slug}` bucket marker
  (no DynamoDB change).
- The retired spec 11 pieces (toggle-list/panel, `POST /members/application-preview`,
  `PUBLIC_TENANT_SLUG_MAP`) are removed and unreferenced; spec 11 is annotated as superseded where this
  spec replaces it.
- Terraform IAM applied plan-first, same window, reviewed in the same PR; no `tfstate` committed; no
  force-replace of a stateful shared resource.

**Parked / out of this spec:**
- The `*.{tenant-id}.jabaki.nl` host addressing model (R4.6) — owned by
  `jabaki-hosting-migration-to-nonprofit`; it later removes the `_slugs/{slug}` lookup entirely.
- Server-owned overlay storage placement (R2.2) — deferred; the builder reuses `upsertField`.

**Resolved decisions (traceability):** OQ1 = explicit `POST …/publish` route; OQ2 = tenant-scoped
uniqueness (no global registry); OQ3 = nonprofit, migration-first; OQ4 = `_slugs/{slug}` bucket marker.
