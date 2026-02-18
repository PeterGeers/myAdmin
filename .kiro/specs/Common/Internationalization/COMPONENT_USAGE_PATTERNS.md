# Component Usage Patterns for Internationalization

This document provides patterns and best practices for using internationalization in React components.

---

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Component Patterns](#component-patterns)
3. [Formatting Patterns](#formatting-patterns)
4. [Advanced Patterns](#advanced-patterns)
5. [Common Pitfalls](#common-pitfalls)
6. [Testing Patterns](#testing-patterns)

---

## Basic Usage

### Using the useTypedTranslation Hook

Always use `useTypedTranslation` instead of `useTranslation` for type safety:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function MyComponent() {
  const { t, i18n } = useTypedTranslation('common');

  return (
    <div>
      <h1>{t('welcome.title')}</h1>
      <p>{t('welcome.message')}</p>
    </div>
  );
}
```

### Specifying Namespace

Always specify the namespace when using translations:

```typescript
// ✅ Good - Explicit namespace
const { t } = useTypedTranslation("common");
t("buttons.save");

// ❌ Bad - No namespace (uses default)
const { t } = useTypedTranslation();
t("buttons.save");
```

### Accessing Current Language

Use `i18n.language` to get the current language:

```typescript
const { i18n } = useTypedTranslation("common");
const currentLang = i18n.language; // 'nl' or 'en'
```

---

## Component Patterns

### Pattern 1: Simple Component

Basic component with translations:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { Button } from '@chakra-ui/react';

function SaveButton() {
  const { t } = useTypedTranslation('common');

  return (
    <Button colorScheme="blue">
      {t('buttons.save')}
    </Button>
  );
}
```

### Pattern 2: Component with Multiple Namespaces

Use multiple hooks for different namespaces:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function UserForm() {
  const { t: tCommon } = useTypedTranslation('common');
  const { t: tValidation } = useTypedTranslation('validation');
  const { t: tAdmin } = useTypedTranslation('admin');

  return (
    <form>
      <label>{tAdmin('userManagement.modal.create.email')}</label>
      <input placeholder={tCommon('placeholders.email')} />
      <span>{tValidation('required.email')}</span>
      <button>{tCommon('buttons.save')}</button>
    </form>
  );
}
```

### Pattern 3: Component with Interpolation

Use interpolation for dynamic values:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function WelcomeMessage({ userName }: { userName: string }) {
  const { t } = useTypedTranslation('common');

  return (
    <h1>{t('welcome.message', { name: userName })}</h1>
  );
}

// Translation key:
// "welcome.message": "Welcome, {{name}}!"
```

### Pattern 4: Component with Formatting

Combine translations with formatting utilities:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { formatDate, formatCurrency } from '../utils/formatting';

function TransactionRow({ transaction }: { transaction: Transaction }) {
  const { t, i18n } = useTypedTranslation('banking');

  return (
    <tr>
      <td>{formatDate(transaction.date, i18n.language)}</td>
      <td>{transaction.description}</td>
      <td>{formatCurrency(transaction.amount, i18n.language)}</td>
      <td>{t(`status.${transaction.status}`)}</td>
    </tr>
  );
}
```

### Pattern 5: Component with Conditional Translations

Use dynamic keys for conditional translations:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function StatusBadge({ status }: { status: string }) {
  const { t } = useTypedTranslation('common');

  return (
    <span className={`status-${status}`}>
      {t(`status.${status}`)}
    </span>
  );
}

// Translation keys:
// "status.active": "Active"
// "status.inactive": "Inactive"
// "status.pending": "Pending"
```

### Pattern 6: Component with Error Handling

Use error handling utilities with translations:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { getErrorMessageByStatus } from '../utils/errorHandling';
import { useToast } from '@chakra-ui/react';

function DataFetcher() {
  const { t } = useTypedTranslation('errors');
  const toast = useToast();

  const fetchData = async () => {
    try {
      const response = await fetch('/api/data');
      if (!response.ok) {
        const errorMsg = getErrorMessageByStatus(response.status, t);
        toast({
          title: t('generic.error'),
          description: errorMsg,
          status: 'error'
        });
      }
    } catch (error) {
      toast({
        title: t('generic.error'),
        description: t('api.networkError'),
        status: 'error'
      });
    }
  };

  return <button onClick={fetchData}>Fetch Data</button>;
}
```

---

## Formatting Patterns

### Pattern 7: Date Formatting

Always use `formatDate` with current language:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { formatDate } from '../utils/formatting';

function DateDisplay({ date }: { date: Date }) {
  const { i18n } = useTypedTranslation('common');

  return (
    <span>{formatDate(date, i18n.language)}</span>
  );
}

// Dutch: 18-02-2026
// English: 2/18/2026
```

### Pattern 8: Number Formatting

Always use `formatNumber` with current language:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { formatNumber } from '../utils/formatting';

function NumberDisplay({ value }: { value: number }) {
  const { i18n } = useTypedTranslation('common');

  return (
    <span>{formatNumber(value, i18n.language)}</span>
  );
}

// Dutch: 1.234,56
// English: 1,234.56
```

### Pattern 9: Currency Formatting

Always use `formatCurrency` with current language:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { formatCurrency } from '../utils/formatting';

function PriceDisplay({ amount }: { amount: number }) {
  const { i18n } = useTypedTranslation('common');

  return (
    <span>{formatCurrency(amount, i18n.language)}</span>
  );
}

// Dutch: €1.234,56
// English: €1,234.56
```

### Pattern 10: Memoized Formatting

Use `useMemo` for expensive formatting operations:

```typescript
import { useMemo } from 'react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { formatDate, formatCurrency } from '../utils/formatting';

function TransactionList({ transactions }: { transactions: Transaction[] }) {
  const { i18n } = useTypedTranslation('banking');

  const formattedTransactions = useMemo(() => {
    return transactions.map(tx => ({
      ...tx,
      formattedDate: formatDate(tx.date, i18n.language),
      formattedAmount: formatCurrency(tx.amount, i18n.language)
    }));
  }, [transactions, i18n.language]);

  return (
    <table>
      {formattedTransactions.map(tx => (
        <tr key={tx.id}>
          <td>{tx.formattedDate}</td>
          <td>{tx.formattedAmount}</td>
        </tr>
      ))}
    </table>
  );
}
```

---

## Advanced Patterns

### Pattern 11: Language Switcher Component

Component for switching languages:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { Menu, MenuButton, MenuList, MenuItem, Button } from '@chakra-ui/react';

function LanguageSelector() {
  const { i18n } = useTypedTranslation('common');

  const languages = [
    { code: 'nl', name: 'Nederlands', flag: '🇳🇱' },
    { code: 'en', name: 'English', flag: '🇬🇧' }
  ];

  const currentLanguage = languages.find(lang => lang.code === i18n.language);

  const handleLanguageChange = async (languageCode: string) => {
    await i18n.changeLanguage(languageCode);

    // Save to API
    try {
      await fetch('/api/user/language', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: languageCode })
      });
    } catch (error) {
      console.error('Failed to save language preference:', error);
    }
  };

  return (
    <Menu>
      <MenuButton as={Button}>
        {currentLanguage?.flag} {currentLanguage?.name}
      </MenuButton>
      <MenuList>
        {languages.map(lang => (
          <MenuItem
            key={lang.code}
            onClick={() => handleLanguageChange(lang.code)}
          >
            {lang.flag} {lang.name}
          </MenuItem>
        ))}
      </MenuList>
    </Menu>
  );
}
```

### Pattern 12: Translated Form Validation

Use validation helpers with translated messages:

```typescript
import { useState } from 'react';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { isValidEmail } from '../utils/validationHelpers';

function EmailInput() {
  const { t } = useTypedTranslation('validation');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  const handleBlur = () => {
    if (!email) {
      setError(t('required.email'));
    } else if (!isValidEmail(email)) {
      setError(t('format.email'));
    } else {
      setError('');
    }
  };

  return (
    <div>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        onBlur={handleBlur}
      />
      {error && <span className="error">{error}</span>}
    </div>
  );
}
```

### Pattern 13: Translated Toast Notifications

Use toast notifications with translations:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useToast } from '@chakra-ui/react';

function SaveButton({ onSave }: { onSave: () => Promise<void> }) {
  const { t } = useTypedTranslation('common');
  const toast = useToast();

  const handleSave = async () => {
    try {
      await onSave();
      toast({
        title: t('messages.success'),
        description: t('messages.saveSuccess'),
        status: 'success',
        duration: 3000
      });
    } catch (error) {
      toast({
        title: t('messages.error'),
        description: t('messages.saveError'),
        status: 'error',
        duration: 5000
      });
    }
  };

  return (
    <button onClick={handleSave}>
      {t('buttons.save')}
    </button>
  );
}
```

### Pattern 14: Translated Table Headers

Use translations for table headers:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function UserTable({ users }: { users: User[] }) {
  const { t } = useTypedTranslation('admin');

  const columns = [
    { key: 'email', label: t('userManagement.table.email') },
    { key: 'name', label: t('userManagement.table.name') },
    { key: 'status', label: t('userManagement.table.status') },
    { key: 'roles', label: t('userManagement.table.roles') }
  ];

  return (
    <table>
      <thead>
        <tr>
          {columns.map(col => (
            <th key={col.key}>{col.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {users.map(user => (
          <tr key={user.id}>
            <td>{user.email}</td>
            <td>{user.name}</td>
            <td>{t(`status.${user.status}`)}</td>
            <td>{user.roles.join(', ')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### Pattern 15: Translated Chart Labels

Use translations for chart labels:

```typescript
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';
import { formatCurrency } from '../utils/formatting';

function RevenueChart({ data }: { data: any[] }) {
  const { t, i18n } = useTypedTranslation('reports');

  return (
    <div>
      <h2>{t('charts.revenue.title')}</h2>
      <BarChart data={data}>
        <XAxis dataKey="month" />
        <YAxis
          label={{ value: t('charts.revenue.yAxis'), angle: -90 }}
          tickFormatter={(value) => formatCurrency(value, i18n.language)}
        />
        <Tooltip
          formatter={(value: number) => formatCurrency(value, i18n.language)}
          labelFormatter={(label) => t(`periods.months.${label}`)}
        />
        <Bar dataKey="revenue" fill="#8884d8" />
      </BarChart>
    </div>
  );
}
```

---

## Common Pitfalls

### Pitfall 1: Hardcoded Text

❌ **Bad:**

```typescript
function MyComponent() {
  return <button>Save</button>;
}
```

✅ **Good:**

```typescript
function MyComponent() {
  const { t } = useTypedTranslation('common');
  return <button>{t('buttons.save')}</button>;
}
```

### Pitfall 2: Missing Namespace

❌ **Bad:**

```typescript
const { t } = useTypedTranslation();
t("buttons.save"); // Uses default namespace
```

✅ **Good:**

```typescript
const { t } = useTypedTranslation("common");
t("buttons.save"); // Explicit namespace
```

### Pitfall 3: Formatting Without Language

❌ **Bad:**

```typescript
function DateDisplay({ date }: { date: Date }) {
  return <span>{date.toLocaleDateString()}</span>;
}
```

✅ **Good:**

```typescript
function DateDisplay({ date }: { date: Date }) {
  const { i18n } = useTypedTranslation('common');
  return <span>{formatDate(date, i18n.language)}</span>;
}
```

### Pitfall 4: String Concatenation

❌ **Bad:**

```typescript
const { t } = useTypedTranslation("common");
const message = t("welcome") + ", " + userName + "!";
```

✅ **Good:**

```typescript
const { t } = useTypedTranslation("common");
const message = t("welcome.message", { name: userName });
// Translation: "Welcome, {{name}}!"
```

### Pitfall 5: Conditional Rendering Without Translation

❌ **Bad:**

```typescript
function StatusBadge({ status }: { status: string }) {
  return <span>{status === 'active' ? 'Active' : 'Inactive'}</span>;
}
```

✅ **Good:**

```typescript
function StatusBadge({ status }: { status: string }) {
  const { t } = useTypedTranslation('common');
  return <span>{t(`status.${status}`)}</span>;
}
```

---

## Testing Patterns

### Pattern 16: Testing Translated Components

Test components with i18n provider:

```typescript
import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../i18n';
import MyComponent from './MyComponent';

describe('MyComponent', () => {
  it('renders translated text', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MyComponent />
      </I18nextProvider>
    );

    // Use regex to match both languages
    expect(screen.getByText(/save|opslaan/i)).toBeInTheDocument();
  });
});
```

### Pattern 17: Testing Language Switching

Test language switching functionality:

```typescript
import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../i18n';
import MyComponent from './MyComponent';

describe('MyComponent language switching', () => {
  it('displays Dutch text', async () => {
    await i18n.changeLanguage('nl');

    render(
      <I18nextProvider i18n={i18n}>
        <MyComponent />
      </I18nextProvider>
    );

    expect(screen.getByText('Opslaan')).toBeInTheDocument();
  });

  it('displays English text', async () => {
    await i18n.changeLanguage('en');

    render(
      <I18nextProvider i18n={i18n}>
        <MyComponent />
      </I18nextProvider>
    );

    expect(screen.getByText('Save')).toBeInTheDocument();
  });
});
```

### Pattern 18: Testing with data-testid

Use data-testid for language-independent testing:

```typescript
// Component
function SaveButton() {
  const { t } = useTypedTranslation('common');
  return (
    <button data-testid="save-button">
      {t('buttons.save')}
    </button>
  );
}

// Test
it('renders save button', () => {
  render(
    <I18nextProvider i18n={i18n}>
      <SaveButton />
    </I18nextProvider>
  );

  expect(screen.getByTestId('save-button')).toBeInTheDocument();
});
```

---

## Summary

### Key Takeaways

1. **Always use `useTypedTranslation`** with explicit namespace
2. **Always use formatting utilities** (`formatDate`, `formatNumber`, `formatCurrency`)
3. **Never hardcode user-facing text** - use translation keys
4. **Use interpolation** for dynamic values
5. **Use `data-testid`** for language-independent testing
6. **Memoize expensive formatting** operations
7. **Handle errors** with translated messages
8. **Test in both languages** to ensure completeness

### Quick Reference

```typescript
// Import
import { useTypedTranslation } from "../hooks/useTypedTranslation";
import { formatDate, formatNumber, formatCurrency } from "../utils/formatting";

// Basic usage
const { t, i18n } = useTypedTranslation("common");

// Translation
t("buttons.save");

// Interpolation
t("welcome.message", { name: "John" });

// Formatting
formatDate(new Date(), i18n.language);
formatNumber(1234.56, i18n.language);
formatCurrency(1234.56, i18n.language);

// Current language
i18n.language; // 'nl' or 'en'

// Change language
i18n.changeLanguage("nl");
```

---

**Last Updated**: February 2026
**Version**: 1.0
