# Templates Folder

This folder contains templates for various file types used by the application.

## Structure

```
templates/
├── html/           # HTML report templates (customizable per tenant)
│   └── aangifte_ib_template.html
├── xml/            # XML/XBRL tax form templates (official schemas)
├── xlsx/           # Excel templates
│   └── template.xlsx
├── email/          # Email templates
└── pdf/            # PDF templates
```

## Template System Architecture

The application uses a **hybrid template approach**:

- **TemplateService** (`backend/src/services/template_service.py`) - Handles simple `{{ placeholder }}` replacement
- **report_generators/** (`backend/src/report_generators/`) - Pre-generates complex sections (like hierarchical table rows)
- **Template Storage** - Templates stored in tenant's Google Drive, metadata in `tenant_template_config` table

### Template Types

**HTML Reports** (Viewing/Analysis - Customizable per tenant):

- Aangifte IB HTML Report - Hierarchical income/expense view
- BTW Aangifte HTML Report - VAT calculations
- STR Invoices - Rental invoices with logos
- Toeristenbelasting HTML Report - Tourist tax calculations

**Official Tax Forms** (Submission to Belastingdienst - NOT customizable):

- IB Aangifte XBRL - Official income tax return XML
- BTW Aangifte XBRL - Official VAT return XML
- Must validate against official schemas

## HTML Templates

### aangifte_ib_template.html

Used for generating Aangifte IB (Income Tax Return) HTML reports.

**Location:** `backend/templates/html/aangifte_ib_template.html`

**Usage:**

```python
from report_generators import generate_aangifte_ib_table_rows

# 1. Generate complex sections
table_rows = generate_aangifte_ib_table_rows(data, cache, year, admin, user_tenants)

# 2. Prepare template data
template_data = {
    'year': year,
    'administration': administration,
    'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'table_rows': table_rows  # Pre-generated HTML
}

# 3. Apply template
html = template_service.apply_field_mappings(template, template_data, mappings)
```

**Features:**

- Hierarchical structure (Parent → Aangifte → Accounts)
- Pre-formatted CSS styling
- Customizable per tenant

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

### For HTML Reports (Customizable):

1. Create template file in `backend/templates/html/`
2. Use `{{ placeholder }}` syntax for simple fields
3. Create generator function in `backend/src/report_generators/` for complex sections
4. Update route handler to use generator + TemplateService
5. Store template in tenant's Google Drive
6. Add metadata to `tenant_template_config` table

### For Official Tax Forms (XBRL/XML):

1. Obtain official schema from Belastingdienst
2. Create XML template in `backend/templates/xml/`
3. Validate against official XSD schema
4. Use same template for all tenants (not customizable)

### For XLSX Templates:

1. Create Excel template with formatting
2. Use openpyxl/xlsxwriter for cell manipulation
3. Store template location in `tenant_template_config`
4. Generate using `report_generators/` module

---

**Last Updated:** January 31, 2026

**Related Documentation:**

- `.kiro/specs/Common/templates/analysis.md` - Template system architecture analysis
- `.kiro/specs/Common/Railway migration/IMPACT_ANALYSIS_SUMMARY.md` - Overall migration plan
- `backend/src/services/template_service.py` - Template service implementation
