# Requirements Document

## Introduction

This feature introduces a generic, autonomous look-and-feel capability on the SAM plane that can
style any HTML page SAM produces — the member application form today, the landing page once it
becomes a SAM function, and future pages. The capability is a reusable SAM function, not a
per-feature bolt-on, and it owns its own styling tooling so it never depends on the Flask landing
plane at runtime (the no-sharing rule between the two planes, ADR 0005: SAM reads only its own
projection).

SAM authors and owns this configuration itself: it writes its own Look_And_Feel_Settings rather
than consuming a one-directional projection of Flask-authored branding (the existing projection
interface has proven too weak to depend on; see Requirement 8).

The capability covers four concerns: (1) SAM-owned look-and-feel settings for a page, authored and
managed on the SAM plane; (2) SAM owning the styling LOGIC itself — reimplemented or relocated to a SAM-owned
home rather than sourced from a Flask-plane module — so SAM can evolve its own page styling
autonomously without depending on the Flask landing plane; (3) applying those settings to the
published application form, resolving the current defect where changing look-and-feel settings has
no observable effect on the published form; and (4) the admin live preview reflecting the same
look-and-feel settings that will be published, so what the administrator sees while authoring
matches the published page. Per-page look and feel is a first-class outcome: the application form
may legitimately differ from the landing page. Pages do NOT inherit each other's look
automatically; an administrator may optionally COPY one Page's look-and-feel settings to another as
a one-time snapshot, after which the Pages remain independent (see Requirement 9).

This document defines WHAT the capability must do. It deliberately does not decide the data model,
the storage location, how settings are authored, whether the SAM-owned styling logic is a clean
reimplementation versus a relocation of the existing logic, or how this relates to or supersedes
the existing Flask `landing_page` branding — those are open design questions (see Assumptions and
Open Questions).

## Glossary

- **SAM_Plane**: The SAM-backed module plane (API Gateway → Lambda handler → domain service →
  repository → DynamoDB) under `sam/**`. Reads only its own projection; never calls the Flask plane
  at runtime.
- **Flask_Landing_Plane**: The Flask/MySQL plane that owns the existing `landing_page` parameter
  namespace and the landing-page branding settings. A separate plane from SAM_Plane.
- **Look_And_Feel_Capability**: The generic, reusable SAM-plane function this feature introduces,
  which produces page styling for any HTML page SAM produces.
- **Look_And_Feel_Settings**: The SAM-owned set of styling attributes for a single page (the set
  the capability reads to produce styling). The attributes supported today by the styling logic are
  color_primary, color_accent, font_heading, font_body, base_spacing, border_radius_global, and
  shadow_style.
  > **Note (extended to ten):** this set of seven was deliberately extended to **ten** by the
  > `bugfix-published-form-styling` bugfix (see
  > `.kiro/specs/Members/15 - sam-page-look-and-feel/bugfix-published-form-styling/`), which added
  > three further values-only attributes — `logo` (URL / asset reference), `header_title` (escaped
  > heading text), and `columns` (bounded enum / integer driving the layout). See that bugfix spec
  > for the rationale and the all-planes rollout.
- **Styling_Logic**: The CSS-generation logic that turns a styling-attribute set into CSS. It
  originates as the Flask landing-page logic (`LandingPageStyles`), today vendored into the SAM
  Members layer; this feature makes it SAM-owned (reimplemented or relocated) so it is no longer
  sourced from a Flask-plane module. It is the server-side (Python) styling path for the published Page; the Admin_Preview renders separately in React (see Requirement 7).
- **Application_Form**: The published, slug-addressed static application-form page rendered on
  SAM_Plane and served from the public-pages hosting.
- **Landing_Page**: The tenant's public landing page. Today it is produced by Flask_Landing_Plane;
  the longer-arc intent is for it to become a SAM function that uses Look_And_Feel_Capability.
- **Page**: Any HTML page SAM produces that can be styled by Look_And_Feel_Capability (the
  Application_Form today, the Landing_Page as a future SAM function, and future pages).
- **Publish_Step**: The SAM publish action that renders a Page into its served artifact
  (`application_publish.py` for the Application_Form).
- **Admin_Preview**: The authoring-time live preview of a Page shown in the admin UI (today the
  React `ApplicationFormRenderer`), distinct from the published artifact.
- **Tenant**: An isolated customer context, identified on SAM_Plane by the verified `tenant_id`.

## Requirements

### Requirement 1: Generic, reusable look-and-feel capability

**User Story:** As a platform maintainer, I want a single reusable SAM look-and-feel capability, so that every page SAM produces is styled through one function rather than per-feature styling code.

#### Acceptance Criteria

1. THE Look_And_Feel_Capability SHALL expose exactly one reusable function that accepts a set of Look_And_Feel_Settings for one Page and returns that Page's styling output.
2. WHEN a Page requests styling with a set of Look_And_Feel_Settings, THE Look_And_Feel_Capability SHALL produce styling output derived solely from the Look_And_Feel_Settings supplied for that Page.
3. WHERE a Page requests styling with an absent or incomplete set of Look_And_Feel_Settings, THE Look_And_Feel_Capability SHALL produce styling using the Styling_Logic's default value for each unset attribute.
4. THE Look_And_Feel_Capability SHALL be invoked by two or more distinct Page types through the same single styling function, without any Page-type-specific copy or variant of that function.
5. WHEN two different Pages each request styling with identical Look_And_Feel_Settings, THE Look_And_Feel_Capability SHALL produce identical styling output for both Pages.

### Requirement 2: SAM-owned settings and autonomy (no-sharing rule)

**User Story:** As a platform maintainer, I want the look-and-feel settings owned and resolved entirely on the SAM plane, so that styling works without any runtime dependency on the Flask landing plane.

#### Acceptance Criteria

1. WHEN the Look_And_Feel_Capability resolves Look_And_Feel_Settings, THE Look_And_Feel_Capability SHALL read those settings exclusively from SAM_Plane-owned state and SHALL NOT include any attribute value originating from Flask_Landing_Plane.
2. WHILE producing styling for a Page, THE Look_And_Feel_Capability SHALL NOT read from or call Flask_Landing_Plane at runtime.
3. THE Look_And_Feel_Settings SHALL be managed on SAM_Plane.
4. WHEN Look_And_Feel_Settings are resolved for a request whose Tenant is verified, THE Look_And_Feel_Capability SHALL scope the resolved settings to that verified Tenant and SHALL exclude any settings belonging to another Tenant.
5. IF Look_And_Feel_Settings are requested for a request whose Tenant cannot be verified, THEN THE Look_And_Feel_Capability SHALL NOT resolve any Tenant's settings and SHALL return a result indicating the Tenant could not be verified, leaving SAM_Plane-owned state unchanged.

### Requirement 3: SAM-owned styling logic

**User Story:** As a platform maintainer, I want the styling logic owned on the SAM plane, so that the capability does not depend on a Flask-plane module and SAM can evolve its own page styling autonomously.

#### Acceptance Criteria

1. THE Styling_Logic used by the Look_And_Feel_Capability SHALL be owned on SAM_Plane (reimplemented or relocated to a SAM-owned location), and SHALL NOT depend on a Flask-plane module as its source of truth, including as a build-time vendored copy.
2. THE Look_And_Feel_Capability SHALL support exactly the following styling attributes: color_primary, color_accent, font_heading, font_body, base_spacing, border_radius_global, and shadow_style. *(Extended to ten by the `bugfix-published-form-styling` bugfix, which added the values-only attributes `logo`, `header_title`, and `columns`; see `bugfix-published-form-styling/`. The "exactly" closed-set / unsupported-attribute rejection of criterion 4 still holds — against the now-ten set.)*
3. WHERE a Look_And_Feel_Settings attribute is absent, THE Look_And_Feel_Capability SHALL produce styling using the SAM-owned Styling_Logic's default value for that attribute.
4. IF a provided Look_And_Feel_Settings attribute is not one of the supported attributes listed in criterion 2, THEN THE Look_And_Feel_Capability SHALL reject the request, SHALL return an error indicating the unsupported attribute, and SHALL produce no Page styling for that request.
5. WHEN the Look_And_Feel_Capability produces a Page's styling, THE Look_And_Feel_Capability SHALL produce it entirely from SAM_Plane-owned code with no runtime call to the Flask plane.

### Requirement 4: Per-page look and feel

**User Story:** As a tenant administrator, I want each page to be able to have its own look and feel, so that the application form can look different from the landing page when that is the intent.

#### Acceptance Criteria

1. THE Look_And_Feel_Capability SHALL accept a distinct set of Look_And_Feel_Settings for each Page independently, such that a change to one Page's Look_And_Feel_Settings does not alter any other Page's Look_And_Feel_Settings.
2. WHEN two Pages are supplied Look_And_Feel_Settings that differ in at least one setting value, THE Look_And_Feel_Capability SHALL produce rendered styling for the two Pages that differs in at least the corresponding styling attribute.
3. WHERE two Pages are supplied Look_And_Feel_Settings that are identical in every setting value, THE Look_And_Feel_Capability SHALL produce rendered styling that is identical across all styling attributes for both Pages.
4. WHERE a Page is supplied no Look_And_Feel_Settings or an incomplete set of Look_And_Feel_Settings, THE Look_And_Feel_Capability SHALL apply the Styling_Logic's default for each unset setting and render the Page without failing.
5. IF a Page is supplied a Look_And_Feel_Setting whose value is outside its permitted set of values, THEN THE Look_And_Feel_Capability SHALL reject the invalid setting, retain the Page's previously stored Look_And_Feel_Settings unchanged, and return an indication identifying the rejected setting.

### Requirement 5: Apply settings to the published application form (resolve the current defect)

**User Story:** As a tenant administrator, I want my configured look-and-feel settings to appear on my published application form, so that changing the settings has a visible effect on the live form.

#### Acceptance Criteria

1. WHEN the Publish_Step renders the Application_Form for a request, THE Publish_Step SHALL supply the Look_And_Feel_Settings resolved for the verified Tenant of that request to the Look_And_Feel_Capability.
2. WHEN a Tenant publishes the Application_Form, THE published Application_Form SHALL carry the styling produced by the Look_And_Feel_Capability from that Tenant's resolved Look_And_Feel_Settings.
3. WHEN a Tenant changes the value of a Look_And_Feel_Settings attribute and republishes the Application_Form, THE published Application_Form SHALL carry styling for that attribute that differs from the styling carried before the change.
4. WHERE a Tenant has no resolved Look_And_Feel_Settings, THE published Application_Form SHALL carry the styling produced by the Look_And_Feel_Capability from the Styling_Logic's defaults.
5. IF the Look_And_Feel_Capability fails to produce styling during the Publish_Step, THEN THE Publish_Step SHALL NOT replace the previously published Application_Form and SHALL return a failure indication to the caller.

### Requirement 6: Landing page as a future SAM function (intent)

**User Story:** As a platform maintainer, I want the capability designed so the landing page can later become a SAM function that uses it, so that one styling capability serves the landing page and the application form.

#### Acceptance Criteria

1. WHEN a Page of type Landing_Page is supplied to the Look_And_Feel_Capability, THE Look_And_Feel_Capability SHALL produce styling output using the same reusable function invoked for a Page of type Application_Form.
2. WHEN a Page of type Landing_Page and a Page of type Application_Form each carry identical Page input attributes, THE Look_And_Feel_Capability SHALL produce identical styling output for both.
3. THE Look_And_Feel_Capability SHALL produce styling for any supplied Page using only attributes carried by that Page, without reading or requiring any Application_Form-specific state.

### Requirement 7: Admin preview reflects the published look and feel

**User Story:** As a tenant administrator, I want the admin live preview of a page to reflect the same look-and-feel settings that will be published, so that what I see while authoring matches the published page.

#### Acceptance Criteria

1. WHEN the admin live preview renders a Page, THE Admin_Preview SHALL render it using the same Look_And_Feel_Settings that the Publish_Step would supply for that Page.
2. WHEN a Tenant changes a Look_And_Feel_Settings attribute, THE Admin_Preview SHALL reflect the changed attribute without requiring the Page to be published.
3. WHERE a Tenant has no resolved Look_And_Feel_Settings, THE Admin_Preview SHALL render using the same defaults the published Page would use.

> Note: Requirement 7 is about the Admin_Preview reflecting the same Look_And_Feel_Settings and resulting appearance as the published Page — NOT about using a single shared renderer. Two render paths are retained deliberately (see Assumptions and Open Questions: "Two deliberate render paths"): the published Page renders on SAM_Plane via the Python Styling_Logic, while the Admin_Preview renders in-browser via a React component so the administrator's unsaved edits appear instantly with no server round-trip (a React component cannot execute the Python server-side Styling_Logic). How the React preview reproduces the Python render output is an open design question.

### Requirement 8: SAM authors its own look-and-feel config autonomously

**User Story:** As a platform maintainer, I want the SAM plane to author and own the look-and-feel configuration itself, so that the capability does not depend on Flask authoring the config or on a one-directional projection that has proven too weak to rely on.

#### Acceptance Criteria

1. THE SAM_Plane SHALL author (create and update) the Look_And_Feel_Settings for a Page as the writer of that configuration, without requiring Flask_Landing_Plane to author it.
2. THE Look_And_Feel_Settings SHALL be owned and persisted on SAM_Plane-owned state, not resolved by reading a one-directional projection of Flask-authored configuration.
3. WHEN a Tenant updates Look_And_Feel_Settings through SAM_Plane, THE updated settings SHALL be the authoritative source for that Page's styling, with no write to or from Flask_Landing_Plane.
4. THE Look_And_Feel_Capability SHALL NOT depend on the existing Flask-to-SAM projection interface for Look_And_Feel_Settings.

### Requirement 9: Copy look-and-feel settings from another page (one-time, no inheritance)

**User Story:** As a tenant administrator, I want to copy the look-and-feel settings from one of my pages to another, so that I can start a page from an existing look without configuring every setting again — while the pages stay independent afterward.

#### Acceptance Criteria

1. WHEN an administrator copies Look_And_Feel_Settings from a source Page to a target Page, THE SAM_Plane SHALL set the target Page's Look_And_Feel_Settings to a one-time snapshot of the source Page's current Look_And_Feel_Settings.
2. WHEN the copy completes, THE target Page's Look_And_Feel_Settings SHALL be independent of the source Page's, such that a subsequent change to either Page's Look_And_Feel_Settings SHALL NOT alter the other Page's Look_And_Feel_Settings.
3. WHEN a copy is performed, THE SAM_Plane SHALL overwrite the target Page's existing Look_And_Feel_Settings with the copied values.
4. THE SAM_Plane SHALL permit a copy only when the source Page and the target Page belong to the same verified Tenant, and SHALL reject a copy whose source Page belongs to another Tenant.
5. THE copy operation SHALL NOT establish any ongoing link or inheritance between the source Page and the target Page.

## Assumptions and Open Questions

The following are deliberately NOT resolved in these requirements — they are design concerns the
user has not decided. They are recorded so the requirements stay grounded without inventing
answers.

- **Settings storage and authoring** — Where SAM-owned Look_And_Feel_Settings live and how they
  are authored are open. These requirements assume only that the settings are resolvable from
  SAM_Plane-owned state (Requirement 2); they do not specify a data model, storage location, or
  authoring UI. A candidate approach (NOT yet decided) is to store the Look_And_Feel_Settings — the
  attribute VALUES, not generated CSS — on the Page's own definition record, so each Page owns its
  look and the CSS is (re)generated from those values by the Styling_Logic at render/publish time.
  Whether to store the attribute values versus a generated-CSS snapshot, and the exact record, are
  design decisions.
- **How the styling logic becomes SAM-owned** — The decision is that the Styling_Logic is
  SAM-owned (Requirement 3): reimplemented or relocated to a SAM-owned location rather than sourced
  from a Flask-plane module. WHICH of those (clean reimplementation versus relocating/extracting the
  existing logic to a SAM-owned shared home), and how the admin React preview achieves parity with
  the Python render output (Requirement 7) given it cannot execute the same server-side logic, are
  open DESIGN decisions.
- **Two deliberate render paths** — The published Page is rendered on SAM_Plane by the Python Styling_Logic (the `LandingPageStyles` CSS path), while the Admin_Preview is rendered in-browser by a React component (`ApplicationFormRenderer`). This split is INTENTIONAL and retained: the preview must show the administrator's UNSAVED edits instantly with no server round-trip (an earlier server-round-trip preview was removed for returning empty fields on unsaved drafts), and an instant in-browser render requires React, which cannot execute the Python server-side Styling_Logic. Requirement 7's parity is therefore about SAME settings and resulting appearance, not one shared renderer. HOW the React preview reproduces the Python Styling_Logic output (e.g. generating and injecting the CSS, or a shared cross-language styling source) is an open DESIGN decision. A candidate approach (NOT yet decided) to resolve this WITHOUT a second renderer is to have the Admin_Preview display the REAL rendered artifact produced by the SAM Python Styling_Logic — e.g. the rendered HTML opened from a local file or served from a SAM preview endpoint and embedded via an iframe (`src` or `srcdoc`) — rather than re-rendering the Page in React; this eliminates the cross-language parity problem entirely (the admin sees the actual output) at the cost of the instant no-round-trip unsaved-edit preview the current React path provides (seeing an unsaved change would require re-rendering via SAM). Note: a browser opens a local `.html` file natively (no extra software), but a `file://` page cannot make live backend calls, so a local-file example is static only. Which approach to take is an open DESIGN decision.
- **Migration and relationship with existing Flask landing-page settings** — The direction is that SAM AUTHORS its own Look_And_Feel_Settings (Requirement 8), rather than consuming a one-directional projection of the Flask-authored `landing_page` branding (the existing projection interface has proven too weak to depend on). HOW the existing Flask `landing_page` branding is migrated or seeded into SAM-owned state (one-time backfill, dual-write during transition, or a clean start), and the transition sequencing, are open DESIGN decisions. These requirements require only that the authoritative settings be SAM-owned and SAM-authored (Requirements 2 and 8).
- **Supersession of the existing `landing_page` branding** — Whether Look_And_Feel_Capability
  supersedes or absorbs the existing `landing_page` branding is open and out of scope for these
  requirements.

## Governance and Steering Impact

Per steering 40 (spec-workflow) governance definition-of-done, any steering or ADR this feature changes MUST be updated to match as part of this spec's completion:

- **Steering 36 (config & parameters)** — This feature SUPERSEDES, for SAM-owned look-and-feel config, steering 36's current model ("MySQL `parameters` is the single source of truth; Flask authors it; SAM reads a one-directional projection; never two writers"). Under Requirement 8, SAM authors and owns its own look-and-feel config (SAM becomes a writer). Steering 36 MUST be rewritten to reflect SAM config-authoring autonomy for SAM-owned config, and to record that the previous one-directional projection interface was too weak to depend on.
- **Related steering/ADRs** — Any related steering that assumes Flask-writes/SAM-reads for this config (e.g. 35 SAM module architecture, 39 SAM data access, and the relevant projection ADRs 0005/0006) MUST be reviewed and updated for consistency where they govern SAM-owned config authoring. The exact edits are a design/implementation concern; the OBLIGATION to update them is in scope here.

## Out of Scope

- Any runtime communication between Flask_Landing_Plane and SAM_Plane (the no-sharing rule).
- Migrating the Flask landing page to a SAM function (only the capability's readiness for that future, Requirement 6, is in scope).
