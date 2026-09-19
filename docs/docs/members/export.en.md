# Export

> Export the displayed members to a CSV file.

## Overview

You export the members from the Members Overview to a CSV file, for example for further processing in a spreadsheet. The export contains the rows currently displayed and that fall within your region scope.

## What you need

- `Members_Export` permission

## Step by step

1. Go to **Member Administration** → **Overview**
2. Optionally set filters to show the selection you want (see [Filters & views](filters-and-views.md))
3. Click **Export**
4. A CSV file is downloaded with the displayed members

!!! info
The export follows what you see: only the rows within your region scope are exported, and active filters help determine which rows end up in the file. A user scoped to Noord therefore exports only Noord members. See [Overview](index.md) for an explanation of region scope.

!!! tip
To export a subset, first filter on region, status, or membership type, for example. Only the filtered rows end up in the CSV.

## Troubleshooting

| Problem                       | Cause                                | Solution                                              |
| ----------------------------- | ------------------------------------ | ----------------------------------------------------- |
| **Export** button is missing  | You do not have the `Members_Export` permission | Ask your Tenant Admin for the export permission |
| Export contains fewer members than expected | A filter is still active or your scope is limited | Clear filters; check your region scope with your Tenant Admin |
