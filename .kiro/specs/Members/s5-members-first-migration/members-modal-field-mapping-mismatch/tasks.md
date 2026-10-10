# Implementation Plan

## Overview

This bugfix corrects four field-mapping mismatches in the members modal, spanning three planes:
the static config file (`scripts/aws/h-dcn/members_config.json`), the seeded MySQL
`members.field_overlay` param (projected to `config#fields`, which is what the modal actually
reads), and — for the newsletter problem only — the member RECORDS. Tasks follow the design's
**Sequencing** section: exploration/preservation tests first (written and run against UNFIXED
code), then config edits → loader guard → re-seed → projection → newsletter investigate+fix,
then verification in the modal.

**Production vs local (IMPORTANT).** The live bug is in PRODUCTION: the modal renders projected `config#fields` + member overlay data flowing from **Railway (prod MySQL) → the DynamoDB `governance_projection` / `sam-members` tables in the `nonprofit-deploy` account**. Local dev/test data is synthetic and CANNOT reproduce the prod symptom, so the config-edit + loader-guard + local re-seed tasks (3, 4, 5) prove the *mechanism* only. The projection + newsletter re-backfill + modal acceptance (the prod tasks below) must run against PRODUCTION, each with a **dry-run/preview first and an explicit human approval gate before any `--apply` / write**. The projection is subject to a version-guard that BLOCKS a config change from propagating unless the tenant row is bumped first (see the prod projection task) — this is the documented interim workaround, not the deferred proper fix.

The four problems live in different layers and are validated largely independently:

| # | Field | Class | Layer | Property |
|---|-------|-------|-------|----------|
| 1 | `newsletter_pref` | data-flow / stored-value | importer + data | Property 1 |
| 2 | `signature_date` | orphan overlay field | static config (+ re-seed) | Property 2, 3 |
| 3 | `privacy_consent` | orphan overlay field (`required:true`) | static config (+ re-seed) | Property 2 |
| 4 | `referral_source` | malformed `show_when` gate | static config (+ re-seed) | Property 5 |

---

## Tasks

- [x] 1. Write bug condition exploration tests (BEFORE any fix)
  - **Property 1: Bug Condition** - Four independent field-mapping mismatches
  - **CRITICAL**: These tests MUST demonstrate the bugs on unfixed code - do NOT fix the code or the tests when they surface the defects
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: These tests encode the expected post-fix behavior - they will validate the fix once it is applied
  - **GOAL**: Surface counterexamples that demonstrate each bug exists and confirm/refute the root-cause hypotheses (especially problem 1, which has three candidate causes)
  - **Scoped PBT Approach**: These are deterministic, config/transform-driven bugs - scope each property to the concrete failing case(s) (the specific config fields, the specific `show_when` shape, the specific source header) for reproducibility

  - Unit test `map_hdcn_row` in `sam/members/migration/hdcn_backfill.py`: build a raw row with `Digitale nieuwsbrieven = "Ja"`, run the transform, assert `record["overlay"]["newsletter_pref"] == "Ja"` — EXPECTED to PASS on current code, proving the transform is correct so the live bug is stale data or a live-header mismatch (root cause disambiguated by the investigation task 6.1)
  - Assert no row in `scripts/aws/h-dcn/members_source_mapping.csv` targets `overlay.signature_date`, yet `signature_date` is declared in `members_config.json` `field_overlay.fields` (demonstrates the orphan → the modal renders a permanently-empty "Datum ondertekening" row)
  - Assert no row in the mapping CSV targets `overlay.privacy_consent`, yet `privacy_consent` (`required: true`) is declared in the config (demonstrates the orphan "Privacy" row)
  - Test `evaluateShowWhen` in `frontend/src/components/members/fieldForm.ts`: assert `evaluateShowWhen({"field":"member_id","op":"not_exists"}, row)` returns `false` for BOTH an existing-member flat row AND an empty create-form value map (proves the gate is malformed / hides everywhere, not create-form-only)
  - Loader test in `scripts/aws/h-dcn/members_mapping_loader.py`: load the mapping contract against a config that declares an unmapped overlay field — on unfixed loader this passes silently (demonstrates the R1.5 / R2.5 gap)
  - Run the tests on UNFIXED code and document the counterexamples: newsletter transform PASSES (bug is data/header, not transform); `signature_date`/`privacy_consent` are declared-but-unbacked orphans; `referral_source` gate resolves `false` everywhere; loader accepts the orphan without complaint
  - **EXPECTED OUTCOME**: The orphan-detection, gate, and loader-guard assertions FAIL on unfixed code (this is correct — it proves the bugs exist); the newsletter transform assertion PASSES (confirming the bug is downstream of the transform)
  - Mark task complete when tests are written, run, and the outcomes are documented
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 6: Preservation** - Mapped overlay fields, other gates, header matching, and additional_info unchanged
  - **IMPORTANT**: Follow observation-first methodology — run the UNFIXED code first, record actual outputs, then assert those observed outputs across the input domain
  - Observe on UNFIXED code: `magazine_pref`, `motor_brand`, `deregistration_date`, `termination_date`, `notes`, `referral_source` render their stored values in the resolved view; record the outputs
  - Observe on UNFIXED code: `Ondertekening` + `Naam voor akkoord` concatenate into `overlay.additional_info` in stable source-column order with the ` | ` delimiter; record the output
  - **Property-based test (mapped overlay preservation)**: generate random members with random declared-and-mapped overlay values → assert every mapped overlay field still renders its stored value (Property 6, R3.1, R3.5)
  - **Property-based test (header-name matching stability)**: generate random raw rows with random column orders and duplicate headers → assert `map_hdcn_row` output is stable and matching stays keyed on the BASE header (lower-cased), NOT `col_index` — the SAM Code col-0 insertion requires no shift (Property 6, R3.2)
  - **Property-based test (additional_info concatenation)**: generate random `(additional_info)`-routed leftover columns → assert stable-order concatenation with ` | ` (Property 6, R3.3)
  - Unit test: any OTHER field carrying a `show_when` gate still toggles correctly via `evaluateShowWhen` (only `referral_source`'s gate changes) (Property 6, R3.4, R3.6)
  - Run all preservation tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior the config/loader/gate changes must not regress)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Edit members_config.json — remove orphan fields and drop the malformed referral gate

  - [x] 3.1 Remove orphan overlay fields and drop the referral_source show_when gate
    - **File**: `scripts/aws/h-dcn/members_config.json` (`field_overlay.fields`)
    - Remove `signature_date` (label "Datum ondertekening", type date, group administrative) — no mapping row targets `overlay.signature_date`; signature info is already routed to `overlay.additional_info` via the `Ondertekening` / `Naam voor akkoord` `(additional_info)` rows, and "Datum ondertekening" (col 30) already contributes to `joined_date`
    - Remove `privacy_consent` (label "Privacy", enum, `required: true`) — orphan with no source column; removal is NON-DESTRUCTIVE (no member record carries `overlay.privacy_consent`) and strictly SAFER for the CRUD form (drops an un-satisfiable always-visible required field). Do NOT add a backing source column — no privacy-consent column exists in the sheet
    - DROP the `show_when` block entirely from the `referral_source` field; keep `type: string`, `required: false`, label nl "Wie/wat/waar", order, and `functional_group: membership`. The gate shape `{"field":"member_id","op":"not_exists"}` is malformed for the implemented `evaluateShowWhen` predicate and hides the field everywhere (view AND create form); dropping it makes `referral_source` render its imported value in the read-only view and present as a free-text input on the create form
    - _Bug_Condition: isBugCondition_orphan("signature_date") = true; isBugCondition_orphan("privacy_consent") = true; isBugCondition_gate(referral_source) = true_
    - _Expected_Behavior: resolved config no longer declares signature_date/privacy_consent (Property 2); referral_source has no gate so it renders for existing members and shows on the create form (Property 5)_
    - _Preservation: all OTHER declared-and-mapped overlay fields and all OTHER show_when gates unchanged (Property 6)_
    - _Requirements: 2.2, 2.4, 2.6, 3.7_

- [x] 4. Add the R2.5 orphan-field guard to the mapping loader

  - [x] 4.1 Implement the config↔mapping orphan-field guard
    - **File**: `scripts/aws/h-dcn/members_mapping_loader.py`, in `load_mapping_contract`
    - **Where**: AFTER the row loop has populated `overlay` (the set of overlay keys the CSV maps) and BEFORE the final `if errors:` check; `declared_overlay = _declared_overlay_keys(config)` is already computed
    - Collect `mapped_overlay_keys = { key for m in overlay.values() for key in m.targets }`
    - Compute `orphans = declared_overlay - mapped_overlay_keys`, then exclude the disposition-backed key: `orphans = orphans - {"additional_info"}` (`additional_info` is populated by the `(additional_info)` disposition, NOT a mapping TARGET, so it is legitimately not in `overlay` targets; `region`/`iban`/`payment_method` DO appear as overlay targets so they are not flagged)
    - For each remaining orphan, append a `MappingContractError`-worthy message and HARD-FAIL for symmetry with the existing overlay-target drift guard (`f"config overlay field {key!r} is declared in members_config.json but has NO mapping backing in the contract (orphan-field guard, R2.5)"`)
    - _Bug_Condition: a config overlay field declared with no mapping-contract backing (isBugCondition_orphan)_
    - _Expected_Behavior: loading the contract with such a config surfaces the orphan as a contract violation rather than loading silently (Property 4)_
    - _Preservation: the existing drift guard (mapping target not declared in config) still fires; a fully-backed config still loads (Property 6)_
    - _Requirements: 2.5_

  - [x] 4.2 Verify the orphan-guard unit tests: raises then passes
    - **Property 4: Expected Behavior** - Orphan-field guard surfaces config↔mapping drift
    - **IMPORTANT**: Re-run the SAME loader tests from task 1 plus add the corrected-config assertion — do NOT rewrite the guard
    - Unit test: `load_mapping_contract` now RAISES for a config declaring a declared-unmapped overlay field (the assertion that failed silently in task 1 now fails loudly)
    - Unit test: `load_mapping_contract` PASSES for the corrected config from task 3 (no orphans remain — `signature_date`/`privacy_consent` removed)
    - Unit test: the existing drift guard still RAISES for a mapping target NOT declared in the config (unchanged direction)
    - **Property-based test (orphan guard)**: generate configs with a random extra declared-but-unmapped overlay field → assert the loader guard flags it (Property 4)
    - Run the loader against the edited config from task 3 to confirm no orphans remain (it should now pass; it would have failed before the config edit — proof the guard works)
    - **EXPECTED OUTCOME**: guard raises for orphans, passes for the corrected config
    - _Requirements: 2.5_

- [x] 5. Re-seed the config into MySQL and run the projection sync
  - **Files**: `scripts/aws/seed-hdcn-members-config.py`, projection sync (rollout C.11)
  - The modal renders the PROJECTED `config#fields` from the MySQL `members.field_overlay` param, NOT the JSON file — this step is REQUIRED for the task 3 config edits to take effect
  - Run `seed-hdcn-members-config.py --tenant h-dcn` as a DRY-RUN first to review the diff (confirm it drops `signature_date` + `privacy_consent` and clears the `referral_source` gate)
  - Re-run with `--apply` to upsert `members.field_overlay`
  - Run the projection sync (rollout C.11) so `config#fields` reflects the new `members.field_overlay` (drops the two fields, clears the referral gate)
  - **NOTE**: problems 2/3/4 are config/projection only and need NO member-record backfill — removing a field does not touch records, and the referral value is already imported
  - **NOTE (local only):** this task was executed against LOCAL Docker MySQL + local dynamodb-local and proves the seed→bump→sync MECHANISM. The PRODUCTION projection (Railway → `nonprofit-deploy` DynamoDB) is Task 5P below and is what actually fixes the modal.
  - _Bug_Condition: isBugCondition_orphan / isBugCondition_gate (as resolved via config#fields)_
  - _Expected_Behavior: resolved config#fields no longer lists signature_date/privacy_consent and carries an ungated referral_source (Property 2, Property 5)_
  - _Preservation: all other projected overlay fields unchanged (Property 6)_
  - _Requirements: 2.2, 2.4, 2.6_

- [x] 5.5 Project the config to PRODUCTION (5P) (Railway MySQL → nonprofit-deploy DynamoDB) — HIGH RISK, approval-gated
  - **HIGH RISK / APPROVAL-GATED**: this task mutates PRODUCTION (Railway prod MySQL and the real `governance_projection` DynamoDB table in the `nonprofit-deploy` account). Every mutating step runs a dry-run/preview first and STOPS for explicit human approval before any `--apply` / write.
  - **Preconditions**: Task 3 (config edit) and Task 4 (loader guard) are complete; the local mechanism (Task 5) is proven; the operator has Railway `.env` `RAILWAY_DB_*` access AND `AWS_PROFILE=nonprofit-deploy` access.
  - **Step A — dry-run seed against Railway (WRITES NOTHING):** run `PYTHONPATH=backend/src backend/scripts/railway-db.sh python scripts/aws/seed-hdcn-members-config.py --tenant h-dcn`. The seed script is dry-run by default (no `--apply`) and `railway-db.sh` maps `RAILWAY_DB_*` onto `DB_*` for this one command, so it reads Railway prod MySQL. Review the printed diff and CONFIRM it drops `signature_date` + `privacy_consent` and clears the `referral_source` gate, and NOTHING else. **STOP and get explicit user approval before Step B.**
  - **Step B — apply seed to Railway prod `members.field_overlay`:** after approval, re-run the same command WITH `--apply`: `PYTHONPATH=backend/src backend/scripts/railway-db.sh python scripts/aws/seed-hdcn-members-config.py --tenant h-dcn --apply`. This MUTATES Railway prod MySQL (`members.field_overlay`).
  - **Step C — version-guard workaround (REQUIRED, else the sync is a no-op):** bump the tenant row on Railway so the projection version advances: `backend/scripts/railway-db.sh -q "UPDATE tenants SET updated_at = CURRENT_TIMESTAMP WHERE administration='h-dcn'"`. WHY: `ProjectionSync._conditional_put` / `_supersedes` writes a `config#*` row only when its `version` STRICTLY supersedes the stored one, and `_scope_config_version(tenant)` derives that version from the TENANT row's `version`/`updated_at`/`revision`/`modified_at` — NOT the changed param (documented in `.kiro/specs/myBacklog/backlog.md`). Without this bump, `sync_administration` reports `written=0 skipped=N` and the app keeps serving the OLD config. This is the documented INTERIM WORKAROUND; the proper per-param-revision fix stays a separate backlog item.
  - **Step D — identity sanity-check BEFORE any prod DynamoDB write:** the repo `.env` exports static personal-account AWS keys + a local DynamoDB endpoint that override `AWS_PROFILE`, so they MUST be stripped. Run `env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json` and CONFIRM it prints account `506221081911` (NonprofitDeployRole), NOT `344561557829`. Do not proceed if it prints the wrong account.
  - **Step E — run the projection sync (READ Railway MySQL + WRITE the real `governance_projection` in nonprofit-deploy):** there is no standalone CLI — invoke `ProjectionSync(DatabaseSourceProvider(db), parameter_service=ParameterService(db)).sync_administration("h-dcn")` (pattern in `scripts/local/onboard-hdcn-local.py`) with `DB_*` mapped to Railway via `railway-db.sh` command mode AND the AWS env stripped/forced for nonprofit-deploy: `env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy`. This is the MUTATING prod write — gate it behind the Step A approval. Confirm the run reports `written>0` (NOT `written=0 skipped=N`, which would mean the Step C bump did not take).
  - **NOTE (fiddly env):** combining Railway-DB env mapping (`railway-db.sh` → `DB_*`) AND the nonprofit-deploy AWS env (`env -u ...` strip + `AWS_PROFILE`) in one command is error-prone. Before trusting a run, verify BOTH the `-> Railway MySQL:` banner printed by `railway-db.sh` AND the `506221081911` identity from Step D. If a fragile one-liner is unreliable, write a tiny wrapper script under `.agent-output/` that sets both env layers and invokes the sync, rather than chaining flags inline.
  - **Step F — verify:** dump the prod `config#fields` item from `governance_projection` (nonprofit-deploy) and confirm `signature_date` / `privacy_consent` are ABSENT and `referral_source` has `show_when: null`.
  - _Requirements: 2.2, 2.4, 2.6_

- [x] 6. Fix Problem 1 (newsletter) — investigate first, then fix conditionally

  - [x] 6.1 Investigate the newsletter data flow (decides the fix)
    - **IMPORTANT**: This investigation determines whether the fix is a data re-backfill (stale data) or a mapping-CSV edit (header mismatch) — do NOT change code before deciding
    - Inspect a stored member record known to have a newsletter value at source: check whether `overlay.newsletter_pref` is present
    - If absent AND the value appears inside `overlay.additional_info` → the cause is a LIVE-SHEET HEADER MISMATCH (root cause 2)
    - If absent from BOTH → the cause is STALE DATA (root cause 1, the leading hypothesis)
    - Compare the live-sheet header text against the mapping base header `digitale nieuwsbrieven` (reuse the header-debug logic referenced in the CSV: `debug_sheet_headers.py`)
    - Document which root cause holds before proceeding to 6.2
    - _Requirements: 1.1, 2.1_

 - [x] 6.2 Re-backfill affected members against PRODUCTION — HIGH RISK, approval-gated
    - **Decision from 6.1**: STALE DATA — NO code change and NO CSV change. `map_hdcn_row` already produces `overlay.newsletter_pref` correctly; the live records predated a correct import, so the fix was a member-record re-backfill, not an edit to `members_source_mapping.csv` or `sam/members/migration/hdcn_backfill.py`.
    - **Ran against PROD (not reproducible locally — synthetic data).** Read the LIVE Google Sheet, wrote the prod `sam-members` table in the `nonprofit-deploy` account (identity confirmed `506221081911` / NonprofitDeployRole before any write).
    - **Dry-run (`--reconcile`, no `--apply`) was clean:** source rows 1242, transformed ok 1215, errors 0, dup numbers 0; reconcile plan to-UPDATE=1215, to-INSERT=0, to-LEAVE=0, UNMATCHABLE=0. User approved.
    - **Applied (`--apply --reconcile`)** — upsert by `member_number` (reuses each existing `member_id`, refreshes in place; idempotent, never deletes). **Manually verified in prod: the code/data is applied — `overlay.newsletter_pref` now populated on the affected records.** ✅
    - **Sheet reference deliberately NOT stored here** (keeps the high-entropy Sheet id out of every tracked file so it can't trip ggshield/GitGuardian; the h-dcn workspace is also avoided as it will become obsolete). The operator supplies `--sheet-id` (or `--sheet-name`) at run time. Future durable home TBD — a tenant parameter for h-dcn, or a git-ignored file under a reorganized `scripts/sam/members/onboarding/h-dcn/`. Service-account key: `/home/peter/projects/h-dcn/.googleCredentials.json`.
    - **NOTE (informational, not a fix)**: the config enum declares lowercase `ja`/`nee` while the importer stores raw `"Ja"`/`"Nee"`; `renderFieldValue` stringifies verbatim so the raw value renders — the dash indicated ABSENCE, not a casing display bug. Enum casing is out of scope.
    - _Bug_Condition: isBugCondition_newsletter(member, sourceRow) — non-empty source newsletter cell but empty stored overlay.newsletter_pref_
    - _Expected_Behavior: overlay.newsletter_pref holds the source value and the modal displays it in the "Nieuwsbrief" row (Property 1)_
    - _Preservation: header-name matching still keyed on base header, not col_index (Property 6, R3.2)_
    - _Requirements: 2.1_
 
  - [x] 6.3 Verify bug condition exploration tests now pass — LOCAL tests + PROD verification
    - **Property 1: Expected Behavior** - Newsletter reaches the modal; no orphan fields; signature routed to additional_info; referral renders
    - **LOCAL (code behavior):** Re-run the SAME exploration tests from task 1 — do NOT write new tests. The task 1 assertions that previously failed now PASS on local: orphans gone from resolved `config#fields` (Property 2), signature info concatenates into `overlay.additional_info` as `Label: value` pairs (Property 3), and `evaluateShowWhen` (gate removed) shows `referral_source` for an existing member AND on the create form (Property 5). These validate CODE behavior and can pass against synthetic local data.
    - **PROD verification (after 5P + 6.2 apply):** assert the prod `config#fields` (nonprofit-deploy `governance_projection`) reflects the drops (`signature_date`/`privacy_consent` absent) and the cleared referral gate, AND that a prod member with a source newsletter value now has `overlay.newsletter_pref` populated in `sam-members` after the re-backfill (Property 1).
    - **EXPECTED OUTCOME**: local exploration tests PASS (bugs fixed in code) AND prod projection/records reflect the fix.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.7_

  - [x] 6.4 Verify preservation tests still pass — LOCAL
    - **Property 6: Preservation** - Mapped fields, other gates, header matching, additional_info unchanged
    - **LOCAL (code behavior):** Re-run the SAME preservation property tests and unit tests from task 2 — do NOT write new tests. These validate code behavior and pass against synthetic local data.
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions to mapped overlay fields, other `show_when` gates, header-name matching, or additional_info concatenation)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 7. Integration tests — LOCAL flows + PROD end-to-end verification
  - **LOCAL (where possible):** run the integration flows from Tasks 1/2 against local — resolve→view over a locally-projected `config#fields` asserts no `signature_date`/`privacy_consent` rows (Property 2, Property 3); the referral gate-removed flow shows the value in the view AND the free-text "Wie/wat/waar" input on the create form (Property 5). These validate code wiring on synthetic data.
  - **PROD end-to-end (after 5P + 6.2 apply):** perform a resolve→view / referral / newsletter end-to-end check against PRODUCTION — resolve the prod `config#fields`, view a real prod member, and confirm the referral value renders in the view + on the create form, and the newsletter value renders in the "Nieuwsbrief" row (Property 1, Property 5, R2.1, R2.6, R3.7).
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 3.7_

- [x] 8. Verify in the PRODUCTION modal (manual acceptance)
  - Done in the PRODUCTION members modal against real prod member data (after 5P projection + 6.2 re-backfill apply):
  - Newsletter renders in the "Nieuwsbrief" row for a member with a source value
  - No "Datum ondertekening" row and no "Privacy" row appear
  - "Wie/wat/waar" renders for existing members in the read-only view AND appears on the create/add-member form
  - _Requirements: 2.1, 2.2, 2.4, 2.6, 3.7_

- [x] 9. Checkpoint - Ensure all tests pass
  - Run the full unit + property-based + integration suites (backend `pytest`, frontend tests for `evaluateShowWhen`)
  - Confirm the PRODUCTION projection (Task 5P) reported `written>0` (not `written=0 skipped=N`) and the PRODUCTION modal acceptance (Task 8) passed
  - Ensure all tests pass; ask the user if questions arise

## Task Dependency Graph

Waves group tasks that can proceed together; each wave completes before the next starts. The
two test tasks (1 and 2) are independent and run first against UNFIXED code; the fix chain
(3 → 4 → 5 → 5.5 → 6 → 7 → 8 → 9) is strictly sequential. Task 5 proves the seed→bump→sync
mechanism LOCALLY; Task 5.5 (labelled "5P") then runs the same projection against PRODUCTION
(so 5.5 depends on 5). Task 6 (newsletter re-backfill + verification) needs the prod projection
live, so it depends on Tasks 3 and 5.5; Task 7 depends on Tasks 5.5 and 6.

```json
{
  "waves": [
    {
      "id": 1,
      "name": "Wave 1 - Exploration & Preservation Tests (BEFORE fix)",
      "tasks": ["1", "2"],
      "dependsOn": [],
      "description": "Write bug condition (Property 1) and preservation (Property 6) tests and run them against unfixed code"
    },
    {
      "id": 2,
      "name": "Wave 2 - Edit members_config.json",
      "tasks": ["3"],
      "dependsOn": ["1", "2"],
      "description": "Remove orphan overlay fields and drop the malformed referral_source show_when gate"
    },
    {
      "id": 3,
      "name": "Wave 3 - Loader orphan-field guard",
      "tasks": ["4"],
      "dependsOn": ["3"],
      "description": "Add the R2.5 config↔mapping orphan-field guard and verify it"
    },
    {
      "id": 4,
      "name": "Wave 4 - Re-seed MySQL + projection sync (LOCAL mechanism)",
      "tasks": ["5"],
      "dependsOn": ["4"],
      "description": "Re-seed the config into local members.field_overlay and run the projection sync so local config#fields reflects the edits — proves the seed→bump→sync mechanism"
    },
    {
      "id": 5,
      "name": "Wave 5 - Project the config to PRODUCTION (5P) (HIGH RISK, approval-gated)",
      "tasks": ["5.5"],
      "dependsOn": ["5"],
      "description": "Run the seed + version-guard tenant bump + projection sync against Railway prod MySQL → nonprofit-deploy governance_projection, dry-run first with an approval gate before each write"
    },
    {
      "id": 6,
      "name": "Wave 6 - Newsletter investigate + prod re-backfill",
      "tasks": ["6"],
      "dependsOn": ["3", "5.5"],
      "description": "Investigate the newsletter data flow, re-backfill affected members against prod sam-members (approval-gated), and verify exploration (local + prod) and preservation (local) tests"
    },
    {
      "id": 7,
      "name": "Wave 7 - Integration tests (local + prod end-to-end)",
      "tasks": ["7"],
      "dependsOn": ["5.5", "6"],
      "description": "Run the resolve→view, referral, and newsletter flows locally where possible plus a prod end-to-end check"
    },
    {
      "id": 8,
      "name": "Wave 8 - Manual verification in the PRODUCTION modal",
      "tasks": ["8"],
      "dependsOn": ["7"],
      "description": "Manually confirm the fixes render correctly in the production members modal"
    },
    {
      "id": 9,
      "name": "Wave 9 - Checkpoint",
      "tasks": ["9"],
      "dependsOn": ["8"],
      "description": "Run the full unit + property-based + integration suites; confirm prod projection written>0 and prod modal acceptance passed"
    }
  ]
}
```

```
Tests first (independent of each other, before any fix):
  Task 1  (Bug Condition exploration tests) ──┐
  Task 2  (Preservation property tests)    ──┤
                                              │
Fix chain:                                    │
  Task 3  (edit members_config.json)          │
     │                                         │
     ▼                                         │
  Task 4  (loader orphan guard)               │
     4.1 (implement guard) ──▶ 4.2 (verify)   │
     │                                         │
     ▼                                         │
  Task 5  (re-seed MySQL + projection sync — LOCAL mechanism)
     │                                         │
     ▼                                         │
  Task 5.5 (5P) (project the config to PRODUCTION — HIGH RISK, approval-gated)  ◀── depends on Task 5
     │                                         │
     ├──────────────┐                          │
     ▼              ▼                          │
  Task 6  (newsletter investigate + prod re-backfill)  ◀── depends on Tasks 3 and 5.5
     6.1 (investigate) ──▶ 6.2 (prod re-backfill, approval-gated)
                              ──▶ 6.3 (verify exploration tests: local + prod)
                              ──▶ 6.4 (verify preservation tests: local)
     │
     ▼
  Task 7  (integration tests: local + prod end-to-end)  ◀── depends on Tasks 5.5 and 6
     │
     ▼
  Task 8  (manual verify in PRODUCTION modal)  ◀── depends on Task 7
     │
     ▼
  Task 9  (checkpoint — run full suite)  ◀── last
```

Ordering summary:
- Tasks 1 and 2 come first and are independent of each other (both written and run against UNFIXED code).
- Task 3 (config edit) → Task 4 (loader guard: 4.1 → 4.2) → Task 5 (LOCAL re-seed + projection sync) form the config fix chain that proves the mechanism.
- Task 5.5 (labelled "5P": PRODUCTION projection — HIGH RISK, approval-gated) depends on Task 5 (mechanism proven locally first); it runs the seed + tenant-row version-guard bump + projection sync against Railway prod MySQL → nonprofit-deploy DynamoDB.
- Task 6 (6.1 investigate → 6.2 prod re-backfill → 6.3 verify exploration tests local+prod → 6.4 verify preservation tests local) depends on Tasks 3 and 5.5.
- Task 7 (integration: local + prod end-to-end) depends on Tasks 5.5 and 6.
- Task 8 (manual verify in the PRODUCTION modal) depends on Task 7.
- Task 9 (checkpoint) is last.

## Notes

- **Re-seed + projection sync is required for config edits to take effect.** The modal renders
  the PROJECTED `config#fields` from the MySQL `members.field_overlay` param, NOT the
  `members_config.json` file. Editing the JSON (Task 3) is inert until Task 5 re-seeds the param
  and runs the projection sync (rollout C.11).
- **Only the newsletter problem needs a member re-backfill.** Problems 2/3/4 (`signature_date`,
  `privacy_consent`, `referral_source`) are config/projection only — removing a field does not
  touch records, and the referral value is already imported. Only Problem 1 (newsletter) may
  require re-importing member RECORDS (Task 6.2).
- **Enum casing is out of scope.** The config enum declares lowercase `ja`/`nee` while the
  importer stores raw `"Ja"`/`"Nee"`; `renderFieldValue` stringifies verbatim, so the raw value
  renders correctly. The dash in the modal indicates ABSENCE of a value, not a casing display
  bug — no casing normalization is part of this fix.
- **`privacy_consent` removal is non-destructive.** No member record stores
  `overlay.privacy_consent`, so dropping the declared field removes an un-satisfiable
  always-visible `required: true` field from the CRUD form without touching any data.
- **Production projection is version-guarded.** A `members.field_overlay` change does not
  propagate to `config#fields` on its own — `_scope_config_version` derives the projection
  version from the tenant row, not the param (documented in `myBacklog/backlog.md`). Task 5P
  bumps `tenants.updated_at` on Railway before syncing as the interim workaround; the proper
  per-param-revision fix is a separate backlog item, out of scope here.
- **Prod writes are approval-gated.** Every production mutation (5P seed `--apply`, 5P
  projection sync, 6.2 re-backfill `--apply`) runs dry-run/preview first and STOPS for explicit
  human approval; identity is sanity-checked to `506221081911` before any nonprofit-deploy
  DynamoDB write.
- **h-dcn Ledenbestand sheet id** = `1k4hOeyzrDi9SuVSN9J8ekxXyMCGNNdrSo3ulUV4y7rg` (worksheet
  `Ledenbestand`). Not secret (an identifier, not credentials); recorded here so the
  backfill/reconcile command is not reconstructed from shell history each time. The
  service-account key stays out of the repo at `/home/peter/projects/h-dcn/.googleCredentials.json`.
