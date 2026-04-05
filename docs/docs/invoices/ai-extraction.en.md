# AI Extraction

> Automatically extract data from invoices using AI.

## Overview

When you upload an invoice, AI automatically extracts the key data. The system combines AI models with 250+ vendor-specific parsers to deliver the best results.

## How does it work?

### Step 1: Text extraction

The system first reads the text from the file:

- **PDF**: Text is extracted directly from the document
- **Images**: OCR (optical character recognition) is used
- **Email**: The message text and attachments are processed

### Step 2: AI analysis

The extracted text is sent to an AI model that tries to recognize the following data:

| Field        | Format     | Example                             |
| ------------ | ---------- | ----------------------------------- |
| Date         | YYYY-MM-DD | 2026-03-15                          |
| Total amount | Number     | 125.50                              |
| VAT amount   | Number     | 21.84                               |
| Description  | Text       | Invoice: 2026-0042, Customer: 12345 |
| Vendor       | Text       | Eneco                               |

!!! info
The system uses previous transactions from the same vendor as context. This means recurring invoices are recognized with increasing accuracy.

### Step 3: Vendor-specific parsers

In addition to AI, the system has 250+ built-in parsers for common vendors. These parsers know the exact format of invoices from vendors like:

- Amazon, Bol.com
- Booking.com, Airbnb
- Energy companies (Eneco, Vattenfall)
- Telecom companies (KPN, T-Mobile)
- And many others

The parser is automatically selected based on the vendor folder.

## What do you see after extraction?

After uploading, an overview appears with the extracted data:

- **Folder** — The vendor folder
- **Filename** — Name of the uploaded file
- **Date** — Extracted invoice date
- **URL** — Link to the file in Google Drive
- **Total amount** — Extracted amount (€)
- **VAT amount** — Extracted VAT (€)
- **Description** — Invoice number and other identifiers

!!! tip
Always check the extracted data. AI is good but not perfect — especially with unusual invoice layouts, results may differ.

## When does AI extraction work best?

- **Digital PDFs** (not scanned) give the best results
- **Standard invoice layouts** with clear labels
- **Vendors that have been processed before** — the system learns from previous transactions

## When does it work less well?

- **Scanned documents** with poor quality
- **Handwritten invoices**
- **Unusual layouts** without clear labels
- **Foreign invoices** with unknown currencies

In these cases, you can manually adjust the data in the next step (see [Editing & approving](editing-approving.md)).

## Troubleshooting

| Problem           | Cause                          | Solution                                                |
| ----------------- | ------------------------------ | ------------------------------------------------------- |
| No data extracted | File contains no readable text | Check that it's a digital PDF (not a poor quality scan) |
| Wrong amount      | AI picked the wrong amount     | Adjust the amount manually in the editing screen        |
| Wrong date        | Multiple dates in the document | Select the correct date manually                        |
| VAT is 0.00       | VAT not found in the document  | Fill in the VAT amount manually                         |
