# Filters & views

> Filter and sort the members table and switch between compact and full view.

## Overview

The Members Overview can contain long lists. With column filters, sortable headers, and the view switch you quickly bring into focus the members you are looking for.

## What you need

- Access to the Member Administration module (`Members_Read` or `Members_CRUD`)

## Filtering columns

You filter the list per column. The available filters are:

| Filter          | Behavior                                                 |
| --------------- | -------------------------------------------------------- |
| Region          | Shows only members of the selected region/subgroup       |
| Status          | Shows only members with the selected membership status   |
| Membership type | Shows only members with the selected type                |

### Step by step

1. Go to **Member Administration** → **Overview**
2. Click the filter icon in the header of the column you want to filter
3. Choose one or more values
4. The table immediately shows only the rows that match the filter

Filters can be combined: a filter on region *Noord* and status *Active* shows only active members in Noord.

!!! tip
Clear a filter by opening the filter icon again and removing the selection. This restores the full list (as far as your scope allows).

!!! info
Filtering happens within what you are already allowed to see. A user scoped to Noord only sees Noord in the region filter — you cannot use a filter to reveal members outside your scope. See [Overview](index.md) for an explanation of region scope.

## Sorting

You can click any sortable column header to order the list by that column:

1. Click the column header (e.g. **Name**) to sort ascending
2. Click again to sort descending

This lets you sort by name, status, or membership type, for example.

## Compact and full view

Use the view switch above the table to toggle between:

- **Compact** — only the core columns (Name, Email, Status, Membership type, Region).
- **Full** — the core columns plus the extra columns from your tenant's field configuration.

### Step by step

1. Go to **Member Administration** → **Overview**
2. Use the **Compact / Full** switch above the table
3. In the full view the extra fields appear as additional columns

!!! info
The extra columns in the full view come from the field configuration your Tenant Admin sets up. If a column you expect is missing, ask your Tenant Admin to adjust the field configuration.

## Troubleshooting

| Problem                       | Cause                                     | Solution                                                    |
| ----------------------------- | ----------------------------------------- | ----------------------------------------------------------- |
| Filter does not show all regions | Your scope covers only one region      | This is correct — you only see regions within your scope    |
| Expected column is missing    | Column is not in the field configuration  | Ask your Tenant Admin to adjust the field configuration     |
| List appears empty            | A filter is still active                  | Clear the active filters to show the full list again        |
