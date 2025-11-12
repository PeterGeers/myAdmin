import requests
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import DatabaseManager
from business_pricing_model import BusinessPricingModel
import warnings
warnings.filterwarnings('ignore', message='pandas only supports SQLAlchemy connectable')

load_dotenv()

class HybridPricingOptimizer:
    def __init__(self, test_mode=False):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.db = DatabaseManager(test_mode=test_mode)
        self.business_model = BusinessPricingModel(test_mode=test_mode)
        
    def generate_pricing_strategy(self, months=14, listing=None):
        """Generate 14-month pricing with AI insights and rule-based execution"""
        
        # Generate AI strategic insights
        ai_insights = self._generate_ai_insights(months, listing)
        print(f"AI insights generated: {bool(ai_insights)}")
        
        # Generate rule-based daily pricing for 14 months with AI adjustments
        days = months * 30  # Approximate days
        daily_pricing = self._generate_daily_pricing(days, listing, ai_insights)
        
        # Save pricing to database
        if listing and daily_pricing:
            self._save_pricing_to_database(daily_pricing, listing)
        
        # Save AI insights to file
        ai_saved = False
        if ai_insights:
            ai_saved = self._save_ai_insights_to_file(ai_insights, listing)
        print(f"AI insights saved: {ai_saved}")
        
        return {
            'daily_prices_count': len(daily_pricing),
            'ai_insights_saved': bool(ai_insights),
            'months_generated': months,
            'listing': listing
        }
    
    def _generate_ai_insights(self, months, listing):
        """Generate AI strategic insights"""
        
        historical_data = self._get_historical_data(listing)
        events_data = self._get_events_data()
        listing_data = self._get_listing_performance(listing) if listing else {}
        
        # Calculate actual historical nightly rates by season/period
        historical_rates = self._calculate_historical_rates(listing, historical_data)
        print(f"Historical data for {listing}: avg_adr_24m={historical_data.get('avg_adr_24m', 0):.2f}")
        print(f"Listing data: {listing_data}")
        
        prompt = f"""
Generate daily ADR for {listing} (Netherlands) for next 30 days.

Location: Hoofddorp, Netherlands - NO US holidays (Thanksgiving, etc.)
Historical ADR: €{historical_data.get('avg_adr_24m', 95):.2f}
Base rates: €{listing_data.get('base_weekday_price', 85):.2f} weekday, €{listing_data.get('base_weekend_price', 110):.2f} weekend

STRATEGY: Use historical ADR (€{historical_data.get('avg_adr_24m', 95):.2f}) as baseline, apply weekend premiums, stay within ±20%.

Return JSON:
{{
  "daily_adr_recommendations": [
    {{"date": "2025-11-12", "recommended_adr": 145.00, "historical_adr": {historical_data.get('avg_adr_24m', 95):.2f}, "variance": "-8.5%", "reasoning": "November weekday"}}
  ],
  "strategy_summary": "Netherlands pricing strategy"
}}

Generate 30 days from today. Use historical ADR as reference for all variance calculations.
"""

        try:
            models = ["openai/gpt-3.5-turbo", "moonshotai/kimi-k2:free"]
            
            for model in models:
                try:
                    response = requests.post(
                        self.base_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.3,
                            "max_tokens": 1500
                        },
                        timeout=15
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result['choices'][0]['message']['content'].strip()
                        
                        if content.startswith('```json'):
                            content = content.replace('```json', '').replace('```', '').strip()
                        
                        try:
                            insights = json.loads(content)
                            print(f"AI insights generated using {model}")
                            return insights
                        except json.JSONDecodeError as e:
                            print(f"{model} JSON parse error: {e}")
                            print(f"Raw content: {content[:500]}...")
                            continue
                        
                except Exception as e:
                    print(f"{model} request failed: {e}")
                    continue
            
            return None
            
        except Exception as e:
            print(f"AI insights failed: {e}")
            return None
    
    def _calculate_historical_rates(self, listing, historical_data):
        """Calculate actual historical nightly rates by period"""
        if not listing or not historical_data.get('monthly_performance'):
            return {"note": "No historical rate data available"}
        
        try:
            rates_analysis = {
                "listing": listing,
                "avg_adr_24m": historical_data.get('avg_adr_24m', 0),
                "total_bookings_24m": historical_data.get('total_bookings_24m', 0),
                "monthly_rates": [],
                "seasonal_rates": []
            }
            
            # Monthly rate trends
            for month_data in historical_data.get('monthly_performance', []):
                rates_analysis["monthly_rates"].append({
                    "period": f"{month_data['year']}-{month_data['month']:02d}",
                    "achieved_adr": round(month_data.get('avg_adr', 0), 2),
                    "bookings": month_data.get('bookings', 0)
                })
            
            # Seasonal rate analysis
            for season_data in historical_data.get('seasonal_performance', []):
                rates_analysis["seasonal_rates"].append({
                    "season": season_data['season'],
                    "achieved_adr": round(season_data.get('avg_adr', 0), 2),
                    "bookings": season_data.get('bookings', 0)
                })
            
            return rates_analysis
            
        except Exception as e:
            print(f"Rate calculation error: {e}")
            return {"error": "Could not calculate historical rates"}
    
    def _calculate_monthly_multipliers(self, historical_data):
        """Calculate monthly multipliers based on historical ADR performance"""
        try:
            monthly_performance = historical_data.get('monthly_performance', [])
            if not monthly_performance:
                return {i: 1.0 for i in range(1, 13)}
            
            # Calculate average ADR across all months
            total_adr = sum(month['avg_adr'] for month in monthly_performance)
            avg_adr = total_adr / len(monthly_performance)
            
            # Calculate multipliers for each month based on historical ADR
            multipliers = {}
            for month_data in monthly_performance:
                month = month_data['month']
                month_adr = month_data['avg_adr']
                multiplier = month_adr / avg_adr if avg_adr > 0 else 1.0
                multipliers[month] = round(multiplier, 3)
            
            # Fill missing months with average (1.0)
            for month in range(1, 13):
                if month not in multipliers:
                    multipliers[month] = 1.0
            
            print(f"Monthly ADR multipliers: {dict(sorted(multipliers.items()))}")
            return multipliers
            
        except Exception as e:
            print(f"Monthly multiplier error: {e}")
            return {i: 1.0 for i in range(1, 13)}
    
    def _calculate_seasonal_multipliers(self, historical_data):
        """Calculate seasonal multipliers based on historical performance"""
        try:
            seasonal_performance = historical_data.get('seasonal_performance', [])
            if not seasonal_performance:
                return {'Spring': 1.0, 'Summer': 1.0, 'Autumn': 1.0, 'Winter': 1.0}
            
            # Calculate average ADR across all seasons
            total_adr = sum(season['avg_adr'] for season in seasonal_performance)
            avg_adr = total_adr / len(seasonal_performance)
            
            # Calculate multipliers relative to average
            multipliers = {}
            for season_data in seasonal_performance:
                season = season_data['season']
                season_adr = season_data['avg_adr']
                multiplier = season_adr / avg_adr if avg_adr > 0 else 1.0
                multipliers[season] = round(multiplier, 3)
            
            print(f"Seasonal multipliers: {multipliers}")
            return multipliers
            
        except Exception as e:
            print(f"Seasonal multiplier error: {e}")
            return {'Spring': 1.0, 'Summer': 1.0, 'Autumn': 1.0, 'Winter': 1.0}
    
    def _get_season(self, month):
        """Get season for a given month"""
        if month in [3, 4, 5]:
            return 'Spring'
        elif month in [6, 7, 8]:
            return 'Summer'
        elif month in [9, 10, 11]:
            return 'Autumn'
        else:
            return 'Winter'
    
    def _generate_daily_pricing(self, days, listing, ai_insights=None):
        """Generate business logic pricing with AI insights as additional data"""
        daily_prices = []
        
        # Get AI daily recommendations if available
        ai_daily_recommendations = {}
        if ai_insights and 'daily_adr_recommendations' in ai_insights:
            for rec in ai_insights['daily_adr_recommendations']:
                ai_daily_recommendations[rec['date']] = rec
            print(f"AI daily recommendations loaded: {len(ai_daily_recommendations)} days")
        
        start_date = datetime.now().date()
        
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Use BusinessPricingModel for main pricing logic
            business_result = self.business_model.calculate_business_price(listing, current_date)
            final_price = business_result['final_price']
            
            # Extract event info from business model
            event_uplift = int((business_result['event_mult'] - 1) * 100)
            event_name = self._get_event_name_for_date(current_date)
            
            # Check if weekend (Friday=4, Saturday=5 only)
            is_weekend = current_date.weekday() in [4, 5]
            
            # Get AI data if available
            ai_data = ai_daily_recommendations.get(date_str, {})
            
            # Get last year ADR for same date
            last_year_adr = self._get_last_year_adr(listing, current_date)
            
            daily_prices.append({
                "date": date_str,
                "price": final_price,
                "is_weekend": is_weekend,
                "event_uplift": event_uplift,
                "event_name": event_name,
                "ai_recommended_adr": ai_data.get('recommended_adr') if isinstance(ai_data, dict) else None,
                "ai_historical_adr": ai_data.get('historical_adr') if isinstance(ai_data, dict) else None,
                "ai_variance": ai_data.get('variance') if isinstance(ai_data, dict) else None,
                "ai_reasoning": ai_data.get('reasoning') if isinstance(ai_data, dict) else None,
                "last_year_adr": last_year_adr
            })
        
        return daily_prices
    
    def _save_pricing_to_database(self, daily_prices, listing):
        """Save pricing to database"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Clear existing recommendations for this listing
            cursor.execute("DELETE FROM pricing_recommendations WHERE listing_name = %s", [listing])
            
            # Insert new recommendations
            insert_sql = """
            INSERT INTO pricing_recommendations 
            (listing_name, price_date, recommended_price, is_weekend, event_uplift, event_name, ai_recommended_adr, ai_historical_adr, ai_variance, ai_reasoning, last_year_adr)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            valid_prices = []
            for price in daily_prices:
                try:
                    datetime.strptime(price['date'], '%Y-%m-%d')
                    valid_prices.append(price)
                except ValueError:
                    continue
            
            for price in valid_prices:
                cursor.execute(insert_sql, [
                    listing,
                    price['date'],
                    price['price'],
                    price['is_weekend'],
                    price['event_uplift'],
                    price['event_name'],
                    price.get('ai_recommended_adr'),
                    price.get('ai_historical_adr'),
                    price.get('ai_variance'),
                    price.get('ai_reasoning'),
                    price.get('last_year_adr')
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
    
    def _save_ai_insights_to_file(self, insights, listing):
        """Save AI insights to JSON file"""
        if not insights:
            print("No AI insights to save")
            return False
            
        try:
            filename = f"ai_insights_{listing.replace(' ', '_') if listing else 'general'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(os.path.dirname(__file__), '..', 'ai_insights', filename)
            
            print(f"Attempting to save to: {filepath}")
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Add metadata
            insights_with_metadata = {
                'generated_at': datetime.now().isoformat(),
                'listing': listing,
                'insights': insights
            }
            
            with open(filepath, 'w') as f:
                json.dump(insights_with_metadata, f, indent=2)
            
            print(f"AI insights saved successfully to: {filename}")
            return True
            
        except Exception as e:
            print(f"Error saving AI insights: {e}")
            import traceback
            traceback.print_exc()
            return False
    
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
    
    def _get_listing_performance(self, listing):
        """Get listing attributes"""
        if not listing:
            return {"base_weekday_price": 85.0, "base_weekend_price": 110.0}
        
        conn = self.db.get_connection()
        
        try:
            attributes_query = """
            SELECT base_weekday_price, base_weekend_price
            FROM listings 
            WHERE listing_name = %s AND active = TRUE
            """
            
            import pandas as pd
            attributes_df = pd.read_sql(attributes_query, conn, params=[listing])
            
            if not attributes_df.empty:
                attr = attributes_df.iloc[0]
                return {
                    "base_weekday_price": float(attr['base_weekday_price']),
                    "base_weekend_price": float(attr['base_weekend_price'])
                }
            else:
                return {"base_weekday_price": 85.0, "base_weekend_price": 110.0}
                
        except Exception as e:
            print(f"Listing data error: {e}")
            return {"base_weekday_price": 85.0, "base_weekend_price": 110.0}
        finally:
            conn.close()
    
    def _get_historical_data(self, listing=None):
        """Get listing-specific historical performance data"""
        conn = self.db.get_connection()
        
        try:
            # Listing-specific historical data
            if listing:
                
                monthly_query = """
                SELECT 
                    YEAR(checkinDate) as year,
                    MONTH(checkinDate) as month,
                    COUNT(*) as bookings,
                    AVG(amountGross/nights) as avg_adr,
                    AVG(nights) as avg_los,
                    SUM(amountGross) as total_revenue
                FROM bnb 
                WHERE listing = %s AND checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
                GROUP BY YEAR(checkinDate), MONTH(checkinDate)
                ORDER BY year, month
                """
                
                # Seasonal performance for this listing
                seasonal_query = """
                SELECT 
                    CASE 
                        WHEN MONTH(checkinDate) IN (3,4,5) THEN 'Spring'
                        WHEN MONTH(checkinDate) IN (6,7,8) THEN 'Summer'
                        WHEN MONTH(checkinDate) IN (9,10,11) THEN 'Autumn'
                        ELSE 'Winter'
                    END as season,
                    COUNT(*) as bookings,
                    AVG(amountGross/nights) as avg_adr,
                    AVG(nights) as avg_los
                FROM bnb 
                WHERE listing = %s AND checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
                GROUP BY 
                    CASE 
                        WHEN MONTH(checkinDate) IN (3,4,5) THEN 'Spring'
                        WHEN MONTH(checkinDate) IN (6,7,8) THEN 'Summer'
                        WHEN MONTH(checkinDate) IN (9,10,11) THEN 'Autumn'
                        ELSE 'Winter'
                    END
                ORDER BY avg_adr DESC
                """
                
                # Planned bookings for this listing
                planned_query = """
                SELECT 
                    COUNT(*) as planned_bookings,
                    AVG(amountGross/nights) as planned_adr,
                    MIN(checkinDate) as earliest_planned,
                    MAX(checkoutDate) as latest_planned
                FROM bnbplanned 
                WHERE listing = %s AND checkinDate >= CURDATE()
                """
                
                import pandas as pd
                monthly_df = pd.read_sql(monthly_query, conn, params=[listing])
                seasonal_df = pd.read_sql(seasonal_query, conn, params=[listing])
                planned_df = pd.read_sql(planned_query, conn, params=[listing])
                
                return {
                    "listing": listing,
                    "monthly_performance": monthly_df.to_dict('records'),
                    "seasonal_performance": seasonal_df.to_dict('records'),
                    "planned_bookings": planned_df.to_dict('records'),
                    "avg_adr_24m": float(monthly_df['avg_adr'].mean()) if not monthly_df.empty else 95.0,
                    "total_bookings_24m": int(monthly_df['bookings'].sum()) if not monthly_df.empty else 0,
                    "avg_los": float(monthly_df['avg_los'].mean()) if not monthly_df.empty else 2.1
                }
            else:
                # General market data
                monthly_query = """
                SELECT 
                    YEAR(checkinDate) as year,
                    MONTH(checkinDate) as month,
                    COUNT(*) as bookings,
                    AVG(amountGross/nights) as avg_adr
                FROM bnb 
                WHERE checkinDate >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                GROUP BY YEAR(checkinDate), MONTH(checkinDate)
                ORDER BY year, month
                """
                
                import pandas as pd
                monthly_df = pd.read_sql(monthly_query, conn)
                
                return {
                    "monthly_performance": monthly_df.to_dict('records'),
                    "avg_adr": float(monthly_df['avg_adr'].mean()) if not monthly_df.empty else 95.0
                }
            
        except Exception as e:
            print(f"Historical data error: {e}")
            return {"avg_adr": 95.0}
        finally:
            conn.close()
    
    def _get_last_year_adr(self, listing, target_date):
        """Get ADR for same date last year"""
        if not listing:
            return None
            
        conn = self.db.get_connection()
        
        try:
            # Look for bookings within ±7 days of same date last year
            last_year_date = target_date.replace(year=target_date.year - 1)
            
            query = """
            SELECT AVG(amountGross/nights) as avg_adr
            FROM bnb 
            WHERE listing = %s 
            AND checkinDate BETWEEN DATE_SUB(%s, INTERVAL 7 DAY) AND DATE_ADD(%s, INTERVAL 7 DAY)
            AND nights > 0
            """
            
            import pandas as pd
            result_df = pd.read_sql(query, conn, params=[listing, last_year_date, last_year_date])
            
            if not result_df.empty and result_df.iloc[0]['avg_adr'] is not None:
                return float(result_df.iloc[0]['avg_adr'])
            else:
                return None
                
        except Exception as e:
            print(f"Last year ADR lookup error: {e}")
            return None
        finally:
            conn.close()
    
    def _get_event_name_for_date(self, date):
        """Get event name for a specific date"""
        conn = self.db.get_connection()
        
        try:
            query = """
            SELECT event_name
            FROM pricing_events 
            WHERE %s BETWEEN start_date AND end_date
            AND active = TRUE
            ORDER BY uplift_percentage DESC
            LIMIT 1
            """
            
            import pandas as pd
            result_df = pd.read_sql(query, conn, params=[date])
            
            if not result_df.empty:
                return result_df.iloc[0]['event_name']
            
            return None
            
        except Exception as e:
            return None
        finally:
            conn.close()