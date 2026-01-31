# IB Aangifte XBRL - Implementation Tasks

**Feature**: Official Income Tax Return XML Submission to Belastingdienst  
**Status**: ⏸️ Postponed Until After Railway Migration  
**Last Updated**: January 31, 2026

---

## ⚠️ POSTPONEMENT NOTICE

Implementation postponed until after Railway Migration Phase 5 is complete.

**See**: [POSTPONEMENT_NOTICE.md](./POSTPONEMENT_NOTICE.md) for details

---

## Phase 1: Research & Documentation ✅ COMPLETE

**Status**: ✅ Complete (January 31, 2026)

- [x] Research Dutch XBRL taxonomy requirements
- [x] Identify official sources
- [x] Create comprehensive documentation (~25,000 words)
- [x] Create placeholder XBRL template
- [x] Document implementation roadmap

**Time**: 1 day

---

## Phase 2: Obtain Taxonomy ⏸️ POSTPONED

**Status**: ⏸️ Postponed

- [ ] Register as software developer with Belastingdienst
- [ ] Download Dutch Taxonomy (NT) package
- [ ] Explore taxonomy structure with Yeti viewer
- [ ] Store taxonomy files

**Estimated Time**: 1-2 days

---

## Phase 3: Update Template ⏸️ POSTPONED

**Status**: ⏸️ Postponed

- [ ] Update namespace declarations with official ones
- [ ] Replace placeholder fields with actual taxonomy elements
- [ ] Add all required fields per official schema
- [ ] Document field mappings
- [ ] Validate template against XSD schema

**Estimated Time**: 2-3 days

---

## Phase 4: Create Generator ⏸️ POSTPONED

**Status**: ⏸️ Postponed

- [ ] Create `backend/src/report_generators/ib_aangifte_xbrl_generator.py`
- [ ] Implement data aggregation from hierarchical to flat form fields
- [ ] Implement tax calculation rules
- [ ] Map Parent/Aangifte data to XBRL fields (Box 1, Box 2, Box 3, etc.)
- [ ] Create unit tests

**Estimated Time**: 3-4 days

---

## Phase 5: Implement Validation ⏸️ POSTPONED

**Status**: ⏸️ Postponed

- [ ] Create `backend/src/utils/xbrl_validator.py`
- [ ] Implement XSD schema validation
- [ ] Add error handling and reporting
- [ ] Test with valid and invalid XBRL files

**Estimated Time**: 1-2 days

---

## Phase 6: Test with Digipoort ⏸️ POSTPONED

**Status**: ⏸️ Postponed

- [ ] Access Digipoort test environment
- [ ] Generate test XBRL files
- [ ] Submit to test environment
- [ ] Fix validation errors
- [ ] Document submission process

**Estimated Time**: 2-3 days

---

## Phase 7: Production Preparation ⏸️ POSTPONED

**Status**: ⏸️ Postponed

- [ ] Obtain PKIoverheid services server certificate
- [ ] Configure certificate in application
- [ ] Create production submission workflow
- [ ] Create user documentation
- [ ] Train users
- [ ] Deploy to production

**Estimated Time**: 3-5 days

---

## Additional: BTW Aangifte XBRL ⏸️ POSTPONED

**Status**: ⏸️ Postponed (Lower priority)

- [ ] Obtain BTW Aangifte XBRL taxonomy
- [ ] Create BTW Aangifte XBRL template
- [ ] Create generator function
- [ ] Implement XSD schema validation

**Estimated Time**: 2-3 weeks

---

## Progress

| Phase   | Status       | Time     |
| ------- | ------------ | -------- |
| Phase 1 | ✅ Complete  | 1 day    |
| Phase 2 | ⏸️ Postponed | 1-2 days |
| Phase 3 | ⏸️ Postponed | 2-3 days |
| Phase 4 | ⏸️ Postponed | 3-4 days |
| Phase 5 | ⏸️ Postponed | 1-2 days |
| Phase 6 | ⏸️ Postponed | 2-3 days |
| Phase 7 | ⏸️ Postponed | 3-5 days |

**Overall**: 14% (1/7 phases complete)  
**Total Time** (when resumed): 13-20 days (2.5-4 weeks)

---

## Resources

- [README.md](./README.md) - Spec overview
- [OBTAINING_XBRL_TAXONOMY_GUIDE.md](./OBTAINING_XBRL_TAXONOMY_GUIDE.md) - How to obtain taxonomy
- [XBRL_IMPLEMENTATION_STATUS.md](./XBRL_IMPLEMENTATION_STATUS.md) - Detailed status
- [NEXT_STEPS_ACTION_GUIDE.md](./NEXT_STEPS_ACTION_GUIDE.md) - Action checklist

---

**Resume After**: Railway Migration Phase 5 Complete
