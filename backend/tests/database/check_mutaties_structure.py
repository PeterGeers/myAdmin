import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv

from database import DatabaseManager
from dialect_helpers import dialect

load_dotenv()

def check_table_structure():
    try:
        db = DatabaseManager()
        
        # Show table structure using dialect helper
        columns = db.execute_query(dialect.describe_table('mutaties'))
        
        print("=== MUTATIES TABLE STRUCTURE ===")
        for column in columns:
            values = list(column.values())
            print(f"  {' - '.join(str(v) for v in values)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_table_structure()
