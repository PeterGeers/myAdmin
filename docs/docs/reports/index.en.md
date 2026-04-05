# Reports

> Dashboards, profit & loss statements, balance sheets, and Excel exports.

## Overview

The Reports module offers two groups of reports: **Financial** (transactions, P&L, VAT, income tax) and **BNB** (short-term rental revenue and analyses). All reports are filterable by period, administration, and category.

## Report groups

### Financial reports

Available via **Reports** → **Financial**:

| Report                                                 | What it shows                                                      |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| [Transactions](dashboards.md#transactions)             | All transactions with filters on date, account, and administration |
| [Actuals (P&L)](pnl-balance-sheets.md)                 | Profit & loss and balance sheet per year/quarter/month             |
| [VAT](../tax/btw.md)                                   | VAT declaration per quarter                                        |
| [Reference analysis](dashboards.md#reference-analysis) | Transactions grouped by reference number                           |
| [Income tax (IB)](../tax/income-tax-ib.md)             | Income tax overview per year                                       |

### BNB reports

Available via **Reports** → **BNB**:

| Report                                     | What it shows                                     |
| ------------------------------------------ | ------------------------------------------------- |
| [BNB Revenue](../str/revenue-summaries.md) | Revenue per listing/channel with filters          |
| BNB Actuals                                | Year-over-year net revenue totals                 |
| Violin charts                              | Distribution of price per night and stay duration |
| Returning guests                           | Guests with multiple bookings                     |
| Future revenue                             | Planned bookings as trend line                    |
| Tourist tax                                | Calculated tourist tax per period                 |
| Country of origin                          | Guest origin by country                           |

## Access

You need specific permissions to view reports:

| Report group | Required permissions                                |
| ------------ | --------------------------------------------------- |
| Financial    | `Finance_CRUD`, `Finance_Read`, or `Finance_Export` |
| BNB          | `STR_CRUD`, `STR_Read`, or `STR_Export`             |

!!! info
If you don't have access to a report group, contact your administrator.

## Common features

All reports offer:

- **Date filters** — Select a period (from/to)
- **Tenant filtering** — Data is automatically filtered by your administration
- **Sorting** — Click column headers to sort
- **Searching** — Type in the search bar to filter
- **Exporting** — [Excel/CSV export](exporting-excel.md) for further analysis

!!! tip
Always select the correct tenant in the navigation bar before viewing reports. Reports only show data from the selected administration.
