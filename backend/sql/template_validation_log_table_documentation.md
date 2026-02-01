# Template Validation Log Table Documentation

**Created**: February 2026  
**Part of**: Phase 2.6 - Template Preview and Validation  
**Purpose**: Track template validation history for audit and debugging purposes

---

## Table Overview

The `template_validation_log` table stores a complete history of all template validation attempts, including validation results, errors, warnings, and metadata about who performed the validation and when.

---

## Table Structure

### Schema Definition

```sql
CREATE TABLE IF NOT EXISTS template_validation_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    validation_result ENUM('success', 'warning', 'error') NOT NULL,
    errors JSON,
    warnings JSON,
    validated_by VARCHAR(255) NOT NULL,
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_administration_template (administration, template_type),
    INDEX idx_validated_at (validated_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
```

---

## Column Descriptions

| Column              | Type         | Nullable | Description                                                                                                                        |
| ------------------- | ------------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `id`                | INT          | NO       | Primary key, auto-incrementing unique identifier for each validation log entry                                                     |
| `administration`    | VARCHAR(100) | NO       | Tenant/administration identifier (e.g., 'GoodwinSolutions', 'PeterPrive')                                                          |
| `template_type`     | VARCHAR(50)  | NO       | Type of template being validated (e.g., 'str_invoice_nl', 'btw_aangifte', 'aangifte_ib', 'toeristenbelasting', 'financial_report') |
| `validation_result` | ENUM         | NO       | Overall validation result: 'success' (no errors), 'warning' (warnings only), 'error' (validation failed)                           |
| `errors`            | JSON         | YES      | Array of error objects with details about validation failures. NULL if no errors.                                                  |
| `warnings`          | JSON         | YES      | Array of warning objects with details about potential issues. NULL if no warnings.                                                 |
| `validated_by`      | VARCHAR(255) | NO       | Email or identifier of the user who performed the validation (Tenant Administrator)                                                |
| `validated_at`      | TIMESTAMP    | YES      | Timestamp when the validation was performed (defaults to current timestamp)                                                        |

---

## Indexes

### 1. Primary Key

- **Index Name**: `PRIMARY`
- **Columns**: `id`
- **Type**: UNIQUE
- **Purpose**: Ensures each log entry has a unique identifier

### 2. Administration + Template Type Index

- **Index Name**: `idx_administration_template`
- **Columns**: `administration`, `template_type`
- **Type**: NON-UNIQUE (composite index)
- **Purpose**: Optimizes queries filtering by tenant and template type (e.g., "show all validation logs for GoodwinSolutions' STR invoices")

### 3. Validated At Index

- **Index Name**: `idx_validated_at`
- **Columns**: `validated_at`
- **Type**: NON-UNIQUE
- **Purpose**: Optimizes time-based queries (e.g., "show all validations from the last 30 days")

---

## JSON Field Structures

### Errors Field

The `errors` field stores an array of error objects. Each error object has the following structure:

```json
[
  {
    "type": "html_syntax",
    "message": "Unclosed tag: <div>",
    "line": 42,
    "severity": "error"
  },
  {
    "type": "missing_placeholder",
    "message": "Required placeholder {{invoice_number}} not found",
    "severity": "error"
  },
  {
    "type": "security",
    "message": "Script tag detected: <script>alert('xss')</script>",
    "severity": "error"
  }
]
```

**Error Types**:

- `html_syntax`: HTML parsing errors (unclosed tags, malformed HTML)
- `missing_placeholder`: Required placeholders not found in template
- `security`: Security violations (script tags, event handlers)
- `invalid_structure`: Template structure issues

### Warnings Field

The `warnings` field stores an array of warning objects. Each warning object has the following structure:

```json
[
  {
    "type": "external_resource",
    "message": "External CSS detected: https://example.com/style.css",
    "severity": "warning"
  },
  {
    "type": "unused_placeholder",
    "message": "Placeholder {{optional_field}} is defined but not used",
    "severity": "warning"
  }
]
```

**Warning Types**:

- `external_resource`: External resources referenced (CSS, images, fonts)
- `unused_placeholder`: Placeholders defined but not used
- `deprecated_syntax`: Deprecated HTML/CSS syntax
- `performance`: Performance concerns (large inline styles, etc.)

---

## Usage Examples

### 1. Insert a Validation Log Entry

```python
from database import DatabaseManager

db = DatabaseManager()

# Successful validation
db.execute_query("""
    INSERT INTO template_validation_log
    (administration, template_type, validation_result, errors, warnings, validated_by)
    VALUES (%s, %s, %s, %s, %s, %s)
""", (
    'GoodwinSolutions',
    'str_invoice_nl',
    'success',
    None,
    None,
    'admin@goodwinsolutions.com'
), fetch=False, commit=True)

# Validation with errors
import json

errors = [
    {
        "type": "html_syntax",
        "message": "Unclosed tag: <div>",
        "line": 42,
        "severity": "error"
    }
]

db.execute_query("""
    INSERT INTO template_validation_log
    (administration, template_type, validation_result, errors, warnings, validated_by)
    VALUES (%s, %s, %s, %s, %s, %s)
""", (
    'GoodwinSolutions',
    'str_invoice_nl',
    'error',
    json.dumps(errors),
    None,
    'admin@goodwinsolutions.com'
), fetch=False, commit=True)
```

### 2. Query Validation History for a Tenant

```python
# Get all validation logs for a specific tenant and template type
results = db.execute_query("""
    SELECT * FROM template_validation_log
    WHERE administration = %s AND template_type = %s
    ORDER BY validated_at DESC
    LIMIT 10
""", ('GoodwinSolutions', 'str_invoice_nl'))

for log in results:
    print(f"Validation at {log['validated_at']}: {log['validation_result']}")
    if log['errors']:
        errors = json.loads(log['errors']) if isinstance(log['errors'], str) else log['errors']
        print(f"  Errors: {len(errors)}")
```

### 3. Query Recent Failed Validations

```python
# Get all failed validations from the last 30 days
results = db.execute_query("""
    SELECT * FROM template_validation_log
    WHERE validation_result = 'error'
    AND validated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    ORDER BY validated_at DESC
""")

print(f"Found {len(results)} failed validations in the last 30 days")
```

### 4. Get Validation Statistics

```python
# Get validation statistics by result type
stats = db.execute_query("""
    SELECT
        administration,
        template_type,
        validation_result,
        COUNT(*) as count,
        MAX(validated_at) as last_validation
    FROM template_validation_log
    GROUP BY administration, template_type, validation_result
    ORDER BY administration, template_type
""")

for stat in stats:
    print(f"{stat['administration']} - {stat['template_type']}: "
          f"{stat['count']} {stat['validation_result']} validations "
          f"(last: {stat['last_validation']})")
```

---

## Integration with TemplatePreviewService

The `template_validation_log` table is used by the `TemplatePreviewService` to:

1. **Log all validation attempts** - Every time a Tenant Administrator uploads or validates a template, an entry is created
2. **Track validation history** - Provides audit trail of who validated what and when
3. **Debug validation issues** - Stores detailed error and warning information for troubleshooting
4. **Generate reports** - Enables reporting on template validation success rates and common issues

Example integration:

```python
class TemplatePreviewService:
    def validate_template(self, template_type, template_content):
        # Perform validation
        errors = self._validate_html_syntax(template_content)
        errors.extend(self._validate_placeholders(template_type, template_content))
        errors.extend(self._validate_security(template_content))

        warnings = self._check_warnings(template_content)

        # Determine result
        if errors:
            result = 'error'
        elif warnings:
            result = 'warning'
        else:
            result = 'success'

        # Log validation
        self.db.execute_query("""
            INSERT INTO template_validation_log
            (administration, template_type, validation_result, errors, warnings, validated_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            self.administration,
            template_type,
            result,
            json.dumps(errors) if errors else None,
            json.dumps(warnings) if warnings else None,
            self.user_email
        ), fetch=False, commit=True)

        return {
            'result': result,
            'errors': errors,
            'warnings': warnings
        }
```

---

## Maintenance and Cleanup

### Retention Policy

Consider implementing a retention policy to prevent the table from growing indefinitely:

```sql
-- Delete validation logs older than 1 year
DELETE FROM template_validation_log
WHERE validated_at < DATE_SUB(NOW(), INTERVAL 1 YEAR);
```

### Archive Old Logs

For compliance or audit purposes, consider archiving old logs before deletion:

```sql
-- Create archive table (one-time)
CREATE TABLE template_validation_log_archive LIKE template_validation_log;

-- Archive logs older than 1 year
INSERT INTO template_validation_log_archive
SELECT * FROM template_validation_log
WHERE validated_at < DATE_SUB(NOW(), INTERVAL 1 YEAR);

-- Then delete from main table
DELETE FROM template_validation_log
WHERE validated_at < DATE_SUB(NOW(), INTERVAL 1 YEAR);
```

---

## Related Tables

- **tenant_template_config**: Stores active template configurations (file IDs, field mappings)
- **ai_usage_log**: Tracks AI assistance usage for cost monitoring (to be created)

---

## Migration Script

The table is created using the migration script:

- **SQL File**: `backend/sql/create_template_validation_log_table.sql`
- **Python Script**: `backend/scripts/create_template_validation_log_table.py`
- **Verification Script**: `backend/scripts/verify_template_validation_log_table.py`

To create the table:

```bash
python backend/scripts/create_template_validation_log_table.py
```

To verify the table structure:

```bash
python backend/scripts/verify_template_validation_log_table.py
```

---

## Testing

### Unit Tests

Test validation logging in `backend/tests/unit/test_template_preview_service.py`:

```python
def test_validation_logging(db, template_preview_service):
    """Test that validation results are logged correctly"""

    # Perform validation
    result = template_preview_service.validate_template(
        'str_invoice_nl',
        '<html><body>{{invoice_number}}</body></html>'
    )

    # Check log was created
    logs = db.execute_query("""
        SELECT * FROM template_validation_log
        WHERE administration = %s AND template_type = %s
        ORDER BY validated_at DESC LIMIT 1
    """, ('GoodwinSolutions', 'str_invoice_nl'))

    assert len(logs) == 1
    assert logs[0]['validation_result'] == result['result']
```

### Integration Tests

Test end-to-end validation logging in `backend/tests/integration/test_template_validation.py`

---

## Security Considerations

1. **Tenant Isolation**: Always filter queries by `administration` to ensure tenants can only see their own validation logs
2. **PII in Logs**: Ensure template content is NOT stored in the log (only validation results)
3. **Access Control**: Only Tenant Administrators should be able to view validation logs for their tenant
4. **JSON Injection**: Validate and sanitize error/warning messages before storing in JSON fields

---

## Performance Considerations

1. **Index Usage**: The composite index `idx_administration_template` is optimized for the most common query pattern (filter by tenant + template type)
2. **JSON Fields**: MySQL 5.7+ has native JSON support with efficient storage and querying
3. **Retention**: Implement regular cleanup to prevent table bloat
4. **Partitioning**: For high-volume systems, consider partitioning by `validated_at` (monthly or yearly)

---

## Future Enhancements

1. **Validation Metrics Dashboard**: Create a dashboard showing validation success rates over time
2. **Automated Alerts**: Send notifications when validation failure rate exceeds threshold
3. **AI Learning**: Use validation logs to improve AI template assistance suggestions
4. **Template Quality Score**: Calculate quality scores based on validation history

---

## References

- **Spec Document**: `.kiro/specs/Common/Railway migration/TASKS.md` (Phase 2.6)
- **Requirements**: `.kiro/specs/Common/template-preview-validation/requirements.md`
- **Design**: `.kiro/specs/Common/template-preview-validation/design.md`
