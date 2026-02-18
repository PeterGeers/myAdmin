# Internationalization (i18n) - Requirements

**Status**: Ready for Implementation
**Created**: February 17, 2026

---

## 1. User Stories

### US-1: Language Selection

**As a** user  
**I want to** select my preferred language (Dutch or English)  
**So that** I can use the application in my native language

**Acceptance Criteria:**

- [ ] Language selector visible in user profile settings
- [ ] Language selector shows flag icons and language names
- [ ] Selected language persists across sessions
- [ ] UI updates immediately after language change (no page refresh)
- [ ] Language preference stored in database

---

### US-2: Multilingual UI

**As a** user  
**I want to** see all UI elements in my selected language  
**So that** I can understand and navigate the application easily

**Acceptance Criteria:**

- [ ] All buttons, labels, and menus translated
- [ ] All form fields and placeholders translated
- [ ] All error messages and validation text translated
- [ ] All help text and tooltips translated
- [ ] All page titles and headers translated
- [ ] No hardcoded strings visible in UI

---

### US-3: Multilingual Reports

**As a** user  
**I want to** generate reports in my selected language  
**So that** I can share them with stakeholders who speak that language

**Acceptance Criteria:**

- [ ] Report headers and labels in user's language
- [ ] Chart of accounts names in user's language
- [ ] Date formats match language convention
- [ ] Number formats match language convention (1.234,56 vs 1,234.56)
- [ ] Currency symbol displayed correctly (€)

---

### US-4: Multilingual Email Notifications

**As a** user  
**I want to** receive email notifications in my selected language  
**So that** I can understand system communications

**Acceptance Criteria:**

- [ ] Email subject lines translated
- [ ] Email body content translated
- [ ] Email templates exist for both languages
- [ ] System-generated emails use recipient's language preference

---

### US-5: Tenant Default Language

**As a** Tenant Admin  
**I want to** set a default language for my tenant  
**So that** new users automatically get the appropriate language

**Acceptance Criteria:**

- [ ] Tenant settings include default language option
- [ ] New users inherit tenant's default language
- [ ] Users can override tenant default with personal preference
- [ ] Tenant default applies to unauthenticated pages (login)

---

### US-6: Multilingual Chart of Accounts

**As a** user  
**I want to** see chart of accounts in my selected language  
**So that** I can understand account names and descriptions

**Acceptance Criteria:**

- [ ] Account names translated in dropdown lists
- [ ] Account descriptions translated in detail views
- [ ] Search works in both languages
- [ ] Filters work with translated names
- [ ] Export includes translated names

---

### US-7: Date and Number Formatting

**As a** user  
**I want to** see dates and numbers formatted according to my language  
**So that** I can read them naturally

**Acceptance Criteria:**

- [ ] Dutch: dates as DD-MM-YYYY
- [ ] English: dates as MM/DD/YYYY
- [ ] Dutch: numbers as 1.234,56
- [ ] English: numbers as 1,234.56
- [ ] Currency always EUR (€) regardless of language
- [ ] Formatting applies to all reports and UI

---

## 2. Functional Requirements

### FR-1: Frontend Translation System

- React application must use `react-i18next` library
- Translation files organized by module (common, auth, reports, etc.)
- Translation keys follow dot notation (e.g., `common.save`, `reports.title`)
- Support for interpolation (e.g., `Welcome, {{name}}!`)
- Support for pluralization (e.g., `1 item` vs `2 items`)
- Fallback to English if translation missing

### FR-2: Backend Translation System

- Flask application must use `Flask-Babel` library
- Translation files in `.po` format
- API error messages translated
- Email templates translated
- Report generation supports language parameter

### FR-3: Language Storage

- User language preference stored in `users` table
- Tenant default language stored in `tenants` table
- Language code format: ISO 639-1 (nl, en)
- Frontend stores language in localStorage for performance

### FR-4: Database Translations

- Chart of accounts translations in `account_translations` table
- VAT rule translations in `vat_rule_translations` table
- Foreign key constraints ensure data integrity
- Unique constraint on (entity_id, language) pairs

### FR-5: Date/Number Formatting

- Use `date-fns` library with locale support
- Dutch locale: `nl` from `date-fns/locale`
- English locale: `enUS` from `date-fns/locale`
- Number formatting using `Intl.NumberFormat`
- Currency formatting always EUR (€)

---

## 3. Non-Functional Requirements

### NFR-1: Performance

- Translation files lazy-loaded per module
- Initial page load < 2 seconds
- Language switch < 500ms
- No performance degradation with translations

### NFR-2: Maintainability

- Translation keys centralized in JSON files
- No hardcoded strings in code
- Translation files in version control
- Clear naming convention for translation keys

### NFR-3: Scalability

- Architecture supports adding new languages
- No code changes required to add language
- Translation files can be edited by non-developers

### NFR-4: Compatibility

- Works in all supported browsers (Chrome, Firefox, Safari, Edge)
- Mobile responsive language selector
- No breaking changes to existing functionality

### NFR-5: Data Integrity

- Language preference changes don't affect data
- Reports remain consistent regardless of language
- Database queries work with translated content

---

## 4. Technical Constraints

### TC-1: Libraries

- Frontend: `react-i18next` v13+ and `i18next` v23+
- Backend: `Flask-Babel` v4+
- Date formatting: `date-fns` v3+

### TC-2: Browser Support

- Modern browsers with ES6+ support
- localStorage available for language persistence

### TC-3: Database

- MySQL 8.0+ for translation tables
- UTF-8 encoding for all text fields

### TC-4: Deployment

- Translation files deployed with application
- No external translation services required
- No runtime translation API calls

---

## 5. Supported Languages

### Phase 1 (Initial Implementation)

- 🇳🇱 **Dutch (nl)** - Primary language
- 🇬🇧 **English (en)** - Secondary language

### Phase 2 (Future)

- 🇩🇪 German (de)
- 🇫🇷 French (fr)
- 🇪🇸 Spanish (es)

---

## 6. Out of Scope

### Not Included in Phase 1:

- ❌ Right-to-left (RTL) language support
- ❌ Multi-currency support (EUR only)
- ❌ Automatic language detection from browser
- ❌ Translation management UI (manual JSON editing)
- ❌ Machine translation integration
- ❌ Translation versioning/history
- ❌ Translation quality metrics
- ❌ User-contributed translations

---

## 7. Dependencies

### Internal Dependencies:

- Chart of Accounts Management (deployed)
- User Management system
- Tenant Management system
- Report generation system
- Email notification system

### External Dependencies:

- `react-i18next` npm package
- `i18next` npm package
- `Flask-Babel` pip package
- `date-fns` npm package

---

## 8. Success Metrics

### Quantitative:

- 100% of UI strings translated
- 0 hardcoded strings in code
- < 500ms language switch time
- 100% test coverage for i18n utilities

### Qualitative:

- User can complete all workflows in either language
- Reports are readable and professional in both languages
- No translation errors or missing keys
- Consistent terminology across application

---

## 9. Acceptance Testing Scenarios

### Scenario 1: First-Time User

1. New user logs in for first time
2. User sees UI in tenant's default language (Dutch)
3. User navigates to profile settings
4. User changes language to English
5. UI updates immediately to English
6. User logs out and logs back in
7. UI remains in English

### Scenario 2: Report Generation

1. User selects Dutch language
2. User generates P&L report
3. Report headers and labels in Dutch
4. Numbers formatted as 1.234,56
5. Dates formatted as DD-MM-YYYY
6. User switches to English
7. User generates same report
8. Report headers and labels in English
9. Numbers formatted as 1,234.56
10. Dates formatted as MM/DD/YYYY

### Scenario 3: Chart of Accounts

1. User opens Chart of Accounts page
2. Account names displayed in user's language
3. User searches for account in Dutch
4. Results show matching accounts
5. User switches language to English
6. Same accounts now show English names
7. Search still works with English terms

### Scenario 4: Email Notifications

1. User A has Dutch language preference
2. User B has English language preference
3. System sends notification to both users
4. User A receives email in Dutch
5. User B receives email in English
6. Both emails contain same information

### Scenario 5: Tenant Admin

1. Tenant Admin sets tenant default to Dutch
2. New user is created
3. New user logs in
4. UI displays in Dutch by default
5. New user can change to English in settings

---

## 10. Risk Assessment

### High Risk:

- **Incomplete translations** - Missing keys show untranslated text
  - Mitigation: Automated validation script to check completeness
- **Breaking existing functionality** - i18n changes affect working code
  - Mitigation: Comprehensive testing before deployment

### Medium Risk:

- **Performance impact** - Loading translations slows down app
  - Mitigation: Lazy loading and caching strategies
- **Date/number formatting bugs** - Incorrect formatting in reports
  - Mitigation: Unit tests for all formatting functions

### Low Risk:

- **Translation quality** - Poor translations confuse users
  - Mitigation: Native speaker review (Peter for Dutch, Kiro for English)

---

## 11. Related Specifications

- **README.md** - Overview and architecture
- **design.md** - Technical design (to be created)
- **TASKS.md** - Implementation checklist (to be created)

---

## 12. Approval

**Specification Author**: Kiro AI  
**Reviewed By**: Peter Geers  
**Approved Date**: February 17, 2026  
**Status**: Ready for Implementation

---
