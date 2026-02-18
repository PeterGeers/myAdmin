# Translation Workflow

This document describes the complete workflow for managing translations in myAdmin, from initial development to production deployment.

## Table of Contents

1. [Overview](#overview)
2. [Development Workflow](#development-workflow)
3. [Translation Process](#translation-process)
4. [Review Process](#review-process)
5. [Testing Workflow](#testing-workflow)
6. [Deployment Workflow](#deployment-workflow)
7. [Maintenance Workflow](#maintenance-workflow)

---

## Overview

### Roles

- **Developer**: Adds translation keys and implements i18n
- **Translator**: Provides translations for new keys
- **Reviewer**: Reviews translations for accuracy and consistency
- **QA**: Tests translations in context
- **DevOps**: Deploys translations to production

### Tools

- **Frontend**: react-i18next, JSON files
- **Backend**: Flask-Babel, .po/.mo files
- **Scripts**: Translation completeness checkers
- **Tests**: Unit, integration, and E2E tests

---

## Development Workflow

### Step 1: Identify Translation Needs

When developing a new feature:

1. **Identify all user-facing text**
   - UI labels and buttons
   - Form fields and placeholders
   - Error and success messages
   - Help text and tooltips

2. **Choose appropriate namespace**
   - `common` - Shared UI elements
   - `auth` - Authentication
   - `reports` - Financial reports
   - `str` - Short-term rental
   - `banking` - Banking features
   - `admin` - Administration
   - `errors` - Error messages
   - `validation` - Form validation

3. **Plan translation keys**
   - Use hierarchical structure
   - Group related translations
   - Use descriptive names

### Step 2: Add Translation Keys

**Frontend** - Add to Dutch file first (primary language):

```json
// frontend/src/locales/nl/common.json
{
  "myFeature": {
    "title": "Mijn Nieuwe Functie",
    "description": "Dit is een beschrijving van de functie",
    "buttons": {
      "save": "Opslaan",
      "cancel": "Annuleren",
      "delete": "Verwijderen"
    },
    "messages": {
      "success": "Succesvol opgeslagen",
      "error": "Er is een fout opgetreden"
    }
  }
}
```

**Add English translations**:

```json
// frontend/src/locales/en/common.json
{
  "myFeature": {
    "title": "My New Feature",
    "description": "This is a description of the feature",
    "buttons": {
      "save": "Save",
      "cancel": "Cancel",
      "delete": "Delete"
    },
    "messages": {
      "success": "Successfully saved",
      "error": "An error occurred"
    }
  }
}
```

### Step 3: Implement in Code

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function MyFeature() {
  const { t } = useTypedTranslation('common');

  return (
    <div>
      <h1>{t('myFeature.title')}</h1>
      <p>{t('myFeature.description')}</p>
      <Button onClick={handleSave}>
        {t('myFeature.buttons.save')}
      </Button>
      <Button onClick={handleCancel}>
        {t('myFeature.buttons.cancel')}
      </Button>
    </div>
  );
}
```

### Step 4: Verify Completeness

```bash
cd frontend
node scripts/check-translations.js
```

Expected output:

```
✓ All keys match! (182 keys)
```

### Step 5: Commit Changes

```bash
git add frontend/src/locales/nl/common.json
git add frontend/src/locales/en/common.json
git add frontend/src/components/MyFeature.tsx
git commit -m "Add translations for MyFeature

- Added Dutch translations (primary)
- Added English translations
- Implemented i18n in component
- All translation keys verified complete"
```

---

## Translation Process

### For New Features

1. **Developer creates translation keys**
   - Add Dutch translations (primary language)
   - Add placeholder English translations
   - Mark English translations for review: `"key": "TODO: Translate"`

2. **Translator reviews and translates**
   - Review Dutch translations for accuracy
   - Provide English translations
   - Ensure consistency with existing translations
   - Consider context and tone

3. **Developer updates translations**
   - Replace placeholder translations
   - Run completeness check
   - Commit updated translations

### For Existing Features

1. **Identify missing or incorrect translations**
   - User feedback
   - QA testing
   - Translation review

2. **Update translation files**
   - Fix incorrect translations
   - Add missing translations
   - Maintain consistency

3. **Verify and deploy**
   - Run completeness check
   - Test in context
   - Deploy to production

---

## Review Process

### Translation Review Checklist

#### Accuracy

- [ ] Translation conveys correct meaning
- [ ] Technical terms are correct
- [ ] Context is appropriate

#### Consistency

- [ ] Terminology matches existing translations
- [ ] Tone is consistent with application
- [ ] Formatting is consistent

#### Quality

- [ ] Grammar is correct
- [ ] Spelling is correct
- [ ] Punctuation is appropriate
- [ ] No machine translation artifacts

#### Technical

- [ ] Interpolation variables are preserved
- [ ] HTML entities are correct
- [ ] Special characters are handled
- [ ] Length is appropriate for UI

### Review Process Steps

1. **Automated Check**

   ```bash
   node scripts/check-translations.js
   ```

2. **Manual Review**
   - Review translations in context
   - Check UI layout with translations
   - Verify formatting (dates, numbers, currency)
   - Test with real data

3. **Peer Review**
   - Native speaker review
   - Context verification
   - Consistency check

4. **Approval**
   - Mark as reviewed
   - Approve for deployment
   - Document any issues

---

## Testing Workflow

### Unit Tests

Test translation keys exist:

```typescript
describe("MyFeature translations", () => {
  it("has all required translation keys", () => {
    const { t } = useTypedTranslation("common");

    expect(t("myFeature.title")).toBeDefined();
    expect(t("myFeature.buttons.save")).toBeDefined();
    expect(t("myFeature.buttons.cancel")).toBeDefined();
  });
});
```

### Integration Tests

Test language switching:

```typescript
describe('MyFeature language switching', () => {
  it('displays Dutch translations', async () => {
    await i18n.changeLanguage('nl');
    render(<MyFeature />);

    expect(screen.getByText('Opslaan')).toBeInTheDocument();
  });

  it('displays English translations', async () => {
    await i18n.changeLanguage('en');
    render(<MyFeature />);

    expect(screen.getByText('Save')).toBeInTheDocument();
  });
});
```

### E2E Tests

Test complete user flows:

```typescript
test("user can use feature in Dutch", async ({ page }) => {
  await page.goto("/");
  await page.click('[data-testid="language-selector"]');
  await page.click('[data-testid="language-option-nl"]');

  await page.goto("/my-feature");
  await expect(page.locator("h1")).toContainText("Mijn Nieuwe Functie");
});
```

### Manual Testing

1. **Switch to Dutch**
   - Verify all text is in Dutch
   - Check date/number formatting
   - Test all user flows

2. **Switch to English**
   - Verify all text is in English
   - Check date/number formatting
   - Test all user flows

3. **Test edge cases**
   - Long translations
   - Special characters
   - Interpolated values
   - Error messages

---

## Deployment Workflow

### Pre-Deployment Checklist

- [ ] All translations complete (run completeness check)
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] E2E tests passing
- [ ] Manual testing complete
- [ ] Translation review approved
- [ ] No hardcoded text remaining

### Deployment Steps

#### 1. Verify Translations

```bash
# Frontend
cd frontend
node scripts/check-translations.js

# Backend
cd backend
python scripts/check_translations.py
```

#### 2. Run Tests

```bash
# Frontend unit tests
cd frontend
npm test

# Frontend E2E tests
npm run test:e2e

# Backend tests
cd backend
pytest
```

#### 3. Build Frontend

```bash
cd frontend
npm run build
```

#### 4. Deploy to Staging

```bash
# Deploy to staging environment
git push origin feature/internationalization

# Verify on staging
# - Test language switching
# - Verify translations
# - Check formatting
```

#### 5. Deploy to Production

```bash
# Merge to main
git checkout main
git merge feature/internationalization

# Push to production
git push origin main

# Monitor deployment
# - Check error logs
# - Verify translations
# - Monitor user feedback
```

### Post-Deployment

1. **Verify Production**
   - Test language switching
   - Verify all translations display correctly
   - Check date/number formatting
   - Monitor error logs

2. **User Communication**
   - Announce new language support
   - Provide language switching instructions
   - Collect user feedback

3. **Monitor**
   - Track language usage
   - Monitor error rates
   - Collect translation feedback

---

## Maintenance Workflow

### Regular Maintenance

#### Weekly

- [ ] Review user feedback on translations
- [ ] Check for missing translations
- [ ] Update translations based on feedback

#### Monthly

- [ ] Run completeness check
- [ ] Review translation consistency
- [ ] Update documentation

#### Quarterly

- [ ] Full translation review
- [ ] Update translation guidelines
- [ ] Review and update formatting utilities

### Adding New Translations

1. **Identify need**
   - New feature
   - User feedback
   - Missing translation

2. **Add translations**
   - Update Dutch file
   - Update English file
   - Run completeness check

3. **Test**
   - Unit tests
   - Integration tests
   - Manual testing

4. **Deploy**
   - Commit changes
   - Deploy to staging
   - Deploy to production

### Updating Existing Translations

1. **Identify issue**
   - User feedback
   - Translation review
   - QA testing

2. **Update translations**
   - Fix incorrect translations
   - Improve clarity
   - Maintain consistency

3. **Verify**
   - Run completeness check
   - Test in context
   - Review changes

4. **Deploy**
   - Commit changes
   - Deploy to production
   - Monitor feedback

### Handling Translation Errors

#### Missing Translation

**Symptom**: Translation key shows instead of text

**Fix**:

1. Add missing key to both language files
2. Run completeness check
3. Test in context
4. Deploy

#### Incorrect Translation

**Symptom**: Wrong meaning or context

**Fix**:

1. Update translation in language file
2. Verify with native speaker
3. Test in context
4. Deploy

#### Formatting Issue

**Symptom**: Wrong date/number format

**Fix**:

1. Check locale configuration
2. Update formatting utility if needed
3. Test with both languages
4. Deploy

---

## Best Practices

### Development

✅ **DO**:

- Add translations before implementing UI
- Use descriptive translation keys
- Group related translations
- Run completeness check before committing
- Test with both languages

❌ **DON'T**:

- Hardcode text in components
- Use generic translation keys
- Skip completeness checks
- Deploy without testing both languages

### Translation

✅ **DO**:

- Maintain consistent terminology
- Consider context and tone
- Use native speakers for review
- Test translations in UI
- Document translation decisions

❌ **DON'T**:

- Use machine translation without review
- Translate technical terms
- Ignore context
- Skip review process

### Testing

✅ **DO**:

- Test with both languages
- Test date/number formatting
- Test with real data
- Test edge cases
- Automate translation checks

❌ **DON'T**:

- Test only in one language
- Skip E2E tests
- Ignore formatting issues
- Deploy without testing

---

## Troubleshooting

### Common Issues

#### Translation Not Showing

**Problem**: Key shows instead of translation

**Solution**:

1. Check key exists in both files
2. Verify namespace is loaded
3. Run completeness check
4. Clear browser cache

#### Wrong Language

**Problem**: UI shows wrong language

**Solution**:

1. Check localStorage
2. Verify language selector
3. Check tenant default_language
4. Clear cache and reload

#### Formatting Issues

**Problem**: Wrong date/number format

**Solution**:

1. Verify i18n.language
2. Check locale mapping
3. Test formatting utilities
4. Update locale configuration

---

## Resources

- [Developer Guide](./DEVELOPER_GUIDE.md)
- [Formatting Guide](./FORMATTING_GUIDE.md)
- [Requirements](./requirements.md)
- [Tasks](./TASKS.md)

---

## Support

For questions or issues:

1. Check this documentation
2. Run completeness checks
3. Review test files
4. Consult with team lead
5. Create issue in project tracker
