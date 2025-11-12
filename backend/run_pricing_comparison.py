import sys
sys.path.append('src')
from database import DatabaseManager

db = DatabaseManager()

print("=== PRICING COMPARISON: RECOMMENDED vs LAST YEAR ADR (March-December) ===\n")

query = """
SELECT 
    listing_name,
    COUNT(*) as total_records,
    AVG(recommended_price) as avg_recommended_price,
    AVG(last_year_adr) as avg_last_year_adr,
    AVG(recommended_price) - AVG(last_year_adr) as price_difference,
    ROUND(((AVG(recommended_price) - AVG(last_year_adr)) / AVG(last_year_adr)) * 100, 2) as percentage_change,
    COUNT(CASE WHEN last_year_adr IS NOT NULL THEN 1 END) as records_with_last_year_data
FROM pricing_recommendations 
WHERE MONTH(price_date) BETWEEN 3 AND 12
GROUP BY listing_name
ORDER BY listing_name
"""

results = db.execute_query(query)

for row in results:
    listing = row['listing_name']
    total = row['total_records']
    avg_rec = row['avg_recommended_price'] or 0
    avg_last = row['avg_last_year_adr'] or 0
    diff = row['price_difference'] or 0
    pct_change = row['percentage_change'] or 0
    with_data = row['records_with_last_year_data'] or 0
    
    print(f"=== {listing} ===")
    print(f"   Total Records: {total}")
    print(f"   Avg Recommended: €{avg_rec:.2f}")
    print(f"   Avg Last Year:   €{avg_last:.2f}")
    print(f"   Difference:      €{diff:.2f}")
    print(f"   Change:          {pct_change:+.1f}%")
    print(f"   Data Coverage:   {with_data}/{total} records")
    print()