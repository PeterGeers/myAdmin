import sys
sys.path.append('src')
from database import DatabaseManager

db = DatabaseManager()

print("=== DEBUGGING PRICING LOGIC FOR 2026-03-22 ===\n")

# Get the specific record
record_query = """
SELECT * FROM pricing_recommendations 
WHERE listing_name = 'Red Studio' 
AND price_date = '2026-03-22'
"""

record = db.execute_query(record_query)
if record:
    r = record[0]
    print("RECORD DETAILS:")
    print(f"Date: {r['price_date']}")
    print(f"Recommended Price: €{r['recommended_price']}")
    print(f"Last Year ADR: €{r['last_year_adr']}")
    print(f"Is Weekend: {r['is_weekend']}")
    print(f"Event: {r['event_name']}")
    print(f"Event Uplift: {r['event_uplift']}%")
    print(f"AI Recommended: €{r['ai_recommended_adr']}")
    print(f"AI Historical: €{r['ai_historical_adr']}")
    print(f"AI Variance: {r['ai_variance']}")
    print(f"AI Reasoning: {r['ai_reasoning']}")

# Check Red Studio base rates
base_query = """
SELECT base_weekday_price, base_weekend_price 
FROM listings 
WHERE listing_name = 'Red Studio'
"""
base_rates = db.execute_query(base_query)
if base_rates:
    b = base_rates[0]
    print(f"\nBASE RATES:")
    print(f"Weekday: €{b['base_weekday_price']}")
    print(f"Weekend: €{b['base_weekend_price']}")

# Check March multiplier for Red Studio
print(f"\nPRICING CALCULATION BREAKDOWN:")
print(f"March 22, 2026 is a Sunday (weekend)")
print(f"Expected calculation:")
print(f"1. Base weekend price: €110")
print(f"2. March multiplier: ~0.857 (from previous output)")
print(f"3. Before event: €110 × 0.857 = €94.27")
print(f"4. Keukenhof +5% uplift: €94.27 × 1.05 = €99.00")
print(f"5. But actual result: €76.49")
print(f"\nSOMETHING IS WRONG - investigating...")

# Check if AI is overriding the calculation
if record and record[0]['ai_recommended_adr']:
    ai_rec = float(record[0]['ai_recommended_adr'])
    print(f"\nAI OVERRIDE DETECTED:")
    print(f"AI recommended: €{ai_rec}")
    print(f"Final price: €{record[0]['recommended_price']}")
    if abs(ai_rec - float(record[0]['recommended_price'])) < 1:
        print("✓ AI recommendation is being used as final price")
    else:
        print("✗ AI recommendation differs from final price")
else:
    print(f"\nNO AI OVERRIDE - using rule-based calculation")
    print(f"This suggests a bug in the monthly multiplier or event logic")