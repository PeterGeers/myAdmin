# SPEC CANDIDATE: Media-asset "merge duplicates" breaks direct S3-key references (NoSuchKey)

**Bug (observed 2026-10-31 after merging two Media-Assets flagged as duplicates):** merging two
duplicate assets deleted the duplicate's S3 object, but a transaction that linked the invoice by a
RAW S3 key (not a tracked reference) was left pointing at the now-deleted key. Clicking the file on
that transaction returns `NoSuchKey`.

## Root cause (confirmed in code + data)

`MediaAssetService.merge_duplicates` (`backend/src/services/media_asset/lifecycle.py`) only
re-homes references that live in the `s3_asset_references` table:

1. move `s3_asset_references` rows from the duplicate asset to the kept asset,
2. `delete_object` the duplicate's S3 object,
3. delete the duplicate's `s3_assets` row.

But invoice links on transactions are stored as a **plain S3 key string in `mutaties.Ref3`**
(filename in `Ref4`) — they are NOT rows in `s3_asset_references`. So the merge never learns about
them, deletes the file they point at, and leaves a dangling key → `NoSuchKey`.

## Evidence (this incident)

- Tenant `kimgeers`, Roborock invoice (one PDF, uploaded twice → content-hash duplicates).
- Merge KEPT `ast_01M3XP2Y9G61SWD3B19KSGC735` (S3 `kimgeers/invoices/ast_01M3XP2Y9G61SWD3B19KSGC735_Roborock.pdf`,
  still present, 54,974 bytes) and DELETED `ast_01M46BGQHVPNVAK1D3YT1X4KXT`.
- Two `mutaties` rows pointed at the DELETED key (the gross + VAT split of one invoice):
  `ID 65087` (`NL260823E5FVSS8Z`) and `ID 65088` (`NL260823E5FVSS8Z BTW`), 2026-08-23.
- Zero rows pointed at the kept key → the transactions were silently orphaned by the merge.
- Manually repaired by repointing both `Ref3` values to the surviving key (data fix only).

## Why it matters

Any invoice-duplicate merge where the transaction link is a raw `mutaties.Ref3` key (the common
case) will break the same way — a silent, data-losing-looking failure (the file still exists under
the kept key, but the link is dead). The merge reports success while leaving dangling references.

## Goal

Merging duplicate assets must NEVER leave a transaction (or any consumer) pointing at a deleted S3
key. After a merge, every surviving link resolves.

## Direction (to design in the spec)

- **Rewrite direct-key references, not just `s3_asset_references`.** When merging, repoint every
  `mutaties.Ref3` (tenant-scoped) that equals the deleted asset's `s3_key` to the kept asset's
  `s3_key`, in the same transaction as the asset delete. Consider other raw-key holders too
  (templates, branding, landing pages) — audit which tables store a raw S3 key.
- **Preferred longer-term fix:** back the invoice link with a tracked `s3_asset_references` row
  (entity_type = the transaction) so the existing re-home logic covers it and raw keys stop leaking
  across the reference boundary — matches the "no raw key outside the reference layer" principle.
- **Safety:** make the merge fail-closed — if a referenced key cannot be repointed, do NOT delete
  the S3 object (or restore it), rather than reporting success with a dangling link.
- **Guard / test:** a preservation test that a merge over an asset referenced BOTH via
  `s3_asset_references` AND via a raw `mutaties.Ref3` leaves both resolving afterwards.
- **One-off sweep:** scan `mutaties.Ref3` for keys that no longer exist in `s3_assets` / S3 and
  report (there may be other already-orphaned links from earlier merges).

## Pointers

- Bug site: `backend/src/services/media_asset/lifecycle.py` → `merge_duplicates` (~L640).
- Route: `POST /api/media-assets/merge-duplicates`; frontend `mediaAssetService.mergeDuplicates`.
- Raw-key holder: `mutaties.Ref3` (S3 key) / `Ref4` (filename); see `pdf_validation.py`,
  `xlsx_download_helpers.py` for how Ref3/Ref4 are read.
- Reference tracking: `s3_asset_references` table + `ENTITY_TYPE_REGISTRY`
  (`services/media_asset/base.py`).
