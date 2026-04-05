# P&L & Balance Sheets

> View profit & loss statements and balance sheets per year, quarter, or month.

## Overview

The Actuals report shows your financial results in a hierarchical structure. You can drill down from year level to quarter and month level, and compare multiple years side by side.

## What You'll Need

- Imported transactions in the database
- Access to financial reports (`Finance_Read` permissions)

## Report structure

The report consists of two parts:

### Balance sheet (VW = N)

Shows your assets and liabilities, grouped by main category:

| Category | Examples                            |
| -------- | ----------------------------------- |
| 1000     | Liquid assets (bank accounts, cash) |
| 2000     | Liabilities (VAT, creditors)        |
| 3000     | Equity                              |

### Profit & Loss (VW = W)

Shows your income and expenses:

| Category | Examples           |
| -------- | ------------------ |
| 4000     | Revenue (income)   |
| 6000     | Operating expenses |
| 7000     | Other expenses     |
| 8000     | Other income       |

## Step by Step

### 1. Open the report

Go to **Reports** → **Financial** → **Actuals**.

### 2. Select years

Choose one or more years to compare. You can show multiple years side by side.

### 3. Choose the detail level

| Level       | What you see                     |
| ----------- | -------------------------------- |
| **Year**    | Totals per year per category     |
| **Quarter** | Q1, Q2, Q3, Q4 columns per year  |
| **Month**   | Jan through Dec columns per year |

### 4. Choose the display format

| Format        | Example   |
| ------------- | --------- |
| 2 decimals    | €1,234.56 |
| 0 decimals    | €1,235    |
| Thousands (K) | €1.2K     |
| Millions (M)  | €0.0M     |

### 5. View the hierarchy

The report shows an expandable structure:

1. **Main category** (e.g., "4000") — Click to expand
2. **Ledger account** (e.g., "4010 Rental revenue") — Amounts per period

The beginning balance is automatically calculated based on all transactions before the selected year.

### 6. Charts

The report also includes visual displays:

- **Bar chart** — Income vs expenses per category
- **Pie chart** — Distribution of costs per category

## Tips

!!! tip
Compare two consecutive years to spot trends. For example, select 2025 and 2026 to see growth.

- The beginning balance is calculated automatically — you don't need to enter it manually
- Use the quarter level for VAT declarations
- Use the month level for detailed cash flow analysis
- Click a main category to see the underlying accounts

## Troubleshooting

| Problem                    | Cause                                        | Solution                                                |
| -------------------------- | -------------------------------------------- | ------------------------------------------------------- |
| Beginning balance is wrong | Transactions from previous years are missing | Import all historical transactions                      |
| Category shows €0          | No transactions in that period               | Check that the correct date period is selected          |
| Report is empty            | No data for selected year                    | Select a year for which transactions have been imported |
