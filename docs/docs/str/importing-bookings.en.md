# Importing Bookings

> Upload and process revenue files from Airbnb, Booking.com, VRBO, or direct bookings.

## Overview

You import bookings by uploading a file from your rental platform. The system recognizes the format, calculates taxes and fees, and separates bookings into realized and planned.

## What You'll Need

- A revenue file from your rental platform
- Access to the STR module (`str_create` permissions)

## Step by Step

### 1. Open the STR module

In myAdmin, go to **STR**. You'll see the upload form.

### 2. Select the platform

Choose the correct platform from the dropdown:

| Platform        | When to choose                                  |
| --------------- | ----------------------------------------------- |
| **Airbnb**      | For Airbnb reservation exports (CSV)            |
| **Booking.com** | For Booking.com booking overviews (Excel)       |
| **VRBO**        | For VRBO reservations + payouts (multiple CSVs) |
| **Direct**      | For Guesty direct bookings (CSV)                |
| **Payout**      | For Booking.com monthly settlement files (CSV)  |

### 3. Select the file

Click **Choose file** and select the downloaded file.

**Per platform:**

**Airbnb:**

- Download your reservation overview as CSV from Airbnb
- The file contains columns like "Begindatum", "Einddatum", "Inkomsten", "Bevestigingscode"
- Cancelled bookings with no earnings are automatically skipped

**Booking.com:**

- Download the booking overview as Excel (.xlsx) from the Extranet
- Contains check-in/check-out dates, guest names, and pricing information

**VRBO:**

- Select multiple files: Reservations CSV + Payouts CSV
- The system automatically detects which file is which based on column headers

**Direct (Guesty):**

- Only CSV files are accepted — Excel (.xls/.xlsx) files are rejected
- Export from Guesty: click the link in the Import Links popup
- Apply the filter: "Checkin is between 2 months ago and 1 year into the future for Platform Manual"
- The system only processes bookings with status "confirmed"
- Cancelled or unconfirmed bookings are skipped
- Channel fee is calculated as 4% of the gross amount (TOTAL PAYOUT)
- Re-importing updates existing bookings instead of creating duplicates (matched by reservation code)
- After saving, optional Stripe enrichment is performed (email, phone, country)

**Payout (Booking.com settlement):**

- Filename must start with `Payout_from_` and end with `.csv`
- This file updates existing bookings with final payout amounts

### 4. Process the file

Click **Process File**. The system:

1. Reads the file and recognizes the format
2. Calculates VAT, tourist tax, and channel fees per booking
3. Determines whether each booking is realized or planned (based on check-in date)
4. Checks for duplicates (reservation code + channel)
5. Shows a preview in three tabs

!!! info "Direct (Guesty) — Duplicate Handling"
For the **Direct** platform, existing bookings are automatically updated when the same reservation code is re-imported. This means you can safely import the same Guesty export multiple times — changed fields are updated, no duplicates are created.

### 5. View the preview

After processing, you'll see:

**Summary card:**

- Total number of bookings
- Total number of nights
- Total gross revenue
- Breakdown per channel

**Three tabs:**

| Tab                | Content                                              |
| ------------------ | ---------------------------------------------------- |
| **Realized**       | Completed bookings (check-in in the past)            |
| **Planned**        | Future bookings (check-in in the future)             |
| **Already loaded** | Duplicates already in the database (will be skipped) |

Each booking shows: channel, guest, listing, dates, nights, guests, gross/fee/net amounts, status, and reservation code.

### 6. Save

Click **Approve and Save** to save the bookings:

- Realized bookings → `bnb` table (permanent archive)
- Planned bookings → `bnbplanned` table (updated with each import)
- Duplicates are automatically skipped

## Tips

!!! tip
Import Airbnb and Booking.com files separately — each platform has its own file format.

- For VRBO, you can select multiple files at once
- Payout imports update existing bookings with final amounts
- The system automatically detects the guest's country of origin
- Cancelled bookings with €0 earnings are skipped
- **Direct (Guesty):** You can safely re-import the same file — duplicates are updated, not created
- **Direct (Guesty):** After saving, the system automatically retrieves contact details from Stripe (if configured)

## Troubleshooting

| Problem                                                | Cause                               | Solution                                                       |
| ------------------------------------------------------ | ----------------------------------- | -------------------------------------------------------------- |
| "No file provided"                                     | No file selected                    | Select a file first                                            |
| "Unsupported platform"                                 | Wrong platform selected             | Check that you chose the correct platform                      |
| No bookings found                                      | Empty file or wrong format          | Check that the file contains bookings                          |
| All bookings as "Already loaded"                       | File was already imported           | This is normal — only new bookings are added                   |
| Payout file rejected                                   | Wrong filename                      | Filename must start with `Payout_from_`                        |
| "Only CSV files are supported for the direct platform" | Excel file selected for Direct      | Export from Guesty as CSV, not Excel                           |
| "Missing required columns: ..."                        | Wrong CSV format for Direct         | Ensure it's a Guesty export with all 13 required columns       |
| All rows skipped for Direct                            | No bookings with status "confirmed" | Check the Guesty filter: only confirmed bookings are processed |
