# XML/XBRL Templates Directory

**Purpose**: Storage for XML and XBRL templates used for official tax submissions  
**Last Updated**: January 31, 2026  
**Status**: XBRL Specification Moved to `.kiro/specs/FIN/AANGIFTE_XBRL`

---

## ⚠️ IMPORTANT: XBRL Specification Relocated

The IB Aangifte XBRL specification and all related documentation has been **moved to a dedicated spec folder**:

**New Location**: `.kiro/specs/FIN/AANGIFTE_XBRL/`

This includes:

- All XBRL documentation (7 files, ~25,000 words)
- XBRL template file
- Implementation guides and status tracking
- Postponement notice

**Why Moved**: To organize specifications by module (Finance) and keep implementation details separate from template storage.

**See**: [.kiro/specs/FIN/AANGIFTE_XBRL/README.md](../../.kiro/specs/FIN/AANGIFTE_XBRL/README.md) for the complete specification.

---

## Directory Contents

This directory is for storing XML/XBRL template files used in production. Currently contains:

### Files

1. **generate_sample_financial_data.py** - Utility script for generating sample data
2. **IMPLEMENTATION_SUMMARY.md** - Summary of template implementation work

### Note

XBRL templates and documentation are now maintained in the spec folder at `.kiro/specs/FIN/AANGIFTE_XBRL/`.

---

## Quick Links

### XBRL Specification (Moved)

📁 **Location**: `.kiro/specs/FIN/AANGIFTE_XBRL/`

**Key Documents**:

- `README.md` - Specification overview
- `POSTPONEMENT_NOTICE.md` - Why implementation is postponed
- `OBTAINING_XBRL_TAXONOMY_GUIDE.md` - How to obtain official taxonomy
- `XBRL_IMPLEMENTATION_STATUS.md` - Implementation progress
- `ib_aangifte_xbrl_template.xml` - Placeholder template

### HTML Templates (Active)

📁 **Location**: `backend/templates/html/`

**Active Templates**:

- Aangifte IB HTML Report (hierarchical view)
- STR Invoices (NL/EN)
- BTW Aangifte HTML Report
- Toeristenbelasting Report

---

## Template Types

### HTML Reports (Viewing/Analysis - Customizable)

**Location**: `backend/templates/html/`

**Purpose**: Internal viewing and analysis  
**Audience**: Business owner, accountant  
**Customizable**: YES (per tenant)  
**Status**: ✅ Implemented and working

### XBRL Forms (Official Submission - NOT Customizable)

**Location**: `.kiro/specs/FIN/AANGIFTE_XBRL/`

**Purpose**: Official tax submission to Belastingdienst  
**Audience**: Tax authority  
**Customizable**: NO (must use official format)  
**Status**: ⏸️ Postponed until after Railway migration

---

## Related Documentation

### Template System

- `backend/src/services/template_service.py` - Template service implementation
- `backend/src/report_generators/` - Report generator functions
- `backend/templates/html/` - HTML template files

### XBRL Specification

- `.kiro/specs/FIN/AANGIFTE_XBRL/` - Complete XBRL specification

---

**Last Updated**: January 31, 2026  
**XBRL Spec Location**: `.kiro/specs/FIN/AANGIFTE_XBRL/`
