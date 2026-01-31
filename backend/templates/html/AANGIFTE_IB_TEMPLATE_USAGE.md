# Aangifte IB Template Usage Guide

**Created**: January 30, 2026  
**Status**: Ready to use ✅

---

## Overview

This template system replaces the hardcoded HTML generation in `app.py` with a proper template-based approach for Aangifte IB reports.

---

## Files

1. **backend/templates/html/aangifte_ib_template.html** - HTML template
2. **backend/templates/xml/financial_report_field_mappings.json** - Field mappings and configuration
3. **backend/src/services/aangifte_ib_template_helper.py** - Helper functions to generate table rows

---

## How It Works

### Current Hardcoded Implementation (app.py)

```python
@app.route('/api/reports/aangifte-ib-export', methods=['POST'])
def aangifte_ib_export():
    # ... get data ...

    # Hardcoded HTML generation
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>...</head>
    <body>
        <h1>Aangifte Inkomstenbelasting - {year}</h1>
        ...
        <table>...</table>
    </body>
    </html>
    """

    return jsonify({'success': True, 'html': html_content})
```

### New Template-Based Implementation

```python
from services.aangifte_ib_template_helper import generate_aangifte_ib_html

@app.route('/api/reports/aangifte-ib-export', methods=['POST'])
def aangifte_ib_export():
    # ... get data ...

    # Load template
    with open('backend/templates/html/aangifte_ib_template.html', 'r') as f:
        template_html = f.read()

    # Generate HTML from template
    html_content = generate_aangifte_ib_html(
        year=year,
        administration=administration,
        report_data=report_data,
        cache=cache,
        user_tenants=user_tenants,
        template_html=template_html
    )

    return jsonify({'success': True, 'html': html_content})
```

---

## Template Structure

### HTML Template

```html
<!DOCTYPE html>
<html>
  <head>
    <title>Aangifte IB - {{ year }}</title>
    <style>
      /* All CSS styles */
    </style>
  </head>
  <body>
    <h1>Aangifte Inkomstenbelasting - {{ year }}</h1>
    <p><strong>Administration:</strong> {{ administration }}</p>
    <p><strong>Generated:</strong> {{ generated_date }}</p>

    <table>
      <thead>
        ...
      </thead>
      <tbody>
        {{ table_rows }}
      </tbody>
    </table>
  </body>
</html>
```

### Placeholders

- `{{ year }}` - Report year (e.g., "2025")
- `{{ administration }}` - Administration name (e.g., "GoodwinSolutions")
- `{{ generated_date }}` - Generation timestamp (e.g., "2026-01-30 13:01:14")
- `{{ table_rows }}` - Generated HTML table rows

---

## Table Row Generation

The `generate_table_rows()` function creates the hierarchical table structure:

### Row Types

1. **Parent Row** (gray background)

   ```html
   <tr class="parent-row">
     <td>4000</td>
     <td></td>
     <td></td>
     <td class="amount">118,989.22</td>
   </tr>
   ```

2. **Aangifte Row** (light gray background, indented)

   ```html
   <tr class="aangifte-row">
     <td class="indent-1"></td>
     <td>Andere kosten</td>
     <td></td>
     <td class="amount">34,958.68</td>
   </tr>
   ```

3. **Account Row** (white background, double indented)

   ```html
   <tr class="account-row">
     <td class="indent-2"></td>
     <td>4001</td>
     <td>Onkosten</td>
     <td class="amount">26,349.54</td>
   </tr>
   ```

4. **Resultaat Row** (conditional coloring)

   ```html
   <tr class="resultaat-positive">
     <td>RESULTAAT</td>
     <td></td>
     <td></td>
     <td class="amount">28,853.76</td>
   </tr>
   ```

5. **Grand Total Row** (orange background)
   ```html
   <tr class="grand-total">
     <td>GRAND TOTAL</td>
     <td></td>
     <td></td>
     <td class="amount">-0.00</td>
   </tr>
   ```

---

## Data Flow

```
1. User requests Aangifte IB export
   ↓
2. Backend queries cache.query_aangifte_ib(year, administration)
   ↓
3. For each Parent + Aangifte:
   - Query cache.query_aangifte_ib_details(year, admin, parent, aangifte, user_tenants)
   ↓
4. generate_table_rows() creates HTML rows:
   - Parent row with total
   - Aangifte row with subtotal
   - Account detail rows (indented)
   ↓
5. generate_aangifte_ib_html() fills template:
   - Replace {{ year }}
   - Replace {{ administration }}
   - Replace {{ generated_date }}
   - Replace {{ table_rows }}
   ↓
6. Return complete HTML to frontend
```

---

## Migration Steps

### Step 1: Update app.py

Replace the hardcoded HTML generation in `aangifte_ib_export()`:

```python
# OLD (lines ~2356-2456 in app.py)
html_content = f"""
<!DOCTYPE html>
<html>
...
"""

# NEW
from services.aangifte_ib_template_helper import generate_aangifte_ib_html

# Load template
template_path = os.path.join(
    os.path.dirname(__file__),
    '..',
    'templates',
    'html',
    'aangifte_ib_template.html'
)
with open(template_path, 'r', encoding='utf-8') as f:
    template_html = f.read()

# Generate HTML
html_content = generate_aangifte_ib_html(
    year=year,
    administration=administration,
    report_data=report_data,
    cache=cache,
    user_tenants=user_tenants,
    template_html=template_html
)
```

### Step 2: Test

```bash
# Test with existing endpoint
curl -X POST http://localhost:5000/api/reports/aangifte-ib-export \
  -H "Content-Type: application/json" \
  -d '{"year": "2025", "administration": "GoodwinSolutions", "data": [...]}'
```

### Step 3: Upload Template to Google Drive (Optional)

For multi-tenant customization:

1. Upload `aangifte_ib_template.html` to tenant's Google Drive
2. Store file ID in `tenant_template_config` table
3. Modify code to fetch template from Google Drive using TemplateService

---

## Benefits of Template Approach

### Before (Hardcoded)

- ❌ HTML mixed with Python code
- ❌ Hard to customize per tenant
- ❌ Difficult to maintain
- ❌ No version control for layout changes

### After (Template-Based)

- ✅ Clean separation of concerns
- ✅ Easy to customize per tenant (store in Google Drive)
- ✅ Easy to maintain and update
- ✅ Version control for templates
- ✅ Can add logos, branding, custom styling

---

## Future Enhancements

1. **Tenant-Specific Templates**
   - Store templates in tenant's Google Drive
   - Allow customization of colors, fonts, logos
   - Use TemplateService to fetch and apply

2. **PDF Generation**
   - Use weasyprint to convert HTML to PDF
   - Professional formatting for printing

3. **Multi-Language Support**
   - Add language parameter
   - Translate labels and headers

4. **Custom Calculations**
   - Allow tenants to define custom formulas
   - Add additional summary rows

---

## Testing

### Unit Tests

```python
def test_generate_table_rows():
    # Test with sample data
    report_data = [
        {'Parent': '4000', 'Aangifte': 'Omzet', 'Amount': 100000.00}
    ]

    rows = generate_table_rows(report_data, 2025, 'TestAdmin', cache, ['TestAdmin'])

    assert '<tr class="parent-row">' in rows
    assert '4000' in rows
    assert '100,000.00' in rows
```

### Integration Tests

```python
def test_aangifte_ib_export_with_template():
    # Test full export with template
    response = client.post('/api/reports/aangifte-ib-export', json={
        'year': '2025',
        'administration': 'GoodwinSolutions',
        'data': [...]
    })

    assert response.status_code == 200
    assert 'Aangifte Inkomstenbelasting' in response.json['html']
```

---

## Comparison with Generated File

Your generated file: `backend/templates/xml/Aangifte_IB_GoodwinSolutions_2025.html`

This template produces **identical output** to the hardcoded version, but with the flexibility to:

- Customize per tenant
- Update layout without code changes
- Add branding and logos
- Generate PDF versions

---

## Version History

| Version | Date       | Changes                                       |
| ------- | ---------- | --------------------------------------------- |
| 1.0     | 2026-01-30 | Initial template creation from hardcoded HTML |
