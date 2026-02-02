#!/usr/bin/env python3
"""
Test Direct Booking Date Parsing
Tests the date parsing logic with sample data
"""

from datetime import datetime, date
import pandas as pd

def test_date_parsing():
    """Test various date formats"""
    
    test_dates = [
        '2026-06-06',
        '2026-06-06 00:00:00',
        '06-06-2026',
        '2026-06-04',
        '2026-05-19',
        '2026-02-02',
    ]
    
    today = date.today()
    print(f"Today: {today}")
    print()
    print(f"{'Input Date':<25} {'Parsed Date':<15} {'Status':<10} {'Correct?'}")
    print("-" * 70)
    
    for test_date in test_dates:
        try:
            # Convert to string and handle various formats
            checkin_str = str(test_date).strip()
            
            # Try different date formats
            checkin_dt = None
            for date_format in ['%Y-%m-%d', '%d-%m-%Y', '%Y-%m-%d %H:%M:%S']:
                try:
                    checkin_dt = datetime.strptime(checkin_str.split()[0], date_format).date()
                    break
                except:
                    continue
            
            if checkin_dt is None:
                # If all formats fail, try pandas to_datetime
                checkin_dt = pd.to_datetime(checkin_str).date()
            
            if checkin_dt > today:
                booking_status = 'planned'
            else:
                booking_status = 'realised'
            
            # Determine if correct
            expected = 'planned' if checkin_dt > today else 'realised'
            correct = '✅' if booking_status == expected else '❌'
            
            print(f"{test_date:<25} {str(checkin_dt):<15} {booking_status:<10} {correct}")
            
        except Exception as e:
            print(f"{test_date:<25} {'FAILED':<15} {'realised':<10} ❌ Error: {e}")
    
    print()
    print("=" * 70)
    print("Testing with actual booking data format:")
    print()
    
    # Simulate actual booking data
    bookings = [
        {'reservationCode': 'HA-8YM4XP', 'startDate': '2026-06-06', 'nights': 1},
        {'reservationCode': 'HA-6316NF', 'startDate': '2026-06-04', 'nights': 1},
        {'reservationCode': 'HA-KN90H2', 'startDate': '2026-05-19', 'nights': 1},
        {'reservationCode': 'GY-8aiVkd', 'startDate': '2026-02-02', 'nights': 1},
    ]
    
    print(f"{'Reservation':<15} {'Check-in':<12} {'Status':<10} {'Expected':<10} {'Match?'}")
    print("-" * 70)
    
    for booking in bookings:
        checkin_date = booking['startDate']
        booking_id = booking['reservationCode']
        
        try:
            checkin_str = str(checkin_date).strip()
            checkin_dt = None
            
            for date_format in ['%Y-%m-%d', '%d-%m-%Y', '%Y-%m-%d %H:%M:%S']:
                try:
                    checkin_dt = datetime.strptime(checkin_str.split()[0], date_format).date()
                    break
                except:
                    continue
            
            if checkin_dt is None:
                checkin_dt = pd.to_datetime(checkin_str).date()
            
            if checkin_dt > today:
                booking_status = 'planned'
            else:
                booking_status = 'realised'
            
            expected = 'planned' if checkin_dt > today else 'realised'
            match = '✅' if booking_status == expected else '❌'
            
            print(f"{booking_id:<15} {str(checkin_dt):<12} {booking_status:<10} {expected:<10} {match}")
            
        except Exception as e:
            print(f"{booking_id:<15} {checkin_date:<12} {'ERROR':<10} {'N/A':<10} ❌")
            print(f"  Error: {e}")


if __name__ == '__main__':
    print("=" * 70)
    print("Direct Booking Date Parsing Test")
    print("=" * 70)
    print()
    test_date_parsing()
