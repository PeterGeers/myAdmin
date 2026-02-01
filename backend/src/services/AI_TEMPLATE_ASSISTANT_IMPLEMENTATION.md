# AI Template Assistant Implementation Summary

**Date**: February 1, 2026  
**Status**: ✅ Complete  
**Test Results**: 38/38 tests passing

---

## Overview

Implemented the `AITemplateAssistant` service that provides AI-powered assistance for fixing template validation errors using the OpenRouter API. This service maintains tenant data privacy by sanitizing templates before sending them to the AI, ensuring no PII is exposed.

---

## Implementation Details

### File Created

- **`backend/src/services/ai_template_assistant.py`** (520 lines)
  - Complete AI template assistance service
  - All 8 required methods implemented
  - Comprehensive error handling
  - Privacy-first design with PII sanitization

### Test File Created

- **`backend/tests/unit/test_ai_template_assistant.py`** (670 lines)
  - 38 comprehensive unit tests
  - 100% test pass rate
  - Tests cover all methods and edge cases
  - Follows project testing standards

---

## Implemented Methods

### 1. `__init__()`

**Purpose**: Initialize the AI template assistant  
**Features**:

- Loads `OPENROUTER_API_KEY` from environment
- Sets API URL and model configuration
- Supports custom model via `OPENROUTER_MODEL` env var
- Logs warning if API key is not configured

**Tests**: 3 tests covering initialization scenarios

---

### 2. `get_fix_suggestions(template_type, template_content, validation_errors, required_placeholders)`

**Purpose**: Get AI suggestions for fixing template errors  
**Features**:

- Validates API key availability
- Sanitizes template to remove PII
- Builds structured prompt for AI
- Calls OpenRouter API with proper headers
- Parses AI response into structured format
- Comprehensive error handling (timeout, network errors, API errors)

**Returns**:

```python
{
    'success': bool,
    'ai_suggestions': {
        'analysis': str,
        'fixes': [
            {
                'issue': str,
                'suggestion': str,
                'code_example': str,
                'location': str,
                'auto_fixable': bool
            }
        ],
        'auto_fix_available': bool,
        'confidence': 'high' | 'medium' | 'low'
    },
    'error': str  # Only if success is False
}
```

**Tests**: 5 tests covering success, errors, timeout, and network failures

---

### 3. `_build_prompt(template_type, template_content, validation_errors, required_placeholders)`

**Purpose**: Build structured prompt for AI analysis  
**Features**:

- Includes template type and required placeholders
- Formats validation errors in readable format
- Includes sanitized template content (truncated to 10KB)
- Requests JSON response format
- Clear instructions for AI analysis

**Tests**: 6 tests covering prompt structure and content

---

### 4. `_sanitize_template(template_content)`

**Purpose**: Remove PII from template before sending to AI  
**Features**:

- Removes hardcoded email addresses (preserves `{{ email }}` placeholders)
- Removes hardcoded phone numbers (preserves `{{ phone }}` placeholders)
- Removes street addresses (preserves `{{ address }}` placeholders)
- Uses regex patterns with negative lookbehind/lookahead to preserve placeholders

**Privacy Protection**:

- ✅ Emails replaced with `email@example.com`
- ✅ Phone numbers replaced with `0123456789`
- ✅ Street addresses replaced with `123 Main Street`
- ✅ Placeholders like `{{ contact_email }}` are preserved

**Tests**: 6 tests covering PII removal and placeholder preservation

---

### 5. `_format_errors(errors)`

**Purpose**: Format validation errors for AI prompt  
**Features**:

- Converts error dictionaries to human-readable format
- Includes error type, message, severity, and line numbers
- Numbered list format for clarity
- Handles empty error lists

**Output Format**:

```
1. [missing_placeholder] Required placeholder not found [severity: error]
2. [syntax_error] Unclosed tag (line 45) [severity: error]
```

**Tests**: 4 tests covering various error formatting scenarios

---

### 6. `_parse_ai_response(response_text)`

**Purpose**: Parse AI response into structured format  
**Features**:

- Extracts JSON from markdown code blocks (`json or `)
- Validates response structure
- Adds missing required fields with defaults
- Fallback to raw text if JSON parsing fails
- Robust error handling

**Tests**: 5 tests covering valid JSON, markdown blocks, and invalid responses

---

### 7. `apply_auto_fixes(template_content, fixes)`

**Purpose**: Apply auto-fixable suggestions to template  
**Features**:

- Iterates through fixes and applies those marked as `auto_fixable`
- Skips fixes with invalid code examples
- Currently supports adding missing placeholders
- Returns original template if fixes fail
- Logs each fix applied

**Tests**: 4 tests covering fix application and error handling

---

### 8. `_add_placeholder(template, code_to_add, location)`

**Purpose**: Add missing placeholder to template  
**Features**:

- Intelligently places code based on location hint
- Supports specific sections: header, footer, body, main
- Falls back to adding before `</body>` tag
- Last resort: appends to end of template
- Handles templates without body tags

**Location Hints Supported**:

- "header section" → adds in `<header>` or `<head>`
- "footer section" → adds in `<footer>`
- "body section" or "main section" → adds in `<main>` or before `</body>`
- Default → adds before `</body>` or appends to end

**Tests**: 5 tests covering different insertion locations

---

## Test Coverage

### Test Classes

1. **TestAITemplateAssistantInit** (3 tests)
   - Initialization with/without API key
   - Custom model configuration

2. **TestTemplateSanitization** (6 tests)
   - Email, phone, and address removal
   - Placeholder preservation

3. **TestErrorFormatting** (4 tests)
   - Empty, single, and multiple errors
   - Line number formatting

4. **TestPromptBuilding** (6 tests)
   - Template type, placeholders, errors inclusion
   - Template truncation
   - JSON format request

5. **TestAIResponseParsing** (5 tests)
   - Valid JSON parsing
   - Markdown code block extraction
   - Invalid JSON fallback
   - Missing field handling

6. **TestAutoFixApplication** (4 tests)
   - Non-fixable skip
   - Placeholder addition
   - Multiple fixes
   - Error handling

7. **TestAddPlaceholder** (5 tests)
   - Header, footer, body, main sections
   - Default location
   - No body tag handling

8. **TestGetFixSuggestions** (5 tests)
   - No API key error
   - Successful API call
   - API errors
   - Timeout handling
   - Network errors

### Test Results

```
38 passed in 0.35s
```

All tests passing with no failures or warnings.

---

## Configuration

### Environment Variables

```bash
# Required
OPENROUTER_API_KEY=your-api-key-here

# Optional - No longer used (now uses smart fallback chain)
# The service automatically tries multiple models for reliability
```

### Smart Fallback Chain

The AI Template Assistant uses a **multi-model fallback strategy** for maximum cost savings and reliability:

1. **`google/gemini-flash-1.5`** (Primary - FREE)
   - Cost: **FREE**
   - Fast and good for structured output
   - Rate-limited but reliable
   - Tries this first to minimize costs

2. **`meta-llama/llama-3.2-3b-instruct:free`** (Free Backup)
   - Cost: **FREE**
   - Good for basic template analysis
   - Backup if Gemini is rate-limited

3. **`deepseek/deepseek-chat`** (Cheap Fallback)
   - Cost: $0.27 input / $1.10 output per 1M tokens
   - Excellent for code analysis and structured output
   - 93% cheaper than Claude 3.5 Sonnet
   - Used if free models fail

4. **`anthropic/claude-3.5-sonnet`** (Paid Fallback - Last Resort)
   - Cost: $3.00 input / $15.00 output per 1M tokens
   - Most reliable and capable
   - Only used if all cheaper models fail

### Benefits of Fallback Strategy

✅ **Cost Optimization**: Tries cheapest models first  
✅ **High Reliability**: Falls back if a model fails or is rate-limited  
✅ **No Configuration Needed**: Works out of the box  
✅ **Automatic Recovery**: Continues trying until success

### API Configuration

- **API URL**: `https://openrouter.ai/api/v1/chat/completions`
- **Temperature**: 0.3 (lower for consistent fixes)
- **Max Tokens**: 2000
- **Timeout**: 30 seconds per model attempt

---

## Privacy & Security

### What AI Sees

✅ Template HTML structure (sanitized)  
✅ Validation error messages  
✅ Template type and required placeholders

### What AI Does NOT See

❌ Actual tenant data (invoices, reports, etc.)  
❌ Sample data used for preview  
❌ Tenant name or identifying information  
❌ Google Drive credentials  
❌ Database connection strings  
❌ Hardcoded emails, phones, or addresses

### Data Sanitization Process

1. **Email Removal**: `john@example.com` → `email@example.com`
2. **Phone Removal**: `1234567890` → `0123456789`
3. **Address Removal**: `123 Main Street` → `123 Main Street` (generic)
4. **Placeholder Preservation**: `{{ contact_email }}` → unchanged

---

## Usage Example

```python
from services.ai_template_assistant import AITemplateAssistant

# Initialize assistant
assistant = AITemplateAssistant()

# Get fix suggestions
result = assistant.get_fix_suggestions(
    template_type='str_invoice_nl',
    template_content='<html><body>...</body></html>',
    validation_errors=[
        {
            'type': 'missing_placeholder',
            'message': "Required placeholder '{{ invoice_number }}' not found",
            'severity': 'error'
        }
    ],
    required_placeholders=['invoice_number', 'guest_name', 'amount']
)

if result['success']:
    suggestions = result['ai_suggestions']
    print(f"Analysis: {suggestions['analysis']}")

    for fix in suggestions['fixes']:
        print(f"Issue: {fix['issue']}")
        print(f"Suggestion: {fix['suggestion']}")
        print(f"Code: {fix['code_example']}")

    # Apply auto-fixes if available
    if suggestions['auto_fix_available']:
        fixed_template = assistant.apply_auto_fixes(
            template_content,
            suggestions['fixes']
        )
else:
    print(f"Error: {result['error']}")
```

---

## Integration Points

### Used By

- `backend/src/tenant_admin_routes.py` (future implementation)
  - POST `/api/tenant-admin/templates/ai-help`
  - POST `/api/tenant-admin/templates/apply-ai-fixes`

### Dependencies

- `requests` - HTTP client for OpenRouter API
- `os` - Environment variable access
- `re` - Regular expressions for sanitization
- `json` - JSON parsing
- `logging` - Logging functionality

---

## Error Handling

### API Key Not Set

```python
{
    'success': False,
    'error': 'AI service not configured - OPENROUTER_API_KEY not set'
}
```

### API Error (500)

```python
{
    'success': False,
    'error': 'AI service returned error: 500'
}
```

### Timeout

```python
{
    'success': False,
    'error': 'AI service request timed out'
}
```

### Network Error

```python
{
    'success': False,
    'error': 'AI service request failed: <error message>'
}
```

---

## Future Enhancements

### Potential Improvements

1. **Cost Tracking**: Log token usage and costs per tenant
2. **Caching**: Cache AI responses for identical errors
3. **More Fix Types**: Support for syntax errors, security issues
4. **Batch Processing**: Analyze multiple templates at once
5. **Custom Prompts**: Allow tenant-specific prompt customization
6. **Feedback Loop**: Learn from accepted/rejected suggestions

### Additional Fix Types

- Syntax error fixes (unclosed tags, mismatched tags)
- Security issue fixes (remove scripts, event handlers)
- Style improvements (formatting, indentation)
- Accessibility fixes (alt text, ARIA labels)

---

## Compliance

### Testing Standards

✅ Follows `.kiro/specs/Common/CICD/TEST_ORGANIZATION.md`  
✅ Unit tests in `backend/tests/unit/`  
✅ All tests use mocking (no external dependencies)  
✅ Fast execution (< 1 second total)  
✅ Descriptive test names  
✅ Comprehensive coverage

### Code Quality

✅ Type hints for all parameters  
✅ Comprehensive docstrings  
✅ Logging at appropriate levels  
✅ Error handling for all edge cases  
✅ No syntax errors or warnings

---

## Conclusion

The AI Template Assistant service is fully implemented and tested, providing a privacy-first approach to helping tenant administrators fix template validation errors. The service maintains zero cross-tenant data access and ensures no PII is sent to external AI services.

**Status**: ✅ Ready for integration with API routes  
**Next Step**: Implement API endpoints in `tenant_admin_routes.py`
