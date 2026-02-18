# Internationalization (i18n) - Technical Design

**Status**: Ready for Implementation
**Created**: February 17, 2026

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  React Components                                       │ │
│  │  - useTranslation() hook                               │ │
│  │  - t('key') function calls                             │ │
│  └────────────────┬───────────────────────────────────────┘ │
│                   │                                          │
│  ┌────────────────▼───────────────────────────────────────┐ │
│  │  i18next Library                                        │ │
│  │  - Language detection                                   │ │
│  │  - Translation loading                                  │ │
│  │  - Interpolation & pluralization                        │ │
│  └────────────────┬───────────────────────────────────────┘ │
│                   │                                          │
│  ┌────────────────▼───────────────────────────────────────┐ │
│  │  Translation Files (JSON)                               │ │
│  │  /locales/nl/*.json                                     │ │
│  │  /locales/en/*.json                                     │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                         Backend                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Flask Routes                                           │ │
│  │  - gettext() / _() function calls                      │ │
│  └────────────────┬───────────────────────────────────────┘ │
│                   │                                          │
│  ┌────────────────▼───────────────────────────────────────┐ │
│  │  Flask-Babel                                            │ │
│  │  - Locale detection from X-Language header             │ │
│  │  - Translation loading                                  │ │
│  └────────────────┬───────────────────────────────────────┘ │
│                   │                                          │
│  ┌────────────────▼───────────────────────────────────────┐ │
│  │  Translation Files (.po/.mo)                            │ │
│  │  /translations/nl/LC_MESSAGES/messages.po               │ │
│  │  /translations/en/LC_MESSAGES/messages.po               │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                         Database                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  users (preferred_language)                             │ │
│  │  tenants (default_language)                             │ │
│  │  account_translations (account_number, language, name)  │ │
│  │  vat_rule_translations (vat_rule_id, language, desc)    │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Frontend Design

### 2.1 i18next Configuration

**File**: `frontend/src/i18n.ts`

```typescript
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

// Import translation files
import commonNl from "./locales/nl/common.json";
import commonEn from "./locales/en/common.json";
import authNl from "./locales/nl/auth.json";
import authEn from "./locales/en/auth.json";
import reportsNl from "./locales/nl/reports.json";
import reportsEn from "./locales/en/reports.json";
// ... more imports

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      nl: {
        common: commonNl,
        auth: authNl,
        reports: reportsNl,
        // ... more namespaces
      },
      en: {
        common: commonEn,
        auth: authEn,
        reports: reportsEn,
        // ... more namespaces
      },
    },
    fallbackLng: "en",
    defaultNS: "common",
    interpolation: {
      escapeValue: false, // React already escapes
    },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
  });

export default i18n;
```

### 2.2 Translation File Structure

```
frontend/src/locales/
├── nl/
│   ├── common.json          # Buttons, labels, common UI
│   ├── auth.json            # Login, registration, password
│   ├── reports.json         # Report generation, filters
│   ├── str.json             # STR module
│   ├── banking.json         # Banking module
│   ├── admin.json           # Admin modules
│   ├── errors.json          # Error messages
│   └── validation.json      # Form validation messages
│
└── en/
    ├── common.json
    ├── auth.json
    ├── reports.json
    ├── str.json
    ├── banking.json
    ├── admin.json
    ├── errors.json
    └── validation.json
```

### 2.3 Component Usage Pattern

```typescript
import { useTranslation } from 'react-i18next';

function MyComponent() {
  const { t, i18n } = useTranslation(['common', 'reports']);

  return (
    <Box>
      <Heading>{t('reports:title')}</Heading>
      <Button onClick={() => i18n.changeLanguage('nl')}>
        {t('common:save')}
      </Button>
      <Text>{t('common:welcome', { name: user.name })}</Text>
    </Box>
  );
}
```

### 2.4 Language Selector Component

**File**: `frontend/src/components/LanguageSelector.tsx`

```typescript
import { Menu, MenuButton, MenuList, MenuItem, Button } from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import { useState, useEffect } from 'react';

const languages = [
  { code: 'nl', name: 'Nederlands', flag: '🇳🇱' },
  { code: 'en', name: 'English', flag: '🇬🇧' }
];

export function LanguageSelector() {
  const { i18n } = useTranslation();
  const [currentLang, setCurrentLang] = useState(i18n.language);

  const changeLanguage = async (langCode: string) => {
    await i18n.changeLanguage(langCode);
    setCurrentLang(langCode);

    // Save to backend
    await fetch('/api/user/language', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: langCode })
    });
  };

  const current = languages.find(l => l.code === currentLang);

  return (
    <Menu>
      <MenuButton as={Button} size="sm">
        {current?.flag} {current?.code.toUpperCase()}
      </MenuButton>
      <MenuList>
        {languages.map(lang => (
          <MenuItem
            key={lang.code}
            onClick={() => changeLanguage(lang.code)}
          >
            {lang.flag} {lang.name}
          </MenuItem>
        ))}
      </MenuList>
    </Menu>
  );
}
```

### 2.5 Date/Number Formatting Utilities

**File**: `frontend/src/utils/formatting.ts`

```typescript
import { format as dateFnsFormat } from "date-fns";
import { nl, enUS } from "date-fns/locale";

const locales = { nl, en: enUS };

export function formatDate(date: Date, language: string): string {
  const locale = locales[language as keyof typeof locales];
  return dateFnsFormat(date, "P", { locale }); // Localized date format
}

export function formatNumber(value: number, language: string): string {
  return new Intl.NumberFormat(language === "nl" ? "nl-NL" : "en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatCurrency(value: number, language: string): string {
  return new Intl.NumberFormat(language === "nl" ? "nl-NL" : "en-US", {
    style: "currency",
    currency: "EUR",
  }).format(value);
}
```

---

## 3. Backend Design

### 3.1 Flask-Babel Configuration

**File**: `backend/src/i18n.py`

```python
from flask import request
from flask_babel import Babel

def get_locale():
    """Determine locale from X-Language header or default to 'nl'"""
    return request.headers.get('X-Language', 'nl')

def init_babel(app):
    """Initialize Flask-Babel"""
    babel = Babel(app, locale_selector=get_locale)
    return babel
```

**File**: `backend/src/app.py`

```python
from flask import Flask
from src.i18n import init_babel

app = Flask(__name__)
app.config['BABEL_DEFAULT_LOCALE'] = 'nl'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

babel = init_babel(app)
```

### 3.2 Translation File Structure

```
backend/
├── babel.cfg                # Babel extraction config
├── translations/
│   ├── nl/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po  # Human-readable translations
│   │       └── messages.mo  # Compiled binary
│   │
│   └── en/
│       └── LC_MESSAGES/
│           ├── messages.po
│           └── messages.mo
```

### 3.3 Babel Configuration

**File**: `backend/babel.cfg`

```ini
[python: **.py]
[jinja2: **/templates/**.html]
encoding = utf-8
```

### 3.4 Usage in Routes

```python
from flask import Blueprint, jsonify
from flask_babel import gettext as _

@app.route('/api/example', methods=['POST'])
def example():
    try:
        # Business logic
        return jsonify({
            'message': _('Operation successful'),
            'data': result
        })
    except ValueError:
        return jsonify({
            'error': _('Invalid input provided')
        }), 400
```

### 3.5 Translation Workflow

```bash
# 1. Extract translatable strings from code
pybabel extract -F babel.cfg -o messages.pot .

# 2. Initialize new language (first time only)
pybabel init -i messages.pot -d translations -l nl
pybabel init -i messages.pot -d translations -l en

# 3. Update existing translations (after code changes)
pybabel update -i messages.pot -d translations

# 4. Edit .po files manually or with tool

# 5. Compile translations
pybabel compile -d translations
```

---

## 4. Database Design

### 4.1 User Language Preference

**IMPORTANT**: Users are stored in AWS Cognito, NOT in a local database table.

**Design Decision**: Store user language preference in Cognito custom attributes

**Rationale**:

- Users already exist in Cognito with email, name, roles
- Cognito supports custom attributes for additional user data
- No need for separate user_preferences table
- Consistent with existing authentication architecture
- Simplifies data model and reduces database queries

**Implementation**:

- Use Cognito custom attribute: `custom:preferred_language`
- Default value: 'nl' (set during user creation)
- Updated via Cognito Admin API when user changes language
- Retrieved from JWT token payload (included in ID token)

**Alternative Considered**: Create separate `user_preferences` table keyed by Cognito user ID (sub claim)

- Rejected because it adds unnecessary complexity and database overhead
- Cognito custom attributes are designed for exactly this use case

**Fallback**: If custom attribute not set, use localStorage on frontend and X-Language header on backend

### 4.2 Tenant Default Language

```sql
ALTER TABLE tenants
ADD COLUMN default_language VARCHAR(5) DEFAULT 'nl'
AFTER tenant_name;

CREATE INDEX idx_tenants_language ON tenants(default_language);
```

### 4.3 Chart of Accounts Translations

```sql
CREATE TABLE account_translations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_number VARCHAR(20) NOT NULL,
    language VARCHAR(5) NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_account_lang (account_number, language),
    FOREIGN KEY (account_number)
        REFERENCES chart_of_accounts(account_number)
        ON DELETE CASCADE,

    INDEX idx_language (language),
    INDEX idx_account_number (account_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 4.4 VAT Rule Translations

```sql
CREATE TABLE vat_rule_translations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vat_rule_id INT NOT NULL,
    language VARCHAR(5) NOT NULL,
    description TEXT NOT NULL,
    applies_to TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_vat_lang (vat_rule_id, language),
    FOREIGN KEY (vat_rule_id)
        REFERENCES vat_rules(id)
        ON DELETE CASCADE,

    INDEX idx_language (language),
    INDEX idx_vat_rule_id (vat_rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 4.5 User Language Preference via Cognito

```python
import boto3

def get_user_language(user_email):
    """Get user's preferred language from Cognito"""
    try:
        cognito = boto3.client('cognito-idp')
        response = cognito.admin_get_user(
            UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
            Username=user_email
        )

        # Extract custom:preferred_language attribute
        for attr in response.get('UserAttributes', []):
            if attr['Name'] == 'custom:preferred_language':
                return attr['Value']

        # Default to Dutch if not set
        return 'nl'
    except Exception as e:
        print(f"Error getting user language: {e}")
        return 'nl'  # Fallback to default

def update_user_language(user_email, language):
    """Update user's preferred language in Cognito"""
    try:
        cognito = boto3.client('cognito-idp')
        cognito.admin_update_user_attributes(
            UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
            Username=user_email,
            UserAttributes=[
                {
                    'Name': 'custom:preferred_language',
                    'Value': language
                }
            ]
        )
        return True
    except Exception as e:
        print(f"Error updating user language: {e}")
        return False
```

### 4.6 Database Query Pattern

```python
def get_chart_of_accounts(language='nl'):
    """Get chart of accounts with translations"""
    query = """
        SELECT
            c.account_number,
            COALESCE(t.account_name, c.account_name) as account_name,
            COALESCE(t.description, c.description) as description,
            c.account_type,
            c.is_active
        FROM chart_of_accounts c
        LEFT JOIN account_translations t
            ON c.account_number = t.account_number
            AND t.language = %s
        WHERE c.is_active = 1
        ORDER BY c.account_number
    """
    return execute_query(query, (language,))
```

---

## 5. API Design

### 5.1 Language Header

All API requests include language preference:

```
X-Language: nl
```

Frontend automatically adds this header:

```typescript
// In API service
const headers = {
  "Content-Type": "application/json",
  "X-Language": i18n.language,
};
```

### 5.2 User Language Endpoints

**GET /api/user/language**

Returns user's preferred language from Cognito custom attribute.

Response:

```json
{
  "language": "nl"
}
```

**PUT /api/user/language**

Updates user's preferred language in Cognito custom attribute.

Request:

```json
{
  "language": "en"
}
```

Response:

```json
{
  "message": "Language preference updated",
  "language": "en"
}
```

**Implementation Notes**:

- Uses Cognito Admin API to read/write custom:preferred_language attribute
- Requires AWS credentials with cognito-idp:AdminGetUser and cognito-idp:AdminUpdateUserAttributes permissions
- Falls back to 'nl' if attribute not set
- Validates language code against whitelist ['nl', 'en']

### 5.3 Tenant Language Endpoints

**GET /api/tenant/language**

```json
{
  "default_language": "nl"
}
```

**PUT /api/tenant/language** (Tenant Admin only)

```json
{
  "default_language": "en"
}
```

---

## 6. Report Generation Design

### 6.1 Template Selection

```python
def get_report_template(report_type, language):
    """Get report template for language"""
    template_path = f"templates/reports/{report_type}_{language}.html"

    # Fallback to English if language template doesn't exist
    if not os.path.exists(template_path):
        template_path = f"templates/reports/{report_type}_en.html"

    return template_path
```

### 6.2 Report Labels

```python
from flask_babel import gettext as _

def get_report_labels(report_type, language):
    """Get translated labels for report"""
    with force_locale(language):
        if report_type == 'profit_loss':
            return {
                'title': _('Profit & Loss Statement'),
                'revenue': _('Revenue'),
                'expenses': _('Expenses'),
                'net_profit': _('Net Profit')
            }
        # ... more report types
```

### 6.3 Excel Export

```python
def export_to_excel(data, language):
    """Export data to Excel with translated headers"""
    wb = openpyxl.Workbook()
    ws = wb.active

    # Translated headers
    headers = get_excel_headers(language)
    ws.append(headers)

    # Format numbers according to language
    for row in data:
        formatted_row = format_row(row, language)
        ws.append(formatted_row)

    return wb
```

---

## 7. Email Template Design

### 7.1 Template Structure

```
backend/templates/emails/
├── invitation_nl.html
├── invitation_en.html
├── password_reset_nl.html
├── password_reset_en.html
├── notification_nl.html
└── notification_en.html
```

### 7.2 Email Sending

```python
def send_email(recipient, template_name, context):
    """Send email in recipient's language"""
    language = get_user_language(recipient)
    template = f"{template_name}_{language}.html"

    html_content = render_template(template, **context)

    # Send email
    send_ses_email(
        to=recipient,
        subject=context['subject'],
        html=html_content
    )
```

---

## 8. Testing Strategy

### 8.1 Frontend Tests

```typescript
// Test language switching
describe('LanguageSelector', () => {
  it('changes language when selected', async () => {
    render(<LanguageSelector />);

    const button = screen.getByRole('button');
    fireEvent.click(button);

    const nlOption = screen.getByText(/Nederlands/);
    fireEvent.click(nlOption);

    await waitFor(() => {
      expect(i18n.language).toBe('nl');
    });
  });
});

// Test translations
describe('MyComponent', () => {
  it('displays Dutch text', () => {
    i18n.changeLanguage('nl');
    render(<MyComponent />);
    expect(screen.getByText('Opslaan')).toBeInTheDocument();
  });

  it('displays English text', () => {
    i18n.changeLanguage('en');
    render(<MyComponent />);
    expect(screen.getByText('Save')).toBeInTheDocument();
  });
});
```

### 8.2 Backend Tests

```python
def test_api_with_dutch_language():
    """Test API returns Dutch messages"""
    response = client.post('/api/example',
        headers={'X-Language': 'nl'})

    assert response.json['message'] == 'Operatie geslaagd'

def test_api_with_english_language():
    """Test API returns English messages"""
    response = client.post('/api/example',
        headers={'X-Language': 'en'})

    assert response.json['message'] == 'Operation successful'
```

### 8.3 Translation Completeness Test

```python
import json
import os

def test_translation_completeness():
    """Ensure all keys exist in both languages"""
    nl_dir = 'frontend/src/locales/nl'
    en_dir = 'frontend/src/locales/en'

    for filename in os.listdir(nl_dir):
        with open(f'{nl_dir}/{filename}') as f:
            nl_keys = set(json.load(f).keys())

        with open(f'{en_dir}/{filename}') as f:
            en_keys = set(json.load(f).keys())

        assert nl_keys == en_keys, f"Missing keys in {filename}"
```

---

## 9. Migration Strategy

### 9.1 Phase 1: Infrastructure (No User Impact)

- Install libraries
- Create translation file structure
- Add database columns (with defaults)
- No UI changes yet

### 9.2 Phase 2: Backend Translation (Gradual)

- Add `_()` calls to routes
- Generate .po files
- Translate strings
- Deploy (still works with existing frontend)

### 9.3 Phase 3: Frontend Translation (Module by Module)

- Start with common components
- Then auth module
- Then reports module
- Then admin modules
- Deploy incrementally

### 9.4 Phase 4: Database Content

- Populate account_translations table
- Populate vat_rule_translations table
- Update queries to use translations

### 9.5 Rollback Plan

- Database columns have defaults (no breaking changes)
- Frontend falls back to English if translation missing
- Backend returns English if locale not found
- Can disable i18n by removing language selector

---

## 10. Performance Considerations

### 10.1 Frontend Optimization

- Lazy load translation files per module
- Cache translations in localStorage
- Minimize bundle size with tree shaking

### 10.2 Backend Optimization

- Compile .po files to .mo (binary format)
- Cache translations in memory
- Use database indexes on language columns

### 10.3 Database Optimization

- Index on (account_number, language)
- Index on (vat_rule_id, language)
- Use LEFT JOIN for optional translations

---

## 11. Security Considerations

### 11.1 Input Validation

- Validate language code against whitelist ['nl', 'en']
- Sanitize translation file paths
- Prevent directory traversal attacks

### 11.2 XSS Prevention

- React automatically escapes translations
- Use `escapeValue: false` only when safe
- Sanitize user-provided content in translations

### 11.3 SQL Injection Prevention

- Use parameterized queries for language parameter
- Validate language code before database queries

---

## 12. Deployment Checklist

- [ ] Install npm packages: `react-i18next`, `i18next`, `date-fns`
- [ ] Install pip packages: `Flask-Babel`
- [ ] Create translation file structure
- [ ] Run database migrations
- [ ] Compile backend translations
- [ ] Build frontend with translations
- [ ] Test language switching
- [ ] Verify reports in both languages
- [ ] Test email templates
- [ ] Update documentation

---

## 13. Maintenance

### 13.1 Adding New Translations

1. Add key to all language files
2. Run translation completeness test
3. Deploy

### 13.2 Adding New Language

1. Create new locale directory
2. Copy English translations as base
3. Translate all strings
4. Add to language selector
5. Test thoroughly

### 13.3 Updating Translations

1. Edit JSON files (frontend) or .po files (backend)
2. Compile backend translations
3. Deploy

---

## 14. Related Documents

- **README.md** - Overview and architecture
- **requirements.md** - User stories and acceptance criteria
- **TASKS.md** - Implementation checklist (to be created)

---
