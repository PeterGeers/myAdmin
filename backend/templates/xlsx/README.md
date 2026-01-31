# XLSX Financial Report Template Configuration

## Overview

The XLSX export functionality now supports configurable template and output paths per tenant, stored in the `tenant_template_config` database table.

## How It Works

### Before (Hardcoded)

```python
self.template_path = 'backend/templates/xlsx/template.xlsx'
self.output_base_path = r'C:\Users\peter\OneDrive\Admin\reports'
```

### After (Database-Configured)

```python
# Paths are retrieved from tenant_template_config table
template_path = self._get_template_path(administration)
output_base_path = self._get_output_base_path(administration)
```

## Configuration

### Database Structure

Paths are stored in the `field_mappings` JSON column:

```json
{
  "template_path": "C:\\path\\to\\template.xlsx",
  "output_base_path": "C:\\path\\to\\output",
  "configured_date": "2026-01-31"
}
```

### Configure Paths

Use the configuration script:

```bash
cd backend
python scripts/configure_xlsx_paths.py \
    --administration GoodwinSolutions \
    --template-path "C:\Users\peter\OneDrive\Admin\templates\template.xlsx" \
    --output-path "C:\Users\peter\OneDrive\Admin\reports"
```

### Manual Configuration

```sql
INSERT INTO tenant_template_config (
    administration,
    template_type,
    template_file_id,
    field_mappings,
    is_active
) VALUES (
    'GoodwinSolutions',
    'financial_report_xlsx',
    'local_file',
    '{"template_path": "C:\\\\path\\\\to\\\\template.xlsx", "output_base_path": "C:\\\\path\\\\to\\\\output"}',
    TRUE
);
```

## Behavior

### Template Path

- **Configured**: Uses path from database
- **Not configured**: Falls back to `backend/templates/xlsx/template.xlsx`
- **File not found**: Creates new workbook

### Output Path

- **Configured**: Uses path from database
- **Not configured**: Falls back to default path
- **Directory doesn't exist**: Creates it automatically

### Output Structure

```
{output_base_path}/
├── GoodwinSolutions2024/
│   ├── GoodwinSolutions2024.xlsx
│   ├── download_log.txt
│   └── {ReferenceNumber}/
│       └── {downloaded files}
└── PeterPrive2025/
    ├── PeterPrive2025.xlsx
    ├── download_log.txt
    └── {ReferenceNumber}/
        └── {downloaded files}
```

## Migration Path

### Current Setup (Local Development)

1. Keep using hardcoded paths (works as before)
2. No changes needed

### Future Setup (Railway/Production)

1. Configure paths per tenant in database
2. Each tenant can have different template/output locations
3. Supports Google Drive, S3, or local paths

## Example Configurations

### Local Development

```json
{
  "template_path": "C:\\Users\\peter\\OneDrive\\Admin\\templates\\template.xlsx",
  "output_base_path": "C:\\Users\\peter\\OneDrive\\Admin\\reports"
}
```

### Docker/Container

```json
{
  "template_path": "/app/templates/xlsx/template.xlsx",
  "output_base_path": "/app/reports"
}
```

### Google Drive (Future)

```json
{
  "template_file_id": "1a2b3c4d5e6f7g8h9i0j",
  "output_destination": "gdrive",
  "output_folder_id": "9i8h7g6f5e4d3c2b1a0"
}
```

## Testing

The existing functionality remains unchanged:

```python
# Works with or without configuration
processor = XLSXExportProcessor(test_mode=False)
results = processor.generate_xlsx_export(['GoodwinSolutions'], [2024])
```

## Related Files

- **Processor**: `backend/src/xlsx_export.py`
- **Configuration Script**: `backend/scripts/configure_xlsx_paths.py`
- **Template**: `backend/templates/xlsx/template.xlsx`
- **Tasks**: `.kiro/specs/Common/Railway migration/TASKS.md`
