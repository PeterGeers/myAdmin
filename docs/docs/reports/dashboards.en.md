# Dashboards

> Interactive overviews of your financial transactions and analyses.

## Overview

The dashboards give you a direct overview of your financial data. You can search, filter, and analyze transactions by reference number.

## Transactions

The Transactions report shows all your financial transactions in a searchable table.

### Available filters

| Filter         | Description                                               |
| -------------- | --------------------------------------------------------- |
| Date from/to   | Select a period (default: current year)                   |
| Administration | Automatically filtered by your tenant                     |
| P&L / Balance  | Filter by profit & loss (W) or balance sheet accounts (N) |

### Columns

| Column         | Description                        |
| -------------- | ---------------------------------- |
| Date           | Transaction date                   |
| Reference      | Reference number                   |
| Description    | Transaction description            |
| Amount         | Transaction amount                 |
| Account        | General ledger account number      |
| Account name   | Name of the general ledger account |
| Administration | Tenant/administration              |

### Features

- **Sorting** — Click a column header to sort ascending/descending
- **Searching** — Type in the search bar under each column to filter
- **CSV export** — Click the export button to download filtered data as CSV

!!! tip
Use the search bar under "Description" to quickly find specific transactions, such as a vendor name or invoice number.

## Reference analysis

The Reference analysis report groups transactions by reference number. This is useful for seeing all postings for a specific vendor or project.

### How to use

1. Go to **Reports** → **Financial** → **Reference analysis**
2. Set the date period
3. The report shows all reference numbers with their total amounts
4. Click a reference number to see the underlying transactions

## Step by Step

### View transactions

1. Go to **Reports** → **Financial** → **Transactions**
2. Set the desired date period
3. Use the filters to refine the results
4. Click column headers to sort
5. Use the search bars for specific queries

### Export data

1. Apply the desired filters
2. Click the **CSV export** button
3. The file downloads with the filtered data

## Troubleshooting

| Problem              | Cause                      | Solution                                      |
| -------------------- | -------------------------- | --------------------------------------------- |
| No data visible      | Wrong date period          | Adjust the date from/to                       |
| "No tenant selected" | No administration selected | Select a tenant in the navigation bar         |
| Table loads slowly   | Large date period          | Limit the period or use more specific filters |
| Maximum 1000 rows    | Limit reached              | Refine your filters to get fewer results      |
