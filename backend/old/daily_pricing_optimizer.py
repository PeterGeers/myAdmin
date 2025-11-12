import requests
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import DatabaseManager

load_dotenv()

class DailyPricingOptimizer:
    def __init__(self, test_mode=False):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.db = DatabaseManager(test_mode=test_mode)
        
    def generate_daily_pricing(self, days=90, listing=None):
        """Generate daily pricing recommendations"""
        
        events_data = self._get_events_data()
        
        prompt = f"""
Generate DAILY pricing for listing '{listing}' in Hoofddorp for next {days} days.

Listing-specific historical performance:
{json.dumps(self._get_listing_performance(listing), indent=2)}

Event Data with Exact Dates:
{json.dumps(events_data, indent=2)}

Rules:
- Base weekday: €85, Base weekend: €110
- Apply event uplifts ONLY on exact event dates
- Weekend = Friday/Saturday (+25% premium)

Return JSON with daily prices:
{{
  "daily_prices": [
    {{"date": "2025-02-01", "price": 85.00, "is_weekend": false, "event_uplift": 0, "event_name": null}},
    {{"date": "2025-02-02", "price": 110.00, "is_weekend": true, "event_uplift": 0, "event_name": null}},
    {{"date": "2025-03-20", "price": 106.25, "is_weekend": false, "event_uplift": 25, "event_name": "Keukenhof 2025"}}
  ]
}}
"""

        # Use rule-based pricing for date-level precision
        print("Using rule-based pricing for accurate date calculations")
        fallback_data = self._generate_fallback_daily_pricing(days, listing)
        
        # Save pricing to database if listing specified
        if listing and 'daily_prices' in fallback_data:
            self.save_pricing_recommendations(fallback_data['daily_prices'], listing)
        
        return fallback_data
    
    def _get_events_data(self):
        """Get events from database"""
        conn = self.db.get_connection()
        
        try:
            events_query = """
            SELECT event_name, start_date, end_date, uplift_percentage
            FROM pricing_events 
            WHERE active = TRUE AND end_date >= CURDATE()
            ORDER BY start_date
            """
            
            import pandas as pd
            events_df = pd.read_sql(events_query, conn)
            
            events_list = []
            for _, row in events_df.iterrows():
                events_list.append({
                    "event_name": row['event_name'],
                    "start_date": str(row['start_date']),
                    "end_date": str(row['end_date']),
                    "uplift_percentage": int(row['uplift_percentage'])
                })
            
            return {"events": events_list}
            
        except Exception as e:
            print(f"Events data error: {e}")
            return {"events": []}
        finally:
            conn.close()
    
    def _generate_fallback_daily_pricing(self, days, listing=None):
        """Generate rule-based daily pricing with listing-specific attributes"""
        daily_prices = []
        
        # Get listing-specific pricing if available
        listing_data = self._get_listing_performance(listing) if listing else {}
        base_weekday = listing_data.get('base_weekday_price', 85)
        base_weekend = listing_data.get('base_weekend_price', 110)
        price_multiplier = listing_data.get('price_multiplier', 1.0)
        
        # Get events for date checking
        events_data = self._get_events_data()
        
        start_date = datetime.now().date()
        
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Check if weekend (Friday=4, Saturday=5 only)
            is_weekend = current_date.weekday() in [4, 5]
            base_price = (base_weekend if is_weekend else base_weekday) * price_multiplier
            
            # Check for events
            event_uplift = 0
            event_name = None
            
            for event in events_data.get("events", []):
                event_start = datetime.strptime(event["start_date"], "%Y-%m-%d").date()
                event_end = datetime.strptime(event["end_date"], "%Y-%m-%d").date()
                
                if event_start <= current_date <= event_end:
                    event_uplift = event["uplift_percentage"]
                    event_name = event["event_name"]
                    break
            
            # Apply event uplift
            final_price = base_price * (1 + event_uplift / 100)
            
            daily_prices.append({
                "date": date_str,
                "price": round(final_price, 2),
                "is_weekend": is_weekend,
                "event_uplift": event_uplift,
                "event_name": event_name
            })
        
        return {"daily_prices": daily_prices}
    
    def save_pricing_recommendations(self, daily_prices, listing):
        """Save pricing recommendations to database"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Clear existing recommendations for this listing
            cursor.execute("DELETE FROM pricing_recommendations WHERE listing_name = %s", [listing])
            
            # Insert new recommendations
            insert_sql = """
            INSERT INTO pricing_recommendations 
            (listing_name, price_date, recommended_price, is_weekend, event_uplift, event_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            valid_prices = []
            for price in daily_prices:
                try:
                    # Validate date format
                    from datetime import datetime
                    datetime.strptime(price['date'], '%Y-%m-%d')
                    valid_prices.append(price)
                except ValueError:
                    print(f"Skipping invalid date: {price['date']}")
                    continue
            
            for price in valid_prices:
                cursor.execute(insert_sql, [
                    listing,
                    price['date'],
                    price['price'],
                    price['is_weekend'],
                    price['event_uplift'],
                    price['event_name']
                ])
            
            conn.commit()
            print(f"Saved {len(valid_prices)} pricing recommendations for {listing}")
            return True
            
        except Exception as e:
            print(f"Error saving pricing: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def _get_listing_performance(self, listing):
        """Get listing attributes and historical performance"""
        if not listing:
            return {"avg_adr": 95.0, "avg_occupancy": 70}
        
        conn = self.db.get_connection()
        
        try:
            # Get listing attributes
            attributes_query = """
            SELECT listing_name, listing_type, max_guests, bedrooms, bathrooms, size_sqm,
                   has_balcony, has_garden, has_parking, has_kitchen, has_ac, has_heating,
                   floor_level, view_type, base_weekday_price, base_weekend_price, price_multiplier,
                   min_stay_weekday, min_stay_weekend
            FROM listings 
            WHERE listing_name = %s AND active = TRUE
            """
            
            # Get historical performance
            performance_query = """
            SELECT COUNT(*) as bookings, AVG(amountGross/nights) as avg_adr, AVG(nights) as avg_los
            FROM bnb 
            WHERE listing = %s AND checkinDate >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            """
            
            import pandas as pd
            attributes_df = pd.read_sql(attributes_query, conn, params=[listing])
            performance_df = pd.read_sql(performance_query, conn, params=[listing])
            
            result = {"listing": listing}
            
            # Add attributes if found
            if not attributes_df.empty:
                attr = attributes_df.iloc[0]
                result.update({
                    "listing_type": attr['listing_type'],
                    "max_guests": int(attr['max_guests']),
                    "bedrooms": int(attr['bedrooms']),
                    "size_sqm": int(attr['size_sqm']) if attr['size_sqm'] else 0,
                    "amenities": {
                        "balcony": bool(attr['has_balcony']),
                        "garden": bool(attr['has_garden']),
                        "parking": bool(attr['has_parking']),
                        "kitchen": bool(attr['has_kitchen']),
                        "ac": bool(attr['has_ac'])
                    },
                    "base_weekday_price": float(attr['base_weekday_price']),
                    "base_weekend_price": float(attr['base_weekend_price']),
                    "price_multiplier": float(attr['price_multiplier']),
                    "min_stay_weekday": int(attr['min_stay_weekday']),
                    "min_stay_weekend": int(attr['min_stay_weekend'])
                })
            
            # Add performance if found
            if not performance_df.empty and performance_df['bookings'].iloc[0] > 0:
                perf = performance_df.iloc[0]
                result.update({
                    "bookings_12m": int(perf['bookings']),
                    "historical_adr": float(perf['avg_adr']),
                    "avg_los": float(perf['avg_los'])
                })
            
            return result
                
        except Exception as e:
            print(f"Listing data error: {e}")
            return {"listing": listing, "base_weekday_price": 85.0, "base_weekend_price": 110.0}
        finally:
            conn.close()