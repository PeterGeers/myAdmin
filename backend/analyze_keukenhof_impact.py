#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from hybrid_pricing_optimizer import HybridPricingOptimizer

def analyze_keukenhof_impact():
    """Analyze Keukenhof event impact vs monthly ADR multipliers"""
    
    optimizer = HybridPricingOptimizer(test_mode=False)
    listing = 'Red Studio'
    
    print(f"=== Keukenhof vs Monthly ADR Impact Analysis ===\n")
    
    # Get historical data and calculate multipliers
    historical_data = optimizer._get_historical_data(listing)
    monthly_multipliers = optimizer._calculate_monthly_multipliers(historical_data)
    
    # Get listing data
    listing_data = optimizer._get_listing_performance(listing)
    base_weekday = listing_data.get('base_weekday_price', 85)
    base_weekend = listing_data.get('base_weekend_price', 110)
    
    print(f"Base Prices: €{base_weekday} weekday, €{base_weekend} weekend\n")
    
    # Keukenhof period: March 20 - May 12
    keukenhof_months = [3, 4, 5]  # March, April, May
    
    print("Monthly ADR Multipliers during Keukenhof season:")
    for month in keukenhof_months:
        month_name = ['', '', '', 'March', 'April', 'May'][month]
        multiplier = monthly_multipliers.get(month, 1.0)
        print(f"- {month_name}: {multiplier:.3f}x")
    
    print(f"\nKeukenhof Event Uplift: +25%")
    
    print(f"\nPricing Comparison for Keukenhof Period:")
    print("Month | Monthly ADR Only | With Keukenhof +25% | Difference")
    print("-" * 60)
    
    for month in keukenhof_months:
        month_name = ['', '', '', 'March', 'April', 'May'][month]
        multiplier = monthly_multipliers.get(month, 1.0)
        
        # Monthly ADR only
        adr_weekday = base_weekday * multiplier
        adr_weekend = base_weekend * multiplier
        
        # With Keukenhof event
        event_weekday = adr_weekday * 1.25
        event_weekend = adr_weekend * 1.25
        
        # Difference
        diff_weekday = event_weekday - adr_weekday
        diff_weekend = event_weekend - adr_weekend
        
        print(f"{month_name:<5} | €{adr_weekday:.2f}/€{adr_weekend:.2f}     | €{event_weekday:.2f}/€{event_weekend:.2f}      | +€{diff_weekday:.2f}/+€{diff_weekend:.2f}")
    
    print(f"\nAnalysis:")
    march_mult = monthly_multipliers.get(3, 1.0)
    april_mult = monthly_multipliers.get(4, 1.0)
    may_mult = monthly_multipliers.get(5, 1.0)
    
    print(f"- March ADR multiplier: {march_mult:.3f}x ({'below' if march_mult < 1.0 else 'above'} average)")
    print(f"- April ADR multiplier: {april_mult:.3f}x ({'below' if april_mult < 1.0 else 'above'} average)")  
    print(f"- May ADR multiplier: {may_mult:.3f}x ({'below' if may_mult < 1.0 else 'above'} average)")
    
    # Calculate total impact
    total_adr_impact = (march_mult + april_mult + may_mult) / 3
    total_event_impact = total_adr_impact * 1.25
    
    print(f"\nCombined Impact:")
    print(f"- Average ADR multiplier for Keukenhof season: {total_adr_impact:.3f}x")
    print(f"- With Keukenhof event (+25%): {total_event_impact:.3f}x")
    print(f"- Total uplift vs base price: {(total_event_impact - 1) * 100:.1f}%")

if __name__ == "__main__":
    analyze_keukenhof_impact()