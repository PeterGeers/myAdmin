# Internationalization Developer Guide

This guide provides comprehensive documentation for developers working with the internationalization (i18n) system in myAdmin.

## Table of Contents

1. [Overview](#overview)
2. [Translation Workflow](#translation-workflow)
3. [Adding New Translations](#adding-new-translations)
4. [Adding a New Language](#adding-a-new-language)
5. [Formatting Utilities](#formatting-utilities)
6. [Best Practices](#best-practices)
7. [Testing](#testing)
8. [Troubleshooting](#troubleshooting)

---

## Overview

myAdmin uses **react-i18next** for frontend internationalization and **Flask-Babel** for backend internationalization.

### Supported Languages

- **Dutch (nl)** - Primary language
- **English (en)** - Secondary language

### Architecture

```
Frontend (React + i18next)
├── Translation Files: frontend/src/locales/{lang}/{namespace}.json
├── Configuration: frontend/src/i18n.ts
├── Hook: useTypedTranslation(namespace)
└── Component: LanguageSelector

Backend (Flask + Flask-Babel)
├── Translation Detection: X-Language header
├── Services: email_template_service.py, tenant_language_service.py
└── Database: tenants.default_language, users.preferred_language
```

---

## Translation Workflow

### 1. Identify Translation Needs

When adding new UI text:

1. **Never hardcode text** - All user-facing text must be translatable
2. **Choose appropriate namespace** - Group related translations
3. **Use descriptive keys** - Make keys self-documenting

### 2. Add Translation Keys

**Frontend** - Add to both `nl` and `en` files:

```json
// frontend/src/locales/nl/common.json
{
  "buttons": {
    "save": "Opslaan",
    "cancel": "Annuleren"
  }
}

// frontend/src/locales/en/common.json
{
  "buttons": {
    "save": "Save",
    "cancel": "Cancel"
  }
}
```

**Backend** - Use Flask-Babel:

```python
from flask_babel import gettext as _

message = _('User created successfully')
```

### 3. Use Translations in Code

**Frontend**:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function MyComponent() {
  const { t } = useTypedTranslation('common');

  return (
    <Button>{t('buttons.save')}</Button>
  );
}
```

**Backend**:

```python
from services.i18n_service import get_translation

message = get_translation('user.created', language='nl')
```

### 4. Verify Completeness

Run translation completeness checks:

```bash
# Frontend
cd frontend
node scripts/check-translations.js

# Backend
cd backend
python scripts/check_translations.py
```

---

## Adding New Translations

### Frontend Translations

#### Step 1: Choose Namespace

Namespaces organize translations by feature:

- `common` - Shared UI elements (buttons, labels, messages)
- `auth` - Authentication and login
- `reports` - Financial reports
- `str` - Short-term rental features
- `banking` - Banking features
- `admin` - Administration features
- `errors` - Error messages
- `validation` - Form validation messages

#### Step 2: Add Keys to Both Languages

**Dutch** (`frontend/src/locales/nl/{namespace}.json`):

```json
{
  "myFeature": {
    "title": "Mijn Functie",
    "description": "Dit is een beschrijving",
    "actions": {
      "submit": "Verzenden",
      "reset": "Resetten"
    }
  }
}
```

**English** (`frontend/src/locales/en/{namespace}.json`):

```json
{
  "myFeature": {
    "title": "My Feature",
    "description": "This is a description",
    "actions": {
      "submit": "Submit",
      "reset": "Reset"
    }
  }
}
```

#### Step 3: Use in Component

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function MyFeature() {
  const { t } = useTypedTranslation('common');

  return (
    <div>
      <h1>{t('myFeature.title')}</h1>
      <p>{t('myFeature.description')}</p>
      <Button>{t('myFeature.actions.submit')}</Button>
      <Button>{t('myFeature.actions.reset')}</Button>
    </div>
  );
}
```

#### Step 4: Verify

```bash
cd frontend
node scripts/check-translations.js
```

### Backend Translations

Backend uses Flask-Babel for dynamic translations:

```python
from flask_babel import gettext as _

# Simple translation
message = _('Hello, World!')

# Translation with interpolation
message = _('Welcome, %(name)s!', name=user.name)

# Pluralization
message = ngettext(
    '%(num)d item',
    '%(num)d items',
    count
)
```

---

## Adding a New Language

### Prerequisites

- Language code (ISO 639-1, e.g., 'fr' for French)
- Native speaker for translations
- Flag emoji for UI

### Frontend Setup

#### Step 1: Create Translation Files

Create directory and files for new language:

```bash
mkdir -p frontend/src/locales/fr
```

Copy and translate all namespace files:

```bash
# Copy from Dutch as template
cp frontend/src/locales/nl/*.json frontend/src/locales/fr/
```

#### Step 2: Update i18n Configuration

Edit `frontend/src/i18n.ts`:

```typescript
const resources = {
  nl: {
    common: nlCommon,
    auth: nlAuth,
    // ... other namespaces
  },
  en: {
    common: enCommon,
    auth: enAuth,
    // ... other namespaces
  },
  fr: {
    // Add new language
    common: frCommon,
    auth: frAuth,
    // ... other namespaces
  },
};
```

#### Step 3: Update LanguageSelector

Edit `frontend/src/components/LanguageSelector.tsx`:

```typescript
const languages: Language[] = [
  { code: "nl", name: "Nederlands", flag: "🇳🇱" },
  { code: "en", name: "English", flag: "🇬🇧" },
  { code: "fr", name: "Français", flag: "🇫🇷" }, // Add new language
];
```

#### Step 4: Update Formatting Utilities

Edit `frontend/src/utils/formatting.ts`:

```typescript
export function formatDate(date: Date, language: string = "nl"): string {
  const locales: Record<string, string> = {
    nl: "nl-NL",
    en: "en-US",
    fr: "fr-FR", // Add new locale
  };

  return date.toLocaleDateString(locales[language] || "nl-NL");
}
```

#### Step 5: Update Database

Add language to tenant and user tables:

```sql
-- Update tenant default language
UPDATE tenants SET default_language = 'fr' WHERE name = 'FrenchTenant';

-- Update user preferred language
UPDATE users SET preferred_language = 'fr' WHERE email = 'user@example.fr';
```

### Backend Setup

#### Step 1: Update Language Detection

Edit `backend/src/services/tenant_language_service.py`:

```python
def validate_language_code(language: str) -> bool:
    """Validate language code"""
    return language in ['nl', 'en', 'fr']  # Add new language
```

#### Step 2: Create Email Templates

Create language-specific email templates:

```bash
cp backend/templates/email/user_invitation_nl.html \
   backend/templates/email/user_invitation_fr.html
```

Translate content in new template.

#### Step 3: Update Email Service

Edit `backend/src/services/email_template_service.py`:

```python
def get_invitation_subject(self, tenant: str, language: Optional[str] = None) -> str:
    if language == 'nl':
        return f"Welkom bij myAdmin - {tenant} Uitnodiging"
    elif language == 'en':
        return f"Welcome to myAdmin - {tenant} Invitation"
    elif language == 'fr':  # Add new language
        return f"Bienvenue à myAdmin - Invitation {tenant}"
    else:
        return f"Welcome to myAdmin - {tenant} Invitation"
```

### Testing New Language

1. **Switch language** in UI
2. **Verify translations** appear correctly
3. **Test date/number formatting**
4. **Test email templates**
5. **Run completeness check**

```bash
cd frontend
node scripts/check-translations.js
```

---

## Formatting Utilities

### Date Formatting

```typescript
import { formatDate } from "../utils/formatting";

// Format with current language
const formatted = formatDate(new Date(), i18n.language);

// Dutch: 18-02-2026
// English: 2/18/2026
```

### Number Formatting

```typescript
import { formatNumber } from "../utils/formatting";

// Format with current language
const formatted = formatNumber(1234.56, i18n.language);

// Dutch: 1.234,56
// English: 1,234.56
```

### Currency Formatting

```typescript
import { formatCurrency } from "../utils/formatting";

// Format with current language
const formatted = formatCurrency(1234.56, i18n.language);

// Dutch: €1.234,56
// English: €1,234.56
```

### Custom Formatting

```typescript
// Date with options
const date = new Date();
const formatted = date.toLocaleDateString(
  i18n.language === "nl" ? "nl-NL" : "en-US",
  {
    year: "numeric",
    month: "long",
    day: "numeric",
  },
);

// Dutch: 18 februari 2026
// English: February 18, 2026
```

---

## Best Practices

### Translation Keys

✅ **DO**:

- Use descriptive, hierarchical keys: `user.profile.edit.title`
- Group related translations: `buttons.save`, `buttons.cancel`
- Use consistent naming: `actions.submit`, `actions.delete`

❌ **DON'T**:

- Use generic keys: `text1`, `label2`
- Mix languages in keys: `gebruiker.profile`
- Use special characters: `user@profile`, `user profile`

### Translation Content

✅ **DO**:

- Keep translations concise
- Use consistent terminology
- Include context in comments
- Test with real data

❌ **DON'T**:

- Translate technical terms (API, URL, etc.)
- Use machine translation without review
- Include HTML in translations (use interpolation)
- Hardcode numbers or dates

### Component Usage

✅ **DO**:

```typescript
// Use typed hook
const { t } = useTypedTranslation("common");

// Use interpolation
t("welcome.message", { name: user.name });

// Use formatting utilities
formatDate(date, i18n.language);
```

❌ **DON'T**:

```typescript
// Don't use untyped hook
const { t } = useTranslation();

// Don't concatenate strings
`Welcome, ${user.name}!`;

// Don't hardcode formats
date.toLocaleDateString();
```

### Performance

✅ **DO**:

- Load only needed namespaces
- Use lazy loading for large translations
- Cache formatted values

❌ **DON'T**:

- Load all namespaces at once
- Format in render loops
- Re-translate static content

---

## Testing

### Unit Tests

Test translation keys exist:

```typescript
import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../i18n';

test('renders translated text', () => {
  render(
    <I18nextProvider i18n={i18n}>
      <MyComponent />
    </I18nextProvider>
  );

  expect(screen.getByText(/opslaan|save/i)).toBeInTheDocument();
});
```

### Integration Tests

Test language switching:

```typescript
test('switches language', async () => {
  const { rerender } = render(<MyComponent />);

  // Switch to English
  await i18n.changeLanguage('en');
  rerender(<MyComponent />);

  expect(screen.getByText('Save')).toBeInTheDocument();
});
```

### E2E Tests

Test complete user flows:

```typescript
test("user can switch language", async ({ page }) => {
  await page.goto("/");
  await page.click('[data-testid="language-selector"]');
  await page.click('[data-testid="language-option-en"]');

  const language = await page.evaluate(() =>
    localStorage.getItem("i18nextLng"),
  );

  expect(language).toBe("en");
});
```

### Completeness Check

Run automated checks:

```bash
# Frontend
cd frontend
node scripts/check-translations.js

# Backend
cd backend
python scripts/check_translations.py
```

---

## Troubleshooting

### Translation Not Showing

**Problem**: Translation key shows instead of translated text

**Solutions**:

1. Check key exists in both language files
2. Verify namespace is loaded
3. Check for typos in key path
4. Run completeness check

```bash
node scripts/check-translations.js
```

### Wrong Language Displayed

**Problem**: UI shows wrong language

**Solutions**:

1. Check localStorage: `localStorage.getItem('i18nextLng')`
2. Verify language selector state
3. Check tenant default_language in database
4. Clear browser cache

### Formatting Issues

**Problem**: Dates/numbers show wrong format

**Solutions**:

1. Verify `i18n.language` is correct
2. Check locale mapping in formatting utilities
3. Test with different locales
4. Use browser DevTools to inspect

### Missing Translations After Update

**Problem**: New translations not appearing

**Solutions**:

1. Clear browser cache
2. Restart development server
3. Check file was saved
4. Verify JSON syntax is valid

```bash
# Validate JSON
node -e "require('./frontend/src/locales/nl/common.json')"
```

### Backend Translation Issues

**Problem**: API returns wrong language

**Solutions**:

1. Check X-Language header is sent
2. Verify tenant default_language
3. Check user preferred_language
4. Review language detection logic

```python
# Debug language detection
print(f"X-Language header: {request.headers.get('X-Language')}")
print(f"Tenant language: {get_tenant_language(tenant)}")
```

---

## Additional Resources

- [react-i18next Documentation](https://react.i18next.com/)
- [Flask-Babel Documentation](https://python-babel.github.io/flask-babel/)
- [i18next Documentation](https://www.i18next.com/)
- [Internationalization Best Practices](https://www.w3.org/International/questions/qa-i18n)

---

## Support

For questions or issues:

1. Check this documentation
2. Review existing translations for examples
3. Run completeness checks
4. Check test files for usage patterns
5. Consult with team lead
