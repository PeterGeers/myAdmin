# XBRL Implementation Status

**Feature**: IB Aangifte XBRL (Official Income Tax Return XML)  
**Last Updated**: January 31, 2026  
**Current Phase**: Research & Documentation Complete  
**Status**: ⏸️ **POSTPONED UNTIL AFTER RAILWAY MIGRATION**

---

## ⚠️ POSTPONEMENT NOTICE

**Decision**: XBRL implementation has been postponed until after Railway migration is complete.

**Rationale**:

- Focus on critical path (Railway migration)
- XBRL is complex and time-consuming (2.5-4 weeks)
- Not blocking current operations (HTML reports are sufficient)
- Solid foundation exists for future implementation

**Resume After**: Railway Migration Phase 5 (Railway Deployment) is complete and stable

**See**: [POSTPONEMENT_NOTICE.md](./POSTPONEMENT_NOTICE.md) for full details

---

## Overview

This document tracks the implementation status of the IB Aangifte XBRL feature, which enables official income tax return submissions to the Dutch Tax Authority (Belastingdienst) in XBRL format.

---

## Implementation Phases

### Phase 1: Research & Documentation ✅ COMPLETE

**Status**: ✅ Complete (January 31, 2026)

**Completed Tasks**:

- [x] Research Dutch XBRL taxonomy requirements
- [x] Identify official sources (SBR-NL, NL Taxonomie, Belastingdienst ODB)
- [x] Document Standard Business Reporting (SBR) process
- [x] Create comprehensive obtaining guide
- [x] Create quick reference document
- [x] Document validation requirements
- [x] Identify required tools and resources

**Deliverables**:

- ✅ `OBTAINING_XBRL_TAXONOMY_GUIDE.md` - Comprehensive step-by-step guide
- ✅ `XBRL_TAXONOMY_QUICK_REFERENCE.md` - Quick access to links and info
- ✅ `IB_AANGIFTE_XBRL_README.md` - Updated with next steps
- ✅ `XBRL_IMPLEMENTATION_STATUS.md` - This status document

**Key Findings**:

- Dutch government uses Standard Business Reporting (SBR) with XBRL
- Taxonomy is called Dutch Taxonomy (NT) or NTCA Taxonomy
- Free developer registration available with Belastingdienst
- Test environment (Digipoort) available for testing
- PKIoverheid certificate required for production submissions
- Taxonomy updated annually (NT15 for 2021, etc.)

---

### Phase 2: Obtain Taxonomy ⏸️ POSTPONED

**Status**: ⏸️ Postponed - Waiting for Railway Migration Completion

**Postponement Reason**: Focus on Railway migration critical path. Will resume after Phase 5 (Railway Deployment) is complete.

**Required Actions** (When Resumed):

1. Register as software developer with Belastingdienst
   - Visit: https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/
   - Look for "Informatie voor softwareontwikkelaars"
   - Complete free registration
2. Download Dutch Taxonomy (NT) package
   - Source: https://www.sbr-nl.nl/ or https://www.nltaxonomie.nl/
   - Download latest version (NT15 or newer)
   - Extract ZIP file
3. Review taxonomy structure
   - Use Taxonomy Viewer (Yeti) at https://odb.belastingdienst.nl/
   - Identify IB Aangifte entry point schema
   - Document required fields
4. Store taxonomy files
   - Place in `backend/templates/xml/taxonomy/` directory
   - Document version and download date

**Estimated Time**: 1-2 days

**Blockers**: None - ready to proceed

---

### Phase 3: Update Template ⏸️ POSTPONED

**Status**: ⏸️ Postponed - Waiting for Railway Migration Completion

**Tasks**:

- [ ] Replace placeholder namespace declarations with official ones
- [ ] Update field names to match taxonomy
- [ ] Add all required fields per official schema
- [ ] Remove placeholder fields
- [ ] Add proper schema references
- [ ] Document field mappings

**Dependencies**:

- Requires completed Phase 2 (taxonomy obtained)

**Estimated Time**: 2-3 days

---

### Phase 4: Create Generator ⏸️ POSTPONED

**Status**: ⏸️ Postponed - Waiting for Railway Migration Completion

**Tasks**:

- [ ] Create `backend/src/report_generators/ib_aangifte_xbrl_generator.py`
- [ ] Implement data aggregation from hierarchical to flat form fields
- [ ] Implement tax calculation rules
- [ ] Map Parent/Aangifte data to XBRL fields (Box 1, Box 2, Box 3, etc.)
- [ ] Create unit tests
- [ ] Test with sample data

**Dependencies**:

- Requires completed Phase 3 (template updated)

**Estimated Time**: 3-4 days

---

### Phase 5: Implement Validation ⏸️ POSTPONED

**Status**: ⏸️ Postponed - Waiting for Railway Migration Completion

**Tasks**:

- [ ] Implement XSD schema validation
- [ ] Create validation utility functions
- [ ] Add error handling and reporting
- [ ] Test with valid and invalid XBRL files
- [ ] Document validation process

**Dependencies**:

- Requires completed Phase 4 (generator created)

**Estimated Time**: 1-2 days

---

### Phase 6: Test with Digipoort ⏸️ POSTPONED

**Status**: ⏸️ Postponed - Waiting for Railway Migration Completion

**Tasks**:

- [ ] Access Digipoort test environment
- [ ] Generate test XBRL files
- [ ] Submit to test environment
- [ ] Verify acceptance
- [ ] Fix any validation errors
- [ ] Document submission process
- [ ] Create troubleshooting guide

**Dependencies**:

- Requires completed Phase 5 (validation implemented)
- Requires developer registration (Phase 2)

**Estimated Time**: 2-3 days

---

### Phase 7: Production Preparation ⏸️ POSTPONED

**Status**: ⏸️ Postponed - Waiting for Railway Migration Completion

**Tasks**:

- [ ] Obtain PKIoverheid services server certificate
- [ ] Configure certificate in application
- [ ] Test certificate-based submission
- [ ] Create production submission workflow
- [ ] Document production process
- [ ] Train users
- [ ] Create user documentation

**Dependencies**:

- Requires completed Phase 6 (test environment validated)

**Estimated Time**: 3-5 days (certificate acquisition may take longer)

---

## Overall Progress

```
Phase 1: Research & Documentation    [████████████████████] 100% ✅
Phase 2: Obtain Taxonomy              [░░░░░░░░░░░░░░░░░░░░]   0% ⏸️
Phase 3: Update Template              [░░░░░░░░░░░░░░░░░░░░]   0% ⏸️
Phase 4: Create Generator             [░░░░░░░░░░░░░░░░░░░░]   0% ⏸️
Phase 5: Implement Validation         [░░░░░░░░░░░░░░░░░░░░]   0% ⏸️
Phase 6: Test with Digipoort          [░░░░░░░░░░░░░░░░░░░░]   0% ⏸️
Phase 7: Production Preparation       [░░░░░░░░░░░░░░░░░░░░]   0% ⏸️

Overall Progress: 14% (1/7 phases complete)
```

---

## Timeline Estimate

| Phase   | Duration | Start      | End           |
| ------- | -------- | ---------- | ------------- |
| Phase 1 | 1 day    | 2026-01-31 | 2026-01-31 ✅ |
| Phase 2 | 1-2 days | TBD        | TBD           |
| Phase 3 | 2-3 days | TBD        | TBD           |
| Phase 4 | 3-4 days | TBD        | TBD           |
| Phase 5 | 1-2 days | TBD        | TBD           |
| Phase 6 | 2-3 days | TBD        | TBD           |
| Phase 7 | 3-5 days | TBD        | TBD           |

**Total Estimated Time**: 13-20 working days (2.5-4 weeks)

**Note**: Certificate acquisition in Phase 7 may add additional time depending on provider.

---

## Resources Created

### Documentation

1. **OBTAINING_XBRL_TAXONOMY_GUIDE.md**
   - Comprehensive guide for obtaining official taxonomy
   - Step-by-step instructions
   - Background information on SBR and XBRL
   - Technical details and requirements

2. **XBRL_TAXONOMY_QUICK_REFERENCE.md**
   - Quick access to essential links
   - Key terms and translations
   - Validation checklist
   - Status tracking

3. **IB_AANGIFTE_XBRL_README.md**
   - Overview of XBRL template
   - Differences from HTML report
   - Implementation pattern
   - Next steps

4. **XBRL_IMPLEMENTATION_STATUS.md** (This Document)
   - Overall implementation status
   - Phase tracking
   - Timeline estimates
   - Progress visualization

### Code Files

1. **ib_aangifte_xbrl_template.xml**
   - Placeholder XBRL template
   - To be updated with official taxonomy fields

### Pending Files

- `backend/src/report_generators/ib_aangifte_xbrl_generator.py` (Phase 4)
- `backend/src/utils/xbrl_validator.py` (Phase 5)
- `backend/tests/unit/test_ib_aangifte_xbrl_generator.py` (Phase 4)
- `backend/tests/integration/test_xbrl_submission.py` (Phase 6)

---

## Key Decisions

### 1. Use Official Taxonomy (Not Custom)

**Decision**: Use the official Dutch Taxonomy (NT) from Belastingdienst without modifications

**Rationale**:

- Required for official submissions
- Ensures compliance
- Validated by government systems

### 2. Separate HTML Report and XBRL Submission

**Decision**: Keep HTML report (for viewing) separate from XBRL submission (for tax authority)

**Rationale**:

- Different purposes and audiences
- HTML is customizable per tenant
- XBRL must use official format for all tenants

### 3. Implement XSD Validation

**Decision**: Validate all XBRL files against official XSD schema before submission

**Rationale**:

- Catch errors early
- Reduce submission failures
- Improve reliability

### 4. Use Digipoort Test Environment

**Decision**: Test thoroughly in Digipoort test environment before production

**Rationale**:

- Safe testing without affecting real submissions
- Identify issues early
- Validate complete submission workflow

---

## Risks & Mitigations

### Risk 1: Taxonomy Complexity

**Risk**: Official taxonomy may be more complex than anticipated

**Mitigation**:

- Use Taxonomy Viewer (Yeti) to explore structure
- Start with minimal required fields
- Consult Belastingdienst developer support
- Consider XBRL consultant if needed

### Risk 2: Validation Failures

**Risk**: Generated XBRL files may fail validation

**Mitigation**:

- Implement local XSD validation before submission
- Test with sample data extensively
- Use Digipoort test environment
- Document common errors and solutions

### Risk 3: Certificate Acquisition Delays

**Risk**: PKIoverheid certificate may take time to obtain

**Mitigation**:

- Start certificate process early (Phase 2)
- Use test environment without certificate initially
- Plan for certificate lead time in timeline

### Risk 4: Annual Taxonomy Updates

**Risk**: Taxonomy changes each year, requiring updates

**Mitigation**:

- Monitor release calendar
- Subscribe to taxonomy update notifications
- Plan for annual maintenance
- Document update process

---

## Success Criteria

### Phase 2 Success

- ✅ Developer registration complete
- ✅ Taxonomy package downloaded
- ✅ Taxonomy files extracted and stored
- ✅ IB Aangifte entry point identified

### Phase 3 Success

- ✅ Template uses official namespace declarations
- ✅ All required fields present
- ✅ Field mappings documented
- ✅ Template validates against XSD schema

### Phase 4 Success

- ✅ Generator function created
- ✅ Data aggregation implemented
- ✅ Tax calculations correct
- ✅ Unit tests passing
- ✅ Sample XBRL files generated

### Phase 5 Success

- ✅ XSD validation implemented
- ✅ Validation errors reported clearly
- ✅ Valid files pass validation
- ✅ Invalid files fail with helpful messages

### Phase 6 Success

- ✅ Test submission accepted by Digipoort
- ✅ No validation errors
- ✅ Submission process documented
- ✅ Error handling implemented

### Phase 7 Success

- ✅ PKIoverheid certificate obtained and configured
- ✅ Production submission successful
- ✅ User documentation complete
- ✅ Users trained
- ✅ Feature deployed to production

---

## Next Immediate Action

**Action**: Register as software developer with Belastingdienst

**Steps**:

1. Visit https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/
2. Look for "Informatie voor softwareontwikkelaars" section
3. Complete registration form
4. Receive confirmation and access credentials
5. Access Digipoort developer portal

**Estimated Time**: 30 minutes - 1 hour

**Assigned To**: TBD

**Target Date**: TBD

---

## Contact Information

### Project Team

- **Project Lead**: TBD
- **Developer**: TBD
- **Tester**: TBD

### External Contacts

- **Belastingdienst Developer Support**: Available after registration
- **SBR-NL Support**: Via website
- **PKIoverheid Certificate Provider**: TBD

---

## Change Log

| Date       | Phase   | Change                                   | Author  |
| ---------- | ------- | ---------------------------------------- | ------- |
| 2026-01-31 | Phase 1 | Research complete, documentation created | Kiro AI |
| TBD        | Phase 2 | Taxonomy obtained                        | TBD     |
| TBD        | Phase 3 | Template updated                         | TBD     |
| TBD        | Phase 4 | Generator created                        | TBD     |
| TBD        | Phase 5 | Validation implemented                   | TBD     |
| TBD        | Phase 6 | Test submission successful               | TBD     |
| TBD        | Phase 7 | Production deployment                    | TBD     |

---

**Status**: Phase 1 Complete - Ready to proceed with Phase 2  
**Last Updated**: January 31, 2026  
**Next Review**: After Phase 2 completion
