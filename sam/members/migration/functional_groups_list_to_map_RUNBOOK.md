# RUNBOOK — `config#fields` `functional_groups` LIST → MAP migration

> spec 03 (`.kiro/specs/Members/03 - config-fields-foolproof-crud`) Task 2.0 · design **C6 / D2a** ·
> design-review **Q3a / Q11** · external-review **Must-fix #4**.
>
> **OWNER-RUN. The agent that authored this migration did NOT run it against PROD, a PROD copy, or
> any real AWS data, and did NOT take a backup/PITR restore point.** Every step below that touches
> real data is performed by the owner. The script
> (`sam/members/migration/functional_groups_list_to_map.py`) is DRY-RUN by default and refuses to
> write without BOTH `--apply` and `--i-have-a-restore-point`.

## What changes

Each tenant's `config#fields` row has its `functional_groups` attribute converted from the legacy
ordered **LIST** `[{key,label,order}, …]` to a **MAP keyed by group key**
`{key:{key,label,order}, …}`, and the row skeleton (`fields` / `overrides` / `functional_groups`
parent maps) + a `version` stamp are backfilled where absent. Nothing else on the row is touched
(`order` is already inside each entry — Q3a; slug / publish-state / every other attribute ride
through verbatim).

**Why:** a MAP lets group writes be a per-path `update_item` on `functional_groups.<gkey>` (Phase
2), which DynamoDB applies without addressing the parts it doesn't name — so a partial groups
payload can no longer truncate the catalog (the proven occurrence-3 bug, 6→1). This is the
STRUCTURAL fix, not a better in-memory merge.

**Dual-read is already deployed** (this task's CODE half): the reader and write service accept BOTH
shapes, so the code runs correctly against legacy LIST rows AND migrated MAP rows. That is what lets
this migration roll out WITHOUT a flag day — the migration is a data cleanup that removes the legacy
shape, not a cutover the code depends on.

## Pre-conditions (do these FIRST — in order)

1. **Confirm the dual-read code is deployed** to the target stage (TEST, then PROD) BEFORE migrating
   that stage. The code reads both shapes, but the migration should follow the code so a rollback of
   the code never strands MAP-only rows. Verify the deployed `MembersProjectionReader` is the
   dual-read version (spec 03 Task 2.0 commit).
2. **Identify the target table + account.** DynamoDB `governance_projection` lives in the DATA
   account `506221081911` (`23-aws-accounts.md`). Sanity-check identity — this MUST print
   `506221081911` (NonprofitDeployRole), not `344561557829` (the override-ranking trap,
   `41-shell-environment.md`):
   ```bash
   env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
     aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json
   ```
3. **Take a restore point — NON-NEGOTIABLE.** Either enable/confirm **PITR** on the table OR take an
   **on-demand backup**, and record the backup ARN / restore timestamp. The catalog is tiny, but the
   migration is a whole-row `put_item`; rollback = restore from this point.
   ```bash
   # on-demand backup (record the returned BackupArn):
   aws dynamodb create-backup --table-name <governance_projection_table> \
     --backup-name fg-list-to-map-pre-migration-$(date +%Y%m%d%H%M) \
     --profile nonprofit-deploy --region eu-west-1 --output json
   ```

## Procedure

### Step A — DRY-RUN preview (safe; reads only)

Run with NO write flags. It Queries/scans the `config#fields` rows and prints the planned
conversion per tenant (`PLAN` = will convert, `SKIP` = already MAP + skeleton + version, idempotent).
No data is modified.

```bash
cd /home/peter/projects/myAdmin && source backend/.venv/bin/activate && \
  env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
  GOVERNANCE_PROJECTION_TABLE=<governance_projection_table> \
  PYTHONPATH=sam:backend/src \
  python -m sam.members.migration.functional_groups_list_to_map
# judge success by stdout + the in-band marker; ignore the tool's Exit Code -1 (steering 41):
printf '\n<<<DONE marker=%s>>>\n' "$?"
```

Review the `PLAN` lines. Every tenant with a legacy LIST should show `groups list -> map (N groups)`
with `N` matching the known catalog size (e.g. h-dcn = 6). An unexpected count is a STOP — investigate
before applying.

### Step B — Apply against a COPY of PROD, then verify with the invariant harness

1. Restore the backup from pre-condition 3 into a **separate table** (a PROD copy), or run against
   the TEST stack seeded from PROD. Do NOT apply to PROD yet.
2. Apply to the copy (both flags required; the second is your affirmation a restore point exists):
   ```bash
   … python -m sam.members.migration.functional_groups_list_to_map \
       --apply --i-have-a-restore-point
   ```
3. **Verify via the invariant harness** (the acceptance gate — design C5 / R9). With the migrated
   copy reachable as the local/endpoint table, the read → Change-Op → read invariant suite must be
   GREEN for the group ops (no truncation), and the migration-shape invariant
   (`test_functional_groups_list_to_map_migration.py`) must pass:
   ```bash
   cd /home/peter/projects/myAdmin && source backend/.venv/bin/activate && \
     python -m pytest sam/tests/test_functional_groups_list_to_map_migration.py \
       sam/tests/test_members_projection_reader.py sam/tests/test_config_write_service.py -q
   printf '\n<<<DONE marker=%s>>>\n' "$?"
   ```
   Confirm the resolved field config (groups, fields, attrs) on the migrated copy is byte-identical
   to the pre-migration resolved view — the migration changes the STORAGE shape, never the RESOLVED
   view a consumer sees.

### Step C — Apply to PROD

Only after Step B is clean on the PROD copy:

1. Re-confirm the PITR/backup restore point covers the CURRENT PROD state (pre-condition 3, re-taken
   if time has passed).
2. Apply to PROD:
   ```bash
   … GOVERNANCE_PROJECTION_TABLE=<PROD_governance_projection_table> \
     python -m sam.members.migration.functional_groups_list_to_map \
       --apply --i-have-a-restore-point
   ```
3. Re-run Step A (DRY-RUN) against PROD — every row should now report `SKIP … already MAP`
   (idempotent). Exercise the live configurator (edit a group order/label, confirm NO truncation,
   confirm reload survives) per the spec's Phase-9 live check.

## New-tenant row skeleton (the create-time half of C6 — task 2.0a)

This migration backfills the `{fields, overrides, functional_groups}` skeleton + `version` onto
**EXISTING / legacy** rows. The **NEW-TENANT** half is
`MembersConfigWriteRepository.ensure_skeleton(tenant_id)` — an idempotent, IF-ABSENT
(`attribute_not_exists(sk)`) create of the same skeleton that NEVER overwrites a populated row. It
reuses the sanctioned C6 whole-row `put_config` primitive (R1.5) — it is NOT a second whole-row
writer, and it is NOT on the runtime Change-Op path.

**Why it is needed:** the Phase-2 path `update_item` requires the three parent maps to already
exist (an `if_not_exists`-in-the-same-op seed is rejected by DynamoDB as "document paths overlap",
Must-fix #1). So a freshly created tenant must have its skeleton seeded BEFORE its first Change-Op.

**Where the onboarding path MUST call it (today this is MANUAL — there is no SAM runtime
tenant-create path in this repo):** tenant onboarding happens on the Flask plane / via the
onboarding scripts, then ProjectionSync (or the seed path) projects `config#fields`. Any path that
provisions a brand-new tenant's config MUST call `ensure_skeleton(tenant_id)` so the skeleton exists
before the configurator issues its first Change-Op. Concretely:

- The config-provisioning / onboarding runner
  (`scripts/onboarding/members/_generic/project-config-to-prod.py` and the per-tenant seed path)
  should call `ensure_skeleton(tenant_id)` once, right after the tenant's `config#fields` row is
  first provisioned (it is a safe no-op if the row already exists).
- When a SAM-plane tenant-create/provision handler is eventually added, wire `ensure_skeleton` into
  it as the first config write (the composition root injects the real
  `MembersConfigWriteRepository`).

Until that call is wired, the Phase-2 Change-Op path still handles a never-authored tenant via the
`base_version=None → attribute_not_exists(sk)` first-write branch — `ensure_skeleton` makes the
skeleton explicit and removes the create-vs-update ambiguity, but a first field write does not hard
depend on it.

## Rollback

- The script is **idempotent**: a re-run converges; it never double-writes a migrated row.
- If a migrated row is wrong, **restore from the PITR restore point / on-demand backup** taken in
  pre-condition 3 (the catalog is tiny, so restore is fast). Because the deployed code dual-reads,
  a restored LEGACY LIST row is served correctly by the current code — no code rollback is needed to
  recover data.

## Non-negotiables

- **Never run `--apply` without a restore point.** The script enforces this (`--i-have-a-restore-point`
  is mandatory with `--apply`), but the affirmation is only as true as you make it.
- **Never apply to PROD before verifying on a PROD copy** via the invariant harness (Step B).
- **Dual-read code before data.** Deploy the Task-2.0 code to a stage before migrating that stage.
- This is the ONE sanctioned whole-row `put_item` on `config#fields` (C6) — do not generalize it into
  a runtime write path. The runtime path is per-path `update_item` (Phase 2).
