"""
Create account_translations table for i18n support
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import DatabaseManager

def create_account_translations_table():
    """Create account_translations table"""
    conn = None
    cursor = None
    
    try:
        db_manager = DatabaseManager()
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        print("Creating account_translations table...")
        
        # Check if table already exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'account_translations'
        """)
        
        table_exists = cursor.fetchone()[0] > 0
        
        if table_exists:
            print("✅ Table 'account_translations' already exists")
        else:
            # Create table
            cursor.execute("""
                CREATE TABLE account_translations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_code VARCHAR(10) NOT NULL,
                    language VARCHAR(5) NOT NULL,
                    account_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    
                    FOREIGN KEY (account_code) 
                        REFERENCES rekeningschema(Account)
                        ON DELETE CASCADE
                        ON UPDATE CASCADE,
                    
                    UNIQUE KEY unique_account_lang (account_code, language),
                    
                    INDEX idx_language (language),
                    INDEX idx_account_code (account_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✅ Created account_translations table")
            
            conn.commit()
        
        # Show table structure
        print("\nTable structure:")
        cursor.execute("DESCRIBE account_translations")
        
        for row in cursor.fetchall():
            field = row[0] if isinstance(row[0], str) else row[0].decode('utf-8')
            type_val = row[1] if isinstance(row[1], str) else row[1].decode('utf-8')
            print(f"  {field:<20} {type_val:<30}")
        
        # Show count
        cursor.execute("SELECT COUNT(*) FROM account_translations")
        count = cursor.fetchone()[0]
        print(f"\nCurrent translations: {count}")
        
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
    create_account_translations_table()
