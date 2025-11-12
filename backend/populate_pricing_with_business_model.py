import sys
sys.path.append('src')
from business_pricing_model import BusinessPricingModel
from database import DatabaseManager
from datetime import datetime, date, timedelta

def populate_pricing_recommendations():
    """Fill pricing_recommendations table using BusinessPricingModel"""
    
    model = BusinessPricingModel()
    db = DatabaseManager()
    
    listings = ['Red Studio', 'Green Studio', 'Child Friendly']
    start_date = date.today()
    days = 420  # 14 months
    
    for listing in listings:
        print(f"Generating pricing for {listing}...")
        
        # Clear existing data
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pricing_recommendations WHERE listing_name = %s", [listing])
        
        # Generate daily prices
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            
            # Get business price
            result = model.calculate_business_price(listing, current_date)
            
            # Insert into database
            insert_sql = """
            INSERT INTO pricing_recommendations 
            (listing_name, price_date, recommended_price, is_weekend, event_uplift, event_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            is_weekend = current_date.weekday() in [4, 5]  # Fri, Sat
            
            cursor.execute(insert_sql, [
                listing,
                current_date,
                result['final_price'],
                is_weekend,
                int((result['event_mult'] - 1) * 100),  # Convert to percentage
                'Business Model'  # Placeholder
            ])
        
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Saved 420 pricing recommendations for {listing}")

if __name__ == "__main__":
    populate_pricing_recommendations()