# Formatting Utilities Guide

This guide documents all formatting utilities available in myAdmin for internationalized date, number, and currency formatting.

## Table of Contents

1. [Overview](#overview)
2. [Date Formatting](#date-formatting)
3. [Number Formatting](#number-formatting)
4. [Currency Formatting](#currency-formatting)
5. [Custom Formatting](#custom-formatting)
6. [Locale Configuration](#locale-configuration)
7. [Examples](#examples)

---

## Overview

All formatting utilities are located in `frontend/src/utils/formatting.ts` and automatically adapt to the current language setting.

### Import

```typescript
import { formatDate, formatNumber, formatCurrency } from "../utils/formatting";
```

### Language Detection

Utilities automatically use the current i18n language:

```typescript
import { useTranslation } from "react-i18next";

function MyComponent() {
  const { i18n } = useTranslation();

  // Automatically uses current language
  const formatted = formatDate(new Date(), i18n.language);
}
```

---

## Date Formatting

### Basic Usage

```typescript
formatDate(date: Date, language?: string): string
```

**Parameters**:

- `date`: Date object to format
- `language`: Optional language code ('nl' or 'en'), defaults to 'nl'

**Returns**: Formatted date string

### Examples

```typescript
const date = new Date("2026-02-18");

// Dutch format (default)
formatDate(date, "nl"); // "18-02-2026"

// English format
formatDate(date, "en"); // "2/18/2026"

// Auto-detect from i18n
formatDate(date, i18n.language);
```

### Locale Mapping

```typescript
const locales: Record<string, string> = {
  nl: "nl-NL", // Netherlands
  en: "en-US", // United States
};
```

### Custom Date Formatting

For more control, use `toLocaleDateString` directly:

```typescript
const date = new Date("2026-02-18");

// Long format
date.toLocaleDateString("nl-NL", {
  year: "numeric",
  month: "long",
  day: "numeric",
});
// "18 februari 2026"

// Short format
date.toLocaleDateString("nl-NL", {
  year: "2-digit",
  month: "2-digit",
  day: "2-digit",
});
// "18-02-26"

// With weekday
date.toLocaleDateString("nl-NL", {
  weekday: "long",
  year: "numeric",
  month: "long",
  day: "numeric",
});
// "woensdag 18 februari 2026"
```

### Date-Time Formatting

```typescript
const datetime = new Date("2026-02-18T14:30:00");

// Date and time
datetime.toLocaleString("nl-NL", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});
// "18-02-2026 14:30"

// Time only
datetime.toLocaleTimeString("nl-NL", {
  hour: "2-digit",
  minute: "2-digit",
});
// "14:30"
```

---

## Number Formatting

### Basic Usage

```typescript
formatNumber(value: number, language?: string): string
```

**Parameters**:

- `value`: Number to format
- `language`: Optional language code ('nl' or 'en'), defaults to 'nl'

**Returns**: Formatted number string

### Examples

```typescript
const number = 1234.56;

// Dutch format (default)
formatNumber(number, "nl"); // "1.234,56"

// English format
formatNumber(number, "en"); // "1,234.56"

// Auto-detect from i18n
formatNumber(number, i18n.language);
```

### Decimal Places

```typescript
// Two decimal places (default)
formatNumber(1234.5, "nl"); // "1.234,50"

// Custom decimal places
(1234.5).toLocaleString("nl-NL", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
// "1.235"

// Three decimal places
(1234.567).toLocaleString("nl-NL", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});
// "1.234,567"
```

### Percentage Formatting

```typescript
const percentage = 0.1234;

// Dutch
percentage.toLocaleString("nl-NL", {
  style: "percent",
  minimumFractionDigits: 2,
});
// "12,34%"

// English
percentage.toLocaleString("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
});
// "12.34%"
```

---

## Currency Formatting

### Basic Usage

```typescript
formatCurrency(value: number, language?: string, currency?: string): string
```

**Parameters**:

- `value`: Amount to format
- `language`: Optional language code ('nl' or 'en'), defaults to 'nl'
- `currency`: Optional currency code, defaults to 'EUR'

**Returns**: Formatted currency string

### Examples

```typescript
const amount = 1234.56;

// Dutch format (default)
formatCurrency(amount, "nl"); // "€1.234,56"

// English format
formatCurrency(amount, "en"); // "€1,234.56"

// Auto-detect from i18n
formatCurrency(amount, i18n.language);
```

### Different Currencies

```typescript
const amount = 1234.56;

// Euro (default)
formatCurrency(amount, "nl", "EUR"); // "€1.234,56"

// US Dollar
formatCurrency(amount, "en", "USD"); // "$1,234.56"

// British Pound
formatCurrency(amount, "en", "GBP"); // "£1,234.56"
```

### Currency Display Options

```typescript
const amount = 1234.56;

// Symbol (default)
amount.toLocaleString("nl-NL", {
  style: "currency",
  currency: "EUR",
  currencyDisplay: "symbol",
});
// "€1.234,56"

// Code
amount.toLocaleString("nl-NL", {
  style: "currency",
  currency: "EUR",
  currencyDisplay: "code",
});
// "EUR 1.234,56"

// Name
amount.toLocaleString("nl-NL", {
  style: "currency",
  currency: "EUR",
  currencyDisplay: "name",
});
// "1.234,56 euro"
```

---

## Custom Formatting

### Compact Notation

```typescript
const largeNumber = 1234567;

// Dutch compact
largeNumber.toLocaleString("nl-NL", {
  notation: "compact",
  compactDisplay: "short",
});
// "1,2 mln."

// English compact
largeNumber.toLocaleString("en-US", {
  notation: "compact",
  compactDisplay: "short",
});
// "1.2M"
```

### Scientific Notation

```typescript
const scientificNumber = 1234567;

scientificNumber.toLocaleString("nl-NL", {
  notation: "scientific",
});
// "1,235E6"
```

### Unit Formatting

```typescript
const distance = 1234.5;

// Kilometers
distance.toLocaleString("nl-NL", {
  style: "unit",
  unit: "kilometer",
});
// "1.234,5 km"

// Miles
distance.toLocaleString("en-US", {
  style: "unit",
  unit: "mile",
});
// "1,234.5 mi"
```

### Relative Time Formatting

```typescript
const rtf = new Intl.RelativeTimeFormat("nl-NL", { numeric: "auto" });

rtf.format(-1, "day"); // "gisteren"
rtf.format(0, "day"); // "vandaag"
rtf.format(1, "day"); // "morgen"
rtf.format(-7, "day"); // "7 dagen geleden"
rtf.format(2, "week"); // "over 2 weken"
```

---

## Locale Configuration

### Supported Locales

```typescript
const locales = {
  nl: "nl-NL", // Dutch (Netherlands)
  en: "en-US", // English (United States)
};
```

### Adding New Locale

To add a new locale (e.g., French):

1. **Update locale mapping**:

```typescript
const locales: Record<string, string> = {
  nl: "nl-NL",
  en: "en-US",
  fr: "fr-FR", // Add new locale
};
```

2. **Update formatting functions**:

```typescript
export function formatDate(date: Date, language: string = "nl"): string {
  const locales: Record<string, string> = {
    nl: "nl-NL",
    en: "en-US",
    fr: "fr-FR",
  };

  return date.toLocaleDateString(locales[language] || "nl-NL");
}
```

3. **Test formatting**:

```typescript
formatDate(new Date(), "fr"); // "18/02/2026"
formatNumber(1234.56, "fr"); // "1 234,56"
formatCurrency(1234.56, "fr"); // "1 234,56 €"
```

---

## Examples

### Complete Component Example

```typescript
import React from 'react';
import { useTranslation } from 'react-i18next';
import { formatDate, formatNumber, formatCurrency } from '../utils/formatting';

interface Transaction {
  date: Date;
  description: string;
  amount: number;
  quantity: number;
}

function TransactionList({ transactions }: { transactions: Transaction[] }) {
  const { i18n } = useTranslation();

  return (
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Description</th>
          <th>Quantity</th>
          <th>Amount</th>
        </tr>
      </thead>
      <tbody>
        {transactions.map((tx, index) => (
          <tr key={index}>
            <td>{formatDate(tx.date, i18n.language)}</td>
            <td>{tx.description}</td>
            <td>{formatNumber(tx.quantity, i18n.language)}</td>
            <td>{formatCurrency(tx.amount, i18n.language)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### Report Formatting Example

```typescript
import { formatCurrency, formatDate } from '../utils/formatting';
import { useTranslation } from 'react-i18next';

function FinancialReport() {
  const { i18n } = useTranslation();

  const report = {
    period: {
      start: new Date('2026-01-01'),
      end: new Date('2026-12-31')
    },
    revenue: 125000.50,
    expenses: 87500.25,
    profit: 37500.25
  };

  return (
    <div>
      <h2>Financial Report</h2>
      <p>
        Period: {formatDate(report.period.start, i18n.language)} -
        {formatDate(report.period.end, i18n.language)}
      </p>
      <table>
        <tr>
          <td>Revenue:</td>
          <td>{formatCurrency(report.revenue, i18n.language)}</td>
        </tr>
        <tr>
          <td>Expenses:</td>
          <td>{formatCurrency(report.expenses, i18n.language)}</td>
        </tr>
        <tr>
          <td>Profit:</td>
          <td>{formatCurrency(report.profit, i18n.language)}</td>
        </tr>
      </table>
    </div>
  );
}
```

### Chart Formatting Example

```typescript
import { formatCurrency } from '../utils/formatting';
import { useTranslation } from 'react-i18next';
import { BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

function RevenueChart({ data }: { data: any[] }) {
  const { i18n } = useTranslation();

  return (
    <BarChart data={data}>
      <XAxis dataKey="month" />
      <YAxis
        tickFormatter={(value) => formatCurrency(value, i18n.language)}
      />
      <Tooltip
        formatter={(value: number) => formatCurrency(value, i18n.language)}
      />
      <Bar dataKey="revenue" fill="#8884d8" />
    </BarChart>
  );
}
```

---

## Best Practices

### ✅ DO

- Always pass `i18n.language` to formatting functions
- Use formatting utilities for all user-facing numbers/dates
- Test formatting with both languages
- Cache formatted values when possible

### ❌ DON'T

- Don't hardcode date/number formats
- Don't use string concatenation for formatting
- Don't format in render loops without memoization
- Don't assume locale from browser settings

### Performance Tips

```typescript
// ✅ Good: Memoize formatted values
const formattedDate = useMemo(
  () => formatDate(date, i18n.language),
  [date, i18n.language]
);

// ❌ Bad: Format in render
return <div>{formatDate(date, i18n.language)}</div>;

// ✅ Better: Format once, reuse
const formatted = formatDate(date, i18n.language);
return <div>{formatted}</div>;
```

---

## Testing

### Unit Tests

```typescript
import { formatDate, formatNumber, formatCurrency } from "./formatting";

describe("Formatting Utilities", () => {
  describe("formatDate", () => {
    it("formats date in Dutch", () => {
      const date = new Date("2026-02-18");
      expect(formatDate(date, "nl")).toBe("18-02-2026");
    });

    it("formats date in English", () => {
      const date = new Date("2026-02-18");
      expect(formatDate(date, "en")).toBe("2/18/2026");
    });
  });

  describe("formatNumber", () => {
    it("formats number in Dutch", () => {
      expect(formatNumber(1234.56, "nl")).toBe("1.234,56");
    });

    it("formats number in English", () => {
      expect(formatNumber(1234.56, "en")).toBe("1,234.56");
    });
  });

  describe("formatCurrency", () => {
    it("formats currency in Dutch", () => {
      expect(formatCurrency(1234.56, "nl")).toContain("€");
      expect(formatCurrency(1234.56, "nl")).toContain("1.234,56");
    });

    it("formats currency in English", () => {
      expect(formatCurrency(1234.56, "en")).toContain("€");
      expect(formatCurrency(1234.56, "en")).toContain("1,234.56");
    });
  });
});
```

---

## Reference

### Browser Support

All formatting utilities use `Intl` API which is supported in:

- Chrome 24+
- Firefox 29+
- Safari 10+
- Edge 12+

### External Resources

- [MDN: Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat)
- [MDN: Intl.NumberFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat)
- [MDN: toLocaleString](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number/toLocaleString)
