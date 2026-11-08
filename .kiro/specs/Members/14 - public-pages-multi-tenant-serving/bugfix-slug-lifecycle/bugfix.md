# Bugfix Requirements Document

**Bugfix — SAM-plane slug lifecycle (author → display → publish) is broken end to end**

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving` (R1.2, R2.1, R2.3, R4).

## Introduction

Spec 14 requires each SAM page producer to OWN its slug on its own `tenant_id`-partitioned record
(R1.2), author a slug that is validated at claim time against the tenant's public prefix (R2.1,
R2.3), and claim the shared `_slugs/{slug}` marker as the one cross-plane uniqueness gate (R4).
Several spec-14 tasks are marked complete, but the slug lifecycle does not satisfy those
requirements: a tenant admin on the SAM plane has **no way to author/set/change the form slug**,
and the SAM admin screen **displays a slug sourced from the Flask landing plane** instead of the
SAM `config#fields.slug`.

The two defects were confirmed this session against real TEST data and the current code; they are
fixed together as ONE bug condition because they are the same broken lifecycle:

- The admin screen shows a Flask-plane address (`https://hdcn-application-form.jabaki.nl/apply`)
  for tenant `h-dcn`, whose SAM `config#fields.slug` is actually `NULL` (verified in
  `test_governance_projection`, `tenant_id=h-dcn`, `sk=config#fields`:
  `slug = {"NULL": true}`). A SAM screen must reflect SAM state — "no public address yet" when the
  SAM slug is absent — never a Flask-plane slug (a cross-plane read; spec 14 R3.2, steering 35
  rule 5a, steering 39).
- There is no client-reachable SAM write path that authors `config#fields.slug` and claims the
  `_slugs/{slug}` marker. The backend author code exists but is unreachable (see Hypothesis in the
  design): `config#fields` is excluded from the generic whole-object config-write door, and the
  `config#fields` Change-Op route has no slug op. So the publish readiness gate is permanently
  stuck at `no_slug` with no SAM way to clear it.

Impact: no SAM tenant can take an application form live through the SAM plane. The capability
spec 14 R2/R4 promised (author a prefixed slug, claim it, display it, then publish) is absent for
new tenants, and the slug shown to admins is misleading.

**Scope boundary (inherited from spec 14 Scope decision, 2026-11-01):** the Flask landing module
is NOT touched — no change to `landing_page_service.py`, `tenant_slugs`, or
`/api/landing/slug`. The fix is SAM-plane backend + the SAM admin frontend ONLY. Old OQ1/OQ2 stay
withdrawn.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a tenant admin opens the SAM Application Form Builder for a tenant whose SAM
`config#fields.slug` is absent/`NULL` (e.g. `h-dcn`) THEN the screen displays a public address
sourced from the Flask landing plane (via `GET /api/landing/slug`) instead of reflecting the
absent SAM slug.

1.2 WHEN the SAM `config#fields.slug` differs from, or is unset relative to, the Flask landing
slug THEN the displayed public address and the Publish-readiness "slug present" signal are computed
from the Flask-plane slug, so the SAM screen can show a slug that the SAM publish gate does not
recognize (the display and the authoritative SAM state disagree).

1.3 WHEN a tenant admin wants to set or change the SAM application-form slug THEN there is no SAM
control or SAM client-reachable endpoint to do so (no author/claim/change action exists in the SAM
admin UI or the SAM API), so the slug cannot be authored on the SAM plane.

1.4 WHEN a tenant has no SAM slug and the admin attempts to publish THEN publish is refused at the
readiness gate with `reason: no_slug` (HTTP 409) and there is no SAM path to clear that
precondition, leaving publish permanently unreachable for that tenant.

### Expected Behavior (Correct)

2.1 WHEN a tenant admin opens the SAM Application Form Builder for a tenant whose SAM
`config#fields.slug` is absent/`NULL` THEN the screen SHALL reflect SAM state and show "no public
address yet" (not set), and SHALL NOT display a Flask landing-plane slug.

2.2 WHEN the SAM `config#fields.slug` is present THEN the displayed public address and the
Publish-readiness "slug present" signal SHALL be computed from the SAM `config#fields.slug` (the
SAM source of truth), so the display and the authoritative SAM publish gate always agree.

2.3 WHEN a tenant admin sets or changes the SAM application-form slug through the SAM admin control
THEN the system SHALL validate the slug at author time with the shared format/reserved rules and
the tenant-prefix-ownership rule (R2.3), claim the shared `_slugs/{slug}` marker for the owning
tenant (R4), and persist the slug on `config#fields.slug` via the sanctioned SAM write path (an
identity-addressed Change-Op, not a whole-record replace; steering 39) — all gated by
`members:admin`.

2.4 WHEN a tenant has authored a valid SAM slug AND the other publish preconditions are met THEN
publish SHALL be reachable (the `no_slug` refusal SHALL no longer apply), with the authored slug as
the form's public address.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the SAM `config#fields.slug` is already present and valid THEN the system SHALL CONTINUE
TO read it via `MembersProjectionReader.get_form_slug` and gate/claim publish exactly as today
(the backend publish gate and `_slugs/{slug}` claim behavior are unchanged for an already-slugged
tenant).

3.2 WHEN any Flask landing-plane operation runs (`/api/landing/slug`, `landing_page_service.py`,
`tenant_slugs`, the 7 live landing tenants' slugs/domains/artifacts) THEN the system SHALL CONTINUE
TO behave exactly as before — the landing module is not modified by this fix (spec 14 Scope
decision; R1.4/R1.5).

3.3 WHEN a tenant admin edits non-slug application-form configuration (field toggles, groups,
application attributes via the `config#fields` Change-Op path; mail config via `config#mail`) THEN
the system SHALL CONTINUE TO save that configuration unchanged — the slug author path is additive
and SHALL NOT alter existing `config#fields` Change-Op or `config#mail` write behavior.

3.4 WHEN a `config#fields` row carries existing publish-state metadata (`published_at` /
`published_version`) THEN the system SHALL CONTINUE TO preserve it — authoring/changing the slug
SHALL NOT fabricate or wipe publish-state owned by the publish path.
