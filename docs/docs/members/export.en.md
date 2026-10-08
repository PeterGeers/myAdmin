# Export

> Export the members to a CSV file.

## Overview

You export the members from the Members Overview to a CSV file, for example for further processing in a spreadsheet. The export contains the members that fall within your region scope.

## What you need

- `Members_Export` permission
- The export button in the Members Overview is additionally only visible to **Tenant Admin** and **SysAdmin**

!!! info
The export button in the overview is deliberately limited to Tenant Admin and SysAdmin: this is a full CSV dump of the members table. If you are an ordinary user and want a filtered or summarized export, use the reporting/pivot views, which offer richer exports.

## Step by step

1. Go to **Member Administration** → **Overview**
2. Click **Export**
3. A CSV file is downloaded (file name `leden-YYYY-MM-DD.csv`)

!!! info
The export contains **all** members within your region scope — not only the rows you have filtered or searched in the table at that moment. The scope is enforced server-side: a user scoped to Noord exports only Noord members. See [Overview](index.md) for an explanation of region scope.

!!! tip
If you want a filtered or summarized export (for example per status or membership type), use the reporting/pivot views. The Members Overview always exports the full list visible within your scope.

## What is in the file?

The CSV contains one column per visible field from your tenant's field configuration (fixed fields, extra fields, and calculated fields), with the real member number. The internal technical member id and system timestamps are not exported.

## Troubleshooting

| Problem                       | Cause                                | Solution                                              |
| ----------------------------- | ------------------------------------ | ----------------------------------------------------- |
| **Export** button is missing  | You do not have the `Members_Export` permission, or you are not a Tenant Admin / SysAdmin | Ask your Tenant Admin for the export permission or an export role |
| Export contains fewer members than expected | Your region scope is limited | Check your region scope with your Tenant Admin |
| You are missing a filterable export | The overview exports the whole list | Use the reporting/pivot views for a filtered export |
