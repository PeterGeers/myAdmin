# Financial Report XLSX - TemplateService Integration

**Date**: January 31, 2026  
**Task**: Update financial report generation to use TemplateService  
**Status**: ✅ Complete

---

## Overview

Updated the financial report XLSX generation to use the centralized `TemplateService` for template management, following the same pattern as other report generators (Aangifte IB, BTW Aangifte, STR Invoices, Toeristenbelasting).

---

## Changes Made

### 1. Created `financial_report_generator.py`

**Location**: `backend/src/report_generators/financial_report_generator.py`

**Purpose**: Separate business logic from the XLSX export processor

**Functions**:

- `make_ledgers(db, year, administration)` - Retrieves ledger data with beginning balances
- `prepare_financial_report_data(db, administration, year)` - Prepares complete report data with metadata

**Why**: This follows the established pattern where report generators handle data retrieval and formatting, while processors handle output generation.

### 2. Updated `xlsx_export.py`

**Changes**:

- Added `TemplateService` initialization in `__init__()`
- Updated `_get_template_path()` to use `TemplateService.get_template_metadata()`
- Updated `_get_output_base_path()` to use `TemplateService.get_template_metadata()`
- Updated `make_ledgers()` to call `financial_report_generator.make_ledgers()`
- Added logging throughout

**Before**:

```python
def _get_template_path(self, administration):
    # Direct database query
    query = "SELECT field_mappings FROM tenant_template_config..."
    results = self.db.execute_query(query, (administration,))
    # Parse JSON manually
    ...
```

**After**:

```python
def _get_template_path(self, administration):
    # Use TemplateService
    metadata = self.template_service.get_template_metadata(
        administration,
        'financial_report_xlsx'
    )
    if metadata and metadata.get('field_mappings'):
        template_path = metadata['field_mappings'].get('template_path')
        ...
```

### 3. Updated `report_generators/__init__.py`

Added `financial_report_generator` to exports:

```python
from . import financial_report_generator

__all__ = [
    'generate_table_rows',
    'str_invoice_generator',
    'btw_aangifte_generator',
    'toeristenbelasting_generator',
    'financial_report_generator',  # NEW
]
```

### 4. Created Unit Tests

**Location**: `backend/tests/unit/test_financial_report_generator.py`

**Tests** (7 total, all passing):

- `test_make_ledgers_with_balance_and_transactions` - Tests normal operation
- `test_make_ledgers_no_balance_data` - Tests with only transactions
- `test_make_ledgers_no_transactions` - Tests with only balance data
- `test_make_ledgers_empty_data` - Tests with no data
- `test_prepare_financial_report_data_success` - Tests successful data preparation
- `test_prepare_financial_report_data_empty` - Tests with empty data
- `test_prepare_financial_report_data_error` - Tests error handling

### 5. Updated Existing Tests

**File**: `backend/tests/unit/test_xlsx_export.py`

**Change**: Updated `test_init` to check for `default_output_base_path` instead of `output_base_path` and verify `template_service` is initialized.

---

## Benefits

### 1. Consistency

- All report generators now use the same pattern
- Centralized template management through `TemplateService`
- Consistent error handling and logging

### 2. Maintainability

- Business logic separated from output generation
- Easier to test individual components
- Clear separation of concerns

### 3. Flexibility

- Template paths can be configured per tenant
- Easy to add new output formats in the future
- Supports future Google Drive/S3 integration

### 4. Backward Compatibility

- ✅ All existing functionality preserved
- ✅ All existing tests pass (19/19)
- ✅ No breaking changes
- ✅ Fallback to default paths if not configured

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Flask Route                              │
│              (aangifte_ib_xlsx_export)                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              XLSXExportProcessor                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Uses TemplateService for:                           │   │
│  │  - Template path retrieval                           │   │
│  │  - Output path retrieval                             │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Uses financial_report_generator for:                │   │
│  │  - Data retrieval (make_ledgers)                     │   │
│  │  - Data preparation                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Handles:                                            │   │
│  │  - Excel file generation (write_workbook)            │   │
│  │  - Google Drive file downloads (export_files)        │   │
│  │  - Progress reporting                                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Database / Google Drive                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Configuration

Template configuration is stored in `tenant_template_config` table:

```sql
SELECT administration, template_type, field_mappings
FROM tenant_template_config
WHERE template_type = 'financial_report_xlsx';
```

**Example field_mappings**:

```json
{
  "template_path": "C:\\Users\\peter\\OneDrive\\Admin\\templates\\template.xlsx",
  "output_base_path": "C:\\Users\\peter\\OneDrive\\Admin\\reports",
  "configured_date": "2026-01-31"
}
```

---

## Usage

### Current Usage (No Changes Required)

```python
# In Flask route
xlsx_processor = XLSXExportProcessor(test_mode=False)
results = xlsx_processor.generate_xlsx_export(['GoodwinSolutions'], [2024])
```

### How It Works Now

1. **Template Path Retrieval**:
   - `XLSXExportProcessor` calls `TemplateService.get_template_metadata()`
   - TemplateService queries database for configuration
   - Returns template path or falls back to default

2. **Data Generation**:
   - `XLSXExportProcessor.make_ledgers()` calls `financial_report_generator.make_ledgers()`
   - Generator retrieves data from database
   - Returns formatted ledger data

3. **Excel Generation**:
   - `XLSXExportProcessor.write_workbook()` creates Excel file
   - Uses template from configured path
   - Saves to configured output path

4. **File Export**:
   - `XLSXExportProcessor.export_files()` downloads Google Drive files
   - Creates folder structure
   - Generates download log

---

## Testing

### Run All Tests

```bash
cd backend

# Test financial report generator
python -m pytest tests/unit/test_financial_report_generator.py -v

# Test XLSX export processor
python -m pytest tests/unit/test_xlsx_export.py -v
```

### Test Results

- ✅ `test_financial_report_generator.py`: 7/7 passed
- ✅ `test_xlsx_export.py`: 19/19 passed
- ✅ **Total**: 26/26 passed

---

## Migration Notes

### For Developers

- No code changes required in routes or calling code
- All existing functionality preserved
- New logging provides better visibility

### For Deployment

- Configuration is optional (uses defaults if not set)
- Can configure per-tenant paths in database
- Supports future Google Drive/S3 integration

---

## Future Enhancements

### Phase 1 (Current) ✅

- Use TemplateService for path management
- Separate business logic into generator module
- Maintain backward compatibility

### Phase 2 (Future)

- Add support for Google Drive template storage
- Add support for S3 output storage
- Add template versioning

### Phase 3 (Future)

- Add template preview functionality
- Add template validation
- Add custom field mappings per tenant

---

## Related Files

**Implementation**:

- `backend/src/xlsx_export.py` - Main processor
- `backend/src/report_generators/financial_report_generator.py` - Data generator
- `backend/src/services/template_service.py` - Template management

**Tests**:

- `backend/tests/unit/test_financial_report_generator.py` - Generator tests
- `backend/tests/unit/test_xlsx_export.py` - Processor tests

**Documentation**:

- `backend/templates/xlsx/README.md` - Usage guide
- `backend/templates/xlsx/IMPLEMENTATION_SUMMARY.md` - Previous implementation
- `.kiro/specs/Common/Railway migration/TASKS.md` - Task tracking

---

## Summary

✅ Task complete  
✅ All tests passing (26/26)  
✅ Backward compatible  
✅ No breaking changes  
✅ Follows established patterns  
✅ Ready for production

The financial report XLSX generation now uses the centralized `TemplateService`, making it consistent with other report generators and ready for future enhancements like Google Drive and S3 integration.
