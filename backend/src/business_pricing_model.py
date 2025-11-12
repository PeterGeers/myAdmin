import mysql.connector
import pandas as pd
from datetime import datetime, timedelta
from database import DatabaseManager
import warnings
warnings.filterwarnings('ignore', message='pandas only supports SQLAlchemy connectable')

class BusinessPricingModel:
    def __init__(self, test_mode=False):
        self.db = DatabaseManager(test_mode=test_mode)
    
    def calculate_business_price(self, listing, date):
        """Calculate price using business logic with occupancy data"""
        
        # 1. Base rate (weekday/weekend)
        base_rate = self._get_base_rate(date)
        
        # 2. Historical performance multiplier
        historical_mult = self._get_historical_multiplier(listing, date)
        
        # 3. Occupancy-based demand multiplier
        occupancy_mult = self._get_occupancy_multiplier(listing, date)
        
        # 4. Booking pace multiplier
        pace_mult = self._get_booking_pace_multiplier(listing, date)
        
        # 5. Event premium
        event_mult = self._get_event_multiplier(date)
        
        # 6. AI correction factor (5% uplift)
        ai_correction = 1.05
        
        # 7. BTW adjustment (placeholder for 9% -> 21% change)
        btw_adjustment = self._get_btw_adjustment(date)
        
        # Final calculation
        business_price = base_rate * historical_mult * occupancy_mult * pace_mult * event_mult * ai_correction * btw_adjustment
        
        return {
            'base_rate': base_rate,
            'historical_mult': historical_mult,
            'occupancy_mult': occupancy_mult,
            'pace_mult': pace_mult,
            'event_mult': event_mult,
            'ai_correction': ai_correction,
            'btw_adjustment': btw_adjustment,
            'final_price': round(business_price, 2)
        }
    
    def _get_base_rate(self, date):
        """Get base weekday/weekend rate"""
        # Friday=4, Saturday=5 are weekend nights
        is_weekend = date.weekday() in [4, 5]
        return 110 if is_weekend else 85
    
    def _get_historical_multiplier(self, listing, date):
        """Get multiplier based on same date historical performance"""
        conn = self.db.get_connection()
        
        try:
            # Get ADR for same date ±7 days in previous years
            query = """
            SELECT AVG(amountGross/nights) as historical_adr
            FROM bnb 
            WHERE listing = %s 
            AND MONTH(checkinDate) = %s
            AND DAY(checkinDate) BETWEEN %s AND %s
            AND YEAR(checkinDate) < %s
            AND nights > 0
            """
            
            result_df = pd.read_sql(query, conn, params=[
                listing, 
                date.month,
                max(1, date.day - 7),
                min(31, date.day + 7),
                date.year
            ])
            
            if not result_df.empty and result_df.iloc[0]['historical_adr']:
                historical_adr = float(result_df.iloc[0]['historical_adr'])
                
                # Get annual baseline for this listing
                baseline_query = """
                SELECT AVG(amountGross/nights) as baseline_adr
                FROM bnb 
                WHERE listing = %s 
                AND checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
                AND nights > 0
                """
                baseline_df = pd.read_sql(baseline_query, conn, params=[listing])
                
                if not baseline_df.empty and baseline_df.iloc[0]['baseline_adr']:
                    baseline_adr = float(baseline_df.iloc[0]['baseline_adr'])
                    return round(historical_adr / baseline_adr, 3)
            
            return 1.0  # Default if no historical data
            
        except Exception as e:
            print(f"Historical multiplier error: {e}")
            return 1.0
        finally:
            conn.close()
    
    def _get_occupancy_multiplier(self, listing, date):
        """Get multiplier based on historical occupancy for this period"""
        conn = self.db.get_connection()
        
        try:
            # Calculate occupancy for same month in previous years
            query = """
            SELECT 
                COUNT(*) as bookings,
                COUNT(DISTINCT DATE(checkinDate)) as booked_days
            FROM bnb 
            WHERE listing = %s 
            AND MONTH(checkinDate) = %s
            AND YEAR(checkinDate) < %s
            """
            
            result_df = pd.read_sql(query, conn, params=[listing, date.month, date.year])
            
            if not result_df.empty:
                bookings = result_df.iloc[0]['bookings']
                booked_days = result_df.iloc[0]['booked_days']
                
                # Estimate occupancy (rough calculation)
                days_in_month = 30  # Approximate
                occupancy_rate = booked_days / days_in_month if days_in_month > 0 else 0
                
                # Apply occupancy-based pricing
                if occupancy_rate > 0.85:  # High demand
                    return 1.2
                elif occupancy_rate > 0.70:  # Good demand
                    return 1.1
                elif occupancy_rate < 0.40:  # Low demand
                    return 0.9
                else:
                    return 1.0
            
            return 1.0
            
        except Exception as e:
            print(f"Occupancy multiplier error: {e}")
            return 1.0
        finally:
            conn.close()
    
    def _get_booking_pace_multiplier(self, listing, date):
        """Get multiplier based on current vs last year booking pace"""
        conn = self.db.get_connection()
        
        try:
            # Days until target date
            days_ahead = (date - datetime.now().date()).days
            
            if days_ahead < 0:  # Past date
                return 1.0
            
            # Current bookings for this date
            current_query = """
            SELECT COUNT(*) as current_bookings
            FROM bnbplanned 
            WHERE listing = %s 
            AND checkinDate = %s
            """
            
            current_df = pd.read_sql(current_query, conn, params=[listing, date])
            current_bookings = current_df.iloc[0]['current_bookings'] if not current_df.empty else 0
            
            # Same date last year bookings (at same time before)
            last_year_date = date.replace(year=date.year - 1)
            last_year_query = """
            SELECT COUNT(*) as last_year_bookings
            FROM bnb 
            WHERE listing = %s 
            AND checkinDate = %s
            """
            
            last_year_df = pd.read_sql(last_year_query, conn, params=[listing, last_year_date])
            last_year_bookings = last_year_df.iloc[0]['last_year_bookings'] if not last_year_df.empty else 0
            
            # Compare booking pace
            if last_year_bookings > 0:
                pace_ratio = current_bookings / last_year_bookings
                if pace_ratio > 1.5:  # Much faster booking
                    return 1.15
                elif pace_ratio > 1.2:  # Faster booking
                    return 1.1
                elif pace_ratio < 0.5:  # Much slower booking
                    return 0.9
                elif pace_ratio < 0.8:  # Slower booking
                    return 0.95
            
            return 1.0
            
        except Exception as e:
            print(f"Booking pace error: {e}")
            return 1.0
        finally:
            conn.close()
    
    def _get_event_multiplier(self, date):
        """Get event-based premium multiplier"""
        conn = self.db.get_connection()
        
        try:
            query = """
            SELECT uplift_percentage, event_name
            FROM pricing_events 
            WHERE %s BETWEEN start_date AND end_date
            AND active = TRUE
            ORDER BY uplift_percentage DESC
            LIMIT 1
            """
            
            result_df = pd.read_sql(query, conn, params=[date])
            
            if not result_df.empty:
                uplift = float(result_df.iloc[0]['uplift_percentage'])
                return 1 + (uplift / 100)  # Convert percentage to multiplier
            
            return 1.0
            
        except Exception as e:
            print(f"Event multiplier error: {e}")
            return 1.0
        finally:
            conn.close()
    
    def _get_btw_adjustment(self, date):
        """Get BTW (VAT) adjustment factor for 9% -> 21% change"""
        # TODO: Implement BTW change logic when decision is made
        # For now, no adjustment (1.0)
        # Future: Check if host or guest pays the extra 12% BTW
        return 1.0