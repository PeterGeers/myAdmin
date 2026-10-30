# Implementation Plan: Admin-driven field/form model (03b)

## Overview

This plan implements design.md's build units (BU-1..BU-10) in the **EXPAND → DEPLOY → VERIFY →
CONTRACT** rollout order so the data is converted before the re-pointed code runs (Req 6.4), and
removal of the old apparatus happens last so rollback survives. Languages: **Python** (SAM Members
plane `sam/members/`, Flask scope-mirror plane `backend/src/`), **TypeScript** (frontend). The
design specifies concrete languages and seams — no language or structure selection is required.

Spine: BU-1..BU-3 (the unified enum-field model, Req 3) land first because every other unit depends
on the option shape. The membership_type collapse is proven orphan-free against the full live h-dcn
member population (design "Migration-safety proof"); `region` is already unified (no migration);
the scope gate is axis-vs-value (Req 4); the forbidden `choices` key is removed (`options` canonical).

**Non-negotiable safety gate (Req 6.4, design "Migration"):** the EXPAND fold into `config#fields`
runs and is verified BEFORE the re-pointed reader is relied upon; a transitional catalog fallback OR
a lock makes the deploy order non-fatal; the `membershiptype#<code>` catalog rows are retired
(CONTRACT) only AFTER the all-tenant post-fold scan passes. The membership-type management
UI/routes/CRUD are removed in a LATER change than the migration, so rollback is preserved.

**Promotion gate (analysis D5, seed):** `test → main` stays BLOCKED until 03b lands AND the
membership_type migration (+ any residual 03a `choices`→`options` backfill) runs against PRODUCTION,
integrity-scan-gated, identically to TEST.

Shell hints — READ `.kiro/steering/41-shell-environment.md` first (authoritative for this WSL
workspace): the UNC-vs-POSIX path split; inline POSIX `cd` (never the `cwd` param); the terminal
always reports `Exit Code: -1` so judge success by the in-band `<<<DONE marker=$?>>>` marker; pagers
disabled; Python venv `backend/.venv`; scratch under repo-root `.agent-output/`; AWS account caveats
(`personal` vs `nonprofit-deploy`). Tech stack + file-size guidance: `.kiro/steering/11-tech-stack.md`.

## Tasks

- [x] 1. BU-1 — Unified option model + option-integrity write-seam (Req 3, the spine)

  - [x] 1.1 Extend `EnumOption` with `allowed` + `order`
    - `sam/members/domain/fixed_fields.py`: add `allowed: bool = True` and `order: int | None = None`
      to `EnumOption` (`{value, label{nl,en}, roles?}`); an absent `allowed` reads `true` (back-compat)
    - Ensure every serializer that emits options carries the two new keys (resolved view, API DTO)
    - _Steering: 38-sam-module-field-config, 39-backend-data-access-sam-dynamodb, 35-sam-module-architecture, 11-tech-stack_
    - _Requirements: 3.1_

  - [x] 1.2 Add option-integrity checks at the config write seam
    - `sam/members/domain/config_write_service.py` (same seam as the kept invariants 1/2): reject a
      write that would leave a required or off-form enum with zero `allowed:true` options (Req 3.4a);
      reject removal/rename of an option `value` still referenced by a member (via the injected
      `usage_probe` used by the delete-field guard) with a caller-safe message naming the option (Req 3.2a)
    - KEEP invariant 1 (`application_choices` ⊆ options) and invariant 2 (known `format.checker`)
    - _Steering: 38-sam-module-field-config, 39-backend-data-access-sam-dynamodb, 36-config-and-parameters, 30-backend-api-flask-mysql (caller-safe errors), 11-tech-stack_
    - _Requirements: 3.2a, 3.4a_

  - [x] 1.3 Write-seam + option-model tests (change-with-tests)
    - `sam/tests/test_config_write_service.py`: zero-`allowed` rejected; in-use option cannot
      vanish/rename; `allowed:false` permitted; relabel permitted
    - **Property 1 / Property 2** round-trip over the REAL `config#fields` fixture (Task 7.x):
      read→write→read preserves `membership_type` options incl. `erelid`=`allowed:false`
    - **Validates: Requirements 3.1, 3.2, 3.2a, 3.4a**
    - `cd backend && source .venv/bin/activate && pytest sam/tests/test_config_write_service.py -q`

- [x] 2. BU-2 + BU-3 — reference check + assembly read the field, not the catalog (Req 3)

  - [x] 2.1 Re-point the membership_type reference check to the field options
    - `sam/members/domain/_membership_writes_validation.py` `_validate_membership_type_reference`:
      replace `self._repo.get_membership_type(...)`/`entry.active` with a lookup against the resolved
      `membership_type` field options — unknown value → `MEMBERSHIP_TYPE_UNKNOWN_REFERENCE`, present
      but `allowed:false` → `MEMBERSHIP_TYPE_RETIRED`; keep the value-changed-only guard so existing
      members with a retired/removed value stay valid (Req 3.2/3.2a)
    - Default when off the form (`_membership_writes_application._default_membership_type`): first
      `allowed:true` by `order`, NOT a catalog read (Req 3.4a)
    - Transitional fallback OR lock (coordinate with Task 6): while catalog rows still exist, a field
      with NO inline options MAY fall back to the catalog; removed in CONTRACT (Task 8)
    - _Steering: 38-sam-module-field-config, 39-backend-data-access-sam-dynamodb, 30-backend-api-flask-mysql (caller-safe errors), 11-tech-stack_
    - _Requirements: 3.2, 3.2a, 3.4a_

  - [x] 2.2 Assembly seam reads the field's own options (no catalog injection)
    - `sam/members/domain/_membership_writes_fieldconfig.py` `get_field_config` /
      `_assemble_field_options`: stop injecting `list_membership_types(active_only=True)`; options come
      from the field's resolved `options` (one assembly pass, no per-kind branch); drop the standalone
      `membership_type_options` feed
    - _Steering: 38-sam-module-field-config, 39-backend-data-access-sam-dynamodb, 11-tech-stack_
    - _Requirements: 3.3_

  - [x] 2.3 Reference-check + assembly tests (change-with-tests)
    - `sam/tests/test_membership_writes*` / resolved-field surface tests: unknown/retired/
      grandfathered-existing against field options; default-from-options when off-form; no catalog injection
    - **Validates: Requirements 3.2, 3.2a, 3.3, 3.4a**
    - `cd backend && source .venv/bin/activate && pytest sam/tests/ -q -k "membership or resolved_field"`

- [x] 3. BU-4 — remove the hardcoded field bindings (Req 1)

  - [x] 3.1 Remove the no-relax + overlay-invariant + forced-required/visible
    - `config_write_service._collect_application_attr_reasons`: delete invariant 3 (the
      `platform_required and application_required is False` reject) + the `platform_required` plumbing
    - `field_resolver._reject_invalid_overlay`: delete the `override.required is False and fixed.required`
      clause (keep unknown-key/collision/dangling-group/choiceless-non-scope-enum)
    - Frontend `ApplicationFieldAttributes.tsx`: drop `requiredForced = isPlatformRequired || isMembershipType`
      (no force-on/disabled); keep "off the form → default supplied"
    - _Steering: 38-sam-module-field-config, 35-sam-module-architecture, 32-frontend-ui, 11-tech-stack_
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 3.2 Tests prove the admin is not overruled (change-with-tests)
    - Delete/invert the relax assertions: `test_config_write_service.py` (~753/829),
      `test_field_resolver.py:209`, `test_status_retirement_preservation_props.py:397`; KEEP
      "two axes don't alias" in `test_field_models_application_attrs.py`
    - **Property 3**: for any field but `member_id`, no save is rejected on an unauthored binding
    - **Validates: Requirements 1.1, 1.2, 1.4**

- [x] 4. BU-5 — config toggles persist both ways at the ROOT (Req 2)

  - [x] 4.1 Fix the change-op diff root cause
    - `frontend/.../fieldConfigChangeOps.ts`: diff against the LOADED state so a true→false transition
      emits an explicit `false` (stop treating `undefined` as both "unchanged" and "off"); the attr
      emitters no longer omit a deliberately-false attribute
    - Toggle call sites `ApplicationFieldAttributes.onToggleRequired` / `ApplicationFieldModal.toggleOnForm`
      send the explicit boolean (not `? true : undefined`). Backend `set_field_application` already SETs false
    - _Steering: 32-frontend-ui, 38-sam-module-field-config, 39-backend-data-access-sam-dynamodb, 11-tech-stack_
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 4.2 Round-trip-every-boolean test (change-with-tests)
    - `fieldConfigChangeOps.test.ts` + `ApplicationFieldAttributes.test.tsx` / `ApplicationFieldModal.test.tsx`:
      ON→OFF→ON for EVERY boolean attribute in EVERY modal, so a future boolean cannot regress the same way
    - **Property 4**: OFF→save→reload shows OFF (explicit `false`, never dropped `undefined`)
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
    - `cd frontend && npx vitest --run src/components/TenantAdmin/MembersConfig`

- [x] 5. BU-9 — display + filter by resolved per-language label (Req 5)

  - [x] 5.1 Filter/search match the resolved per-language label OR the stored key
    - `frontend/.../useMembersColumns.ts` `searchedRows` + `enrichedRows` (`columnValue.coerceByType`):
      for enum columns a search term matches if it matches the resolved per-language label (via
      `resolveEnumValueLabel`/`labelResolver`) OR the stored key — both. nl `Overleden`, gb
      `Passed Away`, AND the raw stored key `died` all match the same `died` row (label matching is
      ADDED on top of key matching; key matching is NOT removed). Build a per-column value→label map
      ONCE (not per row per keystroke); two options sharing a label match both keys. Key stays stored verbatim
    - _Steering: 32-frontend-ui, 38-sam-module-field-config (per-language labels), 11-tech-stack_
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 5.2 Filter-parity test (change-with-tests)
    - `applicationFilterParity.test.ts` + a `useMembersColumns` test: the NL label, the GB label, AND
      the raw stored key all filter the same row (label OR key both supported)
    - **Property 6**: every enum display AND filter resolves `label[locale]→en→nl→value`
    - **Validates: Requirements 5.1, 5.2, 5.3**
    - `cd frontend && npx vitest --run`

- [x] 6. BU-6 — scope derive-on-save; axis-vs-value gate; two-call orchestration (Req 4)

  - [x] 6.1 Derive config#scope from the field + two separate frontend calls
    - Frontend scope-field save makes TWO calls (no runtime cross-plane call): SAM
      `PUT /members/config/scope` (derive the dimension from the field's options, authoritative) THEN
      the Flask `members.scope_dimensions` mirror call. Flask→SAM `scopegrant#` projection unchanged
    - _Steering: 35-sam-module-architecture, 39-backend-data-access-sam-dynamodb, 30-backend-api-flask-mysql, 31-backend-database-flask-mysql, 32-frontend-ui, 11-tech-stack_
    - _Requirements: 4.1, 4.2_

  - [x] 6.2 Axis-vs-value gate (atomic) + error + resync
    - VALUE add/remove within the same scope field → auto-apply on both planes (grants extend/shrink;
      tenant admin owns the data consequence). SCOPE-AXIS change (the set of `scope.enabled` fields
      changes, incl. turning scope off) → do NOT auto-apply, do NOT persist `scope.enabled` (atomic
      refusal), surface "create a project with your System Administrator"
    - On a detected mirror-call failure: caller-safe error + a resync button on the scope screen; SAM authoritative
    - _Steering: 35-sam-module-architecture, 30-backend-api-flask-mysql (caller-safe errors), 32-frontend-ui, 11-tech-stack_
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 6.3 Scope-gate tests (change-with-tests)
    - value-add/remove auto-applies on both planes; axis-change blocks atomically with the SysAdmin
      message and persists nothing; mirror-failure surfaces error + resync
    - **Property 5**: value change auto-applies + config#scope == field options; axis change gated
    - **Validates: Requirements 4.2, 4.5, 4.6**
    - `cd backend && source .venv/bin/activate && pytest sam/tests/ -q -k scope` ; `cd frontend && npx vitest --run`

- [x] 7. BU-7 — data migration (EXPAND + VERIFY), TEST then PROD (Req 6)

  - [x] 7.1 Commit the real-row fixture + the integrity-scan (the proof)
    - Commit a real `config#fields` + membership-type-catalog + member-tally fixture under
      `backend/tests/fixtures/`; implement the integrity scan asserting zero un-folded catalog rows and
      zero orphaned member references (the design proof), runnable per-tenant
    - _Steering: 39-backend-data-access-sam-dynamodb (prove round-trips against REAL data), 34-backend-testing, 23-aws-accounts, 41-shell-environment, 11-tech-stack_
    - _Requirements: 3.6, 6.2, 6.3_

  - [x] 7.2 EXPAND migration script (fold catalog → field options; drop forbidden `choices`)
    - `sam/members/migration/`: fold each tenant's CURRENT membership types into the `membership_type`
      field's `options` (`value`=type_code, `label`, `order`, `allowed`=`active`; `erelid`→`allowed:false`)
      and REMOVE the forbidden legacy `choices` key wherever it co-exists with `options` (incl. region).
      Idempotent + re-runnable; back up every affected row first; LIST the resulting values for owner verification
    - _Steering: 39-backend-data-access-sam-dynamodb, 38-sam-module-field-config, 23-aws-accounts, 41-shell-environment, 42-local-dynamodb-testing, 11-tech-stack_
    - _Requirements: 6.1, 6.2_

  - [x] 7.3 Run EXPAND + VERIFY on TEST (`test_*` tables)
    - Back up → dry-run → apply the fold on `test_governance_projection` / `test_sam-members`; run the
      all-tenant integrity scan (7.1); confirm the listed values; account `nonprofit-deploy` (506221081911)
    - _Steering: 23-aws-accounts, 41-shell-environment, 42-local-dynamodb-testing_
    - _Requirements: 6.3, 6.4, 6.5_

- [x] 8. Checkpoint — EXPAND verified on TEST before DEPLOY relies on it
  - Confirm the fold + all-tenant scan pass on TEST and the SAM/Flask/frontend unit suites are green.
    The re-pointed reader (Tasks 2/3) must have its transitional fallback/lock in place so DEPLOY order
    is non-fatal. Ask the user if questions arise.

- [x] 9. DEPLOY — ship BU-1..BU-6 + BU-9 to TEST via CI/CD (mandatory, steering 43)
  - [x] 9.1 Deploy the SAM + frontend changes
    - Ship through `deploy-sam-members.yml` (OIDC `NonprofitDeployRole`, acct `506221081911`,
      `eu-west-1`, no stored secrets; branch decides env — `test`→test stack). Frontend TEST is the
      local dev server. Confirm CodeQL + GitGuardian green before merge to `test`; verify the stack
      settles and the config/scope write paths are live in TEST
    - _Steering: 43-cicd-deploys, 23-aws-accounts, 35-sam-module-architecture_
    - _Requirements: 8.4_

- [x] 9b. BU-8a — FRONTEND: membership_type is a regular enum field everywhere (close the all-planes gap)
  - [x] 9b.1 Field-config modal edits membership_type inline like any enum
    - `frontend/src/components/TenantAdmin/MembersConfig/MembersFieldModal.tsx`: for a `reference` field (membership_type), render the inline options editor (the same `EnumOptionsEditor`) with the per-option `allowed` (retire/grandfather) control = the "reference status", editing the field's own `options` — NOT `form.choices`. REMOVE the "values are managed in the catalog, not here" note + the `onManageCatalog` catalog pointer. Move the enum path off `form.choices` onto the single `options` vocabulary (03a canonical). Key stays immutable; label/order/required/visible/scope-axis stay editable.
    - _Steering: 32-frontend-ui, 38-sam-module-field-config, 33-frontend-testing, 11-tech-stack_
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 9b.2 Application-form editors source membership_type from the field's own options
    - `ApplicationFieldAttributes.tsx`, `ApplicationFieldModal.tsx`, `applicationChoiceSource.ts`, `applicationMembershipType.ts`, `ApplicationFormPreview.tsx`: the membership_type subset picker + preview source their vocabulary from the field's RESOLVED `options` (allowed-filtered), NOT the live `GET /membership-types` catalog. No runtime catalog read remains on the authoring path.
    - _Steering: 32-frontend-ui, 38-sam-module-field-config, 33-frontend-testing, 11-tech-stack_
    - _Requirements: 3.1, 3.2, 3.4a_
  - [x] 9b.3 Frontend parity tests (change-with-tests)
    - Paired vitest: the field-config modal shows the inline options editor (NOT the catalog note) for membership_type and writes `options`; the application-form picker/preview resolve from the field's options; no component calls `GET /membership-types` on the authoring path.
    - _Steering: 33-frontend-testing, 11-tech-stack_
    - _Requirements: 3.1, 3.2, 3.3, 3.4a_

- [x] 10. BU-8 — CONTRACT: retire catalog rows then remove dead code (Req 7), AFTER verify
  - All children done: 10.1 (TEST catalog rows retired), 10.2 (frontend apparatus), 10.3 (dead
    binding/reconciliation/choices), 10.4 (net −2900 LOC recorded), 10.5 (SAM apparatus). PROD
    catalog-row retirement is Task 12.1.
  - [x] 10.1 Retire the `membershiptype#<code>` catalog rows (data) — TEST
    - DONE on TEST (`test_sam-members`, account `nonprofit-deploy` 506221081911, verified
      `aws sts get-caller-identity` = 506221081911 NonprofitDeployRole, NOT personal).
    - GATE verified against real data BEFORE deleting: the EXPAND fold (Task 7.3) already landed —
      h-dcn's `config#fields` row (in `test_governance_projection`) carries all 7 membership_type
      codes as INLINE field options (gewoon_lid/gezins_lid/erelid[allowed:false]/donateur/
      gezins_donateur/sponsor/overig), and the re-pointed field-options-only reader is live in TEST
      (Task 9.1). Deleting the catalog therefore strands nothing.
    - BACKUP FIRST (reversible): full content of all 7 rows saved to
      `.agent-output/BACKUP_test_sam-members_membershiptype_20261030-185441.json` (restorable by
      put-item).
    - DELETED exactly the 7 `h-dcn membershiptype#<code>` rows by exact PK+SK (no scan-delete).
      Post-delete verify: `begins_with(sk,"membershiptype#")` scan → Count 0 (table 1260→1253,
      −7); `config#fields` membership_type options → still 7 (untouched). Member references
      grandfathered (not touched).
    - PROD retirement is Task 12.1 (same procedure on `sam-members`) — NOT done here.
    - _Steering: 39-backend-data-access-sam-dynamodb, 23-aws-accounts, 41-shell-environment_
    - _Requirements: 6.4_ 

  - [x] 10.2 Remove the membership-type management apparatus — FRONTEND (code)
    - DONE (committed `e4ca04a09`): deleted `MembershipTypesManager.tsx` / `MembershipTypeModal.tsx` + their test, the
      `list/create/update/deactivate MembershipType` client wrappers (+ re-exports + body types),
      the TenantAdmin dashboard tab + barrel re-exports. Re-pointed the member add/edit form read
      path off the catalog onto the field's own resolved `options` (dropped the `listMembershipTypes`
      async feed + the `membershipTypes` prop plumbing + `fieldForm`'s `membershipTypeOptions`/
      `isMembershipTypeField`/`MEMBERSHIP_TYPE_FIELD_KEY`). Updated all paired tests to the eager
      field-options path. Frontend trees green (2196 passed); CRUD guard [OK]. Net −1696 LOC.
    - _Steering: 32-frontend-ui, 33-frontend-testing, 11-tech-stack_
    - _Requirements: 7.2_

  - [x] 10.5 Remove the membership-type catalog apparatus — SAM PLANE (routes, module, repo WRITE methods, transitional fallback)
    - Delete the `GET/POST/PUT/DELETE /membership-types` RouteSpecs (`handler/routes.py`) + their
      dispatch arms (`handler/_dispatch_members.py`); remove `_membership_catalog.py` + the repository
      WRITE methods (`save_membership_type`/`deactivate_membership_type`) from `members_repository.py`
      (interface + pending-stub + impl) and the `MembershipService` catalog methods. KEEP the repository
      READ (`list_membership_types`/`get_membership_type`) — the EXPAND migration
      (`membership_type_catalog_to_field_options.py`, Tasks 10.1/12) reads it to fold the catalog.
      Remove the transitional catalog fallback (Task 2.1) in `_membership_writes_validation.py` /
      `_membership_writes_fieldconfig.py` — the reader is now field-options-only. Migrate the ~95 SAM
      fixture tests that seed `membership_type` via a catalog to author inline `EnumOption`s instead
      (change-with-tests); update the parity harness that asserts the 5 catalog routes exist; the
      pre-03b `hdcn_catalog_seed.py` seed path that uses the WRITE methods must be retired alongside.
      Iterate the FULL SAM suite to green before marking done (do NOT leave it half-migrated → red).
    - _Steering: 35-sam-module-architecture, 39-backend-data-access-sam-dynamodb, 34-backend-testing, 11-tech-stack_
    - _Requirements: 7.2_

  - [x] 10.3 Delete the removed-binding plumbing + dead reconciliation + forbidden `choices` code
    - DONE. Three parts, grounded in what actually runs (verified against `ProjectionSync`, not
      assumed):
    - **(a) Dead scope reconciliation — DELETED.** Removed `reconcile_scope_change` /
      `ScopeChangeReconciliation` / `ScopeReconciliationBlocked` / `assert_appliable` (+ the
      `list_grants` helper only it used, + the unused `dataclass`/`field` import) from
      `backend/src/services/user_tenant_scope_service.py`, and their whole test section from
      `backend/tests/unit/test_user_tenant_scope_service.py` (+ the dead `list_grants` branch in
      the test's FakeDB). Confirmed NO production caller (grep across `backend/`, frontend = zero).
      This superseded spec-02 tasks 3.9/3.10 (03b Req 4's axis-vs-value gate is the real gate, not
      the orphan-block). `pytest tests/unit/test_user_tenant_scope_service.py` -> 29 passed.
    - **(b) No-relax / overlay-invariant plumbing — already gone.** Task 3 already DELETED the
      no-relax reject (invariant 3 + `platform_required` reject clause) from
      `config_write_service._collect_application_attr_reasons` and the relax clause from
      `field_resolver._reject_invalid_overlay`, and the frontend `requiredForced`. Verified: the
      only remaining `platform_required` use is the LIVE Req 3.4a option-integrity check
      (`_collect_option_integrity_reasons`), not the removed binding. Nothing left to delete.
    - **(c) Forbidden `choices` read/write — already gone on the SAM plane (03a).** The SAM reader
      (`_fields_overlay_reader.py`) no longer reads stored `choices`; the SAM write surface
      (`FIELD_DEFINITION_ATTRS`) rejects it; the EXPAND migration strips it from data. The ONLY
      residual `choices` read/write code is the Flask `config#*` projection builders — which
      `ProjectionSync` NO LONGER emits (spec-02 1.15/3.7/5.8) and which are the reversible
      rollback path still feeding the not-yet-run PROD migrations. Deleting them now would break
      the live migration scripts + spend the rollback net before PROD is verified, and is already
      owned by spec-02's GATED end-of-band cleanup (Task 1.19 + scope/mail peers, gated on the
      Task 8 PROD promotion). DEFERRED there — captured in
      `.kiro/specs/myBacklog/spec02-config-builder-end-of-band-cleanup.md` so it is not forgotten.
      Do NOT touch `config#views` (confirmed no `choices` intersection there).
    - _Steering: 39-backend-data-access-sam-dynamodb, 38-sam-module-field-config, 34-backend-testing, 11-tech-stack_
    - _Requirements: 7.3, 7.4, 7.5, 7.6_

  - [x] 10.4 Record the net code-decrease delta
    - DONE. The 03b simplification is a net code DECREASE across every touched Members plane
      (Req 7.7 evidence), measured with `git diff --shortstat`:
    - **CONTRACT branch `spec/03b-contract-sam-catalog-removal`** (base `69657c4f` → HEAD, Tasks
      10.5 + 10.3): 33 files changed, **693 insertions / 1898 deletions = net −1205 LOC**; 2 files
      deleted (`test_membership_type_catalog_read_routes.py`,
      `test_membership_type_catalog_write_routes.py`), 1 added (this backlog doc). By area:
      - SAM product code (`sam/members/`): 7 files, 24 ins / 457 del = **net −433 LOC** (catalog
        routes, dispatch arms, `_membership_catalog.py`, repo WRITE methods, transitional fallback).
      - SAM tests (`sam/tests/`): 22 files, 543 ins / 1109 del = **net −566 LOC** (+2 test files
        deleted) — migrated off the catalog onto inline options.
      - Backend Flask (`backend/`): 2 files, **net −326 LOC** (10.3 dead scope-reconciliation).
    - **Frontend removal (Task 10.2, earlier branch `e4ca04a09`):** already recorded there — **net
      −1696 LOC** (MembershipTypesManager / MembershipTypeModal + their test, catalog client
      wrappers, dashboard tab, prop plumbing).
    - **Before/after of the 03b CONTRACT simplification** (total file length `wc -l` of touched
      code files, branch base `69657c4f` → HEAD for SAM/Flask; Task 10.2's recorded figures for
      frontend):

      | Scope | Files before | Files after | Δ files | LOC before | LOC after | Δ LOC |
      | --- | --- | --- | --- | --- | --- | --- |
      | SAM + Flask (this branch, Tasks 10.5 + 10.3) | 31 | 29 | −2 | 18,581 | 17,256 | −1,325 |
      | Frontend (Task 10.2, branch e4ca04a09) | — | — | −3 | — | — | −1,696 |
      | **03b CONTRACT total** | | | **≈ −5** | | | **≈ −3,021** |

    - The earlier 03b phases (BU-1..BU-9, merged to `test` in separate PRs) were net-ADDITIVE
      feature work (the unified option model, write-seam, scope trigger, EXPAND migration) — the
      CONTRACT phase is where the simplification lands, removing ~3k LOC of retired
      catalog/binding/reconciliation apparatus. Net decrease confirmed (Req 7.7 / Req 8.3 DoD).
      (The `git diff --shortstat` line-change view of the same branch is 693 ins / 1898 del =
      −1205; it counts changed lines, the table counts total file length — same direction.)
    - _Steering: 40-spec-workflow, 11-tech-stack_
    - _Requirements: 7.7, 8.3_

- [ ] 11. BU-10 — governance: steering + docs (Req 8)
  - [ ] 11.1 Update steering + data-model docs
    - Update `.kiro/steering/38-sam-module-field-config.md` where it documents the removed no-relax/forced
      rules; update `sam/members/docs/data-model.md` + `config-guide.md`: the unified enum model
      (reference as a field feature with `allowed`), `config#fields`/`config#scope` are SAM-authored
      (not MySQL-projected), document the `application_*` field attributes (close the doc gap), the
      forbidden-`choices` removal, the membership-type catalog retirement
    - _Steering: 40-spec-workflow, 38-sam-module-field-config_
    - _Requirements: 3.5, 8.1, 8.2_

- [ ] 12. PROD migration + promotion gate (Req 6, analysis D5)
  - [ ] 12.1 Run EXPAND + VERIFY + CONTRACT on PRODUCTION identically to TEST
    - Back up → dry-run → apply the fold on `governance_projection` / `sam-members`; run the all-tenant
      integrity scan; retire the catalog rows; account `nonprofit-deploy` (506221081911). Only after the
      PROD scan passes is `test → main` unblocked
    - _Steering: 43-cicd-deploys, 23-aws-accounts, 41-shell-environment_
    - _Requirements: 6.4, 6.5, 8.4_

  - [ ] 12.2 Checkpoint — promotion readiness
    - Confirm 03b landed, PROD migration + all-tenant scan passed, CI gates green. The `test → main`
      promotion gate (seed) is satisfied only now. Ask the user before merging to `main`.

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "dependsOn": [] },
    { "wave": 2, "tasks": ["2", "3", "4", "5", "6"], "dependsOn": ["1"] },
    { "wave": 3, "tasks": ["7"], "dependsOn": ["1", "2"] },
    { "wave": 4, "tasks": ["8"], "dependsOn": ["7"] },
    { "wave": 5, "tasks": ["9"], "dependsOn": ["8", "3", "4", "5", "6"] },
    { "wave": 6, "tasks": ["9b"], "dependsOn": ["9"] },
    { "wave": 7, "tasks": ["10"], "dependsOn": ["9b"] },
    { "wave": 8, "tasks": ["11"], "dependsOn": ["10"] },
    { "wave": 9, "tasks": ["12"], "dependsOn": ["10", "11"] }
  ]
}
```

```
1 (BU-1 option model + write-seam)   ── the spine; everything depends on the option shape
│
├─> 2 (BU-2/3 reference check + assembly read the field)
├─> 3 (BU-4 remove hardcoded bindings)
├─> 4 (BU-5 toggle root-cause fix)
└─> 5 (BU-9 filter/display by label)
        │
6 (BU-6 scope derive-on-save + axis-vs-value gate)  ── depends on 1 (option shape); independent of 2–5
│
7 (BU-7 EXPAND migration + integrity-scan)  ── needs 1/2 landed in code (reader re-pointed, fallback/lock ready)
│
8 (CHECKPOINT: EXPAND verified on TEST)  ── gates 9; requires 2's transitional fallback/lock in place
│
9 (DEPLOY BU-1..6 + BU-9 to TEST, CI/CD)  ── after 8
│
9b (FRONTEND: membership_type a normal enum on every admin surface) ── before CONTRACT removes the catalog
│
10 (BU-8 CONTRACT: retire catalog rows, THEN remove dead code)  ── after 9 verifies the re-pointed reader live
│
11 (BU-10 governance: steering + docs)  ── after the model is final (10)
│
12 (PROD migration + promotion gate)  ── LAST; unblocks test→main only after PROD scan passes
```

Critical ordering (safety): 1 → 2 → 7 (EXPAND) → 8 (verify) → 9 (deploy) → 9b (frontend parity) → 10 (contract) → 12 (prod).
Tasks 3, 4, 5 are parallelizable after 1. Task 6 is parallelizable after 1. The CONTRACT removals
(10) MUST follow DEPLOY+verify (9) so rollback survives; the membership-type UI/routes/CRUD removal
(10.2) is deliberately a later change than the migration (7).

## Notes

- **Spine first.** Task 1 (the `EnumOption` shape + option-integrity write-seam) is the dependency
  root; do not start 2–6 until the shape is merged, or they will diverge on the option contract.
- **EXPAND before the re-pointed reader is relied upon (Req 6.4).** The re-pointed reader (Task 2)
  ships with a transitional catalog fallback OR a lock so a deploy that lands before the fold cannot
  break member writes. Remove the fallback only in CONTRACT (10.2).
- **CONTRACT is last and reversible-until-then.** Catalog rows are retired (10.1) only after the
  TEST post-fold scan passes and the re-pointed reader is confirmed live; the management UI/routes/
  CRUD removal (10.2) is a separate, later change so rollback is preserved.
- **TEST ⇄ PROD parity (analysis D5).** The same migration + all-tenant integrity scan runs on TEST
  (Task 7.3) and PROD (Task 12.1); `test → main` is BLOCKED until the PROD scan passes.
- **Change-with-tests (steering 30/34/39).** Every behavioral task updates its paired test in the
  SAME change; property tests round-trip against the REAL h-dcn fixture, never a hand-built one.
- **Account/identity (steering 23/41).** All migration/scan work targets `nonprofit-deploy`
  (506221081911); sanity-check `aws sts get-caller-identity` before any PROD action.
- **Scope coordination is frontend-only (Req 4).** No runtime SAM↔Flask call; the frontend makes the
  two calls, and the reconciliation code is DELETED (10.3), not wired in.
- **Do NOT touch `config#views`** (deferred feature; backlog `members-preferred-overview-columns.md`).
