# Tasks — Slug Rename

**Status**: Ready to Start
**Created**: August 18, 2026
**Estimated Total**: 6-7 hours
**Branch**: `feature/slug-rename`

---

## Phase 1: Backend — Rename Logic (3h)

- [x] 1.1 Add `migrate_slug(old_slug, new_slug)` method to `LandingPageService` — copies all DynamoDB items from `PK=TENANT#{old}` to `PK=TENANT#{new}`, deletes originals
- [x] 1.2 Add `rename_slug(tenant, old_slug, new_slug, user_email)` orchestrator method to `TenantSlugService`
- [x] 1.3 Enhance `set_slug()` in `TenantSlugService` to detect rename (old slug exists and differs) and call `rename_slug`
- [x] 1.4 MySQL cleanup in rename flow: UPDATE `tenant_custom_domains.slug` and `s3_asset_references.entity_id`
- [x] 1.5 S3 + CloudFront cleanup: delete old CDN files, invalidate cache, update KVS if custom domain exists
- [x] 1.6 Auto-republish under new slug at end of rename flow

## Phase 2: Frontend — Edit Slug UI (2h)

- [x] 2.1 Add slug display with Edit button to `LandingPageEditor.tsx` (shown when slug already exists)
- [x] 2.2 Add confirmation dialog for slug rename with URL preview and warning
- [x] 2.3 Handle `renamed_from` and `warnings` in API response, reload draft after rename
- [x] 2.4 Update `TenantDetails.tsx` slug section with rename confirmation

## Phase 3: Testing (1.5h)

- [ ] 3.1 Backend unit test: `rename_slug` happy path — DynamoDB, MySQL, S3 all migrated (`tests/unit/test_tenant_slug_service.py`)
- [ ] 3.2 Backend unit test: rename with partial failure returns success + warnings
- [ ] 3.3 Backend unit test: rename to taken slug returns validation error
- [ ] 3.4 Backend unit test: rename to same slug is a no-op
- [ ] 3.5 API integration test: full rename flow via `PUT /api/landing/slug`

## Notes

- Phase 2 depends on Phase 1 (API must return `renamed_from` and `warnings`)
- Phase 3 can run in parallel with Phase 2
- Rename is not fully atomic (spans DynamoDB, S3, MySQL, CloudFront) — partial failures return warnings, not errors
- Old slug becomes immediately available for other tenants after rename
