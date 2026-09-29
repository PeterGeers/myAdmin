# S5m — Design: h-dcn member re-import (direct gsheet + mapping cleanup)

## Overview
All work is confined to the SAM Members backfill and its runner. Nothing in the Lambda request
path changes; nothing writes to the live Sheet. The transform stays a pure function; the new
Google connection is a source adapter behind the existing duck-typed seam.

Files touched:
- `scripts/aws/h-dcn/members_source_mapping.csv` — the authored mapping contract (new; already seeded).
- `scripts/aws/h-dcn/members_config.json` — `magazine_pref` choices, `payment_method`→string, and new
  overlay fields `additional_info`, `deregistration_date`, `termination_date`.
- `scripts/aws/h-dcn/members_config_loader.py` — the CSV mapping loader + ported region variants.
- `sam/members/migration/hdcn_backfill.py` — position-tracking helper, contract-driven transform,
  disposition sets, `additional_info`/`iban_or_payment`, new `GoogleSheetsSourceAdapter`,
  `FileSourceAdapter` raw-header reading.
- `sam/members/domain/calculated_fields.py` — four new derived birth fields.
- `scripts/aws/backfill-hdcn-members.py` — adapter selection + CLI flags + `--reconcile` sync.
- `sam/tests/test_hdcn_backfill.py`, `sam/tests/test_calculated_fields.py` — tests.

Not touched: `fixed_fields.py` (birth_date stays optional), the repository/write-path CODE (the sync
reuses existing `list_members`/`save_member`), the SAM Lambda layer requirements.

## Decisions

### D0 — The mapping is an authored CSV contract, loaded into the transform (R0)
The mapping specification is ONE authored, human- and Kiro-editable file:
`scripts/aws/h-dcn/members_source_mapping.csv` — one row per sheet column with
`source_column` (`<header>#<colindex>`), `col_index`, `target`, `rule`, `note`. This replaces
hand-maintained Python dicts as the AUTHORING surface: "what maps where" lives in one table a human
or Kiro can edit and eyeball against the 49-column sheet, and "freezing" the mapping is committing
the file.

A loader (`members_config_loader.py` companion, mirroring how `members_config.json` is loaded) parses
the CSV into the in-memory structures the transform already uses:
- rows whose `target` is `personal.*`/`membership.*` → the fixed source→dotted-key map
  (`FIXED_SOURCE_COLUMNS` equivalent), carrying the row's `rule`;
- rows whose `target` is `overlay.*` → the source→canonical-overlay-key map
  (`OVERLAY_SOURCE_COLUMNS` equivalent);
- rows whose `target` is `(calculated)` / `(excluded)` / `(additional_info)` → the disposition sets.
The transform consumes these exactly as before; only the AUTHORING moved from code to CSV. (Base-key
matching, R1.3, means a `#<colindex>` duplicate row and its bare-header sibling both resolve to the
same target and coalesce.)

Two guards make it a contract, not just data:
1. **Load/validate guard (R0.4):** the loader rejects an unknown `target` (not a known fixed key, a
   declared overlay key, or a disposition token) or an unknown `rule`; and asserts every `overlay.*`
   target is an overlay field declared in `scripts/aws/h-dcn/members_config.json` (drift guard).
2. **Target-population test (R0.4):** a representative source row asserts each declared fixed/overlay
   target is populated from its source column(s).
Multiple source columns MAY feed one target (multiple rows with the same `target`); how they combine
is the per-target `rule` (D0b).

### D0b — Per-target combination strategies (R0.2/R0.3)
A target is not limited to "one column, copied". The mapping supports these strategies, chosen per
target, kept data-driven and extensible so a new target picks what it needs without new branch logic:
- **single** — one source column → target (the default; today's `FIXED_SOURCE_COLUMNS` /
  `OVERLAY_SOURCE_COLUMNS` entries are `single`).
- **coalesce** — an ORDERED list of columns, first-non-empty wins. This is the SAME mechanism as
  duplicate-header safety (D1/R1): a duplicate header is an implicit coalesce; an explicit ordered
  fallback (prefer col X, else col Y) is the same code path over named columns. In this pilot the
  duplicate `E-mailadres` columns are the coalesce case; both entries point at `personal.email` and
  the first-non-empty value is kept.
- **concat** — an ORDERED list joined with a declared separator (± per-part labels). Two uses here:
  the `additional_info` catch-all (R2.7, `Label: value` joined by ` | `), and — if wanted — a
  composed display value. Name parts already have a CALCULATED `display_name`, so concat is NOT used
  for names in this spec (avoid duplicating that); it is available if a future target needs it.
- **transform** — a single/coalesced value passed through a conversion (`date` ISO-date-part,
  `member_number` shaping, `membership_type` catalog-code, `region` canonicalization, `gender`
  normalization, `magazine` enum-with-fallback). Composes AFTER coalesce (coalesce → transform).
- **conditional split** — one source column → several targets conditionally (`iban_or_payment` on
  `Bankrekeningnummer`: valid IBAN → iban + payment_method=`incasso`; else → payment_method=raw text,
  iban empty). A bespoke rule; logic documented in its CSV note (R0.3).

Representation: the loader (D0) parses the CSV `rule` per row, so each target carries its declared
strategy explicitly (no inference from the target name). `single`/`transform` cover most rows;
`coalesce` is realized by two source headers pointing at the same target resolved via the D1
first-non-empty rule (the duplicate `E-mailadres`/`Datum ondertekening` cases); `concat` is the
`additional_info` accumulator; `iban_or_payment` is a bespoke conditional split. The vocabulary is
fixed by R0.3 and extensible — a new target picks a rule without new branching in the caller.

### D1 — Position tracking at row-build + first-non-empty coalesce in the transform (R1)
Two cooperating mechanisms, so no column is lost to a header collision and duplicates combine
deliberately (not by dict-order accident):

1. **Row-build disambiguation (both adapters, R1.1/R1.2).** When building a row, repeated headers are
   made unique by appending the column index: the first occurrence keeps the bare header, later ones
   become `<header>#<colindex>` (e.g. `E-mailadres`, `E-mailadres#34`). `GoogleSheetsSourceAdapter.
   _rows_from_matrix` applies this over the header row; `FileSourceAdapter` reads the raw header row
   itself (not `csv.DictReader`, which silently collapses duplicates) and applies the same rule. The
   transform therefore ALWAYS receives a collision-free row where every source column is present and
   individually addressable.
2. **Base-header matching + coalesce (transform, R1.3).** `map_hdcn_row` strips a trailing
   `#<colindex>` back to the base header before consulting `FIXED_SOURCE_COLUMNS` /
   `OVERLAY_SOURCE_COLUMNS` / the dispositions. Columns sharing a base thus feed one target and are
   combined first-non-empty: a write to an already-populated target is applied ONLY when the existing
   value is blank and the new value is non-blank. First non-empty (in column order) wins; a later
   empty never overwrites.

Two different non-empty values sharing a base header are a genuine conflict: the first-in-order is
kept, and the loser is reported by its INDEXED name (`<header>#<colindex>`) in the fidelity report
(R1.6) so the operator can see exactly which column lost. A specific duplicate can be excluded by its
indexed name (R1.7 / R2.6). Applies to fixed and overlay targets alike (R1.4).

### D2 — `OVERLAY_SOURCE_COLUMNS` maps Dutch headers → canonical overlay keys (R2.3)
A new module-level constant `OVERLAY_SOURCE_COLUMNS: Mapping[str, str]` keyed by the lower-cased
Dutch header, valued by the canonical overlay key from `members_config.json`. The transform checks
it after `FIXED_SOURCE_COLUMNS` and before the verbatim fold: a match stores under
`overlay[<canonical key>]`; a non-match still folds verbatim (R2.4). This keeps the canonical
vocabulary as DATA (mirroring `FIXED_SOURCE_COLUMNS`), not code branches, and keeps the tenant
config as the single source of truth for the key names.

Why not put these in the tenant config file directly? The config declares the overlay FIELDS
(their type/labels/choices); the Dutch-source-header→key translation is importer concern (the same
place the fixed Dutch→EN translation already lives). Keeping it beside `FIXED_SOURCE_COLUMNS`
co-locates all source-header knowledge in one module.

### D2b — Column dispositions are declared as data; leftovers concatenate into `additional_info` (R2.6/R2.7)
Beyond the two mapping tables, two module-level constants make the non-imported columns explicit,
and a single overlay field absorbs the rest — so overlay NEVER accumulates raw Dutch header keys:
- `CALCULATED_SOURCE_COLUMNS: frozenset[str]` — headers whose value is DERIVED by a calculated field
  and therefore NOT stored (currently `geboortedag`/`geboortemaand`/`geboortejaar`). Recognized and
  skipped (neither stored nor lost — computed). OPEN list.
- `EXCLUDED_SOURCE_COLUMNS: frozenset[str]` — headers deliberately dropped (unfit / near-duplicate).
  Per the CSV: `gezinslid`, `bestuursfunctie`, `in functie sinds`, `lidmaatschapsnummer`, `jubilaris`,
  `bedrag`, `inschrijfformulier`, `kortenaam`, the repeated `h-dcn clubblad`, and the near-duplicate
  `e-mail` / `email address`. The blank-named column is dropped by the existing empty-name rule.
- `overlay.additional_info` — a single declared overlay STRING field (added to
  `members_config.json`). The Additional-info columns per the CSV are `ondertekening` and
  `naam voor akkoord`; each contributes a `Label: value` pair (source header as label, ` | `
  delimiter, stable source-column order, only non-empty cells). If nothing contributes, the field is
  left unset. (`afmelding`/`beeindiging` are NOT additional_info — they are MAPPED to the filterable
  overlay date fields `deregistration_date` / `termination_date`.)

Resolution order in the column loop: FIXED → OVERLAY → CALCULATED (skip) → EXCLUDED (skip) →
else collect into the additional-info accumulator (flushed to `overlay.additional_info` after the
loop). Every disposition is a data-driven decision; the fidelity report labels each source column
with its disposition (R0.5/R2.5).

Note the near-duplicate `E-mailadres` at col 34 is NOT excluded by header — it shares the header of
the mapped col 12, so first-non-empty-wins (D1) already handles it; excluding by header would wrongly
drop col 12 too. Exclusion is by header name, so it only applies to headers that are UNIQUELY the
unwanted column.

### D3 — birth_date is a DATE fixed field needing ISO-date extraction (R2.1)
`Geboorte datum` is added to `FIXED_SOURCE_COLUMNS → personal.birth_date`. Unlike the string fixed
fields, a DATE field must be reduced from the source ISO datetime to `YYYY-MM-DD` before
`validate_fixed_fields` (which enforces `^\d{4}-\d{2}-\d{2}$`). A small `_DATE_FIXED_KEYS` set marks
which fixed dotted keys need `_iso_date_part()` applied in the column loop. Reuses the existing
helper already used for `joined_date`. An unparseable/empty date leaves the field unset (optional),
so it never blocks a row (R2.1, R3.3).

### D4 — Four calculated birth fields mirror `age`/`birthday` (R3)
Add pure derivations to `calculated_fields.py`, each taking `personal.birth_date` as its single
input and returning `None` when absent/unparseable:
- `birth_day` → `born.day` (1–31)
- `birth_month` → `born.month` (1–12)
- `birth_year` → `born.year` (YYYY)
- `birth_quarter` → `(born.month - 1) // 3 + 1` (1–4)
All are `FieldGroup.PERSONAL`, `FieldType.STRING` (the existing convention — a number is not a
stored `FieldType`; the value is rendered as text), with `{nl,en}` labels and `inputs=("personal.
birth_date",)`. They are appended to `CALCULATED_FIELDS`; the module's import-time guard already
rejects a duplicate key or a collision with a fixed key (R3.2). Ordering placed just after
`birthday` (order 56) so the birth cluster reads together.

### D5 — `GoogleSheetsSourceAdapter`: read-only, lazy, matrix→rows (R4)
A new class in `hdcn_backfill.py` next to the other adapters. Shape:
- `__init__(*, spreadsheet_id=None, spreadsheet_name=None, worksheet=None,
  credentials_file=".googleCredentials.json", cell_range=None)` — requires an id OR a name.
- `rows()` → `_fetch_values()` (a single READ-ONLY `spreadsheets.values.get`) → `_rows_from_matrix()`
  (row 0 = header; each later row zipped to headers; short rows padded to header width; blank-named
  columns dropped; duplicate headers resolved first-non-empty-wins per D1/R4.5).
- `describe()` → `"Google Sheet <id|name> [tab '<worksheet>'] (READ-ONLY, direct API)"`.
- Auth: `_load_credentials()` uses `google.oauth2.service_account.Credentials.from_service_account_file`
  with scope `spreadsheets.readonly`; a missing file raises `FileNotFoundError` with setup guidance
  (R4.3). Resolving a sheet by TITLE (`spreadsheet_name`) uses a read-only Drive `files.list` with
  the added `drive.readonly` scope. Credentials REUSE the existing h-dcn service account
  (`h-dcn-migration@…`); `--credentials` defaults to the shared h-dcn key file
  `/home/peter/projects/h-dcn/.googleCredentials.json` (one key for both projects), overridable.
  The Sheet is already shared with that SA as Viewer — no Google Console change. NOTE: the key file
  is gitignored and may be absent on disk; the operator places it before the first live run
  (validate as `test_google_connection.py` does: exists, valid JSON, not the template).
- **Lazy imports (R4.4):** every `from google...`/`from googleapiclient...` import is INSIDE the
  methods, never at module top, so `import hdcn_backfill` in Lambda (no Google libs) is safe.

The adapter is duck-typed against the existing `HdcnSourceAdapter` Protocol — no base class needed.
It is added to `__all__` and the constants (`DEFAULT_GOOGLE_CREDENTIALS_FILE`,
`_SHEETS_READONLY_SCOPE`) documented inline.

### D6 — Runner adapter selection (R4.6)
`backfill-hdcn-members.py` gains a source-selection group: `--source` (file, existing) is now
mutually exclusive with `--sheet-id` / `--sheet-name`; `--worksheet` and `--credentials` accompany
the sheet options. `backfill()` builds `GoogleSheetsSourceAdapter(...)` when a sheet is requested,
else `FileSourceAdapter(...)` as today. The header-probe (`_classify_source_columns`) uses the same
adapter type. Everything downstream (`build_backfill_plan`, `_apply_plan`, report, `--apply` refusal
on mapping errors) is unchanged and adapter-agnostic. `--tenant` stays required.

Live `--apply` against the real `sam-members` table still requires the `nonprofit-deploy` account
with the repo `.env` static keys stripped (steering `23-aws-accounts`); documented in the runner
help, not changed here.

### D7 — Reconciling sync: in-memory member_number index, upsert, absence sweep (R7)
A new `--reconcile` mode turns the insert-only backfill into an idempotent sync. It is additive: the
existing `build_backfill_plan` / `_apply_plan` path is unchanged and remains the default.

Why match in memory. The repository exposes `get_member(tenant, member_id)` (by uuid),
`list_members`, `save_member`, `delete_member` — but NO query by `member_number`. So the sync:
1. Reads all current SAM members for the tenant once (`list_members`) and builds
   `by_number: dict[str, Member]` keyed on `membership.member_number` (blank numbers bucketed
   separately and reported — they cannot be matched, R7.5).
2. Transforms the sheet rows into candidate records (the existing transform).
3. Reconciles per candidate on its (stable, sheet-assigned) `member_number` (R7.2):
   - number in `by_number` → UPDATE: reuse the existing `member_id`, `save_member` the merged record
     (a single `PutItem` — s5k, no guard);
   - number not in `by_number` → INSERT: mint `member_id`, `save_member`;
   - candidate has NO number → UNMATCHABLE: not written, reported (R7.3) — the operator adds a number
     in the sheet (approach A) and re-runs.
4. Absence sweep (R7.4): any SAM member whose `member_number` was NOT seen in the sheet this run is
   UPDATED to `status = "left"` via `save_member` (soft flag; never `delete_member`). A previously
   `left` member present in the sheet is reactivated (its status comes from the transform, default
   `active`).

Because the match key is a stable sheet value and UPDATE reuses the existing `member_id`, re-runs are
idempotent (R5.3) — this is what approach (A) buys over the s5k mint-a-uuid behaviour.

SHEET-WINS (R7.3, confirmed): UPDATE `save_member`s the sheet-derived record, so the sheet's mapped
values overwrite the SAM record's mapped fields — SAM is read-only for synced fields until h-dcn cuts
over. In-app edits to synced fields do not survive a reconcile; this is intentional (sheet is
authoritative in the interim). The internal `member_id` and any non-synced/derived data are preserved.

Refusals (R7.7): `--apply --reconcile` aborts (writes nothing) if any row failed to map (existing
rule) OR if the sheet has duplicate `member_number` values (the operator resolves the duplicate in
the sheet first — a duplicate would make "which record does this update?" ambiguous). Duplicate
numbers ALREADY in SAM are also reported so they can be reconciled.

Reporting (R7.6): the dry-run report gains sync sections — to-INSERT, to-UPDATE, to-LEAVE (soft-flag
`left`), UNMATCHABLE (numberless sheet rows), and duplicate-number collisions — so the operator
reviews the full reconciliation before `--apply`.

This is deliberately an operator CLI, NOT a tenant-admin UI (user decision): the sync touches the
whole partition (incl. soft-deletes) and runs against the `nonprofit-deploy` account, which is an
operator-privileged, infrequent maintenance action.

### D8 — Reuse h-dcn's proven importer knowledge (retargeted to SAM canonical values)
The h-dcn project already has a working direct-Sheets importer,
`h-dcn/backend/scripts/import_members_sheets.py` v2.0, plus `debug_sheet_headers.py` and
`test_google_connection.py`. We REUSE its knowledge rather than reinvent, but do NOT copy it wholesale
(it targets the OLD `Members` DynamoDB table in the Flask plane with Dutch stored values, and its
cleanup is destructive):
- **Auth pattern (reuse as-is conceptually):** `Credentials.from_service_account_file('.googleCredentials.json',
  scopes=['…/spreadsheets.readonly','…/drive.readonly'])`, open by sheet title + worksheet
  `Ledenbestand`. Our adapter uses `google-api-python-client` (already pinned) instead of `gspread`
  (avoids a new dependency); same auth, same scopes, same credentials file/location.
- **Field mapping (port → the CSV):** h-dcn's 27-entry `field_mapping` dict is the GROUND TRUTH for
  source-column → field and seeds `members_source_mapping.csv` (D0). Header names verified against a
  real import.
- **Region normalization (port → SAM canonical):** h-dcn's ~40-variant `regio_value_mapping` +
  `VALID_REGIONS` is far richer than the current `REGION_ALIASES` single entry. Port the VARIANTS into
  the h-dcn region canonicalizer (`members_config_loader.REGION_ALIASES` / the config value set),
  RETARGETED to SAM's canonical region values (e.g. SAM uses `Noord Holland` without a hyphen and
  `Geen`, where h-dcn used `Noord-Holland` and `Overig`). Do not copy the Dutch target values.
- **Business rules (port, retargeted):** gender normalization (`man→M`), the Clubblad→status rule
  (Papier→Sponsor / Digitaal→Club → in SAM these map to a `membership_type`/`status` per the catalog,
  not the old Dutch status strings), the email "no valid email" indicator list, and column-shift
  detection (year-in-Geslacht + gender-in-Regio) are worth porting as data-quality safeguards.
- **Duplicate-header handling (improve, don't copy):** h-dcn DROPS duplicates (`SKIP_DUPLICATE_<i>`),
  which can still lose data if the kept column is the empty one. Our position-tracking + first-non-empty
  coalesce (D1) is strictly better and supersedes that approach.
- **Do NOT reuse:** the destructive `cleanup_existing_members` / table backup / `put_item` to the old
  `Members` table — our write path is the SAM repository (`save_member`) + the R7 reconciling sync.

This makes the mapping/normalization grounded in a proven import rather than the documented column
list alone; the live-sheet run still verifies headers (reusing `debug_sheet_headers.py` logic).

## Data-loss walkthrough (why `peter@pgeer.nl` was dropped, and the fix)
Real sheet has `E-mailadres` at col 12 (populated: `peter@pgeer.nl`) and again at col 34 (empty).
BEFORE: building a dict keyed by header, col 34 OVERWRITES col 12 with `""` → the transform sees an
empty email → dropped.
AFTER D1: row-build gives the two columns distinct keys `E-mailadres` (col 12) and `E-mailadres#34`
(col 34), so nothing collides. The transform strips both back to base `e-mailadres` → both feed
`personal.email` → first-non-empty coalesce keeps col 12's `peter@pgeer.nl` (col 34's empty never
overwrites). Same mechanism protects `H-DCN Clubblad` ×3, `E-Mail`/`Email Address`; and if col 34
had held a DIFFERENT non-empty email, col 12 still wins and `E-mailadres#34` is reported as the
losing column so the operator can reconcile the source.

## Testing strategy (R6)
- Transform unit tests extend the `_raw(**overrides)` pattern with duplicate-header rows and the new
  columns. No live AWS/Google — `FakeDynamoTable` for the write path, injected value matrices for the
  adapter.
- `GoogleSheetsSourceAdapter` tested via a small helper that calls `_rows_from_matrix` on a synthetic
  matrix (headers + duplicate columns + short rows) — no network. A separate test asserts importing
  `hdcn_backfill` does not import Google libs (the lazy-import guarantee).
- Calculated-field tests cover the four new derivations + `None` on missing date.
- Runner tests: sheet flags select the adapter (monkeypatch the adapter to a fake), mutual exclusion,
  `--tenant` required.

## Risks
- **Live-only confirmation.** The duplicate-header fix is unit-proven, but confirming it recovers the
  operator's REAL email/motor/IBAN needs a live read — gated on `.googleCredentials.json` (R6.4).
- **Remaining overlay enum values.** `magazine_pref` (via the `magazine` rule) and `payment_method`
  (via `iban_or_payment`) are normalized IN-SPEC; `region`, `gender`, `membership_type` too. Still
  mapped `single` and therefore storing the raw source value: `motor_brand` and `newsletter_pref` —
  value-level normalization for those is a follow-up (tasks) after live review of the real source
  values. This spec lands every value on the right KEY.
- **Config vocabulary changes.** This spec edits `members_config.json`: `magazine_pref` choices →
  `Geen`/`Papier`/`Digitaal`; `payment_method` enum → free-text string; adds `additional_info`,
  `deregistration_date`, `termination_date` overlay fields. The seed script that pushes the config to
  MySQL must be re-run for these to take effect (onboarding path).
