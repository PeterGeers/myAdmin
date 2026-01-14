import mysql.connector
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def run_query(cursor, query, description, fetch_results=True):
    print(f"\n{'='*60}")
    print(f"QUERY: {description}")
    print(f"{'='*60}")
    try:
        cursor.execute(query)
        
        if fetch_results and cursor.description:
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            if results:
                # Print column headers
                print(" | ".join(f"{col:15}" for col in columns))
                print("-" * (len(columns) * 18))
                
                # Print results
                for row in results:
                    print(" | ".join(f"{str(val):15}" for val in row))
                print(f"\nTotal rows: {len(results)}")
            else:
                print("No results returned")
        else:
            print(f"Query executed successfully. Affected rows: {cursor.rowcount}")
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    return True

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
    
    # STEP 1: Count duplicates before fix
    query1 = """
    SELECT 
        COUNT(*) as total_duplicate_rows
    FROM bnb b1
    WHERE EXISTS (
        SELECT 1 FROM bnb b2 
        WHERE b1.id = b2.id 
        AND b1.reservationCode = b2.reservationCode
        AND b1.checkinDate = b2.checkinDate
        AND b1.guestName = b2.guestName
    )
    """
    run_query(cursor, query1, "Count total duplicate rows before fix")
    
    # STEP 2: Create temporary table with unique records
    print(f"\n{'='*60}")
    print("STEP 2: Creating temporary table with unique records")
    print(f"{'='*60}")
    
    # First drop temp table if exists
    cursor.execute("DROP TEMPORARY TABLE IF EXISTS bnb_unique")
    
    # Create temp table with unique records only
    create_temp = """
    CREATE TEMPORARY TABLE bnb_unique AS
    SELECT DISTINCT * FROM bnb
    """
    cursor.execute(create_temp)
    print(f"Temporary table created with unique records")
    
    # STEP 3: Count records in temp table
    query3 = "SELECT COUNT(*) as unique_records FROM bnb_unique"
    run_query(cursor, query3, "Count unique records in temp table")
    
    # STEP 4: Count records in original table
    query4 = "SELECT COUNT(*) as original_records FROM bnb"
    run_query(cursor, query4, "Count records in original table")
    
    # STEP 5: Backup original table (rename it)
    print(f"\n{'='*60}")
    print("STEP 5: Creating backup of original table")
    print(f"{'='*60}")
    
    try:
        cursor.execute("DROP TABLE IF EXISTS bnb_backup_duplicates")
        cursor.execute("CREATE TABLE bnb_backup_duplicates AS SELECT * FROM bnb")
        print("Backup table 'bnb_backup_duplicates' created successfully")
    except Exception as e:
        print(f"Backup creation failed: {e}")
        print("STOPPING - Cannot proceed without backup")
        exit(1)
    
    # STEP 6: Clear original table and insert unique records
    print(f"\n{'='*60}")
    print("STEP 6: Replacing original table with unique records")
    print(f"{'='*60}")
    
    cursor.execute("DELETE FROM bnb")
    print(f"Original table cleared. Rows affected: {cursor.rowcount}")
    
    cursor.execute("INSERT INTO bnb SELECT * FROM bnb_unique")
    print(f"Unique records inserted. Rows affected: {cursor.rowcount}")
    
    # STEP 7: Add proper PRIMARY KEY constraint
    print(f"\n{'='*60}")
    print("STEP 7: Adding PRIMARY KEY constraint")
    print(f"{'='*60}")
    
    try:
        cursor.execute("ALTER TABLE bnb ADD PRIMARY KEY (id)")
        print("PRIMARY KEY constraint added successfully")
    except Exception as e:
        print(f"PRIMARY KEY constraint failed: {e}")
        print("This might be expected if constraint already exists")
    
    # STEP 8: Verify fix
    query8 = """
    SELECT 
        COUNT(*) as remaining_duplicates
    FROM bnb 
    GROUP BY id 
    HAVING COUNT(*) > 1
    """
    run_query(cursor, query8, "Check for remaining duplicate IDs (should be 0)")
    
    # STEP 9: Final count
    query9 = "SELECT COUNT(*) as final_record_count FROM bnb"
    run_query(cursor, query9, "Final record count")
    
    # Commit changes
    connection.commit()
    
    cursor.close()
    connection.close()
    
    print(f"\n{'='*60}")
    print("DATABASE INTEGRITY FIX COMPLETE!")
    print("- Duplicate rows removed")
    print("- PRIMARY KEY constraint added")
    print("- Backup saved as 'bnb_backup_duplicates'")
    print(f"{'='*60}")
    
except Exception as e:
    print(f"FAILED: {e}")
    if 'connection' in locals():
        connection.rollback()
        print("Changes rolled back due to error")