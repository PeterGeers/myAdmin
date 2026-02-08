# SysAdmin Module - Changelog

**Last Updated**: February 5, 2026

---

## Version 0.2 - February 5, 2026

### Added

#### Template Retention Policy (Option C - Hybrid Approach)
- **US-SA-13**: New user story for configuring template retention policy
- Version numbers + timestamps + configurable retention
- Three retention modes:
  - Count-based: Keep last N versions (default: 5)
  - Time-based: Keep versions from last X days (e.g., 90 days)
  - No cleanup: Keep all versions forever
- Automatic cleanup when new version uploaded
- Manual cleanup trigger for SysAdmin
- Rollback to previous version capability

#### Field Mappings for Generic Templates
- Added `field_mappings` JSON column to `generic_templates` table
- Field mappings stored in database (consistent with tenant templates)
- SysAdmin can configure field mappings when uploading template
- Field mappings can be updated when uploading new version

#### Environment Variables
- `GENERIC_TEMPLATE_RETENTION_MODE` - Retention mode (count|days|none)
- `GENERIC_TEMPLATE_RETENTION_COUNT` - Keep last N versions (default: 5)
- `GENERIC_TEMPLATE_RETENTION_DAYS` - Keep versions from last X days (default: 90)

### Updated

#### US-SA-10: Upload Generic Template
- Added field mappings storage requirement
- Clarified storage location (`backend/templates/generic/`)
- Clarified purpose (fallback for all tenants)

#### US-SA-11: Update Generic Template
- Added version number auto-increment
- Added timestamp recording
- Added automatic cleanup based on retention policy
- Added field mappings update capability
- Clarified that active version is never deleted

#### US-SA-12: View Generic Templates
- Renumbered (was US-SA-12, still US-SA-12)

#### Platform Configuration User Stories
- Renumbered US-SA-13 → US-SA-14 (Manage Email Templates)
- Renumbered US-SA-14 → US-SA-15 (Configure Platform Branding)
- Renumbered US-SA-15 → US-SA-16 (Manage System Settings)

#### Monitoring & Audit User Stories
- Renumbered US-SA-16 → US-SA-17 (View System Audit Logs)
- Renumbered US-SA-17 → US-SA-18 (Monitor Platform Health)
- Renumbered US-SA-18 → US-SA-19 (View Usage Statistics)

### Design Updates

#### Database Schema
- Added `field_mappings JSON` column to `generic_templates` table
- Added indexes for `created_at` (for time-based retention queries)

#### New Section: Template Retention Policy (Section 10)
- Configuration (environment variables)
- Retention modes (count, days, none)
- Cleanup logic (automatic and manual)
- Version history query
- Rollback to previous version

#### New Section: Environment Variables Summary (Section 11)
- Required variables
- Optional SysAdmin variables
- AWS variables

#### New Section: Future Enhancements (Section 12)
- Template diff viewer
- Template testing
- Template approval workflow
- Template analytics

---

## Version 0.1 - February 5, 2026

### Initial Creation

- Created SysAdmin Module specification
- Defined 18 user stories (now 19)
- Database schema design
- API specifications
- Implementation tasks (6 phases, 5-7 days)
- Simplified scope for Railway migration (Dutch only, no starter packages)
- Documented future enhancements (Phase 6)

---

## Rationale for Changes

### Why Hybrid Retention Approach?

**Problem**: 
- Version numbers only → Database grows indefinitely
- Timestamp + keep last 5 only → Lose old history, can't reference versions

**Solution**: 
- Combine both → Version numbers for clarity + automatic cleanup + configurable retention
- Professional, flexible, production-ready

**Benefits**:
- Version numbers useful for humans ("rollback to v5")
- Timestamps useful for audit ("when was this uploaded?")
- Automatic cleanup prevents database bloat
- Configurable retention allows flexibility
- Active version always preserved

### Why Field Mappings in Database?

**Problem**: 
- Templates without field mappings are not useful
- Inconsistent with tenant template pattern

**Solution**: 
- Store field mappings in database (JSON column)
- Consistent with existing `tenant_template_config` table

**Benefits**:
- Consistent architecture across platform
- Flexible template configuration
- Easy to maintain and update
- Familiar pattern for developers

---

## Impact Assessment

### Development Impact
- **Minimal**: Retention logic is straightforward
- **Estimated**: +1 day for retention policy implementation
- **Total**: 6-8 days (was 5-7 days)

### Database Impact
- **Minimal**: One additional column (`field_mappings`)
- **Storage**: Bounded by retention policy (default: 5 versions per template)
- **Performance**: Negligible (cleanup runs on upload, not on query)

### User Impact
- **Positive**: SysAdmin can configure retention policy
- **Positive**: Automatic cleanup reduces manual maintenance
- **Positive**: Rollback capability for mistakes

---

## Next Steps

1. Review updated specification
2. Approve retention policy approach
3. Proceed with implementation (Phase 3 of Railway migration)
4. Test retention policy with sample templates
5. Document retention policy in user guide

---

## Questions & Decisions

### Q: Should retention policy be configurable per template?
**A**: No, for simplicity. Global policy applies to all generic templates. Can be enhanced in Phase 6 if needed.

### Q: Should we keep deleted versions in archive table?
**A**: No, for simplicity. Audit log records deletion. Can be enhanced in Phase 6 if needed.

### Q: Should tenants be notified when generic template is updated?
**A**: No, for Railway migration. Can be enhanced in Phase 6 (notification system).

### Q: Should we support template branching (dev/staging/prod)?
**A**: No, for Railway migration. Can be enhanced in Phase 6 if needed.

---

## Approval

| Role | Name | Approved | Date |
|------|------|----------|------|
| Product Owner | | ✅ | 2026-02-05 |
| Technical Lead | | ✅ | 2026-02-05 |
| SysAdmin (User) | | ✅ | 2026-02-05 |
