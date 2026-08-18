# Requirements: Slug Rename

## User Stories

### US-1: Change slug from Landing Page Editor

**As a** Tenant Admin,
**I want to** change my landing page slug after it was initially set,
**so that** I can rebrand my public URL without losing my draft content and version history.

### US-2: Automatic resource migration on slug change

**As a** system,
**I want to** migrate all dependent resources when a slug changes,
**so that** the old slug stops serving content and the new slug works immediately.

### US-3: Prevent broken links during transition

**As a** Tenant Admin,
**I want** the old slug URL to stop working after I change it (or optionally redirect),
**so that** there's no stale content served under my old name.

## Acceptance Criteria

### AC-1: UI allows slug editing

- [ ] Landing Page Editor shows current slug with an Edit button (when slug already exists)
- [ ] Clicking Edit opens an inline input with validation (same rules as initial setup)
- [ ] Saving triggers the rename workflow
- [ ] TenantDetails page also supports slug editing (already has input, needs save confirmation)

### AC-2: Backend rename endpoint performs full migration

- [ ] DynamoDB: draft item (`TENANT#{old_slug}` → `TENANT#{new_slug}`) is migrated
- [ ] DynamoDB: all version items (`VERSION#N`) are migrated to new PK
- [ ] S3: old CDN files (`{old_slug}/index.html`, `{old_slug}/landing.json`) are deleted
- [ ] S3: new CDN files are written at `{new_slug}/` (via republish)
- [ ] CloudFront: cache invalidated for old slug paths (`/{old_slug}/*`)
- [ ] KVS: if custom domain exists, mapping updated from `domain→old_slug` to `domain→new_slug`
- [ ] MySQL `tenant_custom_domains.slug` column updated
- [ ] MySQL `s3_asset_references.entity_id` updated where `entity_type='landing_page'`

### AC-3: Validation

- [ ] New slug passes same validation rules (format, length, reserved words, uniqueness)
- [ ] Cannot rename to a slug that's already taken by another tenant
- [ ] Cannot rename to the same slug (no-op guard)

### AC-4: Republish after rename

- [ ] After slug change, the landing page is automatically republished under the new slug
- [ ] The new `index.html` uses the correct canonical URL, contact form API URL, etc.

### AC-5: Old slug cleanup

- [ ] Old S3 path content is removed
- [ ] Old slug becomes available for other tenants to claim
- [ ] CloudFront cache for old slug is invalidated

## Out of Scope

- Redirect from old slug to new slug (for v1, old slug simply stops working)
- Bulk rename / admin rename of another tenant's slug
- Slug change history/audit trail (for v1)

## Success Metrics

- Slug rename completes in < 10 seconds
- No stale content served under old slug after invalidation propagates (< 60s)
- Zero data loss (draft sections, version history preserved)
