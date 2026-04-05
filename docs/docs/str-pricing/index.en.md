# STR Pricing

> AI-powered pricing recommendations for your short-term rentals.

## Overview

The STR Pricing module generates daily pricing recommendations for your rental properties. The system combines historical booking data, occupancy rates, seasonal patterns, and events to calculate optimal prices for the next 14 months.

## What can you do here?

| Task                                               | Description                                   |
| -------------------------------------------------- | --------------------------------------------- |
| [View recommendations](viewing-recommendations.md) | View daily pricing recommendations and trends |
| [Event pricing](event-pricing.md)                  | Price uplifts during events and seasons       |
| [Apply suggestions](applying-suggestions.md)       | Generate and use pricing strategy             |

## How does it work?

The pricing calculation uses 7 factors that together determine the recommended price:

| Factor            | Description                            | Range     |
| ----------------- | -------------------------------------- | --------- |
| Base rate         | Weekday or weekend rate per listing    | €85–€160  |
| Historical factor | Performance on the same date last year | 0.5–1.0×  |
| Occupancy factor  | Occupancy rate in the relevant period  | 0.9–1.2×  |
| Pace factor       | Booking pace compared to last year     | 0.9–1.15× |
| Event factor      | Uplift during events and seasons       | 1.0–1.5×  |
| AI correction     | Fixed uplift based on AI analysis      | 1.05×     |
| VAT adjustment    | Correction for VAT rate changes        | 1.0×      |

**Formula:**

```
Recommended price = Base rate × Historical × Occupancy × Pace × Event × AI × VAT
```

## What do you see?

The pricing page shows:

- **Summary table** — Average factors per listing
- **Trend chart** — Historical ADR vs recommended ADR vs base rate over months
- **Monthly overview** — Expandable table with all factors per month
- **Quarterly summary** — Recommended vs historical ADR per quarter
- **Daily recommendations** — Detailed table with price per day

!!! info
ADR stands for Average Daily Rate — the average daily price. This is the standard metric in the rental industry.

## Typical workflow

1. **Generate** a pricing strategy for the next 14 months
2. **View** the recommendations per listing
3. **Analyze** the trends and factors
4. **Use** the recommended prices as a guideline for your platforms

!!! tip
Generate new recommendations regularly (monthly) to account for recent booking data and changing market conditions.
