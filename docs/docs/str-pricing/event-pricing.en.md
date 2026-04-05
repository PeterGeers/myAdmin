# Event Pricing

> Automatic price uplifts during events and seasons.

## Overview

The system automatically applies price uplifts when a date coincides with a known event or season. This ensures you charge higher prices during periods of high demand.

## How does it work?

Events are configured with a date range and an uplift percentage. When a date falls within an event's range, the event factor is applied to the recommended price.

**Calculation:**

```
Event factor = 1 + (uplift percentage / 100)
```

For example: an event with 35% uplift gives a factor of 1.35×.

## Configured events

| Event                 | Period               | Uplift | Type        |
| --------------------- | -------------------- | ------ | ----------- |
| Keukenhof             | March – May          | 25%    | Seasonal    |
| F1 Dutch Grand Prix   | Late August (3 days) | 35–50% | Major event |
| Amsterdam Dance Event | Mid October (5 days) | 35%    | Major event |

!!! info
Events are updated annually with the correct dates. Exact dates may vary per year.

## Event types

| Type                            | Description                                            | Typical uplift |
| ------------------------------- | ------------------------------------------------------ | -------------- |
| **Seasonal** (`seasonal`)       | Longer periods with increased demand (e.g., Keukenhof) | 5–25%          |
| **Major event** (`major_event`) | Short periods with peak demand (e.g., F1, ADE)         | 35–50%         |

## What do you see in the recommendations?

In the daily recommendations table, you'll see for each date:

- **Event** — Name of the event (empty if no event)
- **Uplift** — The uplift percentage
- **Event factor** — The multiplication factor in the factor overview

Dates with an event have a noticeably higher recommended price.

## Example

A listing with a base rate of €100 on a weekday:

| Situation           | Factors                                   | Recommended price |
| ------------------- | ----------------------------------------- | ----------------- |
| Normal day          | 100 × 0.8 × 1.0 × 1.0 × **1.0** × 1.05 =  | €84               |
| Keukenhof (25%)     | 100 × 0.8 × 1.0 × 1.0 × **1.25** × 1.05 = | €105              |
| F1 Grand Prix (50%) | 100 × 0.8 × 1.0 × 1.0 × **1.50** × 1.05 = | €126              |

_Other factors simplified for this example._

## Tips

!!! tip
Check event dates at the beginning of each year. Make sure they match the official dates.

- Major events have the highest uplift — these are your best earning opportunities
- Seasonal events last longer but have a lower uplift
- The uplift is applied automatically — you don't need to adjust anything manually

## Troubleshooting

| Problem                 | Cause                              | Solution                                                            |
| ----------------------- | ---------------------------------- | ------------------------------------------------------------------- |
| No event uplift visible | Date falls outside the event range | Check the event dates                                               |
| Uplift seems too low    | Event is of type "seasonal"        | Seasonal events intentionally have a lower uplift than major events |
| Event is missing        | Not yet configured                 | Contact your administrator to add the event                         |
