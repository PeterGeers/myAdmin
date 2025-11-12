#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def analyze_keukenhof_historical():
    """Analyze actual historical performance during Keukenhof periods"""
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        print("=== Historical Keukenhof Performance Analysis ===\n")
        
        # Keukenhof typically runs mid-March to mid-May
        # Analyze historical performance during these periods
        keukenhof_query = """
        SELECT 
            YEAR(checkinDate) as year,
            COUNT(*) as bookings,
            AVG(amountGross/nights) as avg_adr,
            AVG(nights) as avg_los
        FROM bnb 
        WHERE listing = 'Red Studio' 
        AND (
            (MONTH(checkinDate) = 3 AND DAY(checkinDate) >= 15) OR
            (MONTH(checkinDate) = 4) OR
            (MONTH(checkinDate) = 5 AND DAY(checkinDate) <= 15)
        )
        AND checkinDate >= '2020-01-01'
        GROUP BY YEAR(checkinDate)
        ORDER BY year
        """
        
        # Compare with non-Keukenhof spring periods
        non_keukenhof_query = """
        SELECT 
            YEAR(checkinDate) as year,
            COUNT(*) as bookings,
            AVG(amountGross/nights) as avg_adr,
            AVG(nights) as avg_los
        FROM bnb 
        WHERE listing = 'Red Studio' 
        AND (
            (MONTH(checkinDate) = 3 AND DAY(checkinDate) < 15) OR
            (MONTH(checkinDate) = 5 AND DAY(checkinDate) > 15) OR
            (MONTH(checkinDate) = 6)
        )
        AND checkinDate >= '2020-01-01'
        GROUP BY YEAR(checkinDate)
        ORDER BY year
        """
        
        cursor.execute(keukenhof_query)
        keukenhof_data = cursor.fetchall()
        
        cursor.execute(non_keukenhof_query)
        non_keukenhof_data = cursor.fetchall()
        
        print("Historical Performance During Keukenhof Period (mid-Mar to mid-May):")
        keukenhof_total_adr = 0
        keukenhof_years = 0
        
        for row in keukenhof_data:
            print(f"{row['year']}: {row['bookings']} bookings, ADR: €{row['avg_adr']:.2f}")
            keukenhof_total_adr += row['avg_adr']
            keukenhof_years += 1
        
        keukenhof_avg_adr = keukenhof_total_adr / keukenhof_years if keukenhof_years > 0 else 0
        
        print(f"\nHistorical Performance During Non-Keukenhof Spring (early Mar, late May, June):")
        non_keukenhof_total_adr = 0
        non_keukenhof_years = 0
        
        for row in non_keukenhof_data:
            print(f"{row['year']}: {row['bookings']} bookings, ADR: €{row['avg_adr']:.2f}")
            non_keukenhof_total_adr += row['avg_adr']
            non_keukenhof_years += 1
        
        non_keukenhof_avg_adr = non_keukenhof_total_adr / non_keukenhof_years if non_keukenhof_years > 0 else 0
        
        print(f"\nComparison:")
        print(f"Average ADR during Keukenhof period: €{keukenhof_avg_adr:.2f}")
        print(f"Average ADR during non-Keukenhof spring: €{non_keukenhof_avg_adr:.2f}")
        
        if keukenhof_avg_adr > 0 and non_keukenhof_avg_adr > 0:
            actual_uplift = ((keukenhof_avg_adr / non_keukenhof_avg_adr) - 1) * 100
            print(f"Actual historical uplift during Keukenhof: {actual_uplift:+.1f}%")
            
            print(f"\nRecommendation:")
            if actual_uplift > 25:
                print(f"Current +25% uplift is CONSERVATIVE - historical shows {actual_uplift:.1f}%")
            elif actual_uplift < 10:
                print(f"Current +25% uplift is TOO AGGRESSIVE - historical shows only {actual_uplift:.1f}%")
            else:
                print(f"Current +25% uplift is REASONABLE - historical shows {actual_uplift:.1f}%")
        
        # Get overall baseline for Red Studio
        cursor.execute("""
        SELECT AVG(amountGross/nights) as baseline_adr
        FROM bnb 
        WHERE listing = 'Red Studio' 
        AND checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
        """)
        
        baseline = cursor.fetchone()
        baseline_adr = baseline['baseline_adr'] if baseline else 0
        
        print(f"\nCurrent baseline ADR for Red Studio: €{baseline_adr:.2f}")
        print(f"Database baseline: €85.00 weekday, €110.00 weekend")
        
        if baseline_adr > 0:
            baseline_gap = ((baseline_adr / 97.5) - 1) * 100  # 97.5 = avg of 85 and 110
            print(f"Historical vs Database gap: {baseline_gap:+.1f}%")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    analyze_keukenhof_historical()