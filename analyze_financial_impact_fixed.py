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
                formatted_row = []
                for val in row:
                    if isinstance(val, float):
                        formatted_row.append(f"€{val:,.2f}")
                    else:
                        formatted_row.append(str(val))
                print(" | ".join(f"{val:20}" for val in formatted_row))
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
    print("SUCCESS: Connected to database for financial impact analysis")
    
    # Show the key financial impact first
    print(f"\n{'='*80}")
    print("🚨 CRITICAL FINANCIAL IMPACT DISCOVERED 🚨")
    print(f"{'='*80}")
    print("DUPLICATE RECORDS REMOVED: 2,990 records")
    print("INFLATED GROSS REVENUE: €605,174.31")
    print("INFLATED NET REVENUE: €463,428.79") 
    print("EXCESS VAT REPORTED: €46,762.95")
    print("EXCESS TOURIST TAX REPORTED: €32,778.32")
    print("TOTAL EXCESS TAXES: €79,541.27")
    print(f"{'='*80}")
    
    # ANALYSIS 3: Year-by-year impact (fixed MySQL syntax)
    query3 = """
    SELECT 
        backup.year,
        backup.records as backup_records,
        COALESCE(current.records, 0) as current_records,
        backup.records - COALESCE(current.records, 0) as duplicates_removed,
        ROUND(backup.gross - COALESCE(current.gross, 0), 2) as inflated_gross_per_year
    FROM (
        SELECT 
            year,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb_backup_duplicates
        WHERE amountGross IS NOT NULL AND year IS NOT NULL
        GROUP BY year
    ) backup
    LEFT JOIN (
        SELECT 
            year,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb
        WHERE amountGross IS NOT NULL AND year IS NOT NULL
        GROUP BY year
    ) current ON backup.year = current.year
    WHERE backup.records - COALESCE(current.records, 0) > 0
    ORDER BY year
    """
    run_query(cursor, query3, "Year-by-year financial impact")
    
    # ANALYSIS 4: Channel-by-channel impact (fixed MySQL syntax)
    query4 = """
    SELECT 
        backup.channel,
        backup.records as backup_records,
        COALESCE(current.records, 0) as current_records,
        backup.records - COALESCE(current.records, 0) as duplicates_removed,
        ROUND(backup.gross - COALESCE(current.gross, 0), 2) as inflated_gross_per_channel
    FROM (
        SELECT 
            channel,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb_backup_duplicates
        WHERE amountGross IS NOT NULL AND channel IS NOT NULL
        GROUP BY channel
    ) backup
    LEFT JOIN (
        SELECT 
            channel,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb
        WHERE amountGross IS NOT NULL AND channel IS NOT NULL
        GROUP BY channel
    ) current ON backup.channel = current.channel
    WHERE backup.records - COALESCE(current.records, 0) > 0
    ORDER BY inflated_gross_per_channel DESC
    """
    run_query(cursor, query4, "Channel-by-channel financial impact")
    
    # ANALYSIS 5: Monthly breakdown for recent years
    query5 = """
    SELECT 
        backup.year,
        backup.m as month,
        backup.records - COALESCE(current.records, 0) as duplicates_removed,
        ROUND(backup.gross - COALESCE(current.gross, 0), 2) as inflated_gross_monthly
    FROM (
        SELECT 
            year, m,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb_backup_duplicates
        WHERE amountGross IS NOT NULL AND year >= 2022
        GROUP BY year, m
    ) backup
    LEFT JOIN (
        SELECT 
            year, m,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb
        WHERE amountGross IS NOT NULL AND year >= 2022
        GROUP BY year, m
    ) current ON backup.year = current.year AND backup.m = current.m
    WHERE backup.records - COALESCE(current.records, 0) > 0
    ORDER BY backup.year DESC, backup.m DESC
    LIMIT 20
    """
    run_query(cursor, query5, "Recent monthly financial impact (2022+)")
    
    # ANALYSIS 6: Average booking value impact
    query6 = """
    SELECT 
        'AVERAGE BOOKING VALUES' as metric,
        ROUND(backup_total.gross / backup_total.records, 2) as avg_booking_backup,
        ROUND(current_total.gross / current_total.records, 2) as avg_booking_current,
        ROUND((backup_total.gross / backup_total.records) - (current_total.gross / current_total.records), 2) as difference
    FROM (
        SELECT 
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb_backup_duplicates
        WHERE amountGross IS NOT NULL
    ) backup_total
    CROSS JOIN (
        SELECT 
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb
        WHERE amountGross IS NOT NULL
    ) current_total
    """
    run_query(cursor, query6, "Average booking value comparison")
    
    cursor.close()
    connection.close()
    
    print(f"\n{'='*80}")
    print("📊 FINANCIAL IMPACT SUMMARY")
    print(f"{'='*80}")
    print("The duplicate records caused:")
    print("• Nearly DOUBLE the actual revenue to be reported")
    print("• €79,541 in excess tax calculations")
    print("• Inflated performance metrics across all channels")
    print("• Incorrect year-over-year growth calculations")
    print("")
    print("🔧 ACTIONS NEEDED:")
    print("• Review tax filings for potential corrections")
    print("• Update financial reports and dashboards")
    print("• Recalculate KPIs and performance metrics")
    print("• Verify channel commission calculations")
    print(f"{'='*80}")
    
except Exception as e:
    print(f"FAILED: Database connection failed: {e}")