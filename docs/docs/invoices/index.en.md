# Invoices

> Upload invoices, let AI extract the details, and manage everything via Google Drive.

## Overview

The Invoices module helps you process incoming invoices. Upload a file, let AI extract the key details, review the results, and save the transaction to your administration. All files are automatically stored in Google Drive.

## What can you do here?

| Task                                     | Description                                |
| ---------------------------------------- | ------------------------------------------ |
| [Upload invoices](uploading-invoices.md) | Upload PDFs and other files for processing |
| [AI extraction](ai-extraction.md)        | Automatically extract data using AI        |
| [Edit & approve](editing-approving.md)   | Review results, adjust, and save           |
| [Google Drive](google-drive.md)          | Manage files in Google Drive               |

## Typical workflow

```mermaid
graph LR
    A[Upload file] --> B[AI extraction]
    B --> C[Review]
    C --> D[Approve]
    D --> E[Saved]
```

1. **Upload** an invoice (PDF, image, or email)
2. **AI extracts** the details automatically (date, amount, VAT, vendor)
3. **Review** the extracted data and adjust where needed
4. **Approve** to save the transaction to the database
5. The file is automatically stored in **Google Drive**

## Supported file types

| Type           | Extensions              |
| -------------- | ----------------------- |
| PDF documents  | `.pdf`                  |
| Images         | `.jpg`, `.jpeg`, `.png` |
| Email messages | `.eml`, `.mhtml`        |
| Spreadsheets   | `.csv`                  |

## What gets extracted?

For each invoice, the system tries to recognize the following data:

| Field        | Description                                          |
| ------------ | ---------------------------------------------------- |
| Date         | Invoice date (converted to YYYY-MM-DD)               |
| Total amount | Final amount including VAT                           |
| VAT amount   | Total VAT/sales tax                                  |
| Description  | Invoice number, customer number, or other identifier |
| Vendor       | Name of the supplier                                 |

!!! tip
The system has 250+ vendor-specific parsers as backup. For common vendors like Amazon, Booking.com, and energy companies, data is extracted with extra accuracy.
