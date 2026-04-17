# Creating Invoices

> Draft invoices with line items, calculations, and payment terms.

## Overview

You create invoices as drafts. You select a contact, add line items from your product catalog or manually, and the system automatically calculates VAT and totals. Only when you're satisfied do you send the invoice.

## What You'll Need

- Access to the ZZP module (`zzp_crud` permissions)
- At least one contact in your contact registry
- At least one product in your product catalog (or you enter line items manually)

## Step by Step

### 1. Create a new invoice

1. Go to **ZZP** → **Invoices**
2. Click **New invoice**
3. Select the **contact** you're invoicing
4. Check the invoice date and payment terms

| Field           | Default                  | Description                              |
| --------------- | ------------------------ | ---------------------------------------- |
| Contact         | —                        | The client you're invoicing              |
| Invoice date    | Today                    | Date on the invoice                      |
| Payment terms   | 30 days (configurable)   | Number of days until the due date        |
| Due date        | Automatically calculated | Invoice date + payment terms             |
| Currency        | EUR (configurable)       | Currency of the invoice                  |
| Revenue account | Default revenue account  | General ledger account for the revenue   |
| Notes           | —                        | Free text field for notes on the invoice |

### 2. Add line items

Click **Add line** to add a line item. You have two options:

**From product catalog:**

1. Select a product from the dropdown
2. The name, price, and VAT code are filled in automatically
3. Enter the quantity
4. Optionally adjust the description or price

**Manually:**

1. Enter the description
2. Enter the quantity and unit price
3. Select the VAT code

Each line item contains:

| Field       | Description                                     |
| ----------- | ----------------------------------------------- |
| Product     | Optional — select from your catalog             |
| Description | Description of the delivered service or product |
| Quantity    | Number of units                                 |
| Unit price  | Price per unit (excl. VAT)                      |
| VAT code    | High, low, or zero                              |
| VAT amount  | Automatically calculated                        |
| Line total  | Quantity × unit price (excl. VAT)               |

### 3. Review totals

The system automatically calculates:

| Calculation | Formula                            |
| ----------- | ---------------------------------- |
| Subtotal    | Sum of all line totals (excl. VAT) |
| VAT summary | VAT amounts grouped per VAT code   |
| Total VAT   | Sum of all VAT amounts             |
| Grand total | Subtotal + total VAT               |

!!! info
VAT amounts are calculated based on the rate applicable on the invoice date. The system automatically retrieves the correct rate from your administration.

### 4. Save the invoice

Click **Save** to save the invoice as a draft. You can edit the draft later before sending it.

## Copy last invoice

For recurring clients, you can quickly create a new invoice based on the previous one:

1. Go to **ZZP** → **Invoices**
2. Click **Copy last invoice** for the desired contact
3. The line items from the previous invoice are carried over
4. Adjust the date, quantities, and any changes
5. Click **Save**

!!! tip
Use "Copy last invoice" for clients you invoice monthly. You only need to adjust the hours or quantities.

## Multiple currencies

You can create invoices in currencies other than euro:

1. Select the desired currency when creating the invoice
2. Enter amounts in the chosen currency
3. The exchange rate is stored with the invoice
4. When booking in FIN, amounts are converted to euro

## Selecting a revenue account

You can choose which revenue account the revenue is booked to per invoice:

1. Open the **Revenue account** dropdown when creating the invoice
2. Select the desired account from your chart of accounts
3. Only accounts marked as "ZZP Invoice Ledger" appear in the list

!!! info
If no revenue accounts are configured, the default revenue account from your tenant settings is used. Ask your Tenant Admin to mark the correct accounts in the chart of accounts.

## Tips

!!! tip
Always review the totals before sending an invoice. Once sent, the financial data cannot be modified.

- You can add multiple line items per invoice
- Draft invoices can be edited without restrictions
- The invoice number is only assigned when sending
- Use the notes field for payment instructions or project references

## Troubleshooting

| Problem                       | Cause                            | Solution                                                        |
| ----------------------------- | -------------------------------- | --------------------------------------------------------------- |
| No contacts available         | No contacts created yet          | Create a contact first via [Contacts](contacts.md)              |
| No products in the dropdown   | No products created yet          | Create a product first via [Products](products.md)              |
| VAT is not calculated         | VAT rates not configured         | Ask your Tenant Admin to set up the VAT rates                   |
| Revenue account not available | No accounts marked as ZZP ledger | Ask your Tenant Admin to mark accounts in the chart of accounts |
