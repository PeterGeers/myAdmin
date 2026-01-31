# Guide: Obtaining Official XBRL Taxonomy from Belastingdienst

**Document Purpose**: Step-by-step guide for obtaining the official Dutch XBRL taxonomy for IB Aangifte (Income Tax Return)  
**Last Updated**: January 31, 2026  
**Status**: Research Complete - Action Required

---

## Executive Summary

To implement the IB Aangifte XBRL submission feature, you **must** obtain the official XBRL taxonomy from the Dutch Tax Authority (Belastingdienst). This is not optional - the taxonomy defines the exact structure, field names, and validation rules required for official tax submissions.

**Key Finding**: The Dutch government uses **Standard Business Reporting (SBR)** with XBRL for all digital tax submissions. The taxonomy is called the **Dutch Taxonomy (NT)** or **NTCA Taxonomy** (Netherlands Tax and Customs Administration).

---

## What is the Dutch Taxonomy?

The Dutch Taxonomy is an XBRL-based standard that defines:

- **Field names and structure** for all tax forms (VAT, ICP, Income Tax, etc.)
- **Data types and formats** for each field
- **Validation rules** that must be satisfied
- **Namespace declarations** and schema references
- **Submission requirements** for Digipoort (the government's digital portal)

### Taxonomy Versions

The taxonomy is updated regularly. Recent versions include:

- **NT15** (2021 reporting)
- **NT14** (2020 reporting)
- **NT12** (2018 reporting)

Each year may require a different taxonomy version. You must use the correct version for the tax year you're reporting.

---

## Where to Find the Taxonomy

### Official Sources

1. **SBR-NL Website** (Primary Source)
   - Website: https://www.sbr-nl.nl/
   - The official Standard Business Reporting portal for the Netherlands
   - Contains the complete Dutch Taxonomy
   - **Note**: Some sections may be in Dutch only

2. **NL Taxonomie Website**
   - Website: https://www.nltaxonomie.nl/
   - Alternative access point for the Dutch Taxonomy
   - Provides taxonomy packages for download

3. **Belastingdienst ODB Portal**
   - Website: https://odb.belastingdienst.nl/en/information-about-standard-business-reporting-sbr/
   - Support Digital Messaging (SDM) portal
   - Contains:
     - Release calendar (when new versions are available)
     - Taxonomy viewer (Yeti tool) for exploring taxonomy structure
     - Technical documentation

4. **Digipoort Developer Portal**
   - For software developers building tax submission systems
   - Requires registration (free of charge)
   - Provides:
     - Test environment access
     - Technical specifications
     - Sample files
     - Validation tools

---

## Step-by-Step: How to Obtain the Taxonomy

### Step 1: Register as a Software Developer (Recommended)

**Why**: Access to test environment, technical support, and latest documentation

**How**:

1. Visit the Belastingdienst website
2. Look for "Informatie voor softwareontwikkelaars" (Information for software developers)
3. Register for a **free support subscription**
4. This gives you:
   - Access to Digipoort test environment
   - Technical documentation
   - Support for development and testing
   - Early access to taxonomy updates

**Link**: https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/

### Step 2: Download the Taxonomy Package

**Option A: Via SBR-NL Website**

1. Go to https://www.sbr-nl.nl/
2. Navigate to "Taxonomie" or "Downloads" section
3. Find the latest **NT (Nederlandse Taxonomie)** version
4. Download the **Taxonomy Package** (ZIP file)

**Option B: Via NL Taxonomie Website**

1. Go to https://www.nltaxonomie.nl/
2. Browse or search for "Inkomstenbelasting" (Income Tax)
3. Download the relevant taxonomy package

**Option C: Via Digipoort Developer Portal**

1. Log in to your developer account
2. Access the "Taxonomie" section
3. Download the taxonomy for your target tax year

### Step 3: Explore the Taxonomy Structure

**Use the Taxonomy Viewer (Yeti)**:

1. Go to https://odb.belastingdienst.nl/
2. Access the "Taxonomy viewer (Yeti)" tool
3. Select the taxonomy version you need
4. Explore:
   - Available reports (find "Aangifte Inkomstenbelasting")
   - Required fields and their data types
   - Validation rules
   - Example structures

### Step 4: Download XSD Schema Files

The taxonomy package should include:

- **XSD schema files** (.xsd) - For validation
- **Linkbase files** (.xml) - Define relationships between elements
- **Documentation** - Field descriptions and requirements
- **Examples** - Sample XBRL files

### Step 5: Obtain PKIoverheid Certificate (For Production)

**Important**: To submit XBRL files to Digipoort in production, you need a **PKIoverheid services server certificate**.

**What it is**: A digital certificate for secure communication with Dutch government systems

**How to get it**:

1. Contact a PKIoverheid certificate provider
2. Request a "PKIoverheid services server certificate"
3. Follow their registration and verification process
4. Install the certificate in your application

**Note**: This is only needed for production submissions, not for development/testing.

---

## What You'll Receive

### Taxonomy Package Contents

A typical taxonomy package (ZIP file) contains:

```
NT15_2021/
├── entrypoints/
│   ├── ib-aangifte-2021.xsd          # Income tax return schema
│   ├── vat-declaration-2021.xsd      # VAT declaration schema
│   └── ...
├── taxonomies/
│   ├── bd-algemeen.xsd                # General Belastingdienst elements
│   ├── bd-inkomstenbelasting.xsd      # Income tax specific elements
│   └── ...
├── linkbases/
│   ├── ib-aangifte-label-nl.xml       # Dutch labels
│   ├── ib-aangifte-presentation.xml   # Presentation structure
│   └── ...
├── documentation/
│   ├── technical-guide.pdf
│   └── field-descriptions.pdf
└── examples/
    ├── sample-ib-aangifte.xml
    └── ...
```

### Key Files for IB Aangifte

Look for these specific files:

- **Entry point**: `ib-aangifte-[year].xsd` or similar
- **Schema**: Files defining income tax elements
- **Labels**: Dutch language labels for fields
- **Examples**: Sample XBRL files for income tax returns

---

## Understanding the Taxonomy Structure

### XBRL Basics

An XBRL file consists of:

1. **Context** - Who is reporting and for what period

   ```xml
   <context id="CurrentYear">
     <entity>
       <identifier scheme="http://www.belastingdienst.nl">BSN_NUMBER</identifier>
     </entity>
     <period>
       <startDate>2025-01-01</startDate>
       <endDate>2025-12-31</endDate>
     </period>
   </context>
   ```

2. **Units** - Measurement units (EUR for currency)

   ```xml
   <unit id="EUR">
     <measure>iso4217:EUR</measure>
   </unit>
   ```

3. **Facts** - The actual data values
   ```xml
   <bd-ib:WinstUitOnderneming contextRef="CurrentYear" unitRef="EUR" decimals="2">
     45000.00
   </bd-ib:WinstUitOnderneming>
   ```

### Namespace Conventions

Dutch tax taxonomies typically use namespaces like:

- `bd-ib:` - Belastingdienst Inkomstenbelasting (Income Tax)
- `bd-algemeen:` - General Belastingdienst elements
- `bd-types:` - Data type definitions

**Important**: The exact namespace prefixes and URIs are defined in the taxonomy schema files.

---

## Next Steps After Obtaining Taxonomy

### 1. Update the Template

Replace the placeholder template (`ib_aangifte_xbrl_template.xml`) with:

- Correct namespace declarations from the official schema
- Actual field names from the taxonomy
- Proper structure as defined in the entry point schema

### 2. Implement Validation

```python
import lxml.etree as ET

def validate_xbrl(xml_content, schema_path):
    """Validate XBRL against official schema"""
    schema = ET.XMLSchema(ET.parse(schema_path))
    doc = ET.fromstring(xml_content)

    if not schema.validate(doc):
        errors = schema.error_log
        raise ValueError(f"XBRL validation failed: {errors}")

    return True
```

### 3. Map Your Data to Taxonomy Fields

Create a mapping between your internal data structure and the taxonomy fields:

```python
# Example mapping (actual fields depend on taxonomy)
taxonomy_mapping = {
    'bd-ib:WinstUitOnderneming': calculate_business_profit,
    'bd-ib:InkomenBox1': calculate_box1_income,
    'bd-ib:InkomenBox2': calculate_box2_income,
    'bd-ib:InkomenBox3': calculate_box3_income,
    # ... more mappings
}
```

### 4. Test with Digipoort Test Environment

Before production:

1. Generate XBRL files using your implementation
2. Validate against the XSD schema locally
3. Submit to Digipoort test environment
4. Verify acceptance and correct processing
5. Fix any validation errors

### 5. Document the Submission Process

Create documentation for:

- How to generate the XBRL file
- How to validate it
- How to submit via Digipoort
- How to handle responses (acceptance/rejection)
- Error handling and troubleshooting

---

## Important Considerations

### Language

Most documentation is in **Dutch**. Key terms to know:

- **Aangifte** = Declaration/Return
- **Inkomstenbelasting (IB)** = Income Tax
- **Belastingdienst** = Tax Authority
- **Winst uit onderneming** = Business profit
- **Aftrekposten** = Deductions
- **Belastbaar inkomen** = Taxable income

### Compliance

- **Must use official taxonomy** - No custom modifications allowed
- **Must validate against XSD** - Invalid files will be rejected
- **Must use correct version** - Each tax year may require different taxonomy
- **Must sign with PKIoverheid certificate** - For production submissions

### Updates

- **Monitor release calendar** - New versions released regularly
- **Test before tax season** - Ensure compatibility with new versions
- **Update annually** - Taxonomy changes each year

### Support

If you encounter issues:

1. Check the technical documentation in the taxonomy package
2. Use the Taxonomy Viewer (Yeti) to explore structure
3. Contact Belastingdienst developer support (if registered)
4. Consult SBR-NL community forums
5. Consider hiring an XBRL consultant for complex implementations

---

## Resources

### Official Websites

- **SBR-NL**: https://www.sbr-nl.nl/
- **NL Taxonomie**: https://www.nltaxonomie.nl/
- **Belastingdienst ODB**: https://odb.belastingdienst.nl/
- **Belastingdienst Business**: https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/

### Technical Standards

- **XBRL International**: https://www.xbrl.org/
- **XBRL Specifications**: https://specifications.xbrl.org/
- **Taxonomy Package Specification**: https://www.xbrl.org/guidance/taxonomy-publication/

### Tools

- **Taxonomy Viewer (Yeti)**: Available on ODB portal
- **XBRL Validation Tools**: Various open-source and commercial options
- **Python Libraries**: `lxml`, `arelle` (XBRL processor)

### Community

- **SBR-NL Forums**: Check SBR-NL website for community discussions
- **XBRL International**: Global XBRL community and resources

---

## Action Items

- [ ] Register as software developer with Belastingdienst (free subscription)
- [ ] Download the latest Dutch Taxonomy (NT) package
- [ ] Extract and review the taxonomy files
- [ ] Identify the IB Aangifte entry point schema
- [ ] Explore the taxonomy structure using Yeti viewer
- [ ] Document the required fields for IB Aangifte
- [ ] Update the placeholder template with actual field names
- [ ] Implement XSD schema validation
- [ ] Create field mapping documentation
- [ ] Test with sample data
- [ ] Submit test file to Digipoort test environment
- [ ] Obtain PKIoverheid certificate (for production)
- [ ] Document the complete submission process

---

## Conclusion

Obtaining the official XBRL taxonomy is a **critical prerequisite** for implementing IB Aangifte XBRL submission. The taxonomy is freely available through official Dutch government channels, but requires:

1. **Registration** as a software developer (recommended)
2. **Download** of the taxonomy package
3. **Understanding** of XBRL structure and Dutch tax requirements
4. **Validation** against official schemas
5. **Testing** in the Digipoort test environment

**Estimated Time**: 1-2 days for registration, download, and initial exploration

**Next Task**: Once taxonomy is obtained, update the template with actual field names and structure.

---

**Document Status**: ✅ Complete - Ready for action  
**Created**: January 31, 2026  
**Author**: Kiro AI Assistant
