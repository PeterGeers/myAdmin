# Sending Invoices

> Generate PDF, book in the financial administration, and send by email.

## Overview

When you send a draft invoice, several things happen automatically: a professional PDF is generated with your company logo, the invoice is booked in your financial administration (FIN), and the PDF is emailed to your client. The invoice status changes from "draft" to "sent".

## What You'll Need

- A draft invoice with at least one line item
- A contact with an email address (invoice or general)
- Access to the ZZP module (`zzp_crud` permissions)

## Step by Step

### 1. Send an invoice

1. Go to **ZZP** → **Invoices**
2. Open the draft invoice you want to send
3. Review the details and totals
4. Click **Send**

!!! warning
After sending, the financial data of the invoice can no longer be modified. Review everything carefully before sending.

### 2. What happens in the background

When you click **Send**, the system performs the following steps:

```mermaid
graph LR
    A[Generate PDF] --> B[Store in archive]
    B --> C[Book in FIN]
    C --> D[Send email]
    D --> E[Status: Sent]
```

| Step             | Description                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------- |
| Generate PDF     | Invoice is converted to a professional PDF with your company logo and client details        |
| Store in archive | The PDF is stored via Google Drive or S3                                                    |
| Book in FIN      | Double-entry booking: debtor account (debit) and revenue account (credit), plus VAT entries |
| Send email       | PDF is sent as attachment to the contact's invoice email address                            |
| Update status    | Invoice status changes from "draft" to "sent"                                               |

!!! info
The contact's Client ID is included in the payment reference. This allows the system to automatically match bank payments with this invoice later.

### 3. Download PDF

You can always re-download the PDF of a sent invoice:

1. Go to **ZZP** → **Invoices**
2. Open the sent invoice
3. Click **Download PDF**

If the original file is unavailable, a copy is generated marked as "COPY".

### 4. Send attachments

You can send additional documents with the invoice email:

1. Open the draft invoice
2. Click **Attachments** and select the documents
3. The selected attachments are sent together with the invoice PDF

!!! tip
Use attachments for timesheets, contracts, or delivery confirmations that your client needs with the invoice.

## The invoice PDF

The generated PDF contains:

| Section         | Description                                    |
| --------------- | ---------------------------------------------- |
| Company logo    | Your own logo (if configured)                  |
| Company details | Name, address, CoC, VAT number of your company |
| Client details  | Name, address, and references of the contact   |
| Invoice number  | Automatically assigned number                  |
| Invoice date    | Date of the invoice                            |
| Due date        | Calculated based on payment terms              |
| Line items      | All invoice lines with amounts                 |
| VAT summary     | VAT grouped per rate                           |
| Totals          | Subtotal, VAT, and grand total                 |
| Payment details | IBAN, Client ID as reference                   |

## Invoice statuses

| Status   | Description                                  |
| -------- | -------------------------------------------- |
| Draft    | Invoice is created but not yet sent          |
| Sent     | Invoice is sent and booked in FIN            |
| Paid     | Payment has been received and matched        |
| Overdue  | Due date has passed without payment          |
| Credited | Invoice has been corrected via a credit note |

## Tips

!!! tip
Set up your company logo via tenant settings before sending your first invoice. This way your invoice looks professional right away.

- Check the contact's email address before sending
- The email subject line is configurable per tenant
- If sending fails, the invoice stays in "draft" status — you can try again
- Sent invoices are retained for the legal retention period (default 7 years)

## Troubleshooting

| Problem                  | Cause                             | Solution                                                  |
| ------------------------ | --------------------------------- | --------------------------------------------------------- |
| "No email address found" | Contact has no email address      | Add an email address to the contact                       |
| Email not received       | Email in spam or wrong address    | Check the email address and the recipient's spam folder   |
| PDF without logo         | No logo configured for the tenant | Set up a company logo via tenant settings                 |
| Booking failed           | Missing general ledger accounts   | Check that the debtor and revenue accounts are configured |
