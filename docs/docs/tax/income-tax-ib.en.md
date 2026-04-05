# Income Tax (IB)

> Prepare and export annual income tax declarations.

## Overview

The Aangifte IB report provides a complete overview of your financial position per year. It shows all general ledger accounts grouped in a hierarchical structure: balance sheet accounts (assets and liabilities) and profit & loss accounts (income and expenses).

## What You'll Need

- All transactions for the relevant year imported
- Access to financial reports (`Finance_Read` permissions)
- A selected tenant/administration

## Report structure

The report is built from three levels:

| Level                  | Description                  | Example                     |
| ---------------------- | ---------------------------- | --------------------------- |
| Main category (Parent) | Group of accounts            | 1000, 2000, 4000            |
| Declaration category   | Subcategory within the group | "Liquid assets", "VAT"      |
| Account                | Individual ledger account    | Bank account, Rental income |

### Balance sheet accounts (1000–3000)

| Category | Content                             |
| -------- | ----------------------------------- |
| 1000     | Liquid assets (bank accounts, cash) |
| 2000     | Liabilities (VAT, creditors, loans) |
| 3000     | Equity                              |

### Profit & loss accounts (4000+)

| Category  | Content                                  |
| --------- | ---------------------------------------- |
| 4000      | Revenue (rental income, services)        |
| 5000–7000 | Expenses (operating costs, depreciation) |
| 8000–9000 | Other income and expenses                |

The report automatically calculates:

- **Result** — Total of all P&L accounts (4000+)
- **Grand total** — Should be close to zero if the bookkeeping is correct

## Step by Step

### 1. Open the report

Go to **Reports** → **Financial** → **Aangifte IB**.

### 2. Select the year

Choose the year for which you want to prepare the declaration.

### 3. View the overview

The report shows an expandable table:

- Click a **main category** to see the declaration categories
- Click a **declaration category** to see the individual accounts
- Each account shows the total amount for the year

### 4. Export the report

You have two export options:

| Export            | Format     | Use                                             |
| ----------------- | ---------- | ----------------------------------------------- |
| **Export HTML**   | HTML file  | Print, save, share with tax advisor             |
| **Generate XLSX** | Excel file | Detailed analysis, all transactions per account |

!!! info
The XLSX export contains all individual transactions per ledger account, including beginning balance and Google Drive links to invoices. This may take a while with many transactions.

## Year-end closing

The report also includes a section for year-end closing:

- Check whether the grand total is balanced
- Overview of the result (profit or loss)
- Preparation for the next fiscal year

## Tips

!!! tip
Export the XLSX file at the end of the fiscal year and keep it with your tax declaration. This is your complete financial dossier.

- Check that the grand total is close to €0 — large deviations indicate missing or incorrect postings
- The result (profit/loss) is the basis for your income tax
- Use the HTML export for a quick overview, the XLSX export for details

## Troubleshooting

| Problem                 | Cause                                    | Solution                                       |
| ----------------------- | ---------------------------------------- | ---------------------------------------------- |
| Report is empty         | No transactions for the selected year    | Import transactions or select a different year |
| Grand total is not zero | Bookkeeping is not balanced              | Check for missing or duplicate transactions    |
| XLSX export takes long  | Many transactions and Google Drive links | Wait for the progress bar to complete          |
| Account is missing      | No transactions on that account          | Normal if there were no postings               |
