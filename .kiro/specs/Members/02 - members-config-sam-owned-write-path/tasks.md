# Implementation Plan: Members config — SAM-owned write path (Phase 1)

## Overview

This plan implements the net-new, SAM-owned write path for exactly three tenant-level
`governance_projection` rows — `config#fields`, `config#scope`, `config#mail` — as a strict
**per-record sequenced cutover** (`config#fields` → `config#scope` → `config#mail`). All shared
write infrastructure (API Gateway PUT route, Members Lambda edge wiring, `MembersConfigWriteRepository`,
SAM version model, scoped IAM WRITE grant) is front-loaded into the first record's step (Design Roadmap
Step 0 + Step 1).

The authoring model is **one typed door per concern**. Each per-record migration **deletes** the
migrated `members.*` MySQL rows once SAM is read-back verified live in PROD (reversible until then),
so no raw/MySQL door remains. `config#mail` carries `mail_certified` as a required fail-closed bool
on the written row. Task 7 is the **typed-UI + single-authoring-door** work — the net-new typed Mail
function plus re-instating the blanket `members`-namespace exclusion in the Advanced raw editor — and
introduces **no** raw JSON grid for any Members concern. It depends on the `config#mail` cutover
(Task 5) being complete because the Mail function authors `config#mail`.

Languages: **Python** (SAM Members plane + Flask plane), **TypeScript** (frontend service). The design
specifies concrete languages, so no language selection is required.

Non-negotiable **safety gate** (Design "Per-record sequenced cutover", Requirement 10.1/10.3): for each
record, the SAM write path is live and read-back verified in PROD **before** the ProjectionSync builder
removal merges to `main`. The row always has exactly one authoritative writer, never zero. This ordering
is encoded in the task dependencies and the dependency graph below.

Shell hints — READ `.kiro/steering/41-shell-environment.md` first; it is the authoritative source for how to run commands in this WSL workspace. It covers the details that are easy to get wrong and are NOT repeated in full here:

- the UNC-vs-POSIX path split (file/read/validate tools use the `\\wsl.localhost\Ubuntu\...` UNC path; the bash/terminal tool uses the `/home/peter/projects/myAdmin/...` POSIX path — never cross them);
- always use an inline POSIX `cd` inside the command (never the `cwd` parameter, which emits broken Windows-style paths);
- the terminal integration ALWAYS reports `Exit Code: -1` even on success — judge success by stdout/stderr content and the in-band `<<<DONE marker=$?>>>` marker (`marker=0` = success), not the tool's exit code;
- pagers are disabled globally (do not let `less`/`more` block the shell);
- the Python venv is `backend/.venv`;
- scratch/log output goes under the repo-root `.agent-output/` (git-ignored);
- running anything against Railway uses the `backend/scripts/railway-db.sh` wrapper (see the `#database` skill), and AWS identity/account caveats (profiles `personal` vs `nonprofit-deploy`) are in the steering file too.

Quick convenience commands (the common cases — the steering file is the full reference):

```bash
# DEFAULT: stream stdout + judge success by the in-band marker (NOT the tool's Exit Code: -1).
# Most pytest/vitest summaries need NO file — read them straight from the streamed output.
# Flask / backend tests
cd /home/peter/projects/myAdmin && cd backend && source .venv/bin/activate && pytest <paths> -q; printf '\n<<<DONE marker=%s>>>\n' "$?"
# SAM tests (sam/tests)
cd /home/peter/projects/myAdmin && cd backend && source .venv/bin/activate && pytest sam/tests/<file> -q; printf '\n<<<DONE marker=%s>>>\n' "$?"
# frontend tests (vitest)
cd /home/peter/projects/myAdmin && cd frontend && npx vitest --run <path>; printf '\n<<<DONE marker=%s>>>\n' "$?"

# FALLBACK — only when output is long/verbose or a scratch file is genuinely needed:
# redirect to the repo-root .agent-output/ (git-ignored; ALWAYS the repo-root absolute POSIX
# path, never a relative .agent-output/ from inside backend/), then read that file, then clean up.
cd /home/peter/projects/myAdmin && mkdir -p .agent-output && cd backend && source .venv/bin/activate \
  && pytest <paths> -q > /home/peter/projects/myAdmin/.agent-output/pytest.out 2>&1; printf '\n<<<DONE marker=%s>>>\n' "$?"
# then read /home/peter/projects/myAdmin/.agent-output/pytest.out and remove it when done.
```

## Tasks

- [ ] 1. Shared SAM write infrastructure + `config#fields` cutover (Roadmap Step 0 + Step 1)

  - [x] 1.1 Create `MembersConfigWriteRepository` (versioned put_item, closed set, fail-fast table)
    - New file `sam/members/repository/projection_config_write_repository.py`, sibling of
      `projection_config_reader.py`
    - Define the closed `_WRITABLE_CONFIG_IDS = frozenset({schema.CONFIG_ID_SCOPE, schema.CONFIG_ID_FIELDS, schema.CONFIG_ID_MAIL})`
    - Lazy fail-fast table resolution via `schema.get_projection_table_resource()` from
      `GOVERNANCE_PROJECTION_TABLE` (no default); injectable `table` for tests
    - `put_config(tenant_id, config_id, attributes, version)`: raise `ValueError` on blank `tenant_id`
      and on `config_id ∉ _WRITABLE_CONFIG_IDS`; build key via
      `schema.build_key(tenant_id, schema.build_sort_key(schema.RECORD_TYPE_CONFIG, config_id))`;
      stamp `schema.VERSION_ATTR`; `put_item` the merged item
    - Reuse schema tokens only (`PARTITION_KEY_ATTR`, `SORT_KEY_ATTR`, `VERSION_ATTR`) so writer/reader cannot drift
    - _Requirements: 1.4, 1.6, 2.1, 2.3, 2.4, 3.5, 5.1, 5.2, 5.5_

  - [x] 1.2 Write unit tests for the write repository
    - New `sam/tests/test_projection_config_write_repository.py`: versioned `put_item` writes the
      expected key + `version` + attributes; closed-set guard raises on `views`/unknown id; blank
      `tenant_id` raises before any `put_item`; fail-fast table resolution raises when
      `GOVERNANCE_PROJECTION_TABLE` is missing/blank
    - **Property 2: Split-ownership prefix invariant** — repo writes only `config#{fields,scope,mail}`,
      never `tenant`/`module#`/`role#`/`scopegrant#`/`config#views`
    - **Validates: Requirements 2.1, 2.3, 2.4, 5.2, 5.5**
    - `cd backend && source .venv/bin/activate && pytest sam/tests/test_projection_config_write_repository.py -q`

  - [x] 1.3 Implement the SAM version model (monotonic ISO-8601 write stamp)
    - Add `next_write_stamp()` returning `datetime.now(timezone.utc).isoformat()` in the SAM config-write
      module (service or a small `version.py` helper)
    - Do NOT port Flask `_config_row_version` (max-of-params) — it is dead code once SAM writes atomically
    - Keep the row-level `version` separate from `config#mail` `application_consent_notice.version`
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

  - [x] 1.4 Write version-stamp tests
    - **Property 3: Idempotent / monotonic version stamp** — a later write yields a
      lexicographically-greater stamp; re-put of identical attributes + version is a no-op; row stamp is
      independent of consent-notice version
    - **Validates: Requirements 6.2, 6.4, 6.5**

  - [x] 1.5 Implement the config-write domain service
    - Per-`configId` body validation seam (no boto3 in the domain); for `fields` validate
      `fields`/`overrides`/`functional_groups` shape ONLY — do NOT author `default_page_size`
      (retired per Req 7.2 / Requirement 25); compute the write stamp; delegate
      `(tenant_id, config_id, attributes, version)` to `MembersConfigWriteRepository`
    - Preserve each per-field `scope` attribute verbatim for Task 2 derivation
    - _Requirements: 1.2, 7.1, 7.2, 7.3, 6.1_

  - [x] 1.6 Add API Gateway `PUT /members/config/{configId}` route + Members Lambda edge wiring
    - Route through the existing Members edge (`sam/members/handler/app.py`, `ANY /{proxy+}` surface)
    - `sam/shared` verified-JWT + `Tenant_Admin` entitlement; resolve `tenant_id` from the token (never body)
    - Validate `configId ∈ {fields, scope, mail}` at the route — reject `views`/unknown with 400/404,
      no write; on success return `{success, configId, version}` 200
    - SAM-plane error conventions (`35`): unexpected exception logged server-side, generic client message,
      never echo `str(e)`
    - _Requirements: 1.1, 1.2, 1.3, 2.2, 2.5, 3.1, 3.2, 3.3, 3.4, 17.1, 17.2_

  - [x] 1.7 Write edge/route tests
    - Auth/entitlement rejection (401/403) never reaches the repo; unknown/`views` configId → 400/404;
      valid write returns 200 with authoritative `version`; tenant resolved from token not body
    - **Validates: Requirements 1.1, 1.3, 2.2, 2.5, 3.1, 3.3, 17.1**

  - [x] 1.8 Add the scoped IAM WRITE grant to `sam/members/template.yaml`
    - New statement `Sid: MembersWriteGovernanceProjectionConfig`, `Action: dynamodb:PutItem` only,
      resource = projection table ARN, `dynamodb:LeadingKeys` pinned to the caller's tenant
    - Leave the existing `MembersReadGovernanceProjection` read statement unchanged
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 1.9 Author the `config#fields` row through the write path (Step 1)
    - Wire the `fields` branch end-to-end: domain service authors `fields`/`overrides`/`functional_groups`
      ONLY, in the exact shape `MembersProjectionReader.get_overlay` reads; preserve per-field `scope`
    - Do NOT author `default_page_size` — the tenant-level `default_page_size` is RETIRED (Req 7.2):
      rows-per-page is the per-user runtime selector (Requirement 25), not a `config#fields` attribute
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 1.4, 1.5_

  - [x] 1.10 SAM round-trip equivalence test for config#fields
    - Update `sam/tests/test_config_roundtrip_props.py`
    - **Property 1: Round-trip write/read equivalence** — after `put_config('fields', ...)`,
      `get_overlay` returns equivalent values. Drop any `get_default_page_size` assertion — the accessor
      is retired by Requirement 25 (no tenant `default_page_size` is authored on or read from `config#fields`)
    - **Validates: Requirements 1.4, 1.5, 7.4, 8.1(fields subset)**

  - [~] 1.11 Deploy SAM write infra + IAM grant via `deploy-sam-members.yml` (CI/CD — mandatory)
    - Ship Tasks 1.1–1.9 through `deploy-sam-members.yml` (OIDC `NonprofitDeployRole`, acct
      `506221081911`, `eu-west-1`, no stored AWS secrets); branch decides env (`test`→test stack)
    - Confirm CodeQL + GitGuardian green before merge to `test`; verify stack settles and the PUT route
      is live in TEST
    - _Requirements: 19.1, 19.3, 5.3_

  - [~] 1.12 Migrate `config#fields` per tenant + read-back verify + delete migrated MySQL rows (operational, PRE builder removal)
    - Copy every live tenant's `members.field_overlay` into the SAM-owned `config#fields` row
      (minimum `h-dcn`); read back via the reader to verify. Migrate `members.field_overlay` ONLY
    - `members.default_page_size` is RETIRED by Requirement 25 (rows-per-page is now the per-user
      runtime selector), so it is NOT migrated / NOT re-homed — it is DELETED by the same `members.*`
      cleanup below, never copied to SAM
    - Keep MySQL params until SAM is verified live in PROD (reversible); run in TEST then PROD
    - After PROD read-back verify, DELETE the migrated `members.field_overlay` MySQL row AND the retired
      `members.default_page_size` MySQL row so no raw/MySQL authoring door remains for those keys
      (deletion happens only after the PROD read-back verify — reversible until then; keep the
      verify-before-delete discipline)
    - _Requirements: 10.1, 10.2, 10.4, 10.5, 10.6, 14.2, 5.3, 5.4_

  - [~] 1.13 Repoint `config#fields` save in `membersConfigService.ts` + simplify UX
    - Repoint the fields save from Flask `parameter_admin_routes` to `PUT /members/config/fields`;
      drop the "pending projection" state (SAM write is authoritative); editors consume service unchanged
    - _Requirements: 13.1, 13.2, 13.3_

  - [~] 1.14 Update frontend tests for the repointed fields save
    - Assert the service PUTs to `/members/config/fields` and treats the write as authoritative
    - **Validates: Requirements 13.1, 13.2, 13.4**

  - [~] 1.15 Remove `build_config_fields_row` from ProjectionSync + retire MySQL params (merge to main ONLY after 1.12 PROD-verified)
    - Remove the `build_config_fields_row(...)` append in `ProjectionSync.sync_administration`
      (`backend/src/services/projection_sync.py`); leave scope/mail builders in place
    - Retire `members.field_overlay` (migrated to SAM) in the same change; also DELETE the
      `members.default_page_size` param — it is RETIRED by Requirement 25 (not migrated, not carried
      forward anywhere), so it is removed as a retired param rather than re-homed
    - Keep `SyncResult`/`TenantSource`/`SourceProvider`/`DatabaseSourceProvider` surface unchanged
    - Flask-plane `error_response` + `error_id` convention (`30`) on any touched Flask caught-exception path
    - _Requirements: 10.3, 11.1, 11.2, 11.4, 11.5, 17.3_

  - [~] 1.16 Update ProjectionSync tests to assert config#fields NOT emitted (change-with-tests)
    - Update `backend/tests/unit/test_projection_sync.py` property/preservation tests
    - **Property 4: ProjectionSync no longer emits config#fields** and
      **Property 5: Delete-sweep safety** — verify `_reconcile_scopegrants` + `delete_config_views_residue`
      never touch `config#fields`. The delete-sweep guardrail is VERIFIED / regression-locked by
      Requirement 12 (12.5: `config#*` rows are UPSERT-ONLY, only the `config#views`-only residue cleanup
      ever deletes a `config#` row) — it is no longer an open question
    - The existing regression test `test_sync_reconcile_never_deletes_non_scopegrant_rows` MUST stay green
      AND be EXTENDED (12.6) so a SAM-authored `config#fields` row survives a full
      `ProjectionSync.sync_administration` + `_reconcile_scopegrants` cycle under split ownership (the
      split-ownership survival case) — keep the change-with-tests framing (`30`, `34`)
    - **Validates: Requirements 11.2, 11.3, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6**
    - `cd backend && source .venv/bin/activate && pytest tests/unit/test_projection_sync.py -q`

  - [~] 1.17 Members table rows-per-page runtime selector + DynamoDB cursor paging (OQ-6 RESOLVED, Component 10 / Req 25)
    - Frontend (Members table): add a Rows_Per_Page_Selector with options `50 / 100 / 250 / 500 / Max`
      (mirror the FIN Transactions rows-per-page dropdown pattern, adapted for DynamoDB) plus
      cursor-based prev/next controls — no SQL-style offset / jump-to-page. Next enabled ONLY when the
      last query returned a `LastEvaluatedKey`; Prev enabled ONLY when a previous-page cursor exists;
      otherwise each is disabled
    - SAM Members edge/READ-query path: accept the selected limit/page-size parameter — fixed options
      (50/100/250/500) apply it as the DynamoDB Query `Limit`; `Max` OMITS `Limit` so DynamoDB returns
      one page up to its natural ~1 MB response boundary (Max = one Query page, NOT all rows) — and
      return the `LastEvaluatedKey` cursor to the frontend for every option incl. Max; prev/next walk
      that cursor
    - This is a READ/query-path change on the SAM Members plane, DISTINCT from the config WRITE path this
      spec otherwise introduces; it ships via `deploy-sam-members.yml` (SAM) + the frontend path
    - `default_page_size` is retired (no tenant default); a platform fallback supplies the initial
      pre-selected option (an optional persisted per-user default MAY seed it, but is not required)
    - Dependency: this depends on `config#fields` being SAM-owned (the Members table reads `config#fields`
      for its columns), so keep it in the Task 1 band / after the config#fields cutover; it does NOT
      depend on the scope (Task 3) or mail (Task 5) cutovers
    - WSL shell hints (per `41-shell-environment.md`):
      `cd /home/peter/projects/myAdmin && cd backend && source .venv/bin/activate && pytest sam/tests/<file> -q`
      for the SAM read-path test; `cd /home/peter/projects/myAdmin && cd frontend && npx vitest --run <path>`
      for the frontend selector/paging test
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.8, 25.9, 25.10, 7.2_

  - [~] 1.18 Property test for rows-per-page selector + cursor paging (change-with-tests)
    - **Property 11: Rows-per-page selector + DynamoDB cursor paging** — `Max` returns one page with NO
      `Limit`, bounded by the natural ~1 MB boundary; the fixed options (50/100/250/500) apply the Query
      `Limit`; prev/next is cursor-based on the `LastEvaluatedKey` for every option incl. Max; Next is
      disabled when no `LastEvaluatedKey` was returned and Prev when no previous cursor exists
    - **Validates: Requirement 25** (25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.9, 25.10)
    - `cd /home/peter/projects/myAdmin && cd backend && source .venv/bin/activate && pytest sam/tests/<file> -q`

- [~] 2. Checkpoint — config#fields cutover complete
  - Ensure all SAM + Flask + frontend tests pass; confirm `config#fields` read-back verified in PROD
    before the 1.15 builder-removal merge to `main`. Ask the user if questions arise.

- [~] 3. `config#scope` cutover (Roadmap Step 2)

  - [~] 3.1 Author `config#scope` from the single source (OQ-3 RESOLVED) + fix the dead-toggle defect
    - OQ-3 is DECIDED (ODD 3): `config#scope` is DERIVED from the per-field `scope` attribute on the
      SAM-owned `config#fields` overlay — the single authoring source. Do NOT author from a standalone
      `members.scope_dimensions` param, and do NOT reintroduce the legacy standalone-list fallback
    - Fix the dead-toggle defect: ensure toggling a field's `scope` attribute actually changes the derived
      `config#scope` (no silent fallback to the standalone param). Reference the code defect in
      `build_config_scope_row` — the `_scope_dimensions_from_overlay` fallback that silently masks overlay
      changes — and remove that fallback so the overlay toggle has real effect
    - Author `dimensions` in the `ScopeDimension` shape `get_scope_config` reads; empty `dimensions` → valid
      (tenant-wide); never author `all_wildcard` / `multi_valued`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 22.1_

  - [ ] 3.1a Implement the frontend scope-save MIRROR (SAM `config#scope` authoritative → Flask `members.scope_dimensions` derived mirror)
    - FRONTEND-MIRROR model (supersedes redirect/verify-before-retire): SAM `config#scope` (derived from
      the per-field `scope` attribute) is authoritative; Flask `members.scope_dimensions` is KEPT as a
      frontend-written DERIVED MIRROR — NOT deleted, NOT redirected
    - On each scope save the FRONTEND writes SAM `config#scope` FIRST (authoritative), then mirrors the
      dimension set into Flask `members.scope_dimensions` (best-effort, surfaced retry on failure; SAM
      stays authoritative; the mirror is eventually-consistent). New tenants auto-mirror
    - `members.scope_dimensions` is retired ONLY as an AUTHORING surface — not hand-edited, not in the
      Advanced editor, not authored by ProjectionSync; only the frontend mirror writes it
    - The Flask grant validators (`user_tenant_scope_service`, `_projection_scopegrant` / the `scopegrant#`
      projection builder, the scope picker / validation API) keep reading `members.scope_dimensions`
      UNCHANGED — do NOT redirect them to the overlay, do NOT delete `members.scope_dimensions`
      (Option D is out of scope)
    - Change-with-tests (`30`, `34`): add mirror-write + best-effort-retry tests (SAM written first, then
      the mirror; a failed mirror write surfaces a retry while SAM stays authoritative); keep a
      grant-validation test that still rejects a grant naming an undeclared dimension/value by reading the
      mirror
    - `cd backend && source .venv/bin/activate && pytest tests/unit/test_user_tenant_scope_service.py -q`
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 26.1, 26.2, 26.3_

  - [~] 3.2 SAM scope equivalence + round-trip test
    - Update/create `sam/tests/test_scope_equivalence_props.py`
    - **Property 1: Round-trip write/read equivalence (config#scope)** — after `put_config('scope', ...)`,
      `get_scope_config` returns equivalent dimensions; empty-dimensions resolves tenant-wide
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.5, 1.5**

  - [~] 3.3 Deploy scope write enablement via `deploy-sam-members.yml` (CI/CD — mandatory)
    - Ship Task 3.1 through `deploy-sam-members.yml` (OIDC, no secrets); CodeQL + GitGuardian green;
      verify live in TEST
    - _Requirements: 19.1, 19.3_

  - [~] 3.4 Migrate `config#scope` per tenant + read-back verify + seed the Flask mirror (operational, PRE builder removal)
    - Copy every live tenant's scope source into the SAM-owned `config#scope` row (min `h-dcn`); read back
      via the reader to verify `config#scope`
    - `members.scope_dimensions` is NOT deleted — it is KEPT as the frontend-written Flask mirror. Seed /
      migrate the mirror from the SAM-authoritative dimensions (or confirm the frontend mirror populates it
      on first scope save) so the grant validators keep reading a current mirror; do NOT delete it
    - No verify-before-retire-delete gate applies to this key under the mirror model — only the read-back
      verify of `config#scope` is required
    - _Requirements: 10.1, 10.2, 10.4, 10.5, 10.6, 14.2, 22.4, 26.3_

  - [~] 3.5 Repoint `config#scope` save in `membersConfigService.ts`
    - Repoint scope save to `PUT /members/config/scope`; authoritative write, no pending-projection state
    - _Requirements: 13.1, 13.2, 13.3_

  - [~] 3.6 Update frontend tests for the repointed scope save
    - **Validates: Requirements 13.1, 13.2, 13.4**

  - [~] 3.7 Remove `build_config_scope_row` from ProjectionSync (ProjectionSync stops authoring scope; param persists as the frontend mirror) (merge to main ONLY after 3.4 PROD-verified)
    - Remove the `build_config_scope_row(...)` append in `ProjectionSync.sync_administration` — ProjectionSync
      stops emitting `config#scope` AND stops being the writer of the scope dimensions; keep public surface
      unchanged
    - `members.scope_dimensions` as a PARAM is NOT retired / NOT deleted — under the frontend-mirror model
      it becomes the frontend-written mirror instead of a ProjectionSync-authored / hand-edited param. The
      frontend mirror (3.1a) is now the writer of `members.scope_dimensions`; the param row persists as the
      validator mirror the grant readers consume
    - _Requirements: 10.3, 11.1, 11.2, 11.4, 11.5, 17.3, 22.4, 26.3_

  - [~] 3.8 Update ProjectionSync tests to assert config#scope NOT emitted (change-with-tests)
    - **Property 4: ProjectionSync no longer emits config#scope** and **Property 5: Delete-sweep safety**
      for the `config#scope` prefix. The delete-sweep guardrail is VERIFIED / regression-locked by
      Requirement 12 (12.5: `config#*` rows are UPSERT-ONLY, only the `config#views`-only residue cleanup
      ever deletes a `config#` row) — it is no longer an open question
    - The existing regression test `test_sync_reconcile_never_deletes_non_scopegrant_rows` MUST stay green
      AND be EXTENDED (12.6) so a SAM-authored `config#scope` row survives a full
      `ProjectionSync.sync_administration` + `_reconcile_scopegrants` cycle under split ownership (the
      split-ownership survival case) — keep the change-with-tests framing (`30`, `34`)
    - **Validates: Requirements 11.2, 11.3, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6**
    - `cd backend && source .venv/bin/activate && pytest tests/unit/test_projection_sync.py -q`

  - [~] 3.9 Cross-plane scope-grant reconciliation (two-tier: routine auto-mirror + reminder / orphaning block + contact-SysAdmin)
    - Implement detection that compares a PROPOSED scope-dimension change (SAM/overlay — `config#scope`
      derived from the per-field `scope` attributes) against the existing Flask `user_tenant_scope` grants
      for the tenant, BEFORE applying the change. This is Flask-plane work at the
      `user_tenant_scope_service` seam, paired with the `config#scope` cutover; the detection is
      cross-plane (SAM/overlay-authored dimensions vs Flask MySQL grants)
    - TWO-TIER model (OQ-7 RESOLVED — message-based interim, not a mechanism): the frontend NEVER
      auto-rewrites grants
      - ROUTINE (new tenant / add a dimension or value) → auto-mirror the dimension set into
        `members.scope_dimensions` AND surface a REMINDER to the Tenant Admin to review/update the user
        scope grants (no auto-rewrite)
      - ORPHANING (rename/remove a dimension, drop a value — would strand an existing grant) → BLOCK (do
        not apply silently) and show a contact-SysAdmin interim message; the structural fix is Option D,
        out of scope
    - Invariant: no applied scope change leaves a `user_tenant_scope` grant referencing a dimension/value
      that no longer exists
    - Change-with-tests (`30`, `34`): add/update the reconciliation + detection tests in the same change
    - `cd backend && source .venv/bin/activate && pytest tests/unit/test_user_tenant_scope_service.py -q`
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6, 23.7, 23.8, 22.5, 26.1_

  - [~] 3.10 Property test for scope-grant reconciliation (detection + block + no-silent-stale-grant)
    - Assert the reconciliation detection + block behavior and the no-silent-stale-grant invariant: a
      proposed change that would orphan an existing grant is detected and BLOCKED (not applied); a
      new-tenant / no-grants change applies with no gate; no applied change leaves a grant referencing a
      removed/renamed dimension or value
    - **Property 10: Grant validation rejects undeclared dimensions/values under the single source** +
      the cross-plane reconciliation invariant
    - **Validates: Requirements 22, 23**
    - `cd backend && source .venv/bin/activate && pytest tests/unit/test_user_tenant_scope_service.py -q`

- [~] 4. Checkpoint — config#scope cutover complete
  - Ensure all tests pass; confirm `config#scope` read-back verified in PROD before the 3.7 merge to `main`.
    Ask the user if questions arise.

- [ ] 5. `config#mail` cutover + sender fields (Roadmap Step 3)

  - [~] 5.1 Resolve OQ-2 (now-settled three-surface model) and author `config#mail` through the write path
    - Three-surface model is settled: the `config#mail` authoring covers ONLY the SAM-owned scalars;
      `MemberSenderIdentitiesTab` co-locates in the Mail function screen but KEEPS its own Flask
      sender-identity route (`/api/members/sender-identities`) as a separate dataset (NOT folded into the
      `config#mail` put); `SenderSettingsTab` (invoice SES) stays on Flask/SES, untouched. The only open
      part is whether the sender-identity Flask route needs any change when the Mail function hosts it
    - Author `mail_enabled` gate, `mail_domain`, `mail_local_part`, `mail_certified` (required bool —
      fail-closed pre-send SES-certified gate), `mail_reply_to_default` (optional tenant-authored string),
      and `application_consent_notice` in the reader shape; author consent notice only when well-formed
      (non-blank version + ≥1 non-blank locale); preserve domain-level `consent_notice.version` separately
      from the row `version` (`_resolve_application_consent_notice` shaping)
    - From composition (`<mail_local_part|noreply>@<mail_domain>`) is already implemented. Reply-To:
      interactive send = the invoking user's verified email (runtime, already implemented, unchanged);
      scheduled / unattended send = `config#mail` `mail_reply_to_default` (NEW), falling back to the From
      address when `mail_reply_to_default` is absent
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14, 15.1, 15.2, 15.3, 15.4, 15.5, 20.1_

  - [~] 5.2 SAM config#mail round-trip + reader test
    - Update `sam/tests/test_members_projection_reader.py` (`_config_mail_item` / `is_mail_enabled` /
      consent-notice reads)
    - **Property 1: Round-trip write/read equivalence (config#mail)** — after `put_config('mail', ...)`,
      `is_mail_enabled` / `get_mail_domain` / `get_mail_local_part` return equivalent values; fail-closed
      gate and no-safe-default domain hold
    - Assert `mail_certified` is written as a bool on the row and is **fail-closed**: absent / not
      explicitly `True` blocks the pre-send certification gate (even though the reader exposes no
      `mail_certified` accessor, the written row carries it so the projected shape stays valid)
    - Assert `mail_reply_to_default` round-trips on the `config#mail` row; add a test that a
      scheduled / unattended send Reply-To uses `mail_reply_to_default` (and falls back to the From address
      when it is absent) while an interactive send uses the invoking user's verified email
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14, 1.5**

  - [~] 5.3 Invoice-SES-untouched confirmation test
    - **Property 6: Invoice-SES-untouched invariant** — the Flask/SES invoice path (`SenderSettingsTab`)
      is observably unchanged; no invoice SES read/write path altered
    - **Validates: Requirements 15.4, 15.5**

  - [~] 5.4 Deploy mail write enablement via `deploy-sam-members.yml` (CI/CD — mandatory)
    - Ship Task 5.1 through `deploy-sam-members.yml` (OIDC, no secrets); CodeQL + GitGuardian green;
      verify live in TEST
    - _Requirements: 19.1, 19.3_

  - [~] 5.5 Migrate `config#mail` per tenant + read-back verify + delete migrated MySQL rows (operational, PRE builder removal)
    - Copy every live tenant's `members.mail_enabled` + `members.mail_domain` + `members.mail_local_part`
      + `members.mail_certified` + `members.application_consent_notice` into the SAM-owned `config#mail`
      row (min `h-dcn`); read back; keep MySQL params until PROD-verified
    - `mail_reply_to_default`: if a corresponding `members.mail_reply_to_default` MySQL param exists,
      include it in the migrate + delete list alongside the others. If there is NO existing MySQL param
      (it is a brand-new field authored only via SAM through the typed Mail function), it is net-new on
      `config#mail` — nothing to migrate / nothing to delete for this key
    - After PROD read-back verify, DELETE the migrated `members.mail_enabled` / `members.mail_domain` /
      `members.mail_local_part` / `members.mail_certified` / `members.application_consent_notice` MySQL
      rows (plus `members.mail_reply_to_default` only if it pre-existed) so no raw/MySQL authoring door
      remains for those keys (deletion happens only after the PROD read-back verify — reversible until then)
    - _Requirements: 10.1, 10.2, 10.4, 10.5, 10.6, 14.2_

  - [~] 5.6 Repoint `config#mail` / sender save in `membersConfigService.ts`
    - Repoint mail + sender save to `PUT /members/config/mail`; authoritative write, no pending-projection
    - _Requirements: 13.1, 13.2, 13.3, 14.3_

  - [~] 5.7 Update frontend tests for the repointed mail save
    - **Validates: Requirements 13.1, 13.2, 13.4**

  - [~] 5.8 Remove `build_config_mail_row` + retire `members.*` mail params (merge to main ONLY after 5.5 PROD-verified)
    - Remove the `build_config_mail_row(...)` append in `ProjectionSync.sync_administration`; retire the
      `members.mail_enabled` / `members.mail_domain` / `members.mail_local_part` / `members.mail_certified`
      / `members.application_consent_notice` params in the same change; keep public surface unchanged
    - `mail_reply_to_default`: if a `members.mail_reply_to_default` MySQL param exists, include it in the
      retired set; otherwise it is net-new (authored only via SAM) and there is no param to retire
    - _Requirements: 10.3, 11.1, 11.2, 11.4, 11.5, 17.3_

  - [~] 5.9 Update ProjectionSync tests to assert config#mail NOT emitted (change-with-tests)
    - **Property 4: ProjectionSync no longer emits config#mail** and **Property 5: Delete-sweep safety**
      for the `config#mail` prefix. The delete-sweep guardrail is VERIFIED / regression-locked by
      Requirement 12 (12.5: `config#*` rows are UPSERT-ONLY, only the `config#views`-only residue cleanup
      ever deletes a `config#` row) — it is no longer an open question
    - The existing regression test `test_sync_reconcile_never_deletes_non_scopegrant_rows` MUST stay green
      AND be EXTENDED (12.6) so a SAM-authored `config#mail` row survives a full
      `ProjectionSync.sync_administration` + `_reconcile_scopegrants` cycle under split ownership (the
      split-ownership survival case) — keep the change-with-tests framing (`30`, `34`)
    - **Validates: Requirements 11.2, 11.3, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6**
    - `cd backend && source .venv/bin/activate && pytest tests/unit/test_projection_sync.py -q`

- [~] 6. Checkpoint — config#mail cutover complete
  - Ensure all tests pass; confirm `config#mail` read-back verified in PROD before the 5.8 merge to `main`;
    confirm invoice SES untouched. Ask the user if questions arise.

- [~] 7. Typed authoring UI + single-authoring-door enforcement (Roadmap Step 4)

  - [~] 7.1 Build the NEW dedicated typed Mail function (single door for Members `config#mail` scalars)
    - New single screen under Members Tenant Admin: typed Chakra form fields with Formik/Yup validation
      and bilingual (nl/en) labels per `32-frontend-ui.md` (NOT a raw JSON grid) for `mail_enabled`,
      `mail_domain`, `mail_local_part`, `mail_certified`, `mail_reply_to_default`,
      `application_consent_notice`
    - Saves via `membersConfigService.ts` → `PUT /members/config/mail` (SAM write path, authoritative — no
      pending-projection UX)
    - Co-locate `MemberSenderIdentitiesTab` in the same screen WITHOUT folding it into the `config#mail`
      put — it keeps its own Flask `/api/members/sender-identities` route (a separate dataset / write
      mechanism)
    - _Requirements: 20.1, 20.2, 9.1, 14.4, 15.2_

  - [~] 7.2 Re-instate the blanket `members`-namespace exclusion in `ParameterManagement.tsx`
    - In `frontend/src/components/TenantAdmin/ParameterManagement.tsx`, restore the full `members`-namespace
      exclusion so the Advanced raw editor serves NO `members.*` rows at all (today it hides only
      `field_overlay` / `scope_dimensions` via `TYPED_EDITOR_KEYS` and deliberately SHOWS the mail params —
      reverse that so every `members.*` key is excluded)
    - Update the in-code comment: the mail params now have the dedicated typed Mail function (7.1) as their
      door and their MySQL rows are deleted, so the raw editor must not serve them
    - _Requirements: 14.1, 14.3, 20.4_

  - [~] 7.2* Test: Advanced raw editor shows zero `members.*` rows (change-with-tests)
    - Update the existing allocated frontend test (`ParameterManagement.test.tsx`) per the change-with-tests
      contract — today it asserts the mail params SHOW; flip it to assert all `members.*` rows are hidden
    - **Validates: Requirements 14.1, 14.3**

  - [~] 7.3* Test: single-authoring-door / no-second-writer — Property 8
    - **Property 8: Single authoring door / no second writer** — assert the typed Mail function (and any
      other view that touches `config#mail`) both PUT to the single SAM `PUT /members/config/mail` route,
      and that no `members.*` MySQL write path remains for any migrated key
    - **Validates: Requirements 14.1, 14.3, 14.4**

  - [~] 7.4 Retire the `view_contexts` residue (physical cleanup, delete-only)
    - Apply `backend/src/migrations/retire_members_view_contexts.py` to DELETE every tenant
      `members.view_contexts` MySQL row — run dry-run first (default), then `--apply` in TEST, then in PROD
    - Confirm `ProjectionSync.delete_config_views_residue` has removed any stale `config#views` DynamoDB
      residue (delete-only; it authors no row)
    - This upholds the zero-`members.*`-rows single-authoring-door guarantee for the retired key
      (Requirement 14) — `view_contexts` is RETIRED with no editor and is not among the migrated keys
    - Leave the per-user Session Columns chooser (`ColumnChooser.tsx`,
      `getColumnPreferences`/`saveColumnPreferences`) UNCHANGED
    - WSL shell hints:
      `cd /home/peter/projects/myAdmin && cd backend && source .venv/bin/activate && python -m src.migrations.retire_members_view_contexts` (dry-run)
      then `... python -m src.migrations.retire_members_view_contexts --apply` (after dry-run review, TEST then PROD)
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 14.1_

  - [ ] 7.5* Test/verify `view_contexts` cleanup
    - Assert the migration deletes only `members.view_contexts` rows and is idempotent (re-run is a no-op);
      after apply a scan finds zero `members.view_contexts` MySQL rows and zero `config#views` projection
      rows; rows-per-page is now the per-user runtime Rows_Per_Page_Selector (Requirement 25, Task 1.17),
      so the old `default_page_size` pagination precedence (`membersPagination.ts`,
      `userPreference → default_page_size → platformDefault`) is RETIRED, not carried forward — do not
      assert it; Session Columns untouched
    - Reference the existing migration's own test pattern if present
    - Shell hint: `cd backend && source .venv/bin/activate && pytest <the migration's allocated test path> -q`
    - **Validates: Requirements 21.2, 21.5, 21.6, 21.7**

- [ ] 8. TEST → PROD promotion + CI/CD cutover ordering (Roadmap Step 5)

  - [~] 8.1 Implement the TEST→PROD promotion: structural-change tenant-wide migration + read-back parity
    - Promotion of a STRUCTURAL config change (new/retired row type, added/removed/repurposed attribute)
      is a tenant-wide config migration that updates ALL tenants to the new shape on the deploy that
      introduces it, run test→prod like `backend/src/migrations`, ordered relative to merge-to-main
      (OQ-4 resolved, Req 24). ADDITIVE data changes (new field, enum value, scope toggle, scalar edit)
      are transparent and need NO promotion step
    - The write path already works against both `test_governance_projection` and `governance_projection`
      via `GOVERNANCE_PROJECTION_TABLE`, so no per-env credential/table rewiring is required
    - Keep the read-back parity check comparing TEST and PROD `config#*` rows before the cutover merge
    - Note: 24.1 / 24.2 / 24.6 are reader-behavior guarantees covered at the design level (single-codebase
      reader, additive data consumed with no migration, graceful defaulting), not obligations on this task
    - _Requirements: 18.1, 18.2, 18.4, 18.5, 24.3, 24.4, 24.5, 24.7, 5.3, 5.4_

  - [~] 8.2 Rollback rehearsal test/script
    - Automated rehearsal that restores from the retained MySQL params / prior row and verifies read-back
    - **Validates: Requirements 18.3, 10.5**

  - [~] 8.3 Promote `test → main` production-release gate (CI/CD — mandatory)
    - One reviewed PR `test → main`; CodeQL + GitGuardian green; preview SAM prod changeset (no unexpected
      `Replacement: True`); merge with a merge commit; never push straight to `main`; `workflow_dispatch`
      defaults to TEST. Each builder-removal merge happens only after its record is PROD-verified (safety gate)
    - _Requirements: 19.1, 19.3, 19.4, 19.5, 18.4_

- [~] 9. Final checkpoint — split-ownership verified
  - Ensure all SAM + Flask + frontend tests pass; confirm SAM writes only `config#fields/scope/mail`,
    ProjectionSync writes only `tenant`/`module#`/`role#`/`scopegrant#`, no row ever had zero writers,
    and Cognito + invoice SES are unchanged. Explicitly confirm the Requirement 16 guarantees:
    Cognito writes are unchanged (16.1); ProjectionSync still writes `tenant`/`module#`/`role#`/`scopegrant#`
    (16.2); the SAM plane performs no identity-plane writes (16.3); and the Flask and SAM planes never call
    each other at runtime (16.4). Ask the user if questions arise.
  - _Requirements: 16.1, 16.2, 16.3, 16.4_

## Notes

- Tasks marked with `*` are optional (tests) and can be skipped for a faster MVP, but the change-with-tests
  contract (`30`, `34`) expects paired tests to be updated in the same change as any behavioral edit.
- Each task references specific requirement sub-clauses for traceability.
- Checkpoints enforce the per-record safety gate: a builder-removal merge to `main` (1.15, 3.7, 5.8) only
  after that record's SAM write path is live and read-back verified in PROD (1.12, 3.4, 5.5).
- Each per-record migration (1.12, 3.4, 5.5) DELETES the migrated `members.*` MySQL rows only after the
  PROD read-back verify (reversible until then, Requirement 14.2), so no raw/MySQL authoring door remains.
- `config#mail` carries `mail_certified` as a required fail-closed bool on the written row (authored in
  5.1, migrated in 5.5, tested in 5.2) — the pre-send certification gate refuses sending when it is absent
  or not explicitly `True`.
- `config#mail` also carries `mail_reply_to_default` (optional tenant-authored string; authored in 5.1 via
  the typed Mail function 7.1, round-tripped in 5.2). The From address (`<mail_local_part|noreply>@<mail_domain>`)
  is already implemented. Reply-To: an interactive send uses the invoking user's verified email (runtime,
  already implemented); a scheduled / unattended send uses `mail_reply_to_default`, falling back to the From
  address when it is absent (Req 9.9–9.14, 20.1). If no `members.mail_reply_to_default` MySQL param exists
  it is net-new on `config#mail` (nothing to migrate/retire in 5.5/5.8).
- Task 7 is the typed-UI + single-authoring-door work (no raw JSON grid): the net-new typed Mail function
  (7.1) plus re-instating the blanket `members`-namespace exclusion in the Advanced raw editor (7.2). It
  depends on the `config#mail` cutover (Task 5) being complete because the Mail function authors
  `config#mail`.
- Task 7.4/7.5 retire the `view_contexts` residue (delete-only MySQL migration + `config#views` sweep) to
  uphold the zero-`members.*`-rows guarantee for the retired key; `view_contexts` has no editor; Session
  Columns is a separate per-user feature left untouched.
- Resolved config model (OQ-4 + OQ-5): single codebase / one latest reader → there is NO config
  schema-version system; the write-stamp is ordering / when-written only (does not gate reads or encode
  shape) and Phase 1 is last-writer-wins, no conditional stale-write 409 guard (OQ-5 resolved, Req 6
  incl. 6.6/6.7/6.8). A STRUCTURAL config change (new/retired row type, added/removed/repurposed
  attribute) ships a tenant-wide config migration on deploy run test→prod to update ALL tenants to the new
  shape (OQ-4 resolved, Req 24); ADDITIVE data changes (new field, enum value, scope toggle, scalar edit)
  are transparent and need no promotion (Req 18/24).
- OQ-6 is RESOLVED (no longer an open decision): rows-per-page is a per-user runtime selector
  (50/100/250/500/Max; Max = one DynamoDB Query page at the natural ~1 MB boundary, not all rows) with
  cursor-based prev/next on the `LastEvaluatedKey` (Requirement 25, design Component 10 / Property 11),
  built in Task 1.17/1.18 across the SAM Members READ/query path + the Members table frontend. The
  tenant-level `default_page_size` is RETIRED — not authored on `config#fields`, not migrated to SAM.
- The `config#scope` cutover (Task 3) uses the FRONTEND-MIRROR model and now carries three coupled pieces
  beyond the plain row cutover: (a) single-source derivation — `config#scope` is DERIVED from the per-field
  overlay `scope` attribute (OQ-3 resolved, ODD 3) with the dead-toggle defect fixed (the
  `_scope_dimensions_from_overlay` fallback in `build_config_scope_row` removed, 3.1); (b) the frontend
  scope-save mirror (3.1a) — SAM `config#scope` is authoritative and written FIRST, then the dimension set
  is mirrored into Flask `members.scope_dimensions` (best-effort, surfaced retry). `members.scope_dimensions`
  is KEPT as the frontend-written validator mirror — NOT deleted, NOT redirected (3.4 seeds it, 3.7 leaves
  ProjectionSync as a non-writer); the grant validators (`user_tenant_scope_service`, `_projection_scopegrant`,
  scope picker/validation API) keep reading the mirror UNCHANGED (Option D out of scope); it is retired only
  as an authoring surface. (c) the cross-plane scope-grant reconciliation is TWO-TIER (3.9/3.10): ROUTINE
  (new tenant / add dimension or value) → auto-mirror + a REMINDER to the Tenant Admin to review/update user
  scope grants (no auto-rewrite); ORPHANING (rename/remove dimension, drop value) → block + a
  contact-SysAdmin interim message. The frontend never auto-rewrites grants.
- OQ-7 is RESOLVED: the reconciliation escalation is message-based (routine reminder / orphaning
  contact-SysAdmin interim message), not a mechanism — the structural fix is Option D, out of scope. ALL
  open questions for this spec are now resolved.
- Property tests validate the universal correctness properties in the design; unit tests cover edge cases.
- CI/CD tasks (1.11, 3.3, 5.4, 8.3) are explicit, not afterthoughts: SAM infra + IAM via
  `deploy-sam-members.yml` (OIDC `NonprofitDeployRole`, acct `506221081911`, `eu-west-1`, no AWS secrets);
  frontend repoint + ProjectionSync builder removal ride the full-test-suite / Flask path.

## Task Dependency Graph

> Note: the checkpoint tasks (2, 4, 6, 9) are human verification gates, not units of work, and are intentionally excluded from the dependency graph below.

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "1.4", "1.5", "1.8"] },
    { "id": 2, "tasks": ["1.6"] },
    { "id": 3, "tasks": ["1.7", "1.9"] },
    { "id": 4, "tasks": ["1.10", "1.11"] },
    { "id": 5, "tasks": ["1.12"] },
    { "id": 6, "tasks": ["1.13"] },
    { "id": 7, "tasks": ["1.14", "1.15"] },
    { "id": 8, "tasks": ["1.16", "3.1"] },
    { "id": 9, "tasks": ["3.1a", "3.2", "3.3"] },
    { "id": 10, "tasks": ["3.9"] },
    { "id": 11, "tasks": ["3.10", "3.4"] },
    { "id": 12, "tasks": ["3.5"] },
    { "id": 13, "tasks": ["3.6", "3.7"] },
    { "id": 14, "tasks": ["3.8", "5.1"] },
    { "id": 15, "tasks": ["5.2", "5.3", "5.4"] },
    { "id": 16, "tasks": ["5.5"] },
    { "id": 17, "tasks": ["5.6"] },
    { "id": 18, "tasks": ["5.7", "5.8"] },
    { "id": 19, "tasks": ["5.9", "7.1"] },
    { "id": 20, "tasks": ["7.2", "7.4"] },
    { "id": 21, "tasks": ["7.2*", "7.3*", "7.5*", "1.17"] },
    { "id": 22, "tasks": ["8.1", "1.18"] },
    { "id": 23, "tasks": ["8.2", "8.3"] }
  ]
}
```
