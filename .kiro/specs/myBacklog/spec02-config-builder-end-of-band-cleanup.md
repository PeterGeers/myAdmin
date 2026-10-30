# Spec-02 end-of-band cleanup — delete the dead Flask `config#*` projection builders

**Status:** DEFERRED / GATED — do NOT do under 03b. Owned by spec
`Members/02 - members-config-sam-owned-write-path`. Recorded here (from 03b Task 10.3) so it is
not forgotten.

## Why this is a backlog item, not 03b work

03b Task 10.3 says "remove `choices` read/write code paths". While doing it we confirmed (from
`ProjectionSync.sync_administration`) that **ProjectionSync now emits ZERO `config#*` rows** — the
SAM write path is the authoritative author of `config#fields` / `config#scope` / `config#mail`.
The three Flask builders (`build_config_fields_row` / `build_config_scope_row` /
`build_config_mail_row`) are therefore **unwired from emission** — BUT they are NOT dead yet:

- They are still called by the one-off migration scripts
  `backend/scripts/migrate_config_{fields,scope,mail}_to_sam.py` (the scripts that MOVE each
  tenant's data to SAM), and
- They are still the **reversible rollback path** until each record is read-back verified live in
  PROD, and
- They are still the authoring half of several SAM round-trip / e2e tests
  (`sam/tests/test_config_roundtrip_props.py`, `sam/tests/test_scope_e2e.py`) and Flask builder
  unit tests (`backend/tests/unit/test_projection_content_gate.py`, the
  `test_build_config_fields_row_*` tests in `test_projection_sync.py`).

Spec-02's **non-negotiable per-record safety gate** (02 tasks.md, Design "Per-record sequenced
cutover", Req 10.1/10.3): the SAM write path must be read-back verified in PROD **before** the
builder removal merges to `main`. The row must always have exactly one authoritative writer, never
zero. Deleting the builders now would (a) break the live migration scripts that still need to run
on PROD, (b) spend the rollback net before PROD is verified, and (c) duplicate an already-sequenced
gated task. So: deferred, not done.

## The gate (what must be true before any of this runs)

Spec-02 **Task 8 (TEST → PROD promotion)** is still `[ ]`. The cleanup below is unblocked only
after, per record:
- SAM is the authoritative author **in PROD** and read-back verified;
- the operational MySQL cleanup has run (`--delete-mysql --i-have-prod-verified`) — **irreversible,
  rollback net spent, explicit user go-ahead required**.

## The deferred cleanup tasks (consolidated)

### 1. `config#fields` builder removal — spec-02 Task **1.19** (already written, `[ ]`, GATED)
- Operational prerequisite: `migrate_config_fields_to_sam.py --write --prod --delete-mysql
  --i-have-prod-verified` → delete migrated `members.field_overlay` + retired
  `members.default_page_size` MySQL rows (Req 10.6).
- DELETE `build_config_fields_row` (+ helpers only it used) from
  `backend/src/services/_projection_fields_builder.py` / `_projection_config_builders.py` and its
  import/export from `projection_sync.py`.
- DELETE the migration script `backend/scripts/migrate_config_fields_to_sam.py` + its unit test
  `backend/tests/unit/test_migrate_config_fields_to_sam.py`.
- DELETE the builder-only tests: the `test_build_config_fields_row_*` tests in
  `test_projection_sync.py`, the config#fields cases in `test_projection_content_gate.py`, and
  `test_members_label_fold_roundtrip.py`'s config#fields legs.
- **This is also where the forbidden `choices` write/read on the Flask plane finally goes** — the
  `"choices"` entry in `_OVERLAY_FIELD_DEFAULTS` / `_FIXED_OVERRIDE_FIELDS` and the choices-derive
  in `_map_fixed_override`, plus the `or _collect(spec.get("choices"))` read fallback in
  `_members_config_fields._field_enum_values` / `_projection_config_common._enum_values_from_field`.
  (The SAM plane already stopped reading/writing `choices` in 03a; this is the last residue, and it
  rides out on the config#fields builder deletion — NOT a separate piecemeal edit.)

### 2. `config#scope` builder removal — NOT yet an explicit spec-02 task (prose-only in 3.7)
- Operational prerequisite: PROD run of `migrate_config_scope_to_sam.py` (02 task 3.4 ran TEST
  only; PROD happens at the Task 8 promotion).
- DELETE `build_config_scope_row` (+ helpers only it used) from `_projection_scope_builder.py` /
  `_projection_config_builders.py` and its re-export from `projection_sync.py`.
- DELETE the migration script `backend/scripts/migrate_config_scope_to_sam.py` + its unit test.
- Rewire the SAM round-trip/e2e tests that currently author via `build_config_scope_row`
  (`sam/tests/test_config_roundtrip_props.py`, `sam/tests/test_scope_e2e.py`) to author the
  `config#scope` row via the SAM write path (`MembersConfigWriteRepository.put_config`) instead.
- `members.scope_dimensions` PARAM stays (it is the frontend-written mirror the grant validators
  read) — do NOT delete it.

### 3. `config#mail` builder removal — spec-02 Task **5.8** marks this DEFERRED to Step 8
- Operational prerequisite: PROD read-back verify done (02 task 5.5 deletes the migrated
  `members.mail_*` MySQL rows after PROD verify).
- DELETE `build_config_mail_row` (+ helpers only it used) from `_projection_mail_builder.py` /
  `_projection_config_builders.py` and its re-export.
- DELETE the migration script `backend/scripts/migrate_config_mail_to_sam.py` + its unit test.
- Retire the `members.mail_enabled` / `mail_domain` / `mail_local_part` / `mail_certified` /
  `application_consent_notice` params (+ `mail_reply_to_default` only if it pre-existed as a param).
- Rewire any SAM test authoring via `build_config_mail_row` (fixtures in
  `sam/tests/test_members_projection_reader.py` / `test_config_write_service.py`) to the SAM shape.

### 4. Verify-no-residue (all three)
- grep `build_config_{fields,scope,mail}_row`, `field_overlay`, `default_page_size`, and the
  forbidden `choices` key across `backend/` → zero live refs.
- Run the affected suites green (`test_projection_sync.py`, `test_projection_content_gate.py`, the
  SAM round-trip/e2e suites) on both planes.

## Cross-spec note — 03b superseded spec-02 3.9/3.10

03b Task 10.3 **DELETED** `UserTenantScopeService.reconcile_scope_change` /
`ScopeChangeReconciliation` / `ScopeReconciliationBlocked` / `assert_appliable` (+ their tests in
`backend/tests/unit/test_user_tenant_scope_service.py`). Those were BUILT by spec-02 tasks 3.9/3.10
but 03b's design (BU-6 / analysis) ruled them dead: the axis-vs-value gate (03b Req 4) is the real
scope-change gate, not the orphan-block reconciliation. So spec-02 3.9/3.10 are **superseded** —
they should be marked as such (their deliverable was intentionally removed by 03b), not re-built.
