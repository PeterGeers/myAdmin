# S5m — Tasks: h-dcn member re-import (direct gsheet + mapping cleanup)

Execution order is top-down. Each task names the file(s), the requirement(s) it satisfies, and a
verification command. Tests run via the SAM plane: `sam/pytest.ini` (from the backend venv).

- [ ] 1. Duplicate-header position tracking + first-non-empty coalesce
  - Add a shared row-build helper (used by both adapters, task 5/6) that makes repeated headers
    unique by appending the column index: first occurrence keeps the bare header, later ones become
    `<header>#<colindex>` (design D1/R1.1). No `dict` last-occurrence-wins.
  - In `map_hdcn_row` (`sam/members/migration/hdcn_backfill.py`): strip a trailing `#<colindex>` back
    to the base header before consulting the mapping/dispositions (R1.3); combine columns sharing a
    base by first-non-empty coalesce — write a fixed (`personal.*`/`membership.*`) or `overlay`
    target only when the existing value is blank and the new value is non-blank (R1.4).
  - A genuine conflict (two DIFFERENT non-empty values, same base) keeps the first-in-order and
    records the losing column by its indexed name for the report (R1.6). Blank-named column still
    dropped (R1.5).
  - _Requirements: R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R1.7_
  - _Verify:_ `cd sam && python -m pytest tests/test_hdcn_backfill.py -k "duplicate or coalesce or position" -q`

- [ ] 2. Authored mapping CSV + loader (the declared contract)
  - The mapping file `scripts/aws/h-dcn/members_source_mapping.csv` is the AUTHORING surface (one row
    per sheet column: `source_column`,`col_index`,`target`,`rule`,`note`). A first version exists;
    review/adjust rows (targets, rules, dispositions) as needed.
  - Add a loader (companion to `members_config_loader.py`) that parses the CSV, skips `#` comment
    lines, and produces the in-memory structures the transform uses: fixed source→dotted-key map
    (+rule), overlay source→canonical-key map, and the disposition sets
    (calculated / excluded / additional_info). Validate on load (design D0): every `target` is a known
    fixed key, a declared overlay key, or a disposition token; every `rule` is known; every `overlay.*`
    target is a subset of the overlay fields in `members_config.json` (drift guard).
  - Config edits in `scripts/aws/h-dcn/members_config.json` (already drafted; confirm on implement):
    add STRING overlay field `additional_info`; add `date` overlay fields `deregistration_date` and
    `termination_date` (functional_group `membership`, filterable); `magazine_pref` choices →
    `Geen`/`Papier`/`Digitaal`; `payment_method` enum → free-text string. Re-run the config seed so
    MySQL picks them up (onboarding path).
  - _Requirements: R0.1, R0.2, R0.4, R2.3, R2.7_
  - _Verify:_ `cd sam && python -m pytest tests/test_hdcn_backfill.py -k "mapping or loader or contract" -q`

- [ ] 3. Transform consumes the loaded mapping (birth_date, overlay, dispositions, additional_info)
  - In `map_hdcn_row`, drive fixed/overlay mapping + dispositions from the loaded contract (task 2)
    rather than hardcoded dicts. Apply the per-`rule` conversions: `single`/`coalesce` copy with the
    R1 first-non-empty rule; `date` → `_iso_date_part()` to a bare `YYYY-MM-DD` (birth_date optional —
    absent/unparseable leaves it unset, R2.1/R3.3; also the two membership date fields); `member_number`
    shaping; `membership_type` catalog-code; `region` canonicalization; `gender` (Man/Vrouw→M/V);
    `magazine` (→ Geen/Papier/Digitaal, fallback Geen); `iban_or_payment` (conditional split →
    `overlay.iban` + `overlay.payment_method`).
  - Dispositions: `(calculated)` → not stored; `(excluded)` → dropped; `(additional_info)` and any
    unmapped-but-kept column → concatenated into `overlay.additional_info` as `Label: value` (` | `
    delimiter, stable source order, non-empty only; unset if nothing contributes, R2.7).
  - Resolution order: FIXED → OVERLAY → CALCULATED (skip) → EXCLUDED (skip) → additional_info.
  - _Requirements: R0.3, R2.1, R2.2, R2.3, R2.4, R2.5, R2.6, R2.7, R3.3_
  - _Verify:_ `cd sam && python -m pytest tests/test_hdcn_backfill.py -k "overlay or disposition or additional or birth_date" -q`

- [ ] 3b. Port h-dcn region variants + business rules (retargeted to SAM canonical values)
  - From `h-dcn/backend/scripts/import_members_sheets.py` v2.0: port the ~40-variant
    `regio_value_mapping` into the h-dcn region canonicalizer (`members_config_loader.REGION_ALIASES`
    + the region value set in `members_config.json`), RETARGETED to SAM canonical region values
    (e.g. `Noord Holland` no hyphen, `Geen` not `Overig`) — do NOT copy the Dutch targets.
  - Port gender normalization (`man→M`, `vrouw→V`) and the Clubblad→status/type business rule
    (Papier/Digitaal), expressed in SAM's canonical status/`membership_type`; port the email
    "no-valid-email" indicator list; port column-shift detection as a data-quality warning.
  - Reuse (don't duplicate) the auth pattern + `debug_sheet_headers` logic in the adapter (task 5).
  - _Requirements: R8.1, R8.2, R8.4_
  - _Verify:_ `cd sam && python -m pytest tests/test_hdcn_backfill.py -k "region or gender or clubblad or business" -q`

- [ ] 4. Calculated birth fields
  - In `sam/members/domain/calculated_fields.py` add pure derivations `_derive_birth_day/month/year/
    quarter` and register `birth_day`, `birth_month`, `birth_year`, `birth_quarter` in
    `CALCULATED_FIELDS` (PERSONAL, STRING, input `personal.birth_date`, `{nl,en}` labels), following
    the `age`/`birthday` pattern. Missing/unparseable date → `None`.
  - Confirm the import-time uniqueness / no-fixed-collision guard still passes.
  - _Requirements: R3.1, R3.2, R3.3_
  - _Verify:_ `cd sam && python -m pytest tests/test_calculated_fields.py -q`

- [ ] 5. GoogleSheetsSourceAdapter (read-only, lazy, matrix→rows) + FileSourceAdapter position tracking
  - Add `GoogleSheetsSourceAdapter` to `hdcn_backfill.py` per design D5: service-account auth,
    `spreadsheets.readonly` scope (+ `drive.readonly` for title→id), single `values.get`, LAZY Google
    imports, `_rows_from_matrix` (header row, pad short rows, drop blank-named columns) using the
    shared position-tracking helper (task 1) so duplicate headers become `<header>#<colindex>`.
  - Update `FileSourceAdapter` to read the RAW header row itself (not `csv.DictReader`, which
    silently collapses duplicate headers) and apply the SAME position-tracking helper, so file and
    sheet sources behave identically (R1.2).
  - Add `DEFAULT_GOOGLE_CREDENTIALS_FILE` + `_SHEETS_READONLY_SCOPE`; register the class in `__all__`.
  - _Requirements: R1.1, R1.2, R4.1, R4.2, R4.3, R4.4, R4.5, R5.1_
  - _Verify:_ `cd sam && python -m pytest tests/test_hdcn_backfill.py -k "gsheet or position or filesource" -q`

- [ ] 6. Runner adapter selection + CLI flags
  - In `scripts/aws/backfill-hdcn-members.py` add `--sheet-id`/`--sheet-name` (mutually exclusive with
    `--source`), `--worksheet`, `--credentials`. Build `GoogleSheetsSourceAdapter` when a sheet is
    requested, else `FileSourceAdapter`. Use the same adapter for the header probe. Keep `--tenant`
    required and dry-run the default; `--apply` still refuses a batch with mapping errors.
  - _Requirements: R4.6, R5.1_
  - _Verify:_ `cd sam && python -m pytest tests/test_hdcn_backfill.py -k "runner or sheet or tenant" -q`

- [ ] 7. Reconciling sync (match by member_number, upsert, absence sweep)
  - Add a `--reconcile` (a.k.a. `--sync`) mode to `backfill-hdcn-members.py` (additive — insert-only
    backfill stays the default). Per design D7:
    - read all tenant members via `repo.list_members` and index by `membership.member_number`
      (blank numbers bucketed + reported, R7.5);
    - per transformed candidate: number matched → UPDATE reusing the existing `member_id`; number
      unseen → INSERT (mint `member_id`); numberless candidate → UNMATCHABLE (not written, reported);
    - absence sweep: SAM members whose number was not seen this run → `save_member` with
      `status = "left"` (soft flag; NEVER `delete_member`); a `left` member present in the sheet is
      reactivated.
  - Extend the fidelity report with sync sections: to-INSERT / to-UPDATE / to-LEAVE / UNMATCHABLE /
    duplicate-number collisions.
  - `--apply --reconcile` refuses on mapping errors OR duplicate sheet `member_number` values (R7.7).
  - _Requirements: R5.2, R5.3, R7.1, R7.2, R7.3, R7.4, R7.5, R7.6, R7.7_
  - _Verify:_ `cd sam && python -m pytest tests/test_hdcn_backfill.py -k "reconcile or sync or upsert or absence" -q`

- [ ] 8. Tests — mapping contract, dedup, calculated fields, adapter row-shaping, lazy import, sync
  - Mapping-contract tests (R0.4): every declared fixed/overlay target is populated from its source
    column(s) on a representative row; `OVERLAY_SOURCE_COLUMNS` values are a SUBSET of the overlay
    fields declared in `scripts/aws/h-dcn/members_config.json` (drift guard).
  - Extend `sam/tests/test_hdcn_backfill.py`: a populated value survives an empty duplicate (col 12
    `E-mailadres` kept over an empty col-34 duplicate); position tracking makes the duplicate a
    distinct `<header>#<colindex>` key; a genuine two-value conflict keeps the first and reports the
    losing indexed column; excluding `h-dcn clubblad#<n>` drops only that duplicate; birth_date maps
    from ISO datetime; motor/IBAN/payment/magazine land on canonical overlay keys; a numberless
    sponsor/club row imports; `GoogleSheetsSourceAdapter._rows_from_matrix` on a synthetic matrix
    (duplicates + short rows) with NO network; `FileSourceAdapter` applies the same position tracking;
    importing `hdcn_backfill` needs no Google libs.
  - Disposition tests (R2.6/R2.7): a `CALCULATED_SOURCE_COLUMNS` column (e.g. `Geboortejaar`) is NOT
    stored (neither fixed nor overlay nor additional_info); an `EXCLUDED_SOURCE_COLUMNS` column (e.g.
    `Bestuursfunctie`) is dropped; an unknown non-empty column is concatenated into
    `overlay.additional_info` as `Label: value`; multiple leftovers join with ` | ` in source order;
    no raw Dutch header key appears directly in overlay.
  - Extend `sam/tests/test_calculated_fields.py`: the four birth derivations + `None` on missing date.
  - Sync tests (R6.4) with `FakeDynamoTable`: a matched number UPDATES the same `member_id`; an unseen
    number INSERTS; a SAM member absent from the sheet is soft-flagged `left` (not deleted); a `left`
    member back in the sheet reactivates; a numberless sheet row is UNMATCHABLE (not written); a
    duplicate sheet number blocks `--apply --reconcile`; a second run is idempotent (no duplicates).
  - _Requirements: R0.4, R2.6, R6.1, R6.2, R6.3, R6.4_
  - _Verify:_ `cd sam && python -m pytest tests/test_hdcn_backfill.py tests/test_calculated_fields.py -q`

- [ ] 9. Full SAM suite green + document live-apply steps
  - Run the SAM suite; fix any regressions.
  - Add/confirm operator notes for the live direct-read `--apply` and `--apply --reconcile`: place the
    EXISTING h-dcn service-account key at the shared path
    `/home/peter/projects/h-dcn/.googleCredentials.json` (re-download from Google Cloud if absent; the
    Sheet is already shared with that SA as Viewer) or pass `--credentials`; run against the
    `nonprofit-deploy` account with `.env` static keys stripped; assign a stable member_number in the
    sheet for numberless members BEFORE a reconcile. Live confirmation is a manual gated step.
  - _Requirements: R6.5_
  - _Verify:_ `cd sam && python -m pytest -q`

## Follow-ups (NOT in this spec)
- FORM-level default `incasso` for `payment_method` on manually-added members: needs `default` support
  in the overlay field schema (`VariableOverlayField` + resolver + frontend render) — not present
  today. On IMPORT the common case is already pre-populated (valid IBAN → `incasso`); this follow-up
  only covers the in-app create form. (User decision 2026-09-29: keep as follow-up.)
- Enum-value canonicalization for the overlay enums still mapped `single` — `motor_brand`
  (`Harley-Davidson`→`harley_davidson`, unknown→`eigenbouw`?) and `newsletter_pref` (`Ja`/`Nee`→
  `ja`/`nee`). (`gender`, `magazine`, `region`, `membership_type`, and `payment_method` are already
  normalized in-spec.) Land after live review of the real source values.
- Optional soft duplicate-Lidnummer data-quality report (s5k R3.3 left this optional).
