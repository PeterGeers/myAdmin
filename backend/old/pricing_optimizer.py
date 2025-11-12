import requests
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import DatabaseManager

load_dotenv()

class PricingOptimizer:
    def __init__(self, test_mode=False):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.db = DatabaseManager(test_mode=test_mode)
        
    def generate_pricing_recommendations(self, months=15):
        """Generate 15-month pricing recommendations using AI and historical data"""
        
        # Get historical data and events
        historical_data = self._get_historical_data()
        events_data = self._get_events_data()
        
        # Create AI prompt with historical context
        prompt = f"""
Generate dynamic pricing recommendations for a 2-person short-stay studio in Hoofddorp with these features:
- Heating, AC, free parking, kitchenette, private entrance
- Target: Maximize RevPAR through AI optimization

Historical Performance Data:
{json.dumps(historical_data, indent=2)}

Precise Event Dates with Uplifts:
{json.dumps(events_data, indent=2)}

Generate pricing for next {months} months considering:
1. EXACT event dates (not broad months) - apply uplifts only during actual event periods
2. Weekend vs weekday (weekend +20-30% premium)
4. Length of stay discounts: 7+ nights (-10%), 14+ nights (-15%)
5. Minimum stay rules: 1 nights weekend, 1 night weekday

Return JSON format:
{{
  "recommendations": [
    {{
      "month": "2025-02",
      "weekday_price": 85.00,
      "weekend_price": 110.00,
      "occupancy_target": 95,
      "event_uplift": 0,
      "confidence_range": "±10%",
      "reasoning": "Winter low season, focus on occupancy"
    }}
  ],
  "summary": {{
    "avg_weekday": 95.00,
    "avg_weekend": 125.00,
    "projected_revpar": 180.00,
    "key_insights": ["Seasonal adjustments", "Event premiums"]
  }}
}}
"""

        try:
            # Try GPT-3.5 first, then Kimi fallback
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
                            "max_tokens": 2000
                        },
                        timeout=15
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result['choices'][0]['message']['content'].strip()
                        
                        # Extract JSON
                        if content.startswith('```json'):
                            content = content.replace('```json', '').replace('```', '').strip()
                        
                        pricing_data = json.loads(content)
                        print(f"Pricing generated using {model}")
                        return pricing_data
                        
                except Exception as e:
                    print(f"{model} failed: {e}")
                    continue
            
            # Fallback to rule-based pricing
            return self._generate_fallback_pricing(months)
            
        except Exception as e:
            print(f"AI pricing failed: {e}")
            return self._generate_fallback_pricing(months)
    
    def _get_historical_data(self):
        """Get historical BNB performance data"""
        conn = self.db.get_connection()
        
        try:
            # Monthly performance last 12 months
            monthly_query = """
            SELECT 
                YEAR(checkinDate) as year,
                MONTH(checkinDate) as month,
                COUNT(*) as bookings,
                AVG(amountGross/nights) as avg_adr,
                SUM(nights) as total_nights
            FROM bnb 
            WHERE checkinDate >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY YEAR(checkinDate), MONTH(checkinDate)
            ORDER BY year, month
            """
            
            # Seasonal patterns
            seasonal_query = """
            SELECT 
                CASE 
                    WHEN MONTH(checkinDate) IN (3,4,5) THEN 'Spring'
                    WHEN MONTH(checkinDate) IN (6,7,8) THEN 'Summer'
                    WHEN MONTH(checkinDate) IN (9,10,11) THEN 'Autumn'
                    ELSE 'Winter'
                END as season,
                AVG(amountGross/nights) as avg_adr,
                COUNT(*) as bookings
            FROM bnb 
            WHERE checkinDate >= '2023-01-01'
            GROUP BY 
                CASE 
                    WHEN MONTH(checkinDate) IN (3,4,5) THEN 'Spring'
                    WHEN MONTH(checkinDate) IN (6,7,8) THEN 'Summer'
                    WHEN MONTH(checkinDate) IN (9,10,11) THEN 'Autumn'
                    ELSE 'Winter'
                END
            """
            
            import pandas as pd
            monthly_df = pd.read_sql(monthly_query, conn)
            seasonal_df = pd.read_sql(seasonal_query, conn)
            
            return {
                "monthly_performance": monthly_df.to_dict('records'),
                "seasonal_patterns": seasonal_df.to_dict('records'),
                "avg_adr": float(monthly_df['avg_adr'].mean()) if not monthly_df.empty else 95.0,
                "avg_occupancy": 70  # Estimated from bookings
            }
            
        except Exception as e:
            print(f"Historical data error: {e}")
            return {"avg_adr": 95.0, "avg_occupancy": 70}
        finally:
            conn.close()
    
    def _get_events_data(self):
        """Get precise event dates and uplifts from database"""
        conn = self.db.get_connection()
        
        try:
            events_query = """
            SELECT event_name, start_date, end_date, uplift_percentage, event_type
            FROM pricing_events 
            WHERE active = TRUE AND end_date >= CURDATE()
            ORDER BY start_date
            """
            
            import pandas as pd
            events_df = pd.read_sql(events_query, conn)
            
            # Convert dates to strings for JSON serialization
            events_list = []
            for _, row in events_df.iterrows():
                events_list.append({
                    "event_name": row['event_name'],
                    "start_date": str(row['start_date']),
                    "end_date": str(row['end_date']),
                    "uplift_percentage": int(row['uplift_percentage']),
                    "event_type": row['event_type']
                })
            
            return {
                "events": events_list,
                "total_events": len(events_list)
            }
            
        except Exception as e:
            print(f"Events data error: {e}")
            return {"events": [], "total_events": 0}
        finally:
            conn.close()
    
    def _generate_fallback_pricing(self, months):
        """Rule-based fallback pricing when AI fails"""
        base_weekday = 85
        base_weekend = 110
        recommendations = []
        
        start_date = datetime.now().replace(day=1)
        
        for i in range(months):
            current_date = start_date + timedelta(days=32*i)
            month_str = current_date.strftime("%Y-%m")
            month_num = current_date.month
            
            # Seasonal adjustments
            if month_num in [3,4,5]:  # Spring/Keukenhof
                weekday, weekend = base_weekday * 1.2, base_weekend * 1.3
                event_uplift = 20
            elif month_num in [6,7,8]:  # Summer/F1
                weekday, weekend = base_weekday * 1.3, base_weekend * 1.4
                event_uplift = 30 if month_num == 8 else 15
            elif month_num in [9,10,11]:  # Autumn/ADE
                weekday, weekend = base_weekday * 1.1, base_weekend * 1.2
                event_uplift = 25 if month_num == 10 else 10
            else:  # Winter
                weekday, weekend = base_weekday * 0.9, base_weekend * 0.95
                event_uplift = 0
            
            recommendations.append({
                "month": month_str,
                "weekday_price": round(weekday, 2),
                "weekend_price": round(weekend, 2),
                "occupancy_target": 75,
                "event_uplift": event_uplift,
                "confidence_range": "±15%",
                "reasoning": f"Rule-based pricing for {current_date.strftime('%B')}"
            })
        
        return {
            "recommendations": recommendations,
            "summary": {
                "avg_weekday": round(sum(r["weekday_price"] for r in recommendations) / len(recommendations), 2),
                "avg_weekend": round(sum(r["weekend_price"] for r in recommendations) / len(recommendations), 2),
                "projected_revpar": 180.0,
                "key_insights": ["Seasonal adjustments applied", "Event premiums included"]
            }
        }