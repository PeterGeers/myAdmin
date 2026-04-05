# Viewing Recommendations

> View daily pricing recommendations and trends per listing.

## Overview

After generating a pricing strategy, you can view the recommendations in various views: from a high-level overview to detailed daily prices with all underlying factors.

## What You'll Need

- Generated pricing recommendations (via [Applying suggestions](applying-suggestions.md))
- Access to the STR Pricing module (`str_read` permissions)

## Available views

### Summary table with factors

Shows the average value of each pricing factor per listing:

| Column        | Description                         |
| ------------- | ----------------------------------- |
| Listing       | Name of the rental property         |
| Base rate     | Average base rate (weekday/weekend) |
| Historical    | Average historical factor           |
| Occupancy     | Average occupancy factor            |
| Pace          | Average pace factor                 |
| Event         | Average event factor                |
| AI correction | Fixed AI uplift (1.05×)             |

### Trend chart

A line chart showing per month:

- **Historical ADR** — What you earned per night last year
- **Recommended ADR** — What the system recommends
- **Base rate** — Your configured base prices

This gives you an at-a-glance view of whether recommendations are higher or lower than your historical performance.

### Monthly overview

An expandable table per listing showing per month:

- All 7 factors individually
- Recommended price
- Comparison with last year

Click on a listing to see the monthly details.

### Quarterly summary

Summary per quarter (Q1–Q4):

- Recommended ADR
- Historical ADR
- Difference in percentage

### Daily recommendations

Detailed table showing per day:

| Column            | Description                           |
| ----------------- | ------------------------------------- |
| Date              | The specific day                      |
| Recommended price | Calculated optimal price              |
| AI ADR            | AI-recommended price                  |
| Historical ADR    | Price last year on the same date      |
| Variance          | Percentage difference from historical |
| Weekend           | Whether it's a weekend day            |
| Event             | Event name (if applicable)            |
| Uplift            | Event uplift in percentage            |
| Reasoning         | AI explanation for the recommendation |

!!! info
The table shows the first 50 days. Use the filters to select a specific listing.

## Step by Step

1. Go to **STR Pricing**
2. Select a listing from the dropdown (or view all)
3. Check the trend chart for the big picture
4. Click on a listing in the monthly overview for details
5. Scroll to the daily table for specific dates

## Tips

!!! tip
Pay attention to dates with a high event factor — these are the days where you can generate the most revenue.

- Compare the recommended price with your current price on the platform
- Weekend days typically have a higher base rate
- A low historical factor means you earned less on that date last year

## Troubleshooting

| Problem                    | Cause                              | Solution                                               |
| -------------------------- | ---------------------------------- | ------------------------------------------------------ |
| No recommendations visible | Not yet generated                  | Click "Generate Pricing" to generate recommendations   |
| Historical ADR is 0        | No bookings last year on that date | Normal for new listings or periods without bookings    |
| All prices are the same    | Insufficient historical data       | The system needs at least a few months of booking data |
