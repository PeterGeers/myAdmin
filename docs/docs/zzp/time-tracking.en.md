# Time Tracking

> Track hours worked per client and project.

## Overview

With time tracking, you keep track of how many hours you work per client and project. You can mark hours as billable or non-billable, and convert billable hours directly into invoice line items. This way you always know exactly what still needs to be invoiced.

!!! info
Time tracking can be enabled or disabled per tenant via settings. If you don't see time tracking, ask your Tenant Admin to activate this feature.

## What You'll Need

- Access to the ZZP module (`zzp_crud` permissions)
- At least one contact in your contact registry
- Optional: products linked to hourly rates

## Step by Step

### 1. Log hours

1. Go to **ZZP** → **Time Tracking**
2. Click **New entry**
3. Fill in the fields:

| Field           | Required | Description                                        |
| --------------- | -------- | -------------------------------------------------- |
| Date            | Yes      | Date the hours were worked                         |
| Contact         | Yes      | The client you worked for                          |
| Hours           | Yes      | Number of hours worked (decimal, e.g., 7.5)        |
| Hourly rate     | Yes      | Rate per hour (excl. VAT)                          |
| Product/service | No       | Link to a product from your catalog                |
| Project name    | No       | Name of the project                                |
| Description     | No       | Description of the work performed                  |
| Billable        | No       | Whether these hours can be invoiced (default: yes) |

4. Click **Save**

!!! tip
Link your hours to a product from your catalog. This way the hourly rate and VAT code are filled in automatically.

### 2. Create an invoice from hours

1. Go to **ZZP** → **Time Tracking**
2. Filter by the desired contact and period
3. Select the hours you want to invoice (only unbilled, billable hours)
4. Click **Create invoice**
5. The selected hours are converted into invoice line items
6. Review the invoice and click **Save**

When hours are linked to an invoice, they are marked as "billed" and no longer appear in the list of hours to be invoiced.

### 3. View summaries

Time tracking provides summaries by:

| Summary     | Description                                   |
| ----------- | --------------------------------------------- |
| Per client  | Total hours and amount per contact            |
| Per project | Total hours and amount per project name       |
| Per period  | Total hours per week, month, quarter, or year |

1. Go to **ZZP** → **Time Tracking**
2. Use the filters to select the desired period and client
3. View the summaries at the bottom of the overview

### 4. Upload supporting documents

You can link documents to your time entries:

1. Open a time entry or invoice
2. Click **Upload document**
3. Select the file (e.g., client timesheet, contract, delivery confirmation)
4. The document is stored and linked

!!! info
Linked documents can be sent as attachments when sending an invoice. See [Sending invoices](sending-invoices.md) for more information.

## Billable vs non-billable

| Type         | Description                                        |
| ------------ | -------------------------------------------------- |
| Billable     | Hours you charge to the client                     |
| Non-billable | Hours for internal tasks, acquisition, or training |

Non-billable hours are not included when creating invoices, but are visible in your summaries for your own records.

## Tips

!!! tip
Log your hours daily or weekly. This prevents forgetting hours and lets you quickly create an invoice at the end of the month.

- Use project names consistently so you can view summaries per project
- The hourly rate can differ per entry from the default rate in your product catalog
- Unbilled hours remain visible until you link them to an invoice

## Troubleshooting

| Problem                           | Cause                                    | Solution                                           |
| --------------------------------- | ---------------------------------------- | -------------------------------------------------- |
| Time tracking not visible         | Feature is disabled for your tenant      | Ask your Tenant Admin to enable time tracking      |
| Hours don't appear when invoicing | Hours are already billed or non-billable | Check the status and billable flag of the hours    |
| No contacts available             | No contacts created yet                  | Create a contact first via [Contacts](contacts.md) |
