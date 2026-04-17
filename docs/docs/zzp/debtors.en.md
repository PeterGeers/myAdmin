# Debtors & Creditors

> Manage outstanding receivables and payables.

## Overview

The debtors and creditors overview gives you insight into who still owes you money (debtors) and who you still owe money to (creditors). You can see at a glance which invoices are outstanding, which are overdue, and you can send payment reminders.

## What You'll Need

- Access to the ZZP module (`zzp_read` permissions)
- Sent invoices in your administration

## Step by Step

### 1. View outstanding receivables (debtors)

1. Go to **ZZP** → **Debtors**
2. You see an overview of all outgoing invoices with the status "sent" or "overdue"
3. The invoices are grouped by contact

| Column         | Description                           |
| -------------- | ------------------------------------- |
| Contact        | Name and Client ID of the debtor      |
| Invoice number | Number of the outstanding invoice     |
| Invoice date   | Date of the invoice                   |
| Due date       | Date when payment is expected         |
| Amount         | Outstanding amount                    |
| Status         | Sent or overdue                       |
| Days open      | Number of days since the invoice date |

### 2. View outstanding payables (creditors)

1. Go to **ZZP** → **Creditors**
2. You see an overview of all incoming invoices that have not been paid yet
3. The invoices are grouped by supplier

### 3. Aging analysis

The aging analysis shows outstanding amounts per age category:

| Category   | Description                         |
| ---------- | ----------------------------------- |
| Current    | Not yet overdue                     |
| 1-30 days  | 1 to 30 days past the due date      |
| 31-60 days | 31 to 60 days past the due date     |
| 61-90 days | 61 to 90 days past the due date     |
| 90+ days   | More than 90 days past the due date |

!!! warning
Invoices in the 90+ days category require extra attention. Consider legal action or writing off the receivable.

### 4. Check payments

The system can automatically check whether outstanding invoices have been paid:

1. Go to **ZZP** → **Debtors**
2. Click **Check payments**
3. The system compares bank payments with outstanding invoices
4. Matched invoices are automatically set to "paid"

!!! info
Payment checking matches based on the Client ID in the payment reference and the amount. Make sure your clients include the Client ID in their payment.

### 5. Send a payment reminder

For overdue invoices, you can send a reminder:

1. Go to **ZZP** → **Debtors**
2. Select the overdue invoice
3. Click **Send reminder**
4. The reminder is sent by email to the contact

## Automatic overdue detection

The system checks daily whether invoices are overdue:

- Invoices with the status "sent" whose due date has passed are automatically set to "overdue"
- You see overdue invoices directly in the debtors overview

## Tips

!!! tip
Check your debtors overview weekly. The sooner you take action on overdue invoices, the greater the chance of getting paid.

- Use the aging analysis to prioritize follow-up on outstanding invoices
- Send a reminder as soon as an invoice is overdue — don't wait too long
- The Client ID on your invoices helps with automatic payment matching
- Review the creditors overview to keep track of your own payment obligations

## Troubleshooting

| Problem                           | Cause                                    | Solution                                                                            |
| --------------------------------- | ---------------------------------------- | ----------------------------------------------------------------------------------- |
| Payment not automatically matched | Client ID missing from payment reference | Ask your client to include the Client ID in their payment                           |
| Invoice still shows as "sent"     | Payment not yet imported                 | Import your bank statements first via [Banking](../banking/importing-statements.md) |
| Amount doesn't match              | Partial payment or different amount      | Check the paid amount — partial payments are tracked separately                     |
| Reminder not received             | Email in spam or wrong address           | Check the contact's email address                                                   |
