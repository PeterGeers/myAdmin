# Template System - Implementation Summary

**Date**: January 31, 2026  
**Status**: Architecture Defined, Implementation In Progress

---

## What Was Decided

After analysis and discussion, we've defined a **hybrid template architecture** that balances simplicity with flexibility.

### Key Architectural Decisions:

1. **TemplateService remains simple** - Only handles `{{ placeholder }}` replacement
2. **Complex sections pre-generated** - Hierarchical data (like table rows) generated in `report_generators/` module
3. **Clear separation** - HTML Reports (customizable) vs Official Tax Forms (XBRL, not customizable)
4. **Flexible output** - User chooses: download, save to Google Drive, or save to S3

---

## Template Types

### HTML Reports (For Viewing/Analysis)

**Purpose**: Internal use - view, analyze, print, share  
**Format**: HTML (human-readable)  
**Customizable**: Yes - tenants can customize layout, CSS, branding  
**Storage**: Tenant's Google Drive

**Examples**:

- ✅ Aangifte IB HTML Report (hierarchical view of income/expenses) - **COMPLETED**
- ✅ STR Invoices NL/UK (rental invoices with logos) - **COMPLETED**
- ⏸️ BTW Aangifte HTML Report (VAT calculations and breakdowns)
- ⏸️ Toeristenbelasting HTML Report (tourist tax calculations)

### Official Tax Forms (For Submission)

**Purpose**: Submit to Belastingdienst (Dutch Tax Authorities)  
**Format**: XML/XBRL (machine-readable)  
**Customizable**: NO - must match official schema exactly  
**Storage**: Same template for all tenants

**Examples**:

- ⏸️ IB Aangifte XBRL (official income tax return)
- ⏸️ BTW Aangifte XBRL (official VAT return)
- ⏸️ Toeristenbelasting XML (official tourist tax, if exists)

### XLSX Reports

**Purpose**: Financial reports with formulas and formatting  
**Format**: Excel (XLSX)  
**Customizable**: Yes - template stored per tenant  
**Generation**: Uses openpyxl for cell manipulation

**Examples**:

- ⏸️ Financial Reports (Actuals, Mutaties, etc.)

---

## Architecture Pattern

### For Simple Templates (Direct Placeholder Replacement)

```python
# Example: STR Invoice
data = {
    'invoice_number': 'INV-2026-001',
    'customer_name': 'John Doe',
    'amount': '€ 1,234.56',
    'date': '31-01-2026'
}

html = template_service.apply_field_mappings(template, data, mappings)
```

### For Complex Templates (Pre-Generation + Placeholder Replacement)

```python
# Example: Aangifte IB HTML Report
from report_generators import generate_aangifte_ib_table_rows

# 1. Query data
report_data = cache.query_aangifte_ib(year, administration)

# 2. Pre-generate complex sections
table_rows = generate_aangifte_ib_table_rows(
    report_data, cache, year, administration, user_tenants
)

# 3. Prepare template data
data = {
    'year': year,
    'administration': administration,
    'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'table_rows': table_rows  # Pre-generated HTML
}

# 4. Apply template
html = template_service.apply_field_mappings(template, data, mappings)
```

---

## Module Structure

```
backend/
├── src/
│   ├── services/
│   │   └── template_service.py          # Generic template handling
│   └── report_generators/               # NEW MODULE
│       ├── __init__.py                  # Export functions
│       ├── common_formatters.py         # Shared utilities
│       └── aangifte_ib_generator.py     # Aangifte IB specific logic
└── templates/
    ├── html/                            # HTML report templates
    │   └── aangifte_ib_template.html
    ├── xml/                             # XBRL/XML tax forms
    └── xlsx/                            # Excel templates
```

---

## Current Implementation Status

### ✅ Completed

1. **Database Schema** - `tenant_template_config` table created
2. **TemplateService** - Simple placeholder replacement working
3. **Aangifte IB HTML Template** - Created with `{{ table_rows }}` placeholder at `backend/templates/html/aangifte_ib_template.html`
4. **Aangifte IB Generator** - Implemented `generate_table_rows()` function in `backend/src/report_generators/aangifte_ib_generator.py`
5. **Aangifte IB Field Mappings** - Documented at `backend/templates/html/aangifte_ib_field_mappings.json`
6. **STR Invoice Templates** - Created NL and EN templates at `backend/templates/html/str_invoice_{nl|en}_template.html`
7. **STR Invoice Generator** - Implemented in `backend/src/report_generators/str_invoice_generator.py`
8. **STR Invoice Field Mappings** - Documented at `backend/templates/html/STR_INVOICE_FIELD_MAPPINGS.md`
9. **STR Invoice Routes Updated** - Modified `backend/src/str_invoice_routes.py` to use template-based approach
10. **Unit Tests** - Created comprehensive tests for STR invoice generator (12 tests, all passing)
11. **IB Aangifte XBRL Placeholder** - Created placeholder template at `backend/templates/xml/ib_aangifte_xbrl_template.xml` (requires official schema)
12. **Architecture Analysis** - Documented in `.kiro/specs/Common/templates/analysis.md`
13. **Documentation Updates** - IMPACT_ANALYSIS_SUMMARY.md, TASKS.md, README.md updated

### 🔄 In Progress

1. **End-to-End Testing** - Need to test STR invoices with real data from both tenants

### ⏸️ Not Started

1. **Other HTML Reports** - BTW Aangifte HTML, Toeristenbelasting HTML
2. **Official Tax Forms** - IB Aangifte XBRL, BTW Aangifte XBRL
3. **XLSX Templates** - Financial reports with openpyxl
4. **Template Preview API** - Preview-and-approve workflow for tenant admins
5. **Template Management UI** - Frontend for uploading/configuring templates

---

## Files Created/Modified

### Created:

- ✅ `backend/templates/html/aangifte_ib_template.html` - HTML report template with placeholders
- ✅ `backend/templates/html/aangifte_ib_field_mappings.json` - Field mappings for HTML report
- ✅ `backend/templates/html/str_invoice_nl_template.html` - Dutch STR invoice template
- ✅ `backend/templates/html/str_invoice_en_template.html` - English STR invoice template
- ✅ `backend/templates/html/STR_INVOICE_FIELD_MAPPINGS.md` - STR invoice field mappings documentation
- ✅ `backend/src/report_generators/__init__.py` - Report generators module
- ✅ `backend/src/report_generators/common_formatters.py` - Shared formatting utilities
- ✅ `backend/src/report_generators/aangifte_ib_generator.py` - Aangifte IB HTML generator
- ✅ `backend/src/report_generators/str_invoice_generator.py` - STR invoice HTML generator
- ✅ `backend/src/report_generators/README.md` - Module documentation
- ✅ `backend/tests/unit/test_common_formatters.py` - Unit tests for formatters (73 tests)
- ✅ `backend/tests/unit/test_str_invoice_generator.py` - Unit tests for STR invoice generator (12 tests)
- ✅ `backend/templates/xml/ib_aangifte_xbrl_template.xml` - XBRL placeholder template (requires official schema)
- ✅ `backend/templates/xml/IB_AANGIFTE_XBRL_README.md` - XBRL documentation and requirements
- ✅ `.kiro/specs/Common/templates/analysis.md` - Architecture analysis document
- ✅ `.kiro/specs/Common/templates/issues.md` - Original issues document

### Modified:

- ✅ `.kiro/specs/Common/Railway migration/TASKS.md` - Added detailed subtasks and marked STR invoice task complete
- ✅ `.kiro/specs/Common/Railway migration/IMPACT_ANALYSIS_SUMMARY.md` - Updated template approach
- ✅ `backend/templates/README.md` - Updated with new structure and architecture
- ✅ `backend/templates/xml/IMPLEMENTATION_SUMMARY.md` - This file
- ✅ `backend/src/str_invoice_routes.py` - Updated to use template-based approach with generator
- ✅ `backend/src/app.py` - Updated `aangifte_ib_export()` route to use generator + TemplateService

### To Be Created:

- ⏸️ `backend/src/report_generators/ib_aangifte_xbrl_generator.py` - For XBRL tax form (when official schema obtained)

### Deleted:

- ✅ `backend/templates/xml/AANGIFTE_IB_TEMPLATE_README.md` - Was incorrect (talked about XML for HTML report)

---

## Next Steps

1. ✅ Create `backend/src/report_generators/` module structure - **COMPLETED**
2. ✅ Implement `aangifte_ib_generator.py` with `generate_table_rows()` function - **COMPLETED**
3. ✅ Implement `str_invoice_generator.py` with invoice generation functions - **COMPLETED**
4. ✅ Update `backend/src/app.py` route to use generator + TemplateService - **COMPLETED**
5. ✅ Update `backend/src/str_invoice_routes.py` to use template-based approach - **COMPLETED**
6. Test end-to-end with real data for both Aangifte IB and STR invoices
7. Document the pattern for future report implementations
8. Implement remaining HTML reports (BTW Aangifte, Toeristenbelasting)
9. Obtain official XBRL schemas and implement tax form generators

---

## Related Documentation

- `.kiro/specs/Common/templates/analysis.md` - Detailed architecture analysis
- `.kiro/specs/Common/Railway migration/IMPACT_ANALYSIS_SUMMARY.md` - Overall migration plan
- `.kiro/specs/Common/Railway migration/TASKS.md` - Detailed task breakdown
- `backend/src/services/template_service.py` - TemplateService implementation
- `backend/templates/README.md` - Template folder structure and usage

---

**Last Updated:** January 31, 2026
