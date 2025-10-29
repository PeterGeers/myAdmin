import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def setup_database():
    try:
        # Connect without specifying database first
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', '')
        )
        cursor = conn.cursor()
        
        # Create database
        db_name = os.getenv('DB_NAME', 'transactions_db')
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        print(f"Database '{db_name}' created/verified")
        
        # Use the database
        cursor.execute(f"USE {db_name}")
        
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
        print("Transactions table created/verified")
        
        # Insert sample Avance transaction for testing
        cursor.execute('''
            INSERT IGNORE INTO transactions 
            (date, description, amount, debet, credit, ref, ref3, ref4)
            VALUES 
            ('2024-01-15', 'Avance sample transaction', 150.00, 150.00, 0.00, 'Avance', 'https://drive.google.com/sample', 'Avance')
        ''')
        
        conn.commit()
        print("Sample Avance transaction inserted")
        
        cursor.close()
        conn.close()
        print("Database setup completed successfully!")
        
    except Exception as e:
        print(f"Database setup failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    setup_database()