# Template Preview and Validation - Design

**Feature**: Template Preview and Validation System  
**Status**: Draft  
**Created**: January 31, 2026  
**Owner**: Development Team

---

## 1. Architecture Overview

### 1.1 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  TenantAdmin/TemplateManagement Component            │  │
│  │  - Upload form                                        │  │
│  │  - Preview display                                    │  │
│  │  - Validation results                                 │  │
│  │  - Approve/Reject buttons                             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS/JSON
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Backend API (Flask)                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  /api/tenant-admin/templates/preview (POST)          │  │
│  │  /api/tenant-admin/templates/validate (POST)         │  │
│  │  /api/tenant-admin/templates/approve (POST)          │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  TemplatePreviewService                              │  │
│  │  - fetch_sample_data()                               │  │
│  │  - generate_preview()                                │  │
│  │  - validate_template()                               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
┌──────────────────────┐    ┌──────────────────────┐
│   MySQL Database     │    │   Google Drive       │
│  - Sample data       │    │  - Approved          │
│  - Template metadata │    │    templates         │
└──────────────────────┘    └──────────────────────┘
```

### 1.2 Data Flow

**Upload and Preview Flow**:

1. User uploads template file + field mappings
2. Backend validates file (size, type, syntax)
3. Backend fetches sample data for template type
4. Backend generates preview using report generator
5. Backend returns preview HTML + validation results
6. Frontend displays preview in iframe
7. User reviews and approves/rejects

**Approval Flow**:

1. User clicks "Approve"
2. Backend saves template to Google Drive
3. Backend stores metadata in database
4. Backend marks template as active
5. Frontend shows success message

---

## 2. API Design

### 2.1 POST /api/tenant-admin/templates/preview

Generate a preview of an uploaded template with sample data.

**Request**:

```json
{
  "template_type": "str_invoice_nl",
  "template_content": "<html>...</html>",
  "field_mappings": {
    "invoice_number": "reservationCode",
    "guest_name": "guestName",
    "amount": "amountGross"
  }
}
```

**Response (Success)**:

```json
{
  "success": true,
  "preview_html": "<html>...rendered preview...</html>",
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": ["No sample data found for 2026, using 2025 data"]
  },
  "sample_data_info": {
    "source": "database",
    "record_date": "2025-12-15",
    "record_id": "RES-2025-1234"
  }
}
```

**Response (Validation Errors)**:

```json
{
  "success": false,
  "validation": {
    "is_valid": false,
    "errors": [
      {
        "type": "missing_placeholder",
        "message": "Required placeholder '{{ invoice_number }}' not found in template",
        "severity": "error"
      },
      {
        "type": "syntax_error",
        "message": "Unclosed tag at line 45: <div>",
        "severity": "error",
        "line": 45
      }
    ],
    "warnings": []
  }
}
```

### 2.2 POST /api/tenant-admin/templates/validate

Validate a template without generating a full preview (faster).

**Request**:

```json
{
  "template_type": "btw_aangifte",
  "template_content": "<html>...</html>",
  "field_mappings": {}
}
```

**Response**:

```json
{
  "success": true,
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "checks_performed": [
      "html_syntax",
      "required_placeholders",
      "security_scan",
      "file_size"
    ]
  }
}
```

### 2.3 POST /api/tenant-admin/templates/approve

Approve and activate a template.

**Request**:

```json
{
  "template_type": "str_invoice_nl",
  "template_content": "<html>...</html>",
  "field_mappings": {
    "invoice_number": "reservationCode"
  },
  "notes": "Updated logo and colors"
}
```

**Response**:

```json
{
  "success": true,
  "template_id": "tmpl_abc123",
  "file_id": "1a2b3c4d5e6f7g8h9i",
  "message": "Template approved and activated",
  "previous_version": {
    "file_id": "9i8h7g6f5e4d3c2b1a",
    "archived_at": "2026-01-31T20:30:00Z"
  }
}
```

### 2.4 POST /api/tenant-admin/templates/reject

Reject a template (does not save to Google Drive).

**Request**:

```json
{
  "template_type": "str_invoice_nl",
  "reason": "Colors don't match brand guidelines"
}
```

**Response**:

```json
{
  "success": true,
  "message": "Template rejected. You can upload a new version."
}
```

---

## 3. Database Schema

### 3.1 Extend tenant_template_config Table

Add columns for template versioning and approval tracking:

```sql
ALTER TABLE tenant_template_config
ADD COLUMN version INT DEFAULT 1,
ADD COLUMN approved_by VARCHAR(255),
ADD COLUMN approved_at TIMESTAMP,
ADD COLUMN approval_notes TEXT,
ADD COLUMN previous_file_id VARCHAR(255),
ADD COLUMN status ENUM('draft', 'active', 'archived') DEFAULT 'active';
```

### 3.2 Create template_validation_log Table

Track validation attempts and results:

```sql
CREATE TABLE template_validation_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    validation_result ENUM('pass', 'fail') NOT NULL,
    errors JSON,
    warnings JSON,
    validated_by VARCHAR(255),
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_type (administration, template_type),
    INDEX idx_validated_at (validated_at)
);
```

---

## 4. Backend Implementation

### 4.1 TemplatePreviewService

Create new service: `backend/src/services/template_preview_service.py`

```python
class TemplatePreviewService:
    """Service for template preview and validation"""

    def __init__(self, db, administration):
        self.db = db
        self.administration = administration
        self.template_service = TemplateService(db)

    def generate_preview(self, template_type, template_content, field_mappings):
        """Generate preview with sample data"""
        # 1. Validate template
        validation = self.validate_template(template_type, template_content)
        if not validation['is_valid']:
            return {'success': False, 'validation': validation}

        # 2. Fetch sample data
        sample_data = self.fetch_sample_data(template_type)

        # 3. Generate preview using report generator
        preview_html = self._render_template(
            template_content,
            sample_data,
            field_mappings
        )

        return {
            'success': True,
            'preview_html': preview_html,
            'validation': validation,
            'sample_data_info': sample_data['metadata']
        }

    def validate_template(self, template_type, template_content):
        """Validate template syntax and structure"""
        errors = []
        warnings = []

        # Check 1: HTML syntax
        syntax_errors = self._validate_html_syntax(template_content)
        errors.extend(syntax_errors)

        # Check 2: Required placeholders
        placeholder_errors = self._validate_placeholders(
            template_type,
            template_content
        )
        errors.extend(placeholder_errors)

        # Check 3: Security scan
        security_errors = self._validate_security(template_content)
        errors.extend(security_errors)

        # Check 4: File size
        if len(template_content) > 5 * 1024 * 1024:  # 5MB
            errors.append({
                'type': 'file_size',
                'message': 'Template exceeds 5MB limit',
                'severity': 'error'
            })

        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'checks_performed': [
                'html_syntax',
                'required_placeholders',
                'security_scan',
                'file_size'
            ]
        }

    def fetch_sample_data(self, template_type):
        """Fetch most recent data for template type"""
        # Implementation depends on template type
        # Returns structured data + metadata
        pass

    def approve_template(self, template_type, template_content,
                        field_mappings, user_email, notes):
        """Approve and save template"""
        # 1. Save to Google Drive
        # 2. Update database metadata
        # 3. Archive previous version
        # 4. Log approval
        pass
```

### 4.2 Validation Functions

#### 4.2.1 HTML Syntax Validation

```python
def _validate_html_syntax(self, template_content):
    """Validate HTML is well-formed"""
    from html.parser import HTMLParser

    errors = []

    class ValidationParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.errors = []
            self.tag_stack = []

        def handle_starttag(self, tag, attrs):
            self.tag_stack.append(tag)

        def handle_endtag(self, tag):
            if not self.tag_stack or self.tag_stack[-1] != tag:
                self.errors.append({
                    'type': 'syntax_error',
                    'message': f'Mismatched closing tag: </{tag}>',
                    'severity': 'error'
                })
            else:
                self.tag_stack.pop()

    parser = ValidationParser()
    try:
        parser.feed(template_content)
        errors.extend(parser.errors)

        # Check for unclosed tags
        if parser.tag_stack:
            errors.append({
                'type': 'syntax_error',
                'message': f'Unclosed tags: {", ".join(parser.tag_stack)}',
                'severity': 'error'
            })
    except Exception as e:
        errors.append({
            'type': 'syntax_error',
            'message': f'HTML parsing error: {str(e)}',
            'severity': 'error'
        })

    return errors
```

#### 4.2.2 Placeholder Validation

```python
def _validate_placeholders(self, template_type, template_content):
    """Check for required placeholders"""
    import re

    errors = []

    # Define required placeholders per template type
    REQUIRED_PLACEHOLDERS = {
        'str_invoice_nl': [
            'invoice_number', 'guest_name', 'checkin_date',
            'checkout_date', 'amount_gross', 'company_name'
        ],
        'btw_aangifte': [
            'year', 'quarter', 'administration', 'balance_rows',
            'quarter_rows', 'payment_instruction'
        ],
        'aangifte_ib': [
            'year', 'administration', 'table_rows', 'generated_date'
        ],
        'toeristenbelasting': [
            'year', 'contact_name', 'contact_email', 'nights_total',
            'revenue_total', 'tourist_tax_total'
        ]
    }

    required = REQUIRED_PLACEHOLDERS.get(template_type, [])

    # Find all placeholders in template
    placeholders = re.findall(r'\{\{\s*(\w+)\s*\}\}', template_content)
    found_placeholders = set(placeholders)

    # Check for missing required placeholders
    for placeholder in required:
        if placeholder not in found_placeholders:
            errors.append({
                'type': 'missing_placeholder',
                'message': f"Required placeholder '{{{{ {placeholder} }}}}' not found",
                'severity': 'error',
                'placeholder': placeholder
            })

    return errors
```

#### 4.2.3 Security Validation

```python
def _validate_security(self, template_content):
    """Check for security issues"""
    import re

    errors = []
    warnings = []

    # Check for script tags
    if re.search(r'<script[^>]*>', template_content, re.IGNORECASE):
        errors.append({
            'type': 'security_error',
            'message': 'Script tags are not allowed in templates',
            'severity': 'error'
        })

    # Check for event handlers
    event_handlers = re.findall(
        r'on\w+\s*=',
        template_content,
        re.IGNORECASE
    )
    if event_handlers:
        errors.append({
            'type': 'security_error',
            'message': 'Event handlers (onclick, onload, etc.) are not allowed',
            'severity': 'error'
        })

    # Check for external resources
    external_resources = re.findall(
        r'(src|href)\s*=\s*["\']https?://',
        template_content,
        re.IGNORECASE
    )
    if external_resources:
        warnings.append({
            'type': 'security_warning',
            'message': 'External resources detected. Ensure they are from trusted sources.',
            'severity': 'warning'
        })

    return errors
```

### 4.3 Sample Data Fetching

```python
def fetch_sample_data(self, template_type):
    """Fetch most recent data for preview"""

    if template_type == 'str_invoice_nl' or template_type == 'str_invoice_en':
        return self._fetch_str_invoice_sample()
    elif template_type == 'btw_aangifte':
        return self._fetch_btw_sample()
    elif template_type == 'aangifte_ib':
        return self._fetch_aangifte_ib_sample()
    elif template_type == 'toeristenbelasting':
        return self._fetch_toeristenbelasting_sample()
    else:
        return self._fetch_generic_sample()

def _fetch_str_invoice_sample(self):
    """Fetch most recent STR booking for invoice preview"""
    query = """
        SELECT * FROM bnb_bookings
        WHERE administration = %s
        AND status = 'realised'
        ORDER BY checkin_date DESC
        LIMIT 1
    """

    conn = self.db.get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, [self.administration])
    booking = cursor.fetchone()
    cursor.close()
    conn.close()

    if not booking:
        # Return placeholder data if no bookings exist
        return {
            'data': self._get_placeholder_str_data(),
            'metadata': {
                'source': 'placeholder',
                'message': 'No bookings found, using placeholder data'
            }
        }

    return {
        'data': booking,
        'metadata': {
            'source': 'database',
            'record_date': str(booking['checkin_date']),
            'record_id': booking['reservationCode']
        }
    }
```

### 4.4 API Routes

Create `backend/src/tenant_admin_routes.py`:

```python
from flask import Blueprint, request, jsonify
from services.template_preview_service import TemplatePreviewService
from auth import require_tenant_admin

tenant_admin_bp = Blueprint('tenant_admin', __name__)

@tenant_admin_bp.route('/api/tenant-admin/templates/preview', methods=['POST'])
@require_tenant_admin
def preview_template(current_user, administration):
    """Generate template preview"""
    data = request.get_json()

    # Validate request
    required_fields = ['template_type', 'template_content']
    if not all(field in data for field in required_fields):
        return jsonify({
            'success': False,
            'error': 'Missing required fields'
        }), 400

    # Generate preview
    service = TemplatePreviewService(db, administration)
    result = service.generate_preview(
        template_type=data['template_type'],
        template_content=data['template_content'],
        field_mappings=data.get('field_mappings', {})
    )

    if result['success']:
        return jsonify(result), 200
    else:
        return jsonify(result), 400

@tenant_admin_bp.route('/api/tenant-admin/templates/validate', methods=['POST'])
@require_tenant_admin
def validate_template(current_user, administration):
    """Validate template without full preview"""
    data = request.get_json()

    service = TemplatePreviewService(db, administration)
    validation = service.validate_template(
        template_type=data['template_type'],
        template_content=data['template_content']
    )

    return jsonify({
        'success': True,
        'validation': validation
    }), 200

@tenant_admin_bp.route('/api/tenant-admin/templates/approve', methods=['POST'])
@require_tenant_admin
def approve_template(current_user, administration):
    """Approve and activate template"""
    data = request.get_json()

    service = TemplatePreviewService(db, administration)
    result = service.approve_template(
        template_type=data['template_type'],
        template_content=data['template_content'],
        field_mappings=data.get('field_mappings', {}),
        user_email=current_user['email'],
        notes=data.get('notes', '')
    )

    return jsonify(result), 200 if result['success'] else 400

@tenant_admin_bp.route('/api/tenant-admin/templates/reject', methods=['POST'])
@require_tenant_admin
def reject_template(current_user, administration):
    """Reject template"""
    data = request.get_json()

    # Log rejection
    logger.info(f"Template rejected by {current_user['email']}: {data.get('reason')}")

    return jsonify({
        'success': True,
        'message': 'Template rejected. You can upload a new version.'
    }), 200
```

---

## 5. Frontend Implementation

### 5.1 Component Structure

```
frontend/src/components/TenantAdmin/
├── TemplateManagement/
│   ├── TemplateManagement.tsx          # Main container
│   ├── TemplateUpload.tsx              # File upload form
│   ├── TemplatePreview.tsx             # Preview display
│   ├── ValidationResults.tsx           # Validation errors/warnings
│   ├── FieldMappingEditor.tsx          # Field mapping configuration
│   └── TemplateApproval.tsx            # Approve/Reject buttons
```

### 5.2 TemplateManagement Component

```typescript
import React, { useState } from 'react';
import { TemplateUpload } from './TemplateUpload';
import { TemplatePreview } from './TemplatePreview';
import { ValidationResults } from './ValidationResults';
import { TemplateApproval } from './TemplateApproval';

interface TemplateManagementProps {
  administration: string;
}

export const TemplateManagement: React.FC<TemplateManagementProps> = ({
  administration
}) => {
  const [templateType, setTemplateType] = useState('');
  const [templateContent, setTemplateContent] = useState('');
  const [fieldMappings, setFieldMappings] = useState({});
  const [previewHtml, setPreviewHtml] = useState('');
  const [validation, setValidation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleUpload = async (file: File, type: string, mappings: object) => {
    setIsLoading(true);

    // Read file content
    const content = await file.text();
    setTemplateContent(content);
    setTemplateType(type);
    setFieldMappings(mappings);

    // Generate preview
    try {
      const response = await fetch('/api/tenant-admin/templates/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_type: type,
          template_content: content,
          field_mappings: mappings
        })
      });

      const result = await response.json();

      if (result.success) {
        setPreviewHtml(result.preview_html);
        setValidation(result.validation);
      } else {
        setValidation(result.validation);
      }
    } catch (error) {
      console.error('Preview generation failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleApprove = async (notes: string) => {
    setIsLoading(true);

    try {
      const response = await fetch('/api/tenant-admin/templates/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_type: templateType,
          template_content: templateContent,
          field_mappings: fieldMappings,
          notes
        })
      });

      const result = await response.json();

      if (result.success) {
        alert('Template approved and activated!');
        // Reset form
        setTemplateContent('');
        setPreviewHtml('');
        setValidation(null);
      }
    } catch (error) {
      console.error('Approval failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReject = async (reason: string) => {
    await fetch('/api/tenant-admin/templates/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template_type: templateType,
        reason
      })
    });

    // Keep form state so user can modify and re-upload
    alert('Template rejected. You can modify and re-upload.');
  };

  return (
    <div className="template-management">
      <h2>Template Management</h2>

      <TemplateUpload
        onUpload={handleUpload}
        isLoading={isLoading}
      />

      {validation && (
        <ValidationResults validation={validation} />
      )}

      {previewHtml && (
        <>
          <TemplatePreview html={previewHtml} />

          <TemplateApproval
            onApprove={handleApprove}
            onReject={handleReject}
            isValid={validation?.is_valid}
            isLoading={isLoading}
          />
        </>
      )}
    </div>
  );
};
```

### 5.3 TemplatePreview Component

```typescript
import React from 'react';

interface TemplatePreviewProps {
  html: string;
}

export const TemplatePreview: React.FC<TemplatePreviewProps> = ({ html }) => {
  return (
    <div className="template-preview">
      <h3>Preview</h3>
      <div className="preview-container">
        <iframe
          srcDoc={html}
          title="Template Preview"
          sandbox="allow-same-origin"
          style={{
            width: '100%',
            height: '600px',
            border: '1px solid #ccc',
            borderRadius: '4px'
          }}
        />
      </div>
      <p className="preview-note">
        This preview shows how your template will look with sample data.
      </p>
    </div>
  );
};
```

### 5.4 ValidationResults Component

```typescript
import React from 'react';

interface ValidationError {
  type: string;
  message: string;
  severity: 'error' | 'warning';
  line?: number;
}

interface ValidationResultsProps {
  validation: {
    is_valid: boolean;
    errors: ValidationError[];
    warnings: ValidationError[];
  };
}

export const ValidationResults: React.FC<ValidationResultsProps> = ({
  validation
}) => {
  const { is_valid, errors, warnings } = validation;

  if (is_valid && warnings.length === 0) {
    return (
      <div className="validation-success">
        ✅ Template validation passed
      </div>
    );
  }

  return (
    <div className="validation-results">
      {errors.length > 0 && (
        <div className="validation-errors">
          <h4>❌ Errors ({errors.length})</h4>
          <ul>
            {errors.map((error, index) => (
              <li key={index} className="error-item">
                <strong>{error.type}:</strong> {error.message}
                {error.line && <span> (line {error.line})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="validation-warnings">
          <h4>⚠️ Warnings ({warnings.length})</h4>
          <ul>
            {warnings.map((warning, index) => (
              <li key={index} className="warning-item">
                {warning.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
```

---

## 6. Security Considerations

### 6.1 Input Validation

- **File Size**: Limit to 5MB
- **File Type**: Only accept HTML files
- **Content Sanitization**: Strip dangerous tags and attributes
- **SQL Injection**: Use parameterized queries for sample data
- **XSS Prevention**: Sandbox iframe for preview display

### 6.2 Authentication & Authorization

- **Endpoint Protection**: All endpoints require `@require_tenant_admin` decorator
- **Tenant Isolation**: Verify user belongs to administration
- **Sample Data Filtering**: Always filter by authenticated tenant
- **Google Drive Access**: Use tenant-specific credentials only

### 6.3 Content Security Policy

```python
# Add CSP headers to preview endpoint
@tenant_admin_bp.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'none'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "frame-ancestors 'none';"
    )
    return response
```

### 6.4 Audit Logging

Log all template operations:

- Upload attempts
- Validation results
- Approval/rejection actions
- Template activations
- User who performed action
- Timestamp

---

## 7. Error Handling

### 7.1 Backend Error Responses

```python
# Standard error response format
{
    "success": false,
    "error": {
        "code": "VALIDATION_FAILED",
        "message": "Template validation failed",
        "details": {
            "errors": [...],
            "warnings": [...]
        }
    }
}
```

### 7.2 Error Codes

- `VALIDATION_FAILED`: Template validation errors
- `SAMPLE_DATA_NOT_FOUND`: No sample data available
- `TEMPLATE_TOO_LARGE`: File exceeds size limit
- `INVALID_TEMPLATE_TYPE`: Unknown template type
- `GOOGLE_DRIVE_ERROR`: Failed to save to Google Drive
- `UNAUTHORIZED`: User not authorized for this tenant
- `INTERNAL_ERROR`: Unexpected server error

### 7.3 Frontend Error Handling

```typescript
try {
  const response = await fetch("/api/tenant-admin/templates/preview", {
    method: "POST",
    body: JSON.stringify(data),
  });

  const result = await response.json();

  if (!response.ok) {
    // Handle HTTP errors
    if (response.status === 401) {
      showError("You are not authorized to perform this action");
    } else if (response.status === 400) {
      showValidationErrors(result.validation);
    } else {
      showError("An unexpected error occurred");
    }
  }
} catch (error) {
  // Handle network errors
  showError("Network error. Please check your connection.");
}
```

---

## 8. Performance Optimization

### 8.1 Caching Strategy

- **Sample Data**: Cache for 5 minutes per tenant/template type
- **Validation Rules**: Cache in memory (rarely change)
- **Template Metadata**: Cache after database read

### 8.2 Async Processing

For large templates or slow sample data queries:

```python
from celery import Celery

@celery.task
def generate_preview_async(template_type, template_content, administration):
    """Generate preview asynchronously"""
    service = TemplatePreviewService(db, administration)
    result = service.generate_preview(template_type, template_content, {})

    # Store result in cache with task ID
    cache.set(f'preview_{task_id}', result, timeout=300)

    return result

# API endpoint
@tenant_admin_bp.route('/api/tenant-admin/templates/preview-async', methods=['POST'])
def preview_template_async():
    task = generate_preview_async.delay(...)
    return jsonify({'task_id': task.id}), 202

# Poll for result
@tenant_admin_bp.route('/api/tenant-admin/templates/preview-status/<task_id>')
def preview_status(task_id):
    result = cache.get(f'preview_{task_id}')
    if result:
        return jsonify(result), 200
    else:
        return jsonify({'status': 'processing'}), 202
```

### 8.3 Database Optimization

- Index on `(administration, template_type)` for fast lookups
- Use `LIMIT 1` when fetching sample data
- Connection pooling for concurrent requests

---

## 9. Testing Strategy

### 9.1 Unit Tests

Test individual validation functions:

```python
# tests/unit/test_template_preview_service.py

def test_validate_html_syntax_valid():
    service = TemplatePreviewService(mock_db, 'TestAdmin')
    html = '<html><body><h1>Test</h1></body></html>'
    errors = service._validate_html_syntax(html)
    assert len(errors) == 0

def test_validate_html_syntax_unclosed_tag():
    service = TemplatePreviewService(mock_db, 'TestAdmin')
    html = '<html><body><h1>Test</body></html>'
    errors = service._validate_html_syntax(html)
    assert len(errors) > 0
    assert 'unclosed' in errors[0]['message'].lower()

def test_validate_placeholders_missing():
    service = TemplatePreviewService(mock_db, 'TestAdmin')
    html = '<html><body>{{ guest_name }}</body></html>'
    errors = service._validate_placeholders('str_invoice_nl', html)
    assert len(errors) > 0  # Missing invoice_number, etc.
```

### 9.2 Integration Tests

Test full preview generation flow:

```python
# tests/integration/test_template_preview_integration.py

@pytest.mark.integration
def test_preview_generation_with_sample_data():
    service = TemplatePreviewService(db, 'GoodwinSolutions')

    template = '<html><body>{{ invoice_number }}</body></html>'
    result = service.generate_preview('str_invoice_nl', template, {})

    assert result['success'] is True
    assert 'preview_html' in result
    assert result['validation']['is_valid'] is False  # Missing placeholders
```

### 9.3 API Tests

Test endpoints with authentication:

```python
# tests/api/test_tenant_admin_routes.py

@pytest.mark.api
def test_preview_endpoint_requires_auth(client):
    response = client.post('/api/tenant-admin/templates/preview')
    assert response.status_code == 401

@pytest.mark.api
def test_preview_endpoint_success(client, auth_headers):
    data = {
        'template_type': 'str_invoice_nl',
        'template_content': '<html>...</html>',
        'field_mappings': {}
    }
    response = client.post(
        '/api/tenant-admin/templates/preview',
        json=data,
        headers=auth_headers
    )
    assert response.status_code in [200, 400]  # 400 if validation fails
```

---

## 10. Deployment Considerations

### 10.1 Environment Variables

Add to Railway environment:

```bash
TEMPLATE_MAX_SIZE_MB=5
TEMPLATE_PREVIEW_TIMEOUT=30
ENABLE_ASYNC_PREVIEW=false  # Enable for production
```

### 10.2 Database Migrations

```sql
-- Run before deployment
ALTER TABLE tenant_template_config ADD COLUMN version INT DEFAULT 1;
ALTER TABLE tenant_template_config ADD COLUMN approved_by VARCHAR(255);
ALTER TABLE tenant_template_config ADD COLUMN approved_at TIMESTAMP;

CREATE TABLE template_validation_log (...);
```

### 10.3 Monitoring

- Log all preview generation attempts
- Track validation failure rates
- Monitor preview generation time
- Alert on high error rates

---

## 11. Documentation

### 11.1 API Documentation

Generate OpenAPI/Swagger docs:

```yaml
/api/tenant-admin/templates/preview:
  post:
    summary: Generate template preview
    security:
      - BearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              template_type:
                type: string
                enum: [str_invoice_nl, str_invoice_en, btw_aangifte, ...]
              template_content:
                type: string
              field_mappings:
                type: object
    responses:
      200:
        description: Preview generated successfully
      400:
        description: Validation failed
      401:
        description: Unauthorized
```

### 11.2 User Guide

Create guide for Tenant Administrators:

- How to upload templates
- Understanding validation errors
- Field mapping reference
- Best practices
- Troubleshooting

---

## 12. Future Enhancements

### 12.1 Phase 2 Features

- **Template Versioning UI**: View and compare versions
- **Template Library**: Pre-built templates
- **Batch Upload**: Upload multiple templates at once
- **Template Testing**: Automated tests for templates

### 12.2 Phase 3 Features

- **Visual Editor**: WYSIWYG template builder
- **Template Sharing**: Share templates between tenants
- **A/B Testing**: Test multiple template versions
- **Analytics**: Track template performance

---

## Next Steps

1. ✅ Requirements approved
2. ✅ Design approved
3. ⏭️ Create task breakdown
4. ⏭️ Implement TemplatePreviewService
5. ⏭️ Implement API endpoints
6. ⏭️ Implement frontend components
7. ⏭️ Write tests
8. ⏭️ Deploy to Railway

---

## 13. AI-Powered Template Assistance

### 13.1 Overview

Instead of giving SysAdmin access to tenant templates (privacy concern), we use **OpenRouter AI** to help Tenant Administrators fix their own templates.

**Benefits**:

- ✅ Maintains tenant data privacy (no SysAdmin access)
- ✅ Self-service for tenants (no waiting for support)
- ✅ Learns from common errors
- ✅ Provides instant, context-aware help

### 13.2 AI Assistant Flow

```
User uploads template
    ↓
Validation fails
    ↓
User clicks "Get AI Help"
    ↓
System sends to OpenRouter:
  - Validation errors
  - Template code (sanitized)
  - Template type
  - Required placeholders
    ↓
AI analyzes and returns:
  - Problem explanation
  - Specific fix suggestions
  - Code examples
  - Optional auto-fix
    ↓
User reviews suggestions
    ↓
User accepts → System applies fixes
User rejects → User manually edits
    ↓
Re-validate template
```

### 13.3 API Endpoint: Get AI Help

**POST /api/tenant-admin/templates/ai-help**

**Request**:

```json
{
  "template_type": "str_invoice_nl",
  "template_content": "<html>...</html>",
  "validation_errors": [
    {
      "type": "missing_placeholder",
      "message": "Required placeholder '{{ invoice_number }}' not found",
      "severity": "error"
    }
  ]
}
```

**Response**:

```json
{
  "success": true,
  "ai_suggestions": {
    "analysis": "Your template is missing the required placeholder for invoice number. This field is essential for generating unique invoice identifiers.",
    "fixes": [
      {
        "issue": "Missing {{ invoice_number }} placeholder",
        "suggestion": "Add the invoice number placeholder in the header section",
        "code_example": "<div class=\"invoice-header\">\n  <h2>Invoice #{{ invoice_number }}</h2>\n</div>",
        "location": "line 15-20 (header section)",
        "auto_fixable": true
      }
    ],
    "auto_fix_available": true,
    "confidence": "high"
  }
}
```

### 13.4 Implementation: AITemplateAssistant

````python
# backend/src/services/ai_template_assistant.py

import os
import requests
from typing import Dict, List, Any

class AITemplateAssistant:
    """AI-powered template assistance using OpenRouter"""

    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.api_url = 'https://openrouter.ai/api/v1/chat/completions'
        self.model = 'anthropic/claude-3.5-sonnet'  # or your preferred model

    def get_fix_suggestions(
        self,
        template_type: str,
        template_content: str,
        validation_errors: List[Dict],
        required_placeholders: List[str]
    ) -> Dict[str, Any]:
        """Get AI suggestions for fixing template errors"""

        # Build prompt
        prompt = self._build_prompt(
            template_type,
            template_content,
            validation_errors,
            required_placeholders
        )

        # Call OpenRouter API
        response = requests.post(
            self.api_url,
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': self.model,
                'messages': [
                    {
                        'role': 'system',
                        'content': 'You are a helpful assistant that fixes HTML template errors. Provide specific, actionable fixes with code examples.'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'temperature': 0.3,  # Lower for more consistent fixes
                'max_tokens': 2000
            }
        )

        if response.status_code != 200:
            return {
                'success': False,
                'error': 'AI service unavailable'
            }

        # Parse AI response
        ai_response = response.json()
        suggestions = self._parse_ai_response(
            ai_response['choices'][0]['message']['content']
        )

        return {
            'success': True,
            'ai_suggestions': suggestions
        }

    def _build_prompt(
        self,
        template_type: str,
        template_content: str,
        validation_errors: List[Dict],
        required_placeholders: List[str]
    ) -> str:
        """Build prompt for AI"""

        # Sanitize template (remove any sensitive data)
        sanitized_template = self._sanitize_template(template_content)

        prompt = f"""
I have an HTML template for a {template_type} report that has validation errors.

**Required Placeholders**: {', '.join(required_placeholders)}

**Validation Errors**:
{self._format_errors(validation_errors)}

**Template Code** (first 500 lines):
```html
{sanitized_template[:10000]}  # Limit to 10KB
````

Please analyze the errors and provide:

1. A brief explanation of each issue
2. Specific fixes with code examples
3. The location in the template where fixes should be applied
4. Whether each fix can be auto-applied

Format your response as JSON:
{{
  "analysis": "Overall analysis",
  "fixes": [
    {{
      "issue": "Description of issue",
      "suggestion": "How to fix it",
      "code_example": "Code to add/replace",
      "location": "Where in template",
      "auto_fixable": true/false
    }}
],
"auto_fix_available": true/false,
"confidence": "high/medium/low"
}}
"""
return prompt

    def _sanitize_template(self, template_content: str) -> str:
        """Remove any potentially sensitive data from template"""
        import re

        # Remove any hardcoded email addresses
        template_content = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'email@example.com',
            template_content
        )

        # Remove any hardcoded phone numbers
        template_content = re.sub(
            r'\b\d{10,}\b',
            '0123456789',
            template_content
        )

        # Remove any hardcoded addresses (basic)
        # Keep placeholders like {{ address }}

        return template_content

    def _format_errors(self, errors: List[Dict]) -> str:
        """Format errors for prompt"""
        formatted = []
        for i, error in enumerate(errors, 1):
            formatted.append(
                f"{i}. [{error['type']}] {error['message']}"
            )
        return '\n'.join(formatted)

    def _parse_ai_response(self, response_text: str) -> Dict:
        """Parse AI response into structured format"""
        import json

        try:
            # Try to extract JSON from response
            # AI might wrap it in markdown code blocks
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end]
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end]

            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            # Fallback: return raw text
            return {
                'analysis': response_text,
                'fixes': [],
                'auto_fix_available': False,
                'confidence': 'low'
            }

    def apply_auto_fixes(
        self,
        template_content: str,
        fixes: List[Dict]
    ) -> str:
        """Apply auto-fixable suggestions to template"""

        modified_template = template_content

        for fix in fixes:
            if not fix.get('auto_fixable'):
                continue

            # Apply fix based on type
            if fix['issue'].startswith('Missing'):
                # Add missing placeholder
                modified_template = self._add_placeholder(
                    modified_template,
                    fix['code_example'],
                    fix.get('location', '')
                )

        return modified_template

    def _add_placeholder(
        self,
        template: str,
        code_to_add: str,
        location: str
    ) -> str:
        """Add missing placeholder to template"""
        # Simple implementation: add to end of body
        # More sophisticated: parse location and insert at right place

        if '</body>' in template:
            return template.replace('</body>', f'{code_to_add}\n</body>')
        else:
            return template + '\n' + code_to_add

````

### 13.5 Frontend: AI Help Button

```typescript
// frontend/src/components/TenantAdmin/TemplateManagement/AIHelpButton.tsx

import React, { useState } from 'react';

interface AIHelpButtonProps {
  templateType: string;
  templateContent: string;
  validationErrors: any[];
  onFixesApplied: (fixedTemplate: string) => void;
}

export const AIHelpButton: React.FC<AIHelpButtonProps> = ({
  templateType,
  templateContent,
  validationErrors,
  onFixesApplied
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState(null);

  const handleGetAIHelp = async () => {
    setIsLoading(true);

    try {
      const response = await fetch('/api/tenant-admin/templates/ai-help', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_type: templateType,
          template_content: templateContent,
          validation_errors: validationErrors
        })
      });

      const result = await response.json();

      if (result.success) {
        setSuggestions(result.ai_suggestions);
      }
    } catch (error) {
      console.error('AI help failed:', error);
      alert('AI assistance is temporarily unavailable');
    } finally {
      setIsLoading(false);
    }
  };

  const handleApplyFixes = async () => {
    if (!suggestions?.auto_fix_available) return;

    try {
      const response = await fetch('/api/tenant-admin/templates/apply-ai-fixes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_content: templateContent,
          fixes: suggestions.fixes
        })
      });

      const result = await response.json();

      if (result.success) {
        onFixesApplied(result.fixed_template);
        alert('AI fixes applied! Please review and re-validate.');
        setSuggestions(null);
      }
    } catch (error) {
      console.error('Apply fixes failed:', error);
    }
  };

  return (
    <div className="ai-help-section">
      <button
        onClick={handleGetAIHelp}
        disabled={isLoading || validationErrors.length === 0}
        className="btn btn-primary"
      >
        {isLoading ? '🤖 Analyzing...' : '🤖 Get AI Help'}
      </button>

      {suggestions && (
        <div className="ai-suggestions">
          <h4>AI Analysis</h4>
          <p>{suggestions.analysis}</p>

          <h5>Suggested Fixes:</h5>
          {suggestions.fixes.map((fix, index) => (
            <div key={index} className="fix-suggestion">
              <h6>{fix.issue}</h6>
              <p>{fix.suggestion}</p>
              <pre><code>{fix.code_example}</code></pre>
              <p className="location">Location: {fix.location}</p>
            </div>
          ))}

          {suggestions.auto_fix_available && (
            <button
              onClick={handleApplyFixes}
              className="btn btn-success"
            >
              ✨ Apply All Auto-Fixes
            </button>
          )}

          <p className="confidence">
            Confidence: {suggestions.confidence}
          </p>
        </div>
      )}
    </div>
  );
};
````

### 13.6 Privacy & Security

**What AI Sees**:

- ✅ Template HTML code (sanitized)
- ✅ Validation error messages
- ✅ Template type and required placeholders

**What AI Does NOT See**:

- ❌ Actual tenant data (invoices, reports, etc.)
- ❌ Sample data used for preview
- ❌ Tenant name or identifying information
- ❌ Google Drive credentials
- ❌ Database connection strings

**Data Sanitization**:

- Remove hardcoded emails, phones, addresses
- Remove any API keys or credentials
- Keep only template structure and placeholders

### 13.7 Cost Management

```python
# Track AI usage per tenant
class AIUsageTracker:
    def log_ai_request(self, administration, template_type, tokens_used):
        """Log AI API usage for billing/monitoring"""
        query = """
            INSERT INTO ai_usage_log
            (administration, feature, tokens_used, cost_estimate, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """
        cost = tokens_used * 0.00001  # Estimate based on model pricing
        self.db.execute(query, [
            administration,
            f'template_help_{template_type}',
            tokens_used,
            cost
        ])
```

### 13.8 Fallback Strategy

If AI is unavailable:

1. Show generic troubleshooting tips
2. Link to documentation
3. Provide example templates
4. Allow manual editing and re-validation

---

## 14. Updated Security Model

### 14.1 SysAdmin Access (Revised)

**SysAdmin CAN**:

- ✅ View aggregated metrics (# templates uploaded, validation success rate)
- ✅ View anonymized error patterns
- ✅ Configure AI assistance settings
- ✅ Monitor system health

**SysAdmin CANNOT**:

- ❌ View tenant-specific templates
- ❌ View tenant data
- ❌ Access tenant Google Drive
- ❌ Modify tenant templates

### 14.2 Tenant Data Privacy

All template assistance happens within tenant context:

- Tenant uploads template
- System validates with tenant's sample data
- AI helps fix template (no tenant data sent)
- Tenant approves and activates
- Template saved to tenant's Google Drive

**Zero cross-tenant data access.**
