# Template Versioning Migration Summary

**Date**: February 1, 2026  
**Status**: ✅ Completed Successfully  
**Task**: Extend `tenant_template_config` table for versioning support

---

## Overview

This migration adds versioning and approval workflow support to the `tenant_template_config` table, enabling:

- Template version tracking
- Approval workflow (who approved, when, with notes)
- Template history (previous versions)
- Status management (draft, active, archived)

---

## Changes Made

### 1. Database Schema Changes

#### New Columns Added

| Column Name        | Type                              | Default  | Nullable | Description                                |
| ------------------ | --------------------------------- | -------- | -------- | ------------------------------------------ |
| `version`          | INT                               | 1        | NOT NULL | Version number of the template             |
| `approved_by`      | VARCHAR(255)                      | NULL     | YES      | Email/ID of user who approved the template |
| `approved_at`      | TIMESTAMP                         | NULL     | YES      | Timestamp when template was approved       |
| `approval_notes`   | TEXT                              | NULL     | YES      | Notes from the approver                    |
| `previous_file_id` | VARCHAR(255)                      | NULL     | YES      | Google Drive file ID of previous version   |
| `status`           | ENUM('draft','active','archived') | 'active' | NOT NULL | Current status of the template             |

#### New Indexes Added

| Index Name         | Columns                | Purpose                    |
| ------------------ | ---------------------- | -------------------------- |
| `idx_status`       | status                 | Filter templates by status |
| `idx_approved_by`  | approved_by            | Audit queries by approver  |
| `idx_admin_status` | administration, status | Common query pattern       |

### 2. Files Created

#### SQL Migration Script

- **File**: `backend/sql/alter_tenant_template_config_add_versioning.sql`
- **Purpose**: ALTER TABLE statements to add versioning columns and indexes
- **Features**:
  - Adds all 6 new columns
  - Creates 3 performance indexes
  - Updates existing records to have status 'active'
  - Includes verification queries
  - Includes rollback script in comments

#### Python Migration Script

- **File**: `scripts/templates/migrate_template_versioning.py`
- **Purpose**: Automated migration tool with verification
- **Features**:
  - Dry-run mode to preview changes
  - Automatic detection if migration is needed
  - Verification mode to check migration success
  - Detailed logging and error handling
  - Rollback support

---

## Migration Execution

### Pre-Migration State

- **Columns**: 8 (id, administration, template_type, template_file_id, field_mappings, is_active, created_at, updated_at)
- **Indexes**: 3 (PRIMARY, unique_tenant_template, idx_tenant)

### Post-Migration State

- **Columns**: 14 (original 8 + 6 new versioning columns)
- **Indexes**: 6 (original 3 + 3 new performance indexes)

### Migration Commands

```bash
# Dry run to preview changes
python scripts/templates/migrate_template_versioning.py --dry-run

# Execute migration with verification
python scripts/templates/migrate_template_versioning.py --verify

# Execute migration only
python scripts/templates/migrate_template_versioning.py
```

---

## Verification Results

✅ All 6 columns added successfully  
✅ All 3 indexes created successfully  
✅ Column types match specifications  
✅ Default values applied correctly  
✅ Existing records updated with status 'active'

### Final Schema

```sql
DESCRIBE tenant_template_config;
```

| Field            | Type                              | Null | Key | Default           | Extra                                         |
| ---------------- | --------------------------------- | ---- | --- | ----------------- | --------------------------------------------- |
| id               | int                               | NO   | PRI | NULL              | auto_increment                                |
| administration   | varchar(100)                      | NO   | MUL | NULL              |                                               |
| template_type    | varchar(50)                       | NO   |     | NULL              |                                               |
| template_file_id | varchar(255)                      | NO   |     | NULL              |                                               |
| field_mappings   | json                              | YES  |     | NULL              |                                               |
| version          | int                               | NO   |     | 1                 |                                               |
| approved_by      | varchar(255)                      | YES  | MUL | NULL              |                                               |
| approved_at      | timestamp                         | YES  |     | NULL              |                                               |
| approval_notes   | text                              | YES  |     | NULL              |                                               |
| previous_file_id | varchar(255)                      | YES  |     | NULL              |                                               |
| status           | enum('draft','active','archived') | NO   | MUL | active            |                                               |
| is_active        | tinyint(1)                        | YES  |     | 1                 |                                               |
| created_at       | timestamp                         | YES  |     | CURRENT_TIMESTAMP | DEFAULT_GENERATED                             |
| updated_at       | timestamp                         | YES  |     | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP |

---

## Usage Examples

### Creating a Draft Template

```python
from database import DatabaseManager

db = DatabaseManager()

# Insert a draft template
db.execute_query("""
    INSERT INTO tenant_template_config
    (administration, template_type, template_file_id, version, status)
    VALUES (%s, %s, %s, %s, %s)
""", ('GoodwinSolutions', 'str_invoice_nl', 'draft_file_id_123', 1, 'draft'),
fetch=False, commit=True)
```

### Approving a Template

```python
# Approve a draft template
db.execute_query("""
    UPDATE tenant_template_config
    SET status = 'active',
        approved_by = %s,
        approved_at = NOW(),
        approval_notes = %s
    WHERE administration = %s
        AND template_type = %s
        AND status = 'draft'
""", ('admin@example.com', 'Approved for production use',
      'GoodwinSolutions', 'str_invoice_nl'),
fetch=False, commit=True)
```

### Creating a New Version

```python
# Archive old version and create new version
db.execute_query("""
    UPDATE tenant_template_config
    SET status = 'archived'
    WHERE administration = %s
        AND template_type = %s
        AND status = 'active'
""", ('GoodwinSolutions', 'str_invoice_nl'), fetch=False, commit=True)

# Insert new version
db.execute_query("""
    INSERT INTO tenant_template_config
    (administration, template_type, template_file_id, version,
     previous_file_id, status)
    VALUES (%s, %s, %s, %s, %s, %s)
""", ('GoodwinSolutions', 'str_invoice_nl', 'new_file_id_456', 2,
      'old_file_id_123', 'draft'),
fetch=False, commit=True)
```

### Querying Active Templates

```python
# Get active template for a tenant
result = db.execute_query("""
    SELECT * FROM tenant_template_config
    WHERE administration = %s
        AND template_type = %s
        AND status = 'active'
    LIMIT 1
""", ('GoodwinSolutions', 'str_invoice_nl'))
```

---

## Rollback Instructions

If you need to rollback this migration, run the following SQL:

```sql
-- Remove indexes
DROP INDEX idx_status ON tenant_template_config;
DROP INDEX idx_approved_by ON tenant_template_config;
DROP INDEX idx_admin_status ON tenant_template_config;

-- Remove columns (in reverse order)
ALTER TABLE tenant_template_config DROP COLUMN status;
ALTER TABLE tenant_template_config DROP COLUMN previous_file_id;
ALTER TABLE tenant_template_config DROP COLUMN approval_notes;
ALTER TABLE tenant_template_config DROP COLUMN approved_at;
ALTER TABLE tenant_template_config DROP COLUMN approved_by;
ALTER TABLE tenant_template_config DROP COLUMN version;
```

---

## Next Steps

This migration enables the following Phase 2.6 tasks:

1. **Template Preview Service** - Can now store draft templates
2. **Approval Workflow** - Can track who approved templates and when
3. **Version History** - Can maintain template version history
4. **Status Management** - Can filter templates by status (draft/active/archived)

---

## Testing Recommendations

1. **Unit Tests**: Test TemplateService with new columns
2. **Integration Tests**: Test approval workflow end-to-end
3. **Performance Tests**: Verify index performance on status queries
4. **Rollback Tests**: Test rollback script in test environment

---

## Related Files

- SQL Script: `backend/sql/alter_tenant_template_config_add_versioning.sql`
- Migration Script: `scripts/templates/migrate_template_versioning.py`
- Template Service: `backend/src/services/template_service.py`
- Tasks Document: `.kiro/specs/Common/Railway migration/TASKS.md`

---

**Migration completed successfully on February 1, 2026**
