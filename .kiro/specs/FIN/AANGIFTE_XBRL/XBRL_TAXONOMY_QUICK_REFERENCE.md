# XBRL Taxonomy Quick Reference

**Purpose**: Quick access to essential links and information for obtaining Dutch XBRL taxonomy  
**Last Updated**: January 31, 2026

---

## Essential Links

### Primary Sources

| Resource                   | URL                                                                                                                                                                      | Purpose                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------- |
| **SBR-NL Portal**          | https://www.sbr-nl.nl/                                                                                                                                                   | Main Standard Business Reporting portal |
| **NL Taxonomie**           | https://www.nltaxonomie.nl/                                                                                                                                              | Dutch Taxonomy download site            |
| **Belastingdienst ODB**    | https://odb.belastingdienst.nl/en/information-about-standard-business-reporting-sbr/                                                                                     | Tax authority SBR information           |
| **Developer Registration** | https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/ | Register for free developer support     |

### Tools

| Tool                           | URL                               | Purpose                    |
| ------------------------------ | --------------------------------- | -------------------------- |
| **Taxonomy Viewer (Yeti)**     | Available via ODB portal          | Explore taxonomy structure |
| **Digipoort Test Environment** | Access via developer registration | Test XBRL submissions      |

---

## What to Download

### Required Files

1. **Dutch Taxonomy Package (NT)** - Latest version
   - Format: ZIP file
   - Contains: XSD schemas, linkbases, documentation, examples
   - Source: SBR-NL or NL Taxonomie website

2. **IB Aangifte Entry Point**
   - Look for: `ib-aangifte-[year].xsd` or similar
   - This is the main schema for income tax returns

3. **Documentation**
   - Technical specifications
   - Field descriptions
   - Validation rules
   - Submission guidelines

### Optional but Recommended

- **Sample XBRL files** - Examples of valid submissions
- **Release calendar** - Track taxonomy updates
- **Technical guides** - Implementation best practices

---

## Key Taxonomy Versions

| Version  | Year | Status                     |
| -------- | ---- | -------------------------- |
| **NT15** | 2021 | Current for 2021 reporting |
| **NT14** | 2020 | Previous version           |
| **NT12** | 2018 | Older version              |

**Note**: Always use the taxonomy version that matches your reporting year.

---

## Registration Steps (Summary)

1. Visit Belastingdienst developer page
2. Look for "Informatie voor softwareontwikkelaars"
3. Register for free support subscription
4. Receive access to:
   - Digipoort test environment
   - Technical documentation
   - Developer support
   - Early taxonomy updates

---

## Important Terms (Dutch → English)

| Dutch                      | English                     | Notes                        |
| -------------------------- | --------------------------- | ---------------------------- |
| Aangifte                   | Declaration/Return          | Tax return                   |
| Inkomstenbelasting (IB)    | Income Tax                  | Personal income tax          |
| Belastingdienst            | Tax Authority               | Dutch IRS equivalent         |
| Winst uit onderneming      | Business profit             | From self-employment         |
| Aftrekposten               | Deductions                  | Tax deductions               |
| Belastbaar inkomen         | Taxable income              | After deductions             |
| Digipoort                  | Digital Portal              | Government submission portal |
| PKIoverheid                | PKI Government              | Digital certificate system   |
| SBR                        | Standard Business Reporting | National reporting standard  |
| Nederlandse Taxonomie (NT) | Dutch Taxonomy              | XBRL taxonomy for NL         |

---

## Validation Requirements

### Must Have

- ✅ Valid XML structure
- ✅ Correct namespace declarations
- ✅ All required fields present
- ✅ Correct data types
- ✅ Passes XSD schema validation
- ✅ Signed with PKIoverheid certificate (production only)

### Common Validation Errors

- Missing required fields
- Incorrect data types (e.g., string instead of decimal)
- Invalid namespace URIs
- Incorrect taxonomy version
- Missing or invalid digital signature

---

## Testing Checklist

Before production submission:

- [ ] Downloaded correct taxonomy version
- [ ] Validated XBRL file against XSD schema locally
- [ ] Tested with sample data
- [ ] Submitted to Digipoort test environment
- [ ] Received acceptance confirmation from test environment
- [ ] Obtained PKIoverheid certificate
- [ ] Documented submission process
- [ ] Trained users on the system

---

## Support Contacts

### Official Support

- **Belastingdienst Developer Support**: Available after registration
- **SBR-NL Community**: Check website for forums/contact info
- **Digipoort Helpdesk**: For technical submission issues

### When to Contact Support

- Cannot access taxonomy files
- Validation errors you can't resolve
- Digipoort submission failures
- PKIoverheid certificate issues
- Taxonomy interpretation questions

---

## Python Libraries for XBRL

### Recommended

```python
# XML processing and validation
import lxml.etree as ET

# XBRL-specific processing (optional)
# pip install arelle
# Arelle is a comprehensive XBRL processor
```

### Basic Validation Example

```python
def validate_xbrl(xml_file, schema_file):
    """Validate XBRL against XSD schema"""
    schema = ET.XMLSchema(ET.parse(schema_file))
    doc = ET.parse(xml_file)

    if not schema.validate(doc):
        print("Validation errors:")
        for error in schema.error_log:
            print(f"  Line {error.line}: {error.message}")
        return False

    return True
```

---

## Next Actions

### Immediate (This Week)

1. Register as software developer with Belastingdienst
2. Download latest Dutch Taxonomy (NT) package
3. Extract and review taxonomy files
4. Identify IB Aangifte entry point schema

### Short Term (Next 2 Weeks)

5. Explore taxonomy using Yeti viewer
6. Document required fields for IB Aangifte
7. Update placeholder template with actual field names
8. Implement XSD schema validation

### Medium Term (Next Month)

9. Create field mapping from internal data to taxonomy
10. Generate test XBRL files
11. Submit to Digipoort test environment
12. Iterate based on validation feedback

### Long Term (Before Production)

13. Obtain PKIoverheid certificate
14. Complete end-to-end testing
15. Document submission process
16. Train users
17. Go live with production submissions

---

## File Locations in Project

```
backend/templates/xml/
├── ib_aangifte_xbrl_template.xml          # Placeholder template (to be updated)
├── IB_AANGIFTE_XBRL_README.md             # Main documentation
├── OBTAINING_XBRL_TAXONOMY_GUIDE.md       # Detailed guide (this document's companion)
├── XBRL_TAXONOMY_QUICK_REFERENCE.md       # This file
└── [taxonomy_files]/                       # Place downloaded taxonomy here
    ├── ib-aangifte-2025.xsd               # Entry point schema
    ├── bd-inkomstenbelasting.xsd          # IB-specific elements
    └── ...                                 # Other taxonomy files
```

---

## Status Tracking

| Task                      | Status      | Date       | Notes                 |
| ------------------------- | ----------- | ---------- | --------------------- |
| Research taxonomy sources | ✅ Complete | 2026-01-31 | Guide created         |
| Register as developer     | ⏸️ Pending  | -          | Action required       |
| Download taxonomy         | ⏸️ Pending  | -          | After registration    |
| Review taxonomy structure | ⏸️ Pending  | -          | After download        |
| Update template           | ⏸️ Pending  | -          | After review          |
| Implement validation      | ⏸️ Pending  | -          | After template update |
| Test submission           | ⏸️ Pending  | -          | After validation      |
| Obtain certificate        | ⏸️ Pending  | -          | Before production     |
| Production deployment     | ⏸️ Pending  | -          | Final step            |

---

**Quick Start**: See [OBTAINING_XBRL_TAXONOMY_GUIDE.md](./OBTAINING_XBRL_TAXONOMY_GUIDE.md) for detailed instructions.

**Last Updated**: January 31, 2026
