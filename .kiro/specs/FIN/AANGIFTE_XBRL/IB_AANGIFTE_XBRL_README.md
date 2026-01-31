# IB Aangifte XBRL Template

**Template Type**: `ib_aangifte_xbrl`  
**Purpose**: Official Income Tax Return XML for submission to Belastingdienst  
**Format**: XBRL (eXtensible Business Reporting Language)  
**Status**: PLACEHOLDER - Requires official schema from Belastingdienst  
**Customizable**: NO - Must use official format for all tenants

---

## Overview

This template is for generating the **official IB Aangifte XBRL** file that must be submitted to the Dutch Tax Authority (Belastingdienst). This is different from the **Aangifte IB HTML Report** which is for internal viewing and analysis.

### Key Differences

| Aspect                | IB Aangifte XBRL (This)  | Aangifte IB HTML Report    |
| --------------------- | ------------------------ | -------------------------- |
| **Purpose**           | Official tax submission  | Internal viewing/analysis  |
| **Format**            | XML/XBRL                 | HTML                       |
| **Audience**          | Belastingdienst          | Business owner, accountant |
| **Structure**         | Fixed form fields        | Hierarchical table         |
| **Customizable**      | NO                       | YES (per tenant)           |
| **Validation**        | Required (XSD schema)    | Optional                   |
| **Template Location** | `backend/templates/xml/` | `backend/templates/html/`  |

---

## IMPORTANT: Official Schema Required

⚠️ **This is a PLACEHOLDER template**

The actual XBRL format must be obtained from Belastingdienst and must validate against their official XSD schema. The field names, structure, and taxonomy elements shown in this template are examples only.

### Required Steps Before Implementation:

1. **Obtain Official Schema**
   - Download XBRL taxonomy from Belastingdienst
   - Get XSD schema files for validation
   - Review technical documentation

2. **Understand Requirements**
   - Which fields are mandatory vs optional
   - Data types and formats for each field
   - Validation rules and constraints
   - Submission process and endpoints

3. **Update Template**
   - Replace placeholder fields with actual taxonomy elements
   - Add all required fields per official schema
   - Implement proper namespace declarations
   - Add schema validation

4. **Testing**
   - Validate against official XSD schema
   - Test submission to Belastingdienst test environment
   - Verify acceptance by tax authority systems

---

## XBRL Structure

XBRL files consist of:

1. **Context** - Defines the reporting entity and period
2. **Units** - Defines measurement units (EUR for currency)
3. **Facts** - The actual data values with references to context and units

### Example Structure:

```xml
<xbrl>
  <!-- Who and When -->
  <context id="CurrentYear">
    <entity>
      <identifier>BSN_NUMBER</identifier>
    </entity>
    <period>
      <startDate>2025-01-01</startDate>
      <endDate>2025-12-31</endDate>
    </period>
  </context>

  <!-- Currency -->
  <unit id="EUR">
    <measure>iso4217:EUR</measure>
  </unit>

  <!-- Data Values -->
  <bd:TaxonomyElement contextRef="CurrentYear" unitRef="EUR">
    VALUE
  </bd:TaxonomyElement>
</xbrl>
```

---

## Data Mapping

The data for the XBRL file comes from the same source as the HTML report but is aggregated differently:

### Source Data:

- `mutaties_cache.query_aangifte_ib(year, administration)` - Parent + Aangifte summary
- `mutaties_cache.query_aangifte_ib_details(year, admin, parent, aangifte, user_tenants)` - Account details

### Mapping to XBRL Fields:

The hierarchical data from the cache needs to be aggregated into the flat form fields required by Belastingdienst:

```python
# Example mapping (actual fields depend on official schema)
{
    'bsn_number': tenant.bsn,  # From tenant configuration
    'year': year,
    'box1_income': calculate_box1_income(report_data),  # Aggregate from accounts
    'box2_income': calculate_box2_income(report_data),
    'box3_income': calculate_box3_income(report_data),
    'business_profit': calculate_business_profit(report_data),  # From Parent 4000 + 8000
    'deductions': calculate_deductions(report_data),
    'taxable_income': calculate_taxable_income(report_data),
    'tax_amount': calculate_tax_amount(report_data)
}
```

---

## Implementation Pattern

### 1. Create Generator Function

```python
# backend/src/report_generators/ib_aangifte_xbrl_generator.py

def generate_ib_aangifte_xbrl_data(report_data, tenant_info, year):
    """
    Generate XBRL data from Aangifte IB report data.

    Args:
        report_data: Hierarchical data from cache.query_aangifte_ib()
        tenant_info: Tenant configuration (BSN, etc.)
        year: Tax year

    Returns:
        Dictionary with XBRL field values
    """
    # Aggregate hierarchical data into flat form fields
    # Apply tax calculation rules
    # Return data ready for template
    pass
```

### 2. Use TemplateService

```python
# In route handler
from report_generators import generate_ib_aangifte_xbrl_data

# 1. Query data
report_data = cache.query_aangifte_ib(year, administration)

# 2. Generate XBRL data
xbrl_data = generate_ib_aangifte_xbrl_data(report_data, tenant_info, year)

# 3. Get template
template_xml = template_service.fetch_template_from_drive(
    file_id=metadata['template_file_id'],
    administration='myAdmin'  # Same template for all tenants
)

# 4. Apply field mappings
xml = template_service.apply_field_mappings(template_xml, xbrl_data, mappings)

# 5. Validate against XSD schema
validate_xbrl(xml, schema_path)

# 6. Return or submit
return xml
```

---

## Validation

XBRL files MUST be validated against the official XSD schema before submission:

```python
import lxml.etree as ET

def validate_xbrl(xml_content, schema_path):
    """Validate XBRL against official schema"""
    schema = ET.XMLSchema(ET.parse(schema_path))
    doc = ET.fromstring(xml_content)

    if not schema.validate(doc):
        raise ValueError(f"XBRL validation failed: {schema.error_log}")

    return True
```

---

## Resources

- **Belastingdienst**: https://www.belastingdienst.nl/
- **XBRL International**: https://www.xbrl.org/
- **Dutch Tax Authority Technical Documentation**: Contact Belastingdienst for access
- **SBR (Standard Business Reporting)**: https://www.sbr-nl.nl/

---

## Next Steps

1. ✅ **Obtain official XBRL taxonomy from Belastingdienst** - See [OBTAINING_XBRL_TAXONOMY_GUIDE.md](./OBTAINING_XBRL_TAXONOMY_GUIDE.md)
2. ⏸️ Update template with actual field names and structure
3. ⏸️ Create generator function to aggregate data into form fields
4. ⏸️ Implement XSD schema validation
5. ⏸️ Test with Belastingdienst test environment
6. ⏸️ Document submission process

---

## Additional Resources

- **[Guide: Obtaining XBRL Taxonomy](./OBTAINING_XBRL_TAXONOMY_GUIDE.md)** - Comprehensive step-by-step guide for obtaining the official Dutch XBRL taxonomy from Belastingdienst

---

**Last Updated**: January 31, 2026  
**Status**: Placeholder - Awaiting official schema (Guide available for obtaining taxonomy)
