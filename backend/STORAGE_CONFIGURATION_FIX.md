# Storage Configuration Fix

## Issue
The Storage tab in TenantAdminDashboard was not displaying storage usage statistics correctly. The user had configuration entries in the `tenant_config` table with keys like `google_drive_invoices_folder_id`, but the system was not properly handling these keys.

## Root Cause
1. **Backend**: The GET `/api/tenant-admin/storage/config` endpoint was stripping prefixes (`storage_` or `google_drive_`) from config keys, causing mismatches
2. **Backend**: The GET `/api/tenant-admin/storage/usage` endpoint was using the stripped keys instead of the original database keys
3. **Frontend**: The component was expecting specific hardcoded folder types (`facturen`, `invoices`, `reports`) instead of dynamically handling whatever keys exist in the database

## Solution

### Backend Changes (`backend/src/routes/tenant_admin_storage.py`)

1. **GET `/api/tenant-admin/storage/config`**:
   - Changed query to select ALL keys ending with `_folder_id` (not just `storage_*` or `google_drive_*`)
   - Return keys as-is from database (e.g., `google_drive_invoices_folder_id`)
   - No prefix stripping

2. **GET `/api/tenant-admin/storage/usage`**:
   - Changed query to select ALL keys ending with `_folder_id`
   - Use original config keys (e.g., `google_drive_invoices_folder_id`) as dictionary keys
   - Return usage stats keyed by original config_key for proper matching

### Frontend Changes

1. **`frontend/src/services/tenantAdminApi.ts`**:
   - Changed `StorageConfig` interface from fixed properties to dynamic index signature:
     ```typescript
     export interface StorageConfig {
       [key: string]: string; // Dynamic keys like "google_drive_invoices_folder_id"
     }
     ```

2. **`frontend/src/components/TenantAdmin/StorageConfiguration.tsx`**:
   - Removed hardcoded `folderTypes` array
   - Changed to dynamically render folders based on `Object.entries(config)`
   - Updated `handleSelectFolder()` to use full config key (not construct it)
   - Updated `handleTestFolder()` to use full config key
   - Storage Usage section now properly displays all configured folders with:
     - Config key name (e.g., `google_drive_invoices_folder_id`)
     - Actual folder name from Google Drive
     - File count and total size in MB
     - Link to open folder in Google Drive
   - Added warning message when no folders are configured

## Data Flow

1. **Database** (`tenant_config` table):
   ```
   config_key: "google_drive_invoices_folder_id"
   config_value: "1abc...xyz" (Google Drive folder ID)
   ```

2. **Backend GET /config** returns:
   ```json
   {
     "config": {
       "google_drive_invoices_folder_id": "1abc...xyz",
       "google_drive_reports_folder_id": "1def...uvw"
     }
   }
   ```

3. **Backend GET /usage** returns:
   ```json
   {
     "usage": {
       "google_drive_invoices_folder_id": {
         "folder_id": "1abc...xyz",
         "folder_name": "Invoices 2024",
         "folder_url": "https://drive.google.com/...",
         "file_count": 42,
         "total_size_mb": 156.78,
         "accessible": true
       }
     }
   }
   ```

4. **Frontend** displays each configured folder with its usage statistics

## Benefits

1. **Flexible**: Supports any config key naming convention (not hardcoded)
2. **Accurate**: Keys match exactly between config and usage endpoints
3. **User-friendly**: Shows actual folder names from Google Drive
4. **Maintainable**: No need to update code when adding new folder types

## Testing

To test the fix:

1. Navigate to Tenant Admin → Storage tab
2. Click "Refresh" button
3. Verify that:
   - Configured folders appear in "Folder Mappings" section
   - Storage usage statistics appear in "Storage Usage" section
   - Each folder shows: config key, folder name, file count, size in MB, and "Open in Drive" link
   - Available folders list shows all Google Drive folders with "In Use" badge for configured ones

## Files Modified

- `backend/src/routes/tenant_admin_storage.py` (3 functions updated)
- `frontend/src/services/tenantAdminApi.ts` (StorageConfig interface)
- `frontend/src/components/TenantAdmin/StorageConfiguration.tsx` (complete refactor)

## Status

✅ Backend changes complete
✅ Frontend changes complete
✅ TypeScript compilation successful (no errors)
✅ Ready for testing
