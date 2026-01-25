"""
Setup Test Database for Multi-Tenant Testing

This script creates the testfinance database by copying the structure
from the finance database and adding sample test data for each tenant.
"""

import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def setup_test_database():
    """Create testfinance database with structure from finance database"""
    
    # Connect to MySQL without specifying database
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', '')
    )
    
    cursor = conn.cursor()
    
    try:
        # Drop and create testfinance database
        print("Creating testfinance database...")
        cursor.execute("DROP DATABASE IF EXISTS testfinance")
        cursor.execute("CREATE DATABASE testfinance")
        print("✅ testfinance database created")
        
        # Get all BASE TABLES from finance database (exclude views)
        cursor.execute("USE finance")
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = 'finance' 
            AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\nCopying structure for {len(tables)} base tables...")
        
        # Copy structure for each table
        for table in tables:
            print(f"  Copying {table}...")
            cursor.execute(f"CREATE TABLE testfinance.{table} LIKE finance.{table}")
        
        print("✅ All table structures copied")
        
        # Get all VIEWS from finance database
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = 'finance' 
            AND TABLE_TYPE = 'VIEW'
            ORDER BY TABLE_NAME
        """)
        views = [row[0] for row in cursor.fetchall()]
        
        if views:
            print(f"\nCopying {len(views)} views...")
            cursor.execute("USE testfinance")
            
            # Views may depend on other views, so we need to create them in order
            # Try multiple passes until all views are created
            remaining_views = views.copy()
            max_attempts = len(views) + 1
            attempt = 0
            
            while remaining_views and attempt < max_attempts:
                attempt += 1
                failed_views = []
                
                for view in remaining_views:
                    try:
                        print(f"  Copying view {view}...")
                        # Get view definition
                        cursor.execute(f"SHOW CREATE VIEW finance.{view}")
                        view_def = cursor.fetchone()[1]
                        # Replace database name in view definition
                        view_def = view_def.replace('`finance`.', '`testfinance`.')
                        view_def = view_def.replace('finance.', 'testfinance.')
                        # Drop view if exists
                        cursor.execute(f"DROP VIEW IF EXISTS testfinance.{view}")
                        # Create view in testfinance
                        cursor.execute(view_def)
                    except mysql.connector.Error as e:
                        # View creation failed, probably due to dependency
                        # Will retry in next pass
                        failed_views.append(view)
                        if attempt == max_attempts - 1:
                            print(f"    ⚠️ Warning: Could not create view {view}: {e}")
                
                remaining_views = failed_views
            
            if not remaining_views:
                print("✅ All views copied")
            else:
                print(f"⚠️ Warning: {len(remaining_views)} views could not be created: {', '.join(remaining_views)}")
        
        print("✅ All table structures copied")
        
        # Copy sample data for key tables with tenant filtering
        print("\nCopying sample data...")
        
        # Copy mutaties (transactions) - limit to 100 per tenant
        cursor.execute("""
            INSERT INTO testfinance.mutaties 
            SELECT * FROM finance.mutaties 
            WHERE administration = 'GoodwinSolutions' 
            LIMIT 100
        """)
        print(f"  ✅ Copied {cursor.rowcount} GoodwinSolutions transactions")
        
        cursor.execute("""
            INSERT INTO testfinance.mutaties 
            SELECT * FROM finance.mutaties 
            WHERE administration = 'PeterPrive' 
            LIMIT 50
        """)
        print(f"  ✅ Copied {cursor.rowcount} PeterPrive transactions")
        
        cursor.execute("""
            INSERT INTO testfinance.mutaties 
            SELECT * FROM finance.mutaties 
            WHERE administration = 'InterimManagement' 
            LIMIT 50
        """)
        print(f"  ✅ Copied {cursor.rowcount} InterimManagement transactions")
        
        # Copy rekeningschema (chart of accounts)
        cursor.execute("""
            INSERT INTO testfinance.rekeningschema 
            SELECT * FROM finance.rekeningschema 
            WHERE administration IN ('GoodwinSolutions', 'PeterPrive', 'InterimManagement')
        """)
        print(f"  ✅ Copied {cursor.rowcount} chart of accounts records")
        
        # Copy countries (generic table)
        cursor.execute("""
            INSERT INTO testfinance.countries 
            SELECT * FROM finance.countries
        """)
        print(f"  ✅ Copied {cursor.rowcount} countries")
        
        # Create tenant_config table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS testfinance.tenant_config (
                id INT AUTO_INCREMENT PRIMARY KEY,
                administration VARCHAR(50) NOT NULL,
                config_key VARCHAR(100) NOT NULL,
                config_value TEXT,
                is_secret BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_by VARCHAR(255),
                UNIQUE KEY unique_tenant_config (administration, config_key),
                INDEX idx_administration (administration)
            )
        """)
        print("  ✅ Created tenant_config table")
        
        # Add sample tenant configs
        cursor.execute("""
            INSERT INTO testfinance.tenant_config 
            (administration, config_key, config_value, is_secret, created_by)
            VALUES 
            ('GoodwinSolutions', 'test_config', 'test_value_goodwin', FALSE, 'test@test.com'),
            ('PeterPrive', 'test_config', 'test_value_peter', FALSE, 'test@test.com'),
            ('InterimManagement', 'test_config', 'test_value_interim', FALSE, 'test@test.com')
        """)
        print(f"  ✅ Added {cursor.rowcount} sample tenant configs")
        
        conn.commit()
        
        print("\n✅ Test database setup complete!")
        print("\nDatabase: testfinance")
        print("Tables: All structures copied from finance")
        print("Sample data: Limited records for GoodwinSolutions, PeterPrive, InterimManagement")
        
    except Exception as e:
        print(f"\n❌ Error setting up test database: {e}")
        conn.rollback()
        raise
    
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    setup_test_database()
