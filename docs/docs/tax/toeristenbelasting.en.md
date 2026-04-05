# Tourist Tax (Toeristenbelasting)

> Calculate and report municipal tax on overnight stays.

## Overview

The tourist tax report calculates the tourist tax owed based on your STR bookings. The calculation is based on the number of overnight stays and the applicable rate.

## What You'll Need

- Imported STR bookings (via the [STR module](../str/importing-bookings.md))
- Access to BNB reports (`STR_Read` permissions)

## How does the calculation work?

Tourist tax is calculated per booking:

```
Tourist tax = Gross amount / (100 + tourist tax%) × tourist tax%
```

### Rates

| Period      | Rate  | Calculation basis                 |
| ----------- | ----- | --------------------------------- |
| Before 2026 | 6.02% | On the gross amount excluding VAT |
| From 2026   | 6.9%  | On the gross amount excluding VAT |

!!! info
The rate is automatically determined based on the check-in date of the booking. You don't need to set the rate manually.

## Step by Step

### 1. Open the report

Go to **Reports** → **BNB** → **Tourist tax**.

### 2. Select the year

Choose the year for which you want to calculate tourist tax. The system shows available years based on your booking data.

### 3. Generate the report

The report loads automatically and shows:

- Total tourist tax for the year
- Breakdown per quarter
- Breakdown per listing
- Number of overnight stays per period

### 4. Export the report

Click **Export HTML** to download the report as an HTML file: `Aangifte_Toeristenbelasting_[Year].html`

You can print this file or include it with your declaration to the municipality.

## What does the report show?

| Field              | Description                          |
| ------------------ | ------------------------------------ |
| Listing            | Name of the rental property          |
| Channel            | Airbnb, Booking.com, VRBO, or Direct |
| Number of bookings | Total realized bookings              |
| Number of nights   | Total overnight stays                |
| Gross revenue      | Total booking price                  |
| Tourist tax        | Calculated amount per listing/period |

## Tips

!!! tip
Check the report per quarter if your municipality requires quarterly declarations. Some municipalities ask for an annual declaration.

- Tourist tax is only calculated on realized bookings (not planned ones)
- Cancelled bookings with no earnings are not counted
- Import all booking files before generating the report

## Troubleshooting

| Problem              | Cause                               | Solution                                                          |
| -------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| Report is empty      | No STR bookings imported            | Import bookings via the STR module first                          |
| Amount seems too low | Not all bookings imported           | Check that all platforms (Airbnb, Booking.com, etc.) are imported |
| Wrong rate           | Check-in date falls in wrong period | Check that check-in dates are correct in the booking data         |
| Year not available   | No bookings in that year            | Import bookings for the desired year                              |
