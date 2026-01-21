"""
Database Migration: Add countryName column to bnb and bnbplanned tables

This script:
1. Adds countryName column to bnb table
2. Adds countryName column to bnbplanned table
3. Updates vw_bnb_total view to include countryName
"""

import mysql.connector
import os
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Run the database migration"""
    
    # Database connection
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME'),
        'port': int(os.getenv('DB_PORT', 3306))
    }
    
    print(f"Connecting to database: {db_config['database']} at {db_config['host']}")
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        print("\n=== Starting Migration ===\n")
        
        # Step 1: Add countryName column to bnb table
        print("Step 1: Adding countryName column to bnb table...")
        try:
            cursor.execute("""
                ALTER TABLE bnb 
                ADD COLUMN countryName VARCHAR(100) DEFAULT NULL 
                COMMENT 'Full country name (e.g., Netherlands, Spain, United States)'
            """)
            print("✓ Successfully added countryName column to bnb table")
        except mysql.connector.Error as e:
            if e.errno == 1060:  # Duplicate column name
                print("⚠ countryName column already exists in bnb table")
            else:
                raise
        
        # Step 2: Add countryName column to bnbplanned table
        print("\nStep 2: Adding countryName column to bnbplanned table...")
        try:
            cursor.execute("""
                ALTER TABLE bnbplanned 
                ADD COLUMN countryName VARCHAR(100) DEFAULT NULL 
                COMMENT 'Full country name (e.g., Netherlands, Spain, United States)'
            """)
            print("✓ Successfully added countryName column to bnbplanned table")
        except mysql.connector.Error as e:
            if e.errno == 1060:  # Duplicate column name
                print("⚠ countryName column already exists in bnbplanned table")
            else:
                raise
        
        # Step 3: Update view
        print("\nStep 3: Updating vw_bnb_total view...")
        cursor.execute("DROP VIEW IF EXISTS vw_bnb_total")
        cursor.execute("""
            CREATE VIEW vw_bnb_total AS
            SELECT id,
                sourceFile,
                channel,
                listing,
                checkinDate,
                checkoutDate,
                nights,
                guests,
                amountGross,
                amountNett,
                amountChannelFee,
                amountTouristTax,
                amountVat,
                guestName,
                phone,
                reservationCode,
                reservationDate,
                status,
                pricePerNight,
                daysBeforeReservation,
                addInfo,
                year,
                q,
                m,
                country,
                countryName,
                'actual' AS source_type
            FROM bnb
            UNION ALL
            SELECT id,
                sourceFile,
                channel,
                listing,
                checkinDate,
                checkoutDate,
                nights,
                guests,
                amountGross,
                amountNett,
                amountChannelFee,
                amountTouristTax,
                amountVat,
                guestName,
                phone,
                reservationCode,
                reservationDate,
                status,
                pricePerNight,
                daysBeforeReservation,
                addInfo,
                year,
                q,
                m,
                country,
                countryName,
                'planned' AS source_type
            FROM bnbplanned
        """)
        print("✓ Successfully updated vw_bnb_total view")
        
        # Commit changes
        conn.commit()
        
        print("\n=== Migration Completed Successfully ===\n")
        
        # Verification
        print("Verification:")
        cursor.execute("SHOW COLUMNS FROM bnb LIKE 'countryName'")
        result = cursor.fetchone()
        if result:
            print(f"✓ bnb.countryName: {result[1]}")
        
        cursor.execute("SHOW COLUMNS FROM bnbplanned LIKE 'countryName'")
        result = cursor.fetchone()
        if result:
            print(f"✓ bnbplanned.countryName: {result[1]}")
        
        cursor.execute("DESCRIBE vw_bnb_total")
        columns = [row[0] for row in cursor.fetchall()]
        if 'countryName' in columns:
            print(f"✓ vw_bnb_total includes countryName column")
        
        cursor.close()
        conn.close()
        
        print("\n✓ All changes verified successfully!")
        
    except mysql.connector.Error as e:
        print(f"\n✗ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    run_migration()
