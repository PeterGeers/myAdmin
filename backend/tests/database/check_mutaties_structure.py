import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def check_table_structure():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'finance')
        )
        cursor = conn.cursor()
        
        # Show table structure
        cursor.execute("DESCRIBE mutaties")
        columns = cursor.fetchall()
        
        print("=== MUTATIES TABLE STRUCTURE ===")
        for column in columns:
            print(f"  {column[0]} - {column[1]} - {column[2]} - {column[3]} - {column[4]} - {column[5]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_table_structure()