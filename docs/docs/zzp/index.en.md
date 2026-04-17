# ZZP Invoicing

> Invoice clients, track hours, and manage debtors and creditors.

## Overview

The ZZP module is designed specifically for freelancers and self-employed professionals. You create and send invoices, track hours per client and project, and keep an overview of outstanding receivables and payables. All invoices are automatically booked in your financial administration.

!!! info
The ZZP module requires the FIN module (Financial Administration) to be active for your tenant. Ask your SysAdmin to enable both modules.

## What can you do here?

| Task                                      | Description                                  |
| ----------------------------------------- | -------------------------------------------- |
| [Managing contacts](contacts.md)          | Register and manage clients and suppliers    |
| [Products & services](products.md)        | Maintain your product and service catalog    |
| [Creating invoices](creating-invoices.md) | Draft invoices with line items               |
| [Sending invoices](sending-invoices.md)   | Generate PDF, book in FIN, and send by email |
| [Credit notes](credit-notes.md)           | Correct or credit previously sent invoices   |
| [Time tracking](time-tracking.md)         | Track hours worked per client and project    |
| [Debtors & creditors](debtors.md)         | Manage outstanding receivables and payables  |

## Typical workflow

```mermaid
graph LR
    A[Create contact] --> B[Create product]
    B --> C[Create invoice]
    C --> D[Send]
    D --> E[Check payment]
```

1. **Create a contact** with client details and a unique Client ID
2. **Create a product or service** with price and VAT code
3. **Create an invoice** with line items based on your products
4. **Send the invoice** — PDF is generated, booked in FIN, and emailed
5. **Check payments** — the system automatically matches bank payments with open invoices

## Invoice numbering

Invoices are automatically numbered per tenant and year:

| Component | Example | Description                                       |
| --------- | ------- | ------------------------------------------------- |
| Prefix    | `INV`   | Configurable per tenant                           |
| Year      | `2026`  | Four-digit year of the invoice date               |
| Sequence  | `0001`  | Sequential per tenant and year (minimum 4 digits) |

Example: `INV-2026-0001`, `INV-2026-0002`, and so on.

Credit notes use a separate prefix (default `CN`): `CN-2026-0001`.

## Permissions

| Permission   | What the user can do                         |
| ------------ | -------------------------------------------- |
| `zzp_read`   | View ZZP data (invoices, contacts, products) |
| `zzp_crud`   | Create, edit, and delete ZZP data            |
| `zzp_export` | Export ZZP data                              |
| `zzp_tenant` | Manage ZZP settings for the tenant           |

!!! warning
Which permissions are available depends on the modules the SysAdmin has enabled for your tenant. If the ZZP module is not enabled, ZZP permissions are not available.
