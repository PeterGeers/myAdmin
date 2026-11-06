# Published Application Form Styling Bugfix Design

## Overview

Spec 15 built a SAM-owned Look_And_Feel_Capability — a Layer-2 CSS generator
(`sam/shared/page_styles/render_page_styles`), a stored `look_and_feel` slice on `config#fields`,
a publish-time resolve, and a React admin preview — and marked Req 5.2 (published form carries the
tenant's look-and-feel) and Req 7.1 (preview matches the published page) delivered. The plumbing
RUNS, but it produces styling the published application form's markup never consumes, renders no
logo and no body heading, and the admin preview's good looks come from an INDEPENDENT Chakra
renderer rather than from the shared CSS. So the published form shows no logo, no title/heading, a
single column at every width, and no brand colours on the form's own elements, while the preview
shows a colour-and-column-styled form — the exact divergence Req 7.1 promised would not happen.

This bugfix makes the published form GENUINELY carry the tenant's look-and-feel and makes the
preview reflect the same appearance, sequenced deliberately:

- **A — Reproduce:** failing bug-condition tests that assert the PRODUCED/baked HTML actually
  APPLIES the styling (brand colours on the form's own elements, multi-column collapsing layout,
  logo, heading) — not merely that a generator emits a string. This closes the false-parity gap
  that hid the bug. Plus a frontend test for R-B (stale editor).
- **B — Option 1, genuinely style the published form:** application-form-specific CSS (a
  collapsing multi-column grid, brand colours on the form's own heading/submit/focus) and a
  renderer that emits the logo + heading in the body — built as the SINGLE shared styling source.
- **C — R-A, new inputs:** add `logo`, `header_title`, and `columns` as new values-only
  Look_And_Feel_Settings attributes across all planes (steering 40).
- **D — R-B, no-reload editor:** make the `PUT /members/look-and-feel` edge return the resolved
  `{settings}` (the GET contract) so the client re-seed shows the authored value.
- **E — Keep both render paths, one shared style source:** the in-browser preview (immediate
  proof of a change, no round-trip) and the published HTML page are BOTH retained; the fix makes
  both derive the form's appearance from the SAME resolved style attributes, with parity verified
  on the APPLIED appearance (not a generator string). No single renderer, no iframe.

This document owns the grounded root-cause investigation and the fix approach. `tasks.md` owns the
all-planes + CI/CD delivery sequencing. Nothing here is implemented — the user reviews first.

> **Scope note — spec-authoring only.** This design changes no product code, tests, or fixtures.

## Glossary

- **Bug_Condition (C)**: A publish/render of an application form for a tenant whose resolved
  `Look_And_Feel_Settings` carry distinct values (and/or a logo / header title / column count),
  where the PRODUCED artifact fails to APPLY that styling to the form's own elements (no brand
  colours on the form, single column, no logo, no heading) — i.e. authored look-and-feel has no
  observable effect on the published form.
- **Property (P)**: The published artifact (and the preview) carries the authored look-and-feel —
  brand colours on the form's own heading/submit/focus, a multi-column layout that collapses to
  one column on small screens, the tenant logo, and the header/title — and changing a value
  produces a corresponding, observable change.
- **Preservation**: Everything the form and the capability already do correctly — the applicant
  submit contract, the field/group/consent/locale rendering and escaping, the existing
  seven-attribute Layer-2 contract and its cross-language parity, tenant isolation, the
  landing-page CSS classes, and the publish readiness/failure semantics.
- **F / F'**: The original (unfixed) / fixed functions — the publish render path
  (`ApplicationPublishService.publish` → `render_application_form_page` → `render_page_styles` +
  `build_form_body_html`), the Layer-2 generator, the `PUT /members/look-and-feel` edge, and the
  React preview/builder.
- **Layer 2 / `render_page_styles`**: The SAM-owned CSS generator in
  `sam/shared/page_styles/__init__.py` that turns `Look_And_Feel_Settings` values into
  `PageStyles(css_variables, page_css, font_links)`.
- **Published artifact**: The baked `index.html` the publish step renders for a slug.
- **Admin_Preview**: `ApplicationFormPreview.tsx` — the in-browser React render shown while
  authoring.

## Bug Details

### Bug Condition

The bug manifests whenever a tenant with authored look-and-feel values (distinct brand colours,
and/or a logo, header title, or multi-column choice) publishes or previews the application form:
the produced HTML does not APPLY that styling to the form's own elements. The capability's Layer-2
CSS targets landing-page classes the form markup never uses; the renderer emits no logo and no
body heading; and the preview's appearance comes from Chakra, not the shared CSS — so published and
preview diverge.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type { settings: Look_And_Feel_Settings, artifact: RenderedHTML }
  OUTPUT: boolean

  RETURN settingsDifferFromDefault(input.settings)        // distinct colours / logo / title / columns
         AND NOT artifactAppliesBrandColours(input.artifact)   // form heading/submit/focus not themed
         AND NOT artifactHasMultiColumnLayout(input.artifact)  // single column at all widths
         AND NOT artifactRendersLogo(input.artifact)           // no logo element
         AND NOT artifactRendersHeading(input.artifact)        // no visible body title/heading
END FUNCTION
```

A companion R-B bug condition (the stale editor):
```
FUNCTION isStaleEditorBugCondition(input)
  INPUT: input of type { setResult: PutLookAndFeelResponse }
  OUTPUT: boolean

  // The PUT edge returns the Change-Op write result, not a {settings} map
  RETURN input.setResult.settings IS UNDEFINED
         AND clientReseedsFrom(input.setResult.settings)   // setLookAndFeel(res.settings ?? {}) blanks the edit
END FUNCTION
```

### Examples

- A tenant sets `color_primary = #C01030`, publishes. Expected: the form's submit button /
  heading / input focus carry `#C01030`. Actual: the baked HTML's only `.application-form` rules
  set margins, grey `#ccc` input borders, and `#b42318` error red — the brand colour appears only
  in `:root` variables and in landing-page `.hero`/`.cta`/`.btn` rules the form never uses.
- A tenant publishes on a wide screen. Expected: field groups laid out in multiple columns,
  collapsing to one column below a small breakpoint. Actual: `<fieldset class="form-group">`
  stacks single-column at every width (the generated CSS defines no grid for the form groups).
- A tenant with a logo publishes. Expected: the logo `<img>` renders in the body. Actual: no logo
  — `build_form_body_html` emits no logo element and publish passes no `header_html`.
- A tenant with a form title publishes. Expected: a visible `<h1>`/heading. Actual: only a
  non-visible `<title>` browser-tab element exists.
- **Preview divergence:** for the same settings, `ApplicationFormPreview.tsx` shows a
  colour-and-column-styled form (Chakra `ApplicationFormRenderer`) while the published form does
  not — so the task-13.2 "parity fixture" is satisfied (both generators emit the same `page_css`
  STRING) yet the form is still unstyled, because that string never styles the form.
- **R-B:** a tenant changes `shadow_style` to `dramatic` in the editor; the control snaps back to
  the old value until the page is reloaded.

### Grounded Root-Cause Investigation

Confirmed by reading the shipped code:

1. **Layer-2 CSS targets the wrong classes** — `sam/shared/page_styles/__init__.py`
   `_build_page_css` emits colour/layout rules for landing-page classes (`.hero`, `.cta`, `.btn`,
   `.pricing-card`, `.gallery-grid-*`, `.faq-grid`, `.testimonial-*`, `.contact`, …). The only
   `.application-form` rules it emits set field margins, label weight, grey (`#ccc`) input
   borders, and error states — **no brand colours, no column grid**. The two brand colours
   (`color_primary`/`color_accent`) are inlined only into those landing-page rules; `:root`
   defines font/spacing/radius/shadow variables but **no colour variables**, so the form has
   nothing to reference even if it wanted to. Result: colours not applied to the form, and no grid
   → single column.

2. **Renderer emits no logo and no body heading** —
   `sam/members/domain/application_form_render.py` `build_form_body_html` renders
   `<main><form class="application-form">` with `<fieldset class="form-group">` / `.form-field`
   plus the locale/consent meta controls and the submit script. It emits **no logo `<img>` and no
   visible `<h1>`/title** (the `head_meta` `<title>` is browser-tab only). A `header_html` param
   exists and is emitted verbatim when supplied, but the publish step passes nothing.

3. **Preview looks good for the wrong reason** —
   `frontend/src/components/TenantAdmin/MembersConfig/ApplicationFormPreview.tsx` injects only the
   `:root` variable block into its container, then renders a Chakra `ApplicationFormRenderer` that
   produces columns/colours/layout INDEPENDENTLY of the Layer-2 `page_css`. The task-13.2 parity
   fixture only pins that the TS and Python generators emit the SAME `css_variables`/`page_css`
   STRINGS — it never verified that string actually STYLES the form. So preview↔published parity
   is FALSE: the preview's appearance is Chakra's, not the shared CSS's.

4. **R-B, response-shape mismatch** — `ApplicationFormBuilder.tsx` `handleSetLookAndFeel` does
   `setLookAndFeel(res.settings ?? {})` after a successful `setLookAndFeelSetting`. But the
   `PUT /members/look-and-feel` edge (`sam/members/handler/_dispatch_config.py`
   `write_look_and_feel`) returns the Change-Op write result from
   `LookAndFeelSettingsService.set_setting` (which returns `writer.set_look_and_feel(...)` /
   `remove_look_and_feel(...)`, i.e. `{version, idempotent_replay}`), **not** a `{settings}` map.
   So `res.settings` is `undefined` → `?? {}` BLANKS the optimistic edit, and the editor shows the
   old/default value until a fresh `getLookAndFeelSettings` GET. The GET dispatch (`get_look_and_feel`)
   returns `{"settings": ...}`; the PUT does not — a client/server response-shape mismatch. (Note:
   the existing frontend builder test mocks the set result as `{ settings: ... }`, a shape the real
   edge never produces — a false-green that helped hide this.)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors (must continue to work exactly):**
- The applicant submit flow: the client-side required / EMAIL / IBAN checks and the JSON POST to
  `POST {public_api_base}/public/members/{slug}/applications` (bugfix 3.1).
- The rendered applicant-visible fields, functional-group sections, locale selector, and consent
  control from `get_public_field_config`, with the same server-authoritative filtering and
  escaping (bugfix 3.2).
- Rendering with SAM-owned Layer-2 defaults when a tenant has no / incomplete settings, without
  failing (bugfix 3.3).
- The existing seven-attribute Layer-2 contract: supported-attribute behaviour and
  reject-on-unsupported (bugfix 3.4); the cross-language preview parity for those attributes.
- Publish resolves settings exclusively from SAM-owned state scoped to the verified `tenant_id`,
  no Flask-plane runtime call, no cross-tenant leakage (bugfix 3.5).
- Publish-failure semantics: a Layer-2 failure leaves the previously published form untouched and
  returns a failure indication (bugfix 3.6 / spec 15 Req 5.5).
- **The landing-page CSS classes** (`.hero`, `.cta`, `.btn`, `.pricing-card`, the gallery/faq
  grids, …) are emitted UNCHANGED, so a future SAM landing page is unaffected (bugfix 3.7 — the
  key regression guard for Option 1).

**Scope:** inputs that do NOT satisfy the bug condition must be unaffected — a tenant on pure
defaults, the applicant submit path, and any consumer of the landing-page classes.

## Hypothesized Root Cause

The root cause is confirmed above (not hypothetical). Summarised as the four defects to fix:

1. **CSS is aimed at landing-page classes, not the form** — the generated colour/layout rules
   never match the application-form markup, and there is no colour variable or form grid.
2. **The renderer omits the logo and the body heading** — no element exists to carry them, and
   publish supplies no header fragment.
3. **Two independent render paths** — preview (Chakra) and published (Python Layer-2 CSS) produce
   appearance independently, so "same generator string" ≠ "same appearance"; the parity test
   pinned the string, not the styling.
4. **PUT returns the write-op result, not `{settings}`** — the client re-seed blanks the edit.

## Correctness Properties

Property 1: Bug Condition — Published form carries the APPLIED look-and-feel

_For any_ publish/render of an application form whose resolved `Look_And_Feel_Settings` satisfy the
bug condition (distinct values and/or a logo / header title / column count), the fixed render path
SHALL produce an artifact that APPLIES the styling to the form's OWN elements: the brand colours on
the form heading/title, submit button, and input focus state; a multi-column layout that collapses
to a single column on small screens; the tenant logo; and the header/title — and a change to any
value SHALL produce a corresponding, observable change in the artifact. (Assert APPLIED styling in
the produced HTML, not that a generator emits a string — this closes the false-parity gap.)

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

Property 2: Preservation — Non-bug-condition behaviour and the landing-page classes

_For any_ input where the bug condition does NOT hold (a tenant on defaults; the applicant submit
path; a consumer of the landing-page classes; the existing seven-attribute Layer-2 output for
those seven attributes), the fixed code SHALL produce the same observable result as the original —
preserving the submit contract, the field/group/consent/locale rendering and escaping, tenant
isolation, the publish readiness/failure semantics, and byte-for-byte the emitted landing-page CSS
classes (`.hero`, `.cta`, `.btn`, `.pricing-card`, the gallery/faq grids, …).

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

Property 3: Bug Condition (R-B) — Editor reflects a change with no reload

_For any_ successful `setLookAndFeelSetting(attribute, value)` in the admin editor, the editor
(and the live preview) SHALL immediately show the new value with NO data reload — the fixed
`PUT /members/look-and-feel` edge SHALL return the resolved `{settings}` (the same shape the GET
returns) so the client re-seed shows the authored value, and the editor SHALL NOT blank the value
after a successful save.

**Validates: Requirements 2.8**

## Fix Implementation

The fix is sequenced A → B → C → D (→ E). A is the reproducing tests (owned by `tasks.md` Task 1);
B–E are the fix.

### B — Option 1: genuinely style the PUBLISHED form (the single shared styling source)

**Goal:** the published artifact APPLIES the look-and-feel to the form's own elements.

1. **Application-form CSS block.** Add application-form-specific CSS that:
   - lays out the field groups (`.form-group` / the `.form-field` within) in a MULTI-COLUMN grid
     driven by the new `columns` attribute, collapsing to a single column below a small-screen
     breakpoint (mirroring the existing `@media (max-width: 480px)` collapse pattern the
     landing-page grids already use);
   - applies `color_primary` / `color_accent` to the form's OWN elements — the form
     heading/title, the submit `<button type="submit">`, and the input/select/textarea `:focus`
     state — so a colour change is observable on the form itself.
   - **Decision DD-B1 (WHERE the CSS lives):** EXTEND `sam/shared/page_styles` with an
     application-form CSS block emitted alongside the existing output (rather than a separate
     form-CSS source), so there remains exactly ONE SAM-owned styling source feeding both the
     published render and (via the task-13.2 parity mechanism) the preview. This keeps the
     "one CSS source" invariant spec 15 established and keeps B as the single style source BOTH render paths read (E). To apply colours cleanly, introduce `--color-primary` /
     `--color-accent` `:root` variables (today the colours are inlined only into landing rules)
     and reference them from the form block; the landing rules keep their inlined colours
     UNCHANGED (3.7). The `columns` value drives the grid `grid-template-columns`.

2. **Renderer emits logo + heading.** Extend `build_form_body_html`
   (`application_form_render.py`) to render, when supplied:
   - a logo `<img>` (escaped `src`/`alt`) at the top of the body, and
   - a visible heading element (escaped `header_title`) —
   and have `ApplicationPublishService.publish` compose and pass these (today it passes no
   `header_html`). The existing `header_html` seam is used, or logo/title are passed as explicit
   escaped params. Absent values render byte-identically to today (preservation).

3. **Regression guard (3.7):** assert the emitted landing-page classes are unchanged; a snapshot
   or equality assertion on the landing CSS block guards against the new form block perturbing it.

### C — R-A: new inputs + storage + UI across all planes (steering 40)

Add three new VALUES-ONLY `Look_And_Feel_Settings` attributes — a deliberate, documented extension
of the current exactly-seven set (bugfix 3.4 names this as an allowed extension):

| Attribute | Type | Validation (reject out-of-range like the existing attributes, bugfix 3.4) |
| --- | --- | --- |
| `logo` | URL / asset reference (text) | A reference to an existing asset URL — never an upload of CSS/binary into the slice (values-only, steering 39). Validated as a bounded, well-formed reference; the renderer escapes it. **Decision DD-C1:** a `logo` is a URL/reference string (e.g. an existing public-pages asset URL), NOT a binary upload; storing a URL keeps the write values-only. |
| `header_title` | text | Free text, length-bounded; HTML-escaped on render (XSS-safe, same contract as field labels). |
| `columns` | bounded integer / enum | An enum or bounded integer (e.g. 1–3); an out-of-range value is rejected exactly like `shadow_style` rejects an unknown token (Req 4.5 / bugfix 3.4). |

Plane-by-plane extension (each with paired tests, steering 30/34/33):
- **Layer-2 generator** (`page_styles`): extend `SUPPORTED_ATTRIBUTES`, `_DEFAULTS`, and the CSS
  so `columns` drives the grid; `logo`/`header_title` are consumed by the renderer (they are
  values the renderer reads, not CSS the generator emits — `page_styles` validates them as
  supported and carries defaults). Unsupported-attribute rejection still holds for anything
  outside the now-ten set (3.4).
- **Stored slice** (`config#fields` `look_and_feel`): no schema change — the slice stores arbitrary
  values-only attributes already; the three new keys ride the existing Change-Op path.
- **Edge / service validation** (`look_and_feel_settings_service.set_setting` +
  `_dispatch_config.write_look_and_feel`): extend the supported-attribute check and the
  permitted-value validation (`columns` range, `logo` reference shape, `header_title` length);
  reject with the existing caller-safe 422 envelope, leaving stored values unchanged (Req 4.5).
- **Domain publish** (`application_publish` → renderer): resolve the three new values and pass
  logo/title to `build_form_body_html` and `columns` into the styling.
- **Authoring UI** (`LookAndFeelEditor.tsx` + `ApplicationFormBuilder.tsx`): add data-entry
  controls for logo, header/title, and column count, wired to the existing values-only
  `setLookAndFeelSetting` Change-Op path; surface the caller-safe error envelope.
- **Preview** (`ApplicationFormPreview.tsx` + the parity fixture): reflect the three new values so
  the preview matches (ties to Property 1 / Req 2.6).

### D — R-B: editor reflects a change with no reload

**Decision DD-D1 (chosen approach):** make the `PUT /members/look-and-feel` edge return the
resolved `{settings}` — the SAME shape the GET returns — so the client's existing
`setLookAndFeel(res.settings ?? {})` re-seed shows the authored value. Justification: GET and PUT
then share ONE response contract, so the client never blanks the edit and the editor/preview stay
truthful without a round-trip. In `_dispatch_config.write_look_and_feel`, after the
`set_setting` / `copy_settings` Change-Op succeeds, resolve the tenant's current values
(`get_settings`) and return `{"settings": {...}, ...write-result}`. (Retaining the optimistic
client edit is a weaker fallback — it leaves GET/PUT contracts divergent — so DD-D1 returns
`{settings}` and additionally the client MAY keep the optimistic value as defence in depth.) The
existing frontend builder test that mocks `{ settings: ... }` becomes a TRUE assertion once the
edge actually returns that shape (change-with-tests: update the real edge AND align the paired
tests to the real contract).

### E — Keep two render paths, one shared set of style attributes (parity by construction)

TWO render paths are RETAINED deliberately, each with a job the other cannot do:

1. the **in-browser preview** (React) — the authoring-time, no-round-trip render that gives the
   admin IMMEDIATE proof of what a change looks like before publishing; and
2. the **published HTML page** (Python render on the SAM plane) — the live artifact applicants see.

This split is intentional and stays. An in-browser instant preview REQUIRES React (it cannot run
the Python render without a round-trip), so there is no single renderer and we do NOT replace the
preview with an iframe of the real artifact — doing so would destroy the immediate-feedback preview
the admin needs. (An earlier draft of this design proposed collapsing to one path; that was wrong
and is removed.)

The bug was NOT that there are two paths — it is that the two paths derived their APPEARANCE from
DIFFERENT places (the published page from the Layer-2 `page_css`; the preview from independent
Chakra styling), so they could and did diverge while a string-level fixture stayed green. The fix
is therefore:

**Both renderers MUST produce the form's appearance from the SAME set of style attributes.** The
SAM-owned Layer-2 values (the resolved `Look_And_Feel_Settings` — brand colours, `columns`, logo,
header title, fonts/spacing/radius/shadow) are the ONE source of truth. The Python render applies
them to the published form's elements (B); the React preview applies the SAME attributes to the
same logical elements (grid columns, the brand colours on the form heading/submit/focus, the logo,
the heading). Neither path invents its own styling; both read the same attributes and the same
defaults, so identical attributes produce the same applied appearance on both.

**Parity is verified on APPLIED appearance, not on a generated string.** The task-13.2 fixture is
STRENGTHENED (not replaced by a single renderer): the parity test asserts that, for the same
resolved attributes, the preview and the published artifact apply the SAME styling to the SAME
logical elements — the brand colour reaches the form heading/submit/focus in both, the column count
produces the same multi-column layout in both, the logo and header title appear in both. A test
that only compares generator strings is insufficient (that false-green is part of this bug); the
parity test must assert the applied result on each path.

This is done AS PART OF B and C: when B adds the application-form CSS and the renderer logo/heading,
and C adds `logo`/`header_title`/`columns`, the preview (Task 12) is extended to read and apply the
SAME attributes, and the parity test (Task 13.x / the strengthened 13.2-style fixture) pins that
both paths produce the same applied appearance. There is no separate "unify the renderers" task and
no decision to defer — two paths, one attribute source, parity asserted on the applied result.

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples that demonstrate the bug on UNFIXED code (A), then verify
the fix applies the styling and preserves existing behaviour. The critical A test asserts APPLIED
styling in the PRODUCED artifact — the assertion the shipped parity fixture never made.

### Exploratory Bug Condition Checking

**Goal:** surface counterexamples proving the published form does NOT carry the styling, BEFORE
the fix. Confirm the root-cause analysis (CSS aimed at landing classes; no logo/heading; preview↔
published divergence; stale editor).

**Test Plan:** render/publish an application form with distinct look-and-feel values and assert the
PRODUCED/baked HTML (a) applies brand colours to the form's own elements, (b) has a multi-column
layout collapsing on small screens, (c) includes the logo, (d) includes the title/heading. Run on
UNFIXED code — expect FAILURE. Separately, a frontend test: after a successful
`setLookAndFeelSetting`, the editor shows the new value with no reload — run on UNFIXED code,
expect FAILURE (because the real edge returns no `{settings}`).

**Test Cases:**
1. **Brand colours applied** — publish with `color_primary=#C01030`; assert the baked HTML themes
   the form heading/submit/focus (will FAIL — only landing classes themed).
2. **Multi-column collapsing layout** — publish with `columns=3`; assert a grid rule with a
   small-screen single-column collapse (will FAIL — no form grid).
3. **Logo rendered** — publish with a `logo` reference; assert a logo `<img>` in the body (will
   FAIL — renderer emits none).
4. **Heading rendered** — publish with a `header_title`; assert a visible heading element (will
   FAIL — only a non-visible `<title>`).
5. **R-B no-reload** — a successful set; assert the editor control shows the new value with no GET
   (will FAIL — `res.settings` undefined blanks it).

**Expected Counterexamples:** the baked HTML themes only `.hero`/`.cta`/`.btn`/`.pricing-card`;
`.application-form` carries grey borders and error reds but no brand colour and no grid; no logo
`<img>`; no body heading; the editor snaps back after a successful save.

### Fix Checking

**Goal:** for all inputs satisfying the bug condition, the fixed path produces the expected
behaviour.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  artifact := publish_fixed(input.settings)
  ASSERT artifactAppliesBrandColours(artifact)
     AND artifactHasMultiColumnLayout(artifact)
     AND artifactRendersLogo(artifact)
     AND artifactRendersHeading(artifact)
END FOR

FOR ALL input WHERE isStaleEditorBugCondition(input) DO
  result := putLookAndFeel_fixed(input)
  ASSERT result.settings IS DEFINED AND editorShowsAuthoredValue(result)
END FOR
```

### Preservation Checking

**Goal:** for all inputs NOT satisfying the bug condition, the fixed path produces the same result
as the original — crucially the landing-page CSS classes (3.7) and the applicant submit contract.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT landingCssClasses(publish_fixed(input)) == landingCssClasses(publish_original(input))
  ASSERT submitContract(publish_fixed(input)) == submitContract(publish_original(input))
  ASSERT layer2Output_sevenAttributes(fixed) == layer2Output_sevenAttributes(original)
END FOR
```

**Testing Approach:** property-based testing (Hypothesis ≥100 iterations) for preservation — it
generates many non-bug inputs and guards the landing-class invariant and the seven-attribute
Layer-2 output against drift. Observe the landing CSS and submit markup on UNFIXED code first, then
pin them.

**Test Plan:** observe the UNFIXED landing-class CSS and submit markup; write property tests that
assert they are unchanged after the fix.

**Test Cases:**
1. **Landing classes preserved** — assert the emitted `.hero`/`.cta`/`.btn`/`.pricing-card`/grid
   CSS is byte-identical after the fix (3.7).
2. **Submit contract preserved** — assert the fields/groups/locale/consent markup and the submit
   script are unchanged for the same config (3.1, 3.2).
3. **Defaults preserved** — a tenant with no settings publishes without failing, using the same
   defaults (3.3).
4. **Seven-attribute Layer-2 preserved** — for the existing seven attributes, `render_page_styles`
   output is unchanged (3.4); the preview parity for those attributes holds.

### Unit Tests

- Layer-2: the new application-form CSS block (grid + brand colours via `--color-*` vars); the new
  `columns`/`logo`/`header_title` handling; unsupported-attribute rejection for the now-ten set.
- Renderer: logo `<img>` + heading emission when supplied; byte-identical output when absent.
- Service/edge: `columns`/`logo`/`header_title` validation (reject out-of-range, leave stored
  values unchanged); the `write_look_and_feel` edge returns `{settings}` (D).
- Frontend: the new editor controls send values-only Change-Ops; no-reload reflection (R-B).

### Property-Based Tests

- Property 1: a successful publish APPLIES styling derived from the resolved values to the form's
  own elements (assert APPLIED styling in the artifact, not a generator string).
- Property 2: non-bug inputs preserve the landing classes, the submit contract, and the
  seven-attribute Layer-2 output.
- Property 3: a successful set makes the editor reflect the value with no reload.

### Integration Tests

- Real-data round-trip (steering 39, NON-NEGOTIABLE): author the new attributes via the Change-Op
  against a REAL `config#fields` row (e.g. `h-dcn`), resolve them back, publish, and assert the
  baked artifact carries the applied styling (logo/title/columns/colours) AND that unrelated slices
  (`fields`/`overrides`/slug/publish-state) survive the write by construction.
- Applied-appearance parity (design §E): a test asserting that, for the same resolved attributes,
  the React preview and the published artifact apply the SAME styling to the SAME logical elements
  (brand colour on the form heading/submit/focus, the same column layout, the logo, the header
  title) — the two retained paths cannot diverge in appearance.
