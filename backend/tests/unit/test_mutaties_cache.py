"""
Unit tests for mutaties_cache module.

Tests cache invalidation, TTL expiry, data loading, on-demand year loading,
and the global cache singleton pattern.
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime, timedelta

from mutaties_cache import MutatiesCache, get_cache, invalidate_cache


class TestMutatiesCacheInit:
    """Tests for MutatiesCache initialization."""

    def test_init_default_ttl_thirty_minutes(self):
        """Default TTL is 30 minutes."""
        cache = MutatiesCache()
        assert cache.ttl == timedelta(minutes=30)

    def test_init_custom_ttl(self):
        """Custom TTL is set correctly."""
        cache = MutatiesCache(ttl_minutes=60)
        assert cache.ttl == timedelta(minutes=60)

    def test_init_data_is_none(self):
        """Initial data is None."""
        cache = MutatiesCache()
        assert cache.data is None

    def test_init_last_loaded_is_none(self):
        """Initial last_loaded is None."""
        cache = MutatiesCache()
        assert cache.last_loaded is None

    def test_init_loading_flag_is_false(self):
        """Initial _loading flag is False."""
        cache = MutatiesCache()
        assert cache._loading is False


class TestNeedsRefresh:
    """Tests for _needs_refresh logic (TTL checking)."""

    def test_needs_refresh_when_data_is_none(self):
        """Cache with no data needs refresh."""
        cache = MutatiesCache()
        assert cache._needs_refresh() is True

    def test_needs_refresh_when_last_loaded_is_none(self):
        """Cache with data but no last_loaded needs refresh."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({'col': [1]})
        assert cache._needs_refresh() is True

    def test_no_refresh_when_within_ttl(self):
        """Cache loaded recently does not need refresh."""
        cache = MutatiesCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'col': [1]})
        cache.last_loaded = datetime.now() - timedelta(minutes=10)
        assert cache._needs_refresh() is False

    def test_needs_refresh_when_ttl_expired(self):
        """Cache past TTL needs refresh."""
        cache = MutatiesCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'col': [1]})
        cache.last_loaded = datetime.now() - timedelta(minutes=31)
        assert cache._needs_refresh() is True


class TestInvalidate:
    """Tests for invalidate method (cache clearing)."""

    def test_invalidate_clears_data(self):
        """Invalidate sets data to None."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({'jaar': [2024], 'Amount': [100.0]})
        cache.last_loaded = datetime.now()

        cache.invalidate()

        assert cache.data is None
        assert cache.last_loaded is None

    def test_invalidate_on_empty_cache_no_error(self):
        """Invalidate on already-empty cache does not raise."""
        cache = MutatiesCache()
        cache.invalidate()
        assert cache.data is None
        assert cache.last_loaded is None

    def test_invalidate_causes_next_get_to_refresh(self):
        """After invalidation, _needs_refresh returns True."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({'col': [1]})
        cache.last_loaded = datetime.now()

        cache.invalidate()

        assert cache._needs_refresh() is True


class TestGetData:
    """Tests for get_data method (cache retrieval with auto-refresh)."""

    def test_get_data_valid_cache_returns_data_without_refresh(self):
        """Valid cache returns data without calling the database."""
        cache = MutatiesCache(ttl_minutes=30)
        expected = pd.DataFrame({'jaar': [2024], 'Amount': [100.0]})
        cache.data = expected
        cache.last_loaded = datetime.now() - timedelta(minutes=5)

        mock_db = MagicMock()
        result = cache.get_data(mock_db)

        pd.testing.assert_frame_equal(result, expected)
        mock_db.get_connection.assert_not_called()

    def test_get_data_expired_cache_triggers_refresh(self):
        """Expired cache triggers refresh from database."""
        cache = MutatiesCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'jaar': [2023], 'Amount': [50.0]})
        cache.last_loaded = datetime.now() - timedelta(minutes=31)

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn

        # Mock execute_query for _get_years_to_load
        mock_db.execute_query.return_value = []

        fresh_data = pd.DataFrame({
            'Aangifte': ['IB'], 'TransactionNumber': ['T1'],
            'TransactionDate': ['2024-01-01'], 'TransactionDescription': ['Test'],
            'Amount': [200.0], 'Reknum': ['1000'], 'AccountName': ['Bank'],
            'Parent': ['Assets'], 'VW': ['N'], 'jaar': [2024],
            'kwartaal': [1], 'maand': [1], 'week': [1],
            'ReferenceNumber': ['REF1'], 'administration': ['Admin1'],
            'Ref3': [''], 'Ref4': ['']
        })

        with patch('mutaties_cache.pd.read_sql', return_value=fresh_data):
            result = cache.get_data(mock_db)

        assert cache.last_loaded is not None
        assert len(result) == 1

    def test_get_data_none_cache_triggers_refresh(self):
        """Empty cache (None) triggers refresh."""
        cache = MutatiesCache(ttl_minutes=30)

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.execute_query.return_value = []

        sample_data = pd.DataFrame({
            'Aangifte': ['IB'], 'TransactionNumber': ['T1'],
            'TransactionDate': ['2024-06-01'], 'TransactionDescription': ['Payment'],
            'Amount': [500.0], 'Reknum': ['4000'], 'AccountName': ['Revenue'],
            'Parent': ['Income'], 'VW': ['Y'], 'jaar': [2024],
            'kwartaal': [2], 'maand': [6], 'week': [22],
            'ReferenceNumber': ['REF2'], 'administration': ['Admin1'],
            'Ref3': [''], 'Ref4': ['']
        })

        with patch('mutaties_cache.pd.read_sql', return_value=sample_data):
            result = cache.get_data(mock_db)

        assert cache.data is not None
        assert len(result) == 1

    def test_get_data_with_requested_years_loads_missing(self):
        """Requesting years not in cache loads them on demand."""
        cache = MutatiesCache(ttl_minutes=30)
        cache.data = pd.DataFrame({
            'jaar': [2024], 'Amount': [100.0],
            'TransactionDate': pd.to_datetime(['2024-01-01'])
        })
        cache.last_loaded = datetime.now() - timedelta(minutes=5)

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn

        new_year_data = pd.DataFrame({
            'Aangifte': ['IB'], 'TransactionNumber': ['T2'],
            'TransactionDate': ['2023-03-15'], 'TransactionDescription': ['Old'],
            'Amount': [300.0], 'Reknum': ['1000'], 'AccountName': ['Bank'],
            'Parent': ['Assets'], 'VW': ['N'], 'jaar': [2023],
            'kwartaal': [1], 'maand': [3], 'week': [11],
            'ReferenceNumber': ['REF3'], 'administration': ['Admin1'],
            'Ref3': [''], 'Ref4': ['']
        })

        with patch('mutaties_cache.pd.read_sql', return_value=new_year_data):
            result = cache.get_data(mock_db, requested_years=[2023])

        # Data should now contain both years
        assert 2023 in cache.data['jaar'].values


class TestLoadAdditionalYear:
    """Tests for load_additional_year (on-demand year loading)."""

    def test_load_additional_year_already_cached(self):
        """Year already in cache returns False without DB call."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({'jaar': [2024, 2024], 'Amount': [100.0, 200.0]})

        mock_db = MagicMock()
        result = cache.load_additional_year(mock_db, 2024)

        assert result is False
        mock_db.get_connection.assert_not_called()

    def test_load_additional_year_success(self):
        """Loading a new year appends data and returns True."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({
            'Aangifte': ['IB'], 'TransactionNumber': ['T1'],
            'TransactionDate': pd.to_datetime(['2024-01-01']),
            'TransactionDescription': ['Test'], 'Amount': [100.0],
            'Reknum': ['1000'], 'AccountName': ['Bank'],
            'Parent': ['Assets'], 'VW': ['N'], 'jaar': [2024],
            'kwartaal': [1], 'maand': [1], 'week': [1],
            'ReferenceNumber': ['REF1'], 'administration': ['Admin1'],
            'Ref3': [''], 'Ref4': ['']
        })

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn

        year_data = pd.DataFrame({
            'Aangifte': ['IB'], 'TransactionNumber': ['T2'],
            'TransactionDate': ['2022-05-01'], 'TransactionDescription': ['Old'],
            'Amount': [50.0], 'Reknum': ['4000'], 'AccountName': ['Revenue'],
            'Parent': ['Income'], 'VW': ['Y'], 'jaar': [2022],
            'kwartaal': [2], 'maand': [5], 'week': [18],
            'ReferenceNumber': ['REF2'], 'administration': ['Admin1'],
            'Ref3': [''], 'Ref4': ['']
        })

        with patch('mutaties_cache.pd.read_sql', return_value=year_data):
            result = cache.load_additional_year(mock_db, 2022)

        assert result is True
        assert 2022 in cache.data['jaar'].values
        assert len(cache.data) == 2

    def test_load_additional_year_db_error_returns_false(self):
        """Database error during load returns False."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({'jaar': [2024], 'Amount': [100.0]})

        mock_db = MagicMock()
        mock_db.get_connection.side_effect = Exception("Connection failed")

        result = cache.load_additional_year(mock_db, 2022)

        assert result is False

    def test_load_additional_year_with_none_data_creates_data(self):
        """Loading year when data is None sets it as the cache data."""
        cache = MutatiesCache()
        cache.data = None

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn

        year_data = pd.DataFrame({
            'Aangifte': ['IB'], 'TransactionNumber': ['T1'],
            'TransactionDate': ['2024-01-01'], 'TransactionDescription': ['Test'],
            'Amount': [100.0], 'Reknum': ['1000'], 'AccountName': ['Bank'],
            'Parent': ['Assets'], 'VW': ['N'], 'jaar': [2024],
            'kwartaal': [1], 'maand': [1], 'week': [1],
            'ReferenceNumber': ['REF1'], 'administration': ['Admin1'],
            'Ref3': [''], 'Ref4': ['']
        })

        with patch('mutaties_cache.pd.read_sql', return_value=year_data):
            result = cache.load_additional_year(mock_db, 2024)

        assert result is True
        assert cache.data is not None
        assert len(cache.data) == 1


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats_empty_cache(self):
        """Stats for empty cache show not loaded."""
        cache = MutatiesCache(ttl_minutes=30)
        stats = cache.get_stats()

        assert stats['loaded'] is False
        assert stats['rows'] == 0
        assert stats['last_loaded'] is None
        assert stats['age_seconds'] is None

    def test_get_stats_loaded_cache(self):
        """Stats for loaded cache show correct metrics."""
        cache = MutatiesCache(ttl_minutes=30)
        cache.data = pd.DataFrame({
            'jaar': range(100),
            'Amount': [10.0] * 100,
        })
        cache.last_loaded = datetime.now() - timedelta(minutes=5)

        stats = cache.get_stats()

        assert stats['loaded'] is True
        assert stats['rows'] == 100
        assert stats['columns'] == 2
        assert stats['memory_mb'] >= 0
        assert stats['last_loaded'] is not None
        assert stats['age_seconds'] is not None
        assert stats['ttl_seconds'] == 1800.0
        assert stats['needs_refresh'] is False

    def test_get_stats_expired_cache_shows_needs_refresh(self):
        """Stats for expired cache show needs_refresh=True."""
        cache = MutatiesCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'col': [1]})
        cache.last_loaded = datetime.now() - timedelta(minutes=31)

        stats = cache.get_stats()

        assert stats['loaded'] is True
        assert stats['needs_refresh'] is True


class TestGetYearsToLoad:
    """Tests for _get_years_to_load (year determination strategy)."""

    def test_returns_current_year_when_no_data(self):
        """When no transaction years exist, returns current year."""
        cache = MutatiesCache()
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            [],  # No closed years
            [],  # No transaction years
        ]

        result = cache._get_years_to_load(mock_db)

        assert datetime.now().year in result

    def test_returns_open_years_plus_last_closed(self):
        """Returns open years and the most recent closed year."""
        cache = MutatiesCache()
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            [{'year': 2023}, {'year': 2022}],  # Closed years (desc)
            [{'year': 2024}, {'year': 2023}, {'year': 2022}, {'year': 2021}],  # All years
        ]

        result = cache._get_years_to_load(mock_db)

        # Open years: 2024, 2021 (not in closed list)
        # Last closed year: 2023
        assert 2024 in result
        assert 2021 in result
        assert 2023 in result  # Last closed year for comparisons

    def test_returns_empty_set_on_error(self):
        """Returns empty set when database query fails."""
        cache = MutatiesCache()
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = Exception("DB error")

        result = cache._get_years_to_load(mock_db)

        assert result == set()


class TestRefresh:
    """Tests for _refresh method (full cache reload)."""

    def test_refresh_loads_data_and_sets_last_loaded(self):
        """Refresh loads data and updates last_loaded timestamp."""
        cache = MutatiesCache(ttl_minutes=30)
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.execute_query.return_value = []  # No closed years, no transaction years

        sample_data = pd.DataFrame({
            'Aangifte': ['IB', 'BTW'],
            'TransactionNumber': ['T1', 'T2'],
            'TransactionDate': ['2024-01-01', '2024-02-01'],
            'TransactionDescription': ['A', 'B'],
            'Amount': [100.0, 200.0],
            'Reknum': ['1000', '4000'],
            'AccountName': ['Bank', 'Revenue'],
            'Parent': ['Assets', 'Income'],
            'VW': ['N', 'Y'],
            'jaar': [2024, 2024],
            'kwartaal': [1, 1],
            'maand': [1, 2],
            'week': [1, 5],
            'ReferenceNumber': ['REF1', 'REF2'],
            'administration': ['Admin1', 'Admin1'],
            'Ref3': ['', ''],
            'Ref4': ['', '']
        })

        with patch('mutaties_cache.pd.read_sql', return_value=sample_data):
            cache._refresh(mock_db)

        assert cache.data is not None
        assert len(cache.data) == 2
        assert cache.last_loaded is not None
        assert cache._loading is False

    def test_refresh_converts_transaction_date_to_datetime(self):
        """Refresh converts TransactionDate column to datetime."""
        cache = MutatiesCache()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.execute_query.return_value = []

        sample_data = pd.DataFrame({
            'Aangifte': ['IB'], 'TransactionNumber': ['T1'],
            'TransactionDate': ['2024-03-15'],
            'TransactionDescription': ['Test'], 'Amount': [100.0],
            'Reknum': ['1000'], 'AccountName': ['Bank'],
            'Parent': ['Assets'], 'VW': ['N'], 'jaar': [2024],
            'kwartaal': [1], 'maand': [3], 'week': [11],
            'ReferenceNumber': ['REF1'], 'administration': ['Admin1'],
            'Ref3': [''], 'Ref4': ['']
        })

        with patch('mutaties_cache.pd.read_sql', return_value=sample_data):
            cache._refresh(mock_db)

        assert pd.api.types.is_datetime64_any_dtype(cache.data['TransactionDate'])

    def test_refresh_keeps_old_data_on_error(self):
        """If refresh fails and old data exists, old data is preserved."""
        cache = MutatiesCache()
        old_data = pd.DataFrame({'jaar': [2023], 'Amount': [50.0]})
        cache.data = old_data
        cache.last_loaded = datetime.now() - timedelta(hours=1)

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.execute_query.return_value = []

        with patch('mutaties_cache.pd.read_sql', side_effect=Exception("DB error")):
            cache._refresh(mock_db)

        # Old data should be preserved
        pd.testing.assert_frame_equal(cache.data, old_data)

    def test_refresh_raises_when_no_existing_data(self):
        """If refresh fails and no existing data, exception propagates."""
        cache = MutatiesCache()

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.execute_query.return_value = []

        with patch('mutaties_cache.pd.read_sql', side_effect=Exception("DB error")):
            with pytest.raises(Exception, match="DB error"):
                cache._refresh(mock_db)


class TestGetAvailableYears:
    """Tests for get_available_years method."""

    def test_get_available_years_from_database(self):
        """get_available_years queries DB directly when db_manager provided."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({'jaar': [2024]})
        cache.last_loaded = datetime.now()

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn

        db_years = pd.DataFrame({'year': [2024, 2023, 2022]})

        with patch('mutaties_cache.pd.read_sql', return_value=db_years):
            result = cache.get_available_years(db_manager=mock_db)

        assert result == ['2024', '2023', '2022']

    def test_get_available_years_from_cache_fallback(self):
        """Falls back to cache data when no db_manager provided."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({'jaar': [2022, 2023, 2024]})
        cache.last_loaded = datetime.now()

        result = cache.get_available_years()

        assert '2024' in result
        assert '2023' in result
        assert '2022' in result

    def test_get_available_years_raises_when_no_data(self):
        """Raises ValueError when cache is empty and no db_manager."""
        cache = MutatiesCache()

        with pytest.raises(ValueError, match="Cache not loaded"):
            cache.get_available_years()


class TestGetAvailableAdministrations:
    """Tests for get_available_administrations method."""

    def test_get_available_administrations_all_years(self):
        """Returns all unique administrations."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({
            'jaar': [2024, 2024, 2023],
            'administration': ['Admin1', 'Admin2', 'Admin1']
        })

        result = cache.get_available_administrations()

        assert result == ['Admin1', 'Admin2']

    def test_get_available_administrations_filtered_by_year(self):
        """Returns administrations only for specified year."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({
            'jaar': [2024, 2024, 2023],
            'administration': ['Admin1', 'Admin2', 'Admin3']
        })

        result = cache.get_available_administrations(year=2024)

        assert result == ['Admin1', 'Admin2']

    def test_get_available_administrations_raises_when_no_data(self):
        """Raises ValueError when cache is empty."""
        cache = MutatiesCache()

        with pytest.raises(ValueError, match="Cache not loaded"):
            cache.get_available_administrations()


class TestQueryAangifteIb:
    """Tests for query_aangifte_ib method."""

    def _make_cache_with_data(self):
        """Helper to create a cache with sample aangifte data."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({
            'Aangifte': ['Box1', 'Box1', 'Box3', 'Box1'],
            'TransactionNumber': ['T1', 'T2', 'T3', 'T4'],
            'TransactionDate': pd.to_datetime(['2024-01-01', '2024-02-01', '2024-03-01', '2023-06-01']),
            'TransactionDescription': ['A', 'B', 'C', 'D'],
            'Amount': [100.0, 200.0, 50.0, 300.0],
            'Reknum': ['1000', '1000', '4000', '1000'],
            'AccountName': ['Bank', 'Bank', 'Revenue', 'Bank'],
            'Parent': ['Assets', 'Assets', 'Income', 'Assets'],
            'VW': ['N', 'N', 'Y', 'N'],
            'jaar': [2024, 2024, 2024, 2023],
            'kwartaal': [1, 1, 1, 2],
            'maand': [1, 2, 3, 6],
            'week': [1, 5, 9, 22],
            'ReferenceNumber': ['R1', 'R2', 'R3', 'R4'],
            'administration': ['Admin1', 'Admin1', 'Admin1', 'Admin1'],
            'Ref3': ['', '', '', ''],
            'Ref4': ['', '', '', '']
        })
        cache.last_loaded = datetime.now()
        return cache

    def test_query_aangifte_ib_returns_grouped_data(self):
        """Returns data grouped by Parent and Aangifte for the year."""
        cache = self._make_cache_with_data()
        result = cache.query_aangifte_ib(2024)

        assert len(result) > 0
        # Should have entries for Assets/Box1 and Income/Box3
        parents = [r['Parent'] for r in result]
        assert 'Assets' in parents
        assert 'Income' in parents

    def test_query_aangifte_ib_filters_by_year(self):
        """Only returns data for the requested year."""
        cache = self._make_cache_with_data()
        result = cache.query_aangifte_ib(2023)

        # Only 2023 data: one entry for Assets/Box1 with Amount=300
        assert len(result) == 1
        assert result[0]['Amount'] == 300.0

    def test_query_aangifte_ib_filters_by_administration(self):
        """Filters by administration when specified."""
        cache = self._make_cache_with_data()
        # Add a different administration
        cache.data = pd.concat([cache.data, pd.DataFrame({
            'Aangifte': ['Box2'], 'TransactionNumber': ['T5'],
            'TransactionDate': pd.to_datetime(['2024-04-01']),
            'TransactionDescription': ['E'], 'Amount': [999.0],
            'Reknum': ['5000'], 'AccountName': ['Expense'],
            'Parent': ['Costs'], 'VW': ['Y'], 'jaar': [2024],
            'kwartaal': [2], 'maand': [4], 'week': [14],
            'ReferenceNumber': ['R5'], 'administration': ['OtherAdmin'],
            'Ref3': [''], 'Ref4': ['']
        })], ignore_index=True)

        result = cache.query_aangifte_ib(2024, administration='Admin')

        # Should only include Admin1 data (starts with 'Admin')
        amounts = [r['Amount'] for r in result]
        assert 999.0 not in amounts

    def test_query_aangifte_ib_raises_when_cache_empty(self):
        """Raises ValueError when cache is not loaded."""
        cache = MutatiesCache()

        with pytest.raises(ValueError, match="Cache not loaded"):
            cache.query_aangifte_ib(2024)


class TestQueryAangifteIbDetails:
    """Tests for query_aangifte_ib_details method."""

    def test_returns_account_level_details(self):
        """Returns details grouped by Reknum and AccountName."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({
            'Aangifte': ['Box1', 'Box1', 'Box1'],
            'TransactionNumber': ['T1', 'T2', 'T3'],
            'TransactionDate': pd.to_datetime(['2024-01-01', '2024-02-01', '2024-03-01']),
            'TransactionDescription': ['A', 'B', 'C'],
            'Amount': [100.0, 150.0, 50.0],
            'Reknum': ['1000', '1000', '1010'],
            'AccountName': ['Bank', 'Bank', 'Savings'],
            'Parent': ['Assets', 'Assets', 'Assets'],
            'VW': ['N', 'N', 'N'],
            'jaar': [2024, 2024, 2024],
            'kwartaal': [1, 1, 1],
            'maand': [1, 2, 3],
            'week': [1, 5, 9],
            'ReferenceNumber': ['R1', 'R2', 'R3'],
            'administration': ['Admin1', 'Admin1', 'Admin1'],
            'Ref3': ['', '', ''],
            'Ref4': ['', '', '']
        })
        cache.last_loaded = datetime.now()

        result = cache.query_aangifte_ib_details(2024, 'Admin1', 'Assets', 'Box1')

        assert len(result) == 2  # Two accounts: 1000 and 1010
        amounts_by_account = {r['Reknum']: r['Amount'] for r in result}
        assert amounts_by_account['1000'] == 250.0  # 100 + 150
        assert amounts_by_account['1010'] == 50.0

    def test_filters_by_user_tenants(self):
        """Security filter: only returns data for user's accessible tenants."""
        cache = MutatiesCache()
        cache.data = pd.DataFrame({
            'Aangifte': ['Box1', 'Box1'],
            'TransactionNumber': ['T1', 'T2'],
            'TransactionDate': pd.to_datetime(['2024-01-01', '2024-02-01']),
            'TransactionDescription': ['A', 'B'],
            'Amount': [100.0, 999.0],
            'Reknum': ['1000', '1000'],
            'AccountName': ['Bank', 'Bank'],
            'Parent': ['Assets', 'Assets'],
            'VW': ['N', 'N'],
            'jaar': [2024, 2024],
            'kwartaal': [1, 1],
            'maand': [1, 2],
            'week': [1, 5],
            'ReferenceNumber': ['R1', 'R2'],
            'administration': ['Admin1', 'SecretAdmin'],
            'Ref3': ['', ''],
            'Ref4': ['', '']
        })
        cache.last_loaded = datetime.now()

        result = cache.query_aangifte_ib_details(
            2024, 'all', 'Assets', 'Box1', user_tenants=['Admin1']
        )

        assert len(result) == 1
        assert result[0]['Amount'] == 100.0


class TestGlobalCacheFunctions:
    """Tests for get_cache and invalidate_cache global functions."""

    def test_get_cache_returns_instance(self):
        """get_cache returns a MutatiesCache instance."""
        with patch('mutaties_cache._cache', None):
            result = get_cache()
            assert isinstance(result, MutatiesCache)

    def test_get_cache_returns_singleton(self):
        """get_cache returns the same instance on subsequent calls."""
        with patch('mutaties_cache._cache', None):
            first = get_cache()
            with patch('mutaties_cache._cache', first):
                second = get_cache()
            assert first is second

    def test_get_cache_custom_ttl(self):
        """get_cache respects custom TTL on first creation."""
        with patch('mutaties_cache._cache', None):
            result = get_cache(ttl_minutes=60)
            assert result.ttl == timedelta(minutes=60)

    def test_invalidate_cache_calls_invalidate(self):
        """invalidate_cache calls invalidate on the global instance."""
        mock_cache = MagicMock()
        with patch('mutaties_cache._cache', mock_cache):
            invalidate_cache()
            mock_cache.invalidate.assert_called_once()

    def test_invalidate_cache_no_error_when_not_initialized(self):
        """invalidate_cache does not error when cache is None."""
        with patch('mutaties_cache._cache', None):
            invalidate_cache()  # Should not raise
