# Implementation Plan: Published Application Form Styling Bugfix

## Overview

This plan fixes the spec-15 defect where the PUBLISHED application form does not carry the tenant's
look-and-feel (no logo, no heading, single column, no brand colours on the form's own elements)
while the admin preview does — breaking spec 15 Req 5.2 / 7.1. It follows the exploratory bugfix
methodology (steering 30/34/39): write the failing bug-condition tests FIRST (they must FAIL on
current code — that failure confirms the bug and closes the false-parity gap), write the
preservation tests (they must PASS on current code), THEN apply the fix sequenced A → B → C → D
(→ E).

**CRITICAL — write the exploration tests BEFORE the fix, and run them on UNFIXED code.** The
Task-1 test asserts APPLIED styling in the PRODUCED/baked HTML — not that a generator emits a
string — which is the assertion the shipped task-13.2 parity fixture never made.

Language: Python (SAM domain/repository/handler, `sam/shared/`) and TypeScript/React (frontend) —
the languages the touched seams already use.

Shell/tooling (steering 41): SAM tests run via `python -m pytest sam/tests/... -c sam/pytest.ini`
from the repo root; frontend tests via `cd frontend && npx vitest run <files>`. On this WSL
setup the terminal reports `Exit Code -1` even on success and may swallow stdout — judge
results from a captured log under `.agent-output/` and an in-band `<<<DONE marker=$?>>>`, and
use the POSIX repo path (never the UNC path) for bash. Real AWS/DynamoDB checks (Task 17) use
the `nonprofit-deploy` profile (account 506221081911) per steering 41's override-ranking trap.

Property-based tests use **Hypothesis** (≥100 iterations) for the SAM properties; the frontend
no-reload test is a vitest example. Every product-code task updates its paired test(s) in the SAME
task (change-with-tests contract, steering 30/34/33/39).

Phases:
- **Phase 0 — Reproduce (A):** failing bug-condition tests + passing preservation tests.
- **Phase 1 — Option 1 (B):** genuinely style the published form (the single shared CSS source).
- **Phase 2 — R-A (C):** new logo / header_title / columns attributes across all planes.
- **Phase 3 — R-B (D):** no-reload editor.
- **Phase 4 — Verify + real data + CI/CD.**
- **Phase 5 — Parity (E):** both render paths (React preview + published HTML) apply the SAME
  style attributes; a parity test asserts the SAME applied appearance on each. Two paths kept — no
  single renderer.
- **Phase 6 — Governance (steering 40):** update steering 36 (and any stale 35/39/spec-15
  statement) for the seven→ten attribute extension; confirm cross-plane vocabulary parity.

## Tasks

### Phase 0 — Reproduce the bug (A)

- [x] 1. Write the published-styling bug-condition exploration test
  - **Property 1: Bug Condition** - Published form carries the APPLIED look-and-feel
  - **CRITICAL**: this test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT fix the test or the code when it fails**; this test encodes the expected behaviour and
    will validate the fix when it passes after implementation
  - **GOAL**: surface counterexamples proving the PRODUCED/baked HTML does not apply the styling
  - **Scoped PBT Approach**: scope the property to concrete distinct-value cases (e.g.
    `color_primary=#C01030`, `columns=3`, a `logo` reference, a `header_title`) for reproducibility
  - Publish/render an application form with distinct look-and-feel values and assert the baked HTML
    (a) applies the brand colours to the form's OWN elements (heading/title, submit button, input
    focus), (b) renders a multi-column grid that collapses to one column on small screens, (c)
    includes the logo `<img>`, (d) includes the title/heading element — assert APPLIED styling in
    the artifact, NOT that a generator emits a string (closes the false-parity gap, design Bug
    Details root cause 3)
  - Run on UNFIXED code — **EXPECTED OUTCOME: FAILS** (only landing classes themed; no form grid;
    no logo; no heading)
  - Document the counterexamples found
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.6_

- [x] 2. Write the stale-editor (R-B) bug-condition exploration test
  - **Property 3: Bug Condition** - Editor reflects a change with no reload
  - **CRITICAL**: this test MUST FAIL on unfixed code
  - **GOAL**: reproduce R-B — after a successful `setLookAndFeelSetting`, the editor shows the new
    value with NO reload
  - Drive the real builder success handler against the REAL edge response shape (the Change-Op
    write result `{version, idempotent_replay}` — NOT `{settings}`); assert the control reflects
    the authored value with no GET. (Do NOT mock the set result as `{settings}` — that false-green
    hid this; the test must use the real PUT shape, design root cause 4)
  - Run on UNFIXED code — **EXPECTED OUTCOME: FAILS** (`res.settings` undefined → `?? {}` blanks
    the edit)
  - Document the counterexample
  - _Requirements: 1.8, 2.8_

- [x] 3. Write preservation property tests (BEFORE implementing the fix)
  - **Property 2: Preservation** - Non-bug-condition behaviour and the landing-page classes
  - **IMPORTANT**: follow observation-first methodology
  - Observe on UNFIXED code: the emitted landing-page CSS classes
    (`.hero`/`.cta`/`.btn`/`.pricing-card`/gallery/faq grids); the fields/groups/locale/consent
    submit markup and submit script; the seven-attribute Layer-2 output; a defaults-only publish
  - Write property-based tests (Hypothesis ≥100 iterations) asserting those are unchanged: landing
    classes byte-identical (3.7), submit contract unchanged (3.1/3.2), defaults publish without
    failing (3.3), seven-attribute Layer-2 output unchanged (3.4)
  - Run on UNFIXED code — **EXPECTED OUTCOME: PASS** (baseline to preserve)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 4. Checkpoint — Phase 0 (reproduce) complete
  - Task 1 + 2 FAIL on unfixed code (bug confirmed); Task 3 PASSES (baseline captured). Ask the
    user if questions arise.

### Phase 1 — Option 1 (B): genuinely style the published form

- [x] 5. Layer-2 — application-form CSS block (grid + brand colours), landing classes unchanged
  - [x] 5.1 Extend `sam/shared/page_styles` with an application-form CSS block (DD-B1)
    - Add `--color-primary` / `--color-accent` to the `:root` variables (today the colours are
      inlined only into landing rules) and reference them from a new `.application-form` block
    - Style the form's OWN elements: the form heading/title, the submit `<button type="submit">`,
      and input/select/textarea `:focus` state use the brand colours
    - Lay out `.form-group` / `.form-field` in a MULTI-COLUMN grid (driven later by `columns`,
      Task 8) that collapses to a single column below a small-screen breakpoint (mirror the
      existing `@media (max-width: 480px)` collapse pattern)
    - Keep the single SAM-owned style source (one set of attributes + one generator) that BOTH
      render paths read, so the preview and the published form cannot diverge (design §E)
    - _Bug_Condition: isBugCondition(input) — artifact not themed / single column (design)_
    - _Expected_Behavior: Property 1 — APPLIED styling on the form's own elements_
    - _Preservation: landing-page classes emitted UNCHANGED (3.7)_
    - _Requirements: 2.1, 2.2, 2.5, 3.7_
  - [x] 5.2 Paired Layer-2 tests — brand colours + grid applied; landing CSS preserved
    - Assert the generated CSS themes the form's own elements and defines a collapsing grid; assert
      the landing-class CSS block is byte-identical to the baseline from Task 3 (3.7)
    - _Requirements: 2.1, 2.2, 3.7_

- [x] 6. Renderer — emit the logo + visible heading in the body
  - [x] 6.1 Extend `build_form_body_html` + `publish` to render logo and header_title
    - `build_form_body_html` (`application_form_render.py`) renders, when supplied, a logo `<img>`
      (escaped `src`/`alt`) and a visible heading element (escaped `header_title`) at the top of
      the body; absent values render byte-identically to today (preservation)
    - `ApplicationPublishService.publish` composes and passes these (today it passes no
      `header_html`), resolving them from the stored slice
    - _Bug_Condition: isBugCondition(input) — no logo / no heading (design root cause 2)_
    - _Expected_Behavior: Property 1 — logo + heading rendered_
    - _Preservation: byte-identical body when absent (3.2)_
    - _Requirements: 2.3, 2.4, 3.2_
  - [x] 6.2 Paired renderer tests — logo/heading emitted when supplied; unchanged when absent
    - Assert escaping of `logo`/`header_title`; assert the body is byte-identical when both absent
    - _Requirements: 2.3, 2.4, 3.2_

- [x] 7. Checkpoint — Phase 1 (Option 1) complete
  - The published artifact now applies colours/grid/logo/heading (for values already storable).
    Ask the user if questions arise.

### Phase 2 — R-A (C): new logo / header_title / columns attributes across ALL planes (steering 40)

- [x] 8. Layer-2 plane — support `columns`, `logo`, `header_title`
  - Extend `SUPPORTED_ATTRIBUTES` (the now-ten set — a documented extension of the seven,
    bugfix 3.4), `_DEFAULTS`, and the CSS so `columns` drives the grid `grid-template-columns`;
    `logo`/`header_title` are carried as supported values (consumed by the renderer, Task 6)
  - Unsupported-attribute rejection still holds for anything outside the ten
  - Paired Hypothesis tests: the ten-attribute support; `columns` changes the grid; rejection of a
    key outside the ten (change-with-tests)
  - _Bug_Condition: isBugCondition(input) — column count unsupported today (design C)_
  - _Expected_Behavior: Property 1 — columns drives multi-column layout_
  - _Preservation: seven-attribute output unchanged (3.4)_
  - _Requirements: 2.2, 2.7, 3.4_

- [x] 9. Stored-slice plane — the three new values ride the existing Change-Op path
  - Confirm the `look_and_feel` slice on `config#fields` carries `logo`/`header_title`/`columns`
    as values-only attributes via the existing path-scoped Change-Op (no schema change, no
    whole-record write — steering 39); paired test asserts a SET of a new attribute leaves
    `fields`/`overrides`/slug/publish-state untouched and bumps the version
  - _Bug_Condition: n/a (storage seam for C)_
  - _Preservation: unrelated slices survive by construction (steering 39)_
  - _Requirements: 2.7; spec-15 Req 8.1, 8.3 (Change-Op write contract)_

- [x] 10. Edge + service plane — validate `columns` / `logo` / `header_title`
  - Extend `LookAndFeelSettingsService.set_setting` supported-attribute + permitted-value checks
    and the `write_look_and_feel` edge: `columns` is a bounded integer/enum (DD-C1), `logo` is a
    well-formed URL/asset reference (never a CSS/binary upload — values-only), `header_title` is
    length-bounded text; reject out-of-range with the caller-safe 422 envelope, leaving stored
    values UNCHANGED (Req 4.5 / bugfix 3.4)
  - Paired unit tests: each new attribute rejects out-of-range leaving stored values unchanged; a
    valid set issues one scoped Change-Op
  - _Bug_Condition: n/a (validation seam for C)_
  - _Expected_Behavior: reject out-of-range like existing attributes (3.4)_
  - _Preservation: stored values unchanged on reject (Req 4.5)_
  - _Requirements: 2.7, 3.4_

- [x] 11. Authoring-UI plane — logo / header/title / column-count controls (no half-shipped feature)
  - Add data-entry controls in `LookAndFeelEditor.tsx` + `ApplicationFormBuilder.tsx` for `logo`,
    `header_title`, and `columns`, wired to the existing values-only `setLookAndFeelSetting`
    Change-Op path (never CSS, never a whole record); surface the caller-safe 422/403/409 envelope
  - Paired vitest tests: the new controls send values-only Change-Ops; an edge error surfaces
    without leaking internals (change-with-tests, steering 33)
  - _Bug_Condition: isBugCondition — no UI to enter logo/title/columns (defect 1.7 / R-A)_
  - _Expected_Behavior: Req 2.7 — authored + persisted + round-trips_
  - _Requirements: 2.7; spec-15 Req 8.1 (SAM authors its own config)_

- [x] 12. Preview plane — reflect `logo` / `header_title` / `columns`
  - Extend `ApplicationFormPreview.tsx` (and the parity mechanism) to reflect the three new values
    so the preview matches the published form (ties to Req 2.6); paired test asserts the preview
    reflects a new-attribute edit
  - _Bug_Condition: isBugCondition — preview↔published divergence (design root cause 3)_
  - _Expected_Behavior: Property 1 / Req 2.6 — preview matches published appearance_
  - _Requirements: 2.6, 2.7; spec-15 Req 7.1, 7.2 (admin preview reflects published)_

- [x] 13. Checkpoint — Phase 2 (R-A) complete across all planes
  - Logo/title/columns authored → stored → validated → published → previewed. Ask the user if
    questions arise.

### Phase 3 — R-B (D): editor reflects a change with no reload

- [x] 14. Fix the `PUT /members/look-and-feel` edge to return the resolved `{settings}` (DD-D1)
  - [x] 14.1 Return `{settings}` from `write_look_and_feel` (same shape as GET)
    - After the `set_setting` / `copy_settings` Change-Op succeeds, resolve the tenant's current
      values (`get_settings`) and return `{"settings": {...}, ...write-result}` so GET and PUT
      share one contract; the client's `setLookAndFeel(res.settings ?? {})` then shows the authored
      value (design DD-D1). Optionally keep the optimistic client edit as defence in depth
    - _Bug_Condition: isStaleEditorBugCondition(input) — PUT returns no settings (root cause 4)_
    - _Expected_Behavior: Property 3 — editor reflects the value with no reload_
    - _Preservation: GET contract unchanged; write-result fields still present_
    - _Requirements: 2.8_
  - [x] 14.2 Align the paired tests to the real PUT contract
    - Update the edge test to assert PUT returns `{settings}`; fix the builder test that mocked
      `{ settings: ... }` so it exercises the REAL contract (the false-green that hid R-B) — the
      Task-2 exploration test now PASSES (change-with-tests, no weakening of assertions)
    - _Requirements: 2.8_

- [x] 15. Checkpoint — Phase 3 (R-B) complete
  - A successful save keeps the editor + preview showing the authored value with no reload. Ask
    the user if questions arise.

### Phase 4 — Verify, real data, CI/CD

- [x] 16. Verify the bug-condition exploration tests now pass
  - [x] 16.1 Re-run the published-styling test from Task 1
    - **Property 1: Expected Behavior** - Published form carries the APPLIED look-and-feel
    - **IMPORTANT**: re-run the SAME test from Task 1 — do NOT write a new one
    - **EXPECTED OUTCOME: PASSES** (colours/grid/logo/heading now applied in the artifact)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  - [x] 16.2 Re-run the R-B test from Task 2
    - **Property 3: Expected Behavior** - Editor reflects a change with no reload
    - Re-run the SAME test from Task 2 — **EXPECTED OUTCOME: PASSES**
    - _Requirements: 2.8_
  - [x] 16.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-bug-condition behaviour and the landing-page classes
    - Re-run the SAME tests from Task 3 — **EXPECTED OUTCOME: PASS** (no regressions; landing
      classes + submit contract unchanged)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 17. Real-data round-trip (steering 39, NON-NEGOTIABLE)
  - Against a REAL `config#fields` row (e.g. `h-dcn`): author `logo` / `header_title` / `columns`
    (and a distinct colour) via the values-only Change-Op, resolve them back through the resolved
    view, publish, and confirm the baked artifact carries the APPLIED styling (colours on the
    form's own elements, multi-column collapsing layout, logo, heading); confirm unrelated slices
    (`fields` / `overrides` / slug / publish-state) survive the write by construction
  - Run against the real row before marking done — "tests pass" alone is not sufficient (steering 39)
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.7; spec-15 Req 8.3 (Change-Op write contract)_

- [-] 18. CI/CD — quality gates, deploy paths, production-release gate (steering 43)
  - Confirm the per-PR gates are green on the feature branch: CodeQL Advanced + GitGuardian (root
    cause, not suppression)
  - Confirm the changed paths trigger the right deploys on the branch→env contract:
    `sam/members/**` + `sam/shared/**` → `deploy-sam-members` (TEST on `test`, PROD on `main`);
    `frontend/**` → `deploy-frontend` (PROD on `main`); `config#fields` is already writable so the
    DynamoDB write needs no new IAM
  - This bugfix builds on spec 15 already on `test` (PRs #208/#209/#210 merged incl. the legacy-row
    500 fix); dispatch the nightly `full-test-suite.yml` (optionally a narrowed `scope:`) for
    blast-radius coverage; land TEST verification before the promote `test`→`main` production gate
  - _Requirements: 2.1, 2.6_

- [x] 19. Checkpoint — fix complete and verified (Options 1 + R-A + R-B)
  - All bug-condition tests pass; preservation holds; real-data round-trip green; CI/CD confirmed.
    Ask the user if questions arise.

### Phase 5 — Parity: both render paths apply the SAME style attributes

> Two render paths are RETAINED deliberately (design §E): the in-browser React preview (immediate,
> no-round-trip proof of a change) and the published Python-rendered HTML page. There is NO single
> renderer and NO iframe. The fix is that BOTH derive the form's appearance from the SAME resolved
> `Look_And_Feel_Settings` attributes, and a parity test asserts the SAME APPLIED appearance on
> each path (not a generator string). Most of this lands inside Phase 1/2 (Task 5 builds the one
> SAM style source; Task 12 makes the preview apply the same attributes); this phase adds the
> cross-path applied-appearance parity assertion.

- [x] 20. Applied-appearance parity — preview and published form from the same attributes
  - Strengthen the parity mechanism (the spec-15 task-13.2 string fixture is INSUFFICIENT and part
    of this bug): for the same resolved attributes, assert the preview and the published artifact
    apply the SAME styling to the SAME logical elements — the brand colour reaches the form
    heading/submit/focus on BOTH paths, the `columns` value produces the same multi-column layout
    on BOTH, and the logo + header title appear on BOTH. The test asserts the APPLIED result on each
    path, never merely that the two generators emit the same string.
  - Both paths read the ONE shared source — the Python render (Task 5/6) and the React preview
    (Task 12) consume the SAME attributes + SAME defaults; neither invents its own styling. This
    task adds the test that pins they cannot diverge in applied appearance.
  - Paired tests across the two paths (a SAM/published-artifact assertion + a frontend/preview
    assertion driven from the same attribute fixture).
  - _Requirements: 2.6; spec-15 Req 7.1 (admin preview reflects published)_

### Phase 6 — Governance definition-of-done (steering 40)

- [x] 21. Update steering + spec-15 attribute-contract docs for the seven→ten attribute extension
  - This bugfix adds three new look-and-feel attributes (`logo`, `header_title`, `columns`) to
    the previously exactly-seven set. Per steering 40 governance definition-of-done, every
    steering/ADR/spec doc that states the seven-attribute contract MUST be updated to match:
    - **Steering 36** (`.kiro/steering/36-config-and-parameters.md`) — its SAM-owned
      look-and-feel section lists the seven supported attributes; update to the now-ten set and
      note logo/header_title/columns are values-only (a URL reference / escaped text / bounded
      enum — never CSS or a binary upload).
    - **Steering 35 / 39** — review for any seven-attribute or styling-contract statement that
      is now stale; update only where it would otherwise mislead (no change if none).
    - **Spec 15 docs** (`15 - sam-page-look-and-feel/requirements.md` / `design.md`) — the
      Glossary/Req 3.2 'exactly seven' statements: add a cross-reference to this bugfix recording
      the deliberate extension to ten (do not silently contradict spec 15 — link it).
  - Also confirm the `SUPPORTED_ATTRIBUTES` single-source-of-truth and its parity test still pin
    the TS mirror to the Python set after the extension (steering 40 all-planes — the vocabulary
    must not drift across planes).
  - _Requirements: 2.7, 3.4 (and steering-40 governance definition-of-done)_

- [x] 22. Checkpoint — governance complete
  - Steering 36 (and any stale 35/39/spec-15 statement) reflect the ten-attribute set; the
    cross-plane vocabulary parity holds. Ask the user if questions arise.

## Notes

- Property-based tests use Hypothesis (≥100 iterations) for the SAM properties; the R-B no-reload
  test is a vitest example.
- Every product-code task updates its paired tests in the SAME task (change-with-tests, steering
  30/34/33/39). Task 14.2 specifically re-aligns the builder test that mocked a `{settings}` shape
  the real edge never produced — a false-green that helped hide R-B. Do NOT weaken assertions to
  go green.
- The three new attributes (`logo`, `header_title`, `columns`) are a DELIBERATE, documented
  extension of the exactly-seven Layer-2 set (bugfix 3.4 / design §C) — they are values-only
  (steering 39): a logo is a URL/reference, never a CSS/binary upload into the slice.
- The regression guard (bugfix 3.7) — the landing-page classes emitted UNCHANGED — is asserted in
  Tasks 3 and 5.2; it is the key preservation invariant for Option 1.
- The real-data round-trip (Task 17) is non-negotiable per steering 39.
- Two render paths are RETAINED deliberately (design §E): the instant React preview and the
  published Python HTML. The fix makes BOTH apply the SAME style attributes from the one SAM source;
  Phase 5 (Task 20) asserts applied-appearance parity across the two paths. There is NO single
  renderer and no iframe (an earlier draft proposed that; it was wrong and removed).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2", "3"] },
    { "id": 1, "tasks": ["4"] },
    { "id": 2, "tasks": ["5.1", "6.1"] },
    { "id": 3, "tasks": ["5.2", "6.2"] },
    { "id": 4, "tasks": ["7"] },
    { "id": 5, "tasks": ["8", "9"] },
    { "id": 6, "tasks": ["10"] },
    { "id": 7, "tasks": ["11", "12"] },
    { "id": 8, "tasks": ["13"] },
    { "id": 9, "tasks": ["14.1"] },
    { "id": 10, "tasks": ["14.2", "15"] },
    { "id": 11, "tasks": ["16.1", "16.2", "16.3"] },
    { "id": 12, "tasks": ["17", "18"] },
    { "id": 13, "tasks": ["19"] },
    { "id": 14, "tasks": ["20"] },
    { "id": 15, "tasks": ["21"] },
    { "id": 16, "tasks": ["22"] }
  ]
}
```
