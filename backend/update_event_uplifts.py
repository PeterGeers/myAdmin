#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def update_event_uplifts():
    """Update event uplifts based on historical analysis"""
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Update Keukenhof events to realistic 5% uplift
        cursor.execute("""
        UPDATE pricing_events 
        SET uplift_percentage = 5 
        WHERE event_name LIKE '%Keukenhof%'
        """)
        
        # Keep F1 and ADE at higher levels (they likely have more impact)
        # But let's be more conservative
        cursor.execute("""
        UPDATE pricing_events 
        SET uplift_percentage = 35 
        WHERE event_name LIKE '%F1%'
        """)
        
        cursor.execute("""
        UPDATE pricing_events 
        SET uplift_percentage = 20 
        WHERE event_name LIKE '%ADE%'
        """)
        
        conn.commit()
        
        # Show updated events
        cursor.execute("SELECT * FROM pricing_events ORDER BY start_date")
        events = cursor.fetchall()
        
        print("Updated Event Uplifts:")
        for event in events:
            print(f"- {event[1]}: {event[2]} to {event[3]} (+{event[4]}%)")
        
        print(f"\nChanges made:")
        print(f"- Keukenhof: Reduced to +5% (from +25%) based on historical data")
        print(f"- F1 Dutch GP: Reduced to +35% (from +50%) - more conservative")
        print(f"- ADE: Reduced to +20% (from +35%) - more conservative")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    update_event_uplifts()