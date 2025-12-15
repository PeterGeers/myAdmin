import mysql.connector
from mysql.connector import pooling
from datetime import datetime
import os
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

class DatabaseManager:
    _pool = None
    _use_pool = True
    
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        
        # Use test database if test_mode is True or TEST_MODE env var is set
        use_test = test_mode or os.getenv('TEST_MODE', 'false').lower() == 'true'
        db_name = os.getenv('TEST_DB_NAME', 'testfinance') if use_test else os.getenv('DB_NAME', 'finance')
        
        self.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': db_name
        }
        
        if DatabaseManager._use_pool and not DatabaseManager._pool:
            try:
                pool_config = self.config.copy()
                pool_config.update({
                    'pool_name': 'mypool',
                    'pool_size': 5,
                    'pool_reset_session': True
                })
                DatabaseManager._pool = pooling.MySQLConnectionPool(**pool_config)
            except Exception as e:
                print(f"Connection pool failed, using direct connections: {e}")
                DatabaseManager._use_pool = False
    
    def _get_db_config(self):
        """Get database configuration for SQLAlchemy"""
        return self.config
    
    def get_connection(self):
        if DatabaseManager._use_pool and DatabaseManager._pool:
            try:
                return DatabaseManager._pool.get_connection()
            except Exception:
                DatabaseManager._use_pool = False
        return mysql.connector.connect(**self.config)
    
    @contextmanager
    def get_cursor(self, dictionary=True):
        """Context manager for database operations"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield cursor, conn
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def execute_query(self, query, params=None, fetch=True, commit=False):
        """Execute query with automatic connection management"""
        with self.get_cursor() as (cursor, conn):
            cursor.execute(query, params or ())
            if commit:
                conn.commit()
                return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
            return cursor.fetchall() if fetch else None
    
    def create_tables(self):
        self.execute_query('''
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
        ''', fetch=False, commit=True)
    
    def get_bnb_lookup(self, lookup_type):
        """Get BnB lookup data based on lookup type (e.g., 'bdc')"""
        return self.execute_query(
            "SELECT * FROM bnblookup WHERE bnblookup.lookUp LIKE %s",
            (lookup_type,)
        )
    
    def insert_transactions(self, transactions):
        with self.get_cursor(dictionary=False) as (cursor, conn):
            query = '''
                INSERT INTO transactions (date, description, amount, debet, credit, ref, ref3, ref4)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            '''
            
            data = [(
                t['date'], t['description'], t['amount'], t['debet'], t['credit'],
                t.get('ref', ''), t.get('ref3', ''), t.get('ref4', '')
            ) for t in transactions]
            
            cursor.executemany(query, data)
            conn.commit()
    
    def insert_transaction(self, transaction, table_name='mutaties'):
        """Insert a single transaction into the specified table"""
        return self.execute_query(
            f"""INSERT INTO {table_name} 
                (TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, 
                 Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
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
            ),
            fetch=False,
            commit=True
        )
    
    def get_used_transaction_numbers(self, ref1, table_name='mutaties'):
        """Get existing transaction numbers for duplicate prevention"""
        return self.execute_query(f"SELECT Ref2 FROM {table_name} WHERE Ref1 = %s", (ref1,))
    
    def get_bank_account_lookups(self):
        """Get bank account lookup data"""
        return self.execute_query("SELECT rekeningNummer, Account, Administration FROM lookupbankaccounts_R")
    
    def get_existing_sequences(self, iban, table_name='mutaties'):
        """Get existing Ref2 sequences for a specific IBAN within last 2 years"""
        results = self.execute_query(f"""
            SELECT Ref2 as existing FROM {table_name} 
            WHERE Ref1 = %s AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
            AND Ref2 IS NOT NULL AND Ref2 != ''
        """, (iban,))
        return [r['existing'] for r in results]
    
    def get_patterns(self, administration):
        """Get patterns from vw_ReadReferences view"""
        return self.execute_query("""
            SELECT debet, credit, administration, referenceNumber 
            FROM vw_ReadReferences 
            WHERE administration = %s AND (debet < '1300' OR credit < '1300')
        """, (administration,))
    
    def get_recent_transactions(self, limit=100, table_name='mutaties'):
        """Get recent transactions for lookup data"""
        return self.execute_query(f"""
            SELECT TransactionDescription, Debet, Credit FROM {table_name} 
            ORDER BY ID DESC LIMIT %s
        """, (limit,))
    
    def get_last_transactions(self, reference_number, table_name='mutaties'):
        """Get last transactions for a specific reference number - matches R getLastTransactions exactly"""
        query = f"""
            SELECT * FROM {table_name} 
            WHERE TransactionNumber LIKE %s 
            AND TransactionDate = (
                SELECT MAX(TransactionDate) FROM {table_name} 
                WHERE TransactionNumber LIKE %s
            ) 
            ORDER BY Debet DESC
        """
        
        # Try with reference number first
        results = self.execute_query(query, (f"{reference_number}%", f"{reference_number}%"))
        
        # Fallback to Gamma if no results
        if not results:
            results = self.execute_query(query, ("Gamma%", "Gamma%"))
            for result in results:
                result['TransactionNumber'] = reference_number
                result['ReferenceNumber'] = reference_number
        
        # Ensure at least 2 records
        if len(results) < 2:
            if results:
                second_record = results[0].copy()
                second_record['Debet'] = '2010'
                second_record['Credit'] = results[0]['Debet']
                results.append(second_record)
            else:
                results = [
                    {'Debet': '4000', 'Credit': '1300', 'TransactionNumber': reference_number, 'ReferenceNumber': reference_number},
                    {'Debet': '2010', 'Credit': '4000', 'TransactionNumber': reference_number, 'ReferenceNumber': reference_number}
                ]
        
        return results
    
    def get_previous_transactions(self, reference_number, limit=3, table_name='mutaties'):
        """Get previous transactions with descriptions for AI pattern learning"""
        query = f"""
            SELECT TransactionDate as Datum, TransactionDescription as Omschrijving,
                   TransactionAmount as Bedrag, Debet, Credit
            FROM {table_name}
            WHERE ReferenceNumber LIKE %s
            ORDER BY TransactionDate DESC, ID DESC
            LIMIT %s
        """

        results = self.execute_query(query, (f"%{reference_number}%", limit))
        return results if results else []

    # Database optimization methods
    def get_migration_manager(self):
        """Get database migration manager"""
        from database_migrations import DatabaseMigration
        return DatabaseMigration(self.test_mode)

    def get_query_optimizer(self):
        """Get query optimizer with caching"""
        from database_migrations import QueryOptimizer
        return QueryOptimizer(self.test_mode)

    def optimize_database(self):
        """Run database optimization"""
        migrator = self.get_migration_manager()
        return migrator.optimize_database()

    def check_indexes(self):
        """Check database indexes"""
        migrator = self.get_migration_manager()
        return migrator.check_indexes()

    def create_recommended_indexes(self):
        """Create recommended indexes"""
        migrator = self.get_migration_manager()
        return migrator.create_recommended_indexes()

    def cleanup_database(self):
        """Run database cleanup"""
        migrator = self.get_migration_manager()
        return migrator.cleanup_database()

    def run_migrations(self):
        """Run pending migrations"""
        migrator = self.get_migration_manager()
        return migrator.run_all_migrations()

    def get_migration_status(self):
        """Get migration status"""
        migrator = self.get_migration_manager()
        return migrator.get_migration_status()

    def cached_query(self, query, params=None, cache_key=None, ttl=None):
        """Execute query with caching"""
        optimizer = self.get_query_optimizer()
        return optimizer.cached_query(query, params, cache_key, ttl)

    def analyze_query(self, query):
        """Analyze query performance"""
        optimizer = self.get_query_optimizer()
        return optimizer.analyze_query(query)

    def optimize_query(self, query):
        """Get query optimization suggestions"""
        optimizer = self.get_query_optimizer()
        return optimizer.optimize_query(query)

    def get_cache_stats(self):
        """Get query cache statistics"""
        optimizer = self.get_query_optimizer()
        return optimizer.get_cache_stats()

    def clear_query_cache(self):
        """Clear query cache"""
        optimizer = self.get_query_optimizer()
        return optimizer.clear_cache()
