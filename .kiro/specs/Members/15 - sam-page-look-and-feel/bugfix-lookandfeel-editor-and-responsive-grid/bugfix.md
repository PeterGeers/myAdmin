# Bugfix Requirements Document

## Introduction

Spec 15 — **SAM Page Look-and-Feel** (`.kiro/specs/Members/15 - sam-page-look-and-feel/`) — and its
sibling bugfix `bugfix-published-form-styling/` delivered a SAM-owned look-and-feel capability: a
Layer-2 CSS generator on both planes (`sam/shared/page_styles/__init__.py` and
`frontend/.../pageStyles.ts`), a stored values-only `look_and_feel` slice on `config#fields`, a
publish-time resolve, an authoring editor (`LookAndFeelEditor.tsx` / `ApplicationFormBuilder.tsx`),
and an in-browser admin preview (`ApplicationFormPreview.tsx`). The published-styling bugfix
reconciled the PUT/GET response shapes, threaded `columns`, popped `logo`/`header_title` before
Layer-2, and made the published artifact genuinely carry brand colours / grid / logo / heading.
That work is **done** and is NOT re-opened here — it is referenced as the baseline this bugfix
builds on.

A follow-up **behavioral audit**
(`semantic-review/2026-11-06-232354-look-and-feel-behavioral-audit.md`, verdict NEEDS_CHANGES) then
read the shipped code end-to-end and found that the capability still does not WORK for an
administrator: the authoring editor cannot be typed in, the responsive grid never reflows, the
preview is not WYSIWYG for columns, and a mixed editing session corrupts the working state. The
audit enumerates fourteen defects (D1–D14) with code-cited root causes.

**The unifying theme — and the defining discipline of this bugfix.** Every one of these defects
survived the shipped test suite for the SAME reason the original spec-15 defect did: the tests
asserted that STRINGS and CALLS exist, not that BEHAVIOR works. The editor test fired a single
`fireEvent.change` on a `<select>` (an atomic commit that never exposes the per-keystroke disable)
and asserted `onChange`/`onSave` were *called*; the parity fixture pinned the generated CSS
*strings* byte-for-byte while the preview grid comes from a completely different `sx` override that
the fixture never touches; there is no client-validation test because there is no client
validation. So the suite was green while a real user could not type a URL, the form never reflowed,
and preview ≠ published for columns. **This bugfix's defining discipline is therefore
BEHAVIOR-LEVEL bug-condition tests**: drive real multi-character keystrokes and assert the field
stays editable and keeps every character; toggle the in-flight flag and assert the active control
is not disabled; compare the preview's ACTUAL rendered layout (resolved track count AND reflow
breakpoint) to the published artifact's ACTUAL layout — never the presence of a string or a call.

Scope of this bugfix (four themes):
- **Editor usability** — a live preview on change with a DELIBERATE persist on blur/commit (or
  debounced), the in-flight flag never disabling the field being edited, and client-side validation
  against the same enum maps / patterns the service uses, surfacing the offending control inline.
  (D1, D2, D4, D5, D8, D11, D13, D14)
- **Responsive layout** — both page_styles planes reflow responsively (not a single hard 480px
  collapse), kept in parity. (D3, D12)
- **Preview / published parity** — the preview's actual grid behavior (element, track count, reflow
  breakpoint) matches the published artifact's, verified by comparing rendered layout, not CSS
  strings; and the meta/submit group and logo `alt` contract agree across planes. (D6, D9, D10)
- **Authoring round-trip bookkeeping** — a single consistent re-seed of both working maps from the
  resolved slice so a mixed editing session never drifts. (D7)

> **Scope boundaries.** This is editor-usability + responsive-layout + preview/published parity +
> authoring round-trip bookkeeping. The SAM publish path is otherwise correct — columns are threaded
> into the grid CSS, `logo`/`header_title` are popped from `brand` before Layer-2 and passed as
> explicit render params, and GET/PUT shapes are reconciled. This bugfix does NOT re-open the
> already-fixed spec-15 defect 1.8 (PUT/GET shape) or the already-delivered published-styling
> application — those are referenced as done.

> **Scope note — this is a spec-authoring deliverable only.** No product code, tests, or fixtures
> are changed by this document or its siblings. The user reviews the spec first. The design
> (`design.md`) owns the grounded root-cause investigation and fix approach; the task breakdown
> (`tasks.md`) owns the all-planes + CI/CD delivery with bug-condition-tests-first.

## Bug Analysis

### Current Behavior (Defect)

With the look-and-feel editor open for a tenant, an administrator cannot reliably author values, the
published form does not reflow responsively, the preview disagrees with the published grid, and a
mixed editing session corrupts the working maps.

1.1 **(D1/D4, BLOCKER)** WHEN an administrator types into a free-text look-and-feel control (the
`logo` input, the `header_title` input, or the colour hex text input) THEN the editor accepts only a
single character before the control becomes unusable, because `edit`/`editExtra` call `onChange`
AND `onSave` on every DOM `onChange` (persist-per-keystroke) while the single in-flight flag
`settingLookAndFeel` is passed back as `saving` and bound to `isDisabled` on EVERY control — so the
first keystroke persists, disables the active field, and the PUT response re-seeds it to the stored
one-character value, making multi-character entry impossible.

1.2 **(D2)** WHEN an administrator changes the columns `<select>` THEN the control briefly disables
and can snap back / appears "stuck at 2", because it is a symptom of the same persist-per-keystroke
+ disable-all + re-seed behavior in 1.1.

1.3 **(D5/D8, MAJOR)** WHEN an administrator types a colour hex value or a logo URL character by
character THEN each intermediate, partial, invalid value (`#`, `#1`, `h`, `ht`, `http:`, …) is
persisted and rejected server-side with a 422, producing a toast storm, because there is NO
client-side validation and every value round-trips to `LookAndFeelSettingsService` per keystroke;
the error toast names the setting but does NOT mark or focus the offending control (no
`aria-invalid`, no inline field error), and the in-progress edit is re-seeded / blanked.

1.4 **(D3, MAJOR)** WHEN the application form is rendered on a narrowing-but-not-tiny viewport (e.g.
a 700px window, or a 4-column choice at 1000px) THEN the field groups stay N-up and cramp/overflow
rather than reflowing, because both planes bake a fixed `grid-template-columns: repeat(N, 1fr)` with
a single hard `@media (max-width: 480px)` collapse to one column — there is no responsive reflow
between N and 1.

1.5 **(D6, MAJOR)** WHEN the admin preview and the published form are compared for the same resolved
columns value THEN their responsive grid behavior differs, because the preview lays out via an `sx`
override on the Chakra `[data-testid^="group-grid-"]` `SimpleGrid` collapsing at Chakra `md`
(~768px), while the published form themes the `.form-group` `<fieldset>` collapsing at 480px —
different element, different breakpoint, different collapse logic. A viewport between 480px and
768px shows 1 column in preview but N columns published; the CSS-string parity fixture compares
generator strings the preview grid never uses, so it proves nothing about actual layout.

1.6 **(D7, MAJOR)** WHEN an administrator edits an extra attribute (logo / header_title / columns)
and a seven-attribute attribute (colour / font / spacing / radius / shadow) in the same session THEN
the two working maps drift, because `handleSetLookAndFeel` re-seeds the seven-map from the full
ten-attribute `res.settings` (polluting it with extra keys and discarding the extra map's
authoritative state) while `handleSetExtraLookAndFeel` re-seeds only the extra map and leaves the
seven-map stale — the maps are no longer a clean partition of the resolved slice, so an editor
control can show a stale value after a mixed save.

1.7 **(D9, MINOR)** WHEN an administrator chooses a multi-column layout THEN the `_meta` submit group
(the locale selector + consent control) is also laid out in that column track count on BOTH the
published form and the preview, because the meta group is emitted as a `.form-group` fieldset and the
grid CSS themes every `.form-group` — so a lone consent checkbox and the locale `<select>` are
spread across N columns, which is not what "N columns for my fields" implies.

1.8 **(D10, MINOR)** WHEN the logo is rendered THEN the `alt` text diverges between the two planes —
the preview emits `alt` derived from the header title while the published artifact emits a fixed
empty `alt=""` — so the accessibility contract differs between what is previewed and what is
published.

1.9 **(D11, MINOR)** WHEN an administrator clears a look-and-feel value (persisting `null`) THEN the
control shows the Layer-2 default, which is indistinguishable in the UI from a value that was never
set, because `current()`/`currentExtra()` collapse absent/null to the default for display — there is
no UI signal that a value is cleared versus inheriting a default.

1.10 **(D12, MINOR)** WHEN an administrator chooses 3 or 4 columns THEN the layout never steps down
through intermediate counts (3→2→1) as the viewport narrows, because the baked collapse jumps
straight N→1 at a single breakpoint; the preview likewise collapses N→1 at Chakra `md`. (Tied to the
1.4/D3 fixed-track + single-breakpoint root cause.)

1.11 **(D13, MINOR)** WHEN an administrator enters a logo as a bare `www.` or `http://` reference THEN
it is rejected server-side only (the pattern requires `https://` or a site-relative `/…`) with no
client hint, which — combined with the per-keystroke 422 storm in 1.3 — is especially noisy. (Tied
to the 1.3/D5/D8 client-validation gap.)

1.12 **(D14, MINOR)** WHEN an administrator pastes a `header_title` longer than 200 characters THEN
the client silently truncates it at the `maxLength={200}` with no feedback (while the server also
bounds 200), so the administrator is not told their input was truncated.

1.13 **(D15, MAJOR)** WHEN an administrator wants to set the form logo THEN the only control is a
free-text URL/asset-reference field that assumes the image ALREADY exists at some URL (an S3 / CDN
object) — there is NO way to UPLOAD or STORE an image from the editor, so a reference can be saved
that points at an object which was never uploaded. Observed on deployed TEST: the published form's
logo request to `https://assets.jabaki.nl/h-dcn/logo-task17.png` returns **404 Not Found** (the
reference was stored by an earlier round-trip but no asset was ever put there), and the editor
offers no path to store the actual image. The repo already has an asset-upload path
(`uploadImage()` -> `POST /api/landing/images/upload`, the Media-Asset / `s3_assets` registry, and
`backend/routes/storage.py` `upload_logo` / `get_presigned_url`) that this control does not use.

### Expected Behavior (Correct)

The editor must be usable with real multi-character input and a deliberate persist; the layout must
reflow responsively and in parity across planes and the preview; the preview must be WYSIWYG for
columns; and the working maps must stay a clean partition across a mixed session.

2.1 **(fixes 1.1 / D1/D4)** WHEN an administrator types into any look-and-feel control THEN the
editor SHALL apply a live preview on change and persist the value DELIBERATELY on blur / explicit
commit (or debounced), and the in-flight flag SHALL NEVER disable the field currently being edited —
so a multi-character value (a URL, a title, a hex colour) can be entered in full and every character
is retained.

2.2 **(fixes 1.2 / D2)** WHEN an administrator changes the columns `<select>` THEN the control SHALL
retain the chosen value without snapping back and without being disabled mid-interaction.

2.3 **(fixes 1.3 / D5/D8)** WHEN an administrator enters a colour hex value or a logo reference THEN
the editor SHALL validate client-side against the SAME enum maps / patterns the service uses BEFORE
persisting, SHALL persist only on blur / commit (not per keystroke), and on a validation failure (or
a 422/403/409 from the edge) SHALL surface the offending control inline (`aria-invalid` / a field
error) WITHOUT wiping the in-progress edit.

2.4 **(fixes 1.4 / D3)** WHEN the application form is rendered at any viewport width THEN the field
groups SHALL reflow responsively (e.g. `auto-fit` / `minmax(...)` capped at the authored column
count) rather than staying N-up until a single 480px collapse, in BOTH
`sam/shared/page_styles/__init__.py` and `frontend/.../pageStyles.ts`, kept in parity.

2.5 **(fixes 1.5 / D6)** WHEN the admin preview and the published form are produced for the same
resolved columns value THEN the preview's ACTUAL grid behavior (the element laid out, the track
count, AND the reflow breakpoint) SHALL match the published artifact's actual grid behavior, and a
parity test SHALL assert this by comparing RENDERED layout, not CSS strings.

2.6 **(fixes 1.6 / D7)** WHEN an administrator edits extra and seven-attribute values in the same
session THEN the editor SHALL perform a single consistent re-seed of BOTH working maps (or use one
unified map) from the resolved slice after each save, so the maps never drift and no control shows a
stale value.

2.7 **(fixes 1.7 / D9)** WHEN an administrator chooses a multi-column layout THEN the `_meta`
submit group (locale + consent) SHALL remain single-column on BOTH the published form and the
preview, independent of the authored column count.

2.8 **(fixes 1.8 / D10)** WHEN the logo is rendered THEN BOTH planes SHALL emit ONE agreed `alt`
contract (the same `alt` value / semantics on the preview and the published artifact).

2.9 **(fixes 1.9 / D11)** WHEN an administrator clears a look-and-feel value versus never setting it
THEN the editor SHALL present a defined, distinguishable UI signal for "cleared" versus "inheriting
a default".

2.10 **(fixes 1.10 / D12)** WHEN an administrator chooses 3 or 4 columns and the viewport narrows
THEN the layout SHALL step down through intermediate column counts (not jump straight N→1), as a
consequence of the responsive reflow in 2.4, on both planes and in the preview.

2.11 **(fixes 1.11 / D13)** WHEN an administrator enters a logo reference that is not yet well-formed
(a bare `www.` / `http://`) THEN the editor SHALL give a client-side hint about the required form
BEFORE persisting (part of the 2.3 client validation), so no per-keystroke 422 storm occurs.

2.12 **(fixes 1.12 / D14)** WHEN an administrator enters or pastes a `header_title` longer than the
bound THEN the editor SHALL give explicit feedback that the input exceeds the limit (rather than
silently truncating), while still enforcing the 200-character bound in parity with the server.

2.13 **(fixes 1.13 / D15)** WHEN an administrator sets the form logo THEN the editor SHALL let them
UPLOAD a new image (storing it via the existing Media-Asset / image-upload path and setting `logo`
to the resulting stored reference) AND/OR pick an already-stored asset, with a pasted URL retained
only as a SECONDARY fallback; and WHEN the currently-referenced image fails to load / cannot be
copied (e.g. a 404) THEN the editor SHALL prompt the administrator to store a new image rather than
leaving a dead reference. The upload MUST reuse the existing asset path (not a new subsystem), be
scoped to the verified tenant, and the stored reference MUST satisfy the same values-only `logo`
validation (2.3/2.11).

### Unchanged Behavior (Regression Prevention)

The fix must preserve everything the editor, the publish path, and the capability already do
correctly — the publish threading, the applicant submit contract, the resolved GET/PUT contract, the
supported-attribute vocabulary, tenant isolation, and the landing-page CSS classes.

3.1 WHEN an applicant submits the published form THEN the system SHALL CONTINUE TO run the existing
client-side required / format (EMAIL / IBAN) checks and POST the existing JSON submit contract to
`POST {public_api_base}/public/members/{slug}/applications`, unchanged.

3.2 WHEN the published form is rendered THEN the system SHALL CONTINUE TO render exactly the
applicant-visible fields, functional-group sections, locale selector, and consent control that
`get_public_field_config` exposes today, with the same server-authoritative filtering and escaping —
the `_meta` single-column change (2.7) SHALL affect LAYOUT only, not which controls render.

3.3 WHEN the SAM publish path resolves and renders look-and-feel THEN it SHALL CONTINUE TO thread
`columns` into the grid CSS, pop `logo`/`header_title` from `brand` before Layer-2, pass them as
explicit escaped render params, and propagate an `UnsupportedAttributeError` before the artifact
write — the already-correct publish behavior is not re-opened.

3.4 WHEN the look-and-feel edge handles a GET or a PUT THEN it SHALL CONTINUE TO return the resolved
`{settings}` shape on BOTH (the already-fixed spec-15 defect 1.8) — this bugfix changes only the
CLIENT's split/merge bookkeeping (2.6), not the edge contract.

3.5 WHEN the Layer-2 generator is given a settings mapping THEN it SHALL CONTINUE TO support exactly
the ten attributes it supports today (`color_primary`, `color_accent`, the fonts, spacing, radius,
shadow, plus `columns`, and `logo`/`header_title` as renderer-consumed values) and SHALL CONTINUE
TO reject an unsupported attribute by raising.

3.6 WHEN a Tenant has no resolved `Look_And_Feel_Settings` (or an incomplete set) THEN the published
form and the Admin_Preview SHALL CONTINUE TO render using the SAM-owned Layer-2 defaults for each
unset attribute, without failing.

3.7 WHEN the Publish_Step resolves `Look_And_Feel_Settings` THEN it SHALL CONTINUE TO read them
exclusively from SAM-owned state scoped to the verified `tenant_id`, with no runtime read of or call
to the Flask landing plane, and no cross-tenant leakage.

3.8 WHEN the existing SAM landing-page classes (`.hero`, `.cta`, `.btn`, `.pricing-card`, the
gallery / faq grids, …) are styled by the Layer-2 generator THEN the system SHALL CONTINUE TO emit
those rules unchanged — the responsive-reflow change (2.4) applies to the application-form grid
only, so a future SAM landing page is unaffected.

3.9 WHEN a value is persisted THEN the system SHALL CONTINUE TO write values-only via the existing
path-scoped Change-Op on the `look_and_feel` slice (never generated CSS, never a whole-record write),
scoped to the verified tenant, leaving unrelated slices (`fields` / `overrides` / slug /
publish-state) untouched.

## Additional in-scope requirements (found while testing)

### R-A: Deliberate commit model + client-side validation (editor usability)

The editor's interaction model MUST change from persist-per-keystroke-with-disable-all to a live
preview on change plus a DELIBERATE persist on blur / explicit commit (or debounced), with the
in-flight flag driving only an indicator / Save affordance and NEVER `isDisabled` on the active
field (covers D1/D2/D4). Client-side validation MUST run against the SAME enum maps / patterns the
`LookAndFeelSettingsService` uses, before any persist, and surface the offending control inline on
failure without wiping the edit (covers D5/D8/D13/D14/D11). All frontend planes
(`LookAndFeelEditor.tsx`, `ApplicationFormBuilder.tsx`) with paired BEHAVIOR tests that drive real
multi-character keystrokes and toggle the in-flight flag.

### R-B: Responsive reflow in parity across both page_styles planes (responsive layout)

Both Layer-2 planes (`sam/shared/page_styles/__init__.py` and `frontend/.../pageStyles.ts`) MUST
emit a responsive application-form grid that reflows between the authored column count and one column
(e.g. `auto-fit` / `minmax(...)` capped at the authored columns), replacing the single hard 480px
collapse, kept in cross-plane parity (covers D3/D12). Paired BEHAVIOR tests MUST assert actual reflow
at intermediate widths, not CSS-string equality.

### R-C: Preview is WYSIWYG for columns + meta/alt parity (preview/published parity)

The preview MUST lay out columns through a mechanism whose ACTUAL behavior (element, track count,
reflow breakpoint) matches the published artifact's, and a parity test MUST compare RENDERED layout
rather than generator strings (covers D6). The `_meta` submit group MUST stay single-column on both
planes (covers D9), and the logo `alt` contract MUST agree across both planes (covers D10). The SAM
render plane owns the `_meta` and `alt` emission; the frontend preview plane owns the preview grid;
each gets paired BEHAVIOR tests.

### R-D: Single consistent re-seed of both working maps (authoring round-trip bookkeeping)

The builder MUST re-seed BOTH working maps (or adopt one unified map) from the resolved slice after
every save, so the seven-map and the extra-map stay a clean partition of the resolved state and a
mixed editing session never drifts (covers D7). Paired BEHAVIOR test MUST assert the maps stay a
clean partition after an interleaved extra + seven-attribute save session.

### R-E: Logo upload / asset-pick via the existing Media-Asset path (logo storability)

The `logo` control MUST stop being paste-only. The editor MUST let an administrator UPLOAD an image
(reusing the existing `uploadImage()` -> `POST /api/landing/images/upload` multipart path and the
Media-Asset / `s3_assets` registry, and/or `backend/routes/storage.py` `upload_logo` /
`get_presigned_url` — NOT a new subsystem), which stores the file scoped to the verified tenant and
sets `logo` to the returned stored reference; AND/OR pick an already-stored asset; with a pasted URL
kept only as a secondary fallback. WHEN the referenced image 404s / cannot be copied, the control
MUST surface an 'upload a new image' action. The stored reference MUST satisfy the same values-only
`logo` validation as a typed reference (covers D15). All-planes: the frontend editor upload/pick UI
plane plus whichever existing asset endpoint is reused (the design decides reuse of
`/api/landing/images/upload` vs a members-scoped asset route), with paired BEHAVIOR tests that drive
an upload and assert `logo` is set to the stored reference and the published/preview logo resolves.
