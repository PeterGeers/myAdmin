import mysql.connector
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def run_query(cursor, query, description):
    print(f"\n{'='*60}")
    print(f"QUERY: {description}")
    print(f"{'='*60}")
    try:
        cursor.execute(query)
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        if results:
            # Print column headers
            if columns:
                print(" | ".join(f"{col:15}" for col in columns))
                print("-" * (len(columns) * 18))
            
            # Print results
            for row in results:
                print(" | ".join(f"{str(val):15}" for val in row))
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
    
    # STEP 1: Check table structure
    query1 = "SHOW CREATE TABLE bnb"
    run_query(cursor, query1, "Table structure for bnb")
    
    # STEP 2: Check for actual duplicate IDs (should be impossible)
    query2 = """
    SELECT 
        ID,
        COUNT(*) as count_same_id
    FROM bnb 
    GROUP BY ID 
    HAVING COUNT(*) > 1
    ORDER BY count_same_id DESC
    LIMIT 10
    """
    run_query(cursor, query2, "Records with duplicate IDs")
    
    # STEP 3: Detailed view of reservation code duplicates
    query3 = """
    SELECT 
        ID,
        reservationCode,
        checkinDate,
        guestName,
        COUNT(*) OVER (PARTITION BY reservationCode) as dup_count
    FROM bnb 
    WHERE reservationCode IS NOT NULL 
        AND reservationCode != ''
        AND reservationCode IN (
            SELECT reservationCode 
            FROM bnb 
            WHERE reservationCode IS NOT NULL AND reservationCode != ''
            GROUP BY reservationCode 
            HAVING COUNT(*) > 1
        )
    ORDER BY reservationCode, ID
    LIMIT 20
    """
    run_query(cursor, query3, "Detailed view of duplicate reservation codes")
    
    # STEP 4: Check for encoding issues
    query4 = """
    SELECT 
        reservationCode,
        HEX(reservationCode) as hex_value,
        LENGTH(reservationCode) as length_chars,
        CHAR_LENGTH(reservationCode) as length_unicode,
        COUNT(*) as count
    FROM bnb 
    WHERE reservationCode IS NOT NULL 
        AND reservationCode != ''
    GROUP BY reservationCode, HEX(reservationCode)
    HAVING COUNT(*) > 1
    ORDER BY count DESC
    LIMIT 10
    """
    run_query(cursor, query4, "Check for hidden characters in reservationCode")
    
    # STEP 5: Comprehensive duplicate analysis
    query5 = """
    SELECT 
        reservationCode,
        COUNT(*) as duplicate_count,
        GROUP_CONCAT(DISTINCT ID ORDER BY ID) as all_ids,
        GROUP_CONCAT(DISTINCT checkinDate ORDER BY checkinDate) as all_dates,
        GROUP_CONCAT(DISTINCT guestName ORDER BY guestName SEPARATOR ' | ') as all_guests
    FROM bnb 
    WHERE reservationCode IS NOT NULL 
        AND reservationCode != '' 
    GROUP BY reservationCode 
    HAVING COUNT(*) > 1 
    ORDER BY duplicate_count DESC 
    LIMIT 10
    """
    run_query(cursor, query5, "Comprehensive duplicate analysis")
    
    cursor.close()
    connection.close()
    print(f"\n{'='*60}")
    print("Investigation complete!")
    
except Exception as e:
    print(f"FAILED: Database connection failed: {e}")