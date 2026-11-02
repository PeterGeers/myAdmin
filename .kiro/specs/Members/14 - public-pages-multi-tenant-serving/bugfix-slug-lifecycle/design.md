# SAM Slug Lifecycle Bugfix Design

## Overview

The SAM-plane application-form slug lifecycle (author → display → publish) is broken end to end.
Two defects combine into one broken lifecycle and are fixed together:

- **A (display):** the SAM Application Form Builder reads the slug from the Flask landing plane
  (`GET /api/landing/slug`) and uses it both for the displayed public URL and the Publish
  readiness signal. It ignores the SAM `config#fields.slug` that the module already serves. For a
  tenant with no SAM slug (`h-dcn`, verified `config#fields.slug = NULL`), it shows a Flask-plane
  address rather than "not set". This is a cross-plane read — an autonomy violation (R3.2;
  steering 35 rule 5a; steering 39).
- **B (author/claim/change):** no client-reachable SAM write authors `config#fields.slug` and
  claims `_slugs/{slug}`. The publish path claims the marker only once the slug already exists, and
  the readiness gate refuses `no_slug`; with no author path the gate can never be cleared from the
  SAM plane.

The fix adds a SAM-plane author/claim slug capability (`members:admin`) that validates the slug
(format/reserved + prefix-ownership, R2.3), claims the `_slugs/{slug}` marker (R4), and persists
`config#fields.slug` via the sanctioned SAM Change-Op write path (steering 39); it also fixes the
SAM admin display/readiness to source the slug from SAM state, never from Flask.

The strategy is REUSE, not re-implementation: the validation authority
(`sam/members/domain/form_slug.py`), the marker store claim/rename
(`sam/members/repository/slug_marker_store.py`), and the publish gate's slug read
(`MembersProjectionReader.get_form_slug`) already exist and are correct. The missing pieces are a
client-reachable WRITE path on the SAM plane and a frontend display/readiness that reads SAM
state.

### What EXISTS vs what is MISSING (verified this session)

Backend — EXISTS and correct:

- `form_slug.validate_slug_format` / `validate_slug_prefix_ownership` — the SAM slug format +
  SEC-4 prefix-ownership authority (R2.3/R2.5). Reused as-is.
- `slug_marker_store.S3SlugMarkerStore.claim` / `rename` / `release` / `resolve` — atomic
  `_slugs/{slug}` claim with idempotent same-owner re-publish and clobber backstop (R4); `rename`
  claims-new-before-release-old (R4.6). Reused as-is.
- `MembersProjectionReader.get_form_slug` / `get_public_prefix` — SAM-plane forward reads of the
  slug and the tenant's own public prefix. Reused as-is.
- `ApplicationPublishService` (publish gate) — correctly reads `get_form_slug`, raises
  `PublishNotReady(NO_SLUG)` → 409 `reason: no_slug`. Unchanged.
- `config_write_service._author_form_slug` — ALREADY validates a body `slug` with
  `form_slug.validate_slug_format` and persists `config#fields.slug` (carrying `published_*`
  through). **But it is UNREACHABLE** (see Hypothesis): `config#fields` is excluded from the
  generic whole-object config-write door, so no client request ever reaches it.

Backend — MISSING:

- A client-reachable SAM route/op that (a) format/reserved + prefix-ownership validates a slug at
  author time, (b) claims `_slugs/{slug}`, and (c) persists `config#fields.slug` by identity
  Change-Op. The `config#fields` Change-Op authority (`ConfigFieldsCrudService`) has NO slug op;
  the publish path claims the marker but only for an already-stored slug.
- Rename/change plumbing wired to a client action (the marker-store `rename` exists but nothing
  client-reachable calls it for the form slug).

Frontend — EXISTS:

- `members.ts` overlay type carries `slug?: string | null` (the SAM `config#fields.slug`, served on
  the field-config read). Available but unused for display.
- `applicationReadiness.computeReadiness(fieldConfig, overlay, slug)` — a pure readiness helper that
  takes whatever slug is passed in.

Frontend — WRONG / MISSING:

- `ApplicationFormBuilder.tsx` imports `getSlug` from `landingPageApi` (`GET /api/landing/slug`,
  Flask) and seeds `shell.slug` + readiness from it — the cross-plane read (defect A). The SAM
  `config#fields.slug` (available as `cfg.slug`/overlay) is not read for display.
- No SAM admin control to set/change the slug (defect B). Today the builder "points at the Landing
  Page editor to change it" — a Flask-plane escape hatch that violates SAM autonomy.

### Where the frontend reads the slug TODAY

`frontend/src/components/TenantAdmin/MembersConfig/ApplicationFormBuilder.tsx`, in `load()`:
`slug = (await getSlug()).data?.slug ?? null;` where `getSlug` is
`frontend/src/services/landingPageApi.ts` → Flask `GET /api/landing/slug`. That `slug` seeds
`shell` (the displayed URL) and `computeReadiness(fieldConfig, overlay, shell.slug)`. The SAM
`config#fields.slug` served on the field-config read is not used here.

## Glossary

- **Bug_Condition (C)**: the condition that triggers the bug — a SAM slug-lifecycle interaction
  (author, display, or publish-reachability) where the SAM plane fails to source/author the slug
  from its own `config#fields` state and instead has no author path (B) or reads the Flask-plane
  slug (A).
- **Property (P)**: the desired behavior — the SAM plane authors/claims/persists the slug on its
  own record and displays/gates on the SAM `config#fields.slug` only.
- **Preservation**: an already-slugged SAM tenant's publish gate + claim, all Flask landing-plane
  behavior, and all non-slug `config#fields`/`config#mail` writes stay unchanged.
- **SAM slug source of truth**: `config#fields.slug` (DynamoDB `governance_projection`,
  `tenant_id`-scoped) PLUS the shared `_slugs/{slug}` S3 marker. NOT Flask `tenant_slugs`, NOT the
  Flask landing slug.
- **`get_form_slug`**: `MembersProjectionReader.get_form_slug(tenant_id)` — the SAM forward read of
  `config#fields.slug` (`None` when absent).
- **`_author_form_slug`**: the existing (currently unreachable) `config_write_service` step that
  format-validates and persists `config#fields.slug`.

## Bug Details

### Bug Condition

The bug manifests on any SAM slug-lifecycle interaction for a tenant on the SAM plane: the SAM
admin surface either cannot author a slug at all (no write path reaches `config#fields.slug` +
`_slugs/{slug}`), or it sources the displayed/readiness slug from the Flask plane instead of the
SAM `config#fields.slug`. The two facets share one root: the SAM plane has no reachable slug WRITE
and does not treat `config#fields.slug` as the display/readiness source.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type SlugLifecycleInteraction
         { facet: AUTHOR | DISPLAY | PUBLISH_REACHABILITY,
           tenant_id: str,
           sam_slug: str | None,          # config#fields.slug (SAM truth)
           flask_landing_slug: str | None } # /api/landing/slug (other plane)
  OUTPUT: boolean

  RETURN
    // A — DISPLAY/readiness sources the slug cross-plane instead of from SAM state
    (input.facet = DISPLAY
       AND displayed_or_readiness_slug(input) == input.flask_landing_slug
       AND displayed_or_readiness_slug(input) != input.sam_slug)
    OR
    // B — no SAM client-reachable path authors+claims+persists the slug
    (input.facet = AUTHOR
       AND NOT exists_sam_author_path_that(validates_prefix AND claims_marker AND persists_config_fields_slug))
    OR
    // B consequence — a prefix-less / no-SAM-slug tenant can never reach publish from the SAM plane
    (input.facet = PUBLISH_REACHABILITY
       AND input.sam_slug IS None
       AND NOT exists_sam_author_path())
END FUNCTION
```

### Examples

- `h-dcn` (verified): `config#fields.slug = NULL`, yet the builder displays
  `https://hdcn-application-form.jabaki.nl/apply` (Flask landing slug). Expected: "no public
  address yet". (facet=DISPLAY)
- `h-dcn`: admin wants to set the SAM slug to `h-dcn` or `h-dcn-aanmelden` — there is no SAM
  control or endpoint to do it. (facet=AUTHOR)
- `h-dcn`: admin clicks Publish → 409 `reason: no_slug`, and no SAM path exists to clear it.
  (facet=PUBLISH_REACHABILITY)
- A tenant whose SAM slug is already `foo-apply`: the publish gate reads it and claims
  `_slugs/foo-apply` correctly — NOT a bug (this is the preserved path).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- The publish readiness gate + `_slugs/{slug}` claim for an already-slugged SAM tenant
  (`ApplicationPublishService`, `get_form_slug`, `S3SlugMarkerStore.claim`) behave exactly as
  today.
- All Flask landing-plane behavior: `/api/landing/slug`, `landing_page_service.py`, `tenant_slugs`,
  the 7 live landing tenants' slugs/domains/artifacts — untouched (spec 14 Scope decision).
- All non-slug `config#fields` Change-Op writes (`set_field` / `set_field_application` /
  `reset_field` / `delete_field` / `set_group` / `delete_group`) and `config#mail` writes.
- Existing `config#fields` publish-state metadata (`published_at` / `published_version`) is
  preserved across a slug author/change.

**Scope:**

All interactions that do NOT involve authoring/displaying/gating the SAM form slug are completely
unaffected by this fix. This includes every Flask-plane operation, every non-slug config write, and
the already-correct backend publish gate.

The actual expected correct behavior for buggy inputs is defined in Correctness Properties
(Property 1).

## Hypothesized Root Cause

Based on the verified code, the most likely causes are:

1. **No client-reachable SAM slug WRITE path (primary, defect B).** `config_write_service`
   `_author_form_slug` CAN persist `config#fields.slug`, but `_dispatch_services._WRITABLE_CONFIG_IDS
   = {scope, mail}` EXCLUDES `fields`, and the generic `PUT /members/config/{configId}` route
   rejects `configId=fields` (config#fields is Change-Op-only, spec 03 Task 7.1). The Change-Op
   route (`write_config_fields` → `ConfigFieldsCrudService.apply_ops`) has NO slug op. So the one
   piece of code that writes the slug is unreachable from any client, and nothing claims the marker
   at author time.

2. **Frontend sources the slug cross-plane (primary, defect A).** `ApplicationFormBuilder.tsx`
   calls `getSlug()` (Flask `/api/landing/slug`) and feeds that into both the displayed URL
   (`shell.slug`) and `computeReadiness`. It never reads the SAM `config#fields.slug` (available on
   the field-config response as `cfg.slug` / overlay). So the SAM screen reflects Flask state.

3. **Slug-author was never delivered as a first-class action.** Spec 14 Task 8.1 wired the marker
   claim INTO publish (claim-at-publish), which assumes the slug already exists on
   `config#fields`. The explicit "author/set/change the slug" action that would populate
   `config#fields.slug` in the first place was never built on the SAM plane — the frontend instead
   "points at the Landing Page editor", a cross-plane escape hatch.

4. **Rename path exists but is unwired.** `S3SlugMarkerStore.rename` (claim-new-before-release-old,
   R4.6) exists but no client action calls it for the form slug, so change/rename is unavailable.

## Correctness Properties

Property 1: Bug Condition - SAM slug lifecycle authors + displays + gates from SAM state

_For any_ SAM slug-lifecycle interaction where the bug condition holds (isBugCondition returns
true), the fixed system SHALL: for an AUTHOR interaction, validate the slug (format/reserved then
tenant-prefix-ownership, R2.3), claim the shared `_slugs/{slug}` marker for the owning tenant (R4),
and persist `config#fields.slug` via an identity-addressed Change-Op (never a whole-record
replace); for a DISPLAY interaction, source the displayed address and the "slug present" readiness
signal from the SAM `config#fields.slug` only (showing "not set" when absent), never from the Flask
landing slug; and for a PUBLISH_REACHABILITY interaction, make publish reachable once a valid SAM
slug has been authored (the `no_slug` refusal no longer applies).

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - already-slugged publish, Flask plane, non-slug writes unchanged

_For any_ input where the bug condition does NOT hold (isBugCondition returns false) — an
already-slugged SAM tenant's publish gate/claim, any Flask landing-plane operation, any non-slug
`config#fields`/`config#mail` write, or a `config#fields` row's existing `published_*` metadata —
the fixed system SHALL produce the same result as the original system, preserving the current
publish gate + marker claim, the untouched Flask landing module, the unchanged non-slug config
writes, and the carried-through publish-state metadata.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming the root-cause analysis is correct, the minimal fix honoring the autonomy/layering
constraints (steering 35 rule 5a; steering 39) is:

**1. Backend — add a SAM slug-author Change-Op (domain + route + dispatch).**

- **File**: `sam/members/domain/config_fields_crud_service.py`
  - Add a `set_form_slug(tenant_id, slug | None, *, client_op_id=None)` (and a `rename`/change
    variant if the marker-store `rename` makes it low-cost — see change 2) that:
    1. REUSES `form_slug.validate_slug_format` (format/reserved, R2.3) — reject malformed fail-loud;
    2. REUSES `form_slug.validate_slug_prefix_ownership` with the tenant's own prefix from
       `get_public_prefix` (SEC-4, R2.3) — grandfather an already-owned slug;
    3. claims `_slugs/{slug}` via the injected `S3SlugMarkerStore.claim` (R4) — idempotent
       same-owner, clobber backstop; and
    4. emits a single identity Change-Op `SET slug` (an explicit `null` CLEARS it) on
       `config#fields` — reusing the existing version-conditional `apply_ops` path, NOT a
       whole-record replace (steering 39). Carry `published_*` through (never author them here).
  - The marker store + prefix reader are constructor-injected (dependency inversion; domain stays
    boto3-free, steering 35/39). Tests inject in-memory fakes.
- **File**: `sam/members/handler/routes.py`
  - Add a `members:admin`-gated route to author/change the slug (e.g. a dedicated
    `POST /members/application-form/slug` carrying `{slug}` in the body, or a new slug op recognized
    by the `write_config_fields` Change-Op dispatch). `tenant_id` resolved from the verified token,
    never the body (steering 39).
- **File**: `sam/members/handler/_dispatch_services.py`
  - Wire the new route to the `ConfigFieldsCrudService` slug op (lazy, warm-reused, fakes in tests),
    injecting the real `S3SlugMarkerStore` + projection reader. Map `PublishSlugRejected`-style
    validation to 422/400 and a foreign-owner `SlugTaken` to a caller-safe 409 (steering 30/37;
    never `str(e)`).

  NOTE: the existing `config_write_service._author_form_slug` persists the slug but does NOT claim
  the marker and is unreachable; the chosen approach routes authoring through the Change-Op
  authority (identity op) so a single sanctioned write path owns author + claim together. Whether to
  retire or keep `_author_form_slug` is a design decision to confirm at review (it may remain as the
  internal persistence primitive the new op calls, or be superseded).

**2. Backend — rename/change support.**

- If the existing `S3SlugMarkerStore.rename` (claim-new-before-release-old, R4.6) makes a change
  low-cost, the `set_form_slug` op handles a change by rename (claim new marker, persist new
  `config#fields.slug`, release old marker) in that safe order. Otherwise, keep the first increment
  to author + persist and record rename as a follow-up (noted here per the workflow).

**3. Frontend — fix display + readiness to read SAM state; add the author control.**

- **File**: `frontend/src/components/TenantAdmin/MembersConfig/ApplicationFormBuilder.tsx`
  - Remove the `getSlug` (Flask `landingPageApi`) import + call. Source the slug from the SAM
    field-config response (`cfg.slug` / overlay `slug`) so `shell.slug` and
    `computeReadiness(fieldConfig, overlay, samSlug)` reflect SAM state; show "no public address
    yet" when absent (R2.1/R2.2).
  - Add a `members:admin` control to set/change the public address, calling the new SAM slug-author
    endpoint (via a SAM `membersConfigApi`/`members/...` client, NOT `landingPageApi`), then
    re-loading so the display/readiness reflect the persisted SAM slug.
- **File**: a SAM frontend API client (e.g. `frontend/src/services/members/membersConfigApi.ts`)
  - Add the `setApplicationFormSlug(slug)` call targeting the new SAM route. Do NOT reuse
    `landingPageApi`.

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples that demonstrate the bug on the UNFIXED code, then verify
the fix authors/displays/gates from SAM state and preserves everything else. Per steering 39, the
backend round-trip is proven against the REAL `config#fields` row (`h-dcn`), not a hand-built
fixture.

### Exploratory Bug Condition Checking

**Goal**: surface counterexamples that demonstrate the bug BEFORE implementing the fix; confirm or
refute the root-cause analysis.

**Test Plan**: write tests that exercise each facet on the UNFIXED code.

**Test Cases**:
1. **No SAM author path (backend)**: assert there is no client-reachable SAM write that persists
   `config#fields.slug` + claims `_slugs/{slug}` — e.g. a dispatch/route test showing
   `configId=fields` is rejected by the generic write and `ConfigFieldsCrudService` exposes no slug
   op (will fail/behave-as-buggy on unfixed code). (facet=AUTHOR)
2. **Publish unreachable (backend)**: for a tenant with `config#fields.slug = None`, assert publish
   raises `PublishNotReady(NO_SLUG)` and no SAM path clears it (reproduces the dead-end).
   (facet=PUBLISH_REACHABILITY)
3. **Cross-plane display (frontend)**: render the builder with SAM `cfg.slug = null` and a non-null
   Flask `getSlug()` and assert it CURRENTLY shows the Flask slug / readiness `slugPresent=true`
   (the buggy behavior) — this is the counterexample the fix must invert. (facet=DISPLAY)

**Expected Counterexamples**:
- Backend: no reachable write authors the slug; publish stays `no_slug`.
- Frontend: the displayed address + readiness derive from the Flask slug while SAM slug is absent.

### Fix Checking

**Goal**: verify that for all inputs where the bug condition holds, the fixed system produces the
expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedSystem(input)
  ASSERT expectedBehavior(result)
  // AUTHOR  -> slug validated (format+prefix), _slugs/{slug} claimed, config#fields.slug persisted via Change-Op
  // DISPLAY -> address + readiness sourced from config#fields.slug; "not set" when absent; never Flask slug
  // PUBLISH -> publish reachable once a valid SAM slug is authored
END FOR
```

### Preservation Checking

**Goal**: verify that for all inputs where the bug condition does NOT hold, the fixed system
produces the same result as the original.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalSystem(input) = fixedSystem(input)
  // already-slugged publish gate + claim; Flask landing ops; non-slug config writes; published_* metadata
END FOR
```

**Testing Approach**: observe behavior on the UNFIXED code for non-bug inputs, then write
property-based tests capturing it. Property-based testing is recommended because preservation is a
universal property across many non-buggy inputs (any already-valid slug, any non-slug config write).

**Test Plan**: observe on the UNFIXED code, then assert unchanged after the fix.

**Test Cases**:
1. **Already-slugged publish**: a tenant with a valid stored slug publishes/claims identically
   before and after.
2. **Non-slug config writes**: a `set_field_application` / `config#mail` write round-trips
   unchanged.
3. **Publish-state preservation**: authoring/changing the slug leaves `published_*` untouched (real
   `config#fields` round-trip, `h-dcn`).

### Unit Tests

- `ConfigFieldsCrudService` slug op: format/reserved rejection, prefix-ownership rejection,
  grandfathered re-author, foreign-owner conflict, clear-with-null, single-path Change-Op (no
  whole-record replace).
- Dispatch/route: `members:admin` gate; `tenant_id` from token not body; caller-safe error envelopes
  (422/400/409, no `str(e)`).
- Frontend `applicationReadiness` + builder: readiness/display from SAM slug; "not set" when absent;
  no `landingPageApi.getSlug` call.

### Property-Based Tests

- Property 1 (bug condition): for generated AUTHOR inputs, a valid prefixed slug is persisted +
  claimed and publish becomes reachable; for DISPLAY inputs, the address/readiness equals the SAM
  slug (or "not set"), never the Flask slug.
- Property 2 (preservation): for generated non-slug config writes and already-valid slugs, fixed ==
  original.

### Integration Tests

- Backend paired SAM pytest run (`python -m pytest -c sam/pytest.ini <paths> -q`) exercising the new
  slug op against a real `config#fields` round-trip (`h-dcn`): author → `get_form_slug` reads it back
  → publish gate no longer refuses `no_slug`.
- Frontend builder test: SAM-sourced display + the author control calling the SAM endpoint (not
  Flask), then re-render reflects the persisted SAM slug.
