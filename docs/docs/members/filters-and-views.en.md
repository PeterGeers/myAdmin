# Filters & views

> Search, filter, and sort the members table, and choose your own columns.

## Overview

The Members Overview can contain long lists. With the search box, column filters, sortable headers, and the column chooser you quickly bring into focus the members you are looking for — and decide for yourself which details you see.

## What you need

- Access to the Member Administration module (`Members_Read` or `Members_CRUD`)

## Search across all fields

Above the table is a single search box. Type a name, email address, member number, or any other value and the list is immediately narrowed to the matching rows.

The search box looks at **all** fields of a member — including fields that are not shown as a column in the table. So you can find a member by a detail you have not chosen as a column.

!!! tip
Clear the search box with the cross to restore the full list (as far as your scope allows).

## Filtering columns

Besides the search box, you also filter per column. Each shown column has its own filter in the column header. Common filters are:

| Filter          | Behavior                                                 |
| --------------- | -------------------------------------------------------- |
| Region          | Shows only members of the selected region/subgroup       |
| Status          | Shows only members with the selected membership status   |
| Membership type | Shows only members with the selected type                |

### Step by step

1. Go to **Member Administration** → **Overview**
2. Type in the filter field in the header of the column you want to filter
3. The table immediately shows only the rows that match the filter

Filters and search are combined: a filter on region *Noord* and status *Active* shows only active members in Noord.

!!! info
Filtering happens within what you are already allowed to see. A user scoped to Noord only sees Noord in the region filter — you cannot use a filter to reveal members outside your scope. See [Overview](index.md) for an explanation of region scope.

## Sorting

You can click any sortable column header to order the list by that column:

1. Click the column header (e.g. **Name**) to sort ascending
2. Click again to sort descending

Sorting respects the type of data: numbers and dates are ordered by value, not alphabetically.

## Choosing your own columns

Instead of a fixed "compact / full" switch, you now decide for yourself which columns the table shows, using the **Columns** button in the toolbar.

### Step by step

1. Go to **Member Administration** → **Overview**
2. Click **Columns**
3. Tick the fields you want to show as a column and untick what you want to hide
4. Close the chooser — the table immediately appears with your columns

Your choice is **remembered per user**: the next time you open the overview, your columns are set up the way you left them.

!!! info
The **Member number** column is always first and cannot be hidden. All other columns come from your tenant's field configuration (fixed fields ⊕ extra fields ⊕ calculated fields). If a field you expect is missing, ask your Tenant Admin to adjust the field configuration.

## Views (preset column sets)

If your tenant has configured **views**, a dropdown appears on the left of the toolbar. A view is a ready-made combination of columns and a default sort for a particular purpose (for example "Contact details" or "Financial").

- Pick a view from the list to switch to that column set in one click.
- The dropdown only appears when at least two views are available to you.
- Which views you see may depend on your role — your Tenant Admin decides this.

!!! info
A view only determines which *columns* you see, never which *rows*. Your region scope and your search/filters always determine which members come into view.

## The statistics strip

Above the table, four counters show live how many members you have in view: **Total** (all members within your scope), **Filtered** (the rows currently shown), **Active** (members with status Active), and **Regions** (number of distinct regions). The counters move automatically with your search, filters, and chosen view.

## Troubleshooting

| Problem                       | Cause                                     | Solution                                                    |
| ----------------------------- | ----------------------------------------- | ----------------------------------------------------------- |
| Filter does not show all regions | Your scope covers only one region      | This is correct — you only see regions within your scope    |
| Expected column is missing    | Column is not ticked or not in the field configuration | Turn the column on via **Columns**; if the field is missing, ask your Tenant Admin to adjust the field configuration |
| List appears empty            | A search or filter is still active        | Clear the search box and active filters to show the full list again |
| No **View** dropdown          | Your tenant has only one view (for you)   | This is normal; the dropdown appears only with two or more views |
