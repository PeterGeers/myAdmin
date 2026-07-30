"""
Tests for cache stats and process memory in the health endpoint.

Validates: REQ-3.1 — Memory usage in health endpoint.
"""
import json
import pytest
from unittest.mock import patch, MagicMock


class TestHealthCacheStats:
    """Tests for cache stats section in GET /api/health."""

    def test_health_includes_caches_section(self, client):
        """Health response includes a caches section with all three caches."""
        mock_mutaties = MagicMock()
        mock_mutaties.get_stats.return_value = {
            "tenants_loaded": 3,
            "total_rows": 45000,
            "memory_mb": 85.2,
        }

        mock_bnb = MagicMock()
        mock_bnb.get_stats.return_value = {
            "tenants_loaded": 2,
            "total_rows": 1200,
            "memory_mb": 4.1,
        }

        mock_optimizer = MagicMock()
        mock_optimizer.cache.get_stats.return_value = {
            "total_entries": 142,
            "max_size": 500,
            "hit_rate_percent": 67.3,
            "evictions": 10,
        }

        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', return_value=mock_mutaties), \
             patch('bnb_cache.get_bnb_cache', return_value=mock_bnb), \
             patch('duplicate_query_optimizer.get_query_optimizer', return_value=mock_optimizer):
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'caches' in data

        # Mutaties cache stats
        assert data['caches']['mutaties']['tenants_loaded'] == 3
        assert data['caches']['mutaties']['total_rows'] == 45000
        assert data['caches']['mutaties']['memory_mb'] == 85.2

        # BNB cache stats
        assert data['caches']['bnb']['tenants_loaded'] == 2
        assert data['caches']['bnb']['total_rows'] == 1200
        assert data['caches']['bnb']['memory_mb'] == 4.1

        # Query cache stats
        assert data['caches']['query_cache']['entries'] == 142
        assert data['caches']['query_cache']['max_size'] == 500
        assert data['caches']['query_cache']['hit_rate_percent'] == 67.3

    def test_health_cache_unavailable_shows_error(self, client):
        """When a cache raises an exception, health still returns with error marker."""
        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', side_effect=RuntimeError("not initialized")), \
             patch('bnb_cache.get_bnb_cache', side_effect=RuntimeError("not initialized")), \
             patch('duplicate_query_optimizer.get_query_optimizer', side_effect=ValueError("db_manager required")):
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert data['caches']['mutaties'] == {"error": "unavailable"}
        assert data['caches']['bnb'] == {"error": "unavailable"}
        assert data['caches']['query_cache'] == {"error": "unavailable"}

    def test_health_partial_cache_failure(self, client):
        """If one cache fails, others still report correctly."""
        mock_mutaties = MagicMock()
        mock_mutaties.get_stats.return_value = {
            "tenants_loaded": 1,
            "total_rows": 100,
            "memory_mb": 1.0,
        }

        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', return_value=mock_mutaties), \
             patch('bnb_cache.get_bnb_cache', side_effect=RuntimeError("fail")), \
             patch('duplicate_query_optimizer.get_query_optimizer', side_effect=ValueError("fail")):
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['caches']['mutaties']['tenants_loaded'] == 1
        assert data['caches']['bnb'] == {"error": "unavailable"}
        assert data['caches']['query_cache'] == {"error": "unavailable"}


class TestHealthProcessMemory:
    """Tests for process memory stats in GET /api/health."""

    def test_health_includes_process_section(self, client):
        """Health response includes process RSS and alert threshold."""
        mock_mem = MagicMock()
        mock_mem.rss = 400 * 1024 * 1024  # 400 MB

        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', side_effect=Exception), \
             patch('bnb_cache.get_bnb_cache', side_effect=Exception), \
             patch('duplicate_query_optimizer.get_query_optimizer', side_effect=Exception), \
             patch('psutil.Process') as mock_process:
            mock_process.return_value.memory_info.return_value = mock_mem
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'process' in data
        assert data['process']['rss_mb'] == 400.0
        assert data['process']['alert_threshold_mb'] == 512
        assert 'memory_alert' not in data['process']

    def test_health_memory_alert_when_exceeds_threshold(self, client):
        """Alert flag is set when RSS exceeds MEMORY_ALERT_THRESHOLD_MB."""
        mock_mem = MagicMock()
        mock_mem.rss = 600 * 1024 * 1024  # 600 MB > 512 MB default

        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', side_effect=Exception), \
             patch('bnb_cache.get_bnb_cache', side_effect=Exception), \
             patch('duplicate_query_optimizer.get_query_optimizer', side_effect=Exception), \
             patch('psutil.Process') as mock_process:
            mock_process.return_value.memory_info.return_value = mock_mem
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['process']['rss_mb'] == 600.0
        assert data['process']['memory_alert'] is True

    def test_health_custom_alert_threshold(self, client):
        """Custom MEMORY_ALERT_THRESHOLD_MB env var is respected."""
        mock_mem = MagicMock()
        mock_mem.rss = 300 * 1024 * 1024  # 300 MB > 256 MB custom threshold

        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', side_effect=Exception), \
             patch('bnb_cache.get_bnb_cache', side_effect=Exception), \
             patch('duplicate_query_optimizer.get_query_optimizer', side_effect=Exception), \
             patch('psutil.Process') as mock_process, \
             patch.dict('os.environ', {'MEMORY_ALERT_THRESHOLD_MB': '256'}):
            mock_process.return_value.memory_info.return_value = mock_mem
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['process']['alert_threshold_mb'] == 256
        assert data['process']['rss_mb'] == 300.0
        assert data['process']['memory_alert'] is True

    def test_health_no_alert_when_below_custom_threshold(self, client):
        """No alert when RSS is below custom threshold."""
        mock_mem = MagicMock()
        mock_mem.rss = 200 * 1024 * 1024  # 200 MB < 256 MB

        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', side_effect=Exception), \
             patch('bnb_cache.get_bnb_cache', side_effect=Exception), \
             patch('duplicate_query_optimizer.get_query_optimizer', side_effect=Exception), \
             patch('psutil.Process') as mock_process, \
             patch.dict('os.environ', {'MEMORY_ALERT_THRESHOLD_MB': '256'}):
            mock_process.return_value.memory_info.return_value = mock_mem
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['process']['alert_threshold_mb'] == 256
        assert data['process']['rss_mb'] == 200.0
        assert 'memory_alert' not in data['process']

    def test_health_psutil_failure_graceful(self, client):
        """If psutil fails, rss_mb defaults to 0 and no alert."""
        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', side_effect=Exception), \
             patch('bnb_cache.get_bnb_cache', side_effect=Exception), \
             patch('duplicate_query_optimizer.get_query_optimizer', side_effect=Exception), \
             patch('psutil.Process', side_effect=RuntimeError("no process")):
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['process']['rss_mb'] == 0.0
        assert 'memory_alert' not in data['process']


class TestHealthBackwardCompatibility:
    """Ensure original health response fields are still present."""

    def test_health_still_returns_status_and_scalability(self, client):
        """Original fields (status, endpoints, scalability) are preserved."""
        with patch('routes.system_health_routes.scalability_manager', None), \
             patch('mutaties_cache.get_cache', side_effect=Exception), \
             patch('bnb_cache.get_bnb_cache', side_effect=Exception), \
             patch('duplicate_query_optimizer.get_query_optimizer', side_effect=Exception), \
             patch('psutil.Process', side_effect=Exception):
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert 'endpoints' in data
        assert 'scalability' in data
        assert data['scalability']['manager_active'] is False
