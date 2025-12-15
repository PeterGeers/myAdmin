import os
import json
from datetime import datetime
from database import DatabaseManager

class DatabaseMigration:
    """Database migration system for schema changes and data updates"""

    def __init__(self, test_mode=False):
        self.db = DatabaseManager(test_mode=test_mode)
        self.migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
        self.migrations_table = 'database_migrations'
        os.makedirs(self.migrations_dir, exist_ok=True)

        # Create migrations table if it doesn't exist
        self._create_migrations_table()

    def _create_migrations_table(self):
        """Create table to track applied migrations"""
        self.db.execute_query(f"""
            CREATE TABLE IF NOT EXISTS {self.migrations_table} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                migration_name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'success',
                notes TEXT
            )
        """, fetch=False, commit=True)

    def _get_applied_migrations(self):
        """Get list of already applied migrations"""
        results = self.db.execute_query(f"SELECT migration_name FROM {self.migrations_table}")
        return [row['migration_name'] for row in results]

    def _record_migration(self, migration_name, status='success', notes=None):
        """Record a migration in the database"""
        self.db.execute_query(f"""
            INSERT INTO {self.migrations_table} (migration_name, status, notes)
            VALUES (%s, %s, %s)
        """, (migration_name, status, notes), fetch=False, commit=True)

    def create_migration(self, migration_name, description):
        """Create a new migration file"""
        if not migration_name:
            raise ValueError("Migration name is required")

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{timestamp}_{migration_name}.json"
        filepath = os.path.join(self.migrations_dir, filename)

        migration_template = {
            "name": migration_name,
            "description": description,
            "timestamp": timestamp,
            "up": [],
            "down": [],
            "version": "1.0"
        }

        with open(filepath, 'w') as f:
            json.dump(migration_template, f, indent=2)

        return filepath

    def apply_migration(self, migration_file):
        """Apply a specific migration"""
        try:
            with open(migration_file, 'r') as f:
                migration = json.load(f)

            applied_migrations = self._get_applied_migrations()
            if migration['name'] in applied_migrations:
                print(f"Migration {migration['name']} already applied")
                return False

            print(f"Applying migration: {migration['name']} - {migration['description']}")

            # Execute UP queries
            for query in migration['up']:
                print(f"Executing: {query[:100]}...")
                self.db.execute_query(query, fetch=False, commit=True)

            # Record successful migration
            self._record_migration(migration['name'], notes=migration['description'])
            print(f"Migration {migration['name']} applied successfully")
            return True

        except Exception as e:
            error_msg = f"Migration failed: {str(e)}"
            print(error_msg)
            self._record_migration(migration['name'], status='failed', notes=error_msg)
            raise

    def rollback_migration(self, migration_name):
        """Rollback a specific migration"""
        try:
            # Find the migration file
            migration_file = None
            for filename in os.listdir(self.migrations_dir):
                if filename.startswith(migration_name) or migration_name in filename:
                    migration_file = os.path.join(self.migrations_dir, filename)
                    break

            if not migration_file:
                raise FileNotFoundError(f"Migration {migration_name} not found")

            with open(migration_file, 'r') as f:
                migration = json.load(f)

            print(f"Rolling back migration: {migration['name']}")

            # Execute DOWN queries in reverse order
            for query in reversed(migration['down']):
                print(f"Executing rollback: {query[:100]}...")
                self.db.execute_query(query, fetch=False, commit=True)

            # Remove migration record
            self.db.execute_query(f"""
                DELETE FROM {self.migrations_table} WHERE migration_name = %s
            """, (migration['name'],), fetch=False, commit=True)

            print(f"Migration {migration['name']} rolled back successfully")
            return True

        except Exception as e:
            error_msg = f"Rollback failed: {str(e)}"
            print(error_msg)
            raise

    def run_all_migrations(self):
        """Run all pending migrations"""
        applied_migrations = self._get_applied_migrations()

        # Get all migration files sorted by timestamp
        migration_files = []
        for filename in os.listdir(self.migrations_dir):
            if filename.endswith('.json'):
                migration_files.append(filename)

        migration_files.sort()  # Sort by timestamp prefix

        applied_count = 0
        for filename in migration_files:
            filepath = os.path.join(self.migrations_dir, filename)
            with open(filepath, 'r') as f:
                migration = json.load(f)

            if migration['name'] not in applied_migrations:
                try:
                    self.apply_migration(filepath)
                    applied_count += 1
                except Exception as e:
                    print(f"Failed to apply {migration['name']}: {e}")
                    break

        print(f"Applied {applied_count} migrations")
        return applied_count

    def get_migration_status(self):
        """Get status of all migrations"""
        applied_migrations = self._get_applied_migrations()

        status = {
            'total_migrations': 0,
            'applied_migrations': len(applied_migrations),
            'pending_migrations': 0,
            'migrations': []
        }

        # Get all migration files
        migration_files = []
        for filename in os.listdir(self.migrations_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.migrations_dir, filename)
                with open(filepath, 'r') as f:
                    migration = json.load(f)
                    migration['filename'] = filename
                    migration['applied'] = migration['name'] in applied_migrations
                    migration_files.append(migration)

        # Sort by timestamp
        migration_files.sort(key=lambda x: x['timestamp'])

        status['total_migrations'] = len(migration_files)
        status['pending_migrations'] = len([m for m in migration_files if not m['applied']])
        status['migrations'] = migration_files

        return status

    def optimize_database(self):
        """Run database optimization queries"""
        optimizations = [
            "OPTIMIZE TABLE mutaties",
            "OPTIMIZE TABLE mutaties_test",
            "OPTIMIZE TABLE bnb",
            "OPTIMIZE TABLE bnbplanned",
            "ANALYZE TABLE mutaties",
            "ANALYZE TABLE mutaties_test",
            "ANALYZE TABLE bnb",
            "ANALYZE TABLE bnbplanned"
        ]

        results = []
        for query in optimizations:
            try:
                result = self.db.execute_query(query)
                results.append({
                    'query': query,
                    'success': True,
                    'result': result
                })
            except Exception as e:
                results.append({
                    'query': query,
                    'success': False,
                    'error': str(e)
                })

        return results

    def check_indexes(self):
        """Check and report on database indexes"""
        tables = ['mutaties', 'mutaties_test', 'bnb', 'bnbplanned']

        index_report = []
        for table in tables:
            try:
                # Check if table exists first
                table_exists = self.db.execute_query(f"""
                    SELECT COUNT(*) as count FROM information_schema.tables
                    WHERE table_schema = DATABASE() AND table_name = %s
                """, (table,))

                if table_exists and table_exists[0]['count'] > 0:
                    indexes = self.db.execute_query(f"""
                        SHOW INDEXES FROM {table}
                    """)

                    table_report = {
                        'table': table,
                        'indexes': indexes,
                        'index_count': len(indexes) if indexes else 0
                    }
                    index_report.append(table_report)
            except Exception as e:
                index_report.append({
                    'table': table,
                    'error': str(e)
                })

        return index_report

    def create_recommended_indexes(self):
        """Create recommended indexes for performance"""
        recommended_indexes = [
            # For mutaties tables
            ("mutaties", "idx_transaction_date", "TransactionDate"),
            ("mutaties", "idx_ref1_ref2", "Ref1, Ref2"),
            ("mutaties", "idx_administration", "Administration"),
            ("mutaties_test", "idx_transaction_date", "TransactionDate"),
            ("mutaties_test", "idx_ref1_ref2", "Ref1, Ref2"),
            ("mutaties_test", "idx_administration", "Administration"),

            # For bnb tables
            ("bnb", "idx_checkin_date", "checkinDate"),
            ("bnb", "idx_listing", "listing"),
            ("bnbplanned", "idx_checkin_date", "checkinDate"),
            ("bnbplanned", "idx_listing", "listing")
        ]

        results = []
        for table, index_name, columns in recommended_indexes:
            try:
                # Check if index already exists
                existing_indexes = self.db.execute_query(f"""
                    SHOW INDEXES FROM {table} WHERE Key_name = %s
                """, (index_name,))

                if not existing_indexes:
                    create_query = f"CREATE INDEX {index_name} ON {table} ({columns})"
                    self.db.execute_query(create_query, fetch=False, commit=True)
                    results.append({
                        'table': table,
                        'index': index_name,
                        'columns': columns,
                        'status': 'created'
                    })
                else:
                    results.append({
                        'table': table,
                        'index': index_name,
                        'columns': columns,
                        'status': 'exists'
                    })
            except Exception as e:
                results.append({
                    'table': table,
                    'index': index_name,
                    'columns': columns,
                    'status': 'failed',
                    'error': str(e)
                })

        return results

    def cleanup_database(self):
        """Run database cleanup operations"""
        cleanup_queries = [
            # Remove duplicate transactions
            """
            DELETE t1 FROM mutaties t1
            INNER JOIN mutaties t2
            WHERE t1.ID < t2.ID AND
                  t1.Ref1 = t2.Ref1 AND
                  t1.Ref2 = t2.Ref2 AND
                  t1.TransactionDate = t2.TransactionDate AND
                  t1.TransactionAmount = t2.TransactionAmount
            """,
            # Remove transactions with empty references
            "DELETE FROM mutaties WHERE Ref1 IS NULL OR Ref1 = '' OR Ref2 IS NULL OR Ref2 = ''",
            # Remove old temporary records
            "DELETE FROM mutaties WHERE TransactionDescription LIKE '%TEMP%' AND TransactionDate < (CURDATE() - INTERVAL 1 YEAR)"
        ]

        results = []
        for query in cleanup_queries:
            try:
                result = self.db.execute_query(query, fetch=False, commit=True)
                results.append({
                    'query': query[:50] + '...',
                    'affected_rows': result,
                    'success': True
                })
            except Exception as e:
                results.append({
                    'query': query[:50] + '...',
                    'success': False,
                    'error': str(e)
                })

        return results

# Query optimization and caching
class QueryOptimizer:
    """Query optimization and caching utilities"""

    def __init__(self, test_mode=False):
        self.db = DatabaseManager(test_mode=test_mode)
        self.query_cache = {}
        self.cache_ttl = 300  # 5 minutes

    def cached_query(self, query, params=None, cache_key=None, ttl=None):
        """Execute query with caching"""
        if not cache_key:
            cache_key = f"{query}_{str(params)}"

        # Check cache first
        cached_result = self.query_cache.get(cache_key)
        if cached_result and ('timestamp' not in cached_result or
                            (datetime.now() - cached_result['timestamp']).seconds < (ttl or self.cache_ttl)):
            return cached_result['data']

        # Execute query
        result = self.db.execute_query(query, params)

        # Cache result
        self.query_cache[cache_key] = {
            'data': result,
            'timestamp': datetime.now(),
            'query': query,
            'params': params
        }

        return result

    def clear_cache(self):
        """Clear all cached queries"""
        self.query_cache.clear()

    def get_cache_stats(self):
        """Get cache statistics"""
        return {
            'cache_size': len(self.query_cache),
            'cache_ttl': self.cache_ttl,
            'cached_queries': list(self.query_cache.keys())
        }

    def analyze_query(self, query):
        """Analyze query performance"""
        try:
            # Add EXPLAIN to the query
            explain_query = f"EXPLAIN {query}"
            result = self.db.execute_query(explain_query)

            analysis = {
                'query': query,
                'explain_result': result,
                'recommendations': []
            }

            # Basic analysis
            for row in result:
                if row.get('type') and row['type'] not in ['const', 'eq_ref', 'ref']:
                    analysis['recommendations'].append(
                        f"Consider adding indexes for table {row.get('table')} - access type is {row['type']}"
                    )

                if row.get('rows') and row['rows'] > 1000:
                    analysis['recommendations'].append(
                        f"Query scans {row['rows']} rows - consider optimizing with better indexes or query structure"
                    )

                if row.get('Extra') and 'Using filesort' in row['Extra']:
                    analysis['recommendations'].append(
                        "Query uses filesort - consider adding appropriate indexes to avoid sorting"
                    )

                if row.get('Extra') and 'Using temporary' in row['Extra']:
                    analysis['recommendations'].append(
                        "Query uses temporary tables - consider optimizing query to avoid temporary tables"
                    )

            return analysis

        except Exception as e:
            return {
                'query': query,
                'error': str(e)
            }

    def optimize_query(self, query):
        """Suggest optimizations for a query"""
        analysis = self.analyze_query(query)

        optimizations = {
            'original_query': query,
            'analysis': analysis,
            'optimized_queries': []
        }

        # Simple optimization patterns
        if 'WHERE' in query.upper() and 'LIKE' in query.upper():
            optimizations['optimized_queries'].append({
                'note': 'Consider using exact matches instead of LIKE where possible',
                'query': query.replace('LIKE', '=')
            })

        if 'SELECT *' in query.upper():
            optimizations['optimized_queries'].append({
                'note': 'Specify only needed columns instead of SELECT *',
                'query': query.replace('SELECT *', 'SELECT column1, column2')  # Example
            })

        return optimizations
