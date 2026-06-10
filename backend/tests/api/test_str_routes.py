"""
API tests for str_routes.py

Tests STR (Short-Term Rental) endpoints including auth enforcement,
file upload, booking save, pricing generation, recommendations,
historical data, listings, multipliers, and tax calculations.

Requirements: 20.6
Reference: .kiro/specs/code-quality-fixes-2026-06/tasks.md
"""
import io
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def str_auth():
    """Mock authentication with STR roles for STR endpoints."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['STR_CRUD', 'Finance_CRUD']):
        mock_creds.return_value = ('test@example.com', ['STR_CRUD', 'Finance_CRUD'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


@pytest.mark.api
class TestSTRAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    @pytest.mark.parametrize("method,url,json_data", [
        ('POST', '/api/str/save', {'realised': [], 'planned': []}),
        ('POST', '/api/pricing/generate', {'months': 14}),
        ('GET', '/api/pricing/recommendations', None),
        ('GET', '/api/pricing/historical', None),
        ('GET', '/api/pricing/listings', None),
        ('GET', '/api/pricing/multipliers?listing=Test', None),
        ('POST', '/api/str/write-future', None),
        ('GET', '/api/str/summary', None),
        ('GET', '/api/str/future-trend', None),
        ('POST', '/api/str/calculate-taxes', {'amountGross': 100}),
    ])
    def test_unauthenticated_returns_401_or_403(self, client, method, url, json_data):
        """Unauthenticated requests to STR endpoints should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            if method == 'GET':
                response = client.get(url)
            else:
                response = client.post(url, json=json_data)
        assert response.status_code in (401, 403)


# ============================================================================
# STR Upload Tests
# ============================================================================


@pytest.mark.api
class TestSTRUpload:
    """Tests for POST /api/str/upload."""

    def test_upload_options_returns_ok(self, client):
        """OPTIONS request for CORS preflight succeeds without auth."""
        response = client.options('/api/str/upload')
        assert response.status_code == 200

    @patch('routes.str_routes.STRProcessor')
    def test_upload_no_file_returns_400(self, mock_processor_cls, client, str_auth):
        """Missing file in request returns 400."""
        response = client.post('/api/str/upload', headers=str_auth)
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'No file' in data['error']

    @patch('os.remove')
    @patch('routes.str_routes.STRProcessor')
    def test_upload_success(self, mock_processor_cls, mock_remove, client, str_auth):
        """Successful file upload processes and returns booking data."""
        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor
        mock_processor.process_str_files.return_value = [
            {'guest': 'John', 'amount': 200.0, 'nights': 3}
        ]
        mock_processor.separate_by_status.return_value = {
            'realised': [{'guest': 'John', 'amount': 200.0}],
            'planned': [],
            'already_loaded': []
        }
        mock_processor.generate_summary.return_value = {'total': 200.0, 'count': 1}

        data = {
            'file': (io.BytesIO(b'csv,data,here\n'), 'airbnb_export.csv'),
            'platform': 'airbnb'
        }
        response = client.post(
            '/api/str/upload',
            headers=str_auth,
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['platform'] == 'airbnb'
        assert len(result['realised']) == 1

    @patch('routes.str_routes.STRProcessor')
    def test_upload_empty_filename_returns_400(self, mock_processor_cls, client, str_auth):
        """File with empty filename returns 400."""
        data = {
            'file': (io.BytesIO(b''), ''),
        }
        response = client.post(
            '/api/str/upload',
            headers=str_auth,
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400

    @patch('routes.str_routes.STRProcessor')
    def test_upload_processor_exception(self, mock_processor_cls, client, str_auth):
        """Processing exception returns 500."""
        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor
        mock_processor.process_str_files.side_effect = Exception('Parse error')

        data = {
            'file': (io.BytesIO(b'bad,data\n'), 'test.csv'),
            'platform': 'airbnb'
        }
        response = client.post(
            '/api/str/upload',
            headers=str_auth,
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 500
        result = json.loads(response.data)
        assert result['success'] is False
        assert 'Parse error' in result['error']


# ============================================================================
# STR Save Tests
# ============================================================================


@pytest.mark.api
class TestSTRSave:
    """Tests for POST /api/str/save."""

    @patch('routes.str_routes.STRProcessor')
    @patch('routes.str_routes.STRDatabase')
    def test_save_success(self, mock_db_cls, mock_processor_cls, client, str_auth):
        """Successfully saves realised and planned bookings."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.insert_realised_bookings.return_value = 3
        mock_db.insert_planned_bookings.return_value = 2
        mock_db.insert_future_summary.return_value = 5

        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor
        mock_processor.generate_future_summary.return_value = [{'month': '2024-07', 'amount': 500}]

        response = client.post(
            '/api/str/save',
            headers=str_auth,
            json={
                'realised': [
                    {'guest': 'A', 'amount': 100},
                    {'guest': 'B', 'amount': 200},
                    {'guest': 'C', 'amount': 300},
                ],
                'planned': [
                    {'guest': 'D', 'amount': 400},
                    {'guest': 'E', 'amount': 500},
                ]
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['results']['realised_saved'] == 3
        assert data['results']['planned_saved'] == 2

    @patch('routes.str_routes.STRProcessor')
    @patch('routes.str_routes.STRDatabase')
    def test_save_empty_bookings(self, mock_db_cls, mock_processor_cls, client, str_auth):
        """Saving with empty lists succeeds."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.insert_planned_bookings.return_value = 0

        response = client.post(
            '/api/str/save',
            headers=str_auth,
            json={'realised': [], 'planned': []}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.str_routes.STRDatabase')
    def test_save_database_exception(self, mock_db_cls, client, str_auth):
        """Database exception returns 500."""
        mock_db_cls.return_value.insert_realised_bookings.side_effect = Exception('DB error')

        response = client.post(
            '/api/str/save',
            headers=str_auth,
            json={'realised': [{'guest': 'X', 'amount': 100}], 'planned': []}
        )
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Pricing Generate Tests
# ============================================================================


@pytest.mark.api
class TestPricingGenerate:
    """Tests for POST /api/pricing/generate."""

    def test_generate_success(self, client, str_auth):
        """Successfully generates pricing strategy."""
        mock_module = MagicMock()
        mock_optimizer = MagicMock()
        mock_module.HybridPricingOptimizer.return_value = mock_optimizer
        mock_optimizer.generate_pricing_strategy.return_value = {
            'prices': [{'date': '2024-07-01', 'price': 150.0}]
        }

        with patch.dict('sys.modules', {'hybrid_pricing_optimizer': mock_module}):
            response = client.post(
                '/api/pricing/generate',
                headers=str_auth,
                json={'months': 14, 'listing': 'Beach House'}
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_generate_exception(self, client, str_auth):
        """Exception during pricing generation returns 500."""
        mock_module = MagicMock()
        mock_module.HybridPricingOptimizer.side_effect = Exception('Optimizer not available')
        with patch.dict('sys.modules', {'hybrid_pricing_optimizer': mock_module}):
            response = client.post(
                '/api/pricing/generate',
                headers=str_auth,
                json={'months': 14, 'listing': 'Beach House'}
            )
        assert response.status_code == 500


# ============================================================================
# Pricing Recommendations Tests
# ============================================================================


@pytest.mark.api
class TestPricingRecommendations:
    """Tests for GET /api/pricing/recommendations."""

    @patch('routes.str_routes.DatabaseManager')
    def test_recommendations_success(self, mock_db_cls, client, str_auth):
        """Successfully returns pricing recommendations."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {
                'listing_name': 'Beach House',
                'price_date': '2024-07-15',
                'recommended_price': 150.0,
                'ai_recommended_adr': 145.0,
                'ai_historical_adr': 130.0,
                'ai_variance': 0.12,
                'ai_reasoning': 'High demand period',
                'is_weekend': True,
                'event_uplift': 10.0,
                'event_name': 'Festival',
                'last_year_adr': 125.0,
                'generated_at': '2024-06-01 12:00:00',
                'base_rate': 100.0,
                'historical_mult': 1.1,
                'occupancy_mult': 1.05,
                'pace_mult': 1.02,
                'event_mult': 1.1,
                'ai_correction': 0.98,
                'btw_adjustment': 1.09,
            }
        ]

        response = client.get('/api/pricing/recommendations', headers=str_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1
        assert data['recommendations'][0]['listing_name'] == 'Beach House'

    @patch('routes.str_routes.DatabaseManager')
    def test_recommendations_empty(self, mock_db_cls, client, str_auth):
        """Empty recommendations returns success with empty list."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        response = client.get('/api/pricing/recommendations', headers=str_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 0

    @patch('routes.str_routes.DatabaseManager')
    def test_recommendations_db_exception(self, mock_db_cls, client, str_auth):
        """Database exception returns 500."""
        mock_db_cls.return_value.get_connection.side_effect = Exception('Connection refused')

        response = client.get('/api/pricing/recommendations', headers=str_auth)
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Pricing Historical Tests
# ============================================================================


@pytest.mark.api
class TestPricingHistorical:
    """Tests for GET /api/pricing/historical."""

    @patch('routes.str_routes.DatabaseManager')
    def test_historical_success(self, mock_db_cls, client, str_auth):
        """Returns historical and recommended ADR data."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # First call returns historical, second returns recommended
        mock_cursor.fetchall.side_effect = [
            [{'listing': 'Beach House', 'year': 2024, 'month': 6,
              'bookings': 10, 'historical_adr': 130.0}],
            [{'listing_name': 'Beach House', 'year': 2024, 'month': 7,
              'recommended_adr': 145.0}],
        ]

        response = client.get('/api/pricing/historical', headers=str_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['historical']) == 1
        assert len(data['recommended']) == 1

    @patch('routes.str_routes.DatabaseManager')
    def test_historical_db_exception(self, mock_db_cls, client, str_auth):
        """Database exception returns 500."""
        mock_db_cls.return_value.get_connection.side_effect = Exception('Timeout')

        response = client.get('/api/pricing/historical', headers=str_auth)
        assert response.status_code == 500


# ============================================================================
# Pricing Listings Tests
# ============================================================================


@pytest.mark.api
class TestPricingListings:
    """Tests for GET /api/pricing/listings."""

    @patch('routes.str_routes.DatabaseManager')
    def test_listings_success(self, mock_db_cls, client, str_auth):
        """Returns active listing names."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'listing_name': 'Beach House', 'active': True},
            {'listing_name': 'City Apartment', 'active': True},
        ]

        response = client.get('/api/pricing/listings', headers=str_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'Beach House' in data['listings']
        assert 'City Apartment' in data['listings']

    @patch('routes.str_routes.DatabaseManager')
    def test_listings_db_exception(self, mock_db_cls, client, str_auth):
        """Database exception returns 500."""
        mock_db_cls.return_value.get_connection.side_effect = Exception('DB error')

        response = client.get('/api/pricing/listings', headers=str_auth)
        assert response.status_code == 500


# ============================================================================
# Pricing Multipliers Tests
# ============================================================================


@pytest.mark.api
class TestPricingMultipliers:
    """Tests for GET /api/pricing/multipliers."""

    @patch('routes.str_routes.DatabaseManager')
    def test_multipliers_success(self, mock_db_cls, client, str_auth):
        """Returns multiplier breakdown for a listing."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {
                'price_date': '2024-07-15',
                'listing_name': 'Beach House',
                'recommended_price': 150.0,
                'base_rate': 100.0,
                'historical_mult': 1.1,
                'occupancy_mult': 1.05,
                'pace_mult': 1.02,
                'event_mult': 1.1,
                'ai_correction': 0.98,
                'btw_adjustment': 1.09,
                'is_weekend': True,
                'event_name': 'Festival',
            }
        ]

        response = client.get(
            '/api/pricing/multipliers?listing=Beach House', headers=str_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['listing'] == 'Beach House'
        assert len(data['multipliers']) == 1

    def test_multipliers_missing_listing_returns_400(self, client, str_auth):
        """Missing listing parameter returns 400."""
        response = client.get('/api/pricing/multipliers', headers=str_auth)
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.str_routes.DatabaseManager')
    def test_multipliers_db_exception(self, mock_db_cls, client, str_auth):
        """Database exception returns 500."""
        mock_db_cls.return_value.get_connection.side_effect = Exception('DB error')

        response = client.get(
            '/api/pricing/multipliers?listing=Test', headers=str_auth
        )
        assert response.status_code == 500


# ============================================================================
# STR Write Future Tests
# ============================================================================


@pytest.mark.api
class TestSTRWriteFuture:
    """Tests for POST /api/str/write-future."""

    @patch('routes.str_routes.STRDatabase')
    def test_write_future_success(self, mock_db_cls, client, str_auth):
        """Successfully writes future summary."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.write_bnb_future_summary.return_value = {
            'success': True,
            'inserted': 12,
            'date': '2024-07-01',
            'summary': {'listings': 2, 'months': 6}
        }

        response = client.post('/api/str/write-future', headers=str_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'Written 12 future records' in data['message']

    @patch('routes.str_routes.STRDatabase')
    def test_write_future_failure(self, mock_db_cls, client, str_auth):
        """Service failure returns 400."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.write_bnb_future_summary.return_value = {
            'success': False,
            'error': 'No planned data available'
        }

        response = client.post('/api/str/write-future', headers=str_auth)
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.str_routes.STRDatabase')
    def test_write_future_exception(self, mock_db_cls, client, str_auth):
        """Exception returns 500."""
        mock_db_cls.return_value.write_bnb_future_summary.side_effect = Exception('DB error')

        response = client.post('/api/str/write-future', headers=str_auth)
        assert response.status_code == 500


# ============================================================================
# STR Import Payout Tests
# ============================================================================


@pytest.mark.api
class TestSTRImportPayout:
    """Tests for POST /api/str/import-payout."""

    def test_import_payout_options_returns_ok(self, client):
        """OPTIONS request for CORS preflight succeeds without auth."""
        response = client.options('/api/str/import-payout')
        assert response.status_code == 200

    @patch('routes.str_routes.STRProcessor')
    def test_import_payout_no_file_returns_400(self, mock_processor_cls, client, str_auth):
        """Missing file in request returns 400."""
        response = client.post('/api/str/import-payout', headers=str_auth)
        assert response.status_code == 400

    @patch('routes.str_routes.STRProcessor')
    def test_import_payout_invalid_filename_returns_400(self, mock_proc_cls, client, str_auth):
        """Invalid filename pattern returns 400."""
        data = {
            'file': (io.BytesIO(b'data'), 'invalid_name.csv'),
        }
        response = client.post(
            '/api/str/import-payout',
            headers=str_auth,
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'Invalid file format' in result['error']

    @patch('os.remove')
    @patch('routes.str_routes.STRDatabase')
    @patch('routes.str_routes.STRProcessor')
    def test_import_payout_success(self, mock_proc_cls, mock_db_cls, mock_remove,
                                   client, str_auth):
        """Successful payout import processes and updates bookings."""
        mock_proc = MagicMock()
        mock_proc_cls.return_value = mock_proc
        mock_proc._process_booking_payout.return_value = {
            'summary': {
                'total_rows': 20,
                'reservation_rows': 15,
                'updated_count': 10,
                'error_count': 0
            },
            'updates': [{'reservation_id': 'R1', 'amount': 100}],
            'errors': []
        }

        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.update_from_payout.return_value = {
            'updated': 10,
            'not_found': [],
            'errors': []
        }

        data = {
            'file': (io.BytesIO(b'payout,data\n'), 'Payout_from_2024-06-01_until_2024-06-30.csv'),
        }
        response = client.post(
            '/api/str/import-payout',
            headers=str_auth,
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['database']['updated'] == 10


# ============================================================================
# STR Summary Tests
# ============================================================================


@pytest.mark.api
class TestSTRSummary:
    """Tests for GET /api/str/summary."""

    @patch('routes.str_routes.STRDatabase')
    def test_summary_success(self, mock_db_cls, client, str_auth):
        """Returns STR performance summary."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_str_summary.return_value = {
            'total_revenue': 5000.0,
            'total_bookings': 20,
            'avg_nightly_rate': 125.0
        }

        response = client.get('/api/str/summary', headers=str_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['summary']['total_bookings'] == 20

    @patch('routes.str_routes.STRDatabase')
    def test_summary_with_dates(self, mock_db_cls, client, str_auth):
        """Passes date parameters to service."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_str_summary.return_value = {}

        response = client.get(
            '/api/str/summary?start_date=2024-01-01&end_date=2024-06-30',
            headers=str_auth
        )
        assert response.status_code == 200
        mock_db.get_str_summary.assert_called_once_with('2024-01-01', '2024-06-30')

    @patch('routes.str_routes.STRDatabase')
    def test_summary_exception(self, mock_db_cls, client, str_auth):
        """Exception returns 500."""
        mock_db_cls.return_value.get_str_summary.side_effect = Exception('DB error')

        response = client.get('/api/str/summary', headers=str_auth)
        assert response.status_code == 500


# ============================================================================
# STR Future Trend Tests
# ============================================================================


@pytest.mark.api
class TestSTRFutureTrend:
    """Tests for GET /api/str/future-trend."""

    @patch('routes.str_routes.DatabaseManager')
    def test_future_trend_success(self, mock_db_cls, client, str_auth):
        """Returns future revenue trend data."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'date': '2024-07-01', 'channel': 'airbnb', 'listing': 'Beach House',
             'amount': 3000.0, 'items': 5}
        ]

        response = client.get('/api/str/future-trend', headers=str_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 1
        assert data['data'][0]['amount'] == 3000.0

    @patch('routes.str_routes.DatabaseManager')
    def test_future_trend_db_exception(self, mock_db_cls, client, str_auth):
        """Database exception returns 500."""
        mock_db_cls.return_value.get_connection.side_effect = Exception('DB error')

        response = client.get('/api/str/future-trend', headers=str_auth)
        assert response.status_code == 500


# ============================================================================
# STR Calculate Taxes Tests
# ============================================================================


@pytest.mark.api
class TestSTRCalculateTaxes:
    """Tests for POST /api/str/calculate-taxes."""

    @patch('routes.str_routes.STRProcessor')
    def test_calculate_taxes_success(self, mock_proc_cls, client, str_auth):
        """Successfully calculates taxes for a booking."""
        mock_proc = MagicMock()
        mock_proc_cls.return_value = mock_proc
        mock_proc.calculate_str_taxes.return_value = {
            'amount_vat': 63.0,
            'amount_tourist_tax': 15.0,
            'amount_nett': 667.81,
            'tax_rates_used': {'vat_rate': 0.09, 'tourist_tax_rate': 0.07}
        }

        response = client.post(
            '/api/str/calculate-taxes',
            headers=str_auth,
            json={'amountGross': 745.81, 'checkinDate': '2026-05-07', 'channelFee': 186.45}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'amountVat' in data
        assert 'amountNett' in data
        assert 'taxRates' in data

    @patch('routes.str_routes.STRProcessor')
    def test_calculate_taxes_missing_amount_returns_400(self, mock_proc_cls, client, str_auth):
        """Missing amountGross returns 400."""
        response = client.post(
            '/api/str/calculate-taxes',
            headers=str_auth,
            json={'checkinDate': '2026-05-07'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'amountGross is required' in data['error']

    @patch('routes.str_routes.STRProcessor')
    def test_calculate_taxes_no_body_returns_400(self, mock_proc_cls, client, str_auth):
        """No request body returns 400."""
        response = client.post(
            '/api/str/calculate-taxes',
            headers=str_auth,
            content_type='application/json',
            data='null'
        )
        assert response.status_code == 400

    @patch('routes.str_routes.STRProcessor')
    def test_calculate_taxes_exception(self, mock_proc_cls, client, str_auth):
        """Processor exception returns 500."""
        mock_proc = MagicMock()
        mock_proc_cls.return_value = mock_proc
        mock_proc.calculate_str_taxes.side_effect = Exception('Tax calculation failed')

        response = client.post(
            '/api/str/calculate-taxes',
            headers=str_auth,
            json={'amountGross': 100.0}
        )
        assert response.status_code == 500
