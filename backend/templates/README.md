# Templates Folder

This folder contains templates for various file types used by the application.

## Structure

```
templates/
├── xlsx/           # Excel templates
│   └── template.xlsx
├── email/          # Email templates
└── pdf/            # PDF templates
```

## XLSX Templates

### template.xlsx

Used by `xlsx_export.py` for generating Excel reports.

**Location:** `backend/templates/xlsx/template.xlsx`

**Usage:**

```python
from xlsx_export import XLSXExportProcessor

processor = XLSXExportProcessor()
# Uses template.xlsx automatically
```

**Features:**

- Pre-formatted sheets
- Standard styling
- Column headers

## Email Templates

Email templates for notifications and reports.

**Location:** `backend/templates/email/`

## PDF Templates

PDF templates for invoices and reports.

**Location:** `backend/templates/pdf/`

## Adding New Templates

1. Place template file in appropriate subfolder
2. Update code to reference new template path
3. Document template usage in this README

---

**Last Updated:** January 21, 2026
