# Bugfix Requirements Document

## Introduction

In the Members Application Form Builder (`ApplicationFormBuilder.tsx`), per-field application
attributes authored on a tenant-added field — for example setting IBAN or `payment_method` to
"Verplicht op formulier" (`application_required`) and "Formaatcontrole" = IBAN (`format.checker`)
— are saved and persist in storage, but after a page refresh the builder shows the per-field
toggles back at their platform defaults (required = No, format empty). The settings are stored
and served correctly; only the builder's on-load seeding is wrong, so the UI misrepresents the
saved state. This also corrupts the save diff baseline, so a fresh (unedited) load is treated as
dirty and a single edit can produce an incorrect change set.

This is a FRONTEND-only bug. The write persists (`test_governance_projection` `h-dcn`
`config#fields` row carries `fields.iban.application_required = true`, `format.checker = "IBAN"`,
etc.) and the deployed TEST `members-test` Lambda read serves these attributes inside each
resolved `fields[]` entry. The defect is entirely in how the builder seeds its in-memory working
overlay from the resolved field config on load.

## Bug Analysis

### Current Behavior (Defect)

`ApplicationFormBuilder.load()` seeds its working overlay and diff baseline from
`cfg.field_overlay`, which the current SAM module read no longer surfaces (it is `undefined`).
The working overlay and baseline are therefore seeded to `{}`, so per-field panels find no
authored entry and fall back to platform defaults.

1.1 WHEN the builder loads a resolved field config whose `field_overlay` key is absent (the
current module read) and whose `fields[]` contains a tenant-added field with authored application
attributes (e.g. `iban` with `application_required: true`, `format: {checker: "IBAN"}`) THEN the
system seeds the working overlay to `{}` and the per-field attribute panel shows the required
toggle unchecked and the format select empty.

1.2 WHEN the builder loads a resolved field config whose `field_overlay` key is absent THEN the
system sets the save diff baseline to `JSON.stringify({})`, so the baseline does not reflect the
authoritative stored attributes carried in `fields[]`.

### Expected Behavior (Correct)

2.1 WHEN the builder loads a resolved field config whose `field_overlay` key is absent and whose
`fields[]` contains a tenant-added field with authored application attributes THEN the system
SHALL seed the working overlay by reconstructing it from the resolved `fields[]` /
`functional_groups` (via `flatViewToOverlay(cfg)`), so the per-field attribute panel shows the
required toggle checked and the format select value set to the stored `format.checker` (e.g.
`IBAN`), matching the stored and served state.

2.2 WHEN the builder loads a resolved field config whose `field_overlay` key is absent THEN the
system SHALL set the save diff baseline to `JSON.stringify(flatViewToOverlay(cfg))`, the same
reconstruction used to seed the working overlay, so a fresh unedited load is not dirty and a
single field edit produces exactly one `set_field_application` Change-Op.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the builder loads a resolved field config whose `fields[]` carry NO authored application
attributes THEN the system SHALL CONTINUE TO present the per-field panels at platform defaults and
SHALL CONTINUE TO treat a fresh unedited load as not dirty (empty save diff).

3.2 WHEN a single per-field application attribute is edited after a fresh load THEN the system
SHALL CONTINUE TO produce exactly one `set_field_application` Change-Op for the touched field on
Save, with the server owning storage placement.

3.3 WHEN the resolved field config is loaded THEN the system SHALL CONTINUE TO seed the form-shell
values (slug/URL display, embed, consent) from `config#mail` and the SAM `cfg.slug` exactly as
before — this fix touches only the field-overlay seeding, not the form-shell seeding.
