# S5k — Tasks (member identity & Lidnummer cleanup)

Legend: `[ ]` todo · `[H]` human-run/gated (prod deploy / prod data cleanup) · `(dt)` test-first.
Per steering `34-backend-testing` (SAM via `sam/pytest.ini`), `35-sam-module-architecture-sam`,
`36-config-and-parameters`, `41-shell-environment` (WSL paths; `<<<DONE marker=$?>>>`; no sleep;
strip `.env` AWS keys for nonprofit-deploy). Ship SAM via `deploy-sam-members.yml`; frontend via
GitHub Pages. Small spec — no config/projection/registry work.

## Phase 1 — SAM: optional member_number + delete generation hook (R2, D1)
- [x] **1.1 (dt)** Tests: a member with an EMPTY `member_number` saves OK; a member with an
  arbitrary string (`ABCDEFG`) saves OK; a present value that violates the tenant
  `member_number_format` is rejected (422); empty passes validation.
- [x] **1.2** Remove any "required non-empty member_number" precondition; keep the optional
  `validate_member_number_format` check (present-value-only). (`fixed_fields.py` member_number
  `required=False`; `_validate_member_number` still present-value-only.)
- [x] **1.3** DELETE `hdcn_derive_member_number` + its `register_hdcn_hooks` registration
  (`tenants/hdcn/hooks.py`); keep `hdcn_validate_member`. Retire/unwire the `DERIVE_MEMBER_NUMBER`
  HookName. Remove the create-path `next_counter`/derive call in `MembershipService.create_member`.

## Phase 2 — SAM: delete the uniqueness-guard mechanism (R3, D2)
- [x] **2.1 (dt)** Tests: `save_member` issues a SINGLE `PutItem` (no `TransactWriteItems`); no
  `membernum#` item is written; two saves with the same number BOTH succeed (guard gone — a
  duplicate is data-quality, not blocked).
- [x] **2.2** `repository/members_repository.py` `save_member`: drop the transaction, the guard
  item, the `attribute_not_exists` condition, and `MemberNumberConflictError`. Single `PutItem`.
  (Also `next_counter` + `_is_conditional_check_failed` removed; `delete_member` = single `DeleteItem`.)
- [x] **2.3** Retire the `membernum#` sort-key token from `repository/table_design.py`.
  (`member_number_sk`, `counter_sk`, `RECORD_TYPE_MEMBERNUM`, `RECORD_TYPE_COUNTER` all removed.)
- [x] **2.4** Check for any read path that resolved a member via `membernum#<number>` (reverse
  lookup); replace with a query/list if one exists. (None found — reads are by `member_id`.)
- [x] **2.5 (optional, D3)** Soft duplicate-check on save (query-and-warn, never block).
  **DEFERRED — closed, not implemented** (decided): a duplicate member number is a data-quality
  concern, not a write-time concern, and the h-dcn backfill fidelity report already surfaces
  reused numbers pre-apply.

## Phase 3 — Frontend: member_id containment (R1, D4)
- [x] **3.1** Audit the members UI for `member_id` used as a displayed/administrative value
  (columns, modal rows, exports, labels); remove/replace with `member_number`. Keep it as the
  internal row/React key only. Add a guard test if practical.
  - Table: already shows `member_number` (Lidnummer), not `member_id`. Modal: already omits the
    UUID (s5j removed the mislabeled row). Both clean — no change needed.
  - **CSV export FIXED** (`MembersPage.tsx` `handleExport`): it exported the internal `member_id`
    UUID as the first column (NL-mislabeled "Lidnummer") and read a hardcoded flat-key subset, so
    ~30 columns came out blank and the real Lidnummer was absent. Reworked to use the SAME resolved
    field config as the view modal — `formFields` → `groupFieldsBySection` for the column set
    (functional-group order), `valueFor` + `renderFieldValue` for each cell. `formFields`
    structurally omits `member_id` + system timestamps, so the UUID can no longer leak into the
    export; the real `member_number` and every personal/overlay/calculated field now carry values.
  - Guard test: `MembersExport.test.tsx` now asserts the CSV contains `member_number` (M#####) +
    overlay values and does NOT contain the `member_id` UUIDs. 4/4 export tests pass.
  - NOTE (pre-existing, unrelated): one failing test in `MembersPage.viewContexts.test.tsx`
    ("synthesizes a single default context … fixed columns" — a `Noord` Badge assertion) fails
    identically with the export change stashed, so it is NOT caused by s5k. Left as-is.

## Phase 4 — Verify + ship + prod cleanup (R4)
- [x] **4.1** SAM suite + affected frontend tests green (judge by summary). SAM: GREEN, zero
  failures via `sam/pytest.ini` (full suite, [100%]). Frontend: 66/66 green across
  `MembersExport`, `membersApiService`, `fieldValue`, `fieldForm`. One PRE-EXISTING, unrelated
  failure in `MembersPage.viewContexts.test.tsx` (a `Noord` Badge assertion) — confirmed not
  caused by s5k (fails identically with the export change git-stashed); tracked, not a blocker.
- [ ] **4.2 [H]** Ship: SAM via `deploy-sam-members.yml`; frontend via Pages.
- [ ] **4.3 [H]** Prod data cleanup: delete the 1152 `membernum#` guard rows for h-dcn (idempotent,
  tenant-scoped script). Verify none remain.
- [ ] **4.4 [H]** Prod verify: create a member with a typed `M#####` → saves (single item, no
  guard); create a sponsor with no number → saves; edit a member → no guard write; CloudWatch clean.
- [ ] **4.5** Governance DoD: mark the backlog item done; note auto-numbering as considered &
  rejected and the "suggest next number" toggle as a possible future opt-in.

## Done criteria
- `member_number` is an optional plain string (numeric, alphanumeric, or empty); optional
  per-tenant format validation retained; NO auto-generation; `hdcn_derive_member_number` deleted.
- The `membernum#` guard mechanism is gone (`save_member` = single `PutItem`); guard rows deleted
  in prod; a duplicate number does not corrupt state.
- `member_id` never shown as administration.
- All tests green; verified in prod.
