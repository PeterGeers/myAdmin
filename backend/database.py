import mysql.connector
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
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
    
    def insert_transaction(self, transaction, table_name='mutaties'):
        """Insert a single transaction into the specified table"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        insert_query = f"""
            INSERT INTO {table_name} 
            (TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, 
             Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(insert_query, (
            transaction.get('TransactionNumber', ''),
            transaction.get('TransactionDate', ''),
            transaction.get('TransactionDescription', ''),
            transaction.get('TransactionAmount', 0),
            transaction.get('Debet', ''),
            transaction.get('Credit', ''),
            transaction.get('ReferenceNumber', ''),
            transaction.get('Ref1', ''),
            transaction.get('Ref2', ''),
            transaction.get('Ref3', ''),
            transaction.get('Ref4', ''),
            transaction.get('Administration', 'GoodwinSolutions')
        ))
        
        conn.commit()
        transaction_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return transaction_id
    
    def get_used_transaction_numbers(self, ref1, table_name='mutaties'):
        """Get existing transaction numbers for duplicate prevention"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = f"SELECT Ref2 FROM {table_name} WHERE Ref1 = %s"
        cursor.execute(query, (ref1,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return results
    
    def get_bank_account_lookups(self):
        """Get bank account lookup data"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT rekeningNummer, Account, Administration FROM lookupbankaccounts_R"
        cursor.execute(query)
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return results
    
    def get_existing_sequences(self, iban, table_name='mutaties'):
        """Get existing Ref2 sequences for a specific IBAN within last 2 years"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = f"""
            SELECT Ref2 as existing 
            FROM {table_name} 
            WHERE Ref1 = %s 
            AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
            AND Ref2 IS NOT NULL 
            AND Ref2 != ''
        """
        cursor.execute(query, (iban,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [r['existing'] for r in results]
    
    def get_patterns(self, administration):
        """Get patterns from vw_ReadReferences view"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT debet, credit, administration, referenceNumber 
            FROM vw_ReadReferences 
            WHERE administration = %s 
            AND (debet < '1300' OR credit < '1300')
        """
        cursor.execute(query, (administration,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return results
    
    def get_recent_transactions(self, limit=100, table_name='mutaties'):
        """Get recent transactions for lookup data"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = f"""
            SELECT TransactionDescription, Debet, Credit 
            FROM {table_name} 
            ORDER BY ID DESC 
            LIMIT %s
        """
        cursor.execute(query, (limit,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return results
    
    def get_last_transactions(self, reference_number, table_name='mutaties'):
        """Get last transactions for a specific reference number - matches R getLastTransactions exactly"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # First query: get transactions with matching TransactionNumber and max date
        query = f"""
            SELECT * FROM {table_name} 
            WHERE TransactionNumber LIKE %s 
            AND TransactionDate = (
                SELECT MAX(TransactionDate) 
                FROM {table_name} 
                WHERE TransactionNumber LIKE %s
            ) 
            ORDER BY Debet DESC
        """
        cursor.execute(query, (f"{reference_number}%", f"{reference_number}%"))
        results = cursor.fetchall()
        
        # If no results, fallback to Gamma like R script
        if not results:
            cursor.execute(query, ("Gamma%", "Gamma%"))
            results = cursor.fetchall()
            # Update TransactionNumber and ReferenceNumber
            for result in results:
                result['TransactionNumber'] = reference_number
                result['ReferenceNumber'] = reference_number
        
        # If less than 2 records, duplicate and modify like R script
        if len(results) < 2:
            if results:
                second_record = results[0].copy()
                second_record['Debet'] = '2010'
                second_record['Credit'] = results[0]['Debet']
                results.append(second_record)
            else:
                # Create default records if none found
                default_record = {
                    'Debet': '4000', 'Credit': '1300',
                    'TransactionNumber': reference_number,
                    'ReferenceNumber': reference_number
                }
                results = [default_record, {
                    'Debet': '2010', 'Credit': '4000',
                    'TransactionNumber': reference_number,
                    'ReferenceNumber': reference_number
                }]
        
        cursor.close()
        conn.close()
        return results