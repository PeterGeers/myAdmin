# Realized vs Planned

> The difference between completed and future bookings and how they are stored.

## Overview

When importing bookings, myAdmin automatically separates them into two categories: **realized** (past) and **planned** (future). This distinction is important for your revenue reports and tax declarations.

## How is it determined?

The separation is based on the **check-in date** relative to today:

| Category      | Rule                        | Example                                   |
| ------------- | --------------------------- | ----------------------------------------- |
| **Realized**  | Check-in date ≤ today       | Check-in was March 15 → realized          |
| **Planned**   | Check-in date > today       | Check-in is June 20 → planned             |
| **Cancelled** | Status contains "Cancelled" | Regardless of date, if there are earnings |

!!! info
Cancelled bookings with earnings > €0 are stored as realized (you received cancellation fees). Cancelled bookings with no earnings are skipped.

## Where are they stored?

| Category           | Database table | Behavior                                                              |
| ------------------ | -------------- | --------------------------------------------------------------------- |
| **Realized**       | `bnb`          | Permanent archive — bookings are added, never overwritten             |
| **Planned**        | `bnbplanned`   | Temporary — cleared and refilled with each import per channel/listing |
| **Future revenue** | `bnbfuture`    | Summary — aggregated planned revenue per date/channel/listing         |

### Why are planned bookings overwritten?

Planned bookings change constantly: new reservations come in, existing ones get cancelled or modified. That's why each import fully replaces planned bookings for the relevant channel and listing. This way you always have the most current state.

Realized bookings, on the other hand, are final and are only added (with duplicate checking on reservation code).

## What do you see in the interface?

After importing a file, you'll see three tabs:

### "Realized" tab

Shows all bookings with a check-in date in the past:

- Guest name, listing, dates
- Number of nights and guests
- Gross amount, channel fee, net amount
- VAT and tourist tax
- Reservation code and status

### "Planned" tab

Shows all bookings with a check-in date in the future:

- Same fields as realized
- Amounts are estimates (may still change)

### "Already loaded" tab

Shows bookings that already exist in the database (duplicates):

- These will not be saved again
- Recognition based on reservation code + channel

## Impact on reports

| Report         | Uses                               |
| -------------- | ---------------------------------- |
| BNB Revenue    | Realized bookings                  |
| BNB Actuals    | Realized bookings (year-over-year) |
| Tourist tax    | Realized bookings                  |
| Future revenue | Planned bookings                   |
| Violin charts  | Realized bookings                  |

!!! tip
Import regularly to keep the separation between realized and planned up to date. A booking that was "planned" last month will automatically become "realized" on the next import if the check-in date has passed.

## Troubleshooting

| Problem                                             | Cause                                    | Solution                                                            |
| --------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------- |
| Booking shows as "planned" but guest already stayed | File not re-imported after check-in date | Re-import the file — the booking will now be recognized as realized |
| Planned bookings disappeared                        | Normal behavior on new import            | Planned bookings are replaced with each import per channel          |
| Duplicate realized bookings                         | Should not happen                        | The system checks on reservation code + channel                     |
