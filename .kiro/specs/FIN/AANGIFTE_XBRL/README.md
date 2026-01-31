# IB Aangifte XBRL Specification

**Feature**: Official Income Tax Return XML Submission to Belastingdienst  
**Module**: Finance (FIN)  
**Status**: ⏸️ Postponed Until After Railway Migration  
**Last Updated**: January 31, 2026

---

## Overview

This specification covers the implementation of XBRL (eXtensible Business Reporting Language) submission for IB Aangifte (Income Tax Return) to the Dutch Tax Authority (Belastingdienst).

**Purpose**: Enable official tax return submissions in XBRL format via Digipoort (government digital portal)

**Current Status**: Research and documentation complete. Implementation postponed until after Railway migration is complete.

---

## ⚠️ Postponement Notice

**Decision**: XBRL implementation has been postponed until after Railway migration Phase 5 is complete.

**Rationale**:

- Focus on critical path (Railway migration)
- XBRL is complex and time-consuming (2.5-4 weeks)
- Not blocking current operations (HTML reports are sufficient)
- Solid foundation exists for future implementation

**See**: [POSTPONEMENT_NOTICE.md](./POSTPONEMENT_NOTICE.md) for full details

---

## Documentation

### Quick Start

1. **[POSTPONEMENT_NOTICE.md](./POSTPONEMENT_NOTICE.md)** - Why implementation is postponed
2. **[IB_AANGIFTE_XBRL_README.md](./IB_AANGIFTE_XBRL_README.md)** - Template overview and requirements
3. **[OBTAINING_XBRL_TAXONOMY_GUIDE.md](./OBTAINING_XBRL_TAXONOMY_GUIDE.md)** - Step-by-step guide for obtaining official taxonomy
4. **[XBRL_TAXONOMY_QUICK_REFERENCE.md](./XBRL_TAXONOMY_QUICK_REFERENCE.md)** - Quick reference for links and terms
5. **[XBRL_IMPLEMENTATION_STATUS.md](./XBRL_IMPLEMENTATION_STATUS.md)** - Implementation progress tracking
6. **[NEXT_STEPS_ACTION_GUIDE.md](./NEXT_STEPS_ACTION_GUIDE.md)** - Actionable checklist for implementation
7. **[TASK_COMPLETION_SUMMARY.md](./TASK_COMPLETION_SUMMARY.md)** - Summary of completed research

### Template

- **[ib_aangifte_xbrl_template.xml](./ib_aangifte_xbrl_template.xml)** - Placeholder XBRL template (to be updated with official taxonomy)

---

## What is XBRL?

**XBRL** (eXtensible Business Reporting Language) is an XML-based standard for digital business reporting required by the Dutch Tax Authority for official tax submissions.

### Key Differences: XBRL vs HTML Reports

| Aspect           | XBRL (This Spec)              | HTML Reports               |
| ---------------- | ----------------------------- | -------------------------- |
| **Purpose**      | Official tax submission       | Internal viewing/analysis  |
| **Audience**     | Belastingdienst               | Business owner, accountant |
| **Format**       | XML/XBRL                      | HTML                       |
| **Structure**    | Fixed form fields             | Hierarchical table         |
| **Customizable** | NO (must use official format) | YES (per tenant)           |
| **Validation**   | Required (XSD schema)         | Optional                   |
| **Submission**   | Via Digipoort                 | Download or Google Drive   |

---

## Implementation Phases

### Phase 1: Research & Documentation ✅ COMPLETE

- Status: ✅ Complete (January 31, 2026)
- All documentation created (~25,000 words)

### Phase 2-7: POSTPONED ⏸️

- ⏸️ Phase 2: Obtain Taxonomy
- ⏸️ Phase 3: Update Template
- ⏸️ Phase 4: Create Generator
- ⏸️ Phase 5: Implement Validation
- ⏸️ Phase 6: Test with Digipoort
- ⏸️ Phase 7: Production Preparation

**Overall Progress**: 14% (1/7 phases complete)

**Estimated Time** (when resumed): 2.5-4 weeks

---

## Key Requirements

### Official Sources

1. **SBR-NL Portal**: https://www.sbr-nl.nl/ (Standard Business Reporting)
2. **NL Taxonomie**: https://www.nltaxonomie.nl/ (Taxonomy download)
3. **Belastingdienst ODB**: https://odb.belastingdienst.nl/ (Tax authority SBR info)
4. **Developer Registration**: Free registration for test environment access

### Technical Requirements

- **Dutch Taxonomy (NT)**: Official XBRL taxonomy from Belastingdienst
- **XSD Schema Validation**: All files must validate against official schema
- **PKIoverheid Certificate**: Required for production submissions
- **Digipoort**: Government digital submission portal

### Compliance

⚠️ **Critical Requirements**:

- Must use official Dutch Taxonomy (no custom modifications)
- Must validate against XSD schema
- Must use correct taxonomy version for tax year
- Must sign with PKIoverheid certificate (production)

---

## When to Resume

### Trigger Event

Resume implementation **after Railway Migration Phase 5 (Railway Deployment) is complete and stable**.

### Prerequisites

Before resuming:

1. ✅ Railway migration complete
2. ✅ All Railway phases tested and stable
3. ✅ Production environment running smoothly
4. ✅ No critical issues or bugs
5. ✅ Team has bandwidth for new feature development

### Next Steps (When Resuming)

1. Register as software developer with Belastingdienst
2. Download Dutch Taxonomy (NT) package
3. Follow [NEXT_STEPS_ACTION_GUIDE.md](./NEXT_STEPS_ACTION_GUIDE.md)

---

## Related Specifications

### Current (HTML Reports)

- **Aangifte IB HTML Report**: `backend/templates/html/aangifte_ib_template.html`
  - For internal viewing and analysis
  - Customizable per tenant
  - Already implemented and working

### Future (XBRL Submissions)

- **IB Aangifte XBRL**: This specification (postponed)
- **BTW Aangifte XBRL**: VAT return XBRL (also postponed)

---

## Impact Assessment

### No Impact on Current Operations ✅

- ✅ HTML reports are fully functional
- ✅ All required reports are implemented
- ✅ Template system is working
- ✅ No dependencies on XBRL

### No Impact on Railway Migration ✅

- ✅ Railway migration can proceed as planned
- ✅ All phases (1-5) can be completed
- ✅ XBRL is independent feature

---

## Resources

### Documentation (All Complete)

- ✅ Comprehensive obtaining guide (7,500+ words)
- ✅ Quick reference (3,000+ words)
- ✅ Implementation status tracking (4,500+ words)
- ✅ Action guide (2,500+ words)
- ✅ Task completion summary (3,000+ words)
- ✅ Postponement notice

**Total**: ~25,000 words of comprehensive documentation

### Official Websites

- **SBR-NL**: https://www.sbr-nl.nl/
- **NL Taxonomie**: https://www.nltaxonomie.nl/
- **Belastingdienst ODB**: https://odb.belastingdienst.nl/
- **Developer Registration**: https://www.belastingdienst.nl/wps/wcm/connect/bldcontenten/belastingdienst/business/tax_return/filing_digital_tax_returns/filing-tax-returns-using-accounting-software/

---

## Contact

For questions about this specification:

- **Project Lead**: TBD
- **Technical Lead**: TBD
- **Documentation**: See files in this directory

---

## Summary

✅ **Research Complete**: All documentation and planning finished  
⏸️ **Implementation Postponed**: Will resume after Railway Phase 5  
📚 **Documentation Preserved**: All guides ready for future use  
🎯 **Clear Path Forward**: Can resume quickly when ready

---

**Status**: Postponed - Research Complete  
**Resume After**: Railway Migration Phase 5 Complete  
**Estimated Timeline**: 2.5-4 weeks when resumed  
**Last Updated**: January 31, 2026
