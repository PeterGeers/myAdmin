# Bugfix Requirements Document

## Introduction

The h-dcn Members read-only view modal (`MembersViewBody`) presents four field discrepancies
against the import mapping contract (`scripts/aws/h-dcn/members_source_mapping.csv`, the single
source of truth). The modal renders the RESOLVED field set — fixed base ⊕ tenant overlay ⊕
calculated — where the overlay portion is authored in `scripts/aws/h-dcn/members_config.json`
(`field_overlay.fields`) and seeded into MySQL by `scripts/aws/seed-hdcn-members-config.py`. The
modal shows every declared, `visible` overlay field regardless of whether the import mapping
actually writes data to it — EXCEPT where a field-level `show_when` gate suppresses it for the
member being viewed.

Four distinct problems are observed, each with a different suspected root cause:

1. **Newsletter preference not displayed** — a mapped field (`newsletter_pref`) that exists in
   both the mapping contract and the config, whose value does not appear in the modal.
2. **"Datum ondertekening" field present but broken** — an overlay field (`signature_date`)
   declared in the config that the mapping contract does NOT target; per the contract, signature
   info belongs concatenated into `overlay.additional_info`, not as a standalone modal field.
3. **Unexpected "Privacy" field** — an overlay field (`privacy_consent`, `required: true`)
   declared in the config with NO corresponding source column anywhere in the mapping contract —
   an orphan field with no import backing.
4. **"WieWatWaar" field not displayed** — a mapped field (`referral_source`, label nl
   "Wie/wat/waar") that exists in both the mapping contract and the config AND whose value IS
   imported, but which is hidden in the view modal by a field-level `show_when` gate that only
   renders it on the create/new-member form.

Investigation notes that inform the requirements (data-flow provenance):
- The modal (`frontend/src/components/members/MembersViewBody.tsx`) renders whatever the resolved
  field config lists, sectioned by each field's `functional_group`, reading each value via
  `valueFor(member, group, key)` → `member.overlay[key]`. It does not filter by "has a mapping".
  So an overlay field declared in the config appears in the modal whether or not the importer
  ever writes it — problems 2 and 3 are **config-vs-mapping definition mismatches** (orphan
  overlay fields), not frontend display bugs.
- The importer transform (`sam/members/migration/hdcn_backfill.py`, `map_hdcn_row`) matches
  source columns **by header NAME** (base header, lower-cased), NOT by `col_index`. The
  `col_index` column in the CSV is documented as an audit aid / disambiguator only. Therefore the
  "SAM Code inserted at col 0, so add +1" concern does NOT affect importer matching — matching is
  keyed on the header text (`"Digitale nieuwsbrieven"`), not the numeric position. This is a
  scoping fact captured to keep the fix from chasing a non-cause.
- `newsletter_pref` is mapped with the `single` rule, which copies the raw source cell verbatim
  (`"Ja"`/`"Nee"`) onto `overlay.newsletter_pref`, while the config enum declares lowercase
  choices `ja`/`nee`. The modal's `renderFieldValue` stringifies the stored value as-is (no
  choice→label mapping), so a stored value would still render. Problem 1 is therefore an
  **importer data-flow / stored-value** concern (value not written, or a live-sheet header /
  value-shape mismatch), NOT a frontend display bug.
- `referral_source` (mapping row `WieWatWaar,27,overlay.referral_source,single,How did you find us
  (free text)`) is a DIFFERENT class of problem from `newsletter_pref`. Here the value IS mapped
  and IS imported onto `overlay.referral_source`, and the field IS declared + `visible` in
  `members_config.json` (type `string`, label nl "Wie/wat/waar", `functional_group: membership`).
  The reason it does not appear in the view modal is a **config visibility-gate** problem: the
  config authors `referral_source` with `show_when: {"field": "member_id", "op": "not_exists"}`
  (per decision D10 — "shown only on the new-member form"). The view modal
  (`MembersViewBody.tsx`) filters every section's fields through
  `evaluateShowWhen(f.show_when, flat)` (the same predicate the form + server use), so for an
  EXISTING member — whose flattened row DOES carry a `member_id` — the gate resolves to hidden and
  the imported historical value is never rendered. (Note: `evaluateShowWhen` in `fieldForm.ts`
  treats `show_when` as a map of `{controllingKey: expected}` and ANDs every entry; against the
  `{"field": ..., "op": ...}` shape it requires the flat row to have a `field` key equal to
  `"member_id"` and an `op` key equal to `"not_exists"`, which an existing member's data never
  satisfies — so the field is suppressed in the view modal regardless of interpretation.) The open
  question is whether hiding `referral_source` in the READ-ONLY view modal is intended (it was
  authored as create-form-only per D10) or a bug: the imported historical value cannot be seen
  when viewing an existing member. Unlike the newsletter problem (a data-flow / stored-value
  concern), this is a **config visibility-gate** concern — a mapped, imported field deliberately
  gated out of the view. The fix decision (remove or adjust the `show_when` gate so the stored
  value renders for existing members in the view modal) is to be finalized in design.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a member has a value for the source column `Digitale nieuwsbrieven` (mapped to
    `overlay.newsletter_pref`) THEN the modal does NOT display any newsletter preference value
    (renders the empty-cell dash).

1.2 WHEN the overlay field `signature_date` (label "Datum ondertekening", type date, functional
    group administrative) is declared in `members_config.json` THEN the modal renders a standalone
    "Datum ondertekening" field even though the mapping contract has NO `overlay.signature_date`
    target.

1.3 WHEN a member's source row carries signature information (source column `Ondertekening`,
    disposition `(additional_info)`) THEN that data is neither shown in the modal's "Datum
    ondertekening" field NOR concatenated into the "Aanvullende informatie"
    (`overlay.additional_info`) field as the contract specifies.

1.4 WHEN the overlay field `privacy_consent` (label "Privacy", enum, `required: true`) is declared
    in `members_config.json` THEN the modal renders a "Privacy" field even though NO source column
    in `members_source_mapping.csv` maps to `overlay.privacy_consent` (an orphan overlay field
    with no import backing).

1.5 WHEN the mapping contract is loaded and validated THEN the drift guard only rejects a
    `overlay.*` mapping target that is NOT declared in the config; it does NOT flag a config
    overlay field that has NO mapping backing, so orphan fields (`signature_date`,
    `privacy_consent`) pass validation unnoticed.

1.6 WHEN an EXISTING member (whose flattened row carries a `member_id`) is viewed in the read-only
    modal AND that member has an imported value for `overlay.referral_source` (source column
    `WieWatWaar`, label "Wie/wat/waar") THEN the modal does NOT display the "Wie/wat/waar" value,
    because the field's `show_when` gate (`{"field": "member_id", "op": "not_exists"}`, authored
    per D10 as create-form-only) filters it out via `evaluateShowWhen` even though the value IS
    imported and the field IS declared and `visible`.

### Expected Behavior (Correct)

2.1 WHEN a member has a value for the source column that maps to `overlay.newsletter_pref` THEN
    the system SHALL display that newsletter preference value in the modal (the mapped value is
    written to `overlay.newsletter_pref` on import and rendered in the modal).

2.2 WHEN the mapping contract does NOT target `overlay.signature_date` THEN the system SHALL NOT
    render a standalone "Datum ondertekening" field in the modal (the orphan `signature_date`
    overlay field is removed from `members_config.json` and no longer seeded/resolved).

2.3 WHEN a member's source row carries signature information (`Ondertekening` /
    `Naam voor akkoord`, disposition `(additional_info)`) THEN the system SHALL concatenate that
    data into `overlay.additional_info` as `Label: value` pairs (per the contract) and display it
    in the modal's "Aanvullende informatie" field.

2.4 WHEN no source column maps to `overlay.privacy_consent` THEN the system SHALL NOT render a
    "Privacy" field in the modal — either the orphan `privacy_consent` overlay field is removed
    from `members_config.json`, or a source column is added to the mapping contract to back it
    (decision to be captured in design).

2.5 WHEN the mapping contract and the config are validated together THEN the system SHALL surface
    any config overlay field that has NO mapping backing (an orphan-field guard), so a
    config-vs-mapping mismatch is detected rather than silently rendering an empty modal field.

2.6 WHEN an EXISTING member has an imported value for `overlay.referral_source` (source column
    `WieWatWaar`, label "Wie/wat/waar") THEN the read-only view modal SHALL display that stored
    value — the `show_when` visibility gate on `referral_source` is removed or adjusted so the
    imported historical value renders for existing members in the view (the create-form-only
    behavior authored per D10 no longer suppresses the value when VIEWING an existing member; the
    exact gate change — drop the gate, scope it to the create form only, or split view/edit
    visibility — is to be finalized in design).

### Unchanged Behavior (Regression Prevention)

3.1 WHEN an overlay field is declared in `members_config.json` AND is backed by a source column in
    the mapping contract (e.g. `magazine_pref`, `motor_brand`, `region`, `notes`,
    `deregistration_date`, `termination_date`) THEN the system SHALL CONTINUE TO render it in the
    modal with its stored value.

3.2 WHEN the importer matches a source column to its target THEN the system SHALL CONTINUE TO match
    by header NAME (base header, lower-cased), NOT by `col_index`, so the "SAM Code" column
    inserted at position 0 does not require any col_index shift in matching logic.

3.3 WHEN a member's source row contributes leftover columns already routed to
    `(additional_info)` (e.g. `Naam voor akkoord`) THEN the system SHALL CONTINUE TO concatenate
    those into `overlay.additional_info` in stable source-column order with the ` | ` delimiter.

3.4 WHEN the modal renders the resolved field set THEN the system SHALL CONTINUE TO section fields
    by their parameter-driven `functional_group`, honor field-level `visible` and `show_when`
    gates, and present dates/enums/calculated values via the shared `renderFieldValue` formatter.

3.5 WHEN an overlay `date` field that IS backed by the mapping (e.g. `deregistration_date`,
    `termination_date`) has a stored value THEN the system SHALL CONTINUE TO display it, so
    removing the orphan `signature_date` field does not affect the legitimately mapped date
    overlay fields.

3.6 WHEN any OTHER field carries a `show_when` gate (a field legitimately conditional on another
    field's value) THEN the system SHALL CONTINUE TO honor that gate via `evaluateShowWhen` in the
    view modal, so adjusting only `referral_source`'s visibility does not change conditional
    visibility for the rest of the resolved field set.

3.7 WHEN a NEW member is entered on the create/add-member form THEN the system SHALL CONTINUE TO
    present the `referral_source` ("Wie/wat/waar") input as a free-text field per D10, so making
    the imported value visible in the read-only view does not remove the ability to capture it on
    the new-member form.
