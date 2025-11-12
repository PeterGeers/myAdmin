#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def update_listing_names():
    """Update listing names to match BNB table"""
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Update listing names to match BNB table
        updates = [
            ("UPDATE listings SET listing_name = 'Red Studio' WHERE listing_name = 'JaBaKi Red Studio'", "Red Studio"),
            ("UPDATE listings SET listing_name = 'Green Studio' WHERE listing_name = 'JaBaKi Green Studio'", "Green Studio"),
            ("UPDATE listings SET listing_name = 'Child Friendly' WHERE listing_name = 'JaBaKi Garden House'", "Child Friendly")
        ]
        
        for query, name in updates:
            cursor.execute(query)
            print(f"Updated to: {name}")
        
        conn.commit()
        
        # Verify updates
        cursor.execute("SELECT listing_name, base_weekday_price, base_weekend_price FROM listings")
        listings = cursor.fetchall()
        
        print("\nUpdated listings:")
        for listing in listings:
            print(f"- {listing[0]}: €{listing[1]}/€{listing[2]}")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    update_listing_names()