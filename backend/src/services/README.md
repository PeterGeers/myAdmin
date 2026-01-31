# Services Package

This package contains business logic services for the myAdmin application.

## Services Overview

- **CredentialService**: Secure storage and retrieval of tenant-specific credentials using AES-256 encryption
- **TemplateService**: XML template management with flexible field mappings and multi-format output generation
- **GoogleDriveService**: Tenant-specific Google Drive integration for file storage and retrieval

---

## CredentialService

The `CredentialService` provides secure storage and retrieval of tenant-specific credentials using AES-256 encryption.

**Documentation**: See `IMPLEMENTATION_SUMMARY.md` for detailed implementation information.

### Quick Start

```python
from database import DatabaseManager
from services.credential_service import CredentialService

# Initialize
db = DatabaseManager()
service = CredentialService(db)

# Store credentials
service.store_credential("GoodwinSolutions", "google_drive", {
    "client_id": "123.apps.googleusercontent.com",
    "client_secret": "secret_key"
})

# Retrieve credentials
creds = service.get_credential("GoodwinSolutions", "google_drive")
```

For detailed documentation, see `IMPLEMENTATION_SUMMARY.md`.

---

## TemplateService

The `TemplateService` manages XML templates with flexible field mappings and multi-format output generation.

**Documentation**: See `TEMPLATE_SERVICE_DOCUMENTATION.md` for complete documentation.

### Quick Start

```python
from database import DatabaseManager
from services.template_service import TemplateService

# Initialize
db = DatabaseManager()
template_service = TemplateService(db)

# Get template metadata
metadata = template_service.get_template_metadata('GoodwinSolutions', 'financial_report')

# Fetch template from Google Drive
template_xml = template_service.fetch_template_from_drive(
    metadata['template_file_id'],
    'GoodwinSolutions'
)

# Apply field mappings
data = {'company_name': 'Goodwin Solutions', 'total_revenue': 150000.00}
processed = template_service.apply_field_mappings(
    template_xml,
    data,
    metadata['field_mappings']
)

# Generate output
html_output = template_service.generate_output(processed, data, 'html')
```

### Features

- ✅ Database-backed template configuration
- ✅ Flexible field mapping with nested data support
- ✅ Multiple formatting types (currency, date, number, text)
- ✅ Value transformations (abs, round, uppercase, lowercase)
- ✅ Conditional logic support
- ✅ Multi-format output (HTML, XML, Excel*, PDF*)

\*Excel and PDF generation are placeholders for Phase 2.5

---

## GoogleDriveService

The `GoogleDriveService` provides tenant-specific Google Drive integration.

**Documentation**: See `GOOGLE_DRIVE_UPDATE_SUMMARY.md` for implementation details.

### Quick Start

```python
from google_drive_service import GoogleDriveService

# Initialize with tenant
drive_service = GoogleDriveService('GoodwinSolutions')

# List folders
folders = drive_service.list_subfolders('parent_folder_id')

# Upload file
file_id = drive_service.upload_file('local_file.pdf', 'folder_id')
```

---

## Documentation Index

- `IMPLEMENTATION_SUMMARY.md` - CredentialService implementation details
- `TEMPLATE_SERVICE_DOCUMENTATION.md` - Complete TemplateService documentation
- `GOOGLE_DRIVE_UPDATE_SUMMARY.md` - GoogleDriveService database integration
- `README.md` - This file (overview and quick start)

---

## Testing

Run all service tests:

```bash
# Unit tests
pytest backend/tests/unit/test_credential_service.py -v
pytest backend/tests/unit/test_template_service.py -v
pytest backend/tests/unit/test_google_drive.py -v

# Integration tests
pytest backend/tests/integration/ -v
```
