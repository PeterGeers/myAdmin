# Railway Migration TASKS.md Reorganization Plan

**Date**: 2026-02-08  
**Purpose**: Address "Note PG:" comments and reorganize Phase 3 tasks

---

## Summary of Changes

### 1. Move Tasks from Phase 3 to Phase 5

**Rationale**: Tasks 3.2-3.5 require Google Drive storage which needs Railway deployment first.

**Phase 3 (Simplified - Database & Cognito Only)**:

- 3.1 Create myAdmin Tenant (database + Cognito) ✅ Keep
- 3.2 Configure SysAdmin Access (role setup only) ✅ Keep (renamed from old 3.4)
- 3.3 Testing (database & Cognito only) ✅ Keep (renamed from old 3.5, partial)

**Move to Phase 5 (After Railway Deployment)**:

- Old 3.2 → New 5.12: Setup myAdmin Storage Structure (Google Drive folders)
- Old 3.3 → New 5.13: Migrate Generic Templates (to myAdmin Drive)
- Old 3.4 (storage part) → New 5.14: Test myAdmin Storage Access
- Old 3.5 (template testing) → New 5.15: Test Generic Template Access

---

## Detailed Changes

### Change 1: Phase 2.3 Note (Line ~286)

**Current**:

```
Note PG: There is still work todo to make it usable. But we can postpone this to after the migration. The basics work
```

**Replace with**:

```
**Status**: ✅ Basic functionality complete. Additional work needed post-migration for full usability (see Phase 5 tasks).
```

---

### Change 2: Phase 2.4 Note (Line ~295)

**Current**:

```
Note PG: Google drive has now templates with the same name and the same content but with different file ID's As in Google drive the id's are the UIDs you do not know which is the realm used and why they are created and not overwritten
```

**Replace with**:

```
**Known Issue**: Google Drive may have duplicate templates with same name but different file IDs. The file IDs are unique identifiers in Google Drive. Need to implement deduplication logic or use specific file ID references. This will be addressed in Phase 5 template cleanup tasks.
```

---

### Change 3: Phase 3 Complete Rewrite (Lines ~680-730)

**Current Phase 3**: myAdmin System Tenant (1-2 days) with tasks 3.1-3.5

**New Phase 3**: myAdmin System Tenant (1 day) - Database & Cognito Only

```markdown
## Phase 3: myAdmin System Tenant (1 day)

**Goal**: Create myAdmin tenant for platform management (database and Cognito only)

**Prerequisites**:

- Phase 1 completed
- Phase 2 completed

**Note**: Storage setup (Google Drive folders, template migration) will be done in Phase 5 after Railway deployment.

### Tasks

#### 3.1 Create myAdmin Tenant

- [x] Add myAdmin tenant to database
- [x] Create myAdmin Google Drive account (or use existing)
- [x] Store myAdmin Google Drive credentials in database
- [x] Configure myAdmin tenant in Cognito

**Verification**: myAdmin tenant exists in database and Cognito, credentials stored.

#### 3.2 Configure SysAdmin Access

**Important**: SysAdmin role already exists in Cognito. A user can have multiple roles across different tenants (e.g., TenantAdmin for GoodwinSolutions + SysAdmin for myAdmin).

- [ ] Ensure SysAdmin role has access to myAdmin tenant
- [ ] Verify SysAdmin cannot access other tenant data (GoodwinSolutions, PeterPrive)
- [ ] Test that users with combined roles (TenantAdmin + SysAdmin) can access both their tenant and myAdmin
- [ ] Document role combination behavior

#### 3.3 Testing (Database & Cognito Only)

- [ ] Test SysAdmin access to myAdmin tenant (database queries)
- [ ] Verify tenant isolation (SysAdmin cannot query GoodwinSolutions/PeterPrive data)
- [ ] Test user with combined roles can switch between tenants
- [ ] Run security tests for role-based access control

**Deliverables**:

- ✅ myAdmin tenant created in database
- ✅ myAdmin tenant configured in Cognito
- ✅ SysAdmin role access configured
- ✅ Tenant isolation verified
- ✅ All tests passing

**Note**: Google Drive storage setup, template migration, and template access testing will be done in Phase 5 (tasks 5.12-5.15).
```

---

### Change 4: Phase 4.1 Note (Line ~751)

**Current**:

```
Note PG: Please check what we already have specific template related a lot has been done
```

**Add before task list**:

```
**Note**: Many template-related endpoints already exist from Phase 2.6 (Template Preview and Validation). Review `backend/src/tenant_admin_routes.py` to avoid duplication. Focus on credential management and user management endpoints.
```

---

### Change 5: Phase 4.2 Note (Line ~774)

**Current**:

```
Note PG: check what we already have
```

**Add before task list**:

```
**Note**: Template Management components already exist from Phase 2.6. Review `frontend/src/components/TenantAdmin/TemplateManagement/` before creating new components. Focus on credentials and user management UI.
```

---

### Change 6: Phase 4.4 Note (Line ~807)

**Current**:

```
- [ ] Verify SysAdmin cannot access tenant data *(Note PG: A user with combined roles can??)
```

**Replace with**:

```
- [ ] Verify SysAdmin cannot access tenant data (except myAdmin tenant)
- [ ] Test users with combined roles (TenantAdmin + SysAdmin) can access both their tenant and myAdmin
- [ ] Document role combination behavior and access patterns
```

---

### Change 7: Phase 4 - Add Git Upload Tasks

**Add after each major section**:

After 4.1:

```
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1
```

After 4.2:

```
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1
```

After 4.3:

```
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1
```

After 4.4:

```
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1
```

After 4.5:

```
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1
```

---

### Change 8: Phase 5.3 Note (Line ~869)

**Current**:

```
Note PG: Check what we really have
```

**Replace with**:

```
**Status**: ✅ Already completed (January 31, 2026). All Google Drive endpoints fixed to use tenant-specific credentials. Verified in local testing.
```

---

### Change 9: Add New Phase 5 Tasks (After 5.11)

**Add new section 5.12-5.15** (moved from old Phase 3):

```markdown
#### 5.12 Setup myAdmin Storage Structure

**Prerequisites**: Railway deployed, myAdmin tenant created

- [ ] Create folder structure in myAdmin Google Drive:
  - Generic Templates/
  - Email Templates/
  - Platform Assets/Logos/
  - Platform Assets/Branding/
- [ ] Upload generic templates to myAdmin Drive
- [ ] Store folder IDs in configuration
- [ ] Verify folder access from Railway application
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 5.13 Migrate Generic Templates

**Prerequisites**: 5.12 completed

- [ ] Identify generic templates (used by all tenants)
- [ ] Move to myAdmin Google Drive
- [ ] Update template references in code
- [ ] Test template access from myAdmin tenant
- [ ] Verify tenant-specific templates still work
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 5.14 Test myAdmin Storage Access

**Prerequisites**: 5.12, 5.13 completed

- [ ] Test SysAdmin can access myAdmin Google Drive
- [ ] Test SysAdmin cannot access tenant Google Drives (GoodwinSolutions, PeterPrive)
- [ ] Test users with combined roles can access both
- [ ] Verify folder permissions are correct
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 5.15 Test Generic Template Access

**Prerequisites**: 5.13 completed

- [ ] Test generic template loading from myAdmin Drive
- [ ] Test tenant-specific template loading from tenant Drives
- [ ] Verify template fallback logic (tenant → generic)
- [ ] Test template rendering with both generic and tenant templates
- [ ] Run E2E tests for all report types
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

#### 5.16 Template Deduplication Cleanup

**Prerequisites**: 5.15 completed

**Purpose**: Address duplicate templates in Google Drive (same name, different file IDs)

- [ ] Audit all templates in Google Drive (list all file IDs and names)
- [ ] Identify duplicates (same name, different IDs)
- [ ] Determine which file ID to keep (most recent or explicitly chosen)
- [ ] Update `tenant_template_config` table with correct file IDs
- [ ] Delete duplicate template files from Google Drive
- [ ] Verify all reports still work with deduplicated templates
- [ ] Document template file ID management process
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1
```

---

### Change 10: Add Requirements/Design Task Before Phase 4

**Add new section before Phase 4**:

```markdown
### 3.4 Create Tenant Admin & SysAdmin Specifications

**Prerequisites**: Phase 3.1-3.3 completed

**Purpose**: Document requirements and design before implementing Phase 4

- [ ] Create `.kiro/specs/Common/TenantAdmin-Module/` folder
- [ ] Create `requirements.md` (user stories, acceptance criteria)
  - Credential management requirements
  - User management requirements
  - Template management requirements (reference Phase 2.6)
  - Storage configuration requirements
- [ ] Create `design.md` (technical design)
  - API endpoint specifications
  - Database schema (if new tables needed)
  - Frontend component architecture
  - Authentication and authorization design
- [ ] Create `TASKS.md` (detailed implementation tasks)
  - Break down Phase 4 into granular tasks
  - Add time estimates
  - Add dependencies
- [ ] Review and approve specifications
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Deliverables**:

- ✅ Complete requirements documentation
- ✅ Complete technical design
- ✅ Detailed implementation tasks
- ✅ Specifications reviewed and approved

**Note**: This keeps the Railway migration TASKS.md focused on execution while detailed module specifications live in their own folder.
```

---

### Change 11: Update Progress Tracking Table (Line ~1013)

**Current**:

```
Note PG: Update this table reflects the 5 phase before
```

**Replace table with**:

```markdown
## 📊 Progress Tracking

| Phase                        | Status         | Duration | Start Date | End Date | Notes                                                    |
| ---------------------------- | -------------- | -------- | ---------- | -------- | -------------------------------------------------------- |
| Phase 1: Credentials         | ✅ Completed   | 4 days   | -          | -        | All tasks complete                                       |
| Phase 2: Templates           | ✅ Completed   | 3 days   | -          | -        | Basic functionality complete, post-migration work needed |
| Phase 3: myAdmin Tenant      | 🔄 In Progress | 1 day    | -          | -        | Database & Cognito only                                  |
| Phase 4: Tenant Admin Module | ⏸️ Not Started | 4-5 days | -          | -        | Requires Phase 3.4 (specs) first                         |
| Phase 5: Railway Deployment  | ⏸️ Not Started | 2-3 days | -          | -        | Includes storage setup (5.12-5.16)                       |

**Legend**:

- ⏸️ Not Started
- 🔄 In Progress
- ✅ Completed
- ⚠️ Blocked
- 🔍 Under Review
```

---

### Change 12: Update Notes Section (Line ~1070)

**Current**:

```
Note PG: Add a task git-upload.ps1 after each group of tasks from 4.2 -5.x
Note PG: Do we need a requirements and  design of the Tenant and the SysAdmin functions. If we need it add a task before we start working on it to make a requirements.md design.md and update the tasks in a .kiro\specs\subject. So we can keep this task focussed on execution of the migration and have specialized ityems on tyhe subjects
```

**Replace with**:

```markdown
## Notes

- Each phase should be completed and tested before moving to the next
- Keep local backups until production is stable for 1 week
- Test thoroughly in local environment before Railway deployment
- Document any deviations from the plan
- Update this file as tasks are completed
- **Git uploads**: Each major task group includes `git-upload.ps1` step for version control
- **Specifications**: Detailed module specs (TenantAdmin, SysAdmin) are in separate folders under `.kiro/specs/` to keep this TASKS.md focused on execution
```

---

## Summary of All Changes

1. ✅ Cleaned up "Note PG:" comments with proper formatting
2. ✅ Reorganized Phase 3 to focus on database/Cognito only (1 day instead of 1-2 days)
3. ✅ Moved storage tasks (old 3.2-3.5) to Phase 5 (new 5.12-5.15)
4. ✅ Added template deduplication task (5.16)
5. ✅ Added requirements/design task before Phase 4 (3.4)
6. ✅ Added git-upload.ps1 tasks after each major section in Phase 4 and 5
7. ✅ Clarified role combination behavior (TenantAdmin + SysAdmin)
8. ✅ Updated progress tracking table
9. ✅ Added notes about existing Phase 2.6 work to avoid duplication

---

## Next Steps

1. Review this plan
2. If approved, apply changes to TASKS.md
3. Commit updated TASKS.md to GitHub
4. Create `.kiro/specs/Common/TenantAdmin-Module/` folder structure
5. Begin Phase 3.4 (requirements and design)
