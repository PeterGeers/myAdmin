"""
API tests for migration_routes.py

Tests that the migration endpoint registers and responds correctly,
including security checks (ALLOW_MIGRATION env var and secret).

Requirements: 6.1, 6.2, 6.6, 6.7, 6.8, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


class TestMigrationRoutesAuthEnforcement:
    """Verify migration endpoint security controls."""

    def test_migrate_returns_403_when_allow_migration_not_set(self, client):
        """POST /api/migration/opening-balances/migrate returns 403 when ALLOW_MIGRATION is false."""
        # The module-level ALLOW_UNAUTHENTICATED_MIGRATION is already False by default
        # since the test environment doesn't set ALLOW_MIGRATION=true
        response = client.post(
            '/api/migration/opening-balances/migrate',
            json={'secret': 'migrate-opening-balances-2026'}
        )
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'disabled' in data['error'].lower() or 'migration' in data['error'].lower()

    def test_migrate_returns_403_with_wrong_secret(self, client):
        """POST /api/migration/opening-balances/migrate returns 403 with wrong secret."""
        with patch('routes.migration_routes.ALLOW_UNAUTHENTICATED_MIGRATION', True):
            response = client.post(
                '/api/migration/opening-balances/migrate',
                json={'secret': 'wrong-secret'}
            )
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'invalid' in data['error'].lower() or 'secret' in data['error'].lower()

    def test_migrate_dry_run_returns_preview_data(self, client):
        """POST with dry_run=True and correct secret returns preview without modifying data."""
        with patch('routes.migration_routes.ALLOW_UNAUTHENTICATED_MIGRATION', True), \
             patch('routes.migration_routes.get_years_needing_migration') as mock_years, \
             patch('routes.migration_routes.get_first_year_with_transactions', return_value=2020), \
             patch('routes.migration_routes.DatabaseManager') as mock_db_class:

            mock_db_class.return_value = MagicMock()
            mock_years.return_value = [
                {'administration': 'test-admin', 'year': 2021},
                {'administration': 'test-admin', 'year': 2022},
            ]

            response = client.post(
                '/api/migration/opening-balances/migrate',
                json={
                    'secret': 'migrate-opening-balances-2026',
                    'dry_run': True
                }
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['dry_run'] is True
        assert 'preview' in data
        assert data['total_years'] >= 0
