# Open Issues for Railway Migration

## Status: ✅ ALL DECISIONS MADE

All critical decisions have been made. See `IMPACT_ANALYSIS_SUMMARY.md` for the complete master plan.

---

## ✅ RESOLVED: Issue #1: Google Drive Tenant-Specific Credentials

**Status**: ✅ RESOLVED
**Decision Made**: Decision 1 & 3 in IMPACT_ANALYSIS_SUMMARY.md

**Solution**:

- Tenant-specific Google Drive credentials stored in MySQL (encrypted)
- Each tenant has their own Google Drive with separate credentials
- Encryption key stored in Railway environment variables
- See Decision 1 (Credentials Management) and Decision 3 (File Storage Strategy)

---

## ✅ RESOLVED: Issue #2: Template Storage

**Status**: ✅ RESOLVED
**Decision Made**: Decision 2 in IMPACT_ANALYSIS_SUMMARY.md

**Solution**:

- Templates stored as XML with field mappings in tenant's Google Drive
- Template metadata stored in MySQL (`tenant_template_config` table)
- Tenant Administrator manages templates via Tenant Admin Module
- All templates (STR invoices, financial reports, tax forms) use same approach
- See Decision 2 (Template Storage & Management)

---

## ✅ RESOLVED: Issue #3: Tenant Identification

**Status**: ✅ RESOLVED
**Decision Made**: Already implemented in current system

**Solution**:

- Tenant identification already implemented via Cognito JWT tokens
- `@tenant_required` decorator extracts tenant from token
- Multi-tenant security already in place
- No changes needed for Railway migration

---

## ✅ RESOLVED: Issue #4: User Access Control

**Status**: ✅ RESOLVED
**Decision Made**: Decision 6 in IMPACT_ANALYSIS_SUMMARY.md

**Solution**:

- Tenant Administrator creates user accounts in Cognito
- Assigns tenant + role during user creation
- Sends invitation email to user
- User logs in with pre-configured access
- See Decision 6 (User Access Control)

---

## Next Steps

All decisions are complete. Ready to proceed with:

1. Create `TASKS.md` with implementation tasks
2. Begin implementation following the Architecture Summary
3. Test locally before Railway deployment

---

## Reference

See `IMPACT_ANALYSIS_SUMMARY.md` for:

- All 6 critical decisions
- Architecture summary
- Cost breakdown
- Implementation guidance
