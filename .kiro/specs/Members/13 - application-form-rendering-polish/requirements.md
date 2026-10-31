# Requirements — 13. Public application-form rendering polish

## Context

The PUBLIC member-application form renders (config-driven, accessible, spec 10/12) but round-1 of
this spec left three real defects, confirmed by loading the live `h-dcn` form (`findings.md`). This
round fixes those three root causes. It is still a PRESENTATION + BRANDING pass — it does not change
the field model semantics, submit contract, validation, consent, or the readiness gate.

> **Round-1 retrospective (why this round exists).** Three things were "done" against passing tests
> but wrong in reality — each a lesson baked into the requirements below:
>
> 1. **Group order was a FAILURE, not a scope gap.** The requirement already said "the order the
>    admin configured." The implementation ordered groups by `min(field.order)` — a GUESS — when the
>    real authored per-group `order` (Personal #10 … Administrative #60) lives in the server's
>    `functional_groups` catalog and simply was not propagated to the public form. Deriving an
>    authored sequence from field order is not acceptable; use the authored datum. (R2)
> 2. **Styling was over-engineered into a feature.** Round-1 ended "still heavy orange," and the
>    reaction was to propose a tenant A/B theme toggle. That was scope creep. The real ask is
>    narrow: the form must MATCH THE PUBLIC PAGE'S LIGHT STYLE (white surface, quiet neutral
>    inputs/selects, orange reserved for focus/accent) — NOT carry the admin app's saturated orange.
>    No tenant style toggle. (R3)
> 3. **Logo verified against MOCKS, broken in reality.** Tests injected `logoBaseUrl`, so they
>    never exercised the real base-URL resolution. In production the form mounts WITHOUT
>    `logoBaseUrl`, so `fetchPublicLogo` calls the wrong origin from the public-pages host and
>    silently gets null → no logo. Fix the origin resolution AND verify on the live page. (R5a)

## Hard constraints (must not regress)

- **HC1 — config-driven, not hand-coded.** The form renders WHATEVER the public field-config lists;
  no field/group is hard-coded. Grouping, ordering, layout, and styling stay generic over config.
- **HC2 — accessibility holds.** The axe gate + per-field `id`/`htmlFor`/`aria-*` wiring and the
  ARIA error summary keep passing. Multi-column stays a single logical reading/tab order with
  label↔control association. The lighter styling still meets WCAG contrast + visible focus.
- **HC3 — locale + `show_when` unchanged.** Label resolution (nl fallback), the locale selector,
  and conditional visibility behave exactly as today.
- **HC4 — controlled-component shape unchanged.** The renderer stays controlled (flat dotted-key
  `values` + `onChange`); the parent owns form state.
- **HC5 — resolved view, not raw shape (steering 39).** Any new datum the public read carries (the
  group catalog) is a RESOLVED domain view keyed by domain identity (bare group `key`), never the
  physical `config#fields` / `overrides` / dotted `{group}.{key}` layout. No raw-shape key crosses
  the API boundary.
- **HC6 — verify against REALITY, not mocks.** A rendering/branding fix is "done" only when
  confirmed on the running `h-dcn` page (and, for the server read, against the real `h-dcn` row —
  steering 39). Passing mock-injected tests is necessary but NOT sufficient (this is the round-1
  logo lesson).

## Requirements

### R1 — Fields sit in their functional group, groups are clearly sectioned
**As** an applicant, **I want** each field under its functional group with a clear heading, **so
that** the form reads as organized sections.
- R1.1 Every field renders inside its `functional_group` section (preserve).
- R1.2 Each group renders a readable heading resolving the AUTHORED group `label` from the
  propagated `functional_groups` catalog (R2.2) in the applicant locale (nl fallback, HC3); falls
  back to a presentable form of the group `key` when no catalog label exists. The `__default__`
  bucket renders with NO empty-legend artifact.
- R1.3 A group with no currently-visible field renders nothing (preserve).

### R2 — Groups AND fields follow their AUTHORED sequence (group `order` is real data)
**As** a tenant admin, **I want** groups and fields in the exact order I configured, **so that** the
public form matches the authored sequence used everywhere else in the product.
- R2.1 Fields within a group order by `(order, key)` (preserve).
- R2.2 GROUPS order by the AUTHORED per-group `order` from the tenant's `functional_groups` catalog
  (the `#10…#60` sequence) — NOT first appearance, NOT `min(field.order)`. The catalog (`key`,
  `label`, `order`) MUST be propagated from `get_public_field_config` onto the public field-config
  as a resolved view (HC5). Tiebreak on group `key`; a field whose group is absent from the catalog,
  and the `__default__` bucket, sort LAST (deterministic, surfaced-never-dropped).
- R2.3 Ordering stays a pure, testable transform. A unit test MUST cover the exact round-1 failure:
  with the h-dcn catalog, groups render Personal → Address → Membership → Motorcycle → Financial →
  Administrative (authored `order`), even though a `min(field.order)` derivation would reorder them.
- R2.4 PARITY: the in-browser builder preview filter (spec 12) that reproduces the public read
  orders groups by the SAME authored catalog `order`, so preview matches the live form.

### R3 — The form matches the public page's LIGHT style (not the admin orange)
**As** an applicant, **I want** the form to look like the clean public page it sits on, **so that**
it reads as a calm, branded form rather than a heavy-orange admin screen.
- R3.1 On the white public surface, inputs AND selects read at a QUIET, neutral weight (e.g. a light
  neutral border on white, black/dark text) — not a saturated orange fill. Selects and text inputs
  sit at the SAME visual weight.
- R3.2 Orange is RESERVED for focus and small accents (focus ring / active state), not the resting
  fill of every control. A visible focus ring remains (HC2).
- R3.3 The styling is applied UNIFORMLY to every select + input on the public form via a scoped
  style/variant at the renderer/page boundary — NOT a per-field one-off and NOT a change to the
  global app theme (the admin app stays orange).
- R3.4 The select keeps its chevron affordance; contrast + focus stay WCAG-adequate (HC2). "Not
  heavy orange, matches the page" is confirmed on the live h-dcn page (HC6), not just in tests.
- R3.5 (Explicitly NOT doing) No tenant A/B style toggle, no new theme-choice setting — the round-1
  two-style idea is dropped. One light style that matches the page.

### R4 — Responsive one-line + multi-column on wide, stacked on mobile
**As** an applicant, **I want** label+input on one line in ≥2 columns on desktop, single-column
label-above on mobile, **so that** the form is compact on large screens and usable on small ones.
- R4.1 Mobile (`base`): label above control, single column (delivered round 1 — preserve).
- R4.2 Desktop (`md`+): label beside control, ≥2 columns within a group (delivered — preserve).
- R4.3 Responsive via Chakra's system, no viewport sniffing; an intrinsically-wide field may span
  full width (delivered — preserve).
- R4.4 Single logical reading/tab order + label↔control association (HC2); error-summary anchors
  focus the right control. Re-verify the layout still holds after the R3 styling change.

### R5 — Tenant logo at the top of the form (preserve the round-1 delivery)
**As** an applicant, **I want** the tenant's logo at the top, **so that** the form is branded.
- R5.1 The logo renders at the TOP, above the heading/first group (delivered — preserve).
- R5.2 SOURCE is the ONE branding logo `branding.company_logo_s3_key`, resolved by
  `services/logo_resolver.py` as an inline data URI via the public read
  `GET /api/public/landing/<slug>/logo` — not `landing.json`, not landing-page-gated (delivered).
- R5.3 Accessible `alt`; absent logo → no broken-image placeholder (delivered — preserve).
- R5.4 Constrained + responsive size (delivered — preserve).

### R5a — The logo actually RENDERS on the live public form (round-1 defect fix)
**As** an applicant, **I want** the configured logo to actually appear on the real page, **so that**
branding is not silently dropped.
- R5a.1 ROOT CAUSE: the production mounts (`PublicApplicationFormRoute`, `ApplicationFormBlock`)
  render `ApplicationFormPage` WITHOUT `logoBaseUrl`, so `fetchPublicLogo` falls back to
  `API_BASE_URL` and calls the WRONG origin from the public-pages host (`<slug>.jabaki.nl`) → non-ok
  → graceful null → no logo. The logo endpoint is on the FLASK plane, not the public-pages origin.
- R5a.2 The logo read MUST resolve to the correct backend origin in every real mount (standalone
  `/apply` route, the landing-page `ApplicationFormBlock`, and the builder preview iframe) — e.g. an
  absolute, environment-correct base for the Flask public read, threaded through the mounts (or a
  single correct default), so a null logo means "no logo configured", never "wrong origin".
- R5a.3 `tenantName` SHOULD be threaded to the page so the logo `alt` is the tenant name, not the
  literal "logo", where the name is already available at the mount.
- R5a.4 VERIFY ON THE LIVE PAGE (HC6): load h-dcn (which HAS a `branding.company_logo_s3_key`) and
  confirm the logo renders; do not rely on mock-injected `logoBaseUrl` tests alone. The paired test
  must exercise the DEFAULT (production) origin resolution, not only an injected base.

## Out of scope
- Any change to the field model semantics, submit contract, validation, consent, or readiness gate.
  (The contract GAINS one additive, presentation-only datum: the resolved group catalog.)
- A tenant A/B style toggle or a style-authoring UI (explicitly dropped — R3.5).
- A new logo-UPLOAD surface; converging the fragmented logo configs
  (`tenant-branding-logo-single-source` backlog).

## Verification
- SAM unit tests for `get_public_field_config`: the resolved public view carries the group catalog
  (order + label), defaults safely, and never leaks raw `config#fields` shape (HC5). Prove against
  the REAL `h-dcn` row (steering 39), asserting the authored group order Personal→…→Administrative.
- Frontend unit test (vitest) for `groupFieldsByFunctionalGroup` ordering by the authored catalog —
  including the round-1 failure case (R2.3).
- Render tests: group headings with authored labels + authored order (R1/R2); inputs+selects read
  quiet/light, orange only on focus (R3); responsive layout holds after the styling change (R4);
  logo renders via the DEFAULT origin resolution + absent gracefully (R5/R5a).
- axe gate green under the lighter styling (HC2).
- Builder preview parity (R2.4).
- LIVE verification on h-dcn (HC6): group order = `#10…#60`; form reads light/not-heavy-orange;
  logo visible — screenshots before/after.
