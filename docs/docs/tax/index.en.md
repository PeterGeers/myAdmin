# Tax

> Prepare VAT declarations, income tax, and tourist tax.

## Overview

The Tax module helps you prepare your tax declarations. The system calculates amounts based on your imported transactions and bookings, so you have the correct data for the tax authority.

## What can you do here?

| Task                                 | Description                      |
| ------------------------------------ | -------------------------------- |
| [VAT declaration (BTW)](btw.md)      | Prepare quarterly VAT returns    |
| [Income tax (IB)](income-tax-ib.md)  | Annual income tax declaration    |
| [Tourist tax](toeristenbelasting.md) | Municipal tax on overnight stays |

## Tax type overview

| Tax             | Frequency | Source                 | Calculation                       |
| --------------- | --------- | ---------------------- | --------------------------------- |
| VAT (BTW)       | Quarterly | Financial transactions | Revenue × VAT rate − Input tax    |
| Income tax (IB) | Annually  | All transactions       | Business profit − Deductions      |
| Tourist tax     | Annually  | STR bookings           | Number of nights × Rate per night |

## VAT rates

| Rate | Application                                        |
| ---- | -------------------------------------------------- |
| 21%  | Standard rate (most goods and services)            |
| 9%   | Reduced rate (incl. short-term rental before 2026) |
| 0%   | Exempt                                             |

!!! warning
From January 1, 2026, the VAT rate for short-term rental changed from 9% to 21%. The system automatically applies the correct rate based on the date.

## Where to find the reports?

Tax reports are available in two places:

- **Reports** → **Financial** → **BTW** and **Aangifte IB** tabs
- **Reports** → **BNB** → **Tourist tax** tab

## Tips

!!! tip
Prepare your VAT declaration at the end of each quarter. This way you always have up-to-date data for the tax authority.

- Make sure all transactions are imported before generating a declaration
- Export reports as HTML or XLSX for your records
- Tourist tax is calculated based on your STR bookings — import those first
