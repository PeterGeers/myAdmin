# Pivot Views

> Create dynamic aggregated views of your data by selecting grouping columns, aggregation functions, and filters.

## Overview

Pivot Views let you create ad-hoc aggregated views of your financial transactions or STR bookings. You choose a data source, select columns to group by, pick aggregation functions (SUM, COUNT, AVG, MIN, MAX), and optionally apply filters. Results are displayed in a sortable table that you can export to CSV.

Pivot Views are available in two places:

- **Reports → Financial → Pivot Views** — for financial transactions
- **Reports → BNB → Pivot Views** — for STR bookings

## Using saved models

In the report tabs you work with **saved pivot models**. An administrator creates these models via [Tenant Admin → Pivot Views](../tenant-admin/pivot-views.md). As an end user you can:

1. **Select a model** — Choose a saved model from the dropdown
2. **Adjust filters** — Change filter values (e.g. year, quarter) without modifying the model structure
3. **Execute** — Click **Execute** to view the results

!!! tip
The model structure (group columns, aggregates, data source) is locked. You can only adjust filter values. This keeps reports consistent.

## Result table

### Display modes

The result table supports three display modes:

| Mode             | Description                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------------- |
| **Flat**         | Standard table view with one row per group combination                                       |
| **Hierarchical** | Tree structure with collapsible rows — first group column as top level, others as sub-levels |
| **Column pivot** | Values of a column become column headers, aggregates are spread horizontally                 |

!!! info
Hierarchical mode is only available when two or more group columns are selected. With one group column, flat mode is always shown.

### Number formatting

Switch between three number formats using the toggle above the table:

| Format     | Example    | Description                 |
| ---------- | ---------- | --------------------------- |
| Decimal    | €12,345.67 | Two decimal places          |
| Whole      | €12,346    | Rounded to whole numbers    |
| K-notation | €12.3k     | Abbreviated with k/M suffix |

### Sorting

Click any column header to sort results ascending or descending. This works in both flat and hierarchical mode.

## Exporting

The result table offers two export options:

| Export type         | What it contains                                            |
| ------------------- | ----------------------------------------------------------- |
| **Pivot result**    | The aggregated data as displayed in the table               |
| **Underlying data** | All individual rows before aggregation, with full precision |

### Step by step: Exporting

1. First execute a pivot view so there are results
2. Click the **Export** button
3. Choose **Pivot result** or **Underlying data**
4. The CSV file downloads automatically

!!! note
Export buttons are disabled when there is no data. Execute a query first.

## Available data sources

Which data sources are available depends on the module:

| Module    | Data source            | Description                |
| --------- | ---------------------- | -------------------------- |
| Financial | Financial Transactions | Financial transactions     |
| BNB       | STR Revenue            | Short-term rental bookings |

!!! info
The system administrator can enable additional data sources via the SysAdmin dashboard. Contact your administrator if you're missing a data source.

## Troubleshooting

| Problem                    | Cause                                | Solution                                |
| -------------------------- | ------------------------------------ | --------------------------------------- |
| No models visible          | No models created for this module    | Ask your Tenant Admin to create a model |
| No data after executing    | Filters too restrictive              | Adjust filter values or remove filters  |
| "Column not allowed" error | Column not available for your tenant | Contact your administrator              |
| Export button disabled     | No results loaded                    | Execute a pivot view first              |
| Table loads slowly         | Large dataset or many group columns  | Use filters to narrow the dataset       |
