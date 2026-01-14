import mysql.connector
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def run_query(cursor, query, description):
    print(f"\n{'='*60}")
    print(f"INVESTIGATION: {description}")
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
    print("SUCCESS: Connected to database for duplicate cause investigation")
    
    # INVESTIGATION 1: Check when duplicates were created (by looking at backup table)
    query1 = """
    SELECT 
        sourceFile,
        COUNT(*) as duplicate_count,
        MIN(id) as first_id,
        MAX(id) as last_id,
        GROUP_CONCAT(DISTINCT id ORDER BY id) as all_ids
    FROM bnb_backup_duplicates
    WHERE reservationCode IN (
        SELECT reservationCode 
        FROM bnb_backup_duplicates 
        WHERE reservationCode IS NOT NULL AND reservationCode != ''
        GROUP BY reservationCode 
        HAVING COUNT(*) > 1
    )
    GROUP BY sourceFile, reservationCode
    HAVING COUNT(*) > 1
    ORDER BY duplicate_count DESC, sourceFile
    LIMIT 20
    """
    run_query(cursor, query1, "Source files that created duplicates")
    
    # INVESTIGATION 2: Check ID patterns in duplicates
    query2 = """
    SELECT 
        reservationCode,
        GROUP_CONCAT(id ORDER BY id) as duplicate_ids,
        MAX(id) - MIN(id) as id_gap,
        COUNT(*) as duplicate_count
    FROM bnb_backup_duplicates
    WHERE reservationCode IN (
        SELECT reservationCode 
        FROM bnb_backup_duplicates 
        WHERE reservationCode IS NOT NULL AND reservationCode != ''
        GROUP BY reservationCode 
        HAVING COUNT(*) > 1
    )
    GROUP BY reservationCode
    ORDER BY id_gap DESC
    LIMIT 15
    """
    run_query(cursor, query2, "ID patterns in duplicate records")
    
    # INVESTIGATION 3: Check if duplicates came from different source files
    query3 = """
    SELECT 
        reservationCode,
        COUNT(DISTINCT sourceFile) as different_source_files,
        GROUP_CONCAT(DISTINCT sourceFile) as source_files,
        COUNT(*) as total_duplicates
    FROM bnb_backup_duplicates
    WHERE reservationCode IN (
        SELECT reservationCode 
        FROM bnb_backup_duplicates 
        WHERE reservationCode IS NOT NULL AND reservationCode != ''
        GROUP BY reservationCode 
        HAVING COUNT(*) > 1
    )
    GROUP BY reservationCode
    HAVING COUNT(DISTINCT sourceFile) > 1
    ORDER BY different_source_files DESC
    LIMIT 10
    """
    run_query(cursor, query3, "Duplicates from different source files")
    
    # INVESTIGATION 4: Check date patterns of duplicate creation
    query4 = """
    SELECT 
        SUBSTRING(sourceFile, 1, 20) as source_pattern,
        COUNT(*) as records,
        COUNT(*) / 2 as estimated_duplicates,
        MIN(id) as min_id,
        MAX(id) as max_id
    FROM bnb_backup_duplicates
    WHERE sourceFile IS NOT NULL
    GROUP BY SUBSTRING(sourceFile, 1, 20)
    HAVING COUNT(*) > 10
    ORDER BY records DESC
    LIMIT 15
    """
    run_query(cursor, query4, "Source file patterns and record counts")
    
    # INVESTIGATION 5: Check if there's a pattern in the ID sequence
    query5 = """
    SELECT 
        id,
        reservationCode,
        sourceFile,
        checkinDate,
        CASE 
            WHEN LAG(reservationCode) OVER (ORDER BY id) = reservationCode THEN 'CONSECUTIVE_DUPLICATE'
            ELSE 'FIRST_OCCURRENCE'
        END as duplicate_type
    FROM bnb_backup_duplicates
    WHERE reservationCode IN (
        SELECT reservationCode 
        FROM bnb_backup_duplicates 
        WHERE reservationCode IS NOT NULL AND reservationCode != ''
        GROUP BY reservationCode 
        HAVING COUNT(*) > 1
    )
    ORDER BY id
    LIMIT 30
    """
    run_query(cursor, query5, "Sequential duplicate pattern analysis")
    
    # INVESTIGATION 6: Check for batch import patterns
    query6 = """
    SELECT 
        FLOOR(id / 100) * 100 as id_batch,
        COUNT(*) as records_in_batch,
        COUNT(DISTINCT reservationCode) as unique_codes_in_batch,
        COUNT(*) - COUNT(DISTINCT reservationCode) as duplicates_in_batch
    FROM bnb_backup_duplicates
    WHERE id BETWEEN 4000 AND 5000
    GROUP BY FLOOR(id / 100)
    HAVING duplicates_in_batch > 0
    ORDER BY id_batch
    """
    run_query(cursor, query6, "Batch import patterns around duplicate IDs")
    
    cursor.close()
    connection.close()
    
    print(f"\n{'='*80}")
    print("🔍 DUPLICATE CAUSE ANALYSIS COMPLETE")
    print(f"{'='*80}")
    print("Key findings to look for:")
    print("• Same source files creating duplicates = Re-import issue")
    print("• Different source files = Data processing bug")
    print("• Sequential IDs = Batch processing problem")
    print("• Large ID gaps = Multiple import sessions")
    print(f"{'='*80}")
    
except Exception as e:
    print(f"FAILED: Database connection failed: {e}")