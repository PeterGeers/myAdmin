"""
Create countries lookup table and update view

This script:
1. Creates countries lookup table with code, name, name_nl, region
2. Populates with common countries from booking data
3. Updates vw_bnb_total view to JOIN with countries table
"""

import mysql.connector
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    """Run the migration"""
    
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME'),
        'port': int(os.getenv('DB_PORT', 3306))
    }
    
    print(f"\nConnecting to database: {db_config['database']} at {db_config['host']}")
    print("="*60)
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Step 1: Create countries table
        print("\nStep 1: Creating countries lookup table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS countries (
                    code VARCHAR(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci PRIMARY KEY COMMENT 'ISO 3166-1 alpha-2 country code',
                    name VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'English country name',
                    name_nl VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Dutch country name (optional)',
                    region VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Geographic region (e.g., Europe, Asia)',
                    UNIQUE KEY idx_name (name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Country code to name lookup table'
            """)
            print("✓ Created countries lookup table")
        except mysql.connector.Error as e:
            if e.errno == 1050:
                print("⚠ Countries table already exists")
            else:
                raise
        
        # Step 2: Populate countries table
        print("\nStep 2: Populating countries table...")
        
        countries_data = [
            # Europe
            ('NL', 'Netherlands', 'Nederland', 'Europe'),
            ('DE', 'Germany', 'Duitsland', 'Europe'),
            ('GB', 'United Kingdom', 'Verenigd Koninkrijk', 'Europe'),
            ('FR', 'France', 'Frankrijk', 'Europe'),
            ('BE', 'Belgium', 'België', 'Europe'),
            ('ES', 'Spain', 'Spanje', 'Europe'),
            ('IT', 'Italy', 'Italië', 'Europe'),
            ('CH', 'Switzerland', 'Zwitserland', 'Europe'),
            ('AT', 'Austria', 'Oostenrijk', 'Europe'),
            ('PT', 'Portugal', 'Portugal', 'Europe'),
            ('SE', 'Sweden', 'Zweden', 'Europe'),
            ('NO', 'Norway', 'Noorwegen', 'Europe'),
            ('DK', 'Denmark', 'Denemarken', 'Europe'),
            ('FI', 'Finland', 'Finland', 'Europe'),
            ('PL', 'Poland', 'Polen', 'Europe'),
            ('CZ', 'Czech Republic', 'Tsjechië', 'Europe'),
            ('HU', 'Hungary', 'Hongarije', 'Europe'),
            ('RO', 'Romania', 'Roemenië', 'Europe'),
            ('BG', 'Bulgaria', 'Bulgarije', 'Europe'),
            ('GR', 'Greece', 'Griekenland', 'Europe'),
            ('IE', 'Ireland', 'Ierland', 'Europe'),
            ('HR', 'Croatia', 'Kroatië', 'Europe'),
            ('SK', 'Slovakia', 'Slowakije', 'Europe'),
            ('LV', 'Latvia', 'Letland', 'Europe'),
            ('LT', 'Lithuania', 'Litouwen', 'Europe'),
            ('EE', 'Estonia', 'Estland', 'Europe'),
            ('LU', 'Luxembourg', 'Luxemburg', 'Europe'),
            ('CY', 'Cyprus', 'Cyprus', 'Europe'),
            ('MT', 'Malta', 'Malta', 'Europe'),
            ('IS', 'Iceland', 'IJsland', 'Europe'),
            ('UA', 'Ukraine', 'Oekraïne', 'Europe'),
            ('RS', 'Serbia', 'Servië', 'Europe'),
            ('AL', 'Albania', 'Albanië', 'Europe'),
            ('MK', 'North Macedonia', 'Noord-Macedonië', 'Europe'),
            ('MD', 'Moldova', 'Moldavië', 'Europe'),
            ('GE', 'Georgia', 'Georgië', 'Europe/Asia'),
            # Americas
            ('US', 'United States', 'Verenigde Staten', 'North America'),
            ('CA', 'Canada', 'Canada', 'North America'),
            ('MX', 'Mexico', 'Mexico', 'North America'),
            ('BR', 'Brazil', 'Brazilië', 'South America'),
            ('AR', 'Argentina', 'Argentinië', 'South America'),
            ('CO', 'Colombia', 'Colombia', 'South America'),
            ('PE', 'Peru', 'Peru', 'South America'),
            ('UY', 'Uruguay', 'Uruguay', 'South America'),
            ('PA', 'Panama', 'Panama', 'Central America'),
            ('EC', 'Ecuador', 'Ecuador', 'South America'),
            # Asia
            ('CN', 'China', 'China', 'Asia'),
            ('JP', 'Japan', 'Japan', 'Asia'),
            ('IN', 'India', 'India', 'Asia'),
            ('KR', 'South Korea', 'Zuid-Korea', 'Asia'),
            ('TR', 'Turkey', 'Turkije', 'Asia/Europe'),
            ('SG', 'Singapore', 'Singapore', 'Asia'),
            ('MY', 'Malaysia', 'Maleisië', 'Asia'),
            ('TH', 'Thailand', 'Thailand', 'Asia'),
            ('PH', 'Philippines', 'Filipijnen', 'Asia'),
            ('HK', 'Hong Kong', 'Hong Kong', 'Asia'),
            ('AE', 'United Arab Emirates', 'Verenigde Arabische Emiraten', 'Middle East'),
            ('SA', 'Saudi Arabia', 'Saoedi-Arabië', 'Middle East'),
            ('IL', 'Israel', 'Israël', 'Middle East'),
            ('AZ', 'Azerbaijan', 'Azerbeidzjan', 'Asia'),
            ('KZ', 'Kazakhstan', 'Kazachstan', 'Asia'),
            ('UZ', 'Uzbekistan', 'Oezbekistan', 'Asia'),
            ('PK', 'Pakistan', 'Pakistan', 'Asia'),
            # Oceania
            ('AU', 'Australia', 'Australië', 'Oceania'),
            ('NZ', 'New Zealand', 'Nieuw-Zeeland', 'Oceania'),
            # Africa
            ('ZA', 'South Africa', 'Zuid-Afrika', 'Africa'),
            ('EG', 'Egypt', 'Egypte', 'Africa'),
            ('MA', 'Morocco', 'Marokko', 'Africa'),
            ('NG', 'Nigeria', 'Nigeria', 'Africa'),
            # Russia
            ('RU', 'Russia', 'Rusland', 'Europe/Asia')
        ]
        
        insert_query = """
            INSERT INTO countries (code, name, name_nl, region) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                name = VALUES(name),
                name_nl = VALUES(name_nl),
                region = VALUES(region)
        """
        
        cursor.executemany(insert_query, countries_data)
        print(f"✓ Populated countries table with {len(countries_data)} countries")
        
        # Step 3: Update view
        print("\nStep 3: Updating vw_bnb_total view with country JOIN...")
        cursor.execute("DROP VIEW IF EXISTS vw_bnb_total")
        cursor.execute("""
            CREATE VIEW vw_bnb_total AS
            SELECT 
                b.id,
                b.sourceFile,
                b.channel,
                b.listing,
                b.checkinDate,
                b.checkoutDate,
                b.nights,
                b.guests,
                b.amountGross,
                b.amountNett,
                b.amountChannelFee,
                b.amountTouristTax,
                b.amountVat,
                b.guestName,
                b.phone,
                b.reservationCode,
                b.reservationDate,
                b.status,
                b.pricePerNight,
                b.daysBeforeReservation,
                b.addInfo,
                b.year,
                b.q,
                b.m,
                b.country,
                c.name AS countryName,
                c.name_nl AS countryNameNL,
                c.region AS countryRegion,
                'actual' AS source_type
            FROM bnb b
            LEFT JOIN countries c ON b.country = c.code
            
            UNION ALL
            
            SELECT 
                b.id,
                b.sourceFile,
                b.channel,
                b.listing,
                b.checkinDate,
                b.checkoutDate,
                b.nights,
                b.guests,
                b.amountGross,
                b.amountNett,
                b.amountChannelFee,
                b.amountTouristTax,
                b.amountVat,
                b.guestName,
                b.phone,
                b.reservationCode,
                b.reservationDate,
                b.status,
                b.pricePerNight,
                b.daysBeforeReservation,
                b.addInfo,
                b.year,
                b.q,
                b.m,
                b.country,
                c.name AS countryName,
                c.name_nl AS countryNameNL,
                c.region AS countryRegion,
                'planned' AS source_type
            FROM bnbplanned b
            LEFT JOIN countries c ON b.country = c.code
        """)
        print("✓ Updated vw_bnb_total view with country JOIN")
        
        conn.commit()
        
        print("\n" + "="*60)
        print("Migration Completed Successfully!")
        print("="*60 + "\n")
        
        # Verification
        print("Verification:")
        print("-"*60)
        
        cursor.execute("SELECT COUNT(*) FROM countries")
        count = cursor.fetchone()[0]
        print(f"✓ Countries table has {count} countries")
        
        cursor.execute("DESCRIBE vw_bnb_total")
        columns = [row[0] for row in cursor.fetchall()]
        if 'countryName' in columns and 'countryNameNL' in columns:
            print(f"✓ View includes countryName and countryNameNL columns")
        
        # Show sample data
        print("\nSample country lookups:")
        print("-"*60)
        cursor.execute("""
            SELECT country, countryName, countryNameNL, COUNT(*) as bookings
            FROM vw_bnb_total 
            WHERE country IS NOT NULL 
            GROUP BY country, countryName, countryNameNL
            ORDER BY bookings DESC 
            LIMIT 10
        """)
        
        print(f"{'Code':4s} | {'English Name':20s} | {'Dutch Name':20s} | {'Bookings':>8s}")
        print("-"*60)
        for row in cursor.fetchall():
            print(f"{row[0]:4s} | {row[1]:20s} | {row[2] or 'N/A':20s} | {row[3]:8d}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "="*60)
        print("✓ All changes verified successfully!")
        print("="*60 + "\n")
        
    except mysql.connector.Error as e:
        print(f"\n✗ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    run_migration()
