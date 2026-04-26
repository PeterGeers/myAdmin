# Managing Pivot Models

> Create, edit, and delete pivot models available to users in your organization.

## Overview

As a Tenant Admin you create pivot models that your users can use in the report tabs. A model defines the structure of a pivot view: which data source, which group columns, which aggregations, and which default filters. Users can then only adjust filter values — the structure remains locked.

Manage pivot models via **Tenant Admin** → **Pivot Views**.

## Creating a model

### Step by step

1. Go to **Tenant Admin** → **Pivot Views**
2. Select a **data source** from the dropdown (e.g. Financial Transactions, STR Revenue)
3. Choose **group columns** — the columns to group by (max. 5)
4. Choose **aggregate measures** — combination of function (SUM, COUNT, AVG, MIN, MAX) and column (max. 10)
5. Optionally set **filters** as default values
6. Optionally configure a **column pivot** and **nest levels**
7. Click **Execute** to preview the results
8. Click **Save** and give the model a name

!!! warning
Model names must be unique within your tenant. Using an existing name will result in an error.

### Choosing group columns

Group columns determine how data is split. Examples:

| Grouping                     | Result                                       |
| ---------------------------- | -------------------------------------------- |
| `year`                       | One row per year                             |
| `year`, `quarter`            | One row per year-quarter combination         |
| `channel`, `listing`, `year` | One row per channel-listing-year combination |

### Choosing aggregate measures

Aggregate measures compute values per group:

| Function | Description | Example                    |
| -------- | ----------- | -------------------------- |
| SUM      | Sum values  | SUM(Amount) — total amount |
| COUNT    | Count rows  | COUNT(\*) — number of rows |
| AVG      | Average     | AVG(pricePerNight)         |
| MIN      | Minimum     | MIN(Amount)                |
| MAX      | Maximum     | MAX(amountGross)           |

### Configuring column pivot

With a column pivot, the values of a column become column headers:

1. Select a column as **Column Pivot** (e.g. `year`)
2. Optionally add **nest levels** (e.g. `quarter` under `year`)
3. The result table then shows columns per year, with sub-columns per quarter

!!! info
A column cannot be used simultaneously as a group column, column pivot, and nest level.

## Editing models

1. Select an existing model from the **Load** dropdown
2. Adjust the configuration
3. Click **Save** — the model is updated with the same name

## Deleting models

1. Select the model from the **Load** dropdown
2. Click **Delete**
3. Confirm the deletion

!!! warning
Deleted models are no longer available to users in the report tabs.

## Display modes

When creating a model you can set the default display mode:

| Mode             | When to use                                                      |
| ---------------- | ---------------------------------------------------------------- |
| **Flat**         | Simple table, suitable for 1 group column                        |
| **Hierarchical** | Tree structure with collapsible rows, ideal for 2+ group columns |

The display mode can be toggled by the end user without re-executing the query.

## Column access

Which columns are available is determined by two levels:

1. **System level** — The system administrator determines which columns per data source are available
2. **Tenant level** — As Tenant Admin you can further restrict available columns via **Settings** → **Parameters** (namespace `ui.pivot`)

!!! tip
If you're missing a column, check the `allowed_columns.<datasource>` parameter in your tenant settings. The system administrator may also have excluded columns at system level.

## Troubleshooting

| Problem                     | Cause                                 | Solution                                               |
| --------------------------- | ------------------------------------- | ------------------------------------------------------ |
| "Name already exists" error | Model name already in use             | Choose a different name or edit the existing model     |
| No data sources available   | No sources enabled by SysAdmin        | Contact the system administrator                       |
| Column not visible          | Column excluded or restricted         | Check the `allowed_columns` parameter                  |
| Model not visible in report | Data source has no module tag         | Contact the system administrator                       |
| Validation error on save    | No group column or aggregate selected | Select at least 1 group column and 1 aggregate measure |
