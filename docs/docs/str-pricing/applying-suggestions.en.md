# Applying Suggestions

> Generate and use a pricing strategy for your rental properties.

## Overview

You generate a pricing strategy by having the system calculate 14 months of daily prices. The recommendations are saved and can be used as a guideline for setting prices on your rental platforms.

## What You'll Need

- Historical booking data (at least a few months)
- Configured listings with base rates
- Access to the STR Pricing module

## Step by Step

### 1. Open STR Pricing

In myAdmin, go to **STR Pricing**. You'll see the pricing dashboard.

### 2. Select a listing

Choose a specific listing from the dropdown, or leave it empty to generate for all listings at once.

### 3. Generate the pricing strategy

Click **Generate Pricing**. The system:

1. Retrieves historical booking data (last 24 months)
2. Calculates base rates per listing (weekday/weekend)
3. Analyzes occupancy rates and booking pace
4. Checks the event calendar for uplifts
5. Asks AI for strategic insights (30 days)
6. Calculates daily prices for 14 months (~420 days)
7. Saves all recommendations to the database

!!! info
Generation may take a moment (30-60 seconds) as the system consults AI models and calculates hundreds of daily prices.

### 4. View the results

After generation, a confirmation appears with the number of generated daily prices. The recommendations are now visible in all views (see [Viewing recommendations](viewing-recommendations.md)).

### 5. Use the recommendations

The recommended prices are a guideline. You can use them to:

- Set prices on **Airbnb**, **Booking.com**, and other platforms
- Recognize seasonal patterns and adjust your strategy
- Check whether your current prices are in line with the market

!!! warning
Recommendations are based on historical data and AI analysis. Use them as a guideline, not as absolute truth. Always consider local market conditions.

## What happens when regenerating?

When you regenerate:

- All existing recommendations for the selected listing are deleted
- New recommendations are calculated with the most recent data
- The trend chart and tables are updated

This is normal and desired — you always want the most current recommendations.

## Tips

!!! tip
Generate new recommendations after every major import of booking data. This way the system accounts for your latest performance.

- Generate for all listings at once for a consistent overview
- Compare recommendations with your actual prices on the platforms
- Pay attention to the AI reasoning in the daily table — it provides context for the recommendation
- Base rates are configured per listing in the listings configuration

## Troubleshooting

| Problem                 | Cause                        | Solution                                                          |
| ----------------------- | ---------------------------- | ----------------------------------------------------------------- |
| Generation fails        | No API key configured        | Contact your administrator to set up the OpenRouter API key       |
| All prices are the same | No historical data available | Import booking data via the STR module first                      |
| Generation takes long   | AI model is slow             | Wait for the process to complete — this can take up to 60 seconds |
| No listings in dropdown | No listings configured       | Contact your administrator to add listings                        |
