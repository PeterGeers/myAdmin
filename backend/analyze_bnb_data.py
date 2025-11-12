#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager
import pandas as pd
from datetime import datetime

def analyze_bnb_data():
    """Analyze existing BNB data for pricing model development"""
    
    print("=== BNB Data Analysis for Dynamic Pricing ===\n")
    
    db = DatabaseManager(test_mode=False)  # Use production data
    conn = db.get_connection()
    
    try:
        # Check bnb table structure and data
        print("1. BNB Table Analysis:")
        bnb_query = """
        SELECT COUNT(*) as total_records,
               MIN(checkinDate) as earliest_checkin,
               MAX(checkoutDate) as latest_checkout,
               AVG(amountGross) as avg_total,
               AVG(nights) as avg_nights
        FROM bnb 
        WHERE checkinDate IS NOT NULL
        """
        
        bnb_df = pd.read_sql(bnb_query, conn)
        print(f"Total records: {bnb_df['total_records'].iloc[0]}")
        print(f"Date range: {bnb_df['earliest_checkin'].iloc[0]} to {bnb_df['latest_checkout'].iloc[0]}")
        print(f"Average total: €{bnb_df['avg_total'].iloc[0]:.2f}")
        print(f"Average nights: {bnb_df['avg_nights'].iloc[0]:.1f}")
        
        # Monthly occupancy and ADR analysis
        print("\n2. Monthly Performance (Last 12 months):")
        monthly_query = """
        SELECT 
            YEAR(checkinDate) as year,
            MONTH(checkinDate) as month,
            COUNT(*) as bookings,
            SUM(nights) as total_nights,
            AVG(pricePerNight) as adr,
            SUM(amountGross) as revenue
        FROM bnb 
        WHERE checkinDate >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        GROUP BY YEAR(checkinDate), MONTH(checkinDate)
        ORDER BY year, month
        """
        
        monthly_df = pd.read_sql(monthly_query, conn)
        for _, row in monthly_df.iterrows():
            print(f"{int(row['year'])}-{int(row['month']):02d}: {int(row['bookings'])} bookings, {int(row['total_nights'])} nights, ADR: €{row['adr']:.2f}")
        
        # Check bnbplanned table
        print("\n3. BNB Planned Table Analysis:")
        planned_query = """
        SELECT COUNT(*) as total_planned,
               MIN(checkinDate) as earliest_planned,
               MAX(checkoutDate) as latest_planned,
               AVG(amountGross) as avg_planned_total
        FROM bnbplanned 
        WHERE checkinDate IS NOT NULL
        """
        
        planned_df = pd.read_sql(planned_query, conn)
        print(f"Planned bookings: {planned_df['total_planned'].iloc[0]}")
        if planned_df['total_planned'].iloc[0] > 0:
            print(f"Planned range: {planned_df['earliest_planned'].iloc[0]} to {planned_df['latest_planned'].iloc[0]}")
            print(f"Average planned total: €{planned_df['avg_planned_total'].iloc[0]:.2f}")
        
        # Seasonal analysis
        print("\n4. Seasonal Patterns:")
        seasonal_query = """
        SELECT 
            CASE 
                WHEN MONTH(checkinDate) IN (3,4,5) THEN 'Spring (Keukenhof)'
                WHEN MONTH(checkinDate) IN (6,7,8) THEN 'Summer (F1 Aug)'
                WHEN MONTH(checkinDate) IN (9,10,11) THEN 'Autumn (ADE Oct)'
                ELSE 'Winter'
            END as season,
            COUNT(*) as bookings,
            AVG(pricePerNight) as avg_adr,
            AVG(nights) as avg_length_of_stay
        FROM bnb 
        WHERE checkinDate >= '2023-01-01'
        GROUP BY 
            CASE 
                WHEN MONTH(checkinDate) IN (3,4,5) THEN 'Spring (Keukenhof)'
                WHEN MONTH(checkinDate) IN (6,7,8) THEN 'Summer (F1 Aug)'
                WHEN MONTH(checkinDate) IN (9,10,11) THEN 'Autumn (ADE Oct)'
                ELSE 'Winter'
            END
        ORDER BY avg_adr DESC
        """
        
        seasonal_df = pd.read_sql(seasonal_query, conn)
        for _, row in seasonal_df.iterrows():
            print(f"{row['season']}: {row['bookings']} bookings, ADR: €{row['avg_adr']:.2f}, LOS: {row['avg_length_of_stay']:.1f} nights")
        
        # Weekend vs weekday analysis
        print("\n5. Weekend vs Weekday Analysis:")
        weekday_query = """
        SELECT 
            CASE WHEN DAYOFWEEK(checkinDate) IN (1,7) THEN 'Weekend' ELSE 'Weekday' END as day_type,
            COUNT(*) as bookings,
            AVG(pricePerNight) as avg_adr
        FROM bnb 
        WHERE checkinDate >= '2023-01-01'
        GROUP BY CASE WHEN DAYOFWEEK(checkinDate) IN (1,7) THEN 'Weekend' ELSE 'Weekday' END
        """
        
        weekday_df = pd.read_sql(weekday_query, conn)
        for _, row in weekday_df.iterrows():
            print(f"{row['day_type']}: {row['bookings']} bookings, ADR: €{row['avg_adr']:.2f}")
        
        print("\n=== Analysis Complete ===")
        print("Next steps:")
        print("1. Create AI pricing optimizer using this historical data")
        print("2. Build /api/pricing/recommendations endpoint")
        print("3. Add React pricing dashboard")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    analyze_bnb_data()