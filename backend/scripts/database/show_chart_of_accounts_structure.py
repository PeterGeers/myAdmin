"""
Show chart_of_accounts table structure
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import DatabaseManager

def show_table_structure():
    """Show chart_of_accounts table structure"""
    conn = None
    cursor = None
    
    try:
        db_manager = DatabaseManager()
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        print("Chart of Accounts table structure:\n")
        
        cursor.execute("DESCRIBE rekeningschema")
        
        for row in cursor.fetchall():
            field = row[0] if isinstance(row[0], str) else row[0].decode('utf-8')
            type_val = row[1] if isinstance(row[1], str) else row[1].decode('utf-8')
            null_val = row[2] if isinstance(row[2], str) else row[2].decode('utf-8')
            key_val = row[3] if isinstance(row[3], str) else row[3].decode('utf-8')
            default_val = row[4] if row[4] is None else (row[4] if isinstance(row[4], str) else row[4].decode('utf-8'))
            print(f"  {field:<30} {type_val:<20} {null_val:<10} {key_val:<10} {default_val or ''}")
        
        print("\n\nSample data:")
        cursor.execute("SELECT * FROM rekeningschema LIMIT 5")
        
        for row in cursor.fetchall():
            print(f"  {row}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    show_table_structure()
