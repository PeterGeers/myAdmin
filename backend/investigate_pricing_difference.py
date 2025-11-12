import sys
sys.path.append('src')
from database import DatabaseManager

db = DatabaseManager()

print("=== INVESTIGATING GREEN vs RED STUDIO PRICING DIFFERENCE ===\n")

# Compare actual historical ADR patterns
print("1. ACTUAL HISTORICAL ADR COMPARISON (March-December):")
comparison_query = """
SELECT 
    listing,
    MONTH(checkinDate) as month,
    AVG(amountGross/nights) as avg_adr,
    COUNT(*) as bookings
FROM bnb 
WHERE listing IN ('Green Studio', 'Red Studio')
AND MONTH(checkinDate) BETWEEN 3 AND 12
AND checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
AND nights > 0
GROUP BY listing, MONTH(checkinDate)
ORDER BY month, listing
"""

results = db.execute_query(comparison_query)
month_names = ['', '', '', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

print("Month    | Green Studio | Red Studio   | Difference")
print("---------|--------------|--------------|------------")

green_data = {}
red_data = {}

for row in results:
    listing = row['listing']
    month = row['month']
    avg_adr = row['avg_adr'] or 0
    bookings = row['bookings']
    
    if listing == 'Green Studio':
        green_data[month] = avg_adr
    else:
        red_data[month] = avg_adr

for month in range(3, 13):
    green_adr = green_data.get(month, 0)
    red_adr = red_data.get(month, 0)
    diff = green_adr - red_adr
    print(f"{month_names[month]:<8} | €{green_adr:>9.2f} | €{red_adr:>9.2f} | €{diff:>+8.2f}")

print("\n2. LAST YEAR ADR DATA AVAILABILITY:")
last_year_query = """
SELECT 
    listing_name,
    COUNT(*) as total_records,
    COUNT(CASE WHEN last_year_adr IS NOT NULL THEN 1 END) as with_last_year,
    AVG(last_year_adr) as avg_last_year_adr
FROM pricing_recommendations
WHERE listing_name IN ('Green Studio', 'Red Studio')
AND MONTH(price_date) BETWEEN 3 AND 12
GROUP BY listing_name
"""

last_year_data = db.execute_query(last_year_query)
for row in last_year_data:
    listing = row['listing_name']
    total = row['total_records']
    with_data = row['with_last_year']
    avg_last = row['avg_last_year_adr'] or 0
    coverage = (with_data / total * 100) if total > 0 else 0
    print(f"{listing}: {with_data}/{total} records ({coverage:.1f}%), avg last year: €{avg_last:.2f}")

print("\n3. MONTHLY MULTIPLIER IMPACT:")
multiplier_query = """
SELECT 
    listing_name,
    MONTH(price_date) as month,
    AVG(recommended_price) as avg_recommended,
    COUNT(*) as records
FROM pricing_recommendations
WHERE listing_name IN ('Green Studio', 'Red Studio')
AND MONTH(price_date) BETWEEN 3 AND 12
GROUP BY listing_name, MONTH(price_date)
ORDER BY month, listing_name
"""

multiplier_data = db.execute_query(multiplier_query)
print("Month    | Green Rec    | Red Rec      | Difference")
print("---------|--------------|--------------|------------")

green_rec = {}
red_rec = {}

for row in multiplier_data:
    listing = row['listing_name']
    month = row['month']
    avg_rec = row['avg_recommended'] or 0
    
    if listing == 'Green Studio':
        green_rec[month] = avg_rec
    else:
        red_rec[month] = avg_rec

for month in range(3, 13):
    green_r = green_rec.get(month, 0)
    red_r = red_rec.get(month, 0)
    diff = green_r - red_r
    print(f"{month_names[month]:<8} | €{green_r:>9.2f} | €{red_r:>9.2f} | €{diff:>+8.2f}")