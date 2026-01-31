# XLSX Financial Report Field Mappings

## Template Type

- **Template Type ID**: `financial_report_xlsx`
- **Sheet Name**: `data`

## Configuration Fields

Stored in `tenant_template_config.field_mappings` JSON:

| Field Name         | Type   | Description                     | Example                                                       |
| ------------------ | ------ | ------------------------------- | ------------------------------------------------------------- |
| `template_path`    | string | Path to Excel template file     | "C:\\Users\\peter\\OneDrive\\Admin\\templates\\template.xlsx" |
| `output_base_path` | string | Base directory for output files | "C:\\Users\\peter\\OneDrive\\Admin\\reports"                  |

## Data Source

- **SQL Query**: `make_ledgers()` method in `backend/src/xlsx_export.py`
- **View**: `vw_mutaties`
- **Sheet**: Replaces "data" sheet in template

## Configuration Example

```json
{
  "template_path": "C:\\Users\\peter\\OneDrive\\Admin\\templates\\template.xlsx",
  "output_base_path": "C:\\Users\\peter\\OneDrive\\Admin\\reports"
}
```

## Related Files

- **Processor**: `backend/src/xlsx_export.py`
- **Template**: `backend/templates/xlsx/template.xlsx`
