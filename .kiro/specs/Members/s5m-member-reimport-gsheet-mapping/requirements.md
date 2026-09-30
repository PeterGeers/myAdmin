# S5m — h-dcn member re-import: direct gsheet connection + mapping cleanup

## Summary
The h-dcn member backfill loads member records from the Google-Sheet "HDCN Ledenbestand", but a
data-quality review found that **data present in the source is not landing on the member record**
(concrete example: the member's real e-mail `peter@pgeer.nl` is missing; motor data, IBAN and
payment method are largely empty). This spec fixes the import and makes it a repeatable, read-only,
reconciling sync. Scope kept minimal and non-destructive:

1. **Duplicate-header data loss (the main bug).** The real sheet repeats column names (e.g. two
   `E-mailadres` columns, three `H-DCN Clubblad`). The transform reads each row as a dict keyed by
   header, so the LAST occurrence wins — an empty duplicate silently clobbers a populated cell. Fixed
   by position tracking + first-non-empty coalesce (R1).
2. **A declared, complete mapping contract (R0/R2).** All source→target mapping is authored in ONE
   editable CSV (`members_source_mapping.csv`): every fixed/overlay target names its source column(s)
   and a combination/conversion rule; `Geboorte datum`→`birth_date` (+ calculated day/month/year/
   quarter, R3); motor/financial/preference columns land on the tenant's CANONICAL overlay keys; and
   every non-mapped column has an explicit disposition (Calculated / Excluded / Additional-info) so
   nothing lands as a raw Dutch overlay key and nothing is silently dropped.
3. **Automated read-only direct connection + reconciling sync (R4/R7).** An operator-run
   `GoogleSheetsSourceAdapter` reads the live Sheet directly (no manual export). A `--reconcile` mode
   keeps SAM in step with the sheet while the sheet remains h-dcn's system of record: match by
   `member_number`, upsert, and soft-flag `left` (never delete) members gone from the sheet.

Governs the SAM Members module (`sam/members`) + its runner (`scripts/aws/backfill-hdcn-members.py`)
+ the tenant onboarding config (`scripts/aws/h-dcn/members_config.json`, `members_source_mapping.csv`).
Follows steering `35-sam-module-architecture-sam.md`, `23-aws-accounts.md`, `34-backend-testing.md`.
Builds on **s5k** (optional `member_number` — numberless sponsor/club rows already import) and reuses
h-dcn's proven importer knowledge (R8).

## Background (verified 2026-09-29 — code + h-dcn migration spec)
- Transform: `sam/members/migration/hdcn_backfill.py`. `map_hdcn_row()` is a pure transform;
  TODAY `FIXED_SOURCE_COLUMNS` maps a LOWER-CASED Dutch header → dotted EN key (`personal.*` /
  `membership.*`), and any column not named there (and not the region/derived columns) folds VERBATIM
  into `overlay` under its raw header. THIS SPEC replaces that verbatim fold with a declared mapping
  contract (R0/R2.6): raw Dutch overlay keys are eliminated in favour of canonical overlay keys +
  explicit dispositions. Source adapters implement a duck-typed Protocol
  `HdcnSourceAdapter{rows(), describe()}`; today only `FileSourceAdapter` (CSV/JSON) is live —
  `LegacyDynamoSourceAdapter` is a stub, there is NO Google Sheets adapter.
- The runner `scripts/aws/backfill-hdcn-members.py` is dry-run by default; `--apply` writes via
  `repo.save_member` (single `PutItem`, s5k — no uniqueness guard). It HARDCODES `FileSourceAdapter`
  and takes `--source` (file path), `--tenant` (required, no default), `--members-config`, etc.
- The real 2026 sheet has **49 columns** with DUPLICATES: `E-mailadres` at col 12 AND col 34;
  `H-DCN Clubblad` at col 21 AND col 29 AND col 35; extra `E-Mail`/`Email Address` (cols 45/46);
  a trailing blank-named column. (Full list: `migrationHDCNLedenbestand/gdrive-member-migrate.md`
  §"All 49 Columns".)
- `personal.birth_date` already EXISTS in `fixed_fields.py` as an OPTIONAL `DATE` field; `age` and
  `birthday` already exist in `calculated_fields.py` deriving from it (both resolve to `None` when
  `birth_date` is absent). The source `Geboorte datum` is an ISO datetime
  (`1975-04-12T00:00:00.000Z`); the transform already has `_iso_date_part()` used for `joined_date`.
- The tenant's canonical overlay field keys are authored in `scripts/aws/h-dcn/members_config.json`:
  `motor_brand`, `motor_type`, `build_year`, `license_plate`, `iban`, `payment_method`,
  `magazine_pref`, `newsletter_pref`, `referral_source`, `privacy_consent`, `notes`,
  `signature_date`. These are the correct import targets (NOT raw Dutch header keys).
- Google auth: NO Sheets client exists; the repo has Drive plumbing in
  `backend/src/services/google_oauth_service.py` using `google.oauth2.service_account` +
  `googleapiclient.discovery.build` with LAZY imports. `backend/requirements.txt` already pins
  `google-api-python-client` / `google-auth-*`; the runner runs in `backend/.venv`. The SAM Lambda
  layer (`sam/shared/requirements.txt`) ships NO Google libs. The `migrationHDCNLedenbestand`
  setup doc specifies a service-account JSON at project-root `.googleCredentials.json` (gitignored)
  and the Sheet shared as **Viewer** with the SA email.

## User stories

### US1 — an explicit, complete source→target mapping (the driver)
As a tenant admin, I want the import to follow a DECLARED mapping — a defined list of target fields
(the fixed base fields, plus the tenant's overlay fields) and, for each target, exactly which
source column(s) feed it and how — so that every target whose source has a value is populated, and
nothing lands by accident or is dropped by a duplicate column. A member's real e-mail, motor
details, IBAN and payment method are covered because they are named targets in that mapping.

_The mapping is the specification, not "whatever the code happens to match":_
- _Every FIXED base field that has a source column is a named target and MUST be loaded when the
  source has a value (e.g. `E-mailadres → personal.email`, `Geboorte datum → personal.birth_date`)._
- _Every tenant OVERLAY field that has a source column is a named target loaded onto its CANONICAL
  overlay key (e.g. `Bankrekeningnummer → overlay.iban`, `Clubblad → overlay.magazine_pref`)._
- _A target MAY be fed by MORE THAN ONE source column, and ONE source column MAY drive several targets
  — the mapping declares the per-target combination/conversion rule (R0.3): e.g. the duplicate
  `E-mailadres` columns both feed `personal.email` (coalesce, first-non-empty, R1); `Bankrekeningnummer`
  drives both `overlay.iban` and `overlay.payment_method` (conditional split)._
- _A source column that is NOT a mapped target falls into one of THREE non-mapped dispositions (never a
  silent drop, and never a raw undeclared overlay key) — see R2.6:_
  - _**Calculated (not imported):** the value is DERIVED by the record, not stored. The redundant
    split-birth columns (`Geboortedag`/`Geboortemaand`/`Geboortejaar`) are here — computed from
    `birth_date` (US3/R3). The calculated-field list is OPEN and may be extended later._
  - _**Excluded (deliberately dropped):** columns not fit for purpose, or exact / near-duplicates.
    This is expected to be a LARGE list (e.g. `Bestuursfunctie`, `in functie sinds`, `Ondertekening`,
    `Naam voor akkoord`, `Inschrijfformulier`, `Jubilaris`, `KorteNaam`, the repeated `H-DCN Clubblad`,
    the near-duplicate `E-Mail` / `Email Address`, `Lidmaatschapsnummer`). Dropped by DECISION and
    listed, so the drop is observable._
  - _**Additional-info (kept, concatenated):** anything worth keeping but not worth its own field is
    CONCATENATED into a single declared `overlay.additional_info` field (label: value pairs, stable
    order) — so no real data is lost and the record stays clean (NO scattering of raw Dutch header
    keys across overlay)._

### US2 — automated direct read-only connection, run as a reconciling sync
As the operator, I want to run (repeatedly, from the CLI) a READ-ONLY direct import from the live
Sheet that RECONCILES SAM Members against the sheet, so that — for as long as the Google Sheet
remains h-dcn's system of record (i.e. until h-dcn cuts over to SAM Members) — the SAM copy stays in
step: rows present in the sheet are created/updated, and members that have disappeared from the sheet
are flagged (not deleted) for an admin to review and then delete manually.

_Semantics (see R7):_
- _Run mode: an OPERATOR CLI (not a tenant-admin UI). Dry-run stays the default; `--apply` writes._
- _Matching is ALWAYS by `member_number`. A row WITH a Lidnummer is a MEMBER → `member_number` =
  `M<shaped digits>`. A row with an EMPTY Lidnummer is a CONTACT (sponsor / sister club / dealer, not
  a member) → `member_number` = `C_` + `Achternaam` (the organisation name, which is unique and
  stable, used verbatim as the stable match key). No operator effort in the sheet, no hashing. A row
  with empty Lidnummer AND empty Achternaam is UNMATCHABLE (reported, not written)._
- _Reconciliation is an UPSERT: a matched `member_number` UPDATES the existing SAM record; an unseen
  `member_number` INSERTS a new one._
- _A SAM member whose `member_number` is ABSENT from the current sheet is SOFT-flagged
  `status = left` ("Uitgeschreven") — never hard-deleted by the sync. Deletion is a separate manual
  admin step after review._

### US3 — birth date and its derived fields
As a tenant admin, I want the birth date imported when present, so the calculated age, birthday, and
birth day/month/year/quarter are available; when the source has no birth date, those simply stay
empty (missing is missing — never a fabricated value, never a blocked import).

## Requirements

### R0 — the mapping is a declared, complete, tested contract
- **R0.1** The source→target mapping MUST be expressed as DATA in ONE authored, human- and
  Kiro-editable file — `scripts/aws/h-dcn/members_source_mapping.csv` — NOT scattered code branches.
  It has one ROW per sheet column with columns: `source_column` (`<header>#<colindex>`, R1.1),
  `col_index`, `target` (a fixed dotted key `personal.*`/`membership.*`, a canonical overlay key
  `overlay.*`, or a disposition token `(calculated)`/`(excluded)`/`(additional_info)`), `rule` (the
  combination/conversion strategy, R0.2/R0.3), and `note`. The importer LOADS this file as the
  mapping contract; editing the file (re-target a column, change a rule, move a column between
  dispositions) changes the import WITHOUT code changes. "Freezing" the mapping = committing the file.
  Any `overlay.*` target MUST be an overlay field declared in `members_config.json` (no invented keys,
  R0.4). `#`-prefixed lines are comments.
- **R0.2** Each mapping entry defines HOW the source value reaches the target via a per-target
  COMBINATION STRATEGY (R0.3): which source column(s) feed it and how they combine/convert. The
  concrete conversions the `transform` strategy composes with are: direct copy (string), ISO-date-part
  extraction (`date`, e.g. `birth_date`), member-number shaping (`member_number`), catalog-code mapping
  (`membership_type`), region canonicalization (`region`), gender normalization (`gender` — Dutch
  `Man`/`Vrouw` and `m`/`v` → the tenant enum `M`/`V`/`X`/`N`), and enum normalization with a catch-all
  fallback (e.g. `magazine` — `Clubblad` → `magazine_pref` `Geen`/`Papier`/`Digitaal`, empty/unrecognized
  → `Geen`) — the source rarely carries the target's canonical value verbatim, so most enum-ish fields
  need a normalizing transform, not a raw copy. Enum transforms are ported from h-dcn's importer.
- **R0.3** A target MAY be fed by ONE or MORE source columns, and the mapping DECLARES how they
  combine (the combination strategy is per-target, not one global rule). The supported strategies:
  - **single** — one source column → one target (the common case).
  - **coalesce (first-non-empty)** — an ORDERED list of source columns; take the first that has a
    value. Covers duplicate headers (the two `E-mailadres` columns) AND ordered fallbacks (try a
    preferred column, else a secondary). This is the same mechanism as the duplicate-header safety
    rule (R1); a bare duplicate header is just an implicit coalesce.
  - **concat** — an ORDERED list of source columns joined into one string with a declared separator
    and (optionally) per-part labels — e.g. name parts, or the `additional_info` catch-all (R2.7).
  - **transform** — a single (or coalesced) source value passed through a declared conversion:
    ISO-date-part extraction, member-number shaping, catalog-code mapping, region canonicalization,
    enum normalization with fallback (`gender`, `magazine`) (R0.2). Composable with coalesce.
  - **conditional split (one source → several targets)** — a single source column may drive MORE than
    one target, conditionally. The declared case: `iban_or_payment` on `Bankrekeningnummer` — a value
    passing a simple IBAN test sets `overlay.iban`=value and `overlay.payment_method`=`incasso`; a
    non-IBAN value sets `overlay.payment_method`=the raw text and leaves `iban` empty; empty leaves
    both unset. The `target` column names both targets as `a+b`. This is a bespoke rule (its logic is
    documented in the mapping note); it is the mechanism for "derive several fields from one source".
  The default when a mapping entry names a single column with no strategy is **single**. The design
  keeps this data-driven and EXTENSIBLE so a new target can pick the strategy it needs without new
  branching logic. A source column absent from every mapping is NOT an error — it takes a
  non-mapped disposition (Calculated / Excluded / Additional-info, R2.6).
- **R0.4** The mapping is TESTED as a contract: the CSV loads and validates (every `target` is a known
  fixed key, a declared overlay key, or a disposition token; every `rule` is a known strategy; every
  `overlay.*` target is a subset of the tenant config's overlay fields — drift guard); and a
  representative source row asserts each declared fixed/overlay target is populated from its source
  column(s).
- **R0.5** The fidelity report enumerates, for a given source, which declared targets were populated
  and which source columns were folded/observably not-mapped — so a reviewer can read the mapping
  outcome, not infer it.

### R1 — duplicate-header safety (position tracking + first-non-empty coalesce)
- **R1.1** Column POSITION is preserved so no source column is lost to a header collision. When a
  header repeats in the source, the row-builder MUST make each occurrence a UNIQUE key by appending
  its zero/one-based COLUMN INDEX to the repeated occurrences: the FIRST occurrence keeps the bare
  header, later occurrences become `<header>#<colindex>` (e.g. `E-mailadres`, `E-mailadres#34`). A
  plain `dict` (Python last-occurrence-wins) MUST NOT be relied on to resolve duplicates — that is
  precisely what silently dropped a populated value before.
- **R1.2** The row-builder disambiguation (R1.1) is applied consistently by EVERY source adapter
  (`GoogleSheetsSourceAdapter._rows_from_matrix` and the CSV/JSON `FileSourceAdapter`), so the
  transform always receives collision-free rows regardless of source.
- **R1.3** MATCHING is by BASE header: the transform strips a trailing `#<colindex>` back to the base
  header before consulting the mapping tables and dispositions. All columns sharing a base header
  therefore feed the SAME target and are combined by first-non-empty COALESCE (R0.3): the first
  non-empty value in column order wins; a later empty NEVER overwrites a populated one. (This is the
  duplicate-header safety guarantee, now a deliberate coalesce over position-tracked columns rather
  than a dict-order accident.)
- **R1.4** The coalesce applies to fixed fields (`personal.*` / `membership.*`) AND to `overlay`
  keys.
- **R1.5** A blank-named source column continues to be dropped (DynamoDB rejects empty attribute
  names) — unchanged behaviour, still surfaced in the fidelity report.
- **R1.6** No non-empty source value is silently discarded: if two DIFFERENT non-empty values share a
  base header (a genuine data conflict, not an empty duplicate), the first-in-column-order is kept
  and the conflict is OBSERVABLE in the fidelity report, keyed by the indexed column name
  (`<header>#<colindex>`) so the operator can see exactly which column lost and reconcile the source.
- **R1.7** A specific duplicate column can be targeted by its INDEXED name in a disposition — e.g.
  excluding just `h-dcn clubblad#35` (R2.6) without affecting the base `H-DCN Clubblad` at col 21.

### R2 — complete the source→member mapping
- **R2.1** Map `Geboorte datum` (and the spelling variant `Geboortedatum`) → `personal.birth_date`,
  reducing the ISO datetime to a bare `YYYY-MM-DD` via the existing date-part helper. `birth_date`
  stays OPTIONAL — an absent source cell leaves it unset (no default, no block).
- **R2.2** The redundant split birth columns (`Geboortedag` / `Geboortemaand` / `Geboortejaar`) are
  NOT imported — their value is DERIVED from `birth_date` by the calculated fields (R3), so they are
  in the CALCULATED disposition (R2.6), not stored on the record (not as a fixed field and not in
  overlay). They are listed so the non-import is observable, never a silent drop.
- **R2.3** Map the known club / motor / financial / membership-preference columns onto the tenant's
  CANONICAL overlay keys (from `members_config.json`), not raw Dutch header keys:
  `Motormerk→motor_brand`, `Type motor→motor_type`, `Bouwjaar→build_year`, `Kenteken→license_plate`,
  `Clubblad→magazine_pref` (enum, `magazine` rule), `Digitale nieuwsbrieven→newsletter_pref`,
  `WieWatWaar→referral_source`, `Opmerkingen→notes`, `Afmelding→deregistration_date` and
  `Beeindiging→termination_date` (filterable membership date fields, stored only when present).
  `Bankrekeningnummer` drives BOTH `overlay.iban` and `overlay.payment_method` via the conditional
  `iban_or_payment` rule (valid IBAN → iban=value + payment_method=`incasso`; non-IBAN text →
  payment_method=that text, iban empty) — R0.3. There is no separate `Betaalwijze` source column.
- **R2.4** A source column that is not a mapped target and not in the calculated or excluded
  dispositions (R2.6) is CONCATENATED into the single `overlay.additional_info` field (R2.7) —
  unchanged fidelity (nothing silently dropped), but WITHOUT scattering raw Dutch header keys across
  overlay.
- **R2.5** The per-field mapping summary in the fidelity report reflects the canonical overlay keys
  so a reviewer can confirm motor/financial/preference data actually landed.
- **R2.6** Every source column has exactly ONE of four explicit dispositions; the disposition of
  each real-export column is DECLARED (as data / a documented list) so it is reviewable and testable,
  never incidental:
  - **Mapped** — a fixed or overlay target (R2.1/R2.3): loaded onto the record.
  - **Calculated** — the value is derived by the record and NOT stored. Currently: `Geboortedag` /
    `Geboortemaand` / `Geboortejaar` (→ derived from `birth_date`, R3). OPEN list.
  - **Excluded** — deliberately dropped as unfit-for-purpose or (near-)duplicate. Expected to be a
    LARGE list: `Bestuursfunctie`, `in functie sinds`, `Ondertekening`, `Naam voor akkoord`,
    `Inschrijfformulier`, `Jubilaris`, `KorteNaam`, the repeated `H-DCN Clubblad`, the near-duplicate
    `E-Mail` / `Email Address`, `Lidmaatschapsnummer`, and the trailing blank-named column. Additions
    are a DECISION recorded here, not a silent code drop.
  - **Additional-info** — anything else is concatenated into `overlay.additional_info` (R2.7).
  A source column may move between Calculated / Excluded / Additional-info by editing the declared
  lists; moving a column TO Mapped requires a mapping-table entry (R0.1).
- **R2.7** `overlay.additional_info` is a single declared overlay STRING field (added to
  `scripts/aws/h-dcn/members_config.json` so it resolves/renders like any other overlay field). The
  importer builds its value by concatenating each Additional-info source column as `Label: value`
  pairs, in a STABLE order (source column order), separated by a consistent delimiter (` | `), using
  the source header as the label. Only NON-EMPTY source cells contribute; if none contribute the
  field is left unset (not an empty string).

### R3 — calculated birth fields
- **R3.1** Add read-only CALCULATED fields derived purely from `personal.birth_date`, following the
  existing `age`/`birthday` pattern (never stored; missing input → `None`, never raises):
  `birth_day` (1–31), `birth_month` (1–12), `birth_year` (YYYY), `birth_quarter` (1–4).
- **R3.2** These join the existing calculated registry (`age`, `birthday`, `display_name`,
  `years_member`, `application_year`) and MUST pass the registry's import-time uniqueness /
  no-collision-with-fixed guard.
- **R3.3** `birth_date` remains an OPTIONAL FIXED field — this requirement does NOT make it required
  and does NOT change the fixed registry's required-ness.

### R4 — automated read-only direct Google Sheets connection
- **R4.1** Add a `GoogleSheetsSourceAdapter` implementing `HdcnSourceAdapter` (`rows()`,
  `describe()`) that reads the live Sheet DIRECTLY via the Sheets API and yields the SAME
  `{header: value}` row shape as `FileSourceAdapter`, so the transform is source-agnostic.
- **R4.2** It MUST be READ-ONLY: authenticate with a service account using ONLY the
  `spreadsheets.readonly` scope (plus `drive.readonly` when resolving a sheet by title), and only
  call `spreadsheets.values.get`. It MUST NOT write, update, or delete the source (R5.2 of s5).
- **R4.3** REUSE the EXISTING h-dcn Google Cloud SERVICE ACCOUNT (`h-dcn-migration@…`, project
  `h-dcn-sheets-api`) that the h-dcn importer already uses and with which the "HDCN Ledenbestand"
  Sheet is already shared as Viewer — do NOT create a new project / service account / share. The
  importer authenticates with that service account's JSON key file at a CONFIGURABLE path
  (`--credentials`, R4.6). NOTE (verified 2026-09-29): the key file is NOT currently on disk in
  either project (it is gitignored), and the h-dcn `.secrets` holds only OAuth *client* credentials
  (`GOOGLE_CLIENT_ID/SECRET`), NOT the service-account key — a DIFFERENT credential type. So the
  operator must first place the service-account JSON key (re-download from Google Cloud, or locate the
  existing copy) at the `--credentials` path before the first live run.
  - Default `--credentials` path resolves to the SHARED h-dcn file
    `/home/peter/projects/h-dcn/.googleCredentials.json` (one key, both projects use it — no second
    secret to manage), overridable with `--credentials`. Real credentials NEVER live in the repo
    (gitignored); the value tables/mapping do.
  - A missing/invalid credentials file fails FAST with an actionable message (mirroring h-dcn's
    `test_google_connection.py` checks: file exists, valid JSON, not the template).
- **R4.4** The Google client libraries MUST be imported LAZILY (inside the adapter methods, not at
  module import), mirroring `google_oauth_service`, so importing `hdcn_backfill` in the SAM Lambda
  runtime (whose layer ships no Google libs) never fails.
- **R4.5** The adapter applies the R1 duplicate-header rule when turning the Sheets value matrix
  into rows (short rows padded to the header width; first-non-empty-wins across duplicate headers).
- **R4.6** Wire the runner to select the adapter: new mutually-exclusive source options
  (`--sheet-id` or `--sheet-name`, plus `--worksheet` and `--credentials`) vs the existing
  `--source` file. Dry-run stays the default; `--apply` still refuses a batch with mapping errors.
  `--tenant` stays required (no default tenant).

### R5 — non-destructive posture
- **R5.1** The live Sheet stays the source of truth for as long as h-dcn uses it; the importer only
  READS it and NEVER writes back.
- **R5.2** The sync never HARD-deletes a SAM member. A member gone from the sheet is soft-flagged
  (R7.4); actual deletion is a separate manual admin step after review.
- **R5.3** Idempotency is achieved by matching on `member_number` (R7): a MEMBER carries its `M…`
  Lidnummer; a CONTACT (empty Lidnummer) is keyed by `C_` + its organisation name (`Achternaam`),
  which is unique and stable. A re-run therefore updates the same record instead of minting a
  duplicate. (This supersedes the s5k caveat that numberless rows were non-idempotent.) Caveat: if a
  contact's organisation name is EDITED in the sheet, the derived `C_…` key changes → the sync treats
  it as a new contact and soft-flags the old one `left` (R7.4); this is an accepted tradeoff, made
  visible in the report — org names change rarely.

### R7 — reconciling sync (operator CLI upsert, match by member_number)
- **R7.1** The importer runs as an OPERATOR CLI (not a tenant-admin UI). Dry-run stays the default;
  `--apply` performs the reconciliation. `--tenant` stays required (no default tenant). A new
  `--reconcile`/`--sync` mode selects the upsert+absence behaviour; without it the runner keeps its
  existing insert-only backfill behaviour (backward compatible).
- **R7.2** Matching key: `member_number` ONLY, DERIVED per row (no operator sheet-editing, no hashing):
  - Lidnummer PRESENT → MEMBER, `member_number` = `M<shaped digits>` (the `member_number` rule).
  - Lidnummer EMPTY, Achternaam PRESENT → CONTACT (sponsor/club/dealer), `member_number` = `C_` +
    `Achternaam` (organisation name; unique + stable → the idempotent match key). The `M`/`C_` prefix
    also classifies the row (member vs contact) at a glance; contacts additionally carry a
    contact-ish `membership_type` from `Soort lidmaatschap` (s5k catalog code).
  - EMPTY ROW (no meaningful data — e.g. no Lidnummer, no Achternaam, no other populated field) →
    SKIPPED / excluded from the load entirely (a blank spacer row; not counted as an error, not
    written). A row that HAS some data but still derives no `member_number` (no Lidnummer and no
    Achternaam, yet e.g. an email present) is reported as UNMATCHABLE (visible, not written) so the
    operator can fix the source.
  The tenant `member_number` FORMAT constraint MUST accept both the `M…` and `C_…` forms (the closed
  `^M\d{5}$` regex is relaxed/extended so a `C_…` contact key validates) — a config impact (R2.3/R8).
- **R7.3** Reconciliation is an UPSERT keyed on `member_number`:
  - a sheet row whose `member_number` matches an existing SAM member UPDATES that record (preserving
    its internal `member_id`);
  - a sheet row whose `member_number` is not yet in SAM INSERTS a new record (minting `member_id`);
  - an EMPTY row (no meaningful data) is SKIPPED / excluded from the load (R7.2); a row that has data
    but derives no `member_number` is reported as UNMATCHABLE (not upserted) — never inserted blindly.
  - **SHEET-WINS (confirmed 2026-09-29):** on UPDATE the sheet's mapped values OVERWRITE the SAM
    record's mapped fields. While the Google Sheet is h-dcn's system of record (until cutover), SAM is
    effectively READ-ONLY for synced fields — an in-app edit to a synced field is reverted to the
    sheet value on the next reconcile. This is intended; the sheet is authoritative during the interim.
    (Non-synced/derived fields and the internal `member_id` are untouched.)
- **R7.4** Absence sweep: a SAM record (MEMBER `M…` OR CONTACT `C_…`) whose `member_number` is ABSENT
  from the current sheet is SOFT-flagged `status = "left"` (the closed `MembershipStatus` value; nl
  "Uitgeschreven"). It is NOT deleted. A record already `left` that reappears in the sheet is
  reactivated per the sheet. (Confirmed 2026-09-29: contacts are INCLUDED in the sweep — a contact
  removed from the sheet is flagged `left` like a member.)
- **R7.5** The sync reads all current SAM members for the tenant (single tenant-partition read) and
  indexes them by `member_number` to drive matching — the repository has no query-by-number, so this
  is done in memory. Members with a blank SAM `member_number` cannot be matched by number and are
  reported (they should have been given a number in the sheet, R7.2).
- **R7.6** The dry-run fidelity report for a sync enumerates: to-INSERT, to-UPDATE, to-LEAVE
  (soft-flag `left`), UNMATCHABLE (numberless sheet rows), and any ambiguous/duplicate
  `member_number` collisions in the sheet or in SAM — so the operator reviews before `--apply`.
- **R7.7** `--apply` for a sync refuses to run if the batch has mapping errors (existing rule) OR if
  the sheet contains duplicate `member_number` values (a matching hazard — the operator resolves the
  duplicate in the sheet first).

### R8 — reuse h-dcn's proven importer knowledge
- **R8.1** The auth pattern, the SERVICE ACCOUNT itself (R4.3 — same `h-dcn-migration@…`, same shared
  Sheet), the field mapping, region-variant normalization, gender normalization, Clubblad business
  rule, email "no-valid-email" indicators, and column-shift detection are REUSED/PORTED from
  `h-dcn/backend/scripts/import_members_sheets.py` v2.0 (+ `debug_sheet_headers.py` /
  `test_google_connection.py`), so this work is grounded in a proven import, not the documented
  column list alone.
- **R8.2** Ported VALUE tables are RETARGETED to the SAM module's ENGLISH canonical vocabulary
  (region / status / membership_type in `members_config.json`), NOT copied with h-dcn's old Dutch
  stored values. The mapping STRUCTURE and variant knowledge are reused; the target values are the
  SAM canonical set.
- **R8.3** The destructive parts of h-dcn's script (cleanup/delete existing members, table backup,
  `put_item` to the old `Members` table) are NOT reused — the SAM write path (`save_member`) + the
  R7 reconciling sync replace them.
- **R8.4** Duplicate-header handling is IMPROVED, not copied: h-dcn drops duplicates; s5m uses
  position tracking + first-non-empty coalesce (R1), which preserves data h-dcn's approach can lose.

### R6 — verify before done
- **R6.1** SAM tests (run via `sam/pytest.ini`): duplicate-header first-non-empty-wins (a populated
  value survives an empty duplicate); `birth_date` maps from the ISO datetime; the four calculated
  birth fields derive correctly and resolve to `None` on a missing date; motor/IBAN/payment/magazine
  columns land on the canonical overlay keys; a numberless sponsor/club row imports.
- **R6.2** `GoogleSheetsSourceAdapter` row-shaping (matrix→rows, padding, duplicate handling) is unit
  tested WITHOUT any network/live Google call (inject a fake value matrix). Importing `hdcn_backfill`
  does not require Google libs.
- **R6.3** Runner: `--sheet-id`/`--sheet-name` selects the Sheets adapter; `--source` still works;
  the two are mutually exclusive; `--tenant` still required.
- **R6.4** Reconciling sync (R7): with `--reconcile`, a sheet member_number matching an existing SAM
  member UPDATES it (same `member_id`); an unseen number INSERTS; a SAM member absent from the sheet
  is soft-flagged `left`; a numberless sheet row is reported UNMATCHABLE (not written); duplicate
  sheet member_numbers block `--apply`. A `left` member reappearing in the sheet is reactivated.
  Tested with in-memory `FakeDynamoTable` (no live AWS).
- **R6.5** SAM suite green. Live verification (real Sheet, `--apply --reconcile` against
  `nonprofit-deploy`) is a manual step gated on the operator providing `.googleCredentials.json` +
  sharing the Sheet — documented, not automated in CI.

## Out of scope
- No change to the fixed-field registry's required-ness (birth_date stays optional — R3.3).
- No auto-numbering / uniqueness guard (rejected in s5k).
- No new entity-kind model for sponsors/clubs (s5k: optional Lidnummer + `membership_type` catalog
  entry already covers them).
- No `gspread` dependency — use the already-pinned `google-api-python-client`.
- No write-back / two-way sync to the Sheet (read-only only).
- The legacy Flask/MySQL `import_members_sheets.py` (a different plane) is not modified.
