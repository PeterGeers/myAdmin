"""
Show all tables in the database
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import DatabaseManager

def show_all_tables():
    """Show all tables"""
    conn = None
    cursor = None
    
    try:
        db_manager = DatabaseManager()
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        print("All tables in database:\n")
        
        cursor.execute("SHOW TABLES")
        
        tables = cursor.fetchall()
        for table in tables:
            print(f"  {table[0]}")
        
        print(f"\nTotal: {len(tables)} tables")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    show_all_tables()
