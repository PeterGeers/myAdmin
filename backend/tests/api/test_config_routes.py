"""
API tests for config_routes.py

Tests that the config blueprint loads and serves ledger parameters correctly.
This is a public endpoint (no auth required).

Requirements: 6.1, 6.2, 6.6, 6.7, 6.8, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


class TestConfigRoutesPublicAccess:
    """Verify config endpoints are publicly accessible without auth."""

    def test_ledger_parameters_responds_without_auth(self, client):
        """GET /api/config/ledger-parameters should respond without auth headers."""
        with patch('routes.config_routes._get_ledger_parameters', return_value=[]):
            response = client.get('/api/config/ledger-parameters')
        assert response.status_code == 200

    def test_ledger_parameters_returns_json_array(self, client):
        """GET /api/config/ledger-parameters should return a JSON array."""
        mock_params = [
            {'key': 'btw_high', 'type': 'percentage', 'label_nl': 'BTW Hoog'},
            {'key': 'btw_low', 'type': 'percentage', 'label_nl': 'BTW Laag'},
        ]
        with patch('routes.config_routes._get_ledger_parameters', return_value=mock_params):
            response = client.get('/api/config/ledger-parameters')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]['key'] == 'btw_high'

    def test_ledger_parameters_handles_missing_config_file(self, client):
        """When config file is missing, endpoint should return empty array gracefully."""
        # Reset the cached value so _get_ledger_parameters re-reads
        import routes.config_routes as config_mod
        original = config_mod._ledger_parameters
        config_mod._ledger_parameters = None

        with patch('os.path.exists', return_value=False), \
             patch('builtins.open', side_effect=FileNotFoundError('No such file')):
            response = client.get('/api/config/ledger-parameters')

        # Restore
        config_mod._ledger_parameters = original

        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
