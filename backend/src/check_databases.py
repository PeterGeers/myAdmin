import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def check_databases():
    try:
        # Connect without database to list all databases
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', '')
        )
        cursor = conn.cursor()
        
        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()
        
        print("Available databases:")
        for db in databases:
            print(f"  - {db[0]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_databases()