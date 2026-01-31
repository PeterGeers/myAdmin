# Template Field Mappings Index

This document provides an index of all template field mapping documentation in the system.

**Last Updated**: January 31, 2026

---

## Overview

Field mapping documentation describes the structure, placeholders, data sources, and formatting rules for each template type in the system. These documents are essential for:

- Understanding template structure and requirements
- Customizing templates per tenant
- Integrating new data sources
- Troubleshooting template issues
- Maintaining consistency across reports

---

## HTML Report Templates

HTML templates are **customizable per tenant** and stored in tenant-specific Google Drive folders.

### 1. Aangifte IB (Income Tax) Report

**Purpose**: Hierarchical view of income and expenses for tax reporting

**Documentation**: [`html/AANGIFTE_IB_FIELD_MAPPINGS.md`](html/AANGIFTE_IB_FIELD_MAPPINGS.md)

**Template Type ID**: `aangifte_ib_html`

**Key Features**:

- Three-level hierarchy (Parent → Aangifte → Account)
- Automatic RESULTAAT calculation (P&L accounts only)
- Grand total verification
- Tenant isolation with security filtering

**Fields**:

- `year` - Report year
- `administration` - Tenant identifier
- `generated_date` - Generation timestamp
- `table_rows` - Pre-generated hierarchical HTML rows

**Generator**: `backend/src/report_generators/aangifte_ib_generator.py`

---

### 2. BTW Aangifte (VAT Declaration) Report

**Purpose**: VAT calculations and breakdowns for quarterly tax filing

**Documentation**: [`html/BTW_AANGIFTE_FIELD_MAPPINGS.md`](html/BTW_AANGIFTE_FIELD_MAPPINGS.md)

**Template Type ID**: `btw_aangifte_html`

**Key Features**:

- Balance data (accounts 2010, 2020, 2021)
- Quarter-specific data
- Automatic VAT calculations
- Payment instructions (te betalen/ontvangen)

**Fields**:

- `administration`, `year`, `quarter`, `end_date`
- `balance_rows` - Balance account data
- `quarter_rows` - Quarter-specific data
- `payment_instruction`, `received_btw`, `prepaid_btw`

**Generator**: `backend/src/report_generators/btw_aangifte_generator.py`

---

### 3. STR Invoice (Short-Term Rental)

**Purpose**: Professional invoices for short-term rental bookings

**Documentation**: [`html/STR_INVOICE_FIELD_MAPPINGS.md`](html/STR_INVOICE_FIELD_MAPPINGS.md)

**Template Type ID**: `str_invoice_nl` or `str_invoice_en`

**Key Features**:

- Multi-language support (Dutch/English)
- Conditional line items (VAT, tourist tax)
- Company branding and logo
- Booking channel integration

**Fields**:

- Company info: `company_name`, `company_address`, `company_vat`, etc.
- Booking info: `reservationCode`, `guestName`, `checkinDate`, etc.
- Financial: `net_amount`, `vat_amount`, `tourist_tax`, `amountGross`
- `table_rows` - Dynamic invoice line items

**Generator**: `backend/src/report_generators/str_invoice_generator.py`

---

### 4. Toeristenbelasting (Tourist Tax) Report

**Purpose**: Tourist tax declaration for short-term rental properties

**Documentation**: [`html/TOERISTENBELASTING_FIELD_MAPPINGS.md`](html/TOERISTENBELASTING_FIELD_MAPPINGS.md)

**Template Type ID**: `toeristenbelasting_html`

**Key Features**:

- Rental statistics (nights, occupancy rates)
- Financial data (tourist tax, revenue, fees)
- Taxable revenue calculation
- Next year projection

**Fields**:

- Basic: `year`, `next_year`, `datum`
- Contact: `functie`, `telefoonnummer`, `email`, `naam`, `plaats`
- Period: `periode_van`, `periode_tm`, `aantal_kamers`, `aantal_slaapplaatsen`
- Statistics: `totaal_verhuurde_nachten`, `kamerbezettingsgraad`, etc.
- Financial: `saldo_toeristenbelasting`, `belastbare_omzet_logies`, etc.

**Generator**: `backend/src/report_generators/toeristenbelasting_generator.py`

---

## Excel Report Templates

Excel templates are **configurable per tenant** with customizable paths and formatting.

### 5. Financial Report XLSX

**Purpose**: Comprehensive financial report with all transactions and beginning balances

**Documentation**: [`xlsx/FIELD_MAPPINGS.md`](xlsx/FIELD_MAPPINGS.md)

**Template Type ID**: `financial_report_xlsx`

**Key Features**:

- Beginning balance calculation
- Complete transaction history
- Professional Excel formatting
- Optional document downloads from Google Drive

**Configuration Fields**:

- `template_path` - Path to Excel template
- `output_base_path` - Output directory

**Data Fields** (per row):

- Transaction: `TransactionNumber`, `TransactionDate`, `TransactionDescription`, `Amount`
- Account: `Reknum`, `AccountName`, `Parent`, `Administration`
- Classification: `VW`, `jaar`, `kwartaal`, `maand`, `week`
- References: `ReferenceNumber`, `DocUrl`, `Document`

**Processor**: `backend/src/xlsx_export.py`

---

## XML/XBRL Templates

Official tax forms that **must validate against government schemas** and are **NOT customizable**.

### 6. IB Aangifte XBRL (Income Tax Return)

**Status**: Moved to separate specification

**Documentation**: `.kiro/specs/FIN/AANGIFTE_XBRL/README.md`

**Note**: Implementation planned post-Railway migration

---

### 7. BTW Aangifte XBRL (VAT Return)

**Status**: Moved to separate specification

**Documentation**: `.kiro/specs/FIN/AANGIFTE_XBRL/README.md`

**Note**: Implementation planned post-Railway migration

---

## Template Categories

### Customizable Templates (HTML/XLSX)

These templates can be customized per tenant:

- ✅ Company branding (logos, colors, fonts)
- ✅ Custom fields and sections
- ✅ Language selection
- ✅ Formatting preferences
- ✅ Storage location (Google Drive, S3, local)

**Storage**: Tenant-specific Google Drive folders or configured paths

**Metadata**: `tenant_template_config` table

### Official Templates (XBRL/XML)

These templates must conform to government schemas:

- ❌ No customization allowed
- ❌ Must validate against official XSD schemas
- ✅ Same template for all tenants
- ✅ Automatic validation before submission

**Storage**: Application templates folder

**Validation**: XSD schema validation required

---

## Database Schema

All template metadata is stored in the `tenant_template_config` table:

```sql
CREATE TABLE tenant_template_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    template_file_id VARCHAR(255) NOT NULL,
    field_mappings JSON,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_template (administration, template_type),
    INDEX idx_tenant (administration)
);
```

**Template Types**:

- `aangifte_ib_html`
- `btw_aangifte_html`
- `str_invoice_nl`
- `str_invoice_en`
- `toeristenbelasting_html`
- `financial_report_xlsx`

---

## Common Patterns

### Placeholder Syntax

All templates use double curly brace syntax:

```html
{{ field_name }}
```

Example:

```html
<h1>Report for {{ year }}</h1>
<p>Administration: {{ administration }}</p>
```

### Pre-Generated Sections

Complex sections (like hierarchical tables) are pre-generated by report generators:

```python
# Generator creates HTML/data structure
table_rows = generator.generate_table_rows(data, cache, year, admin, tenants)

# Template receives pre-generated content
template_data = {
    'year': year,
    'table_rows': table_rows  # Already formatted
}
```

### Common Formatters

All generators use shared formatting functions from `common_formatters.py`:

- `format_currency(amount)` - Format with € symbol
- `format_amount(amount)` - Format without currency symbol
- `format_date(date, format)` - Format dates
- `escape_html(text)` - Prevent XSS attacks
- `safe_float(value)` - Safe numeric conversion

---

## Template Service

The `TemplateService` class handles template loading and placeholder replacement:

```python
from services.template_service import TemplateService

service = TemplateService()

# Load template from Google Drive or local file
template = service.load_template(
    administration='GoodwinSolutions',
    template_type='aangifte_ib_html'
)

# Apply field mappings
output = service.apply_template(
    template_content=template,
    data=template_data
)
```

**Location**: `backend/src/services/template_service.py`

---

## Report Generators

Report generators transform raw data into template-ready structures:

**Location**: `backend/src/report_generators/`

**Modules**:

- `aangifte_ib_generator.py` - Aangifte IB reports
- `btw_aangifte_generator.py` - BTW Aangifte reports
- `str_invoice_generator.py` - STR invoices
- `toeristenbelasting_generator.py` - Tourist tax reports
- `common_formatters.py` - Shared formatting utilities

**Pattern**:

```python
from report_generators import aangifte_ib_generator

# Generate structured data
report_data = aangifte_ib_generator.generate_table_rows(
    report_data=raw_data,
    cache=cache,
    year=2025,
    administration='GoodwinSolutions',
    user_tenants=['GoodwinSolutions']
)

# Apply to template
template_data = {
    'year': 2025,
    'table_rows': report_data
}
```

---

## Testing

Each template type has corresponding unit tests:

**Location**: `backend/tests/unit/`

**Test Files**:

- `test_aangifte_ib_generator.py`
- `test_btw_aangifte_generator.py`
- `test_str_invoice_generator.py`
- `test_toeristenbelasting_generator.py`
- `test_common_formatters.py`

**Test Pattern**:

```python
def test_generate_report():
    # Arrange
    data = create_sample_data()

    # Act
    result = generator.generate_report(data, cache, year, admin)

    # Assert
    assert result['success'] == True
    assert 'table_rows' in result
    assert len(result['table_rows']) > 0
```

---

## Migration Notes

### Phase 2.3 Status

All HTML templates have been converted and documented:

- ✅ Aangifte IB HTML Report
- ✅ BTW Aangifte HTML Report
- ✅ STR Invoices (NL/EN)
- ✅ Toeristenbelasting HTML Report
- ✅ Financial Report XLSX

### Remaining Work

- [ ] Upload templates to tenant Google Drive folders (Phase 2.4)
- [ ] Implement template preview and validation (Phase 2.6)
- [ ] XBRL tax forms (separate specification, post-Railway migration)

---

## Related Documentation

- **Template System Architecture**: `.kiro/specs/Common/templates/analysis.md`
- **Railway Migration Plan**: `.kiro/specs/Common/Railway migration/IMPACT_ANALYSIS_SUMMARY.md`
- **Railway Migration Tasks**: `.kiro/specs/Common/Railway migration/TASKS.md`
- **Template Service**: `backend/src/services/template_service.py`
- **Report Generators**: `backend/src/report_generators/README.md`
- **XBRL Specification**: `.kiro/specs/FIN/AANGIFTE_XBRL/README.md`

---

## Quick Reference

| Template Type           | Documentation                               | Generator                         | Template File                           |
| ----------------------- | ------------------------------------------- | --------------------------------- | --------------------------------------- |
| Aangifte IB HTML        | `html/AANGIFTE_IB_FIELD_MAPPINGS.md`        | `aangifte_ib_generator.py`        | `html/aangifte_ib_template.html`        |
| BTW Aangifte HTML       | `html/BTW_AANGIFTE_FIELD_MAPPINGS.md`       | `btw_aangifte_generator.py`       | `html/btw_aangifte_template.html`       |
| STR Invoice NL          | `html/STR_INVOICE_FIELD_MAPPINGS.md`        | `str_invoice_generator.py`        | `html/str_invoice_nl_template.html`     |
| STR Invoice EN          | `html/STR_INVOICE_FIELD_MAPPINGS.md`        | `str_invoice_generator.py`        | `html/str_invoice_en_template.html`     |
| Toeristenbelasting HTML | `html/TOERISTENBELASTING_FIELD_MAPPINGS.md` | `toeristenbelasting_generator.py` | `html/toeristenbelasting_template.html` |
| Financial Report XLSX   | `xlsx/FIELD_MAPPINGS.md`                    | `xlsx_export.py`                  | `xlsx/template.xlsx`                    |

---

**For questions or updates, refer to the individual field mapping documents linked above.**
