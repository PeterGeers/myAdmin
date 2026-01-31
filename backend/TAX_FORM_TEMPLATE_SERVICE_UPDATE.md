# Tax Form Generation - TemplateService Integration

**Date**: January 31, 2026  
**Status**: ✅ Completed  
**Task**: Update tax form generation to use TemplateService

---

## Overview

Updated all HTML tax report generation routes to use the TemplateService for consistent template loading and field mapping application, replacing manual placeholder replacement.

---

## Changes Made

### 1. BTW Aangifte Route (`backend/src/app.py`)

**Route**: `/api/btw/generate-report`

**Changes**:

- Added TemplateService initialization
- Implemented template metadata retrieval from database
- Added Google Drive template fetching with filesystem fallback
- Replaced manual placeholder replacement with `template_service.apply_field_mappings()`
- Maintained backward compatibility with filesystem templates

**Pattern**:

```python
# Initialize TemplateService
template_service = TemplateService(db)

# Try to get template from database/Google Drive
metadata = template_service.get_template_metadata(administration, 'btw_aangifte_html')

if metadata:
    # Load from Google Drive
    template_content = template_service.fetch_template_from_drive(...)
    field_mappings = metadata.get('field_mappings', {})
else:
    # Fallback to filesystem
    with open(template_path, 'r') as f:
        template_content = f.read()
    field_mappings = {...}  # Default mappings

# Apply field mappings
html_report = template_service.apply_field_mappings(template_content, template_data, field_mappings)
```

---

### 2. Aangifte IB Export Route (`backend/src/app.py`)

**Route**: `/api/reports/aangifte-ib-export`

**Changes**:

- Added TemplateService initialization
- Implemented template metadata retrieval from database
- Added Google Drive template fetching with filesystem fallback
- Replaced manual placeholder replacement with `template_service.apply_field_mappings()`
- Maintained backward compatibility with filesystem templates

**Pattern**: Same as BTW Aangifte (see above)

---

### 3. Toeristenbelasting Processor (`backend/src/toeristenbelasting_processor.py`)

**Changes**:

- Added `from services.template_service import TemplateService` import
- Added logging support
- Updated `generate_toeristenbelasting_report()` method to use TemplateService
- Implemented template metadata retrieval from database
- Added Google Drive template fetching with filesystem fallback
- Replaced manual placeholder replacement with `template_service.apply_field_mappings()`
- Maintained backward compatibility with filesystem templates

**Pattern**: Same as BTW Aangifte (see above)

---

## Benefits

### 1. Consistency

- All tax report routes now use the same TemplateService pattern
- Consistent with STR invoice generation (already using TemplateService)
- Unified approach to template management across the application

### 2. Flexibility

- Templates can be stored in Google Drive (tenant-specific)
- Field mappings can be configured per tenant in database
- Supports advanced features (formatting, transformations, conditionals)

### 3. Maintainability

- Centralized template logic in TemplateService
- Easier to add new template types
- Clearer separation of concerns (data generation vs template rendering)

### 4. Backward Compatibility

- Graceful fallback to filesystem templates if database/Google Drive unavailable
- No breaking changes to existing functionality
- Existing templates continue to work

---

## Testing

### Integration Tests

Created `backend/tests/integration/test_template_service_integration.py`:

- ✅ TemplateService initialization
- ✅ Simple field mapping application
- ✅ HTML content field mapping (pre-generated table rows)
- ✅ Missing field handling with defaults
- ✅ BTW Aangifte template structure
- ✅ Aangifte IB template structure

**Result**: 6/6 tests passing

### Unit Tests

Verified existing unit tests still pass:

- ✅ `test_btw_aangifte_generator.py` - 18/18 tests passing
- ✅ `test_toeristenbelasting_generator.py` - 11/11 tests passing

---

## Migration Path

### Current State (Phase 2.5)

- ✅ Templates stored in filesystem (`backend/templates/html/`)
- ✅ Routes use TemplateService with filesystem fallback
- ✅ Field mappings JSON files documented

### Next Steps (Phase 2.4 - Already Completed)

- ✅ Templates uploaded to tenant Google Drives
- ✅ Template metadata stored in `tenant_template_config` table
- ✅ Routes automatically use Google Drive templates when available

### Future Enhancements (Phase 2.6)

- Template preview and validation API
- Frontend UI for template management
- Approval workflow for template changes

---

## Field Mappings

### BTW Aangifte

**Template Type**: `btw_aangifte_html`  
**Fields**: administration, year, quarter, end_date, generated_date, balance_rows, quarter_rows, received_btw, prepaid_btw, payment_instruction  
**Documentation**: `backend/templates/html/BTW_AANGIFTE_FIELD_MAPPINGS.md`

### Aangifte IB

**Template Type**: `aangifte_ib_html`  
**Fields**: year, administration, generated_date, table_rows  
**Documentation**: `backend/templates/html/AANGIFTE_IB_FIELD_MAPPINGS.md`

### Toeristenbelasting

**Template Type**: `toeristenbelasting_html`  
**Fields**: year, next_year, datum, functie, telefoonnummer, email, naam, plaats, periode_van, periode_tm, aantal_kamers, aantal_slaapplaatsen, totaal_verhuurde_nachten, cancelled_nachten, verhuurde_kamers_inwoners, totaal_belastbare_nachten, kamerbezettingsgraad, bedbezettingsgraad, saldo_toeristenbelasting, ontvangsten_excl_btw_excl_toeristenbelasting, ontvangsten_logies_inwoners, kortingen_provisie_commissie, no_show_omzet, totaal_2_3_4, belastbare_omzet_logies, verwachte_belastbare_omzet_volgend_jaar  
**Documentation**: `backend/templates/html/TOERISTENBELASTING_FIELD_MAPPINGS.md`

---

## Architecture

### Template Loading Flow

```
1. Route receives request
   ↓
2. Generate report data using report_generators module
   ↓
3. Initialize TemplateService
   ↓
4. Try to get template metadata from database
   ├─ Success: Fetch template from Google Drive
   └─ Failure: Load template from filesystem (fallback)
   ↓
5. Apply field mappings using TemplateService
   ↓
6. Return HTML to frontend
```

### Data Flow

```
Database Query → report_generators → Template Data → TemplateService → HTML Output
                                                           ↓
                                              Template (Google Drive or Filesystem)
                                                           ↓
                                              Field Mappings (Database or Default)
```

---

## Notes

### Official XBRL Tax Forms

The official XBRL tax forms (IB Aangifte XBRL, BTW Aangifte XBRL) have been moved to a separate specification at `.kiro/specs/FIN/AANGIFTE_XBRL/` and will be implemented post-Railway migration. This task focused only on HTML reports.

### Template Types

- **HTML Reports** (this task): Customizable per tenant, for viewing/analysis
- **XBRL Tax Forms** (future): Official schemas, not customizable, for submission to Belastingdienst

---

## Related Files

### Modified Files

- `backend/src/app.py` - Updated BTW and Aangifte IB routes
- `backend/src/toeristenbelasting_processor.py` - Updated to use TemplateService

### New Files

- `backend/tests/integration/test_template_service_integration.py` - Integration tests

### Documentation

- `backend/templates/html/BTW_AANGIFTE_FIELD_MAPPINGS.md`
- `backend/templates/html/AANGIFTE_IB_FIELD_MAPPINGS.md`
- `backend/templates/html/TOERISTENBELASTING_FIELD_MAPPINGS.md`

---

## Completion Checklist

- ✅ Updated BTW Aangifte route to use TemplateService
- ✅ Updated Aangifte IB export route to use TemplateService
- ✅ Updated Toeristenbelasting processor to use TemplateService
- ✅ Created integration tests
- ✅ Verified existing unit tests pass
- ✅ Maintained backward compatibility
- ✅ Documented changes

---

**Status**: Task completed successfully. All tax form HTML reports now use TemplateService for consistent template management.
