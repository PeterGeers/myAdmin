# Design: Slug Rename

## Impact Analysis

### Where the slug is persisted

| Storage        | Location                        | Key Pattern                                | Action on Rename          |
| -------------- | ------------------------------- | ------------------------------------------ | ------------------------- |
| MySQL          | `tenant_slugs.slug`             | Direct column                              | UPDATE                    |
| MySQL          | `tenant_custom_domains.slug`    | Column per domain record                   | UPDATE                    |
| MySQL          | `s3_asset_references.entity_id` | Where `entity_type='landing_page'`         | UPDATE                    |
| DynamoDB       | `myadmin-landing-pages`         | `PK=TENANT#{slug}`, `SK=LANDING#HOME`      | Migrate (copy+delete)     |
| DynamoDB       | `myadmin-landing-pages`         | `PK=TENANT#{slug}`, `SK=VERSION#{n}`       | Migrate (copy+delete)     |
| S3             | `myadmin-public-pages-{env}`    | `{slug}/index.html`, `{slug}/landing.json` | Delete old, republish new |
| CloudFront     | Cache                           | `/{slug}/*` paths                          | Invalidate old slug       |
| CloudFront KVS | `domain_mapping`                | `custom_domain → slug` value               | Update value              |

### What does NOT need changing

- **Tracked S3 assets** (images, etc.): keyed by `{tenant}/{category}/{asset_id}_{file}` — uses tenant name, NOT slug
- **Image URLs in HTML**: absolute URLs to CloudFront using the asset path — not affected by slug change
- **DynamoDB table structure**: no schema change needed
- **CloudFront Function code**: reads slug from URL at runtime, no hardcoded values

## Architecture

### Rename Flow (Backend)

```
PUT /api/landing/slug  (existing endpoint, enhanced)
    │
    ├── 1. Validate new slug (format, uniqueness, reserved)
    │
    ├── 2. Detect if this is a rename (old slug exists and differs)
    │       If same slug → no-op, return success
    │       If no existing slug → simple INSERT (existing behavior)
    │       If different slug → RENAME workflow:
    │
    ├── 3. Migrate DynamoDB records
    │       ├── Read all items with PK=TENANT#{old_slug}
    │       ├── Write each to PK=TENANT#{new_slug} (same SK)
    │       └── Delete originals after successful writes
    │
    ├── 4. Update MySQL records
    │       ├── UPDATE tenant_slugs SET slug = new_slug
    │       ├── UPDATE tenant_custom_domains SET slug = new_slug WHERE administration = tenant
    │       └── UPDATE s3_asset_references SET entity_id = new_slug
    │                  WHERE entity_type = 'landing_page' AND administration = tenant
    │
    ├── 5. Delete old S3 CDN files
    │       ├── DELETE {old_slug}/index.html
    │       └── DELETE {old_slug}/landing.json
    │
    ├── 6. Republish under new slug
    │       └── Call publish(tenant, user_email) — writes new CDN files
    │
    ├── 7. Update CloudFront KVS (if custom domain exists)
    │       └── put_kvs_mapping(custom_domain, new_slug)
    │
    └── 8. Invalidate CloudFront cache for old slug
            └── CreateInvalidation: /{old_slug}/*
```

### Error Handling Strategy

The rename is NOT fully atomic (spans DynamoDB, S3, MySQL, CloudFront). Strategy:

1. **MySQL first**: update `tenant_slugs` — this is the source of truth. If this fails, abort.
2. **DynamoDB migration**: copy-then-delete pattern. If copy succeeds but delete fails, we have duplicates (acceptable, can be cleaned up).
3. **S3 + CloudFront**: best-effort. If these fail, the page won't serve but data is safe. A manual republish fixes it.
4. **Partial failure**: return `success: true` with warnings about cleanup steps that failed.

### API Contract

#### PUT /api/landing/slug (enhanced)

Request:

```json
{ "slug": "new-slug-name" }
```

Response (rename case):

```json
{
  "success": true,
  "slug": "new-slug-name",
  "renamed_from": "old-slug-name",
  "warnings": []
}
```

Response (with partial failure):

```json
{
  "success": true,
  "slug": "new-slug-name",
  "renamed_from": "old-slug-name",
  "warnings": [
    "Failed to delete old S3 files",
    "CloudFront invalidation pending"
  ]
}
```

## Frontend Changes

### Landing Page Editor (`LandingPageEditor.tsx`)

Current behavior: slug input only shown when `needsSlug === true`.

New behavior:

- When slug exists, show it in a read-only badge/display with an "Edit" button
- Clicking Edit transitions to inline edit mode (same input + validate + save flow)
- After successful rename, reload the draft (PK changed in DynamoDB)

### Tenant Details (`TenantDetails.tsx`)

Already has slug input with validation. Needs:

- Confirmation dialog when changing an existing slug ("This will change your public URL")
- Show the full URL preview: `{new_slug}.jabaki.nl`

## Security

- Tenant_Admin role required (existing check)
- `@tenant_required()` ensures you can only rename your own slug
- Slug uniqueness enforced at DB level (UNIQUE constraint)

## Performance

- DynamoDB migration: N+1 reads + N+1 writes (typically < 20 items for versions)
- S3 deletes: 2 objects
- CloudFront invalidation: async, < 60s propagation
- Total expected time: 2-5 seconds
