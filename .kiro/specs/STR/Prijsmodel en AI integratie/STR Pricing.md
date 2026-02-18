# STR Pricing Business Rules & Logic

## Overview
The STR Pricing system calculates `pricing_recommendations.recommended_price` using a hybrid approach combining business logic with AI insights. This document explains the bottom-up calculation methodology for each listing.

## Core Calculation Formula

```
recommended_price = base_rate × historical_mult × occupancy_mult × pace_mult × event_mult × ai_correction × btw_adjustment
```

## 1. Base Rate Calculation (`_get_base_rate`)

**Source**: `listings` table - listing-specific rates
**Logic**: Weekend vs weekday differentiation

```sql
SELECT base_weekday_price, base_weekend_price 
FROM listings 
WHERE listing_name = ? AND active = TRUE
```

**Weekend Definition**: Friday (4) and Saturday (5) nights
**Current Base Rates**:
- **Child Friendly**: €130 weekday, €160 weekend
- **Green Studio**: €100 weekday, €120 weekend  
- **Red Studio**: €100 weekday, €120 weekend

## 2. Historical Performance Multiplier (`_get_historical_multiplier`)

**Purpose**: Adjust pricing based on same-date historical performance
**Data Source**: `bnb` table with guest fee adjustments for nrOfGuests > 2

```sql
-- Child Friendly guest fee adjustment: (amountGross - ((guests - 2) * 30)) / nights
SELECT AVG(
    CASE 
        WHEN listing = 'Child Friendly' AND guests > 2 
        THEN (amountGross - ((guests - 2) * 30)) / nights
        ELSE amountGross / nights
    END
) as historical_adr
FROM bnb 
WHERE listing = ? 
AND MONTH(checkinDate) = ?
AND DAY(checkinDate) BETWEEN ? AND ?
AND YEAR(checkinDate) < ?
```

**Calculation**: `historical_adr / baseline_adr`
**Range**: 0.5 - 2.0 (typical)

## 3. Occupancy-Based Demand Multiplier (`_get_occupancy_multiplier`)

**Purpose**: Price adjustment based on historical occupancy patterns
**Logic**: Higher occupancy = higher prices

```sql
SELECT COUNT(*) as bookings, COUNT(DISTINCT DATE(checkinDate)) as booked_days
FROM bnb 
WHERE listing = ? AND MONTH(checkinDate) = ? AND YEAR(checkinDate) < ?
```

**Multiplier Rules**:
- **>85% occupancy**: 1.2x (high demand premium)
- **>70% occupancy**: 1.1x (good demand)
- **<40% occupancy**: 0.9x (low demand discount)
- **40-70% occupancy**: 1.0x (standard)

## 4. Revenue Trend Multiplier (`_get_booking_pace_multiplier`)

**Purpose**: Dynamic pricing based on revenue trends over 12-month periods
**Data Source**: `bnbfuture` table with planned revenue by listing and channel

**Logic**:
```sql
WITH monthly_latest AS (
    SELECT 
        date, listing, amount,
        STR_TO_DATE(date, '%Y%m') as date_parsed,
        ROW_NUMBER() OVER (PARTITION BY listing, date ORDER BY id DESC) as rn
    FROM bnbfuture 
    WHERE listing = ?
)
SELECT 
    SUM(CASE WHEN date_parsed >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH) 
        THEN amount ELSE 0 END) as last_12_months,
    SUM(CASE WHEN date_parsed BETWEEN DATE_SUB(CURDATE(), INTERVAL 24 MONTH) 
        AND DATE_SUB(CURDATE(), INTERVAL 12 MONTH) 
        THEN amount ELSE 0 END) as previous_12_months
FROM monthly_latest 
WHERE rn = 1
```

**Table Structure**:
- `date`: CHAR(12) in YYYYMM format (e.g., '202411')
- `amount`: DOUBLE - planned revenue amount
- `listing`: VARCHAR(128) - property name
- `channel`: VARCHAR(128) - booking platform

**Calculation**:
```python
revenue_trend_ratio = last_12_months_revenue / previous_12_months_revenue
```

**Implementation Details**:
- **Multiple measurements**: Uses ROW_NUMBER() to select latest measurement per month (ORDER BY id DESC)
- **Data aggregation**: SUM of amount over 12-month periods using only one value per month
- **Date format**: YYYYMM string converted to date for comparison
- **Missing data**: Returns 1.0x (neutral) when no bnbfuture data available
- **Zero previous revenue**: Returns 1.0x to avoid division by zero
- **Fair comparison**: Prevents double-counting months with multiple measurements

**Multiplier Rules**:
- **>1.5x trend**: 1.15x (strong revenue growth)
- **>1.2x trend**: 1.1x (good revenue growth)
- **<0.5x trend**: 0.9x (significant revenue decline)
- **<0.8x trend**: 0.95x (moderate revenue decline)
- **0.8-1.2x trend**: 1.0x (stable revenue)


## 5. Event Premium Multiplier (`_get_event_multiplier`)

**Source**: `pricing_events` table
**Logic**: Date-based event uplifts

```sql
SELECT uplift_percentage, event_name
FROM pricing_events 
WHERE ? BETWEEN start_date AND end_date
AND active = TRUE
ORDER BY uplift_percentage DESC
LIMIT 1
```

**Current Events**:
- **Keukenhof Season**: +5% (March-May)
- **Dutch Grand Prix**: +10% (August weekend)
- **Amsterdam Dance Event**: +5% (October)
- **Christmas/New Year**: +8% (Dec 24-Jan 2)

**Calculation**: `1 + (uplift_percentage / 100)`

## 6. AI Correction Factor

**Purpose**: 5% AI-driven adjustment for market conditions
**Value**: Fixed at 1.05 (5% uplift)
**Rationale**: AI provides market intelligence correction to business logic

## 7. BTW (VAT) Adjustment

**Purpose**: Future-proofing for VAT changes
**Current**: 1.0 (no adjustment)
**Future**: Placeholder for 9% → 21% VAT change implementation

## Listing-Specific Characteristics

### Child Friendly
- **Premium Positioning**: Highest base rates (€130/€160)
- **Guest Fee Adjustment**: Deducts €30 per extra guest (>2) from historical ADR
- **Target Market**: Families, higher willingness to pay
- **Historical ADR**: €158.44 (adjusted for guest fees)

### Green Studio  
- **Mid-Tier Positioning**: Standard rates (€100/€120)
- **Balanced Performance**: Consistent €95-€108 ADR range
- **Target Market**: Business travelers, couples
- **Growth Potential**: +12% vs last year

### Red Studio
- **Budget Positioning**: Standard rates (€100/€120) 
- **Price Sensitive**: Lower historical ADR €99.68
- **Target Market**: Budget-conscious travelers
- **Conservative Growth**: -6% vs last year

## AI Integration Layer

### Data Sources for AI
- **Historical Performance**: 24-month ADR trends
- **Seasonal Patterns**: Monthly performance variations
- **Event Calendar**: Netherlands-specific events
- **Market Conditions**: Booking pace and occupancy

### AI Model Inputs
```json
{
  "listing": "Child Friendly",
  "historical_adr": 158.44,
  "base_weekday": 130,
  "base_weekend": 160,
  "seasonal_trends": {...},
  "events": {...}
}
```

### AI Output Processing
- **Primary**: Business logic calculation
- **Secondary**: AI recommendations as validation/adjustment
- **Storage**: Both business and AI results in `pricing_recommendations`

## Database Schema

### pricing_recommendations Table
```sql
CREATE TABLE pricing_recommendations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    listing_name VARCHAR(128),
    price_date DATE,
    recommended_price DECIMAL(10,2),      -- Final business logic result
    ai_recommended_adr DECIMAL(10,2),     -- AI suggestion
    ai_historical_adr DECIMAL(10,2),      -- AI historical reference
    ai_variance VARCHAR(10),              -- AI vs historical variance
    ai_reasoning TEXT,                    -- AI explanation
    is_weekend TINYINT(1),
    event_uplift INT DEFAULT 0,
    event_name VARCHAR(128),
    last_year_adr DECIMAL(10,2),          -- Same date last year
    base_rate DECIMAL(10,2),              -- Base weekday/weekend rate
    historical_mult DECIMAL(5,3),         -- Historical performance multiplier
    occupancy_mult DECIMAL(5,3),          -- Occupancy-based multiplier
    pace_mult DECIMAL(5,3),               -- Revenue trend multiplier
    event_mult DECIMAL(5,3),              -- Event premium multiplier
    ai_correction DECIMAL(5,3),           -- AI correction factor
    btw_adjustment DECIMAL(5,3),          -- VAT adjustment factor
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Business Rules Summary

1. **Base Rate Foundation**: Listing-specific weekday/weekend rates
2. **Historical Intelligence**: Same-date performance from previous years
3. **Revenue Intelligence**: 12-month revenue trend analysis from bnbfuture data
4. **Event Premiums**: Netherlands-specific event calendar
5. **AI Enhancement**: 5% market correction factor
6. **Guest Fee Adjustment**: Child Friendly deducts extra guest charges
7. **Revenue Trends**: 12-month rolling revenue performance analysis
8. **Market Positioning**: Premium/Mid-tier/Budget differentiation

## Key Performance Indicators

### Revenue Optimization
- **RevPAR**: Revenue per available room
- **ADR Growth**: Year-over-year average daily rate
- **Occupancy Impact**: Booking conversion at different price points

### Pricing Accuracy
- **Variance Analysis**: Recommended vs actual achieved rates
- **Market Response**: Booking pace changes after price adjustments
- **Competitive Position**: Rate comparison within market segment

## Multiplier Analysis Dashboard

### STR Pricing Optimizer Display
The frontend shows a **Pricing Multipliers Summary** table with average values per listing:

- **Base Rate**: Average weekday/weekend base price used
- **Historical**: Historical performance adjustment factor
- **Occupancy**: Demand-based occupancy multiplier
- **Revenue Trend**: 12-month revenue trend multiplier
- **Event**: Event-based premium multiplier
- **AI Correction**: Fixed 5% AI adjustment factor
- **Records**: Number of pricing calculations included

### API Endpoint
```
GET /api/pricing/multipliers
```
Returns average multiplier values grouped by listing for analysis.

## Future Enhancements

1. **Dynamic Event Detection**: Automatic event discovery and impact analysis
2. **Competitor Pricing**: Market rate intelligence integration
3. **Weather Impact**: Weather-based demand adjustments
4. **Length of Stay**: Dynamic pricing for longer bookings
5. **Channel Optimization**: Platform-specific pricing strategies
6. **Multiplier Trends**: Historical multiplier performance tracking

## Usage Guidelines

### For Understanding
- Review calculation steps to understand price derivation
- Analyze multiplier impacts on final pricing
- Compare business logic vs AI recommendations

### For Improvements
- Adjust base rates based on market performance
- Modify multiplier ranges based on booking data
- Add new events or seasonal patterns
- Enhance AI correction factors

### For Troubleshooting
- Check each multiplier component for unexpected values
- Validate historical data quality and completeness
- Review event calendar accuracy and timing
- Verify guest fee adjustments for Child Friendly

This document serves as both explanation and prompt for future STR pricing system enhancements.