# BTW Aangifte HTML Report - Implementation Summary

## Overview

Successfully converted the BTW Aangifte (VAT Declaration) report from hardcoded HTML generation to a template-based approach, following the same pattern as the Aangifte IB report.

**Implementation Date**: January 31, 2025  
**Status**: ✅ Complete  
**Tests**: 18/18 passing

---

## What Was Implemented

### 1. HTML Template

**File**: `backend/templates/html/btw_aangifte_template.html`

- Clean, structured HTML template with placeholders
- Responsive styling with proper table formatting
- Summary section with calculations
- Link to Belastingdienst portal
- Supports customization per tenant

**Key Features**:

- Balance data table (BTW accounts up to end date)
- Quarter data table (BTW + revenue accounts for quarter)
- Summary section with payment instruction
- Professional styling with color-coded amounts

### 2. Report Generator

**File**: `backend/src/report_generators/btw_aangifte_generator.py`

Implemented comprehensive generator with the following functions:

#### Main Function

- `generate_btw_report(cache, db, administration, year, quarter)` - Main entry point

#### Helper Functions

- `_calculate_quarter_end_date(year, quarter)` - Calculate quarter end dates
- `_get_balance_data(cache, db, administration, end_date)` - Retrieve balance data
- `_get_quarter_data(cache, db, administration, year, quarter)` - Retrieve quarter data
- `_calculate_btw_amounts(balance_data, quarter_data)` - Perform VAT calculations
- `_format_table_rows(data)` - Format data into HTML table rows
- `prepare_template_data(report_data)` - Prepare data for template rendering

#### Key Features

- Uses cache for efficient data retrieval
- Filters by administration, date, and account numbers
- Calculates total balance, received BTW, prepaid BTW
- Generates payment instruction (te betalen/ontvangen)
- HTML escaping for security
- Comprehensive error handling and logging

### 3. Route Update

**File**: `backend/src/app.py`

Updated the `/api/btw/generate-report` route to:

- Use the new generator instead of BTWProcessor
- Load and apply the HTML template
- Replace placeholders with formatted data
- Maintain backward compatibility with existing transaction logic

### 4. Field Mappings Documentation

**File**: `backend/templates/html/BTW_AANGIFTE_FIELD_MAPPINGS.md`

Comprehensive documentation including:

- All template placeholders and their descriptions
- Data source queries and filters
- Calculation logic and formulas
- Customization options per tenant
- Usage examples and code snippets
- Database schema for template storage

### 5. Unit Tests

**File**: `backend/tests/unit/test_btw_aangifte_generator.py`

Created 18 comprehensive unit tests covering:

#### Test Classes

1. **TestQuarterEndDateCalculation** (5 tests)
   - Q1, Q2, Q3, Q4 end dates
   - Invalid quarter handling

2. **TestBTWCalculations** (4 tests)
   - Positive balance (te ontvangen)
   - Negative balance (te betalen)
   - Zero balance
   - Only received BTW accounts

3. **TestTableRowFormatting** (3 tests)
   - Valid data formatting
   - Empty data handling
   - HTML escaping

4. **TestTemplateDataPreparation** (2 tests)
   - Complete data preparation
   - Missing fields handling

5. **TestGetBalanceData** (2 tests)
   - Correct filtering
   - Empty results

6. **TestGetQuarterData** (1 test)
   - Correct filtering by year/quarter

7. **TestGenerateBTWReport** (1 test)
   - End-to-end report generation

**Test Results**: ✅ All 18 tests passing

---

## Architecture

### Data Flow

```
┌─────────────────┐
│   Cache Data    │  (mutaties_cache)
│  (Transactions) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ BTW Generator   │  Filter & Calculate
│  - Balance data │  - By date, admin, accounts
│  - Quarter data │  - Group by account
│  - Calculations │  - Calculate totals
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Structured Data │  Ready for template
│  - balance_rows │
│  - quarter_rows │
│  - calculations │
│  - metadata     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ HTML Template   │  Replace placeholders
│  - Load file    │
│  - Replace {{ }}│
│  - Return HTML  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Final Output   │  HTML Report
└─────────────────┘
```

### Key Design Decisions

1. **Separation of Concerns**
   - Generator: Data processing and business logic
   - Template: Presentation and layout
   - Route: Orchestration and API handling

2. **Reusable Components**
   - Uses common_formatters for consistent formatting
   - Follows same pattern as Aangifte IB generator
   - Can be easily extended for other report types

3. **Security**
   - HTML escaping for all user-provided content
   - Administration filtering in data queries
   - No SQL injection vulnerabilities

4. **Maintainability**
   - Well-documented code with docstrings
   - Comprehensive unit tests
   - Clear error handling and logging

---

## Data Sources

### Balance Data

**Accounts**: 2010, 2020, 2021 (BTW accounts)  
**Filter**: TransactionDate <= quarter_end_date  
**Aggregation**: Sum by account

### Quarter Data

**Accounts**: 2010, 2020, 2021 (BTW) + 8001, 8002, 8003 (Revenue)  
**Filter**: jaar = year AND kwartaal = quarter  
**Aggregation**: Sum by account

### Calculations

- **Total Balance** = Sum of all balance data
- **Received BTW** = Sum of accounts 2020, 2021 from quarter data
- **Prepaid BTW** = Received BTW - Total Balance
- **Payment Instruction** = "€X te betalen" or "€X te ontvangen"

---

## Template Placeholders

| Placeholder                 | Type   | Description                   |
| --------------------------- | ------ | ----------------------------- |
| `{{ administration }}`      | string | Tenant identifier             |
| `{{ year }}`                | int    | Report year                   |
| `{{ quarter }}`             | int    | Quarter number (1-4)          |
| `{{ end_date }}`            | date   | Quarter end date              |
| `{{ generated_date }}`      | string | Report generation timestamp   |
| `{{ balance_rows }}`        | HTML   | Balance data table rows       |
| `{{ quarter_rows }}`        | HTML   | Quarter data table rows       |
| `{{ payment_instruction }}` | string | Payment instruction           |
| `{{ received_btw }}`        | string | Formatted received BTW amount |
| `{{ prepaid_btw }}`         | string | Formatted prepaid BTW amount  |

---

## Usage Example

```python
from report_generators import btw_aangifte_generator
from mutaties_cache import get_cache
from database import DatabaseManager

# Get cache and database
cache = get_cache()
db = DatabaseManager(test_mode=False)
cache.get_data(db)

# Generate report
report_data = btw_aangifte_generator.generate_btw_report(
    cache=cache,
    db=db,
    administration='GoodwinSolutions',
    year=2025,
    quarter=1
)

# Prepare template data
template_data = btw_aangifte_generator.prepare_template_data(report_data)

# Load template
with open('backend/templates/html/btw_aangifte_template.html', 'r') as f:
    template = f.read()

# Replace placeholders
html = template
for key, value in template_data.items():
    html = html.replace(f'{{{{ {key} }}}}', str(value))

# Save or return HTML
print(html)
```

---

## Testing

### Run Unit Tests

```bash
python -m pytest backend/tests/unit/test_btw_aangifte_generator.py -v
```

### Test Coverage

- ✅ Quarter end date calculation
- ✅ Balance data retrieval and filtering
- ✅ Quarter data retrieval and filtering
- ✅ BTW amount calculations
- ✅ Table row formatting
- ✅ HTML escaping
- ✅ Template data preparation
- ✅ End-to-end report generation

---

## Migration from BTWProcessor

### Before (Hardcoded)

```python
# btw_processor.py
def _generate_html_report(self, ...):
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>...</head>
    <body>
        <h1>BTW aangifte</h1>
        ...
    </body>
    </html>
    """
    return html_content
```

### After (Template-based)

```python
# btw_aangifte_generator.py
def generate_btw_report(cache, db, administration, year, quarter):
    # Generate structured data
    return {
        'balance_rows': formatted_rows,
        'quarter_rows': formatted_rows,
        'calculations': {...},
        'metadata': {...}
    }

# app.py
template = load_template('btw_aangifte_template.html')
html = apply_template(template, report_data)
```

### Benefits

1. **Customizable**: Tenants can modify templates without code changes
2. **Maintainable**: Template changes don't require deployment
3. **Testable**: Generator logic can be unit tested independently
4. **Consistent**: Uses same pattern as other reports
5. **Secure**: Proper HTML escaping and validation

---

## Next Steps

### Phase 2 Completion

- [x] BTW Aangifte HTML Report converted ✅
- [ ] Toeristenbelasting HTML Report (next task)
- [ ] IB Aangifte XBRL (official tax form)
- [ ] BTW Aangifte XBRL (official tax form)

### Future Enhancements

- [ ] Add support for multiple languages (currently Dutch only)
- [ ] Add PDF export option
- [ ] Add email delivery option
- [ ] Add template preview functionality
- [ ] Add template validation
- [ ] Store templates in Google Drive per tenant

---

## Related Files

### Implementation

- `backend/templates/html/btw_aangifte_template.html` - HTML template
- `backend/src/report_generators/btw_aangifte_generator.py` - Generator
- `backend/src/app.py` - Route handler (BTW section)

### Documentation

- `backend/templates/html/BTW_AANGIFTE_FIELD_MAPPINGS.md` - Field mappings
- `backend/templates/html/BTW_AANGIFTE_IMPLEMENTATION_SUMMARY.md` - This file

### Tests

- `backend/tests/unit/test_btw_aangifte_generator.py` - Unit tests (18 tests)

### Legacy (for reference)

- `backend/src/btw_processor.py` - Original hardcoded implementation

---

## Conclusion

The BTW Aangifte HTML Report has been successfully converted to a template-based approach, following the established pattern from the Aangifte IB report. The implementation includes:

✅ Clean HTML template with placeholders  
✅ Comprehensive generator with business logic  
✅ Updated route handler  
✅ Complete field mappings documentation  
✅ 18 passing unit tests  
✅ No diagnostic errors

The report is now ready for tenant customization and can be easily maintained and extended in the future.
