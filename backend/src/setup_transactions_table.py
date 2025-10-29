import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def setup_table():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'finance')
        )
        cursor = conn.cursor()
        
        # Show existing tables
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print("Existing tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Create transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE,
                description TEXT,
                amount DECIMAL(10,2),
                debet DECIMAL(10,2),
                credit DECIMAL(10,2),
                ref VARCHAR(255),
                ref3 VARCHAR(500),
                ref4 VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("Transactions table created")
        
        # Insert sample Avance data
        cursor.execute('''
            INSERT INTO transactions 
            (date, description, amount, debet, credit, ref, ref3, ref4)
            VALUES 
            ('2024-01-15', 'Avance sample transaction', 150.00, 150.00, 0.00, 'Avance', 'https://drive.google.com/sample', 'Avance')
        ''')
        
        conn.commit()
        print("Sample Avance transaction added")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    setup_table()