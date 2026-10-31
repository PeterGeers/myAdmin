# Image Asset Management Overview

**Status**: Active
**Purpose**: Media asset lifecycle for all S3-stored objects — upload, registration,
references, orphan/retention, reconciliation, and admin maintenance (merge/import/cleanup).

## What this domain covers

Assets are first-class domain objects tracked in a central MySQL registry (`s3_assets` and
`s3_asset_references`) instead of storing raw S3 keys in application data. This enables safe
cleanup of orphans, consistency reconciliation between S3 and application data, and a clear
upload-to-deletion lifecycle across tenants. Buckets: `myadmin-shared-{env}` and
`myadmin-public-pages-{env}`.

Key code: `backend/src/services/media_asset/` (service plane) and the media-asset routes
(`backend/src/routes/media_asset_routes/`).

## Specs in this domain

| Spec | Status | Description | Link |
| --- | --- | --- | --- |
| Media Asset Management (feature) | active | Canonical feature spec: registry, references, lifecycle, reconciliation. | [requirements](requirements.md) · [design](design.md) · [tasks](tasks.md) |
| merge-duplicates-and-storage-500s (bugfix) | done | Fixed two 500s: `POST /api/media-assets/merge-duplicates` (delete-tolerance + precise `IntegrityError` catch) and `GET /api/tenant-admin/storage/config` (read from `parameters`, precise folder-id filter). | [_archive/merge-duplicates-and-storage-500s](_archive/merge-duplicates-and-storage-500s/bugfix.md) |

## Cross-references

- **Bug 2 of the archived bugfix is tenant-admin-storage-adjacent.** The storage/config fix
  (`backend/src/routes/tenant_admin_storage.py`) is in the tenant-admin storage area, not strictly
  media-asset; it was fixed alongside merge-duplicates and is filed here. If you arrive from the
  Tenant angle, that bug lives in `_archive/merge-duplicates-and-storage-500s`.
- **Open follow-up candidate:** merging duplicate assets can still orphan transaction links held
  as raw `mutaties.Ref3` S3 keys (`NoSuchKey`). Tracked, not yet implemented, in
  [`../../myBacklog/media-asset-merge-breaks-direct-key-references.md`](../../myBacklog/media-asset-merge-breaks-direct-key-references.md).

## Conventions

Completed specs for this domain move to `_archive/` and are marked `"status": "done"` in their
`.config.kiro`. Active specs sit directly in this folder. See the root
[`.kiro/specs/README.md`](../../README.md) for the overall model.
