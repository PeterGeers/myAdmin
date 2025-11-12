import sys
sys.path.append('src')
from database import DatabaseManager

db = DatabaseManager()

print("=== PRICING FACTORS ANALYSIS ===\n")

# 1. Check listing-specific multipliers and base rates
print("1. LISTING CONFIGURATION:")
config_query = """
SELECT listing_name, base_weekday_price, base_weekend_price, property_premium_factor, active
FROM listings 
WHERE active = TRUE
ORDER BY listing_name
"""
configs = db.execute_query(config_query)
for config in configs:
    listing = config['listing_name']
    weekday = config['base_weekday_price']
    weekend = config['base_weekend_price'] 
    multiplier = config['property_premium_factor']
    print(f"{listing}: €{weekday} weekday, €{weekend} weekend, {multiplier}x multiplier")

print("\n2. HISTORICAL ADR BY LISTING (24 months):")
historical_query = """
SELECT 
    listing,
    COUNT(*) as bookings,
    AVG(amountGross/nights) as avg_adr,
    MIN(checkinDate) as earliest,
    MAX(checkinDate) as latest
FROM bnb 
WHERE checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
AND nights > 0
GROUP BY listing
ORDER BY listing
"""
historical = db.execute_query(historical_query)
for hist in historical:
    listing = hist['listing']
    bookings = hist['bookings']
    avg_adr = hist['avg_adr'] or 0
    earliest = hist['earliest']
    latest = hist['latest']
    print(f"{listing}: {bookings} bookings, €{avg_adr:.2f} avg ADR ({earliest} to {latest})")

print("\n3. MONTHLY PERFORMANCE PATTERNS:")
monthly_query = """
SELECT 
    listing,
    MONTH(checkinDate) as month,
    COUNT(*) as bookings,
    AVG(amountGross/nights) as avg_adr
FROM bnb 
WHERE checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
AND MONTH(checkinDate) BETWEEN 3 AND 12
AND nights > 0
GROUP BY listing, MONTH(checkinDate)
ORDER BY listing, month
"""
monthly = db.execute_query(monthly_query)
current_listing = None
for row in monthly:
    listing = row['listing']
    month = row['month']
    bookings = row['bookings']
    avg_adr = row['avg_adr'] or 0
    
    if listing != current_listing:
        print(f"\n{listing} Monthly ADR:")
        current_listing = listing
    
    month_names = ['', '', '', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    print(f"  {month_names[month]}: €{avg_adr:.2f} ({bookings} bookings)")

print("\n4. AI RECOMMENDATION PATTERNS:")
ai_query = """
SELECT 
    listing_name,
    AVG(ai_recommended_adr) as avg_ai_rec,
    AVG(ai_historical_adr) as avg_ai_hist,
    COUNT(CASE WHEN ai_recommended_adr IS NOT NULL THEN 1 END) as ai_records
FROM pricing_recommendations
WHERE MONTH(price_date) BETWEEN 3 AND 12
GROUP BY listing_name
ORDER BY listing_name
"""
ai_data = db.execute_query(ai_query)
for ai in ai_data:
    listing = ai['listing_name']
    ai_rec = ai['avg_ai_rec'] or 0
    ai_hist = ai['avg_ai_hist'] or 0
    ai_records = ai['ai_records'] or 0
    print(f"{listing}: AI avg €{ai_rec:.2f}, AI historical €{ai_hist:.2f} ({ai_records} AI records)")