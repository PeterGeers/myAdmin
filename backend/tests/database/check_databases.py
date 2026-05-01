import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from dotenv import load_dotenv

from database import DatabaseManager

load_dotenv()

def check_databases():
    try:
        db = DatabaseManager()
        
        databases = db.execute_query("SHOW DATABASES")
        
        print("Available databases:")
        for db_row in databases:
            print(f"  - {list(db_row.values())[0]}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_databases()
