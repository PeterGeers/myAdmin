import mysql.connector
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def run_query(cursor, query, description):
    print(f"\n{'='*60}")
    print(f"ANALYSIS: {description}")
    print(f"{'='*60}")
    try:
        cursor.execute(query)
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        if results:
            # Print column headers
            if columns:
                print(" | ".join(f"{col:20}" for col in columns))
                print("-" * (len(columns) * 23))
            
            # Print results
            for row in results:
                print(" | ".join(f"{str(val):20}" for val in row))
            print(f"\nTotal rows: {len(results)}")
        else:
            print("No results returned")
            
    except Exception as e:
        print(f"ERROR: {e}")

try:
    # Connect to database
    connection = mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        port=int(os.getenv('DB_PORT', 3306))
    )
    
    cursor = connection.cursor()
    print("SUCCESS: Connected to database")
    
    # Check what tables exist
    query0 = "SHOW TABLES LIKE '%bnb%'"
    run_query(cursor, query0, "Available BNB tables")
    
    # ANALYSIS 1: Check current data distribution by ID ranges
    query1 = """
    SELECT 
        CASE 
            WHEN id < 4000 THEN 'OLD (< 4000)'
            WHEN id < 5000 THEN 'RANGE 4000-4999'
            WHEN id < 6000 THEN 'RANGE 5000-5999'
            WHEN id < 7000 THEN 'RANGE 6000-6999'
            WHEN id < 8000 THEN 'RANGE 7000-7999'
            ELSE 'NEWEST (8000+)'
        END as id_range,
        COUNT(*) as records,
        MIN(id) as min_id,
        MAX(id) as max_id
    FROM bnb
    GROUP BY 
        CASE 
            WHEN id < 4000 THEN 'OLD (< 4000)'
            WHEN id < 5000 THEN 'RANGE 4000-4999'
            WHEN id < 6000 THEN 'RANGE 5000-5999'
            WHEN id < 7000 THEN 'RANGE 6000-6999'
            WHEN id < 8000 THEN 'RANGE 7000-7999'
            ELSE 'NEWEST (8000+)'
        END
    ORDER BY min_id
    """
    run_query(cursor, query1, "Current data distribution by ID ranges")
    
    # ANALYSIS 2: Check recent source files and their patterns
    query2 = """
    SELECT 
        sourceFile,
        COUNT(*) as records,
        MIN(id) as min_id,
        MAX(id) as max_id,
        MIN(checkinDate) as earliest_checkin,
        MAX(checkinDate) as latest_checkin
    FROM bnb
    WHERE id > 6000
    AND sourceFile IS NOT NULL
    GROUP BY sourceFile
    ORDER BY max_id DESC
    LIMIT 15
    """
    run_query(cursor, query2, "Recent source files (ID > 6000)")
    
    # ANALYSIS 3: Check if there are any remaining duplicates (should be 0)
    query3 = """
    SELECT 
        reservationCode,
        COUNT(*) as count
    FROM bnb
    WHERE reservationCode IS NOT NULL AND reservationCode != ''
    GROUP BY reservationCode
    HAVING COUNT(*) > 1
    LIMIT 10
    """
    run_query(cursor, query3, "Any remaining duplicates (should be empty)")
    
    # ANALYSIS 4: Check the most recent records
    query4 = """
    SELECT 
        id,
        sourceFile,
        channel,
        reservationCode,
        checkinDate,
        amountGross
    FROM bnb
    ORDER BY id DESC
    LIMIT 15
    """
    run_query(cursor, query4, "Most recent records in clean table")
    
    # ANALYSIS 5: Check data consistency - should be 1:1 ratio
    query5 = """
    SELECT 
        'CURRENT TABLE STATS' as description,
        COUNT(*) as total_records,
        COUNT(DISTINCT reservationCode) as unique_reservation_codes,
        COUNT(*) - COUNT(DISTINCT reservationCode) as should_be_zero
    FROM bnb
    WHERE reservationCode IS NOT NULL AND reservationCode != ''
    """
    run_query(cursor, query5, "Data consistency check")
    
    # ANALYSIS 6: Check recent months data
    query6 = """
    SELECT 
        year,
        m as month,
        COUNT(*) as records,
        ROUND(SUM(amountGross), 2) as total_gross
    FROM bnb
    WHERE year >= 2024
    GROUP BY year, m
    ORDER BY year DESC, m DESC
    LIMIT 15
    """
    run_query(cursor, query6, "Recent months data (2024+)")
    
    cursor.close()
    connection.close()
    
    print(f"\n{'='*80}")
    print("📊 RECENT DATA ANALYSIS")
    print(f"{'='*80}")
    print("Your observation is correct - if the figures look normal now,")
    print("it suggests the duplication was a recent issue that has been fixed.")
    print("The clean data should show:")
    print("• No duplicate reservation codes")
    print("• Normal revenue patterns")
    print("• Consistent record counts")
    print(f"{'='*80}")
    
except Exception as e:
    print(f"FAILED: Database connection failed: {e}")