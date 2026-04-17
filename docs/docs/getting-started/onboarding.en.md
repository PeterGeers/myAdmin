# Setting Up Modules

> Step-by-step guide to get started with each module.

## Overview

myAdmin consists of multiple modules that you can activate individually. Below you'll find per module what you need and which first steps to take to get started.

!!! info
Modules are enabled by your SysAdmin. If you don't see a module, ask whether it has been activated for your tenant.

---

## Banking

Import bank statements, set up patterns for automatic account assignment, and process transactions.

**Prerequisites:**

- FIN module must be active
- CSV bank statements from your bank (Rabobank, Revolut, or credit card)

**First steps:**

1. Download a bank statement as CSV from your online banking
2. Go to **Banking** and click **Import**
3. Upload the CSV file and review the imported transactions
4. Click **Apply Patterns** to automatically assign accounts
5. Review the transactions and save

→ More: [Banking](../banking/index.md)

---

## Invoices

Upload PDF invoices, let AI extract the details, and store everything in Google Drive.

**Prerequisites:**

- FIN module must be active
- Google Drive must be configured (ask your Tenant Admin)

**First steps:**

1. Check that Google Drive is set up via **Settings**
2. Go to **Invoices** and click **Upload**
3. Select a PDF invoice
4. Wait for the AI to extract the details
5. Review the result and click **Approve**

→ More: [Invoices](../invoices/index.md)

---

## STR (Short-Term Rental)

Process revenue files from Airbnb, Booking.com, and other rental platforms.

**Prerequisites:**

- FIN module must be active
- Revenue files from your rental platform (CSV or Excel)

**First steps:**

1. Download a revenue file from Airbnb or Booking.com
2. Go to **STR** and click **Import**
3. Select the platform and upload the file
4. View the realized and planned bookings
5. Check the calculated amounts and save

→ More: [STR](../str/index.md)

---

## STR Pricing

View AI-powered pricing recommendations for your rental properties.

**Prerequisites:**

- STR module must be active
- At least one season of booking data imported

**First steps:**

1. Make sure you have imported enough booking data via the STR module
2. Go to **STR Pricing**
3. View the pricing recommendations per property and period
4. Compare the recommended prices with your current rates
5. Apply suggestions where desired

→ More: [STR Pricing](../str-pricing/index.md)

---

## ZZP Invoicing

Create and send invoices to your clients, track hours per project, and manage your debtors and creditors.

**Prerequisites:**

- FIN module must be active
- ZZP module must be enabled by your SysAdmin

**First steps:**

1. **Check that the FIN module is active** — the ZZP module requires FIN
2. **Create your first contact** — go to **ZZP** → **Contacts** and create a contact with a unique Client ID and company name
3. **Create your first product or service** — go to **ZZP** → **Products** and create a product with price and VAT code
4. **Create your first invoice** — go to **ZZP** → **Invoices**, select the contact, add line items, and save as draft
5. **Send the invoice** — open the draft and click **Send** to generate the PDF, book in FIN, and send by email
6. **Set up time tracking** (optional) — if you want to track hours, go to **ZZP** → **Time Tracking** and log your first hours
7. **Configure email settings** (optional) — ask your Tenant Admin to set up the email subject and sender

!!! tip
Start with one contact and one product to learn the process. You can always add more later.

→ More: [ZZP Invoicing](../zzp/index.md)

---

## Reports

View interactive dashboards, generate profit & loss statements, and export to Excel.

**Prerequisites:**

- FIN module must be active
- Transactions must be imported and processed

**First steps:**

1. Make sure you have processed bank statements and/or invoices
2. Go to **Reports**
3. Choose a dashboard or report
4. Set the desired period
5. Export to Excel if needed

→ More: [Reports](../reports/index.md)

---

## Tax

Prepare VAT declarations, income tax (IB), and tourist tax.

**Prerequisites:**

- FIN module must be active
- Transactions must be processed for the relevant period

**First steps:**

1. Make sure all transactions for the declaration period are processed
2. Go to **Tax** and choose the type of declaration (VAT, IB, or tourist tax)
3. Select the period
4. Review the calculated amounts
5. Export the overview for your declaration

→ More: [Tax](../tax/index.md)

---

## PDF Validation

Check whether Google Drive links in your transactions still work and fix broken links.

**Prerequisites:**

- Google Drive must be configured
- Transactions with Google Drive links in your administration

**First steps:**

1. Go to **PDF Validation**
2. Click **Start Validation**
3. Wait until the check is complete
4. Review the results — green links work, red links are broken
5. Fix broken links where needed

→ More: [PDF Validation](../pdf-validation/index.md)
