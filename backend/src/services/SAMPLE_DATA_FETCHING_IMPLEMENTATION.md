# Sample Data Fetching Implementation Summary

**Date**: February 1, 2026
**Task**: Implement Sample Data Fetching for Template Preview Service
**Status**: ✅ Completed

## Overview

Implemented comprehensive sample data fetching methods for the TemplatePreviewService to support template preview generation across all template types. The implementation includes robust error handling and fallback mechanisms to ensure preview generation always succeeds.

## Implementation Details

### 1. STR Invoice Sample Data (`_fetch_str_invoice_sample()`)

**Purpose**: Fetch the most recent realised STR booking for invoice preview

**Implementation**:

- Queries `vw_bnb_total` view for most recent realised booking
- Uses `prepare_invoice_data()` from `str_invoice_generator` to format data
- Generates invoice number from reservation code
- Falls back to placeholder data if no bookings found

**Data Source**: Database (vw_bnb_total view)

**Fallback**: Comprehensive placeholder invoice data with all required fields

### 2. BTW Aangifte Sample Data (`_fetch_btw_sample()`)

**Purpose**: Fetch most recent BTW (VAT) quarter data for preview

**Implementation**:

- Calculates current year and quarter
- Attempts to use `generate_btw_report()` from `btw_aangifte_generator`
- Initializes MutatiesCache for data retrieval
- Prepares template data using `prepare_template_data()`
- Falls back to placeholder if generator unavailable or fails

**Data Source**: Database via MutatiesCache

**Fallback**: Placeholder BTW data with sample balance and quarter rows

### 3. Aangifte IB Sample Data (`_fetch_aangifte_ib_sample()`)

**Purpose**: Fetch most recent income tax data for preview

**Implementation**:

- Uses previous year (current year data may be incomplete)
- Attempts to use `generate_table_rows()` from `aangifte_ib_generator`
- Filters MutatiesCache data by year and administration
- Generates table rows from filtered data
- Falls back to placeholder if no data or generator unavailable

**Data Source**: Database via MutatiesCache

**Fallback**: Placeholder income tax data with sample table rows

### 4. Toeristenbelasting Sample Data (`_fetch_toeristenbelasting_sample()`)

**Purpose**: Fetch most recent tourist tax declaration data for preview

**Implementation**:

- Uses current year
- Attempts to use `generate_toeristenbelasting_report()` from generator
- Initializes both MutatiesCache and BNBCache
- Extracts template_data from report
- Falls back to placeholder if generator unavailable or fails

**Data Source**: Database via MutatiesCache and BNBCache

**Fallback**: Placeholder tourist tax data with sample statistics

### 5. Generic Sample Data (`_fetch_generic_sample()`)

**Purpose**: Provide fallback data for unknown template types

**Implementation**:

- Always returns placeholder data
- Includes common fields (administration, year, dates)
- Provides formatted currency and number samples
- Ensures preview generation never fails

**Data Source**: Generated placeholder

**Fallback**: N/A (this is the fallback)

### 6. Error Handling (`_get_placeholder_str_data()`)

**Purpose**: Provide comprehensive placeholder STR invoice data

**Implementation**:

- Complete invoice data structure with all required fields
- Realistic sample values
- Company information included
- Properly formatted dates and amounts

## Key Features

### Robust Error Handling

- All methods wrapped in try-except blocks
- Graceful fallback to placeholder data on any error
- Detailed logging of errors and warnings
- Never returns None (always provides usable data)

### Import Safety

- Imports done inside methods (lazy loading)
- Handles ImportError gracefully
- Falls back if dependencies unavailable
- No hard dependencies on report generators

### Data Quality

- Attempts to use real data first
- Falls back to realistic placeholder data
- Metadata indicates data source (database vs placeholder)
- Includes helpful messages in metadata

### Metadata Structure

All sample data returns include:

```python
{
    'data': {...},  # Template data
    'metadata': {
        'source': 'database' | 'placeholder',
        'record_date': '...',
        'record_id': '...',
        'message': '...'  # Helpful context
    }
}
```

## Testing

### Test Coverage

- 18 unit tests for sample data fetching
- All tests passing (47 total tests in test_template_preview_service.py)
- Tests cover:
  - Successful data fetching
  - No data scenarios
  - Database errors
  - Fallback behavior
  - Data structure validation
  - Routing to correct methods
  - Exception handling

### Test Files

- `backend/tests/unit/test_template_preview_service.py`
  - TestSampleDataFetching class (18 tests)

## Integration Points

### Database

- Uses DatabaseManager for queries
- Queries vw_bnb_total view for STR data
- Uses MutatiesCache for financial data
- Uses BNBCache for booking data

### Report Generators

- Integrates with `str_invoice_generator`
- Integrates with `btw_aangifte_generator`
- Integrates with `aangifte_ib_generator`
- Integrates with `toeristenbelasting_generator`

### Template Service

- Called by `fetch_sample_data()` method
- Routes to appropriate fetcher based on template_type
- Supports all template types:
  - str_invoice_nl
  - str_invoice_en
  - btw_aangifte
  - aangifte_ib
  - toeristenbelasting
  - generic (fallback)

## Files Modified

1. **backend/src/services/template_preview_service.py**
   - Updated `_fetch_str_invoice_sample()` - Real database query
   - Updated `_fetch_btw_sample()` - Generator integration with fallback
   - Updated `_fetch_aangifte_ib_sample()` - Generator integration with fallback
   - Updated `_fetch_toeristenbelasting_sample()` - Generator integration with fallback
   - Updated `_fetch_generic_sample()` - Enhanced placeholder data
   - Updated `_get_placeholder_str_data()` - Better documentation

2. **backend/tests/unit/test_template_preview_service.py**
   - Added TestSampleDataFetching class
   - 18 new unit tests
   - Tests for all sample data methods
   - Tests for routing and error handling

## Benefits

### For Users

- Template previews always work (never fail)
- Real data used when available
- Realistic placeholder data when not
- Clear indication of data source

### For Developers

- Easy to extend with new template types
- Robust error handling
- Well-tested
- Clear separation of concerns

### For System

- No hard dependencies
- Graceful degradation
- Detailed logging
- Performance optimized (lazy imports)

## Next Steps

The sample data fetching implementation is complete and ready for:

1. Integration with preview generation workflow
2. API endpoint implementation
3. Frontend integration
4. End-to-end testing

## Related Documentation

- `.kiro/specs/Common/template-preview-validation/design.md` - Overall design
- `.kiro/specs/Common/Railway migration/TASKS.md` - Task tracking
- `backend/src/services/template_preview_service.py` - Implementation
- `backend/tests/unit/test_template_preview_service.py` - Tests
