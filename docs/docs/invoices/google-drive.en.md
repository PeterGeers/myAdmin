# Google Drive

> Manage invoice files in Google Drive.

## Overview

All uploaded invoices are automatically stored in Google Drive. The system organizes files per vendor in a folder structure that is separated per administration (tenant).

## How does it work?

### Folder structure

Files are stored in the following structure:

```
Google Drive/
└── [Administration]/
    └── Facturen/
        ├── Amazon/
        │   ├── invoice-2026-001.pdf
        │   └── invoice-2026-002.pdf
        ├── Booking.com/
        │   └── commission-march-2026.pdf
        ├── Eneco/
        │   └── annual-statement-2025.pdf
        └── [Vendor]/
            └── [file].pdf
```

- Each administration has its own main folder
- Within the main folder, there's a folder per vendor
- Files are automatically placed in the correct vendor folder

### Link to transactions

When an invoice is processed, the system stores the Google Drive link in the **Ref3** field of the transaction. This allows you to open the original file directly from any transaction.

## Step by Step

### Open a file from a transaction

1. Go to **Banking** or view a transaction
2. Click the **Ref3** field (contains the Google Drive URL)
3. The file opens in a new tab in Google Drive

### Create a new vendor folder

1. Go to **Invoices**
2. Click **Create new folder**
3. Enter the vendor name
4. The folder is created in Google Drive and appears in the folder list

## Authentication

Google Drive access is configured per administration by your administrator. The system uses OAuth authentication to securely connect to Google Drive.

!!! info
If the Google Drive connection expires, a notification appears in the application. Contact your administrator to renew the connection.

## Tips

- All files are also directly accessible via Google Drive in your browser
- The folder structure is managed automatically — you don't need to create folders yourself
- Files are not deleted from Google Drive when you delete a transaction

## Troubleshooting

| Problem                                    | Cause                                             | Solution                                    |
| ------------------------------------------ | ------------------------------------------------- | ------------------------------------------- |
| "Google Drive OAuth credentials not found" | No credentials configured for this administration | Contact your administrator                  |
| Link doesn't open                          | Google Drive session expired                      | Log into Google Drive again in your browser |
| File not found                             | File was moved or deleted in Google Drive         | Check the trash in Google Drive             |
| Upload failed                              | Insufficient storage space                        | Check available space in Google Drive       |
