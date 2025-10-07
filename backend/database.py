import mysql.connector
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', 'transactions_db')
        }
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def create_tables(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
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
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def get_bnb_lookup(self, lookup_type):
        """Get BnB lookup data based on lookup type (e.g., 'bdc')"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM bnblookup WHERE bnblookup.lookUp LIKE %s"
        cursor.execute(query, (lookup_type,))
        result = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return result
    
    def insert_transactions(self, transactions):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = '''
            INSERT INTO transactions (date, description, amount, debet, credit, ref, ref3, ref4)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        '''
        
        for transaction in transactions:
            cursor.execute(query, (
                transaction['date'],
                transaction['description'],
                transaction['amount'],
                transaction['debet'],
                transaction['credit'],
                transaction.get('ref', ''),
                transaction.get('ref3', ''),
                transaction.get('ref4', '')
            ))
        
        conn.commit()
        cursor.close()
        conn.close()