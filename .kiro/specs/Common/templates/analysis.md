# Template System Analysis

**Date**: January 30, 2026  
**Status**: Analysis in Progress  
**Related**: `.kiro/specs/Common/templates/issues.md`

---

## Executive Summary

The template system implementation has revealed architectural questions about how to handle complex, hierarchical data structures (like Aangifte IB reports) within the existing TemplateService framework.

**Core Question**: How should the TemplateService handle hierarchical/repeating data structures while maintaining simplicity and tenant customizability?

---

## Current Architecture

### What We Have Built

#### 1. Database Schema ✅

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

**Status**: Created and tested locally

#### 2. TemplateService ✅

**Location**: `backend/src/services/template_service.py`

**Capabilities**:

- `get_template_metadata(administration, template_type)` - Fetch template config from DB
- `fetch_template_from_drive(file_id, administration)` - Download template from Google Drive
- `apply_field_mappings(template_xml, data, mappings)` - Replace `{{ placeholder }}` with data
- `generate_output(template, data, output_format)` - Generate HTML/XML/Excel/PDF

**Current Limitation**: Only supports simple placeholder replacement, not loops or hierarchical structures

#### 3. Template Format

- Uses `{{ placeholder }}` syntax
- Field mappings JSON defines data paths and formatting
- Supports: text, currency, date, number formatting
- Supports: transformations (abs, round, uppercase, lowercase)
- Supports: conditionals (show/hide based on values)

---

## The Challenge: Hierarchical Data

### Example: Aangifte IB Report

The Aangifte IB report has a 3-level hierarchy:

```
Parent (e.g., 4000)                     € 120,000.00
  └── Aangifte (e.g., "Omzet")          € 120,000.00
      ├── Account 4001 - Onkosten       €  26,349.54
      ├── Account 4010 - Toeristenb.    €   6,118.34
      └── Account 4025 - Computer       €   1,094.17
```

**Data Source**:

- `cache.query_aangifte_ib(year, admin)` → Parent + Aangifte summary
- `cache.query_aangifte_ib_details(year, admin, parent, aangifte, user_tenants)` → Account details

**Challenge**: How to generate this hierarchical HTML table using the TemplateService?

---

## Architectural Options

### Option 1: Pre-Generate Complex Sections ⭐ (RECOMMENDED)

**Approach**: Generate complex HTML sections (like table rows) in the route handler, pass as a single field to TemplateService.

**Template**:

```html
<tbody>
  {{ table_rows }}
</tbody>
```

**Route Handler**:

```python
# Generate table rows HTML
table_rows_html = ""
for parent_group in grouped_data:
    table_rows_html += f'<tr class="parent-row">...</tr>'
    for aangifte in parent_group.aangiftes:
        table_rows_html += f'<tr class="aangifte-row">...</tr>'
        for account in aangifte.accounts:
            table_rows_html += f'<tr class="account-row">...</tr>'

# Pass to TemplateService
data = {
    'year': 2025,
    'administration': 'GoodwinSolutions',
    'table_rows': table_rows_html  # Pre-generated HTML
}

html = template_service.apply_field_mappings(template, data, mappings)
```

**Pros**:

- ✅ Simple - no changes to TemplateService
- ✅ Works with existing architecture
- ✅ Template remains customizable (CSS, layout)
- ✅ Complex logic stays in Python (where it belongs)

**Cons**:

- ❌ Some HTML generation in route handler
- ❌ Less flexible for tenant customization of row structure

---

### Option 2: Extend TemplateService with Loop Support

**Approach**: Add loop/iteration support to TemplateService (like Jinja2).

**Template**:

```html
<tbody>
  {% for parent_group in grouped_data %}
  <tr class="parent-row">
    <td>{{ parent_group.parent }}</td>
    <td class="amount">{{ parent_group.total|format_currency }}</td>
  </tr>
  {% for aangifte in parent_group.aangiftes %}
  <tr class="aangifte-row">
    ...
  </tr>
  {% for account in aangifte.accounts %}
  <tr class="account-row">
    ...
  </tr>
  {% endfor %} {% endfor %} {% endfor %}
</tbody>
```

**Implementation**: Add loop parsing to `apply_field_mappings()` or integrate Jinja2.

**Pros**:

- ✅ Full flexibility in templates
- ✅ Tenant can customize row structure
- ✅ Clean separation of logic and presentation

**Cons**:

- ❌ Major change to TemplateService
- ❌ More complex template syntax
- ❌ Harder to validate templates
- ❌ Security concerns (template injection)

---

### Option 3: Use Jinja2 Template Engine

**Approach**: Replace custom TemplateService with Jinja2.

**Pros**:

- ✅ Industry-standard solution
- ✅ Full feature set (loops, conditionals, filters, macros)
- ✅ Well-documented and tested
- ✅ Security features built-in

**Cons**:

- ❌ Complete rewrite of TemplateService
- ❌ Different syntax from current `{{ placeholder }}`
- ❌ More complex for simple use cases
- ❌ Larger dependency

---

## Recommendation: Hybrid Approach

**Use Option 1 (Pre-Generate) for complex hierarchical data**  
**Keep TemplateService simple for standard use cases**

### Rationale:

1. **Simplicity**: TemplateService remains simple and maintainable
2. **Flexibility**: Complex logic in Python, simple formatting in templates
3. **Tenant Customization**: Tenants can still customize CSS, layout, headers, footers
4. **No Breaking Changes**: Works with existing architecture
5. **Future-Proof**: Can add Jinja2 later if needed

### Implementation Pattern:

```python
# Route Handler (app.py)
def generate_aangifte_ib_report():
    # 1. Query data from cache
    report_data = cache.query_aangifte_ib(year, administration)

    # 2. Generate complex sections (table rows)
    table_rows = generate_aangifte_ib_table_rows(
        report_data, year, administration, cache, user_tenants
    )

    # 3. Prepare data for template
    data = {
        'year': year,
        'administration': administration,
        'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'table_rows': table_rows  # Pre-generated HTML
    }

    # 4. Get template from Google Drive (or local)
    template_html = template_service.fetch_template_from_drive(
        file_id=metadata['template_file_id'],
        administration=administration
    )

    # 5. Apply field mappings (simple placeholder replacement)
    html = template_service.apply_field_mappings(
        template_html, data, metadata['field_mappings']
    )

    return html
```

**Helper Function** (separate module, not in TemplateService):

```python
# backend/src/report_generators/aangifte_ib_generator.py
def generate_aangifte_ib_table_rows(report_data, year, admin, cache, user_tenants):
    """Generate HTML table rows for Aangifte IB report"""
    rows = []
    # ... complex logic to generate hierarchical rows ...
    return ''.join(rows)
```

---

## Template Types and Complexity

### Simple Templates (Use TemplateService as-is)

- **STR Invoices**: Simple placeholders (name, address, amount, date)
- **Email Templates**: Simple placeholders (user name, link, message)
- **Simple Reports**: Summary data with simple placeholders

### Complex Templates - HTML Reports (Use Pre-Generation)

- **Aangifte IB HTML Report**: Hierarchical table (parent → aangifte → accounts) for viewing/analysis
- **Actuals Report**: Multi-level drill-down (year → quarter → month)
- **BTW Aangifte HTML Report**: Complex calculations and groupings for viewing/analysis

### Complex Templates - Official Tax Forms (Use TemplateService + Validation)

- **IB Aangifte XML**: Official income tax return XML for Belastingdienst (XBRL format)
- **BTW Aangifte XBRL**: Official VAT return XML for Belastingdienst (XBRL format)
- **Toeristenbelasting XML**: Tourist tax return XML (if official format exists)

**Note**: Tax form XMLs must validate against official Belastingdienst schemas and are NOT customizable per tenant.

---

## Important Distinction: Reports vs Tax Forms

### HTML Reports (For Viewing/Analysis)

**Purpose**: Internal use - view, analyze, print, share  
**Format**: HTML (human-readable)  
**Customizable**: Yes - tenants can customize layout, CSS, branding  
**Data**: Detailed breakdowns, all transactions  
**Validation**: None required

**Examples**:

- Aangifte IB HTML Report (hierarchical view of income/expenses)
- BTW Aangifte HTML Report (VAT calculations and breakdowns)
- Actuals Report (financial position with drill-down)

### Official Tax Forms (For Submission)

**Purpose**: Submit to Belastingdienst (Dutch Tax Authorities)  
**Format**: XML/XBRL (machine-readable)  
**Customizable**: NO - must match official schema exactly  
**Data**: Aggregated totals, specific form fields  
**Validation**: REQUIRED - must validate against official XSD schema

**Examples**:

- IB Aangifte XBRL (official income tax return)
- BTW Aangifte XBRL (official VAT return)
- Toeristenbelasting XML (official tourist tax return, if exists)

### Key Differences

| Aspect            | HTML Reports               | Tax Form XMLs             |
| ----------------- | -------------------------- | ------------------------- |
| **Audience**      | Business owner, accountant | Tax authorities           |
| **Purpose**       | Analysis, record-keeping   | Official filing           |
| **Format**        | HTML                       | XML/XBRL                  |
| **Structure**     | Flexible, hierarchical     | Fixed, flat form fields   |
| **Customization** | Per tenant                 | None (official format)    |
| **Validation**    | Optional                   | Required (XSD schema)     |
| **Storage**       | Google Drive or download   | Submit to Belastingdienst |
| **Template Type** | `aangifte_ib_html_report`  | `ib_aangifte_xbrl`        |

### In the Database

```sql
-- HTML Report Template
INSERT INTO tenant_template_config (
    administration,
    template_type,
    template_file_id
) VALUES (
    'GoodwinSolutions',
    'aangifte_ib_html_report',  -- Customizable per tenant
    'google_drive_file_id_123'
);

-- Tax Form Template (same for all tenants)
INSERT INTO tenant_template_config (
    administration,
    template_type,
    template_file_id
) VALUES (
    'GoodwinSolutions',
    'ib_aangifte_xbrl',  -- Official format, not customizable
    'google_drive_file_id_456'  -- Same template for all tenants
);
```

---

## Concerns Addressed

### 1. XML vs HTML Templates

**Answer**: Support both. Template format is determined by file extension and content.

- `.html` templates → HTML output
- `.xml` templates → XML output
- TemplateService is format-agnostic (just string replacement)

### 2. Simple Variable Limitation

**Answer**: For complex data, pre-generate sections and pass as single variable.

- Simple data: Direct placeholder replacement
- Complex data: Pre-generate HTML/XML, pass as `{{ complex_section }}`

### 3. Hierarchical Data Handling

**Answer**: Pre-generate in route handler, pass to TemplateService.

- Keeps TemplateService simple
- Complex logic in Python (testable, maintainable)
- Template remains customizable (CSS, layout)

### 4. Helper Functions vs TemplateService

**Answer**: Helper functions are OK, but separate from TemplateService.

- TemplateService: Generic template handling (fetch, apply mappings, generate output)
- Helper Functions: Report-specific logic (generate table rows, calculate totals)
- Location: `backend/src/report_generators/` (not in services/)

---

## Storage Locations

### Templates

**Storage**: Tenant's Google Drive (per tenant customization)
**Metadata**: `tenant_template_config` table (file_id, field_mappings)
**Fallback**: Local templates in `backend/templates/` for defaults

### Generated Reports (HTML/PDF)

**Option 1**: Return to frontend (user downloads)
**Option 2**: Store in tenant's Google Drive (for record keeping)
**Option 3**: Temporary local storage (auto-cleanup after 24h)

**Recommendation**: Option 1 (return to frontend) + Option 2 (optional save to Drive)

### XLSX Exports

**Current**: Local storage at `C:\Users\peter\OneDrive\Admin\reports\{admin}{year}\`
**Future**:

- Railway: `/app/reports/` (container storage)
- Option to save to tenant's Google Drive
- Option to download directly

### Invoice Files (from Google Drive)

**Current**: Downloaded to local storage alongside XLSX
**Future**:

- Keep in Google Drive (reference by URL)
- Download on-demand when needed
- Optional: Copy to tenant's archive folder

---

## Next Steps

### Immediate (Complete Current Task)

1. ✅ Keep template simple with `{{ table_rows }}` placeholder
2. ✅ Create helper function to generate table rows HTML
3. ✅ Update route handler to use helper + TemplateService
4. ✅ Test with real data
5. ✅ Document the pattern

### Short-Term (Other Templates)

1. **STR Invoices** - Simple template (no pre-generation needed)
2. **Aangifte IB HTML Report** - HTML report for viewing (DONE - needs testing)
3. **BTW Aangifte HTML Report** - HTML report for viewing (may need pre-generation)
4. **BTW Aangifte XBRL** - Official VAT return XML for Belastingdienst
5. **Toeristenbelasting HTML Report** - HTML report for viewing
6. **Toeristenbelasting XML** - Official tourist tax XML (if format exists)
7. **IB Aangifte XBRL** - Official income tax return XML for Belastingdienst

### Long-Term (Enhancements)

1. Consider Jinja2 integration if many complex templates
2. Add template validation
3. Add template preview functionality
4. Build template editor UI for tenant administrators

---

## Conclusion

**Recommended Approach**: Hybrid model

- TemplateService handles simple placeholder replacement
- Complex sections pre-generated in route handlers
- Helper functions in separate module (`report_generators/`)
- Templates remain customizable (CSS, layout, simple fields)

**This approach**:

- ✅ Works with existing architecture
- ✅ Keeps TemplateService simple
- ✅ Allows tenant customization
- ✅ Handles complex hierarchical data
- ✅ Maintainable and testable
- ✅ No breaking changes

---

## Files to Review/Update

1. `.kiro/specs/Common/Railway migration/IMPACT_ANALYSIS_SUMMARY.md` - Update template approach
2. `.kiro/specs/Common/Railway migration/TASKS.md` - Clarify template tasks
3. `backend/src/services/template_service.py` - Keep as-is (simple)
4. `backend/templates/html/aangifte_ib_template.html` - Simple template with placeholders
5. `backend/src/report_generators/` - NEW: Create helper functions here

---

## Questions for Discussion

1. ✅ **Agreed on hybrid approach?** (Pre-generate complex sections)
2. ✅ **Where to store helper functions?** Create `backend/src/report_generators/` module for report-specific generation logic (NOT in services/). This module will contain report generators that pre-generate complex sections (like hierarchical table rows) before passing to TemplateService.
3. ✅ **Storage strategy for generated reports?** Provide user option to choose output destination:
   - **Download to local filesystem**: Return report to frontend for immediate download
   - **Upload to Google Drive**: Save to tenant's Google Drive folder
   - **Upload to S3**: Save to tenant's S3 bucket (future option)

   Implementation: Add `output_destination` parameter to report generation endpoints with values: `download`, `gdrive`, or `s3`.

4. ✅ **XLSX export integration?** Use hybrid approach:
   - **Template metadata storage**: Use TemplateService to store XLSX template location (file_id in Google Drive/S3)
   - **Generation logic**: Keep separate in `report_generators/` module (XLSX generation uses different libraries like openpyxl/xlsxwriter, not simple placeholder replacement)
   - **Workflow**:
     1. TemplateService retrieves XLSX template file location from database
     2. Report generator fetches template, populates data using openpyxl
     3. Generated file saved to chosen destination (download/gdrive/s3)

   **Rationale**: XLSX templates require cell-level manipulation (formulas, formatting, multiple sheets) which is fundamentally different from HTML/XML placeholder replacement. Keeping generation logic separate maintains clean separation of concerns while still leveraging TemplateService for metadata management.

5. ✅ **Template validation?** Implement preview-and-approve workflow:
   - **Template Preview API**: Create endpoint `/api/tenant-admin/templates/preview` that:
     1. Accepts uploaded template + field mappings
     2. Fetches sample data from database (e.g., most recent report data)
     3. Generates example output using the template
     4. Returns preview to frontend for review
   - **Approval Flow**:
     1. Tenant Admin uploads template
     2. System generates preview with real sample data
     3. Admin reviews preview in UI
     4. Admin approves → template saved to Google Drive + metadata stored in database
     5. Admin rejects → can modify and try again
   - **Validation Checks**:
     - Syntax validation (HTML/XML well-formed)
     - Placeholder validation (all required placeholders present)
     - Sample data rendering (no errors during generation)

   **Benefits**: Prevents broken templates from being activated, gives tenant admins confidence their customizations work correctly.
