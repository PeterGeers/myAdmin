# Template Service - Complete Documentation

**Last Updated**: January 30, 2026  
**Status**: ✅ Phase 2.2 Complete  
**Location**: `backend/src/services/template_service.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Implementation Summary](#implementation-summary)
3. [Core Methods](#core-methods)
4. [Field Mapping System](#field-mapping-system)
5. [Output Generation](#output-generation)
6. [Testing](#testing)
7. [Usage Examples](#usage-examples)
8. [Integration](#integration)
9. [Security & Performance](#security--performance)

---

## Overview

The `TemplateService` is a core component of the Railway migration that manages XML templates with flexible field mappings and multi-format output generation. It enables tenant-specific template customization and supports multiple output formats (HTML, XML, Excel, PDF).

### Key Features

- ✅ Database-backed template configuration
- ✅ Flexible field mapping with nested data support
- ✅ Multiple formatting types (currency, date, number, text)
- ✅ Value transformations (abs, round, uppercase, lowercase)
- ✅ Conditional logic support
- ✅ Multi-format output (HTML, XML, Excel*, PDF*)
- ✅ Tenant isolation and security
- ✅ Comprehensive error handling

\*Excel and PDF generation are placeholders for Phase 2.5

---

## Implementation Summary

### File Details

- **Path**: `backend/src/services/template_service.py`
- **Lines of Code**: ~640 lines
- **Dependencies**:
  - `database.py` (DatabaseManager)
  - `google_drive_service.py` (GoogleDriveService)
  - Standard libraries: `json`, `logging`, `xml.etree.ElementTree`, `datetime`, `io`

### Implementation Status

| Component         | Status         | Notes                           |
| ----------------- | -------------- | ------------------------------- |
| Core Service      | ✅ Complete    | All methods implemented         |
| Unit Tests        | ✅ Complete    | 41/43 tests passing (2 skipped) |
| Integration Tests | ⏳ Pending     | Phase 2.6                       |
| HTML Output       | ✅ Complete    | Fully tested                    |
| XML Output        | ✅ Complete    | Fully tested                    |
| Excel Output      | ⏳ Placeholder | Phase 2.5                       |
| PDF Output        | ⏳ Placeholder | Phase 2.5                       |

---

## Core Methods

### 1. get_template_metadata(administration, template_type)

Retrieves template metadata from the `tenant_template_config` table.

**Signature:**

```python
def get_template_metadata(
    self,
    administration: str,
    template_type: str
) -> Optional[Dict[str, Any]]
```

**Parameters:**

- `administration`: Tenant identifier (e.g., 'GoodwinSolutions')
- `template_type`: Type of template (e.g., 'financial_report', 'str_invoice')

**Returns:**

- Dictionary containing:
  - `template_file_id`: Google Drive file ID
  - `field_mappings`: Parsed JSON field mappings
  - `is_active`: Boolean indicating if template is active
  - `created_at`, `updated_at`: Timestamps
- `None` if template not found

**Example:**

```python
metadata = service.get_template_metadata('GoodwinSolutions', 'financial_report')
print(metadata['template_file_id'])  # Google Drive file ID
print(metadata['field_mappings'])    # Field mapping configuration
```

**Status**: ✅ Fully implemented and tested

---

### 2. fetch_template_from_drive(file_id, administration)

Fetches XML template content from Google Drive using tenant-specific credentials.

**Signature:**

```python
def fetch_template_from_drive(
    self,
    file_id: str,
    administration: str
) -> str
```

**Parameters:**

- `file_id`: Google Drive file ID
- `administration`: Tenant identifier for credential lookup

**Returns:**

- String containing XML template content

**Raises:**

- `Exception`: If file download fails or credentials are invalid

**Example:**

```python
template_xml = service.fetch_template_from_drive(
    'abc123xyz',
    'GoodwinSolutions'
)
print(template_xml)  # XML template content
```

**Status**: ✅ Fully implemented (integration tests pending)

---

### 3. apply_field_mappings(template_xml, data, mappings)

Applies field mappings to template placeholders, replacing them with formatted data values.

**Signature:**

```python
def apply_field_mappings(
    self,
    template_xml: str,
    data: Dict[str, Any],
    mappings: Dict[str, Any]
) -> str
```

**Parameters:**

- `template_xml`: XML template with placeholders (e.g., `{{ guest_name }}`)
- `data`: Dictionary containing data values
- `mappings`: Field mapping configuration

**Returns:**

- Processed XML string with placeholders replaced

**Features:**

1. **Field Replacement**: Replaces `{{ field_name }}` with actual values
2. **Nested Data Access**: Supports dot notation (e.g., `guest.name`)
3. **Value Formatting**: Currency, date, number, text formatting
4. **Transformations**: abs, round, uppercase, lowercase
5. **Default Values**: Uses defaults when data is missing
6. **Conditional Logic**: Evaluates and applies conditional rules

**Example:**

```python
template = "<invoice><guest>{{ guest_name }}</guest></invoice>"
data = {"guest": {"name": "john doe"}}
mappings = {
    "fields": {
        "guest_name": {
            "path": "guest.name",
            "transform": "uppercase"
        }
    }
}

result = service.apply_field_mappings(template, data, mappings)
# Result: "<invoice><guest>JOHN DOE</guest></invoice>"
```

**Status**: ✅ Fully implemented and tested

---

### 4. generate_output(template, data, output_format)

Generates output in specified format from processed template.

**Signature:**

```python
def generate_output(
    self,
    template: str,
    data: Dict[str, Any],
    output_format: str
) -> Any
```

**Parameters:**

- `template`: Template content (with field mappings already applied)
- `data`: Data dictionary (may be used for additional processing)
- `output_format`: Output format ('html', 'xml', 'excel', 'pdf')

**Returns:**

- Format-dependent output:
  - `'html'`: HTML string
  - `'xml'`: XML string
  - `'excel'`: BytesIO object (when implemented)
  - `'pdf'`: BytesIO object (when implemented)

**Supported Formats:**

- ✅ HTML - Fully implemented
- ✅ XML - Fully implemented with validation
- ⏳ Excel - Placeholder (NotImplementedError)
- ⏳ PDF - Placeholder (NotImplementedError)

**Example:**

```python
html_output = service.generate_output(processed_template, data, 'html')
xml_output = service.generate_output(processed_template, data, 'xml')
```

**Status**: ✅ Core functionality implemented (HTML/XML complete)

---

## Field Mapping System

### Field Configuration Structure

```python
{
    "fields": {
        "field_name": {
            "path": "nested.data.path",      # Dot notation for nested data
            "format": "currency",             # Format type
            "transform": "abs",               # Optional transformation
            "default": "0.00"                 # Default value if missing
        }
    },
    "formatting": {
        "currency": "EUR",                    # Currency symbol
        "date_format": "DD-MM-YYYY",         # Date format
        "locale": "nl-NL"                    # Locale for formatting
    },
    "conditionals": [
        {
            "field": "invoice_total",
            "operator": "gt",
            "value": 100,
            "action": "show"
        }
    ]
}
```

### Supported Format Types

#### 1. Currency Formatting

**Supported Currencies:**

- EUR (€)
- USD ($)
- GBP (£)

**Example:**

```python
{
    "path": "invoice.total",
    "format": "currency"
}
# Input: 150.50
# Output: "€ 150.50" (with EUR formatting)
```

#### 2. Date Formatting

**Supported Formats:**

- `DD-MM-YYYY` (30-01-2026)
- `YYYY-MM-DD` (2026-01-30)
- `MM/DD/YYYY` (01/30/2026)

**Example:**

```python
{
    "path": "invoice.date",
    "format": "date"
}
# Input: "2026-01-30"
# Output: "30-01-2026" (with DD-MM-YYYY formatting)
```

#### 3. Number Formatting

**Features:**

- Configurable decimal places
- Thousand separators
- Locale-aware formatting

**Example:**

```python
{
    "path": "quantity",
    "format": "number"
}
# Input: 1234.56
# Output: "1,234.56"
```

#### 4. Text Formatting

**Features:**

- Plain text passthrough
- Optional transformations

**Example:**

```python
{
    "path": "guest.name",
    "format": "text",
    "transform": "uppercase"
}
# Input: "john doe"
# Output: "JOHN DOE"
```

### Supported Transformations

#### Mathematical Transformations

1. **abs** - Absolute value

   ```python
   # Input: -150.50
   # Output: 150.50
   ```

2. **round** - Round to 2 decimals
   ```python
   # Input: 150.567
   # Output: 150.57
   ```

#### Text Transformations

1. **uppercase** - Convert to uppercase

   ```python
   # Input: "john doe"
   # Output: "JOHN DOE"
   ```

2. **lowercase** - Convert to lowercase
   ```python
   # Input: "JOHN DOE"
   # Output: "john doe"
   ```

### Conditional Logic

**Supported Operators:**

- `eq` - Equal
- `ne` - Not equal
- `gt` - Greater than
- `lt` - Less than
- `gte` - Greater than or equal
- `lte` - Less than or equal
- `contains` - String contains

**Example:**

```python
{
    "field": "invoice_total",
    "operator": "gt",
    "value": 100,
    "action": "show"
}
# Shows content only if invoice_total > 100
```

---

## Output Generation

### HTML Output

**Implementation:**

```python
def _generate_html(self, template: str, data: Dict[str, Any]) -> str:
    """Generate HTML output from template."""
    return template  # Direct passthrough
```

**Features:**

- Direct passthrough of processed template
- No additional transformation needed
- Field mappings already applied
- Ready for browser rendering

**Use Cases:**

- Web-based reports
- Email templates
- Preview functionality
- Browser-based rendering

**Status**: ✅ Fully implemented and tested

---

### XML Output

**Implementation:**

```python
def _generate_xml(self, template: str, data: Dict[str, Any]) -> str:
    """Generate XML output from template."""
    try:
        ET.fromstring(template)  # Validate XML
        return template
    except ET.ParseError as e:
        logger.warning(f"XML validation failed: {e}")
        return template  # Return anyway
```

**Features:**

- XML validation using ElementTree
- Graceful error handling
- Warning logging for invalid XML
- Returns template even if validation fails

**Use Cases:**

- Data exchange formats
- API responses
- System integrations
- Structured data storage

**Status**: ✅ Fully implemented and tested

---

### Excel Output (Placeholder)

**Planned Implementation:**

- Parse template XML structure
- Map data to Excel cells
- Apply formatting (currency, dates, numbers)
- Generate workbook with multiple sheets
- Return as BytesIO for download

**Planned Libraries:**

- openpyxl or xlsxwriter

**Use Cases:**

- Financial reports
- Data exports
- Spreadsheet analysis
- Batch processing

**Status**: ⏳ Placeholder (Phase 2.5)

---

### PDF Output (Placeholder)

**Planned Implementation:**

- Convert HTML template to PDF
- Apply CSS styling
- Handle page breaks
- Generate table of contents
- Return as BytesIO for download

**Planned Libraries:**

- reportlab or weasyprint

**Use Cases:**

- Printable reports
- Official documents
- Invoices
- Tax forms

**Status**: ⏳ Placeholder (Phase 2.5)

---

## Testing

### Unit Tests

**Test File**: `backend/tests/unit/test_template_service.py`

**Test Results:**

- ✅ 41 tests passed
- ⏭️ 2 tests skipped (Google Drive mocking)
- ⏱️ Execution time: 0.45 seconds
- 📊 Pass rate: 100% (excluding skipped)

**Test Coverage:**

#### Initialization (1 test)

- ✅ Service initialization with database manager

#### Template Metadata (6 tests)

- ✅ Successful metadata retrieval
- ✅ Template not found handling
- ✅ Dict field mappings handling
- ✅ Invalid JSON handling
- ✅ Database error handling

#### Field Mapping (3 tests)

- ✅ Successful field mapping application
- ✅ Default values when data missing
- ✅ Empty mappings handling

#### Field Value Extraction (3 tests)

- ✅ Nested path extraction
- ✅ Missing path with defaults
- ✅ None value handling

#### Formatting (4 tests)

- ✅ Currency formatting (EUR, USD)
- ✅ Date formatting (DD-MM-YYYY, YYYY-MM-DD)
- ✅ Number formatting

#### Transformations (5 tests)

- ✅ Absolute value transform
- ✅ Round transform
- ✅ Uppercase transform
- ✅ Lowercase transform
- ✅ Invalid transform handling

#### Conditional Evaluation (8 tests)

- ✅ Equality condition
- ✅ Not equal condition
- ✅ Greater than condition
- ✅ Less than condition
- ✅ Greater than or equal condition
- ✅ Less than or equal condition
- ✅ Contains condition
- ✅ Unknown operator handling

#### Output Generation (6 tests)

- ✅ HTML output generation
- ✅ XML output generation
- ✅ Invalid XML handling
- ✅ Excel not implemented (expected exception)
- ✅ PDF not implemented (expected exception)
- ✅ Unsupported format handling

#### Edge Cases (4 tests)

- ✅ Format value with None
- ✅ Invalid currency value
- ✅ Invalid date value
- ✅ Invalid number value

#### Integration-Style (1 test)

- ✅ Complete STR invoice workflow

### Running Tests

```bash
# Run all template service tests
pytest backend/tests/unit/test_template_service.py -v

# Run specific test categories
pytest backend/tests/unit/test_template_service.py -k "html or xml" -v
pytest backend/tests/unit/test_template_service.py -k "formatting" -v
pytest backend/tests/unit/test_template_service.py -k "transform" -v
```

---

## Usage Examples

### Example 1: Complete Template Processing Workflow

```python
from services.template_service import TemplateService
from database import DatabaseManager

# Initialize service
db = DatabaseManager()
template_service = TemplateService(db)

# Step 1: Get template metadata
metadata = template_service.get_template_metadata(
    'GoodwinSolutions',
    'financial_report'
)

# Step 2: Fetch template from Google Drive
template_xml = template_service.fetch_template_from_drive(
    metadata['template_file_id'],
    'GoodwinSolutions'
)

# Step 3: Prepare data
data = {
    'company_name': 'Goodwin Solutions',
    'report_date': '2026-01-30',
    'total_revenue': 150000.00,
    'total_expenses': 95000.00,
    'net_profit': 55000.00
}

# Step 4: Apply field mappings
processed_template = template_service.apply_field_mappings(
    template_xml,
    data,
    metadata['field_mappings']
)

# Step 5: Generate output
html_output = template_service.generate_output(
    processed_template,
    data,
    'html'
)

# Use the output
print(html_output)  # Display or send via email
```

### Example 2: STR Invoice Generation

```python
# Prepare STR invoice data
invoice_data = {
    'guest': {
        'name': 'John Doe',
        'email': 'john@example.com'
    },
    'invoice': {
        'number': 'INV-2026-001',
        'date': '2026-01-30',
        'total': 450.00,
        'tax': 81.00
    },
    'items': [
        {'description': 'Accommodation', 'amount': 350.00},
        {'description': 'Tourist Tax', 'amount': 19.00}
    ]
}

# Get template and process
metadata = template_service.get_template_metadata('GoodwinSolutions', 'str_invoice')
template_xml = template_service.fetch_template_from_drive(
    metadata['template_file_id'],
    'GoodwinSolutions'
)

# Apply mappings
processed = template_service.apply_field_mappings(
    template_xml,
    invoice_data,
    metadata['field_mappings']
)

# Generate PDF (when implemented)
# pdf_output = template_service.generate_output(processed, invoice_data, 'pdf')
```

### Example 3: Error Handling

```python
try:
    # Attempt to get template
    metadata = template_service.get_template_metadata(
        'GoodwinSolutions',
        'unknown_template'
    )

    if metadata is None:
        print("Template not found")
        # Handle missing template

except Exception as e:
    print(f"Error: {e}")
    # Handle error gracefully
```

---

## Integration

### Database Integration

**Table**: `tenant_template_config`

```sql
CREATE TABLE tenant_template_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    template_file_id VARCHAR(255) NOT NULL,
    field_mappings JSON,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_template (administration, template_type),
    INDEX idx_tenant (administration)
);
```

**Usage:**

- Uses `DatabaseManager` for all database operations
- Queries `tenant_template_config` table
- Supports test mode via DatabaseManager

### Google Drive Integration

**Service**: `GoogleDriveService`

**Features:**

- Tenant-specific authentication
- File download via Google Drive API
- Credential management via `CredentialService`

**Usage:**

```python
# Fetch template from Google Drive
drive_service = GoogleDriveService(administration)
template_content = drive_service.download_file(file_id)
```

### Credential Service Integration

**Service**: `CredentialService`

**Features:**

- Encrypted credential storage
- Tenant isolation
- AES-256 encryption

**Usage:**

- Indirectly used via `GoogleDriveService`
- Tenant credentials retrieved from database
- Automatic encryption/decryption

---

## Security & Performance

### Security Features

1. **No Code Execution**: Safe template processing without eval()
2. **Input Validation**: All parameters validated
3. **Safe Error Messages**: No sensitive data in error messages
4. **Tenant Isolation**: Strict tenant credential separation
5. **Encrypted Storage**: All credentials encrypted at rest

### Performance Optimizations

1. **Efficient String Replacement**: Single-pass template processing
2. **Minimal Object Creation**: Reuse objects where possible
3. **Early Return on Errors**: Fail fast for better performance
4. **Lazy Evaluation**: Conditionals evaluated only when needed

### Future Optimizations (Phase 2.5)

1. **Template Caching**: Cache frequently used templates
2. **Field Mapping Compilation**: Pre-compile field mappings
3. **Batch Processing**: Process multiple templates in parallel
4. **Async Generation**: Support async output generation

---

## Design Patterns

### Patterns Used

1. **Service Pattern**: Single responsibility for template management
2. **Dependency Injection**: DatabaseManager injected via constructor
3. **Factory Pattern**: Output generation based on format type
4. **Strategy Pattern**: Different formatting strategies per type
5. **Template Method**: Consistent processing pipeline

### Best Practices

- ✅ Comprehensive docstrings
- ✅ Type hints for all methods
- ✅ Descriptive variable names
- ✅ Modular helper methods
- ✅ Separation of concerns
- ✅ DRY principle (no code duplication)

---

## Next Steps

### Phase 2.3: Convert Templates to XML

- [ ] Convert financial report template
- [ ] Convert STR invoice template
- [ ] Convert BTW Aangifte template
- [ ] Convert Toeristenbelasting template
- [ ] Convert IB Aangifte template

### Phase 2.4: Migrate Templates to Google Drive

- [ ] Create template folders in tenant Google Drives
- [ ] Upload XML templates
- [ ] Store metadata in database

### Phase 2.5: Update Report Generation Routes

- [ ] Update financial report generation
- [ ] Update STR invoice generation
- [ ] Update tax form generation
- [ ] Implement Excel output generation
- [ ] Implement PDF output generation

---

## References

- **Implementation**: `backend/src/services/template_service.py`
- **Unit Tests**: `backend/tests/unit/test_template_service.py`
- **Task List**: `.kiro/specs/Common/Railway migration/TASKS.md`
- **Field Mappings**: `.kiro/specs/Common/Railway migration/FIELD_MAPPINGS_DOCUMENTATION.md`
- **Impact Analysis**: `.kiro/specs/Common/Railway migration/IMPACT_ANALYSIS_SUMMARY.md`

---

**Documentation Complete** - Last Updated: January 30, 2026
