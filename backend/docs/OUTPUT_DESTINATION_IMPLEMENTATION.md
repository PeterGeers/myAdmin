# Output Destination Implementation

**Date**: January 2026  
**Status**: ✅ Complete  
**Related Task**: `.kiro/specs/Common/Railway migration/TASKS.md` - Phase 2, Task 2.5

---

## Overview

Implemented output destination management for generated reports, allowing users to choose where their reports are saved:

- **download**: Return content to frontend for local download (default)
- **gdrive**: Upload to tenant's Google Drive
- **s3**: AWS S3 upload (placeholder for future implementation)

---

## Implementation Details

### 1. OutputService (`backend/src/services/output_service.py`)

Created a new service to handle output destination management:

**Key Methods**:

- `handle_output()`: Main entry point for handling output destinations
- `_handle_download()`: Returns content to frontend for download
- `_handle_gdrive_upload()`: Uploads content to tenant's Google Drive
- `_handle_s3_upload()`: Placeholder for S3 upload (raises NotImplementedError)
- `_get_or_create_reports_folder()`: Gets or creates tenant-specific Reports folder in Google Drive

**Features**:

- Automatic timestamp addition to filenames when file already exists in Google Drive
- Tenant-specific Reports folders (e.g., `Reports_GoodwinSolutions`)
- Support for custom folder IDs
- Comprehensive error handling and logging

### 2. Updated Report Endpoints

Updated the following endpoints to support `output_destination` parameter:

#### a. Aangifte IB Export (`backend/src/app.py`)

- **Endpoint**: `POST /api/reports/aangifte-ib-export`
- **New Parameters**:
  - `output_destination`: 'download' (default), 'gdrive', or 's3'
  - `folder_id`: Optional Google Drive folder ID
- **Response**: Returns content for download OR URL for gdrive/s3

#### b. BTW Generate Report (`backend/src/app.py`)

- **Endpoint**: `POST /api/btw/generate-report`
- **New Parameters**:
  - `output_destination`: 'download' (default), 'gdrive', or 's3'
  - `folder_id`: Optional Google Drive folder ID
- **Response**: Returns HTML report for download OR URL for gdrive/s3

#### c. Toeristenbelasting Generate Report (`backend/src/app.py`)

- **Endpoint**: `POST /api/toeristenbelasting/generate-report`
- **New Parameters**:
  - `output_destination`: 'download' (default), 'gdrive', or 's3'
  - `folder_id`: Optional Google Drive folder ID
- **Response**: Returns HTML report for download OR URL for gdrive/s3

#### d. STR Invoice Generation (`backend/src/str_invoice_routes.py`)

- **Endpoint**: `POST /api/str-invoice/generate-invoice`
- **New Parameters**:
  - `output_destination`: 'download' (default), 'gdrive', or 's3'
  - `folder_id`: Optional Google Drive folder ID
- **Response**: Returns invoice HTML for download OR URL for gdrive/s3

### 3. Unit Tests (`backend/tests/unit/test_output_service.py`)

Created comprehensive unit tests for OutputService:

**Test Coverage** (11 tests, all passing):

- ✅ Service initialization
- ✅ Download destination handling
- ✅ Invalid destination error handling
- ✅ Google Drive upload for new files
- ✅ Google Drive upload for existing files (timestamp addition)
- ✅ Google Drive upload with custom folder ID
- ✅ S3 upload not implemented error
- ✅ Get existing Reports folder
- ✅ Create new Reports folder
- ✅ Error when parent folder not configured
- ✅ Download with different content types

---

## Usage Examples

### Frontend Usage

#### Download (Default)

```javascript
const response = await fetch("/api/reports/aangifte-ib-export", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    year: 2025,
    administration: "GoodwinSolutions",
    data: reportData,
    output_destination: "download", // or omit for default
  }),
});

const result = await response.json();
// result.html contains the report content
// result.filename contains the suggested filename
```

#### Google Drive Upload

```javascript
const response = await fetch("/api/reports/aangifte-ib-export", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    year: 2025,
    administration: "GoodwinSolutions",
    data: reportData,
    output_destination: "gdrive",
  }),
});

const result = await response.json();
// result.url contains the Google Drive URL
// result.filename contains the uploaded filename
// result.message contains success message
```

#### Google Drive Upload to Specific Folder

```javascript
const response = await fetch("/api/reports/aangifte-ib-export", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    year: 2025,
    administration: "GoodwinSolutions",
    data: reportData,
    output_destination: "gdrive",
    folder_id: "1a2b3c4d5e6f7g8h9i0j", // Custom folder ID
  }),
});
```

---

## API Response Formats

### Download Response

```json
{
  "success": true,
  "html": "<html>...</html>",
  "filename": "Aangifte_IB_GoodwinSolutions_2025.html"
}
```

### Google Drive Response

```json
{
  "success": true,
  "destination": "gdrive",
  "url": "https://drive.google.com/file/d/abc123",
  "filename": "Aangifte_IB_GoodwinSolutions_2025.html",
  "message": "Report uploaded to Google Drive: Aangifte_IB_GoodwinSolutions_2025.html"
}
```

### S3 Response (Future)

```json
{
  "success": false,
  "error": "S3 upload destination is not yet implemented. Please use 'download' or 'gdrive' destinations."
}
```

---

## Google Drive Folder Structure

Reports are uploaded to tenant-specific folders:

```
Facturen (or testFacturen in test mode)
└── Reports_GoodwinSolutions/
    ├── Aangifte_IB_GoodwinSolutions_2025.html
    ├── BTW_Aangifte_GoodwinSolutions_2025_Q1.html
    └── Invoice_RES123_NL.html
└── Reports_PeterPrive/
    ├── Aangifte_IB_PeterPrive_2025.html
    └── ...
```

---

## Error Handling

The OutputService provides comprehensive error handling:

1. **Invalid Destination**: Raises `ValueError` with valid options
2. **S3 Not Implemented**: Raises `NotImplementedError` with helpful message
3. **Google Drive Errors**: Logs error and raises `Exception` with details
4. **Missing Configuration**: Raises `Exception` when parent folder ID not configured
5. **File Already Exists**: Automatically adds timestamp to filename

---

## Security Considerations

1. **Tenant Isolation**: Each tenant has their own Reports folder
2. **Authentication**: All endpoints require Cognito authentication
3. **Authorization**: Tenant-required decorator ensures users can only access their own data
4. **Google Drive Credentials**: Uses tenant-specific credentials from database

---

## Future Enhancements

### S3 Upload Implementation

When implementing S3 upload, update `_handle_s3_upload()` method:

```python
def _handle_s3_upload(self, content, filename, administration, content_type):
    """Handle S3 upload destination"""
    import boto3

    s3_client = boto3.client('s3')
    bucket_name = os.getenv('S3_REPORTS_BUCKET')

    # Upload to S3
    s3_key = f"reports/{administration}/{filename}"
    s3_client.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=content.encode('utf-8'),
        ContentType=content_type
    )

    # Generate presigned URL
    url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket_name, 'Key': s3_key},
        ExpiresIn=3600
    )

    return {
        'success': True,
        'destination': 's3',
        'url': url,
        'filename': filename,
        's3_key': s3_key,
        'message': f'Report uploaded to S3: {filename}'
    }
```

### Additional Output Formats

- PDF generation (using weasyprint or reportlab)
- Excel generation (using openpyxl)
- Email delivery (using AWS SES)

---

## Testing

Run unit tests:

```bash
cd backend
python -m pytest tests/unit/test_output_service.py -v
```

All 11 tests passing ✅

---

## Related Documentation

- **Railway Migration Tasks**: `.kiro/specs/Common/Railway migration/TASKS.md`
- **Template Service**: `backend/src/services/template_service.py`
- **Google Drive Service**: `backend/src/google_drive_service.py`
- **Report Generators**: `backend/src/report_generators/`

---

## Changelog

### January 2026

- ✅ Created OutputService with download, gdrive, and s3 (placeholder) support
- ✅ Updated 4 report endpoints to support output_destination parameter
- ✅ Created comprehensive unit tests (11 tests, all passing)
- ✅ Implemented automatic Reports folder creation per tenant
- ✅ Added timestamp handling for duplicate filenames
- ✅ Documented implementation and usage

---

## Notes

- Default behavior is unchanged (download) for backward compatibility
- Frontend changes are required to use new gdrive/s3 destinations
- S3 implementation is a placeholder and will raise NotImplementedError
- All endpoints maintain backward compatibility with existing frontend code
