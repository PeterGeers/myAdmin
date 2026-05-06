"""
API tests for scalability_routes.py

Tests monitoring endpoints return expected metrics and
authentication enforcement.

Requirements: 5.3, 5.5, 8.3, 8.4
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestScalabilityAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_dashboard_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to dashboard should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/scalability/dashboard')
        assert response.status_code in (401, 403)

    def test_dashboard_non_sysadmin_returns_403(self, client, mock_auth):
        """Non-SysAdmin user should get 403 on scalability endpoints."""
        response = client.get(
            '/api/scalability/dashboard',
            headers=mock_auth
        )
        assert response.status_code == 403

    def test_status_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to status should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/scalability/status')
        assert response.status_code in (401, 403)

    def test_config_non_sysadmin_returns_403(self, client, mock_auth):
        """Non-SysAdmin user should get 403 on config endpoint."""
        response = client.get(
            '/api/scalability/config',
            headers=mock_auth
        )
        assert response.status_code == 403


# ============================================================================
# Dashboard Tests
# ============================================================================


class TestScalabilityDashboard:
    """Tests for GET /api/scalability/dashboard."""

    @patch('scalability_routes.DatabaseManager')
    @patch('scalability_routes.get_scalability_manager')
    def test_dashboard_with_manager_available(
        self, mock_get_manager, mock_db_class, client, mock_auth_sysadmin
    ):
        """Dashboard returns full data when scalability manager is available."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_manager.get_comprehensive_statistics.return_value = {
            'scalability_manager': {
                'uptime_seconds': 3600,
                'total_requests': 1000,
                'avg_response_time': 0.05,
                'requests_per_second': 10.0
            },
            'connection_pool': {
                'total_connections_used': 50,
                'total_errors': 2,
                'avg_response_time': 0.01,
                'pool_count': 5
            },
            'async_processing': {
                'tasks_processed': {
                    'io_tasks': 500,
                    'cpu_tasks': 200,
                    'batch_operations': 50
                },
                'performance': {
                    'avg_processing_time': 0.1,
                    'queue_sizes': {'io': 0, 'cpu': 0}
                }
            },
            'resource_monitoring': {},
            'current_resources': {},
            'scalability_improvements': {'concurrent_capacity': '10x'}
        }
        mock_manager.get_health_status.return_value = {
            'health_score': 95,
            'status': 'healthy',
            'scalability_ready': True
        }

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_scalability_statistics.return_value = {}
        mock_db.get_scalability_health.return_value = {}
        mock_db.get_connection_pool_status.return_value = {}

        response = client.get(
            '/api/scalability/dashboard',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['scalability_active'] is True
        assert data['concurrent_capacity'] == '10x baseline'

    @patch('scalability_routes.DatabaseManager')
    @patch('scalability_routes.get_scalability_manager')
    def test_dashboard_without_manager(
        self, mock_get_manager, mock_db_class, client, mock_auth_sysadmin
    ):
        """Dashboard returns fallback data when manager is unavailable."""
        mock_get_manager.side_effect = Exception('Not initialized')

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_scalability_statistics.return_value = {}
        mock_db.get_scalability_health.return_value = {}
        mock_db.get_connection_pool_status.return_value = {}

        response = client.get(
            '/api/scalability/dashboard',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['scalability_active'] is False


# ============================================================================
# Status Tests
# ============================================================================


class TestScalabilityStatus:
    """Tests for GET /api/scalability/status."""

    @patch('scalability_routes.scalability_manager', None)
    def test_status_no_manager_returns_503(self, client, mock_auth_sysadmin):
        """Status returns 503 when scalability manager is not initialized."""
        response = client.get(
            '/api/scalability/status',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 503
        data = json.loads(response.data)
        assert data['scalability_active'] is False

    def test_status_with_manager_returns_metrics(self, client, mock_auth_sysadmin):
        """Status returns metrics when manager is available."""
        mock_manager = MagicMock()
        mock_manager.get_comprehensive_statistics.return_value = {
            'scalability_manager': {
                'uptime_seconds': 7200,
                'total_requests': 5000,
                'avg_response_time': 0.03,
                'requests_per_second': 25.0
            }
        }
        mock_manager.get_health_status.return_value = {
            'health_score': 90,
            'status': 'healthy',
            'scalability_ready': True
        }

        with patch('scalability_routes.scalability_manager', mock_manager):
            response = client.get(
                '/api/scalability/status',
                headers=mock_auth_sysadmin
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['scalability_active'] is True
        assert data['concurrent_capacity'] == '10x baseline'


# ============================================================================
# Config Tests
# ============================================================================


class TestScalabilityConfig:
    """Tests for GET /api/scalability/config."""

    @patch('scalability_routes.get_scalability_manager')
    def test_config_no_manager_returns_defaults(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Config returns default values when manager is unavailable."""
        mock_get_manager.return_value = None

        response = client.get(
            '/api/scalability/config',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['scalability_configured'] is False
        assert 'default_config' in data

    @patch('scalability_routes.get_scalability_manager')
    def test_config_with_manager_returns_configuration(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Config returns full configuration when manager is available."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_manager.config = MagicMock(
            db_pool_size=10,
            db_max_overflow=5,
            db_pool_timeout=30,
            db_pool_recycle=3600,
            max_worker_threads=8,
            io_thread_pool_size=4,
            cpu_thread_pool_size=4,
            async_queue_size=100,
            batch_processing_size=50,
            monitoring_interval_seconds=60,
            performance_alert_threshold=0.8,
            resource_alert_threshold=0.9
        )
        mock_manager.get_comprehensive_statistics.return_value = {
            'scalability_manager': {
                'uptime_seconds': 3600,
                'total_requests': 1000,
                'avg_response_time': 0.05,
                'requests_per_second': 10.0
            },
            'scalability_improvements': {'concurrent_capacity': '10x'}
        }

        response = client.get(
            '/api/scalability/config',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['scalability_configured'] is True
        assert data['configuration']['database']['pool_size'] == 10


# ============================================================================
# Performance Tests
# ============================================================================


class TestScalabilityPerformance:
    """Tests for GET /api/scalability/performance."""

    @patch('scalability_routes.scalability_manager', None)
    def test_performance_no_manager_returns_503(self, client, mock_auth_sysadmin):
        """Performance returns 503 when manager is not initialized."""
        response = client.get(
            '/api/scalability/performance',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 503
        data = json.loads(response.data)
        assert data['performance_monitoring'] is False

    def test_performance_with_manager_returns_metrics(self, client, mock_auth_sysadmin):
        """Performance returns metrics when manager is available."""
        mock_manager = MagicMock()
        mock_manager.resource_monitor.get_current_metrics.return_value = {
            'cpu_percent': 45.0,
            'memory_percent': 60.0
        }
        mock_manager.resource_monitor.get_metrics_summary.return_value = {
            'avg_cpu': 40.0,
            'avg_memory': 55.0
        }
        mock_manager.config.monitoring_interval_seconds = 60

        with patch('scalability_routes.scalability_manager', mock_manager):
            response = client.get(
                '/api/scalability/performance',
                headers=mock_auth_sysadmin
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['performance_monitoring'] is True
        assert 'current_metrics' in data
        assert 'metrics_summary' in data


# ============================================================================
# Realtime Metrics Tests
# ============================================================================


class TestRealtimeMetrics:
    """Tests for GET /api/scalability/realtime."""

    def test_realtime_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to realtime should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/scalability/metrics/realtime')
        assert response.status_code in (401, 403)

    @patch('scalability_routes.get_scalability_manager')
    def test_realtime_no_manager_returns_503(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Realtime returns 503 when manager is unavailable."""
        mock_get_manager.return_value = None

        response = client.get(
            '/api/scalability/metrics/realtime',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 503
        data = json.loads(response.data)
        assert data['realtime_monitoring'] is False

    @patch('scalability_routes.get_scalability_manager')
    def test_realtime_with_manager_returns_metrics(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Realtime returns metrics when manager is available."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_manager.resource_monitor.get_current_metrics.return_value = {
            'cpu_percent': 30.0,
            'memory_percent': 50.0
        }
        mock_manager.get_comprehensive_statistics.return_value = {
            'scalability_manager': {
                'avg_response_time': 0.02,
                'requests_per_second': 50.0,
                'total_requests': 10000,
                'uptime_seconds': 7200
            },
            'connection_pool': {
                'total_connections_used': 20,
                'total_errors': 0,
                'avg_response_time': 0.005
            },
            'async_processing': {
                'performance': {
                    'queue_sizes': {'io': 0, 'cpu': 0},
                    'avg_processing_time': 0.05
                }
            }
        }

        response = client.get(
            '/api/scalability/metrics/realtime',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['realtime_monitoring'] is True
        assert 'current_performance' in data
        assert 'system_resources' in data
        assert 'connection_pools' in data

    @patch('scalability_routes.get_scalability_manager')
    def test_realtime_exception_returns_500(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Realtime returns 500 on unexpected error."""
        mock_get_manager.side_effect = Exception('Unexpected error')

        response = client.get(
            '/api/scalability/metrics/realtime',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['realtime_monitoring'] is False


# ============================================================================
# Load Test Tests
# ============================================================================


class TestRunLoadTest:
    """Tests for POST /api/scalability/load-test."""

    def test_load_test_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to load-test should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/scalability/load-test',
                                   json={'concurrent_users': 10})
        assert response.status_code in (401, 403)

    @patch('scalability_routes.get_scalability_manager')
    def test_load_test_exceeds_max_users_returns_400(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Load test rejects concurrent_users > 200."""
        response = client.post(
            '/api/scalability/load-test',
            headers=mock_auth_sysadmin,
            json={'concurrent_users': 250}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Maximum 200' in data['error']

    @patch('scalability_routes.get_scalability_manager')
    def test_load_test_exceeds_max_duration_returns_400(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Load test rejects test_duration > 300."""
        response = client.post(
            '/api/scalability/load-test',
            headers=mock_auth_sysadmin,
            json={'test_duration': 600}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Maximum 300' in data['error']

    @patch('scalability_routes.get_scalability_manager')
    def test_load_test_no_manager_returns_503(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Load test returns 503 when manager is unavailable."""
        mock_get_manager.return_value = None

        response = client.post(
            '/api/scalability/load-test',
            headers=mock_auth_sysadmin,
            json={'concurrent_users': 5, 'requests_per_user': 2, 'test_duration': 5}
        )

        assert response.status_code == 503
        data = json.loads(response.data)
        assert data['load_test_available'] is False


# ============================================================================
# Optimize Tests
# ============================================================================


class TestOptimizeScalability:
    """Tests for POST /api/scalability/optimize."""

    def test_optimize_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to optimize should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/scalability/optimize', json={})
        assert response.status_code in (401, 403)

    @patch('scalability_routes.get_scalability_manager')
    @patch('scalability_routes.DatabaseManager')
    def test_optimize_database_type_success(
        self, mock_db_class, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Optimize with type=database applies DB optimizations."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.optimize_for_concurrency.return_value = {'indexes_added': 3}
        mock_db.config = {}

        response = client.post(
            '/api/scalability/optimize',
            headers=mock_auth_sysadmin,
            json={'type': 'database', 'test_mode': True}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['optimization_type'] == 'database'
        assert len(data['optimizations_applied']) >= 1
        db_opt = next(o for o in data['optimizations_applied'] if o['type'] == 'database')
        assert db_opt['status'] == 'completed'

    @patch('scalability_routes.get_scalability_manager')
    @patch('scalability_routes.DatabaseManager')
    def test_optimize_all_with_manager(
        self, mock_db_class, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Optimize with type=all applies all optimizations."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.optimize_for_concurrency.return_value = {'indexes_added': 2}
        mock_db.config = {}

        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_manager.connection_pool.get_pool_statistics.return_value = {
            'pool_count': 5,
            'total_connections_used': 30
        }
        mock_manager.resource_monitor.get_current_metrics.return_value = {
            'cpu_percent': 25.0
        }

        response = client.post(
            '/api/scalability/optimize',
            headers=mock_auth_sysadmin,
            json={'type': 'all', 'test_mode': True}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['optimization_type'] == 'all'
        assert data['success_rate'] > 0
        assert 'scalability_improvement' in data

    @patch('scalability_routes.get_scalability_manager')
    @patch('scalability_routes.DatabaseManager')
    def test_optimize_database_failure_handled(
        self, mock_db_class, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Optimize handles database optimization failure gracefully."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.optimize_for_concurrency.side_effect = Exception('DB error')
        mock_db.config = {}
        mock_get_manager.return_value = None

        response = client.post(
            '/api/scalability/optimize',
            headers=mock_auth_sysadmin,
            json={'type': 'database', 'test_mode': True}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        db_opt = next(o for o in data['optimizations_applied'] if o['type'] == 'database')
        assert db_opt['status'] == 'failed'


# ============================================================================
# Alerts Tests
# ============================================================================


class TestScalabilityAlerts:
    """Tests for GET /api/scalability/alerts."""

    def test_alerts_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to alerts should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/scalability/alerts')
        assert response.status_code in (401, 403)

    @patch('scalability_routes.get_scalability_manager')
    def test_alerts_no_manager_returns_empty(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Alerts returns empty list when manager is unavailable."""
        mock_get_manager.return_value = None

        response = client.get(
            '/api/scalability/alerts',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['alerts_available'] is False
        assert data['alerts'] == []

    @patch('scalability_routes.get_scalability_manager')
    def test_alerts_healthy_system_no_alerts(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Alerts returns empty when system is healthy."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_manager.get_health_status.return_value = {
            'health_score': 95,
            'status': 'healthy',
            'scalability_ready': True,
            'issues': []
        }
        mock_manager.resource_monitor.get_metrics_summary.return_value = {}

        response = client.get(
            '/api/scalability/alerts',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['alerts_available'] is True
        assert data['alert_count'] == 0

    @patch('scalability_routes.get_scalability_manager')
    def test_alerts_low_health_score_generates_warning(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Alerts generates warning when health score is below 70."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_manager.get_health_status.return_value = {
            'health_score': 55,
            'status': 'degraded',
            'scalability_ready': False,
            'issues': ['High memory usage detected'],
            'recommendations': ['Increase memory allocation']
        }
        mock_manager.resource_monitor.get_metrics_summary.return_value = {}

        response = client.get(
            '/api/scalability/alerts',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['alerts_available'] is True
        assert data['alert_count'] >= 1
        # Should have a performance alert for low health score
        perf_alerts = [a for a in data['alerts'] if a['type'] == 'performance']
        assert len(perf_alerts) >= 1
        assert perf_alerts[0]['severity'] == 'warning'

    @patch('scalability_routes.get_scalability_manager')
    def test_alerts_critical_health_score(
        self, mock_get_manager, client, mock_auth_sysadmin
    ):
        """Alerts generates critical alert when health score is below 50."""
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        mock_manager.get_health_status.return_value = {
            'health_score': 30,
            'status': 'critical',
            'scalability_ready': False,
            'issues': ['Database error rate high']
        }
        mock_manager.resource_monitor.get_metrics_summary.return_value = {}

        response = client.get(
            '/api/scalability/alerts',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        perf_alerts = [a for a in data['alerts'] if a['type'] == 'performance']
        assert len(perf_alerts) >= 1
        assert perf_alerts[0]['severity'] == 'critical'


# ============================================================================
# Database Status Tests
# ============================================================================


class TestScalabilityDatabaseStatus:
    """Tests for GET /api/scalability/database."""

    def test_database_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to database status should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/scalability/database')
        assert response.status_code in (401, 403)

    @patch('scalability_routes.DatabaseManager')
    def test_database_status_success(
        self, mock_db_class, client, mock_auth_sysadmin
    ):
        """Database status returns full info when DB is available."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_scalability_statistics.return_value = {'queries_per_sec': 100}
        mock_db.get_scalability_health.return_value = {'status': 'healthy'}
        mock_db.get_connection_pool_status.return_value = {'active': 5}
        mock_db.optimize_for_concurrency.return_value = {'recommendations': []}

        response = client.get(
            '/api/scalability/database',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'database_scalability' in data
        assert data['database_scalability']['statistics'] == {'queries_per_sec': 100}
        assert data['database_scalability']['health'] == {'status': 'healthy'}

    @patch('scalability_routes.DatabaseManager')
    def test_database_status_error_returns_500(
        self, mock_db_class, client, mock_auth_sysadmin
    ):
        """Database status returns 500 on DB error."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_scalability_statistics.side_effect = Exception('Connection failed')

        response = client.get(
            '/api/scalability/database',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['database_scalability'] == 'unavailable'
