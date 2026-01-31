# Template Folders Created - Summary

**Date**: January 31, 2026
**Task**: Create template folders in each tenant's Google Drive
**Status**: ✅ Completed

---

## Overview

Successfully created the required folder structure in each tenant's Google Drive and stored the folder IDs in the `tenant_config` database table for future reference.

---

## Folder Structure Created

The following folders were created for each tenant:

1. **Templates/** - For storing tenant-specific templates (invoices, reports, tax forms)
2. **Invoices/** - For storing generated invoices (SHARED between tenants)
3. **Reports/** - For storing generated reports

**Note**: The Invoices folder is shared between GoodwinSolutions and PeterPrive tenants.

---

## GoodwinSolutions

**Root Folder**: `1C1eIugI8NTv4_BNNw-lEI8BCRr3eifYq`
**Root URL**: https://drive.google.com/drive/folders/1C1eIugI8NTv4_BNNw-lEI8BCRr3eifYq

### Created Folders

| Folder            | ID                                                              | URL                                                                                                  |
| ----------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Templates         | `1akidXDxK_A5xNRSyj6PGkFF97iKvAElC`                             | https://drive.google.com/drive/folders/1akidXDxK_A5xNRSyj6PGkFF97iKvAElC                             |
| Invoices (SHARED) | `0B9OBNkcEDqv1YWQzZDkyM2YtMTE4Yy00ODUzLWIzZmEtMTQ1NzEzMDQ1N2Ix` | https://drive.google.com/drive/folders/0B9OBNkcEDqv1YWQzZDkyM2YtMTE4Yy00ODUzLWIzZmEtMTQ1NzEzMDQ1N2Ix |
| Reports           | `1g0zG_yjoKjTHS9h9c-2lwwOmtihWGry_`                             | https://drive.google.com/drive/folders/1g0zG_yjoKjTHS9h9c-2lwwOmtihWGry_                             |

**Note**: Invoices folder is shared with PeterPrive tenant.

---

## PeterPrive

**Root Folder**: `0B9OBNkcEDqv1YWQzZDkyM2YtMTE4Yy00ODUzLWIzZmEtMTQ1NzEzMDQ1N2Ix`
**Root URL**: https://drive.google.com/drive/folders/0B9OBNkcEDqv1YWQzZDkyM2YtMTE4Yy00ODUzLWIzZmEtMTQ1NzEzMDQ1N2Ix

### Created Folders

| Folder            | ID                                                              | URL                                                                                                  |
| ----------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Templates         | `15lsRAvhHcomJS0E_uszlPPg3jpHUVT2K`                             | https://drive.google.com/drive/folders/15lsRAvhHcomJS0E_uszlPPg3jpHUVT2K                             |
| Invoices (SHARED) | `0B9OBNkcEDqv1YWQzZDkyM2YtMTE4Yy00ODUzLWIzZmEtMTQ1NzEzMDQ1N2Ix` | https://drive.google.com/drive/folders/0B9OBNkcEDqv1YWQzZDkyM2YtMTE4Yy00ODUzLWIzZmEtMTQ1NzEzMDQ1N2Ix |
| Reports           | `1almAuqZnjbDDi5K_LrztR9Ce7DMJ7Aqh`                             | https://drive.google.com/drive/folders/1almAuqZnjbDDi5K_LrztR9Ce7DMJ7Aqh                             |

**Note**: Invoices folder is shared with GoodwinSolutions tenant.

---

## Database Storage

All folder IDs have been stored in the `tenant_config` table with the following keys:

- `google_drive_root_folder_id` - Root folder for the tenant
- `google_drive_templates_folder_id` - Templates folder
- `google_drive_invoices_folder_id` - Invoices folder
- `google_drive_reports_folder_id` - Reports folder

### Query to View Configuration

```sql
SELECT administration, config_key, config_value
FROM tenant_config
WHERE config_key LIKE '%folder%'
ORDER BY administration, config_key;
```

---

## Script Created

**Location**: `scripts/create_template_folders.py`

**Features**:

- Authenticates with tenant-specific Google Drive credentials from database
- Checks if folders already exist before creating
- Creates folders in the tenant's root folder (or Drive root if not specified)
- Stores folder IDs in `tenant_config` table
- Supports dry-run mode for testing
- Can process all tenants or a specific tenant

**Usage**:

```bash
# Dry run for all tenants
python scripts/create_template_folders.py --dry-run

# Create folders for all tenants
python scripts/create_template_folders.py

# Create folders for specific tenant
python scripts/create_template_folders.py --tenant GoodwinSolutions

# Dry run for specific tenant
python scripts/create_template_folders.py --tenant GoodwinSolutions --dry-run
```

---

## GoogleDriveService Enhancement

**File**: `backend/src/google_drive_service.py`

**Enhancement**: Fixed token handling to merge `client_id` and `client_secret` from OAuth credentials when the token doesn't include them. This ensures compatibility with tokens stored in the database.

**Change**:

```python
# Ensure token_data has client_id and client_secret from oauth_creds
if 'client_id' not in token_data and 'installed' in oauth_creds:
    token_data['client_id'] = oauth_creds['installed']['client_id']
    token_data['client_secret'] = oauth_creds['installed']['client_secret']
elif 'client_id' not in token_data and 'web' in oauth_creds:
    token_data['client_id'] = oauth_creds['web']['client_id']
    token_data['client_secret'] = oauth_creds['web']['client_secret']
```

---

## Next Steps

1. ✅ Template folders created
2. ⏭️ Upload templates to tenant Google Drives (next task in TASKS.md)
3. ⏭️ Store template metadata in `tenant_template_config` table
4. ⏭️ Verify templates are accessible

---

## Verification

To verify the folders were created correctly:

1. **Check Google Drive**: Visit the URLs above to see the folders
2. **Check Database**: Run the SQL query above to see the stored folder IDs
3. **Test Script**: Run the script in dry-run mode to verify it detects existing folders

---

## Notes

- The script automatically handles existing folders and won't create duplicates
- Folder IDs are stored in the database for easy retrieval by other services
- The script uses tenant-specific credentials from the database (encrypted)
- Token refresh is handled automatically by the GoogleDriveService
