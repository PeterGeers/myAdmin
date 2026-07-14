# Import & Export

> Import historical trips and export your records for the Dutch Tax Authority.

## Overview

With the import and export function you can:

- **Import** — load historical trips from CSV or Excel (e.g., when switching from another system)
- **Export** — download your trip records as PDF, CSV or Excel

!!! info
Import is intended for one-time migration of historical data. For daily use, register trips via the regular entry screen or [Quick Entry](snelle-invoer.md).

## What you need

- Access to the ZZP module (`zzp_crud` permissions)
- At least one registered vehicle
- A CSV or Excel file with your trip data (for import)

---

## Importing

### Step 1: Download template

First download the import template so your file has the correct format:

1. Go to **ZZP** → **Trip Registration**
2. Click **Import**
3. Click **Download template**
4. Choose **CSV** or **Excel**

The template contains all columns with example data and explanations.

### Step 2: Prepare file

Fill in the template with your historical trips. Note the following requirements:

| Column         | Format                       | Required | Example                      |
| -------------- | ---------------------------- | -------- | ---------------------------- |
| Date           | DD-MM-YYYY                   | Yes      | 15-03-2025                   |
| Start address  | Free text                    | Yes      | Amsterdam, Keizersgracht 100 |
| End address    | Free text                    | Yes      | Utrecht, Jaarbeursplein 1    |
| Start odometer | Integer                      | Yes      | 45000                        |
| End odometer   | Integer                      | Yes      | 45045                        |
| Trip purpose   | Text from the dropdown       | Yes      | Client visit                 |
| Category       | Business / Private / Commute | Yes      | Business                     |
| Client         | Name or client ID            | No       | Company BV                   |
| Notes          | Free text                    | No       | Q1 results meeting           |

!!! warning "Important for CSV files" - Use **semicolon (;)** as separator (default for Dutch Excel) - Use **UTF-8** encoding - The first row must contain column headers - Dates in DD-MM-YYYY format (not American MM/DD/YYYY)

### Step 3: Import

1. Go to **ZZP** → **Trip Registration** → **Import**
2. Select the **vehicle** you are importing for
3. Click **Choose file** and select your CSV or Excel file
4. Click **Upload**

### Step 4: Map columns

If your column names differ from the template, the mapping screen appears:

1. Map each column from your file to the correct field
2. Mark columns you want to skip
3. Click **Next**

### Step 5: Check validation

The system checks all records and shows the results:

| Status     | Icon   | Meaning                                    | Action            |
| ---------- | ------ | ------------------------------------------ | ----------------- |
| ✅ OK      | Green  | Record is valid and ready for import       | No action needed  |
| ⚠️ Warning | Orange | Record is valid but has an attention point | Review and decide |
| ❌ Error   | Red    | Record is invalid and cannot be imported   | Correct or skip   |

### Step 6: Correct or skip errors

1. Click on a row with an error to edit it
2. Correct the value in the inline editing field
3. Or click **Skip** to exclude the record from import
4. Click **Re-validate** to check the changes

### Step 7: Confirm import

1. Review the summary: records OK / Warning / Error / Skipped
2. Click **Import**
3. Wait for the import to complete
4. View the result: number of imported trips and any errors

---

## Exporting

### Available formats

| Format    | Best for                                  | Contains                                             |
| --------- | ----------------------------------------- | ---------------------------------------------------- |
| **PDF**   | Tax authority, accountant, archive        | All legally required fields, totals, signature block |
| **CSV**   | Own processing in Excel or other software | Raw data, suitable for filtering and calculations    |
| **Excel** | Ready-made overview with formatting       | Formatted table, summaries per category              |

### How to export

1. Go to **ZZP** → **Trip Registration**
2. Set the desired filters (date range, vehicle, category, client)
3. Click **Export**
4. Choose the format: **PDF**, **CSV** or **Excel**
5. The file is downloaded

### PDF export for the Tax Authority

The PDF export is specifically designed to meet Dutch Tax Authority requirements:

- All trips per vehicle, sorted by date
- Per trip: date, start address, end address, start odometer, end odometer, distance, purpose, category
- Total overview per category (business / private / commute)
- Annual overview suitable for income tax return

## Troubleshooting

| Problem                    | Cause                             | Solution                                        |
| -------------------------- | --------------------------------- | ----------------------------------------------- |
| Import fails completely    | File is not readable              | Check if it is a valid CSV or xlsx file         |
| Many validation errors     | Wrong date format or separator    | Use DD-MM-YYYY and semicolon as separator       |
| Columns are not recognized | Column names differ from template | Use column mapping or download the template     |
| Export contains no data    | Filters are too strict            | Widen the date range or remove filters          |
| PDF is empty               | No trips in the selected period   | Check if there are trips for the chosen vehicle |
