# Bugfix Requirements Document

## Introduction

Spec 15 — **SAM Page Look-and-Feel** (`.kiro/specs/Members/15 - sam-page-look-and-feel/`) — was
marked delivered on branch `test` (PRs #208 / #209 / #210 merged, including a just-shipped fix for a
500 on legacy `config#fields` rows). Its stated purpose (spec 15 `requirements.md` Introduction,
concern 3) was to "resolve the current defect where changing look-and-feel settings has no
observable effect on the published form", and it promised two user-visible outcomes:

- **spec 15 Req 5.2** — "WHEN a Tenant publishes the Application_Form, THE published Application_Form
  SHALL carry the styling produced by the Look_And_Feel_Capability from that Tenant's resolved
  Look_And_Feel_Settings"; and
- **spec 15 Req 7.1** — the Admin_Preview "SHALL render it using the same Look_And_Feel_Settings that
  the Publish_Step would supply", so what the administrator sees while authoring matches the
  published page (the Req 7 note extends this to "the same Look_And_Feel_Settings **and resulting
  appearance**").

**Delivered reality (observed on deployed TEST, confirmed by reading the shipped code):** the
published / hosted application form does **not** visibly carry the look-and-feel. With distinct
look-and-feel values authored and published, the live form shows:

- no tenant logo,
- no page title / heading in the body,
- a single-column layout at **all** screen widths (no multi-column grouping), and
- primary / accent brand colours that are **not** applied to the form's own elements.

Meanwhile the admin in-browser preview (`ApplicationFormPreview.tsx`) **does** show a logo-less but
otherwise colour-and-column-styled form, so preview and published diverge — the exact thing spec 15
Req 7.1 promised would match. The look-and-feel plumbing spec 15 built (the SAM-owned Layer-2
generator, the stored `look_and_feel` slice, the publish-time resolve) runs, but it produces styling
that the application form's markup never actually consumes, and it renders no logo / title. So
spec 15 Req 5.2 and Req 7.1 were marked delivered but are **not met**. This is the bug.

This document captures the observable defect, the correct behavior spec 15 promised, and the existing
behavior that must be preserved. The design document (`design.md`) owns the grounded root-cause
investigation, the fix approach (sequenced A → B → C → D), and the preview/published unification
decision; the task breakdown (`tasks.md`) owns the all-planes + CI/CD delivery. Nothing here
prescribes implementation — it defines WHAT is broken and WHAT correct looks like.

> **Scope note — this is a spec-authoring deliverable only.** No product code, tests, or fixtures are
> changed by this document or its siblings. The user reviews the spec first.

## Bug Analysis

### Current Behavior (Defect)

With a tenant that has authored distinct `Look_And_Feel_Settings` (e.g. a vivid `color_primary` /
`color_accent`, a non-`system` heading font, `relaxed` spacing) and published its application form,
the published / hosted form does not visibly carry those settings, and preview and published diverge.

1.1 WHEN a Tenant publishes the Application_Form with resolved `Look_And_Feel_Settings` whose
`color_primary` / `color_accent` differ from the defaults THEN the published form's own elements
(form headings, the submit button, input focus state) render with their hard-coded / neutral colours
and do NOT carry the tenant's brand colours, because the Layer-2 `page_css` applies those colours only
to landing-page classes the application-form markup never uses.

1.2 WHEN a Tenant publishes the Application_Form on a wide screen THEN the published form renders its
field groups in a single column at every screen width, because the generated CSS defines no
multi-column grid for the form's field groups.

1.3 WHEN a Tenant with a configured logo publishes the Application_Form THEN the published form body
contains no logo image, because the renderer emits no logo element and the publish step supplies no
header fragment.

1.4 WHEN a Tenant publishes the Application_Form THEN the published form body contains no visible
page title / heading (only a non-visible `<title>` browser-tab element exists), because the renderer
emits no body-level title / heading.

1.5 WHEN a Tenant changes a `Look_And_Feel_Settings` value and republishes THEN the published form's
own visible elements show no corresponding change (beyond any `:root` variable a form element happens
to reference), so changing a look-and-feel setting still has no observable effect on the published
form — the defect spec 15 set out to resolve.

1.6 WHEN the admin live preview and the published form are compared for the same resolved
`Look_And_Feel_Settings` THEN the preview shows a colour-and-column-styled form while the published
form does not, because the preview's visible appearance is produced by an independent React (Chakra)
renderer rather than by the Layer-2 CSS that styles (or fails to style) the published page.

1.7 WHEN a Tenant wants to configure the form's logo, header/title text, or number of columns
THEN the admin UI provides NO data-entry control to enter and persist these — the authoring
editor exposes only the existing seven colour/font/spacing/radius/shadow attributes, so there is
no way for an administrator to supply a logo, a header/title, or a column count for the published
form at all (they cannot be authored, therefore cannot be stored, therefore cannot be rendered).

1.8 WHEN a Tenant changes a `Look_And_Feel_Settings` value in the admin editor THEN the editor
control does NOT update to show the changed value; the change becomes visible only after the data
is reloaded. Root cause (confirmed): the `PUT /members/look-and-feel` edge returns the Change-Op
write result (`{version, idempotent_replay}`), NOT a `{settings}` map, so the builder's success
handler `setLookAndFeel(res.settings ?? {})` re-seeds the working map from an absent `settings`
and BLANKS the optimistic local edit — the editor then shows the pre-edit/default value until a
fresh `getLookAndFeelSettings` load repopulates it. (A client/server response-shape mismatch
between the GET contract `{settings}` and the PUT response, compounded by discarding the
optimistic edit.)

### Expected Behavior (Correct)

The published application form must genuinely carry the tenant's resolved look-and-feel, and the admin
preview must reflect the same settings AND resulting appearance as the published page — fulfilling
spec 15 Req 5.2 and Req 7.1.

2.1 WHEN a Tenant publishes the Application_Form with resolved `Look_And_Feel_Settings` whose
`color_primary` / `color_accent` differ from the defaults THEN the published form SHALL apply those
brand colours to the form's own visible elements (at minimum the form heading / title, the submit
button, and input focus state).

2.2 WHEN a Tenant publishes the Application_Form on a wide screen THEN the published form SHALL render
its field groups in a multi-column layout, and SHALL collapse that layout to a single column on small
screens.

2.3 WHEN a Tenant with a configured logo publishes the Application_Form THEN the published form body
SHALL render the tenant's logo image.

2.4 WHEN a Tenant with a configured form title / heading publishes the Application_Form THEN the
published form body SHALL render that title / heading as a visible element.

2.5 WHEN a Tenant changes a `Look_And_Feel_Settings` value (brand colour, layout / column choice,
logo, or title) and republishes THEN the published form SHALL carry a corresponding, observable change
on the form's own elements.

2.6 WHEN the admin live preview and the published form are produced for the same resolved
`Look_And_Feel_Settings` THEN the Admin_Preview SHALL reflect the same settings AND the same resulting
appearance (brand colours on the form's own elements, multi-column layout, logo, and title) that the
published form carries.

2.7 WHEN a Tenant uses the admin look-and-feel editor THEN the UI SHALL provide data-entry
controls to enter a tenant **logo**, a form **header/title**, and the **number of columns**, and
SHALL persist those values (values-only) to SAM-owned state so they are available to the
Publish_Step and the Admin_Preview. The logo, header/title, and column-count SHALL round-trip:
a reload of the editor SHALL show the persisted values.

2.8 WHEN a Tenant changes any `Look_And_Feel_Settings` value in the admin editor THEN the editor
SHALL immediately reflect the changed value (and the live preview SHALL reflect it per Req 7.2),
WITHOUT requiring a data reload. A successful persist SHALL keep the editor showing the authored
value (the write response SHALL carry the resolved settings, or the client SHALL retain its
optimistic edit — the editor SHALL NOT blank the value after a successful save).

### Unchanged Behavior (Regression Prevention)

The fix must preserve everything the application form and the look-and-feel capability already do
correctly — the applicant-facing submit contract, the field/group/consent/locale rendering, the
seven-attribute Layer-2 contract and its parity, tenant isolation, and the publish readiness/failure
semantics.

3.1 WHEN an applicant submits the published form THEN the system SHALL CONTINUE TO run the existing
client-side required / format (EMAIL / IBAN) checks and POST the existing JSON submit contract to
`POST {public_api_base}/public/members/{slug}/applications`, unchanged.

3.2 WHEN the published form is rendered THEN the system SHALL CONTINUE TO render exactly the
applicant-visible fields, functional-group sections, locale selector, and consent control that
`get_public_field_config` exposes today, with the same server-authoritative filtering and escaping.

3.3 WHEN a Tenant has no resolved `Look_And_Feel_Settings` (or an incomplete set) THEN the published
form and the Admin_Preview SHALL CONTINUE TO render using the SAM-owned Layer-2 defaults for each
unset attribute, without failing.

3.4 WHEN the Layer-2 generator is given a settings mapping THEN it SHALL CONTINUE TO support exactly
the attributes it supports today for its existing attributes and SHALL CONTINUE TO reject an
unsupported attribute by raising, producing no styling for that request (any NEW attribute added by
this bugfix is a deliberate, documented extension of that set, covered in the design).

3.5 WHEN the Publish_Step resolves `Look_And_Feel_Settings` THEN it SHALL CONTINUE TO read them
exclusively from SAM-owned state scoped to the verified `tenant_id`, with no runtime read of or call
to the Flask landing plane, and no cross-tenant leakage.

3.6 WHEN the Layer-2 generator fails to produce styling during the Publish_Step (e.g. an unsupported
attribute) THEN the Publish_Step SHALL CONTINUE TO leave the previously published form untouched and
return a failure indication (spec 15 Req 5.5), writing no new artifact.

3.7 WHEN the existing SAM landing-page classes (`.hero`, `.cta`, `.btn`, `.pricing-card`, the
gallery / faq grids, …) are styled by the Layer-2 generator THEN the system SHALL CONTINUE TO emit
those rules unchanged, so a future SAM landing page that uses them is unaffected by the
application-form styling added here.

## Additional in-scope requirements (found while testing)

### R-A: Admin data entry + storage for logo, header/title, and column count

The admin look-and-feel authoring UI MUST let an administrator ENTER and STORE a tenant **logo**,
a form **header/title**, and the **number of columns** for the application form, as new
values-only Look_And_Feel_Settings (a deliberate, documented extension of the current
seven-attribute set). These values MUST persist to SAM-owned state (the `look_and_feel` slice via
the existing values-only Change-Op write path — never generated CSS, never a whole record), be
scoped to the verified tenant, and be consumed by BOTH the Publish_Step (so the published form
renders them — ties to 2.1–2.5) and the Admin_Preview (so the preview matches — ties to 2.6).
All planes per steering 40: Layer-2 generator / stored slice / edge validation / service /
authoring UI / preview, each with paired tests. (Covers defect 1.7 / expected 2.7.)

### R-B: Editor reflects a change immediately (no reload required)

Changing a look-and-feel value in the editor MUST update the editor (and the live preview)
immediately, without a data reload. The fix MUST resolve the response-shape mismatch behind
defect 1.8 — the `PUT /members/look-and-feel` edge SHALL return the resolved `{settings}` (the
same shape the GET returns) so the client's re-seed shows the authored value, AND/OR the client
SHALL retain its optimistic edit rather than blanking it on a successful save. A paired test MUST
assert that after a successful set the editor shows the new value with NO reload. (Covers defect
1.8 / expected 2.8.)
