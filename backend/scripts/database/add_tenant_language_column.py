"""
Add default_language column to tenants table for i18n support
"""
import sys
import os

# Add parent directory to path to import database module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import DatabaseManager

def add_tenant_language_column():
    """Add default_language column to tenants table"""
    conn = None
    cursor = None
    
    try:
        db_manager = DatabaseManager()
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        print("Adding default_language column to tenants table...")
        
        # Check if column already exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'tenants' 
            AND COLUMN_NAME = 'default_language'
        """)
        
        column_exists = cursor.fetchone()[0] > 0
        
        if column_exists:
            print("✅ Column 'default_language' already exists in tenants table")
        else:
            # Add column
            cursor.execute("""
                ALTER TABLE tenants
                ADD COLUMN default_language VARCHAR(5) DEFAULT 'nl'
                AFTER display_name
            """)
            print("✅ Added default_language column")
            
            # Add index
            cursor.execute("""
                CREATE INDEX idx_tenants_default_language 
                ON tenants(default_language)
            """)
            print("✅ Added index on default_language")
            
            # Update existing tenants
            cursor.execute("""
                UPDATE tenants
                SET default_language = 'nl'
                WHERE default_language IS NULL
            """)
            print("✅ Updated existing tenants to 'nl'")
            
            conn.commit()
        
        # Verify the change
        print("\nCurrent tenants:")
        cursor.execute("""
            SELECT 
                administration,
                display_name,
                default_language,
                status
            FROM tenants
            ORDER BY administration
        """)
        
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} - Language: {row[2]} - Status: {row[3]}")
        
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    add_tenant_language_column()
