"""
Unit tests for bnb_cache module.

Tests cache TTL logic, refresh triggers, data filtering,
and edge cases for expired cache entries.

Requirements: 1.8, 2.2, 2.3, 8.5
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from bnb_cache import BnbCache, get_bnb_cache


class TestBnbCacheInit:
    """Tests for BnbCache initialization."""

    def test_init_default_ttl_thirty_minutes(self):
        """Test default TTL is 30 minutes."""
        cache = BnbCache()
        assert cache.ttl == timedelta(minutes=30)

    def test_init_custom_ttl_sets_correctly(self):
        """Test custom TTL is set correctly."""
        cache = BnbCache(ttl_minutes=60)
        assert cache.ttl == timedelta(minutes=60)

    def test_init_data_is_none(self):
        """Test initial data is None."""
        cache = BnbCache()
        assert cache.data is None

    def test_init_last_refresh_is_none(self):
        """Test initial last_refresh is None."""
        cache = BnbCache()
        assert cache.last_refresh is None


class TestIsValid:
    """Tests for is_valid method (cache TTL logic)."""

    def test_is_valid_no_data_returns_false(self):
        """Test cache with no data is invalid."""
        cache = BnbCache()
        assert cache.is_valid() is False

    def test_is_valid_no_last_refresh_returns_false(self):
        """Test cache with data but no last_refresh is invalid."""
        cache = BnbCache()
        cache.data = pd.DataFrame({'col': [1, 2, 3]})
        assert cache.is_valid() is False

    def test_is_valid_fresh_data_returns_true(self):
        """Test cache refreshed recently is valid."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'col': [1, 2, 3]})
        cache.last_refresh = datetime.now() - timedelta(minutes=5)
        assert cache.is_valid() is True

    def test_is_valid_expired_data_returns_false(self):
        """Test cache past TTL is invalid."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'col': [1, 2, 3]})
        cache.last_refresh = datetime.now() - timedelta(minutes=31)
        assert cache.is_valid() is False

    def test_is_valid_exactly_at_ttl_boundary_returns_false(self):
        """Test cache exactly at TTL boundary is invalid (strict less-than)."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'col': [1, 2, 3]})
        # Set last_refresh to exactly 30 minutes ago
        cache.last_refresh = datetime.now() - timedelta(minutes=30, seconds=1)
        assert cache.is_valid() is False


class TestGetData:
    """Tests for get_data method (cache retrieval with auto-refresh)."""

    def test_get_data_valid_cache_returns_cached_data(self, mock_db):
        """Test valid cache returns data without refresh."""
        cache = BnbCache(ttl_minutes=30)
        expected_data = pd.DataFrame({'col': [1, 2, 3]})
        cache.data = expected_data
        cache.last_refresh = datetime.now() - timedelta(minutes=5)

        result = cache.get_data(mock_db)

        pd.testing.assert_frame_equal(result, expected_data)
        # Verify no DB call was made (cache was valid)
        mock_db.get_cursor.assert_not_called()

    def test_get_data_expired_cache_triggers_refresh(self, mock_db):
        """Test expired cache triggers refresh from database."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'col': [1]})
        cache.last_refresh = datetime.now() - timedelta(minutes=31)

        # Mock the DB cursor to return a DataFrame via pd.read_sql
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        sample_data = pd.DataFrame({
            'checkinDate': ['2024-01-15'],
            'checkoutDate': ['2024-01-18'],
            'channel': ['Airbnb'],
            'listing': ['Property1'],
            'nights': [3],
            'amountGross': [300.0],
            'amountNett': [270.0],
            'amountChannelFee': [30.0],
            'amountTouristTax': [9.0],
            'amountVat': [15.0],
            'guestName': ['Test Guest'],
            'guests': [2],
            'reservationCode': ['ABC123'],
            'status': ['realised'],
            'source_type': ['actual'],
            'year': [2024],
            'quarter': [1],
            'month': [1],
        })

        with patch('bnb_cache.pd.read_sql', return_value=sample_data):
            result = cache.get_data(mock_db)

        assert cache.last_refresh is not None
        assert len(result) == 1

    def test_get_data_no_cache_triggers_refresh(self, mock_db):
        """Test empty cache triggers refresh from database."""
        cache = BnbCache(ttl_minutes=30)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        sample_data = pd.DataFrame({
            'checkinDate': ['2024-06-01'],
            'checkoutDate': ['2024-06-05'],
            'channel': ['Booking.com'],
            'listing': ['Property2'],
            'nights': [4],
            'amountGross': [400.0],
            'amountNett': [360.0],
            'amountChannelFee': [40.0],
            'amountTouristTax': [12.0],
            'amountVat': [20.0],
            'guestName': ['Another Guest'],
            'guests': [3],
            'reservationCode': ['DEF456'],
            'status': ['planned'],
            'source_type': ['planned'],
            'year': [2024],
            'quarter': [2],
            'month': [6],
        })

        with patch('bnb_cache.pd.read_sql', return_value=sample_data):
            result = cache.get_data(mock_db)

        assert cache.data is not None
        assert len(result) == 1


class TestRefresh:
    """Tests for refresh method (database loading)."""

    def test_refresh_loads_data_and_sets_last_refresh(self, mock_db):
        """Test refresh loads data from DB and updates last_refresh."""
        cache = BnbCache(ttl_minutes=30)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        sample_data = pd.DataFrame({
            'checkinDate': ['2024-01-15', '2024-02-20'],
            'checkoutDate': ['2024-01-18', '2024-02-23'],
            'channel': ['Airbnb', 'Booking.com'],
            'listing': ['Prop1', 'Prop2'],
            'nights': [3, 3],
            'amountGross': [300.0, 350.0],
            'amountNett': [270.0, 315.0],
            'amountChannelFee': [30.0, 35.0],
            'amountTouristTax': [9.0, 10.5],
            'amountVat': [15.0, 17.5],
            'guestName': ['Guest A', 'Guest B'],
            'guests': [2, 1],
            'reservationCode': ['RES1', 'RES2'],
            'status': ['realised', 'planned'],
            'source_type': ['actual', 'planned'],
            'year': [2024, 2024],
            'quarter': [1, 1],
            'month': [1, 2],
        })

        with patch('bnb_cache.pd.read_sql', return_value=sample_data):
            cache.refresh(mock_db)

        assert cache.data is not None
        assert len(cache.data) == 2
        assert cache.last_refresh is not None

    def test_refresh_converts_date_columns_to_datetime(self, mock_db):
        """Test refresh converts checkinDate and checkoutDate to datetime."""
        cache = BnbCache(ttl_minutes=30)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        sample_data = pd.DataFrame({
            'checkinDate': ['2024-03-01'],
            'checkoutDate': ['2024-03-05'],
            'channel': ['Airbnb'],
            'listing': ['Prop1'],
            'nights': ['3'],
            'amountGross': ['300.0'],
            'amountNett': ['270.0'],
            'amountChannelFee': ['30.0'],
            'amountTouristTax': ['9.0'],
            'amountVat': ['15.0'],
            'guestName': ['Guest'],
            'guests': ['2'],
            'reservationCode': ['RES1'],
            'status': ['realised'],
            'source_type': ['actual'],
            'year': [2024],
            'quarter': [1],
            'month': [3],
        })

        with patch('bnb_cache.pd.read_sql', return_value=sample_data):
            cache.refresh(mock_db)

        assert pd.api.types.is_datetime64_any_dtype(cache.data['checkinDate'])
        assert pd.api.types.is_datetime64_any_dtype(cache.data['checkoutDate'])

    def test_refresh_converts_numeric_columns_to_float(self, mock_db):
        """Test refresh converts numeric columns and fills NaN with 0."""
        cache = BnbCache(ttl_minutes=30)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        sample_data = pd.DataFrame({
            'checkinDate': ['2024-01-01'],
            'checkoutDate': ['2024-01-03'],
            'channel': ['Airbnb'],
            'listing': ['Prop1'],
            'nights': [None],
            'amountGross': [None],
            'amountNett': ['invalid'],
            'amountChannelFee': [10.0],
            'amountTouristTax': [3.0],
            'amountVat': [5.0],
            'guestName': ['Guest'],
            'guests': [None],
            'reservationCode': ['RES1'],
            'status': ['realised'],
            'source_type': ['actual'],
            'year': [2024],
            'quarter': [1],
            'month': [1],
        })

        with patch('bnb_cache.pd.read_sql', return_value=sample_data):
            cache.refresh(mock_db)

        # NaN/invalid values should be filled with 0
        assert cache.data['nights'].iloc[0] == 0.0
        assert cache.data['amountGross'].iloc[0] == 0.0
        assert cache.data['amountNett'].iloc[0] == 0.0
        assert cache.data['guests'].iloc[0] == 0.0

    def test_refresh_fills_nan_string_columns_with_empty(self, mock_db):
        """Test refresh fills NaN in string columns with empty string."""
        cache = BnbCache(ttl_minutes=30)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        sample_data = pd.DataFrame({
            'checkinDate': ['2024-01-01'],
            'checkoutDate': ['2024-01-03'],
            'channel': [None],
            'listing': [None],
            'nights': [2],
            'amountGross': [200.0],
            'amountNett': [180.0],
            'amountChannelFee': [20.0],
            'amountTouristTax': [6.0],
            'amountVat': [10.0],
            'guestName': [None],
            'guests': [1],
            'reservationCode': [None],
            'status': [None],
            'source_type': [None],
            'year': [2024],
            'quarter': [1],
            'month': [1],
        })

        with patch('bnb_cache.pd.read_sql', return_value=sample_data):
            cache.refresh(mock_db)

        assert cache.data['channel'].iloc[0] == ''
        assert cache.data['listing'].iloc[0] == ''
        assert cache.data['guestName'].iloc[0] == ''
        assert cache.data['reservationCode'].iloc[0] == ''
        assert cache.data['status'].iloc[0] == ''
        assert cache.data['source_type'].iloc[0] == ''

    def test_refresh_database_error_raises_exception(self, mock_db):
        """Test refresh raises exception when database fails."""
        cache = BnbCache(ttl_minutes=30)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch('bnb_cache.pd.read_sql', side_effect=Exception("DB connection failed")):
            with pytest.raises(Exception, match="DB connection failed"):
                cache.refresh(mock_db)

        # Data should remain None after failed refresh
        assert cache.data is None


class TestInvalidate:
    """Tests for invalidate method."""

    def test_invalidate_clears_data(self):
        """Test invalidate sets data to None."""
        cache = BnbCache()
        cache.data = pd.DataFrame({'col': [1, 2, 3]})
        cache.last_refresh = datetime.now()

        cache.invalidate()

        assert cache.data is None
        assert cache.last_refresh is None

    def test_invalidate_on_empty_cache_no_error(self):
        """Test invalidate on already-empty cache does not raise."""
        cache = BnbCache()
        cache.invalidate()
        assert cache.data is None
        assert cache.last_refresh is None


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_empty_cache_returns_not_loaded(self):
        """Test status of empty cache shows not loaded."""
        cache = BnbCache(ttl_minutes=45)
        status = cache.get_status()

        assert status['loaded'] is False
        assert status['row_count'] == 0
        assert status['memory_mb'] == 0
        assert status['last_refresh'] is None
        assert status['ttl_minutes'] == 45.0
        assert status['is_valid'] is False

    def test_get_status_loaded_cache_returns_correct_info(self):
        """Test status of loaded cache shows correct metrics."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({
            'col1': range(100),
            'col2': ['text'] * 100,
        })
        cache.last_refresh = datetime.now() - timedelta(minutes=5)

        status = cache.get_status()

        assert status['loaded'] is True
        assert status['row_count'] == 100
        assert status['memory_mb'] >= 0
        assert status['last_refresh'] is not None
        assert status['ttl_minutes'] == 30.0
        assert status['is_valid'] is True

    def test_get_status_expired_cache_shows_invalid(self):
        """Test status of expired cache shows is_valid=False."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({'col': [1]})
        cache.last_refresh = datetime.now() - timedelta(minutes=31)

        status = cache.get_status()

        assert status['loaded'] is True
        assert status['is_valid'] is False


class TestQueryByYear:
    """Tests for query_by_year method (data filtering)."""

    def _make_cache_with_data(self):
        """Helper to create a cache with sample data."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({
            'checkinDate': pd.to_datetime(['2024-01-15', '2024-06-20', '2023-12-01']),
            'checkoutDate': pd.to_datetime(['2024-01-18', '2024-06-23', '2023-12-04']),
            'channel': ['Airbnb', 'Booking.com', 'Airbnb'],
            'listing': ['Prop1', 'Prop1', 'Prop2'],
            'nights': [3, 3, 3],
            'amountGross': [300.0, 350.0, 280.0],
            'amountNett': [270.0, 315.0, 252.0],
            'amountChannelFee': [30.0, 35.0, 28.0],
            'amountTouristTax': [9.0, 10.5, 8.4],
            'amountVat': [15.0, 17.5, 14.0],
            'guestName': ['Guest A', 'Guest B', 'Guest C'],
            'guests': [2, 1, 4],
            'reservationCode': ['RES1', 'RES2', 'RES3'],
            'status': ['realised', 'cancelled', 'realised'],
            'source_type': ['actual', 'actual', 'actual'],
            'year': [2024, 2024, 2023],
            'quarter': [1, 2, 4],
            'month': [1, 6, 12],
        })
        cache.last_refresh = datetime.now()
        return cache

    def test_query_by_year_returns_matching_records(self, mock_db):
        """Test query_by_year returns only records for specified year."""
        cache = self._make_cache_with_data()
        result = cache.query_by_year(mock_db, 2024)

        assert len(result) == 2
        assert all(r['year'] == 2024 for r in result)

    def test_query_by_year_with_status_filter(self, mock_db):
        """Test query_by_year with status filter returns matching records."""
        cache = self._make_cache_with_data()
        result = cache.query_by_year(mock_db, 2024, status='cancelled')

        assert len(result) == 1
        assert result[0]['status'] == 'cancelled'

    def test_query_by_year_no_matches_returns_empty(self, mock_db):
        """Test query_by_year with non-existent year returns empty list."""
        cache = self._make_cache_with_data()
        result = cache.query_by_year(mock_db, 2025)

        assert result == []

    def test_query_by_year_string_year_converted_to_int(self, mock_db):
        """Test query_by_year accepts string year and converts to int."""
        cache = self._make_cache_with_data()
        result = cache.query_by_year(mock_db, '2023')

        assert len(result) == 1
        assert result[0]['year'] == 2023


class TestQueryCancelledByYear:
    """Tests for query_cancelled_by_year method."""

    def test_query_cancelled_by_year_returns_only_cancelled(self, mock_db):
        """Test returns only cancelled bookings for the year."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({
            'checkinDate': pd.to_datetime(['2024-01-15', '2024-06-20']),
            'checkoutDate': pd.to_datetime(['2024-01-18', '2024-06-23']),
            'channel': ['Airbnb', 'Booking.com'],
            'listing': ['Prop1', 'Prop1'],
            'nights': [3, 3],
            'amountGross': [300.0, 350.0],
            'amountNett': [270.0, 315.0],
            'amountChannelFee': [30.0, 35.0],
            'amountTouristTax': [9.0, 10.5],
            'amountVat': [15.0, 17.5],
            'guestName': ['Guest A', 'Guest B'],
            'guests': [2, 1],
            'reservationCode': ['RES1', 'RES2'],
            'status': ['realised', 'cancelled'],
            'source_type': ['actual', 'actual'],
            'year': [2024, 2024],
            'quarter': [1, 2],
            'month': [1, 6],
        })
        cache.last_refresh = datetime.now()

        result = cache.query_cancelled_by_year(mock_db, 2024)

        assert len(result) == 1
        assert result[0]['status'] == 'cancelled'


class TestQueryRealisedByYear:
    """Tests for query_realised_by_year method."""

    def test_query_realised_by_year_excludes_cancelled(self, mock_db):
        """Test returns only non-cancelled bookings for the year."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({
            'checkinDate': pd.to_datetime(['2024-01-15', '2024-06-20', '2024-08-01']),
            'checkoutDate': pd.to_datetime(['2024-01-18', '2024-06-23', '2024-08-04']),
            'channel': ['Airbnb', 'Booking.com', 'Airbnb'],
            'listing': ['Prop1', 'Prop1', 'Prop2'],
            'nights': [3, 3, 3],
            'amountGross': [300.0, 350.0, 400.0],
            'amountNett': [270.0, 315.0, 360.0],
            'amountChannelFee': [30.0, 35.0, 40.0],
            'amountTouristTax': [9.0, 10.5, 12.0],
            'amountVat': [15.0, 17.5, 20.0],
            'guestName': ['Guest A', 'Guest B', 'Guest C'],
            'guests': [2, 1, 3],
            'reservationCode': ['RES1', 'RES2', 'RES3'],
            'status': ['realised', 'cancelled', 'planned'],
            'source_type': ['actual', 'actual', 'planned'],
            'year': [2024, 2024, 2024],
            'quarter': [1, 2, 3],
            'month': [1, 6, 8],
        })
        cache.last_refresh = datetime.now()

        result = cache.query_realised_by_year(mock_db, 2024)

        assert len(result) == 2
        statuses = [r['status'] for r in result]
        assert 'cancelled' not in statuses
        assert 'realised' in statuses
        assert 'planned' in statuses


class TestGetBnbCache:
    """Tests for get_bnb_cache global factory function."""

    def test_get_bnb_cache_returns_instance(self):
        """Test get_bnb_cache returns a BnbCache instance."""
        with patch('bnb_cache._bnb_cache', None):
            result = get_bnb_cache()
            assert isinstance(result, BnbCache)

    def test_get_bnb_cache_returns_same_instance(self):
        """Test get_bnb_cache returns singleton instance."""
        with patch('bnb_cache._bnb_cache', None):
            first = get_bnb_cache()
            # Patch the global to the first instance so second call reuses it
            with patch('bnb_cache._bnb_cache', first):
                second = get_bnb_cache()
            assert first is second


class TestCacheExpiredThenRefresh:
    """Tests for edge case: expired cache entry returns fresh data after refresh."""

    def test_expired_cache_refreshes_and_returns_fresh_data(self, mock_db):
        """Test that expired cache triggers refresh and returns new data."""
        cache = BnbCache(ttl_minutes=30)

        # Set up stale data
        stale_data = pd.DataFrame({
            'checkinDate': pd.to_datetime(['2023-01-01']),
            'checkoutDate': pd.to_datetime(['2023-01-03']),
            'channel': ['OldChannel'],
            'listing': ['OldProp'],
            'nights': [2],
            'amountGross': [100.0],
            'amountNett': [90.0],
            'amountChannelFee': [10.0],
            'amountTouristTax': [3.0],
            'amountVat': [5.0],
            'guestName': ['Old Guest'],
            'guests': [1],
            'reservationCode': ['OLD1'],
            'status': ['realised'],
            'source_type': ['actual'],
            'year': [2023],
            'quarter': [1],
            'month': [1],
        })
        cache.data = stale_data
        cache.last_refresh = datetime.now() - timedelta(minutes=60)  # Expired

        # Set up fresh data from DB
        fresh_data = pd.DataFrame({
            'checkinDate': ['2024-07-01'],
            'checkoutDate': ['2024-07-05'],
            'channel': ['NewChannel'],
            'listing': ['NewProp'],
            'nights': [4],
            'amountGross': [500.0],
            'amountNett': [450.0],
            'amountChannelFee': [50.0],
            'amountTouristTax': [15.0],
            'amountVat': [25.0],
            'guestName': ['New Guest'],
            'guests': [3],
            'reservationCode': ['NEW1'],
            'status': ['planned'],
            'source_type': ['planned'],
            'year': [2024],
            'quarter': [3],
            'month': [7],
        })

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch('bnb_cache.pd.read_sql', return_value=fresh_data):
            result = cache.get_data(mock_db)

        # Should have fresh data, not stale
        assert len(result) == 1
        assert result['channel'].iloc[0] == 'NewChannel'
        assert result['listing'].iloc[0] == 'NewProp'
        # last_refresh should be updated
        assert (datetime.now() - cache.last_refresh).total_seconds() < 5

    def test_valid_cache_does_not_refresh(self, mock_db):
        """Test that valid cache does not trigger refresh."""
        cache = BnbCache(ttl_minutes=30)
        cache.data = pd.DataFrame({
            'checkinDate': pd.to_datetime(['2024-01-15']),
            'checkoutDate': pd.to_datetime(['2024-01-18']),
            'channel': ['Airbnb'],
            'listing': ['Prop1'],
            'nights': [3],
            'amountGross': [300.0],
            'amountNett': [270.0],
            'amountChannelFee': [30.0],
            'amountTouristTax': [9.0],
            'amountVat': [15.0],
            'guestName': ['Guest'],
            'guests': [2],
            'reservationCode': ['RES1'],
            'status': ['realised'],
            'source_type': ['actual'],
            'year': [2024],
            'quarter': [1],
            'month': [1],
        })
        cache.last_refresh = datetime.now() - timedelta(minutes=10)
        original_refresh = cache.last_refresh

        result = cache.get_data(mock_db)

        # Should not have refreshed
        assert cache.last_refresh == original_refresh
        assert len(result) == 1
        mock_db.get_cursor.assert_not_called()
