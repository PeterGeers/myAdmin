# Checking & Fixing Links

> Validate Google Drive links and repair broken connections.

## Overview

The validation function scans your transactions for Google Drive links and checks whether each file is still accessible. Broken links can be updated manually, or the system repairs them automatically where possible.

## What You'll Need

- Transactions with Google Drive links (Ref3 field)
- Access to the PDF Validation module (`invoices_read` permissions)
- A selected tenant/administration

## Step by Step

### 1. Open PDF Validation

In myAdmin, go to **PDF Validation**.

### 2. Select the year

Choose the year you want to check from the dropdown. You can also choose "All Years", but this takes longer.

### 3. Start the validation

Click **Validate PDF URLs**. The system:

1. Scans all transactions with Google Drive URLs for the selected year and administration
2. Checks each URL against Google Drive
3. Shows real-time progress via a progress bar
4. Reports the running count every 10 records

During validation, you'll see:

- **Progress bar** — Percentage completed
- **Counter** — "Processed X/Y records"
- **Running count** — "X OK, Y issues"

### 4. View the results

After completion, you'll see a summary:

| Statistic     | Description                                    |
| ------------- | ---------------------------------------------- |
| Total records | Number of transactions with Google Drive links |
| Valid URLs    | Number of working links (green)                |
| Issues found  | Number of broken or unknown links (red)        |

Below that, a table appears showing only the problematic records:

| Column             | Description                                           |
| ------------------ | ----------------------------------------------------- |
| Status             | Type of problem (file not found, not in folder, etc.) |
| Transaction number | Transaction identifier                                |
| Date               | Transaction date                                      |
| Description        | Transaction description                               |
| Amount             | Transaction amount                                    |
| Reference          | Reference number (vendor name)                        |
| URL (Ref3)         | The current Google Drive link                         |
| Document (Ref4)    | Filename                                              |
| Administration     | Tenant                                                |

### 5. Fix broken links

For each problematic record, you can click **Update**. A form appears where you can edit:

| Field                | Description               |
| -------------------- | ------------------------- |
| Reference number     | The vendor name/reference |
| Document URL (Ref3)  | The new Google Drive link |
| Document name (Ref4) | The filename              |

After filling in:

1. The system automatically validates the new URL
2. If the URL is valid, all transactions with the same original URL are updated
3. You'll see a confirmation of the number of updated records

!!! info
The update applies to all transactions with the same original Ref3 URL. If a vendor has multiple transactions with the same broken link, they are all repaired at once.

## Automatic repair

The system automatically repairs some links:

- **Folder URLs** → If the document is found in the folder, the folder URL is automatically replaced with the direct file URL
- These records appear as "Updated" (blue) in the results

## Tips

!!! tip
Start with the most recent year and work backwards. Recent links are most important for your current administration.

- Validate per year to limit waiting time
- Gmail links (yellow) can only be checked manually by opening the link
- After repairing, click **Refresh Results** to re-validate
- Broken links are often caused by moving files in Google Drive

## Troubleshooting

| Problem               | Cause                                                        | Solution                                                          |
| --------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------- |
| No records found      | No transactions with Google Drive links in the selected year | Select a different year or check that invoices have been uploaded |
| Validation takes long | Many records to check                                        | Select a specific year instead of "All Years"                     |
| "No tenant selected"  | No administration selected                                   | Select a tenant in the navigation bar                             |
| Update failed         | Invalid new URL                                              | Check that the new URL is a valid Google Drive link               |
| Many "File not found" | Files deleted from Google Drive                              | Check the trash in Google Drive — deleted files can be restored   |
