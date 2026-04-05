# Uploading Invoices

> Upload PDFs and other files for processing in myAdmin.

## Overview

You upload invoices by selecting a file and choosing a vendor folder. The system uploads the file to Google Drive, extracts the content, and prepares transactions for you to review and approve.

## What You'll Need

- An invoice file (PDF, image, email, or CSV)
- Access to the Invoices module (`invoices_create` permissions)

## Step by Step

### 1. Open the Invoices module

In myAdmin, go to **Invoices**. You'll see the upload form.

### 2. Choose a vendor folder

Type the vendor name in the search field. The system filters available folders as you type.

- Select the correct folder from the list
- The filter must show exactly 1 folder before you can upload

!!! info
Vendor doesn't exist yet? Click **Create new folder** and enter the name. The folder will be created in Google Drive.

### 3. Select the file

Click **Choose file** and select the invoice. Supported formats:

- PDF (`.pdf`) — most common
- Images (`.jpg`, `.jpeg`, `.png`)
- Email messages (`.eml`, `.mhtml`)
- Spreadsheets (`.csv`)

### 4. Upload

Click **Upload**. The system:

1. Uploads the file to Google Drive in the chosen vendor folder
2. Checks for duplicates (filename + folder)
3. Extracts text from the file
4. Lets AI extract the data
5. Prepares transaction records based on templates

You'll see a progress bar during upload.

### 5. Duplicate detection

If the file was already uploaded before, a warning appears showing:

- Details of the existing transaction (date, amount, description)
- Link to the existing file in Google Drive

You can choose:

| Action            | What it does                                 |
| ----------------- | -------------------------------------------- |
| **Upload anyway** | Process the file again (creates a duplicate) |
| **Cancel**        | Stop the upload                              |

!!! warning
Duplicate detection checks filename and vendor folder over the past 6 months. Don't rename a file to bypass the check.

### 6. Next steps

After a successful upload, you'll see:

- The extracted data (see [AI extraction](ai-extraction.md))
- Prepared transactions ready for review (see [Editing & approving](editing-approving.md))

## Tips

- Upload one invoice at a time for the best results
- Use clear folder names that match the vendor name
- PDF files give the best extraction results

## Troubleshooting

| Problem                                  | Cause                          | Solution                                                        |
| ---------------------------------------- | ------------------------------ | --------------------------------------------------------------- |
| "No file provided"                       | No file selected               | Select a file before uploading                                  |
| "Invalid file type"                      | Unsupported file format        | Use PDF, JPG, PNG, EML, MHTML, or CSV                           |
| "No tenant selected"                     | No administration selected     | Select a tenant in the navigation bar first                     |
| "Please narrow down to exactly 1 folder" | Multiple folders in the filter | Type more text to narrow the filter to 1 folder                 |
| Upload failed                            | Google Drive connection lost   | Contact your administrator to renew the Google Drive connection |
