# RUNBOOK — membership_type catalog → field options EXPAND migration

> spec 03b (`.kiro/specs/Members/03b - admin-driven-field-form-model`) Task 7.2 · design
> **"Migration" § EXPAND→DEPLOY→VERIFY→CONTRACT** · Req **6.1a / 6.2 / 6.3 / 6.5**.
>
> **OWNER-RUN. The agent that authored this migration did NOT run it against TEST, PROD, a copy, or
> any real AWS data, and did NOT take a backup/PITR restore point.** Every step below that touches
> real data is performed by the owner. The script
> (`sam/members/migration/membership_type_catalog_to_field_options.py`) is DRY-RUN by default and
> refuses to write without BOTH `--apply` and `--i-have-a-restore-point`. Task 7.3 runs it on TEST;
> Task 12 on PROD.

## What changes

> **TWO tables are involved.** The `config#fields` rows folded/written live in the **projection**
> table (`GOVERNANCE_PROJECTION_TABLE` = `governance_projection` / `test_governance_projection`).
> The `membershiptype#<code>` **catalog** that is folded IN lives in the **members** table
> (`MEMBERS_TABLE` = `sam-members` / `test_sam-members`). Every command below MUST set BOTH env
> vars — with only `GOVERNANCE_PROJECTION_TABLE` set, the catalog read hits the wrong table, finds
> zero rows, and silently SKIPs every fold (the bug the Task 7.3 dry-run surfaced).

For each tenant's `config#fields` row (in `governance_projection` / `test_governance_projection`):

1. **Fold the catalog into the field's options.** Each `membershiptype#<code>` catalog entry
   `{type_code, label{nl,en}, active, order}` becomes ONE option on the `membership_type` field
   (stored at the dotted override key `membership.membership_type`):

   ```
   { value: <type_code>, label: {nl,en}, order: <order>, allowed: <active> }
   ```

   An ACTIVE entry folds to `allowed:true` (offered in the picker); a RETIRED entry
   (`active:false`, e.g. h-dcn's `erelid`) folds to **`allowed:false`** — the grandfather case
   (hidden from the picker, but still resolving the reference of the 4 members who hold it, so NOT
   an orphan). `value` = the immutable former `type_code` member records point at.

2. **Drop the forbidden `choices` key wherever it co-exists with `options`** — across EVERY override
   entry, INCLUDING `region` (live h-dcn carries inline `choices`+`options`). `options` is the only
   canonical representation on a config field (03a); `choices` is forbidden residue. A `choices`
   entry with NO `options` alongside it is left untouched (the migration never drops a sole
   vocabulary source).

Nothing else on the row is touched — `application_*` flags, `scope` binding, `type`, slug,
`functional_groups`, every other field's override ride through verbatim. **region's VALUES are not
re-folded** (already inline + synced per live data; Req 4's derive-on-save keeps them consistent) —
only its forbidden `choices` residue is stripped.

**Why:** after the fold, the `membership_type` field's own `options` are the single vocabulary; the
member-reference check and the option-assembly seam read the field, not the catalog (design
BU-1/BU-2/BU-3). The catalog rows are then retired in CONTRACT (Task 10.1), once the integrity scan
is green.

## Rollout order (EXPAND → DEPLOY → VERIFY → CONTRACT)

This migration is the **EXPAND** step. It is ADDITIVE and harmless to the old code (which still
reads the catalog): it only ADDS options onto the field and removes redundant `choices`. The
re-pointed reader (DEPLOY) runs AFTER the fold; the catalog rows are retired (CONTRACT) only AFTER
the post-fold integrity scan passes. Run order per environment: EXPAND (this) → confirm scan →
DEPLOY re-pointed code → VERIFY scan → CONTRACT (retire catalog rows).

## Pre-conditions (do these FIRST — in order)

1. **Identify the target table + account.** DynamoDB `governance_projection` (and the `sam-members`
   catalog) live in the DATA account `506221081911` (`23-aws-accounts.md`). Sanity-check identity —
   this MUST print `506221081911` (NonprofitDeployRole), not `344561557829` (the override-ranking
   trap, `41-shell-environment.md`):
   ```bash
   env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
     aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json
   ```
2. **Take a restore point — NON-NEGOTIABLE.** Enable/confirm **PITR** on `governance_projection` OR
   take an **on-demand backup**, and record the backup ARN / restore timestamp. The script ALSO
   prints a full-row `BACKUP …` line per affected row to stdout (capture it), but that complements —
   does NOT replace — the PITR/on-demand backup.
   ```bash
   aws dynamodb create-backup --table-name <governance_projection_table> \
     --backup-name mt-fold-pre-migration-$(date +%Y%m%d%H%M) \
     --profile nonprofit-deploy --region eu-west-1 --output json
   ```

## Procedure

### Step A — DRY-RUN preview (safe; reads only) — LIST the resulting values (Req 6.2)

Run with NO write flags. It scans the `config#fields` rows, reads each tenant's catalog, and prints
the planned fold per tenant (`PLAN` = will fold / strip, `SKIP` = already folded + choices-clean,
idempotent) AND the resulting `membership_type` option values (retired ones flagged) so the owner
can verify exactly what will be loaded.

```bash
cd /home/peter/projects/myAdmin && source backend/.venv/bin/activate && \
  env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
  GOVERNANCE_PROJECTION_TABLE=<governance_projection_table> \
  MEMBERS_TABLE=<members_table> \
  PYTHONPATH=sam:backend/src \
  python -m sam.members.migration.membership_type_catalog_to_field_options
printf '\n<<<DONE marker=%s>>>\n' "$?"
```

Review the `PLAN` lines. For h-dcn the listing must show the 7 values with `erelid` flagged
`(retired)` — matching `backend/tests/fixtures/hdcn_membership_type_options.json`. Verify EVERY
tenant (Req 6.5), not only h-dcn — any tenant with un-folded catalog rows must appear as a `PLAN`.

### Step B — Apply (both flags required)

```bash
cd /home/peter/projects/myAdmin && source backend/.venv/bin/activate && \
  env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
  GOVERNANCE_PROJECTION_TABLE=<governance_projection_table> \
  MEMBERS_TABLE=<members_table> \
  PYTHONPATH=sam:backend/src \
  python -m sam.members.migration.membership_type_catalog_to_field_options \
    --apply --i-have-a-restore-point | tee .agent-output/mt-fold-apply-$(date +%Y%m%d%H%M).log
printf '\n<<<DONE marker=%s>>>\n' "$?"
```

Each affected row emits a `BACKUP <stamp> {full row json}` line BEFORE it is written — the `tee`
keeps those backup lines. Without `--i-have-a-restore-point` the script REFUSES to write.

### Step C — VERIFY with the integrity scan (the gate — Req 6.3)

Re-run the Task-7.1 integrity scan; it must report PASS (exit 0): zero un-folded active catalog
rows, zero orphaned member references across ALL tenants.

```bash
cd /home/peter/projects/myAdmin && source backend/.venv/bin/activate && \
  env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
  GOVERNANCE_PROJECTION_TABLE=<governance_projection_table> \
  MEMBERS_TABLE=<members_table> \
  PYTHONPATH=sam:backend/src \
  python scripts/scan_membership_type_integrity.py
printf '\n<<<DONE marker=%s>>>\n' "$?"
```

Re-run Step A (DRY-RUN) — every row should now report `SKIP … already folded` (idempotent).

### Step D — TEST then PROD parity (Req 6.5)

Run A→B→C against TEST (`test_*` tables) first (Task 7.3), then against PROD (unprefixed, Task 12),
IDENTICALLY, each integrity-scan-gated. `test → main` is BLOCKED until PROD is folded + scan-green.

## Idempotency & rollback

- **Idempotent + re-runnable:** a row whose options already cover every active catalog code, whose
  retired codes are `allowed:false`, and which carries no forbidden `choices` beside `options` is
  detected (`row_needs_fold → False`) and SKIPPED. A re-run after a partial/interrupted apply
  converges without double-writing.
- **Rollback:** restore from the PITR restore point / on-demand backup (pre-condition 2), or
  `put_item` the per-row `BACKUP` lines the apply log captured. The catalog rows are NOT touched by
  this migration (they are retired separately in CONTRACT), so the old code path still works on a
  rolled-back row.

## Non-negotiables

- **Never run `--apply` without a restore point.** The script enforces `--i-have-a-restore-point`
  with `--apply`, but the affirmation is only as true as you make it.
- **Never retire the catalog rows (CONTRACT) before the post-fold integrity scan is green.**
- **Run TEST and PROD identically, each scan-gated** (Req 6.5 / analysis D5 parity gate).
- The fold writes the single `overrides` attribute via the sanctioned C6 whole-item put; it is a
  one-time migration primitive, NOT a runtime write path.
