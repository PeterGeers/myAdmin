# VAT Declaration (BTW)

> Prepare and save quarterly VAT (BTW) returns.

## Overview

The VAT report calculates your sales tax per quarter based on your financial transactions. It shows the VAT received, input tax (VAT paid), and the difference you need to pay or receive back.

## What You'll Need

- Imported transactions for the relevant quarter
- Access to financial reports (`Finance_Read` permissions)
- A selected tenant/administration

## How does the calculation work?

The system calculates three components:

| Component           | Description                                       | Accounts                 |
| ------------------- | ------------------------------------------------- | ------------------------ |
| VAT account balance | Running balance of VAT accounts up to quarter end | 2010, 2020, 2021         |
| VAT received        | VAT received on your revenue                      | Revenue and VAT accounts |
| Input tax           | VAT paid on purchases                             | Input tax accounts       |

**Final calculation:**

```
Amount due = VAT received − Input tax
```

- Positive result → You need to pay VAT to the tax authority
- Negative result → You receive VAT back from the tax authority

## Step by Step

### 1. Open the VAT report

Go to **Reports** → **Financial** → **BTW**.

### 2. Select year and quarter

Choose the year and quarter (Q1–Q4) for which you want to prepare the declaration.

| Quarter | Period             | End date     |
| ------- | ------------------ | ------------ |
| Q1      | January – March    | March 31     |
| Q2      | April – June       | June 30      |
| Q3      | July – September   | September 30 |
| Q4      | October – December | December 31  |

### 3. Generate the report

Click **Generate report**. The system:

1. Calculates the balance of VAT accounts up to the end of the quarter
2. Calculates received VAT and input tax for the quarter
3. Shows the result: amount to pay or receive

### 4. View the report

The report shows two sections:

**Balance overview:**

- VAT accounts with their balances up to the end of the quarter
- Total balance

**Quarter overview:**

- VAT and revenue accounts for the specific quarter
- VAT received
- Input tax (VAT paid)
- Payment instruction ("€X to pay" or "€X to receive")

### 5. Save the transaction

Click **Save** to record the VAT transaction in the database. The report is also uploaded as an HTML file.

## Exporting

- The report is automatically saved as an HTML file: `BTW_[Administration]_[Year]_Q[Quarter].html`
- You can print or save the HTML file for your records

## Tips

!!! tip
Only generate the VAT report after all transactions for the quarter have been imported. Missing transactions lead to incorrect calculations.

- Always verify the result before submitting the declaration to the tax authority
- The system accounts for the correct VAT rate (9% or 21%) based on the transaction date
- Keep the HTML report for your own records

## Troubleshooting

| Problem              | Cause                                      | Solution                                           |
| -------------------- | ------------------------------------------ | -------------------------------------------------- |
| Report is empty      | No transactions in the quarter             | Import transactions for this quarter first         |
| VAT amount is wrong  | Transactions missing or incorrectly posted | Check that all transactions are correctly imported |
| "No tenant selected" | No administration selected                 | Select a tenant in the navigation bar              |
| Save failed          | No write permissions                       | Contact your administrator                         |
