"""
Unit tests for database_migrations module.

Tests migration tracking, version ordering logic, schema state queries,
and the QueryOptimizer caching/analysis functionality.

Requirements: 1.9, 2.2, 8.5
"""

import pytest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime

from database_migrations import DatabaseMigration, QueryOptimizer


class TestDatabaseMigrationInit:
    """Tests for DatabaseMigration initialization."""

    def test_init_creates_migrations_table(self, mock_db):
        """Test that __init__ creates the migrations tracking table."""
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)

        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert 'CREATE TABLE IF NOT EXISTS' in call_args[0][0]
        assert 'database_migrations' in call_args[0][0]


class TestGetAppliedMigrations:
    """Tests for _get_applied_migrations method."""

    @pytest.fixture
    def migration(self, mock_db):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
        # Reset mock after init call
        mock_db.execute_query.reset_mock()
        return dm

    def test_get_applied_migrations_returns_names(self, migration, mock_db):
        """Test that applied migrations are returned as a list of names."""
        mock_db.execute_query.return_value = [
            {'migration_name': 'add_users_table'},
            {'migration_name': 'add_index_email'},
        ]

        result = migration._get_applied_migrations()

        assert result == ['add_users_table', 'add_index_email']

    def test_get_applied_migrations_empty_returns_empty_list(self, migration, mock_db):
        """Test that no applied migrations returns empty list."""
        mock_db.execute_query.return_value = []

        result = migration._get_applied_migrations()

        assert result == []


class TestRecordMigration:
    """Tests for _record_migration method."""

    @pytest.fixture
    def migration(self, mock_db):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
        mock_db.execute_query.reset_mock()
        return dm

    def test_record_migration_inserts_with_success_status(self, migration, mock_db):
        """Test recording a successful migration."""
        migration._record_migration('test_migration', status='success', notes='Test notes')

        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert 'INSERT INTO' in call_args[0][0]
        assert call_args[0][1] == ('test_migration', 'success', 'Test notes')

    def test_record_migration_inserts_with_failed_status(self, migration, mock_db):
        """Test recording a failed migration."""
        migration._record_migration('bad_migration', status='failed', notes='Error occurred')

        call_args = mock_db.execute_query.call_args
        assert call_args[0][1] == ('bad_migration', 'failed', 'Error occurred')


class TestCreateMigration:
    """Tests for create_migration method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        return dm

    def test_create_migration_creates_json_file(self, migration):
        """Test that create_migration creates a properly formatted JSON file."""
        filepath = migration.create_migration('add_users', 'Add users table')

        assert os.path.exists(filepath)
        assert filepath.endswith('.json')

        with open(filepath, 'r') as f:
            content = json.load(f)

        assert content['name'] == 'add_users'
        assert content['description'] == 'Add users table'
        assert content['up'] == []
        assert content['down'] == []
        assert content['version'] == '1.0'
        assert 'timestamp' in content

    def test_create_migration_empty_name_raises_error(self, migration):
        """Test that empty migration name raises ValueError."""
        with pytest.raises(ValueError, match="Migration name is required"):
            migration.create_migration('', 'Description')

    def test_create_migration_filename_has_timestamp_prefix(self, migration):
        """Test that filename starts with timestamp."""
        filepath = migration.create_migration('test_mig', 'Test')

        filename = os.path.basename(filepath)
        # Filename format: YYYYMMDDHHMMSS_name.json
        parts = filename.split('_', 1)
        assert len(parts[0]) == 14  # timestamp length
        assert parts[0].isdigit()


class TestApplyMigration:
    """Tests for apply_migration method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        mock_db.execute_query.reset_mock()
        return dm

    def test_apply_migration_executes_up_queries(self, migration, mock_db, temp_dir):
        """Test that apply_migration executes all UP queries."""
        migration_data = {
            'name': 'add_column',
            'description': 'Add email column',
            'timestamp': '20240101120000',
            'up': ['ALTER TABLE users ADD COLUMN email VARCHAR(255)'],
            'down': ['ALTER TABLE users DROP COLUMN email'],
            'version': '1.0'
        }
        filepath = os.path.join(temp_dir, 'test_migration.json')
        with open(filepath, 'w') as f:
            json.dump(migration_data, f)

        # Mock _get_applied_migrations to return empty (not yet applied)
        with patch.object(migration, '_get_applied_migrations', return_value=[]):
            result = migration.apply_migration(filepath)

        assert result is True
        # Should have called execute_query for the UP query + recording
        assert mock_db.execute_query.call_count >= 2

    def test_apply_migration_already_applied_returns_false(self, migration, mock_db, temp_dir):
        """Test that already-applied migration returns False."""
        migration_data = {
            'name': 'existing_migration',
            'description': 'Already applied',
            'timestamp': '20240101120000',
            'up': ['SELECT 1'],
            'down': [],
            'version': '1.0'
        }
        filepath = os.path.join(temp_dir, 'test_migration.json')
        with open(filepath, 'w') as f:
            json.dump(migration_data, f)

        with patch.object(migration, '_get_applied_migrations', return_value=['existing_migration']):
            result = migration.apply_migration(filepath)

        assert result is False

    def test_apply_migration_failure_records_failed_status(self, migration, mock_db, temp_dir):
        """Test that failed migration records failure and re-raises."""
        migration_data = {
            'name': 'bad_migration',
            'description': 'Will fail',
            'timestamp': '20240101120000',
            'up': ['INVALID SQL'],
            'down': [],
            'version': '1.0'
        }
        filepath = os.path.join(temp_dir, 'test_migration.json')
        with open(filepath, 'w') as f:
            json.dump(migration_data, f)

        # First call for UP query raises, second for recording
        mock_db.execute_query.side_effect = [Exception("SQL Error"), None]

        with patch.object(migration, '_get_applied_migrations', return_value=[]):
            with pytest.raises(Exception, match="SQL Error"):
                migration.apply_migration(filepath)


class TestGetMigrationStatus:
    """Tests for get_migration_status method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        mock_db.execute_query.reset_mock()
        return dm

    def test_get_migration_status_counts_applied_and_pending(self, migration, temp_dir):
        """Test status correctly counts applied vs pending migrations."""
        # Create two migration files
        for name in ['mig_a', 'mig_b']:
            data = {'name': name, 'description': f'{name} desc', 'timestamp': '20240101120000', 'up': [], 'down': [], 'version': '1.0'}
            with open(os.path.join(temp_dir, f'{name}.json'), 'w') as f:
                json.dump(data, f)

        with patch.object(migration, '_get_applied_migrations', return_value=['mig_a']):
            result = migration.get_migration_status()

        assert result['total_migrations'] == 2
        assert result['applied_migrations'] == 1
        assert result['pending_migrations'] == 1

    def test_get_migration_status_empty_dir(self, migration, temp_dir):
        """Test status with no migration files."""
        with patch.object(migration, '_get_applied_migrations', return_value=[]):
            result = migration.get_migration_status()

        assert result['total_migrations'] == 0
        assert result['applied_migrations'] == 0
        assert result['pending_migrations'] == 0

    def test_get_migration_status_sorted_by_timestamp(self, migration, temp_dir):
        """Test that migrations are sorted by timestamp."""
        for ts, name in [('20240201', 'second'), ('20240101', 'first')]:
            data = {'name': name, 'description': '', 'timestamp': ts, 'up': [], 'down': [], 'version': '1.0'}
            with open(os.path.join(temp_dir, f'{ts}_{name}.json'), 'w') as f:
                json.dump(data, f)

        with patch.object(migration, '_get_applied_migrations', return_value=[]):
            result = migration.get_migration_status()

        assert result['migrations'][0]['name'] == 'first'
        assert result['migrations'][1]['name'] == 'second'


class TestQueryOptimizerCachedQuery:
    """Tests for QueryOptimizer.cached_query method."""

    @pytest.fixture
    def optimizer(self, mock_db):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            opt = QueryOptimizer(test_mode=True)
        return opt

    def test_cached_query_first_call_executes_query(self, optimizer, mock_db):
        """Test that first call executes the query."""
        mock_db.execute_query.return_value = [{'id': 1, 'name': 'test'}]

        result = optimizer.cached_query("SELECT * FROM users", cache_key='test_key')

        assert result == [{'id': 1, 'name': 'test'}]
        mock_db.execute_query.assert_called_once()

    def test_cached_query_second_call_uses_cache(self, optimizer, mock_db):
        """Test that second call returns cached result without DB query."""
        mock_db.execute_query.return_value = [{'id': 1}]

        # First call
        optimizer.cached_query("SELECT * FROM users", cache_key='cache_test')
        mock_db.execute_query.reset_mock()

        # Second call should use cache
        result = optimizer.cached_query("SELECT * FROM users", cache_key='cache_test')

        assert result == [{'id': 1}]
        mock_db.execute_query.assert_not_called()

    def test_clear_cache_empties_cache(self, optimizer, mock_db):
        """Test that clear_cache removes all cached entries."""
        mock_db.execute_query.return_value = [{'id': 1}]
        optimizer.cached_query("SELECT 1", cache_key='key1')

        optimizer.clear_cache()

        assert optimizer.query_cache == {}

    def test_get_cache_stats_returns_info(self, optimizer, mock_db):
        """Test cache stats reporting."""
        mock_db.execute_query.return_value = []
        optimizer.cached_query("SELECT 1", cache_key='stat_key')

        stats = optimizer.get_cache_stats()

        assert stats['cache_size'] == 1
        assert stats['cache_ttl'] == 300
        assert 'stat_key' in stats['cached_queries']


class TestQueryOptimizerAnalyzeQuery:
    """Tests for QueryOptimizer.analyze_query method."""

    @pytest.fixture
    def optimizer(self, mock_db):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            opt = QueryOptimizer(test_mode=True)
        return opt

    def test_analyze_query_returns_analysis(self, optimizer, mock_db):
        """Test that analyze_query returns analysis with recommendations."""
        mock_db.execute_query.return_value = [
            {'type': 'ALL', 'table': 'users', 'rows': 5000, 'Extra': 'Using filesort'}
        ]

        result = optimizer.analyze_query("SELECT * FROM users ORDER BY name")

        assert 'query' in result
        assert 'explain_result' in result
        assert 'recommendations' in result
        assert len(result['recommendations']) > 0

    def test_analyze_query_efficient_query_no_recommendations(self, optimizer, mock_db):
        """Test that efficient queries get fewer recommendations."""
        mock_db.execute_query.return_value = [
            {'type': 'const', 'table': 'users', 'rows': 1, 'Extra': ''}
        ]

        result = optimizer.analyze_query("SELECT * FROM users WHERE id = 1")

        assert result['recommendations'] == []

    def test_analyze_query_error_returns_error_dict(self, optimizer, mock_db):
        """Test that DB errors return error information."""
        mock_db.execute_query.side_effect = Exception("Table not found")

        result = optimizer.analyze_query("SELECT * FROM nonexistent")

        assert 'error' in result
        assert 'Table not found' in result['error']


class TestRollbackMigration:
    """Tests for rollback_migration method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        mock_db.execute_query.reset_mock()
        return dm

    def test_rollback_migration_executes_down_queries_in_reverse(self, migration, mock_db, temp_dir):
        """Test that rollback executes DOWN queries in reverse order."""
        migration_data = {
            'name': 'add_columns',
            'description': 'Add columns',
            'timestamp': '20240101120000',
            'up': ['ALTER TABLE users ADD COLUMN email VARCHAR(255)', 'ALTER TABLE users ADD COLUMN phone VARCHAR(50)'],
            'down': ['ALTER TABLE users DROP COLUMN email', 'ALTER TABLE users DROP COLUMN phone'],
            'version': '1.0'
        }
        filepath = os.path.join(temp_dir, '20240101120000_add_columns.json')
        with open(filepath, 'w') as f:
            json.dump(migration_data, f)

        result = migration.rollback_migration('add_columns')

        assert result is True
        # Should have executed down queries + delete from migrations table
        assert mock_db.execute_query.call_count >= 3

    def test_rollback_migration_not_found_raises_error(self, migration, temp_dir):
        """Test that missing migration file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            migration.rollback_migration('nonexistent_migration')

    def test_rollback_migration_removes_record(self, migration, mock_db, temp_dir):
        """Test that rollback removes the migration record from DB."""
        migration_data = {
            'name': 'test_mig',
            'description': 'Test',
            'timestamp': '20240101120000',
            'up': ['SELECT 1'],
            'down': ['SELECT 1'],
            'version': '1.0'
        }
        filepath = os.path.join(temp_dir, '20240101120000_test_mig.json')
        with open(filepath, 'w') as f:
            json.dump(migration_data, f)

        migration.rollback_migration('test_mig')

        # Check that DELETE was called
        calls = [str(c) for c in mock_db.execute_query.call_args_list]
        assert any('DELETE' in c for c in calls)

    def test_rollback_migration_failure_raises(self, migration, mock_db, temp_dir):
        """Test that rollback failure raises exception."""
        migration_data = {
            'name': 'fail_mig',
            'description': 'Will fail',
            'timestamp': '20240101120000',
            'up': ['SELECT 1'],
            'down': ['INVALID SQL'],
            'version': '1.0'
        }
        filepath = os.path.join(temp_dir, '20240101120000_fail_mig.json')
        with open(filepath, 'w') as f:
            json.dump(migration_data, f)

        mock_db.execute_query.side_effect = Exception("Rollback SQL Error")

        with pytest.raises(Exception, match="Rollback SQL Error"):
            migration.rollback_migration('fail_mig')


class TestRunAllMigrations:
    """Tests for run_all_migrations method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        mock_db.execute_query.reset_mock()
        return dm

    def test_run_all_migrations_applies_pending(self, migration, mock_db, temp_dir):
        """Test that all pending migrations are applied."""
        # Create two migration files
        for i, name in enumerate(['first', 'second']):
            data = {'name': name, 'description': f'{name} migration', 'timestamp': f'2024010{i}120000', 'up': [f'CREATE TABLE {name} (id INT)'], 'down': [], 'version': '1.0'}
            with open(os.path.join(temp_dir, f'2024010{i}120000_{name}.json'), 'w') as f:
                json.dump(data, f)

        with patch.object(migration, '_get_applied_migrations', return_value=[]):
            result = migration.run_all_migrations()

        assert result == 2

    def test_run_all_migrations_skips_already_applied(self, migration, mock_db, temp_dir):
        """Test that already-applied migrations are skipped."""
        data = {'name': 'existing', 'description': 'Already done', 'timestamp': '20240101120000', 'up': ['SELECT 1'], 'down': [], 'version': '1.0'}
        with open(os.path.join(temp_dir, '20240101120000_existing.json'), 'w') as f:
            json.dump(data, f)

        with patch.object(migration, '_get_applied_migrations', return_value=['existing']):
            with patch.object(migration, 'apply_migration', return_value=False) as mock_apply:
                result = migration.run_all_migrations()

        assert result == 0

    def test_run_all_migrations_stops_on_failure(self, migration, mock_db, temp_dir):
        """Test that migration stops on first failure."""
        for i, name in enumerate(['good', 'bad', 'never']):
            data = {'name': name, 'description': '', 'timestamp': f'2024010{i}120000', 'up': ['SELECT 1'], 'down': [], 'version': '1.0'}
            with open(os.path.join(temp_dir, f'2024010{i}120000_{name}.json'), 'w') as f:
                json.dump(data, f)

        call_count = [0]
        def mock_apply(filepath):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Migration failed")
            return True

        with patch.object(migration, '_get_applied_migrations', return_value=[]):
            with patch.object(migration, 'apply_migration', side_effect=mock_apply):
                result = migration.run_all_migrations()

        # Only the first one should have been counted as applied
        assert result == 1

    def test_run_all_migrations_empty_dir_returns_zero(self, migration, temp_dir):
        """Test that empty migrations dir returns 0."""
        with patch.object(migration, '_get_applied_migrations', return_value=[]):
            result = migration.run_all_migrations()

        assert result == 0


class TestOptimizeDatabase:
    """Tests for optimize_database method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        mock_db.execute_query.reset_mock()
        return dm

    def test_optimize_database_runs_all_queries(self, migration, mock_db):
        """Test that all optimization queries are executed."""
        mock_db.execute_query.return_value = [{'status': 'OK'}]

        result = migration.optimize_database()

        assert len(result) == 8  # 4 OPTIMIZE + 4 ANALYZE
        assert all(r['success'] is True for r in result)

    def test_optimize_database_handles_errors(self, migration, mock_db):
        """Test that individual query errors are captured."""
        mock_db.execute_query.side_effect = [
            [{'status': 'OK'}],
            Exception("Table not found"),
            [{'status': 'OK'}],
            Exception("Permission denied"),
            [{'status': 'OK'}],
            [{'status': 'OK'}],
            [{'status': 'OK'}],
            [{'status': 'OK'}],
        ]

        result = migration.optimize_database()

        assert len(result) == 8
        success_count = sum(1 for r in result if r['success'])
        failure_count = sum(1 for r in result if not r['success'])
        assert success_count == 6
        assert failure_count == 2


class TestCheckIndexes:
    """Tests for check_indexes method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        mock_db.execute_query.reset_mock()
        return dm

    def test_check_indexes_returns_report(self, migration, mock_db):
        """Test that index check returns report for each table."""
        # First call: table exists check, second: show indexes
        mock_db.execute_query.side_effect = [
            [{'count': 1}], [{'Key_name': 'PRIMARY', 'Column_name': 'id'}],
            [{'count': 1}], [{'Key_name': 'PRIMARY', 'Column_name': 'id'}],
            [{'count': 1}], [{'Key_name': 'PRIMARY', 'Column_name': 'id'}],
            [{'count': 1}], [{'Key_name': 'PRIMARY', 'Column_name': 'id'}],
        ]

        result = migration.check_indexes()

        assert len(result) == 4
        assert all('table' in r for r in result)

    def test_check_indexes_table_not_exists(self, migration, mock_db):
        """Test handling when table doesn't exist."""
        mock_db.execute_query.side_effect = [
            [{'count': 0}],  # mutaties doesn't exist
            [{'count': 0}],  # mutaties_test doesn't exist
            [{'count': 0}],  # bnb doesn't exist
            [{'count': 0}],  # bnbplanned doesn't exist
        ]

        result = migration.check_indexes()

        # Tables that don't exist should not be in the report
        assert len(result) == 0

    def test_check_indexes_handles_errors(self, migration, mock_db):
        """Test that errors are captured in the report."""
        mock_db.execute_query.side_effect = Exception("Access denied")

        result = migration.check_indexes()

        assert len(result) == 4
        assert all('error' in r for r in result)


class TestCreateRecommendedIndexes:
    """Tests for create_recommended_indexes method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        mock_db.execute_query.reset_mock()
        return dm

    def test_create_recommended_indexes_creates_new(self, migration, mock_db):
        """Test creating indexes that don't exist yet."""
        # For each index: first call checks if exists (empty = doesn't exist), second creates it
        mock_db.execute_query.side_effect = [
            [],  # index doesn't exist
            None,  # create index
        ] * 10  # 10 recommended indexes

        result = migration.create_recommended_indexes()

        assert len(result) == 10
        assert all(r['status'] == 'created' for r in result)

    def test_create_recommended_indexes_skips_existing(self, migration, mock_db):
        """Test that existing indexes are skipped."""
        mock_db.execute_query.side_effect = [
            [{'Key_name': 'idx_transaction_date'}],  # index exists
        ] * 10

        result = migration.create_recommended_indexes()

        assert len(result) == 10
        assert all(r['status'] == 'exists' for r in result)

    def test_create_recommended_indexes_handles_errors(self, migration, mock_db):
        """Test that creation errors are captured."""
        mock_db.execute_query.side_effect = [
            [],  # index doesn't exist
            Exception("Permission denied"),  # create fails
        ] * 10

        result = migration.create_recommended_indexes()

        assert len(result) == 10
        assert all(r['status'] == 'failed' for r in result)


class TestCleanupDatabase:
    """Tests for cleanup_database method."""

    @pytest.fixture
    def migration(self, mock_db, temp_dir):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            with patch('os.makedirs'):
                dm = DatabaseMigration(test_mode=True)
                dm.migrations_dir = temp_dir
        mock_db.execute_query.reset_mock()
        return dm

    def test_cleanup_database_runs_all_queries(self, migration, mock_db):
        """Test that all cleanup queries are executed."""
        mock_db.execute_query.return_value = 5  # affected rows

        result = migration.cleanup_database()

        assert len(result) == 3
        assert all(r['success'] is True for r in result)
        assert all(r['affected_rows'] == 5 for r in result)

    def test_cleanup_database_handles_errors(self, migration, mock_db):
        """Test that individual query errors are captured."""
        mock_db.execute_query.side_effect = [
            5,  # first query succeeds
            Exception("Foreign key constraint"),  # second fails
            3,  # third succeeds
        ]

        result = migration.cleanup_database()

        assert len(result) == 3
        assert result[0]['success'] is True
        assert result[1]['success'] is False
        assert result[2]['success'] is True


class TestQueryOptimizerOptimizeQuery:
    """Tests for QueryOptimizer.optimize_query method."""

    @pytest.fixture
    def optimizer(self, mock_db):
        with patch('database_migrations.DatabaseManager', return_value=mock_db):
            opt = QueryOptimizer(test_mode=True)
        return opt

    def test_optimize_query_with_like(self, optimizer, mock_db):
        """Test optimization suggestion for LIKE queries."""
        mock_db.execute_query.return_value = [{'type': 'ALL', 'table': 'users', 'rows': 100, 'Extra': ''}]

        result = optimizer.optimize_query("SELECT * FROM users WHERE name LIKE '%test%'")

        assert 'original_query' in result
        assert 'optimized_queries' in result
        assert any('LIKE' in q.get('note', '') or 'exact' in q.get('note', '') for q in result['optimized_queries'])

    def test_optimize_query_with_select_star(self, optimizer, mock_db):
        """Test optimization suggestion for SELECT * queries."""
        mock_db.execute_query.return_value = [{'type': 'ALL', 'table': 'users', 'rows': 100, 'Extra': ''}]

        result = optimizer.optimize_query("SELECT * FROM users WHERE id = 1")

        assert any('column' in q.get('note', '').lower() for q in result['optimized_queries'])

    def test_optimize_query_no_patterns(self, optimizer, mock_db):
        """Test query without optimization patterns."""
        mock_db.execute_query.return_value = [{'type': 'const', 'table': 'users', 'rows': 1, 'Extra': ''}]

        result = optimizer.optimize_query("SELECT name FROM users WHERE id = 1")

        assert result['original_query'] == "SELECT name FROM users WHERE id = 1"
