"""
Quick test script to verify country report query
Run: python test_country_query.py
"""

from database import DatabaseManager

def test_country_query():
    db = DatabaseManager(test_mode=False)
    connection = db.get_connection()
    cursor = connection.cursor()
    
    # Test with a sample administration (adjust as needed)
    test_admin = ['VW']  # Replace with your actual administration code
    placeholders = ', '.join(['%s'] * len(test_admin))
    
    query = f"""
        SELECT 
            country, 
            countryName, 
            countryNameNL,
            countryRegion,
            COUNT(*) as bookings
        FROM vw_bnb_total 
        WHERE country IS NOT NULL AND administration IN ({placeholders})
        GROUP BY country, countryName, countryNameNL, countryRegion
        ORDER BY COUNT(*) DESC
    """
    
    print("Executing query:")
    print(query)
    print(f"Parameters: {test_admin}")
    print("\n" + "="*80 + "\n")
    
    cursor.execute(query, test_admin)
    results = cursor.fetchall()
    
    print(f"Found {len(results)} countries\n")
    print(f"{'Country':<8} {'Name':<25} {'Dutch Name':<25} {'Region':<20} {'Bookings':>10}")
    print("-" * 100)
    
    for row in results:
        country, name, name_nl, region, bookings = row
        print(f"{country:<8} {name:<25} {name_nl or 'N/A':<25} {region or 'N/A':<20} {bookings:>10}")
    
    cursor.close()
    connection.close()
    
    print("\n" + "="*80)
    print(f"Total countries: {len(results)}")
    if results:
        print(f"Top country: {results[0][1]} ({results[0][0]}) with {results[0][4]} bookings")

if __name__ == '__main__':
    test_country_query()
