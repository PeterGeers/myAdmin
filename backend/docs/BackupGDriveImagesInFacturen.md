# Backup Google Drive Facturen to OneDrive

## Objective
Automate incremental backup of invoice images from Google Drive "Facturen" folder to OneDrive, copying only new files since last backup.

## Implementation Approach

### Technology Stack
- **Language**: Python
- **APIs**: Google Drive API + Microsoft Graph API
- **Libraries**: `google-api-python-client`, `msgraph-sdk-python`

### Script Logic

1. **Authentication**
   - Google Drive API: Read access to Facturen folder
   - Microsoft Graph API: Write access to OneDrive backup folder

2. **Configuration**
   - Source: Google Drive folder ID (Facturen)
   - Target: OneDrive folder path
   - State file: Store `last_backup_date` timestamp

3. **Incremental Sync Process**
   ```
   - Read last_backup_date from state file
   - Query Google Drive: files where createdTime > last_backup_date
   - For each new file:
     * Download from Google Drive (temp or stream)
     * Upload to OneDrive
     * Log success/failure
   - Update last_backup_date to current timestamp
   - Save state file
   ```

4. **Error Handling**
   - Retry failed uploads
   - Log all operations
   - Email notification on completion/errors

5. **Scheduling**
   - Windows Task Scheduler (daily/weekly)
   - Or cron job on Linux/Mac

## Key Features
- Only processes new files (efficient)
- Maintains original filenames
- Preserves folder structure (optional)
- Idempotent (safe to re-run)
- Progress tracking and logging
