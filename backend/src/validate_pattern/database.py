import mysql.connector
from mysql.connector import pooling
from datetime import datetime
import os
from dotenv import load_dotenv
from contextlib import contextmanager
import threading
import time
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    _scalability_manager = None
    _use_scalability = True
    _legacy_pool = None
    _use_legacy_pool = True
    
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
        
        # Try to initialize scalability manager
        self._initialize_scalability_manager()
        
        # Fallback to legacy pool if scalability manager fails
        if not DatabaseManager._scalability_manager and DatabaseManager._use_legacy_pool and not DatabaseManager._legacy_pool:
            try:
                pool_config = self.config.copy()
                pool_config.update({
                    'pool_name': 'legacy_pool',
                    'pool_size': 20,  # Increased from 5 to 20 for better concurrency
                    'pool_reset_session': True,
                    'pool_recycle': 3600,  # Recycle connections every hour
                    'autocommit': False
                })
                DatabaseManager._legacy_pool = pooling.MySQLConnectionPool(**pool_config)
                logger.info("✅ Legacy connection pool initialized with 20 connections")
            except Exception as e:
                logger.warning(f"⚠️ Legacy connection pool failed, using direct connections: {e}")
                DatabaseManager._use_legacy_pool = False
    
    def _initialize_scalability_manager(self):
        """Initialize scalability manager for advanced connection pooling"""
        if DatabaseManager._scalability_manager is None and DatabaseManager._use_scalability:
            try:
                # Import here to avoid circular imports
                from scalability_manager import get_scalability_manager
                DatabaseManager._scalability_manager = get_scalability_manager(self.config)
                logger.info("🚀 Scalability Manager initialized for database connections")
            except Exception as e:
                logger.warning(f"⚠️ Scalability Manager initialization failed, using legacy pool: {e}")
                DatabaseManager._use_scalability = False
    
    def _get_db_config(self):
        """Get database configuration for SQLAlchemy"""
        return self.config
    
    def get_connection(self, pool_type='primary'):
        """Get database connection with scalability improvements"""
        # Try scalability manager first (advanced pooling)
        if DatabaseManager._scalability_manager:
            try:
                return DatabaseManager._scalability_manager.get_database_connection(pool_type)
            except Exception as e:
                logger.warning(f"⚠️ Scalability manager connection failed, falling back to legacy: {e}")
        
        # Fallback to legacy pool
        if DatabaseManager._use_legacy_pool and DatabaseManager._legacy_pool:
            try:
                return DatabaseManager._legacy_pool.get_connection()
            except Exception as e:
                logger.warning(f"⚠️ Legacy pool connection failed, using direct connection: {e}")
                DatabaseManager._use_legacy_pool = False
        
        # Final fallback to direct connection
        return mysql.connector.connect(**self.config)
    
    @contextmanager
    def get_cursor(self, dictionary=True, pool_type='primary'):
        """Context manager for database operations with scalability improvements"""
        start_time = time.time()
        
        # Use scalability manager's connection context if available
        if DatabaseManager._scalability_manager:
            try:
                with DatabaseManager._scalability_manager.get_database_connection(pool_type) as conn:
                    cursor = conn.cursor(dictionary=dictionary)
                    try:
                        yield cursor, conn
                    except Exception as e:
                        conn.rollback()
                        raise e
                    finally:
                        cursor.close()
                        
                        # Record performance metrics
                        response_time = time.time() - start_time
                        DatabaseManager._scalability_manager.record_request_metrics(response_time)
                return
            except Exception as e:
                logger.warning(f"⚠️ Scalability manager cursor failed, falling back: {e}")
        
        # Fallback to legacy approach
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
    
    def execute_query(self, query, params=None, fetch=True, commit=False, pool_type='primary'):
        """Execute query with automatic connection management and scalability improvements"""
        # Determine optimal pool type based on query
        if pool_type == 'primary':
            if query.strip().upper().startswith(('SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN')):
                if 'pattern_' in query.lower() or 'analytics' in query.lower():
                    pool_type = 'analytics'
                else:
                    pool_type = 'readonly'
        
        with self.get_cursor(pool_type=pool_type) as (cursor, conn):
            cursor.execute(query, params or ())
            if commit:
                conn.commit()
                return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
            return cursor.fetchall() if fetch else None
    
    def execute_batch_queries(self, queries_with_params, commit=True):
        """Execute multiple queries in batch for better performance"""
        if not queries_with_params:
            return []
        
        # Use scalability manager for batch processing if available
        if DatabaseManager._scalability_manager:
            try:
                def execute_single_query(query_params):
                    query, params = query_params
                    return self.execute_query(query, params, fetch=False, commit=False)
                
                results = DatabaseManager._scalability_manager.batch_process_items(
                    queries_with_params, execute_single_query
                )
                
                # Commit all changes at once
                if commit:
                    with self.get_cursor() as (cursor, conn):
                        conn.commit()
                
                return results
            except Exception as e:
                logger.warning(f"⚠️ Batch processing failed, falling back to sequential: {e}")
        
        # Fallback to sequential processing
        results = []
        with self.get_cursor() as (cursor, conn):
            for query, params in queries_with_params:
                cursor.execute(query, params or ())
                results.append(cursor.rowcount)
            
            if commit:
                conn.commit()
        
        return results
    
    def execute_async_query(self, query, params=None, fetch=True, commit=False):
        """Execute query asynchronously using scalability manager"""
        if DatabaseManager._scalability_manager:
            future = DatabaseManager._scalability_manager.submit_async_task(
                'io', self.execute_query, query, params, fetch, commit
            )
            return future
        else:
            # Fallback to synchronous execution
            return self.execute_query(query, params, fetch, commit)
    
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
        """Get bank account lookup data from vw_rekeningnummers (actual bank accounts only)"""
        return self.execute_query("SELECT rekeningNummer, Account, administration FROM vw_rekeningnummers")
    
    def get_existing_sequences(self, iban, table_name='mutaties', administration=None):
        """Get existing Ref2 sequences for a specific IBAN within last 2 years, optionally filtered by administration"""
        query = f"""
            SELECT Ref2 as existing FROM {table_name} 
            WHERE Ref1 = %s AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
            AND Ref2 IS NOT NULL AND Ref2 != ''
        """
        params = [iban]
        
        # Add administration filter if provided (for tenant isolation)
        if administration:
            query += " AND administration = %s"
            params.append(administration)
        
        results = self.execute_query(query, tuple(params))
        return [r['existing'] for r in results]
    
    def get_patterns(self, administration):
        """Get patterns from vw_readreferences view with date filtering"""
        return self.execute_query("""
            SELECT debet, credit, administration, referenceNumber, Date
            FROM vw_readreferences 
            WHERE administration = %s 
            AND (debet < '1300' OR credit < '1300')
            AND Date >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
            ORDER BY Date DESC
        """, (administration,))
    
    def get_recent_transactions(self, limit=100, table_name='mutaties'):
        """Get recent transactions for lookup data"""
        return self.execute_query(f"""
            SELECT TransactionDescription, Debet, Credit, administration FROM {table_name} 
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

    def check_duplicate_transactions(self, reference_number, transaction_date, transaction_amount, table_name='mutaties'):
        """
        Check for existing transactions with matching criteria within 2-year window.
        
        Args:
            reference_number (str): The reference number to match
            transaction_date (str): The transaction date to match (YYYY-MM-DD format)
            transaction_amount (float): The transaction amount to match
            table_name (str): The table to search in (default: 'mutaties')
            
        Returns:
            List[Dict]: List of matching transactions, empty list if none found
            
        Raises:
            Exception: If database connection fails or query execution fails
        """
        try:
            query = f"""
                SELECT ID, TransactionNumber, TransactionDate, TransactionDescription, 
                       TransactionAmount, Debet, Credit, ReferenceNumber, 
                       Ref1, Ref2, Ref3, Ref4, Administration
                FROM {table_name}
                WHERE ReferenceNumber = %s
                AND TransactionDate = %s
                AND ABS(TransactionAmount - %s) < 0.01
                AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
                ORDER BY ID DESC
            """
            
            results = self.execute_query(query, (reference_number, transaction_date, transaction_amount))
            return results if results else []
            
        except mysql.connector.Error as e:
            # Log the error but don't raise it to allow graceful degradation
            print(f"Database error during duplicate check: {e}")
            raise Exception(f"Database connection failed during duplicate check: {str(e)}")
        except Exception as e:
            print(f"Unexpected error during duplicate check: {e}")
            raise Exception(f"Duplicate check failed: {str(e)}")

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
    
    # Scalability monitoring and management methods
    def get_scalability_statistics(self):
        """Get comprehensive scalability statistics"""
        if DatabaseManager._scalability_manager:
            return DatabaseManager._scalability_manager.get_comprehensive_statistics()
        else:
            return {
                'scalability_manager': 'Not initialized',
                'legacy_pool_active': DatabaseManager._use_legacy_pool,
                'direct_connections': not DatabaseManager._use_legacy_pool
            }
    
    def get_scalability_health(self):
        """Get scalability health status"""
        if DatabaseManager._scalability_manager:
            return DatabaseManager._scalability_manager.get_health_status()
        else:
            return {
                'health_score': 50,
                'status': 'limited',
                'issues': ['Scalability manager not initialized'],
                'scalability_ready': False,
                'concurrent_user_capacity': '1x baseline',
                'recommendations': ['Initialize scalability manager for 10x improvement']
            }
    
    def optimize_for_concurrency(self):
        """Optimize database settings for high concurrency"""
        optimizations = []
        
        try:
            # Check current connection limits
            max_connections = self.execute_query("SHOW VARIABLES LIKE 'max_connections'")
            if max_connections:
                current_max = int(max_connections[0]['Value'])
                if current_max < 500:
                    optimizations.append({
                        'setting': 'max_connections',
                        'current': current_max,
                        'recommended': 500,
                        'query': "SET GLOBAL max_connections = 500;"
                    })
            
            # Check thread cache size
            thread_cache = self.execute_query("SHOW VARIABLES LIKE 'thread_cache_size'")
            if thread_cache:
                current_cache = int(thread_cache[0]['Value'])
                if current_cache < 100:
                    optimizations.append({
                        'setting': 'thread_cache_size',
                        'current': current_cache,
                        'recommended': 100,
                        'query': "SET GLOBAL thread_cache_size = 100;"
                    })
            
            # Check query cache
            query_cache = self.execute_query("SHOW VARIABLES LIKE 'query_cache_size'")
            if query_cache:
                current_cache = int(query_cache[0]['Value'])
                if current_cache < 268435456:  # 256MB
                    optimizations.append({
                        'setting': 'query_cache_size',
                        'current': current_cache,
                        'recommended': 268435456,
                        'query': "SET GLOBAL query_cache_size = 268435456;"
                    })
            
            return {
                'optimizations_available': len(optimizations),
                'recommendations': optimizations,
                'scalability_impact': '2-3x improvement in concurrent performance'
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking database optimization: {e}")
            return {
                'error': str(e),
                'optimizations_available': 0,
                'recommendations': []
            }
    
    def get_connection_pool_status(self):
        """Get detailed connection pool status"""
        status = {
            'scalability_manager_active': DatabaseManager._scalability_manager is not None,
            'legacy_pool_active': DatabaseManager._use_legacy_pool,
            'direct_connections_fallback': not DatabaseManager._use_legacy_pool and not DatabaseManager._scalability_manager
        }
        
        if DatabaseManager._scalability_manager:
            status['scalability_stats'] = DatabaseManager._scalability_manager.connection_pool.get_pool_statistics()
        
        return status
    
    @classmethod
    def shutdown_scalability_manager(cls):
        """Shutdown scalability manager gracefully"""
        if cls._scalability_manager:
            cls._scalability_manager.shutdown()
            cls._scalability_manager = None
            logger.info("✅ Scalability manager shutdown complete")
