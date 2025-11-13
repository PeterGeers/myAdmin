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
        base_rate = self._get_base_rate(date, listing)
        
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
    
    def _get_base_rate(self, date, listing=None):
        """Get base weekday/weekend rate for specific listing"""
        if not listing:
            # Fallback to default rates
            is_weekend = date.weekday() in [4, 5]
            return 110 if is_weekend else 85
        
        conn = self.db.get_connection()
        try:
            query = """
            SELECT base_weekday_price, base_weekend_price
            FROM listings 
            WHERE listing_name = %s AND active = TRUE
            """
            
            result_df = pd.read_sql(query, conn, params=[listing])
            
            if not result_df.empty:
                is_weekend = date.weekday() in [4, 5]
                weekday_price = float(result_df.iloc[0]['base_weekday_price'])
                weekend_price = float(result_df.iloc[0]['base_weekend_price'])
                return weekend_price if is_weekend else weekday_price
            
            # Fallback if listing not found
            is_weekend = date.weekday() in [4, 5]
            return 110 if is_weekend else 85
            
        except Exception as e:
            print(f"Base rate error: {e}")
            is_weekend = date.weekday() in [4, 5]
            return 110 if is_weekend else 85
        finally:
            conn.close()
    
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
        """Get multiplier based on revenue trends over 12-month periods"""
        conn = self.db.get_connection()
        
        try:
            # First check if bnbfuture table has data
            check_query = "SELECT COUNT(*) as count FROM bnbfuture WHERE listing = %s"
            check_df = pd.read_sql(check_query, conn, params=[listing])
            
            if check_df.iloc[0]['count'] == 0:
                print(f"No bnbfuture data for {listing}, using default pace multiplier 1.0")
                return 1.0
            
            # Get 2024 vs 2023 monthly revenue data for specific month
            monthly_query = """
            WITH monthly_data AS (
                SELECT 
                    YEAR(date) as year,
                    MONTH(date) as month,
                    SUM(amount) as monthly_amount
                FROM bnbfuture 
                WHERE listing = %s AND MONTH(date) = %s
                GROUP BY YEAR(date), MONTH(date)
            )
            SELECT 
                AVG(CASE WHEN year = 2024 THEN monthly_amount ELSE NULL END) as year_2024,
                AVG(CASE WHEN year = 2023 THEN monthly_amount ELSE NULL END) as year_2023,
                COUNT(*) as total_records
            FROM monthly_data
            """
            
            result_df = pd.read_sql(monthly_query, conn, params=[listing, date.month])
            
            # If no data found with exact listing name, try aggregating all channels for this listing
            if result_df.empty or result_df.iloc[0]['total_records'] == 0:
                aggregate_query = """
                WITH monthly_aggregated AS (
                    SELECT 
                        YEAR(date) as year,
                        MONTH(date) as month,
                        date,
                        SUM(amount) as total_amount
                    FROM bnbfuture 
                    WHERE listing = %s
                    GROUP BY YEAR(date), MONTH(date), date
                )
                SELECT 
                    SUM(CASE WHEN date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH) 
                        THEN total_amount ELSE 0 END) as last_12_months,
                    SUM(CASE WHEN date BETWEEN DATE_SUB(CURDATE(), INTERVAL 24 MONTH) 
                        AND DATE_SUB(CURDATE(), INTERVAL 12 MONTH) 
                        THEN total_amount ELSE 0 END) as previous_12_months,
                    COUNT(*) as total_records
                FROM monthly_aggregated
                """
                result_df = pd.read_sql(aggregate_query, conn, params=[listing])
            
            if not result_df.empty and result_df.iloc[0]['total_records'] > 0:
                year_2024 = float(result_df.iloc[0]['year_2024'] or 0)
                year_2023 = float(result_df.iloc[0]['year_2023'] or 0)
                
                total_records = result_df.iloc[0]['total_records']
                print(f"Monthly pace data for {listing} (month {date.month}): 2024={year_2024:.0f}, 2023={year_2023:.0f}, records={total_records}")
                
                # Calculate revenue trend ratio
                if year_2023 > 0 and year_2024 > 0:
                    monthly_trend_ratio = year_2024 / year_2023
                    print(f"2024 vs 2023 trend ratio for {listing} (month {date.month}): {monthly_trend_ratio:.3f}")
                    
                    # Apply multiplier rules based on revenue trends
                    if monthly_trend_ratio > 1.5:
                        print(f"Strong monthly growth multiplier: 1.15")
                        return 1.15
                    elif monthly_trend_ratio > 1.2:
                        print(f"Good monthly growth multiplier: 1.1")
                        return 1.1
                    elif monthly_trend_ratio < 0.3:
                        print(f"Very significant monthly decline multiplier: 0.9")
                        return 0.9
                    elif monthly_trend_ratio < 0.7:
                        print(f"Moderate monthly decline multiplier: 0.95")
                        return 0.95
                    else:
                        print(f"Stable monthly revenue multiplier: 1.0")
                        return 1.0
                elif total_records > 0:
                    print(f"Missing 2024 or 2023 data for {listing} (month {date.month}), using default 1.0")
                else:
                    print(f"No previous revenue data, using default 1.0")
            else:
                print(f"No monthly revenue data found for {listing} (month {date.month}), using default 1.0")
            

            return 1.0  # Default for no data or stable revenue
            
        except Exception as e:
            print(f"Monthly revenue trend error for {listing}: {e}")
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