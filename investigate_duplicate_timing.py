import mysql.connector
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def run_query(cursor, query, description):
    print(f"\n{'='*60}")
    print(f"TIMING ANALYSIS: {description}")
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
    print("SUCCESS: Connected to database for timing analysis")
    
    # ANALYSIS 1: Check the highest ID ranges to see when duplicates were created
    query1 = """
    SELECT 
        FLOOR(id / 500) * 500 as id_range_start,
        FLOOR(id / 500) * 500 + 499 as id_range_end,
        COUNT(*) as total_records,
        COUNT(DISTINCT reservationCode) as unique_codes,
        COUNT(*) - COUNT(DISTINCT reservationCode) as duplicates_in_range,
        MIN(id) as min_id,
        MAX(id) as max_id
    FROM bnb_backup_duplicates
    WHERE id > 4000
    GROUP BY FLOOR(id / 500)
    HAVING duplicates_in_range > 0
    ORDER BY id_range_start DESC
    LIMIT 20
    """
    run_query(cursor, query1, "ID ranges with duplicates (recent first)")
    
    # ANALYSIS 2: Check the current maximum ID in clean table vs backup
    query2 = """
    SELECT 
        'BACKUP (with duplicates)' as table_name,
        MAX(id) as max_id,
        COUNT(*) as total_records
    FROM bnb_backup_duplicates
    
    UNION ALL
    
    SELECT 
        'CURRENT (clean)' as table_name,
        MAX(id) as max_id,
        COUNT(*) as total_records
    FROM bnb
    """
    run_query(cursor, query2, "Maximum IDs comparison")
    
    # ANALYSIS 3: Look at recent source files that had duplicates
    query3 = """
    SELECT 
        sourceFile,
        COUNT(*) as total_records,
        COUNT(DISTINCT reservationCode) as unique_codes,
        COUNT(*) - COUNT(DISTINCT reservationCode) as duplicates,
        MIN(id) as min_id,
        MAX(id) as max_id,
        CASE 
            WHEN MAX(id) > 7000 THEN 'VERY_RECENT'
            WHEN MAX(id) > 6000 THEN 'RECENT'
            WHEN MAX(id) > 5000 THEN 'OLDER'
            ELSE 'OLD'
        END as recency
    FROM bnb_backup_duplicates
    WHERE sourceFile IS NOT NULL
    GROUP BY sourceFile
    HAVING duplicates > 0
    ORDER BY max_id DESC
    LIMIT 15
    """
    run_query(cursor, query3, "Recent source files with duplicates")
    
    # ANALYSIS 4: Check if there are any patterns in the most recent IDs
    query4 = """
    SELECT 
        id,
        reservationCode,
        sourceFile,
        checkinDate,
        'DUPLICATE' as status
    FROM bnb_backup_duplicates
    WHERE id > 7000
    AND reservationCode IN (
        SELECT reservationCode 
        FROM bnb_backup_duplicates 
        WHERE id > 7000
        GROUP BY reservationCode 
        HAVING COUNT(*) > 1
    )
    ORDER BY id DESC
    LIMIT 20
    """
    run_query(cursor, query4, "Most recent duplicates (ID > 7000)")
    
    # ANALYSIS 5: Check when the duplication pattern started
    query5 = """
    SELECT 
        FLOOR(id / 100) * 100 as id_batch,
        COUNT(*) as records,
        COUNT(DISTINCT reservationCode) as unique_codes,
        ROUND((COUNT(*) - COUNT(DISTINCT reservationCode)) / COUNT(*) * 100, 1) as duplicate_percentage
    FROM bnb_backup_duplicates
    WHERE id BETWEEN 4000 AND 8000
    GROUP BY FLOOR(id / 100)
    HAVING duplicate_percentage > 0
    ORDER BY id_batch
    """
    run_query(cursor, query5, "Duplication pattern progression")
    
    # ANALYSIS 6: Check if recent data in current table looks normal
    query6 = """
    SELECT 
        FLOOR(id / 100) * 100 as id_batch,
        COUNT(*) as records,
        COUNT(DISTINCT reservationCode) as unique_codes,
        MIN(id) as min_id,
        MAX(id) as max_id
    FROM bnb
    WHERE id > 7000
    GROUP BY FLOOR(id / 100)
    ORDER BY id_batch DESC
    LIMIT 10
    """
    run_query(cursor, query6, "Recent data in clean table (should be normal)")
    
    cursor.close()
    connection.close()
    
    print(f"\n{'='*80}")
    print("⏰ TIMING ANALYSIS SUMMARY")
    print(f"{'='*80}")
    print("Key insights:")
    print("• Higher ID ranges = More recent data")
    print("• If duplicates stop at certain ID = When problem was fixed")
    print("• Source file dates can indicate when duplication started")
    print("• Current table should show normal patterns")
    print(f"{'='*80}")
    
except Exception as e:
    print(f"FAILED: Database connection failed: {e}")