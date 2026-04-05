# STR (Short-Term Rental)

> Process bookings from Airbnb, Booking.com, VRBO, and direct reservations.

## Overview

The STR module processes revenue files from rental platforms. You import booking files, the system automatically calculates VAT, tourist tax, and channel fees, and stores everything separated into realized and planned bookings.

## What can you do here?

| Task                                          | Description                                                     |
| --------------------------------------------- | --------------------------------------------------------------- |
| [Import bookings](importing-bookings.md)      | Upload files from Airbnb, Booking.com, VRBO, or direct bookings |
| [Realized vs planned](realized-vs-planned.md) | The difference between completed and future bookings            |
| [Revenue summaries](revenue-summaries.md)     | View revenue, occupancy, and trends                             |

## Supported platforms

| Platform    | File type                 | Details                                                  |
| ----------- | ------------------------- | -------------------------------------------------------- |
| Airbnb      | CSV                       | Dutch format with columns like "Begindatum", "Inkomsten" |
| Booking.com | Excel (.xlsx/.xls) or CSV | Check-in/check-out, guest names, pricing                 |
| VRBO        | CSV (multiple files)      | Reservations + Payouts separately                        |
| Direct      | Excel (.xlsx)             | Your own direct bookings                                 |
| Payout      | CSV                       | Booking.com monthly settlement files                     |

## What gets calculated?

For each booking, the system automatically calculates:

| Field           | Description                                |
| --------------- | ------------------------------------------ |
| Gross amount    | Total booking price                        |
| Channel fee     | Platform commission (e.g., 15% for Airbnb) |
| VAT             | 9% (before 2026) or 21% (from 2026)        |
| Tourist tax     | 6.02% (before 2026) or 6.9% (from 2026)    |
| Net amount      | Paid out to owner                          |
| Price per night | Net amount ÷ number of nights              |

!!! info
Tax rates are automatically determined based on the check-in date. Bookings with check-in from January 1, 2026 use the new rates.

## Typical workflow

1. **Download** the revenue file from your rental platform
2. **Select** the platform and upload the file
3. **View** the preview with realized and planned bookings
4. **Check** the calculated amounts
5. **Save** to the database

!!! tip
Import regularly (monthly) to keep your revenue summaries up to date. Planned bookings are updated with each import.
