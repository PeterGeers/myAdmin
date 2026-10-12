# Members Modal Field-Mapping Mismatch Bugfix Design

## Overview

The h-dcn Members read-only view modal (`MembersViewBody`) surfaces four distinct field
discrepancies against the import mapping contract (`scripts/aws/h-dcn/members_source_mapping.csv`).
The modal renders the RESOLVED field set — fixed base ⊕ tenant overlay ⊕ calculated — where the
overlay portion is authored in `scripts/aws/h-dcn/members_config.json`
(`field_overlay.fields`), seeded into MySQL by `scripts/aws/seed-hdcn-members-config.py`, and
projected to `config#fields`. The modal shows every declared, `visible` overlay field regardless
of whether the importer ever writes data to it, EXCEPT where a field-level `show_when` gate
suppresses it.

The four problems have four DIFFERENT root causes, and — critically — they live in different
layers:

| # | Field | Class | Layer |
|---|-------|-------|-------|
| 1 | `newsletter_pref` | data-flow / stored-value | importer + data (backfill / live-sheet header) |
| 2 | `signature_date` | orphan overlay field | static config (+ re-seed) |
| 3 | `privacy_consent` | orphan overlay field, `required:true` | static config (+ re-seed), CRUD-form impact |
| 4 | `referral_source` | visibility-gate (malformed `show_when`) | static config (+ re-seed) |

The fix strategy is: (a) confirm/repair the newsletter data flow, (b) delete the two orphan
overlay fields from the config and re-seed, routing signature info to `additional_info`, (c)
repair the `referral_source` visibility gate so the imported value renders in the view while the
field is still captured on the create form, and (d) add a config↔mapping orphan-field guard in
the mapping loader so this class of drift is caught at load time. Because some fixes span both the
static config file AND the seeded MySQL `members.field_overlay` param (and, for newsletter,
possibly a re-backfill of member records), the design ends with an explicit sequencing section.

## Glossary

- **Bug_Condition (C)**: The condition that triggers a given problem — see each numbered
  Correctness Property for the formal predicate.
- **Property (P)**: The desired post-fix behavior for inputs where C holds.
- **Preservation**: Existing behavior that MUST remain unchanged by the fix (the mapped,
  legitimately-backed overlay fields; header-name matching; additional_info concatenation).
- **`map_hdcn_row`** — the pure backfill transform in `sam/members/migration/hdcn_backfill.py`
  that maps one raw h-dcn sheet row to `{ personal, membership, overlay }`, matching source
  columns by BASE header (lower-cased), NOT by `col_index`.
- **`evaluateShowWhen`** — the frontend predicate in
  `frontend/src/components/members/fieldForm.ts` (mirrored server-side by `evaluate_show_when` in
  `sam/members/domain/field_resolver.py`) that treats `show_when` as a map of
  `{controllingKey: expected}`, ANDing every entry.
- **`valueFor`** — the accessor in `frontend/src/components/members/fieldValue.ts` the view uses
  to read `member.overlay[key]`.
- **Orphan overlay field** — an overlay field DECLARED in `members_config.json` that NO row in
  `members_source_mapping.csv` targets, so the importer never writes it and the modal renders an
  empty (dash) row.
- **Overlay field_overlay param** — `members.field_overlay` seeded into MySQL from the config
  file; the modal renders the PROJECTED form of this (`config#fields`), not the file directly, so
  a config edit only takes effect after a re-seed + projection sync.

## Bug Details

### Bug Condition

Four independent conditions. Each is formalized below; the common thread is a mismatch between
what the config DECLARES as a visible overlay field and what the mapping contract actually WRITES
(or, for problem 4, what the visibility gate permits).

**Formal Specification (problem 1 — newsletter data flow):**
```
FUNCTION isBugCondition_newsletter(member, sourceRow)
  INPUT:  member of type Member, sourceRow of type raw h-dcn row
  OUTPUT: boolean

  RETURN sourceRow has a non-empty cell under the live-sheet header for newsletter
         AND member.overlay.newsletter_pref is absent/empty in the stored record
END FUNCTION
```
The mapping row `Digitale nieuwsbrieven,36,overlay.newsletter_pref,single` DOES map the column,
and `map_hdcn_row` copies the raw cell verbatim onto `overlay.newsletter_pref`. So a correctly
imported record SHOULD carry the value. The bug is therefore that the value did NOT reach
`overlay.newsletter_pref` for the records currently in the modal — a data-flow / stored-value
concern, not a display bug (see Hypothesized Root Cause).

**Formal Specification (problems 2 & 3 — orphan overlay fields):**
```
FUNCTION isBugCondition_orphan(fieldKey)
  INPUT:  fieldKey of type string (an overlay field key)
  OUTPUT: boolean

  RETURN fieldKey IN members_config.json.field_overlay.fields
         AND NO row in members_source_mapping.csv has target == ("overlay." + fieldKey)
END FUNCTION
```
`isBugCondition_orphan("signature_date")` → true (no mapping row targets it; "Datum
ondertekening" col 30 is consumed as a `joined_date` coalesce input, "Ondertekening" col 32 goes
to `(additional_info)`). `isBugCondition_orphan("privacy_consent")` → true (no source column
anywhere maps to it).

**Formal Specification (problem 4 — malformed visibility gate):**
```
FUNCTION isBugCondition_gate(field, flatRow)
  INPUT:  field with show_when == {"field":"member_id","op":"not_exists"}, flatRow
  OUTPUT: boolean

  RETURN field.show_when is present
         AND evaluateShowWhen(field.show_when, flatRow) == false FOR ALL real rows
END FUNCTION
```
`evaluateShowWhen` treats `{"field":"member_id","op":"not_exists"}` as TWO controlling keys —
`field` (expected `"member_id"`) and `op` (expected `"not_exists"`) — ANDed. No member record and
no create-form Formik value set carries a flat `field` or `op` key, so the gate resolves to
`false` for EVERY input. `referral_source` is therefore suppressed in the view modal AND on the
create form — the D10 "create-form-only" intent was never actually achieved.

### Examples

- **Newsletter**: A member whose source row has `Digitale nieuwsbrieven = "Ja"` shows a dash for
  "Nieuwsbrief" in the modal (expected: the stored value renders). Note the config enum declares
  lowercase `ja`/`nee` while the importer copies raw `"Ja"`/`"Nee"` verbatim; `renderFieldValue`
  stringifies the stored value as-is (no choice→label mapping), so a stored `"Ja"` WOULD still
  render — meaning the dash indicates the value is absent, not a casing display bug.
- **signature_date**: The modal renders a standalone "Datum ondertekening" (Administratief
  section) date row that is always empty — no mapping row ever writes `overlay.signature_date`.
- **privacy_consent**: The modal renders a "Privacy" row (Lidmaatschap section, `required:true`)
  that is always empty — no source column backs it.
- **referral_source**: A member imported with `WieWatWaar = "via een vriend"` shows NO
  "Wie/wat/waar" row in the view (the gate hides it), and a new-member form ALSO omits the field
  (the same malformed gate hides it there too).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Overlay fields DECLARED in the config AND backed by a mapping row (`magazine_pref`,
  `motor_brand`, `motor_type`, `build_year`, `license_plate`, `iban`, `payment_method`, `region`,
  `notes`, `additional_info`, `deregistration_date`, `termination_date`, `referral_source`) must
  CONTINUE to render with their stored values.
- The importer must CONTINUE to match source columns by BASE header NAME (lower-cased), NOT by
  `col_index`; the "SAM Code" column inserted at position 0 requires no col_index shift.
- Leftover `(additional_info)` columns (`Ondertekening`, `Naam voor akkoord`) must CONTINUE to be
  concatenated into `overlay.additional_info` as `Label: value` pairs in stable source-column
  order with the ` | ` delimiter.
- Legitimately-mapped overlay `date` fields (`deregistration_date`, `termination_date`) must
  CONTINUE to display; removing the orphan `signature_date` must not affect them.
- Every OTHER field carrying a `show_when` gate must CONTINUE to honor it via `evaluateShowWhen`;
  only `referral_source`'s gate changes.
- The modal must CONTINUE to section fields by `functional_group`, honor field-level `visible`,
  and present dates/enums/calculated via `renderFieldValue`.

**Scope:**
All inputs that do NOT satisfy one of the four bug conditions above are completely unaffected.
Specifically: any overlay field that is both declared AND mapped; any non-`referral_source`
`show_when` gate; and all fixed `personal.*`/`membership.*` fields.

The actual expected correct behavior for each bug input is defined in the Correctness Properties.

## Hypothesized Root Cause

### Problem 1 — newsletter_pref not shown

The mapping and transform are correct in the CURRENT code: `Digitale nieuwsbrieven` (col 36) →
`overlay.newsletter_pref`, rule `single`, and PASS 2 of `map_hdcn_row` copies the raw string onto
`overlay[newsletter_pref]`. So the most likely causes, in priority order:

1. **Stale data — records imported before the newsletter row existed / not re-backfilled.** The
   members currently visible were produced by a backfill run whose contract predated (or differed
   from) the current `Digitale nieuwsbrieven` row, so `overlay.newsletter_pref` was never written
   for them. This is the leading hypothesis and is confirmed by inspecting a stored record.
2. **Live-sheet header mismatch.** `map_hdcn_row` matches on the BASE header lower-cased
   (`digitale nieuwsbrieven`). If the live sheet's header text differs (extra spacing, a rename,
   a trailing qualifier), the column is never matched and the value is silently routed to
   `(additional_info)` as an unmapped leftover (or dropped if excluded). The mapping CSV header
   itself notes "VERIFY against the live sheet header on first direct-read run".
3. **Value lands in additional_info instead.** If (2) holds, the newsletter value would appear
   concatenated inside "Aanvullende informatie" rather than in "Nieuwsbrief" — a tell that
   distinguishes a header mismatch (value present in additional_info) from stale data (value
   absent everywhere).

This is NOT a casing/display bug: `renderFieldValue` stringifies `overlay.newsletter_pref`
verbatim, so a stored `"Ja"` renders as `Ja` regardless of the enum's lowercase choices. The
investigation step (below) resolves which of 1/2/3 holds before committing the fix.

### Problems 2 & 3 — orphan overlay fields

`signature_date` and `privacy_consent` are declared in `members_config.json.field_overlay.fields`
with `visible` (default) but NO mapping row targets `overlay.signature_date` or
`overlay.privacy_consent`. The modal (`MembersViewBody` → `formFields` → `groupFieldsBySection`)
renders whatever the resolved config lists and does not filter by "has a mapping backing", so both
render as permanently-empty rows. Root cause: **config-vs-mapping definition mismatch** (the
config over-declares). The mapping loader's drift guard only rejects a mapping target NOT declared
in the config (the one direction); it does not flag a config field with NO mapping backing (the
other direction) — so these orphans passed validation unnoticed.

### Problem 4 — referral_source visibility gate

`referral_source` is authored with `show_when: {"field": "member_id", "op": "not_exists"}` (per
D10, intended as create-form-only). But `evaluateShowWhen` / `evaluate_show_when` interpret
`show_when` as `{controllingKey: expected}` ANDed — so this shape means "show only when a flat key
`field == 'member_id'` AND a flat key `op == 'not_exists'`". No member record and no create-form
value set has flat `field`/`op` keys, so the predicate is ALWAYS false. Root cause: **the
`show_when` value is malformed relative to the implemented predicate** — it does not express
"member_id absent" in the supported convention; it accidentally hides the field everywhere,
including the create form D10 wanted it on.

## Correctness Properties

Property 1: Bug Condition — Newsletter preference reaches and renders in the modal

_For any_ member whose source row carries a non-empty newsletter cell (the live-sheet header
mapped to `overlay.newsletter_pref`), the fixed data flow SHALL result in `overlay.newsletter_pref`
holding that value and the modal SHALL display it in the "Nieuwsbrief" row (not the empty-cell
dash).

**Validates: Requirements 2.1**

Property 2: Bug Condition — No orphan overlay field renders in the modal

_For any_ overlay field key where `isBugCondition_orphan(fieldKey)` holds (declared in the config
but with no mapping row backing), the fixed config SHALL NOT declare that field, so the resolved
field set SHALL NOT include it and the modal SHALL NOT render a row for it.

**Validates: Requirements 2.2, 2.4**

Property 3: Bug Condition — Signature info routed to additional_info

_For any_ member whose source row carries signature information (`Ondertekening` / `Naam voor
akkoord`, disposition `(additional_info)`), the system SHALL concatenate that data into
`overlay.additional_info` as `Label: value` pairs and display it in the "Aanvullende informatie"
row (never in a standalone "Datum ondertekening" field, which no longer exists).

**Validates: Requirements 2.3**

Property 4: Bug Condition — Orphan-field guard surfaces config↔mapping drift

_For any_ config where an overlay field is declared with no mapping-contract backing, loading the
mapping contract with that config SHALL surface the orphan field as a contract violation (or an
explicit warning), rather than loading silently.

**Validates: Requirements 2.5**

Property 5: Bug Condition — referral_source renders in the view for existing members

_For any_ existing member with an imported `overlay.referral_source` value, the fixed
visibility gate SHALL allow the read-only view modal to display that value, while the create form
SHALL still present the `referral_source` input for a new member (D10 preserved).

**Validates: Requirements 2.6, 3.7**

Property 6: Preservation — Mapped overlay fields and other gates unchanged

_For any_ input that does NOT satisfy a bug condition (a declared-and-mapped overlay field, a
non-`referral_source` `show_when` gate, header-name matching, or additional_info concatenation),
the fixed system SHALL produce the same result as before the fix.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Problem 1 — newsletter_pref (investigate, then fix the data flow)

**Investigation (required first — decides the fix):**
1. Inspect a stored member record known to have a newsletter value at source: check whether
   `overlay.newsletter_pref` is present. If absent AND the value appears inside
   `overlay.additional_info`, the cause is a live-sheet header mismatch (root cause 2). If absent
   from BOTH, the cause is stale data (root cause 1).
2. Compare the live-sheet header text against the mapping base header `digitale nieuwsbrieven`
   (reuse the header-debug logic referenced in the CSV: `debug_sheet_headers.py`).

**Fix by outcome:**
- **Stale data (most likely):** No code change. Re-run the h-dcn backfill for the affected field
  so `overlay.newsletter_pref` is populated (see Sequencing). The mapping and transform are
  already correct.
- **Header mismatch:** Update the `source_column` in `members_source_mapping.csv` for the
  newsletter row to the exact live header (the loader matches on the base header lower-cased), then
  re-backfill.

**File**: `scripts/aws/h-dcn/members_source_mapping.csv` (only if header mismatch);
`sam/members/migration/hdcn_backfill.py` (no change expected).

**Note on enum casing (informational, not a fix):** the config enum declares `ja`/`nee` while the
importer stores `"Ja"`/`"Nee"`. `renderFieldValue` does not map choice→label, so the raw value
renders. This is a cosmetic inconsistency only; it does not cause the empty display and is out of
scope for the display fix. (If desired later, either lowercase on import or add a choice→label
lookup in `renderFieldValue` — deferred.)

### Problems 2 & 3 — remove orphan overlay fields

**File**: `scripts/aws/h-dcn/members_config.json`

**Specific Changes**:
1. **Remove `signature_date`** from `field_overlay.fields`. Signature information is already routed
   to `overlay.additional_info` via the `Ondertekening` / `Naam voor akkoord` `(additional_info)`
   rows, and "Datum ondertekening" (col 30) already contributes to `joined_date`. No standalone
   field is needed. No mapping-CSV change is required (nothing targets it).
2. **Remove `privacy_consent`** from `field_overlay.fields`. It is an orphan with no source column
   and is `required: true`.

**`privacy_consent` required-field impact assessment (safe path):**
- `privacy_consent` is `required: true`. On the CRUD create/edit form, a required overlay field
  makes the server enforce required-ness — but only when the field is VISIBLE (the
  `_required_when_visible` rule keyed on `show_when`). Since it has no `show_when`, it is always
  visible and thus always required on the form. Removing it therefore REMOVES an un-satisfiable
  required field, which is strictly safer for the create/edit form (a manual add currently must
  supply a value the import never provides).
- **Existing records**: no member record carries `overlay.privacy_consent`, so removing the field
  cannot orphan or invalidate stored data — it only stops rendering an empty row. Removal is
  non-destructive to member records.
- **Recommendation**: REMOVE `privacy_consent` (option per R2.4). Do NOT add a backing source
  column — there is no privacy-consent column in the sheet, and inventing one would fabricate data.
  If a genuine consent requirement emerges later, it should be introduced deliberately as its own
  spec (form default + source), not reconstructed here.

**Re-seed requirement**: YES. The modal renders `config#fields` projected from the MySQL
`members.field_overlay` param, NOT the JSON file directly. Editing the file alone changes nothing
in the running modal. After editing, re-run `seed-hdcn-members-config.py --apply` to upsert the
param, then run the projection sync so `config#fields` drops the two fields.

### Problem 4 — repair the referral_source visibility gate

**File**: `scripts/aws/h-dcn/members_config.json`

**Decision**: DROP the `show_when` gate on `referral_source` entirely. Rationale:
- The current gate shape is malformed for the implemented predicate and hides the field
  EVERYWHERE (view AND create form), which already violates D10's "show on create form" intent.
- The supported `show_when` convention (`{controllingKey: expected}` ANDed, exact-match) cannot
  express "member_id is absent" — there is no `not_exists`/`op` operator in `evaluateShowWhen` /
  `evaluate_show_when`. Introducing one would be a cross-cutting predicate change (frontend +
  server) far beyond a config edit and beyond this bug's scope.
- Dropping the gate makes `referral_source` behave like every other declared, mapped, `visible`
  overlay field: it renders its imported value in the read-only view (satisfying 2.6) and presents
  as a free-text input on the create form (satisfying 3.7, which was actually broken before).
- The view is read-only and the edit form simply shows the current (possibly historical) value —
  no split view/edit visibility is needed. A free-text field showing its stored value on edit is
  correct and matches D10 (values kept verbatim).

**Specific change**: delete the `show_when` block from the `referral_source` field in
`members_config.json`. Keep `type: string`, `required: false`, label, order, functional_group.

**Re-seed requirement**: YES (same reason as problems 2/3 — re-seed + projection sync).

### R2.5 — config↔mapping orphan-field guard in the mapping loader

**File**: `scripts/aws/h-dcn/members_mapping_loader.py`

**Where**: in `load_mapping_contract`, AFTER the row loop has populated `overlay` (the set of
overlay keys the CSV maps) and BEFORE the final `if errors:` check. The declared overlay
vocabulary is already computed as `declared_overlay = _declared_overlay_keys(config)`.

**Change**: add a check that every declared overlay key has a mapping backing — i.e. appears as a
target in some overlay row. Collect the set of overlay keys actually targeted by the CSV
(`mapped_overlay_keys = { key for m in overlay.values() for key in m.targets }`) and flag any
`declared_overlay - mapped_overlay_keys` as an orphan.

Pseudocode:
```
mapped_overlay_keys = union of m.targets for every OverlayMapping in overlay.values()
orphans = declared_overlay - mapped_overlay_keys
# Exclude keys legitimately populated by a NON-mapped path (derived/business rules):
#   - "region" is written via the region rule (already in overlay targets, so not an orphan)
#   - "additional_info" is populated by the (additional_info) disposition, NOT a mapping target
#   - "iban"/"payment_method" come from the iban_or_payment split (already overlay targets)
# So exclude the known derived/disposition-backed keys:
orphans = orphans - {"additional_info"}
for key in sorted(orphans):
    errors.append(
        f"config overlay field {key!r} is declared in members_config.json but has NO "
        f"mapping backing in the contract (orphan-field guard, R2.5)"
    )
```

**Guard-design note**: `additional_info` is deliberately excluded because it is populated by the
`(additional_info)` disposition rather than by a mapping TARGET, so it is legitimately not in
`overlay` targets. All other overlay fields are expected to be backed by a mapping row (or the
region/iban/payment derived rules, which DO appear as overlay targets). After problems 2/3 remove
`signature_date` and `privacy_consent`, this guard passes; if either is re-added without a mapping
row, the guard fails loudly — which is the intended regression tripwire. Decide whether the guard
raises `MappingContractError` (hard fail, consistent with the existing drift guard) or emits a
warning; recommend HARD FAIL for symmetry with the existing overlay-target drift guard.

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples on the UNFIXED code (confirm each root cause), then
verify the fix corrects the bug input and preserves everything else. The four problems are
validated largely independently because they touch different layers.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate each bug BEFORE fixing, and confirm/refute the
root-cause hypotheses (especially problem 1, which has three candidate causes).

**Test Plan**: Unit-test the transform and the loader against fixtures; inspect a real record for
the newsletter data-flow question.

**Test Cases**:
1. **Newsletter data-flow (decisive)**: Build a raw row with `Digitale nieuwsbrieven = "Ja"`, run
   `map_hdcn_row`, assert `record["overlay"]["newsletter_pref"] == "Ja"`. Expected to PASS on
   current code → proving the transform is correct and the live bug is stale data or a live-header
   mismatch (inspect a stored record to disambiguate).
2. **signature_date orphan**: Assert no row in `members_source_mapping.csv` targets
   `overlay.signature_date`, yet `signature_date` is in the config fields (demonstrates the
   orphan) — on unfixed code the config carries it.
3. **privacy_consent orphan**: Same assertion for `overlay.privacy_consent`.
4. **referral_source gate**: Assert `evaluateShowWhen({"field":"member_id","op":"not_exists"}, row)`
   returns `false` for both an existing-member flat row AND an empty create-form value map (will
   fail to show on unfixed code in BOTH contexts — proving the gate is malformed, not
   create-form-only).
5. **Orphan guard (loader)**: Load the mapping contract against a config that declares an unmapped
   overlay field; on unfixed loader this passes silently (demonstrates R1.5 gap).

**Expected Counterexamples**:
- Newsletter transform test PASSES → the bug is not in the transform; confirm via record inspection.
- `signature_date` / `privacy_consent` render as empty modal rows (config declares, mapping does not back).
- `referral_source` hidden in view AND create form.
- Loader accepts an orphan overlay field without complaint.

### Fix Checking

**Goal**: For all inputs where a bug condition holds, the fixed system produces the expected behavior.

**Pseudocode:**
```
# Problem 1
FOR ALL sourceRow WHERE newsletter cell non-empty DO
  record := map_hdcn_row(sourceRow)
  ASSERT record.overlay.newsletter_pref == sourceRow[newsletter]
END FOR

# Problems 2 & 3
FOR ALL fieldKey WHERE isBugCondition_orphan(fieldKey) DO
  ASSERT fieldKey NOT IN resolvedConfig.fields   # after config edit + re-seed
END FOR

# Problem 4
FOR ALL existingMember WITH overlay.referral_source DO
  ASSERT evaluateShowWhen(referralField.show_when, flatten(member)) == true
END FOR
```

### Preservation Checking

**Goal**: For all inputs where NO bug condition holds, the fixed system equals the original.

**Pseudocode:**
```
FOR ALL member WHERE field is a declared-and-mapped overlay field DO
  ASSERT renderView_fixed(member, field) == renderView_original(member, field)
END FOR

FOR ALL field WITH a non-referral_source show_when DO
  ASSERT evaluateShowWhen_fixed(field.show_when, row) == evaluateShowWhen_original(field.show_when, row)
END FOR
```

**Testing Approach**: Property-based testing is recommended for the preservation checks —
generating random member records and random declared-and-mapped overlay values, then asserting the
view rows are unchanged, catches edge cases a handful of unit tests would miss. Header-name
matching and additional_info concatenation are also good PBT targets (generate random column
orders / duplicate headers and assert the transform output is stable).

**Test Plan**: Observe the current view behavior for the mapped fields and the current transform
output for additional_info on unfixed code, then write property-based tests capturing that
behavior so the config/loader/gate changes cannot regress them.

**Test Cases**:
1. **Mapped overlay preservation**: `magazine_pref`, `motor_brand`, `deregistration_date`,
   `termination_date`, `notes`, `referral_source` still render their stored values after the fix.
2. **additional_info preservation**: `Ondertekening` + `Naam voor akkoord` still concatenate into
   `overlay.additional_info` in stable order with ` | `.
3. **Other show_when gates preservation**: any other conditionally-visible field still toggles
   correctly.
4. **Header-name matching preservation**: the SAM Code col-0 insertion still requires no col_index
   shift.

### Unit Tests

- `map_hdcn_row`: newsletter value reaches `overlay.newsletter_pref`; signature columns reach
  `overlay.additional_info`; no `overlay.signature_date`/`overlay.privacy_consent` produced.
- `members_mapping_loader.load_mapping_contract`: orphan-field guard raises for a declared-unmapped
  overlay field; passes for the corrected config; still raises the existing drift guard for a
  mapping target not declared in config.
- `evaluateShowWhen` / `evaluate_show_when`: `referral_source` (gate removed) is shown for both an
  existing member and a create-form value map; other gates unchanged.

### Property-Based Tests

- Generate random members with random declared-and-mapped overlay values → assert the view renders
  each value (preservation, Property 6).
- Generate random raw rows with random column orders and duplicate headers → assert
  `map_hdcn_row` output is stable and header-name matching holds (Property 6 / R3.2).
- Generate configs with a random extra declared-but-unmapped overlay field → assert the loader
  guard flags it (Property 4).

### Integration Tests

- Full resolve → view flow: after config edit + re-seed + projection sync, the resolved
  `config#fields` no longer lists `signature_date`/`privacy_consent`; the modal renders no rows for
  them.
- End-to-end referral: an existing member with an imported `referral_source` shows the value in the
  view modal; the create form presents the free-text input.
- Newsletter end-to-end: after re-backfill of the affected field, a member with a source newsletter
  value shows it in the "Nieuwsbrief" row.

## Sequencing (config → re-seed → projection → re-backfill)

The changes span three planes — the static config file, the seeded MySQL param, and (for
newsletter) the member RECORDS. Order matters:

1. **Edit `members_config.json`**: remove `signature_date`, remove `privacy_consent`, drop the
   `show_when` on `referral_source`.
2. **Add the R2.5 orphan-field guard** to `members_mapping_loader.py`. Run the loader against the
   edited config to confirm no orphans remain (it should now pass; it would have failed before the
   config edit — proof the guard works).
3. **Re-seed the config into MySQL**: run `seed-hdcn-members-config.py --tenant h-dcn --apply` to
   upsert `members.field_overlay` (dry-run first to review the diff). The modal reads the projected
   `config#fields`, not the file — this step is REQUIRED for the config edits to take effect.
4. **Run the projection sync** (rollout C.11) so `config#fields` reflects the new
   `members.field_overlay` (drops the two fields, clears the referral gate).
5. **Investigate + fix newsletter (problem 1)**:
   - Inspect a stored record and the live-sheet header to decide stale-data vs header-mismatch.
   - If header mismatch: update the newsletter row's `source_column` in the mapping CSV.
   - **Re-backfill the affected members** so `overlay.newsletter_pref` is populated. Only the
     newsletter problem needs a member-record re-import — problems 2/3/4 are config/projection only
     and need NO backfill (removing a field does not touch records; the referral value is already
     imported).
6. **Verify in the modal**: newsletter renders; no "Datum ondertekening"/"Privacy" rows;
   "Wie/wat/waar" renders for existing members and appears on the create form.

Backfill vs config-only summary:
- **Config + re-seed + projection only** (no backfill): problems 2, 3, 4.
- **Config/mapping (maybe) + re-backfill**: problem 1.
