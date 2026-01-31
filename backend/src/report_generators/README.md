# Report Generators Module

## Overview

The `report_generators` module contains specialized generator functions that transform raw data into formatted output for various report types. Each generator is responsible for applying business logic, performing calculations, and structuring data in a format ready for template rendering.

## Purpose

This module separates **data transformation logic** from **template rendering**, following the principle of separation of concerns:

- **Report Generators** (this module): Transform raw data → structured output
- **Template Service** (`services/template_service.py`): Apply templates → final output (HTML/XML/PDF)

## Architecture

```
┌─────────────────┐
│   Raw Data      │  (from database/cache)
│   (dict/list)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Report Generator│  (this module)
│  - Business     │  - Apply calculations
│    Logic        │  - Format data
│  - Formatting   │  - Structure output
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Structured Data │  (ready for template)
│   (dict/list)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Template Service│  (services/template_service.py)
│  - Load template│  - Apply field mappings
│  - Render output│  - Generate HTML/XML/PDF
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Final Output   │  (HTML/XML/PDF/Excel)
└─────────────────┘
```

## Module Structure

```
report_generators/
├── __init__.py                    # Package initialization and exports
├── common_formatters.py           # Shared formatting utilities
├── README.md                      # This file
├── aangifte_ib_generator.py       # Aangifte IB report generator (planned)
├── btw_aangifte_generator.py      # BTW Aangifte generator (planned)
└── str_invoice_generator.py       # STR invoice generator (planned)
```

## Common Formatters

The `common_formatters.py` module provides shared utilities used across all generators:

### Currency & Number Formatting

```python
from report_generators.common_formatters import format_currency, format_amount

# Format as currency with symbol
formatted = format_currency(1234.56, currency='EUR')
# Returns: "€ 1,234.56"

# Format as amount without symbol
formatted = format_amount(1234.56, decimals=2)
# Returns: "1,234.56"
```

### Date & Time Formatting

```python
from report_generators.common_formatters import format_date, format_datetime

# Format date
formatted = format_date('2025-01-31', format_type='DD-MM-YYYY')
# Returns: "31-01-2025"

# Format datetime
formatted = format_datetime('2025-01-31 14:30:00')
# Returns: "31-01-2025 14:30:00"
```

### Safe Type Conversion

```python
from report_generators.common_formatters import safe_float, safe_int

# Safely convert to float
value = safe_float('123.45', default=0.0)
# Returns: 123.45

# Safely convert to int
value = safe_int('invalid', default=0)
# Returns: 0
```

### HTML Utilities

```python
from report_generators.common_formatters import escape_html, truncate_text

# Escape HTML special characters
safe_text = escape_html('<script>alert("XSS")</script>')
# Returns: "&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;"

# Truncate long text
short_text = truncate_text('This is a very long text', max_length=10)
# Returns: "This is..."
```

### CSS Class Helpers

```python
from report_generators.common_formatters import get_css_class_for_amount

# Get CSS class based on amount
css_class = get_css_class_for_amount(100.50)
# Returns: "positive"

css_class = get_css_class_for_amount(-50.25)
# Returns: "negative"
```

## Generator Pattern

Each report generator should follow this consistent pattern:

### 1. Function Signature

```python
def generate_report_name(
    report_data: List[Dict[str, Any]],
    cache: Any,
    year: int,
    administration: str,
    user_tenants: List[str],
    **kwargs
) -> Dict[str, Any]:
    """
    Generate [Report Name] report data.

    Args:
        report_data: Raw report data from database
        cache: Cache instance for additional data lookups
        year: Report year
        administration: Administration/tenant identifier
        user_tenants: List of tenants user has access to (for security)
        **kwargs: Additional parameters specific to this report

    Returns:
        Dictionary containing structured report data ready for template:
        {
            'rows': [...],           # Formatted table rows
            'totals': {...},         # Calculated totals
            'metadata': {...},       # Report metadata
            'summary': {...}         # Summary information
        }
    """
```

### 2. Data Processing Steps

```python
def generate_report_name(...):
    # Step 1: Validate inputs
    if not report_data:
        raise ValueError("Report data is required")

    # Step 2: Initialize result structure
    result = {
        'rows': [],
        'totals': {},
        'metadata': {},
        'summary': {}
    }

    # Step 3: Process data (group, calculate, format)
    grouped_data = _group_data(report_data)

    for group_key, items in grouped_data.items():
        # Apply business logic
        processed_items = _process_items(items, cache, user_tenants)

        # Format for output
        formatted_rows = _format_rows(processed_items)
        result['rows'].extend(formatted_rows)

    # Step 4: Calculate totals
    result['totals'] = _calculate_totals(result['rows'])

    # Step 5: Add metadata
    result['metadata'] = {
        'year': year,
        'administration': administration,
        'generated_at': datetime.now().isoformat()
    }

    return result
```

### 3. Helper Functions

Keep helper functions private (prefix with `_`) and focused:

```python
def _group_data(data: List[Dict]) -> Dict[str, List[Dict]]:
    """Group data by a specific key."""
    grouped = {}
    for item in data:
        key = item.get('group_key')
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(item)
    return grouped

def _calculate_totals(rows: List[Dict]) -> Dict[str, float]:
    """Calculate totals from rows."""
    totals = {}
    for row in rows:
        amount = safe_float(row.get('amount', 0))
        category = row.get('category', 'other')
        totals[category] = totals.get(category, 0) + amount
    return totals

def _format_rows(items: List[Dict]) -> List[Dict]:
    """Format items into table rows."""
    rows = []
    for item in items:
        rows.append({
            'description': escape_html(item.get('description', '')),
            'amount': format_currency(item.get('amount', 0)),
            'css_class': get_css_class_for_amount(item.get('amount', 0))
        })
    return rows
```

## Usage Example

### In Route Handler (app.py)

```python
from report_generators.aangifte_ib_generator import generate_aangifte_ib_report
from services.template_service import TemplateService

@app.route('/api/reports/aangifte-ib-export', methods=['POST'])
@cognito_required(required_permissions=['reports_export'])
@tenant_required()
def aangifte_ib_export(user_email, user_roles, tenant, user_tenants):
    """Generate Aangifte IB report."""
    try:
        data = request.get_json()
        year = data.get('year')
        administration = data.get('administration', tenant)
        report_data = data.get('data', [])

        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)
        cache.get_data(db)

        # Step 1: Generate structured report data
        structured_data = generate_aangifte_ib_report(
            report_data=report_data,
            cache=cache,
            year=year,
            administration=administration,
            user_tenants=user_tenants
        )

        # Step 2: Apply template and generate output
        template_service = TemplateService(db)

        # Get template metadata
        template_metadata = template_service.get_template_metadata(
            administration=administration,
            template_type='aangifte_ib_html'
        )

        # Fetch template from Google Drive
        template_content = template_service.fetch_template_from_drive(
            file_id=template_metadata['template_file_id'],
            administration=administration
        )

        # Apply field mappings
        rendered_template = template_service.apply_field_mappings(
            template_xml=template_content,
            data=structured_data,
            mappings=template_metadata['field_mappings']
        )

        # Generate final output
        html_output = template_service.generate_output(
            template=rendered_template,
            data=structured_data,
            output_format='html'
        )

        return jsonify({
            'success': True,
            'html': html_output,
            'filename': f'Aangifte_IB_{administration}_{year}.html'
        })

    except Exception as e:
        logger.error(f"Failed to generate Aangifte IB report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
```

## Best Practices

### 1. Separation of Concerns

- **Generators**: Focus on data transformation and business logic
- **Templates**: Focus on presentation and layout
- **Formatters**: Focus on consistent formatting across all reports

### 2. Security

- Always validate `user_tenants` to ensure users can only access their own data
- Use `escape_html()` for any user-provided content in HTML output
- Never trust raw data - always validate and sanitize

```python
# Good: Filter by user_tenants
details = cache.query_aangifte_ib_details(
    year, administration, parent, aangifte, user_tenants
)

# Bad: No tenant filtering
details = cache.query_aangifte_ib_details(
    year, administration, parent, aangifte
)
```

### 3. Error Handling

- Use try-except blocks for data processing
- Log errors with context
- Provide meaningful error messages
- Use safe conversion functions (`safe_float`, `safe_int`)

```python
try:
    amount = safe_float(item.get('amount', 0))
    formatted = format_currency(amount)
except Exception as e:
    logger.error(f"Failed to format amount for item {item.get('id')}: {e}")
    formatted = "0.00"
```

### 4. Performance

- Filter zero amounts early to reduce processing
- Use generators for large datasets
- Cache expensive calculations
- Minimize database queries

```python
# Filter zero amounts early
non_zero_items = [
    item for item in items
    if abs(safe_float(item.get('amount', 0))) >= 0.01
]
```

### 5. Testing

- Write unit tests for each generator function
- Test with edge cases (empty data, zero amounts, missing fields)
- Test with real data samples
- Verify security (tenant isolation)

## Migration Strategy

When converting existing hardcoded report generation to use this module:

1. **Extract data processing logic** from route handler
2. **Create generator function** following the pattern above
3. **Use common formatters** instead of inline formatting
4. **Update route handler** to use generator + template service
5. **Test thoroughly** with real data
6. **Document any special requirements** in generator docstring

## Future Enhancements

- [ ] Add support for Excel output generation
- [ ] Add support for PDF output generation
- [ ] Add caching for expensive calculations
- [ ] Add data validation utilities
- [ ] Add report preview functionality
- [ ] Add unit tests for all generators

## Related Documentation

- **Template Service**: `backend/src/services/TEMPLATE_SERVICE_DOCUMENTATION.md`
- **Template Implementation**: `backend/templates/xml/IMPLEMENTATION_SUMMARY.md`
- **Railway Migration Tasks**: `.kiro/specs/Common/Railway migration/TASKS.md`
- **Template Analysis**: `.kiro/specs/Common/templates/analysis.md`

## Questions or Issues?

If you have questions about implementing a new generator or using the common formatters, refer to:

1. This README for patterns and best practices
2. `common_formatters.py` for available utility functions
3. Existing generator implementations for examples
4. Template Service documentation for integration details
