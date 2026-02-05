# Internationalization (i18n) Specification

**Status**: Draft
**Created**: February 5, 2026
**Priority**: High - Blocks Phase 3 & 4 implementation

---

## 📖 Overview

Make myAdmin fully language-agnostic, supporting multiple languages throughout the entire application. Initial languages: Dutch (nl) and English (en).

---

## 🎯 Scope

### What Needs Translation

**Frontend (React):**
- ✅ UI labels, buttons, menus
- ✅ Form labels and placeholders
- ✅ Error messages and validation
- ✅ Help text and tooltips
- ✅ Report titles and headers
- ✅ Email templates (user-facing)

**Backend (Python):**
- ✅ API error messages
- ✅ Email templates (system-generated)
- ✅ Report headers and labels
- ✅ Validation messages
- ✅ Notification messages

**Database:**
- ✅ Chart of accounts (account names)
- ✅ VAT rule descriptions
- ✅ Template metadata
- ✅ System messages

**Templates:**
- ✅ Report templates (HTML/XLSX)
- ✅ Invoice templates
- ✅ Email templates

---

## 🌍 Supported Languages

### Phase 1 (Initial)
- 🇳🇱 **Dutch (nl)** - Primary language
- 🇬🇧 **English (en)** - Secondary language

### Phase 2 (Future)
- 🇩🇪 German (de)
- 🇫🇷 French (fr)
- 🇪🇸 Spanish (es)

---

## 🏗️ Architecture

### Frontend: react-i18next

**Library**: `react-i18next` + `i18next`

**Structure:**
```
frontend/src/
├── locales/
│   ├── nl/
│   │   ├── common.json          # Common UI elements
│   │   ├── auth.json            # Authentication
│   │   ├── reports.json         # Reports module
│   │   ├── str.json             # STR module
│   │   ├── banking.json         # Banking module
│   │   ├── admin.json           # Admin modules
│   │   └── errors.json          # Error messages
│   │
│   └── en/
│       ├── common.json
│       ├── auth.json
│       ├── reports.json
│       ├── str.json
│       ├── banking.json
│       ├── admin.json
│       └── errors.json
│
├── i18n.ts                      # i18next configuration
└── components/
    └── LanguageSelector.tsx     # Language switcher
```

**Usage Example:**
```typescript
import { useTranslation } from 'react-i18next';

function MyComponent() {
  const { t } = useTranslation('common');
  
  return (
    <Button>{t('save')}</Button>
    <Text>{t('welcome', { name: user.name })}</Text>
  );
}
```

### Backend: Flask-Babel

**Library**: `Flask-Babel`

**Structure:**
```
backend/
├── translations/
│   ├── nl/
│   │   └── LC_MESSAGES/
│   │       ├── messages.po      # Translation file
│   │       └── messages.mo      # Compiled translations
│   │
│   └── en/
│       └── LC_MESSAGES/
│           ├── messages.po
│           └── messages.mo
│
├── babel.cfg                    # Babel configuration
└── src/
    └── i18n.py                  # i18n utilities
```

**Usage Example:**
```python
from flask_babel import gettext as _

@app.route('/api/example')
def example():
    return {
        'message': _('Operation successful'),
        'error': _('Invalid input')
    }
```

---

## 📋 Implementation Plan

### Phase 1: Infrastructure Setup (2 days)
- [ ] Install and configure react-i18next (frontend)
- [ ] Install and configure Flask-Babel (backend)
- [ ] Create translation file structure
- [ ] Create LanguageSelector component
- [ ] Store user language preference (localStorage + database)

### Phase 2: Frontend Translation (3-4 days)
- [ ] Extract all hardcoded strings
- [ ] Create translation keys
- [ ] Translate to Dutch and English
- [ ] Update all components to use t() function
- [ ] Test language switching

### Phase 3: Backend Translation (2-3 days)
- [ ] Extract all hardcoded strings
- [ ] Create .po files for nl and en
- [ ] Translate API messages
- [ ] Update email templates
- [ ] Test with different languages

### Phase 4: Database Content (2 days)
- [ ] Add language columns to relevant tables
- [ ] Create multilingual chart of accounts
- [ ] Create multilingual VAT rules
- [ ] Migration scripts for existing data

### Phase 5: Templates (2 days)
- [ ] Create language-specific report templates
- [ ] Update template service to select by language
- [ ] Test report generation in both languages

---

## 🗄️ Database Schema Changes

### User Preferences
```sql
ALTER TABLE users 
ADD COLUMN preferred_language VARCHAR(5) DEFAULT 'nl';
```

### Tenant Settings
```sql
ALTER TABLE tenants 
ADD COLUMN default_language VARCHAR(5) DEFAULT 'nl';
```

### Multilingual Content
```sql
-- Chart of Accounts with translations
CREATE TABLE account_translations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_number VARCHAR(20) NOT NULL,
    language VARCHAR(5) NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    description TEXT,
    UNIQUE KEY unique_account_lang (account_number, language),
    FOREIGN KEY (account_number) REFERENCES chart_of_accounts(account_number)
);

-- VAT Rules with translations
CREATE TABLE vat_rule_translations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vat_rule_id INT NOT NULL,
    language VARCHAR(5) NOT NULL,
    description TEXT NOT NULL,
    applies_to TEXT,
    UNIQUE KEY unique_vat_lang (vat_rule_id, language),
    FOREIGN KEY (vat_rule_id) REFERENCES vat_rules(id)
);
```

---

## 🎨 User Experience

### Language Selection

**User Level:**
- User can select preferred language in profile settings
- Language persists across sessions
- Overrides tenant default

**Tenant Level:**
- Tenant Admin sets default language for tenant
- New users inherit tenant default
- Can be overridden per user

**System Level:**
- SysAdmin sets platform default (Dutch)
- Used for new tenants
- Used for unauthenticated pages (login, etc.)

### Language Switcher UI
```
┌─────────────────────────────────┐
│  myAdmin                    🌍 NL│
│                               ▼  │
│  ┌──────────────────────────┐   │
│  │ 🇳🇱 Nederlands           │   │
│  │ 🇬🇧 English              │   │
│  └──────────────────────────┘   │
└─────────────────────────────────┘
```

---

## 📝 Translation File Examples

### frontend/src/locales/nl/common.json
```json
{
  "save": "Opslaan",
  "cancel": "Annuleren",
  "delete": "Verwijderen",
  "edit": "Bewerken",
  "close": "Sluiten",
  "welcome": "Welkom, {{name}}!",
  "loading": "Laden...",
  "error": "Er is een fout opgetreden",
  "success": "Succesvol opgeslagen"
}
```

### frontend/src/locales/en/common.json
```json
{
  "save": "Save",
  "cancel": "Cancel",
  "delete": "Delete",
  "edit": "Edit",
  "close": "Close",
  "welcome": "Welcome, {{name}}!",
  "loading": "Loading...",
  "error": "An error occurred",
  "success": "Successfully saved"
}
```

### frontend/src/locales/nl/reports.json
```json
{
  "title": "Rapporten",
  "financial": "Financiële Rapporten",
  "actuals": "Actuele Balans",
  "profitLoss": "Winst & Verlies",
  "btw": "BTW Aangifte",
  "aangifteIb": "Aangifte IB",
  "generateReport": "Rapport Genereren",
  "selectYear": "Selecteer Jaar",
  "selectQuarter": "Selecteer Kwartaal"
}
```

---

## 🔗 Integration Points

### Starter Package System
- Chart of accounts: `default_nl.json`, `default_en.json`
- VAT rules: `netherlands_nl.json`, `netherlands_en.json`
- Templates: `str_invoice_nl.html`, `str_invoice_en.html`
- Email templates: `invitation_nl.html`, `invitation_en.html`

### Report Generation
```python
def generate_report(tenant, report_type, language):
    # Get template in user's language
    template = get_template(report_type, language)
    
    # Get translations for report labels
    labels = get_report_labels(report_type, language)
    
    # Generate report
    return render_template(template, data=data, labels=labels)
```

---

## ⚠️ Impact on Existing Specs

### SysAdmin Module
- **Update**: Starter Package Management must support multiple languages
- **Add**: Language selection when creating tenant
- **Add**: Upload translations for chart of accounts, VAT rules

### Tenant Admin Module
- **Update**: Template Management must support language selection
- **Add**: Language preference in tenant settings
- **Add**: User language preference management

### Railway Migration
- **Blocker**: Phase 3 & 4 should implement i18n from the start
- **Recommendation**: Add Phase 2.5 for i18n infrastructure

---

## 📊 Estimated Effort

| Phase | Effort | Priority |
|-------|--------|----------|
| Infrastructure Setup | 2 days | High |
| Frontend Translation | 3-4 days | High |
| Backend Translation | 2-3 days | High |
| Database Content | 2 days | Medium |
| Templates | 2 days | Medium |
| **Total** | **11-13 days** | **2-3 weeks** |

---

## 🎯 Success Criteria

- ✅ User can switch language and see entire UI translated
- ✅ Reports generate in user's preferred language
- ✅ Email notifications sent in user's language
- ✅ Chart of accounts displays in user's language
- ✅ No hardcoded strings in code
- ✅ New languages can be added without code changes

---

## 📚 Related Specifications

- **SysAdmin Module**: Starter Package Management
- **Tenant Admin Module**: User Management, Settings
- **Railway Migration**: Phase 2.5 (new) or Phase 3

---

## 🆘 Questions to Answer

1. **When to implement?** 
   - Option A: Before Phase 3 (recommended - clean slate)
   - Option B: After Phase 5 (refactor existing code)

2. **Translation workflow?**
   - Who translates? (You, professional translator, AI?)
   - How to manage translations? (JSON files, translation service?)

3. **Date/Number formatting?**
   - Dutch: 1.234,56 (comma decimal, dot thousands)
   - English: 1,234.56 (dot decimal, comma thousands)

4. **Currency?**
   - Always EUR, or support multiple currencies?

---

## Next Steps

1. Review this specification
2. Decide when to implement (before or after Phase 3?)
3. Create detailed requirements.md and design.md
4. Update Railway migration plan to include i18n phase

---

**This is a foundational change that affects everything. Should we implement it before continuing with Phase 3 & 4?**
