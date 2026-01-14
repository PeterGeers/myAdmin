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
    
    # ANALYSIS 1: Compare totals between backup (with duplicates) and current (clean) table
    query1 = """
    SELECT 
        'BACKUP (with duplicates)' as table_name,
        COUNT(*) as total_records,
        ROUND(SUM(amountGross), 2) as total_gross_revenue,
        ROUND(SUM(amountNett), 2) as total_net_revenue,
        ROUND(SUM(amountChannelFee), 2) as total_channel_fees,
        ROUND(SUM(amountTouristTax), 2) as total_tourist_tax,
        ROUND(SUM(amountVat), 2) as total_vat
    FROM bnb_backup_duplicates
    WHERE amountGross IS NOT NULL
    
    UNION ALL
    
    SELECT 
        'CURRENT (clean)' as table_name,
        COUNT(*) as total_records,
        ROUND(SUM(amountGross), 2) as total_gross_revenue,
        ROUND(SUM(amountNett), 2) as total_net_revenue,
        ROUND(SUM(amountChannelFee), 2) as total_channel_fees,
        ROUND(SUM(amountTouristTax), 2) as total_tourist_tax,
        ROUND(SUM(amountVat), 2) as total_vat
    FROM bnb
    WHERE amountGross IS NOT NULL
    """
    run_query(cursor, query1, "Financial totals comparison")
    
    # ANALYSIS 2: Calculate the difference (financial impact)
    query2 = """
    SELECT 
        'FINANCIAL IMPACT' as description,
        (backup.total_records - current.total_records) as duplicate_records_removed,
        ROUND((backup.total_gross - current.total_gross), 2) as inflated_gross_revenue,
        ROUND((backup.total_net - current.total_net), 2) as inflated_net_revenue,
        ROUND((backup.total_fees - current.total_fees), 2) as inflated_channel_fees,
        ROUND((backup.total_tax - current.total_tax), 2) as inflated_tourist_tax,
        ROUND((backup.total_vat - current.total_vat), 2) as inflated_vat
    FROM (
        SELECT 
            COUNT(*) as total_records,
            SUM(amountGross) as total_gross,
            SUM(amountNett) as total_net,
            SUM(amountChannelFee) as total_fees,
            SUM(amountTouristTax) as total_tax,
            SUM(amountVat) as total_vat
        FROM bnb_backup_duplicates
        WHERE amountGross IS NOT NULL
    ) backup
    CROSS JOIN (
        SELECT 
            COUNT(*) as total_records,
            SUM(amountGross) as total_gross,
            SUM(amountNett) as total_net,
            SUM(amountChannelFee) as total_fees,
            SUM(amountTouristTax) as total_tax,
            SUM(amountVat) as total_vat
        FROM bnb
        WHERE amountGross IS NOT NULL
    ) current
    """
    run_query(cursor, query2, "Financial impact of removing duplicates")
    
    # ANALYSIS 3: Year-by-year impact
    query3 = """
    SELECT 
        COALESCE(backup.year, current.year) as year,
        COALESCE(backup.records, 0) as backup_records,
        COALESCE(current.records, 0) as current_records,
        COALESCE(backup.records, 0) - COALESCE(current.records, 0) as duplicates_removed,
        ROUND(COALESCE(backup.gross, 0) - COALESCE(current.gross, 0), 2) as inflated_gross_per_year
    FROM (
        SELECT 
            year,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb_backup_duplicates
        WHERE amountGross IS NOT NULL AND year IS NOT NULL
        GROUP BY year
    ) backup
    FULL OUTER JOIN (
        SELECT 
            year,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb
        WHERE amountGross IS NOT NULL AND year IS NOT NULL
        GROUP BY year
    ) current ON backup.year = current.year
    ORDER BY year
    """
    run_query(cursor, query3, "Year-by-year financial impact")
    
    # ANALYSIS 4: Channel-by-channel impact
    query4 = """
    SELECT 
        COALESCE(backup.channel, current.channel) as channel,
        COALESCE(backup.records, 0) - COALESCE(current.records, 0) as duplicates_removed,
        ROUND(COALESCE(backup.gross, 0) - COALESCE(current.gross, 0), 2) as inflated_gross_per_channel
    FROM (
        SELECT 
            channel,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb_backup_duplicates
        WHERE amountGross IS NOT NULL AND channel IS NOT NULL
        GROUP BY channel
    ) backup
    FULL OUTER JOIN (
        SELECT 
            channel,
            COUNT(*) as records,
            SUM(amountGross) as gross
        FROM bnb
        WHERE amountGross IS NOT NULL AND channel IS NOT NULL
        GROUP BY channel
    ) current ON backup.channel = current.channel
    WHERE COALESCE(backup.records, 0) - COALESCE(current.records, 0) > 0
    ORDER BY inflated_gross_per_channel DESC
    """
    run_query(cursor, query4, "Channel-by-channel financial impact")
    
    # ANALYSIS 5: Tax implications
    query5 = """
    SELECT 
        'TAX IMPACT SUMMARY' as description,
        ROUND((backup.total_vat - current.total_vat), 2) as excess_vat_reported,
        ROUND((backup.total_tax - current.total_tax), 2) as excess_tourist_tax_reported,
        ROUND((backup.total_vat - current.total_vat) + (backup.total_tax - current.total_tax), 2) as total_excess_taxes
    FROM (
        SELECT 
            SUM(amountTouristTax) as total_tax,
            SUM(amountVat) as total_vat
        FROM bnb_backup_duplicates
        WHERE amountGross IS NOT NULL
    ) backup
    CROSS JOIN (
        SELECT 
            SUM(amountTouristTax) as total_tax,
            SUM(amountVat) as total_vat
        FROM bnb
        WHERE amountGross IS NOT NULL
    ) current
    """
    run_query(cursor, query5, "Tax reporting impact")
    
    cursor.close()
    connection.close()
    
    print(f"\n{'='*60}")
    print("FINANCIAL IMPACT ANALYSIS COMPLETE!")
    print("Key areas to review:")
    print("- Revenue reporting accuracy")
    print("- Tax calculations and filings")
    print("- Channel performance metrics")
    print("- Year-over-year comparisons")
    print(f"{'='*60}")
    
except Exception as e:
    print(f"FAILED: Database connection failed: {e}")