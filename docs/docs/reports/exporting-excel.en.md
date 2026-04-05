# Excel Export

> Export reports to Excel and CSV for further analysis.

## Overview

myAdmin offers multiple export options so you can use data in Excel, your accounting software, or for your tax advisor.

## Available exports

| Export           | Format | Where to find                                     |
| ---------------- | ------ | ------------------------------------------------- |
| Transactions     | CSV    | Reports → Financial → Transactions → CSV export   |
| Income tax (IB)  | HTML   | Reports → Financial → Aangifte IB → Export HTML   |
| Income tax (IB)  | XLSX   | Reports → Financial → Aangifte IB → Generate XLSX |
| BNB Revenue      | CSV    | Reports → BNB → BNB Revenue → Export              |
| Financial report | XLSX   | Via the XLSX export function with template        |

## Export transactions (CSV)

The quickest way to export transaction data:

1. Go to **Reports** → **Financial** → **Transactions**
2. Set the desired filters (date, administration, P&L/Balance)
3. Click **CSV export**
4. The file downloads as `mutaties-[from]-[to].csv`

The CSV file contains: date, reference, description, amount, debit, credit, and administration.

## Export income tax (IB)

### HTML export

1. Go to **Reports** → **Financial** → **Aangifte IB**
2. Select the year
3. Click **Export HTML**
4. A formatted HTML file downloads that you can print or save

### XLSX export (Excel)

1. Go to **Reports** → **Financial** → **Aangifte IB**
2. Select the year
3. Click **Generate XLSX**
4. The system generates an Excel file with:
   - Beginning balance
   - All transactions for the year
   - Grouped by general ledger account
   - Google Drive links to invoices (if available)

!!! info
The XLSX export may take a moment as the system processes all transactions and retrieves Google Drive links. You'll see a progress bar during generation.

The Excel file is generated based on a template configured per administration.

## Financial report (XLSX)

The comprehensive financial report contains:

| Section           | Description                                                     |
| ----------------- | --------------------------------------------------------------- |
| Beginning balance | Balances of all balance sheet accounts at the start of the year |
| Transactions      | All postings for the selected year                              |
| Ledger accounts   | Grouped by account with subtotals                               |
| Documents         | Links to invoices in Google Drive                               |

## Tips

!!! tip
Export your Aangifte IB as XLSX at the end of the fiscal year. This file contains everything your tax advisor needs.

- CSV exports contain the filtered data — adjust your filters first
- XLSX exports use a template with formatting and formulas
- HTML exports are suitable for printing
- All exports respect tenant filtering — you only see data from your own administration

## Troubleshooting

| Problem                       | Cause                                   | Solution                                                     |
| ----------------------------- | --------------------------------------- | ------------------------------------------------------------ |
| Export is empty               | No data in the selected period          | Check your filters and date period                           |
| XLSX export fails             | Template not found                      | Contact your administrator                                   |
| Export takes long             | Many transactions or Google Drive links | Wait for the progress bar to complete                        |
| CSV contains wrong characters | Encoding issue                          | Open the file in Excel via "Import data" with UTF-8 encoding |
