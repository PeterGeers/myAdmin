"""
Integration tests for PostMigrationReconciliation.

Verifies the reconciliation script correctly identifies:
- Consistent state (zero discrepancies)
- Unregistered S3 objects
- Missing S3 objects (in registry but not in S3)
- Stale references (pointing to non-existent entities)

Uses mocks for S3 and DB since we can't connect to real services in tests.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from scripts.post_migration_reconciliation import PostMigrationReconciliation


@pytest.mark.integration
class TestPostMigrationReconciliation:
    """Integration tests for the post-migration reconciliation script."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock DatabaseManager."""
        db = MagicMock()
        db.execute_query = MagicMock()
        db.transaction = MagicMock()
        return db

    @pytest.fixture
    def mock_env(self):
        """Set required environment variables for bucket resolution."""
        env_vars = {
            'S3_SHARED_BUCKET': 'myadmin-shared-test',
            'LANDING_PAGES_BUCKET': 'myadmin-public-pages-test',
        }
        with patch.dict(os.environ, env_vars):
            yield

    @pytest.fixture
    def reconciliation(self, mock_db, mock_env):
        """Create a PostMigrationReconciliation instance with mocked deps."""
        with patch(
            'scripts.post_migration_reconciliation.DatabaseManager',
            return_value=mock_db,
        ), patch(
            'scripts.post_migration_reconciliation.ParameterService',
        ):
            recon = PostMigrationReconciliation(verbose=False)
            recon.db = mock_db
            return recon

    def test_all_consistent_zero_discrepancies(self, reconciliation, mock_db, mock_env):
        """When all S3 objects match registry and refs are valid, report shows zero issues."""
        tenant = 'TestTenant'

        # Setup: _list_s3_objects returns keys that match registry exactly
        s3_keys = [
            f'{tenant}/invoices/ast_001_invoice.pdf',
            f'{tenant}/branding/ast_002_logo.png',
        ]

        registry_rows = [
            {'s3_key': s3_keys[0], 'bucket': 'myadmin-shared-test'},
            {'s3_key': s3_keys[1], 'bucket': 'myadmin-shared-test'},
        ]

        # References that point to existing entities
        ref_rows = [
            {'id': 1, 'asset_id': 'ast_001', 'entity_type': 'invoice', 'entity_id': '100'},
            {'id': 2, 'asset_id': 'ast_002', 'entity_type': 'branding', 'entity_id': f'{tenant}:logo'},
        ]

        # Mock the reconciliation at the service level
        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation'
        ) as mock_recon:
            mock_recon.return_value = {
                'success': True,
                'tenant': tenant,
                'phase1': {
                    'unregistered': [],
                    'missing': [],
                    'total_s3': 2,
                    'total_registry': 2,
                },
                'phase2': {
                    'stale_removed': 0,
                    'newly_orphaned': 0,
                    'skipped_types': [],
                },
                'phase3': {'success': True, 'transitioned': 0},
                'summary': {
                    'administration': tenant,
                    'timestamp': '2026-08-11T10:00:00Z',
                    'total_assets': 2,
                    'consistent': 2,
                    'unregistered': 0,
                    'missing': 0,
                    'stale_references': 0,
                    'newly_eligible': 0,
                },
            }

            result = reconciliation.run_tenant_reconciliation(tenant)

        assert result['passed'] is True
        assert result['tenant'] == tenant
        assert result['discrepancies'] == []

    def test_unregistered_s3_object_detected(self, reconciliation, mock_db, mock_env):
        """When S3 has objects not in registry, report includes them as unregistered."""
        tenant = 'TestTenant'

        unregistered_objects = [
            {'s3_key': f'{tenant}/invoices/orphan_file.pdf', 'bucket': 'myadmin-shared-test'},
            {'s3_key': f'{tenant}/branding/unknown_logo.png', 'bucket': 'myadmin-shared-test'},
        ]

        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation'
        ) as mock_recon:
            mock_recon.return_value = {
                'success': True,
                'tenant': tenant,
                'phase1': {
                    'unregistered': unregistered_objects,
                    'missing': [],
                    'total_s3': 4,
                    'total_registry': 2,
                },
                'phase2': {
                    'stale_removed': 0,
                    'newly_orphaned': 0,
                    'skipped_types': [],
                },
                'phase3': {'success': True, 'transitioned': 0},
                'summary': {
                    'administration': tenant,
                    'timestamp': '2026-08-11T10:00:00Z',
                    'total_assets': 2,
                    'consistent': 2,
                    'unregistered': 2,
                    'missing': 0,
                    'stale_references': 0,
                    'newly_eligible': 0,
                },
            }

            result = reconciliation.run_tenant_reconciliation(tenant)

        assert result['passed'] is False
        assert len(result['discrepancies']) == 1

        disc = result['discrepancies'][0]
        assert disc['category'] == 'unregistered'
        assert disc['count'] == 2
        assert f'{tenant}/invoices/orphan_file.pdf' in disc['examples']
        assert f'{tenant}/branding/unknown_logo.png' in disc['examples']

    def test_missing_s3_object_detected(self, reconciliation, mock_db, mock_env):
        """When registry has records but S3 objects don't exist, report includes them."""
        tenant = 'TestTenant'

        missing_objects = [
            {'s3_key': f'{tenant}/invoices/ast_003_deleted.pdf', 'bucket': 'myadmin-shared-test'},
        ]

        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation'
        ) as mock_recon:
            mock_recon.return_value = {
                'success': True,
                'tenant': tenant,
                'phase1': {
                    'unregistered': [],
                    'missing': missing_objects,
                    'total_s3': 2,
                    'total_registry': 3,
                },
                'phase2': {
                    'stale_removed': 0,
                    'newly_orphaned': 0,
                    'skipped_types': [],
                },
                'phase3': {'success': True, 'transitioned': 0},
                'summary': {
                    'administration': tenant,
                    'timestamp': '2026-08-11T10:00:00Z',
                    'total_assets': 3,
                    'consistent': 2,
                    'unregistered': 0,
                    'missing': 1,
                    'stale_references': 0,
                    'newly_eligible': 0,
                },
            }

            result = reconciliation.run_tenant_reconciliation(tenant)

        assert result['passed'] is False
        assert len(result['discrepancies']) == 1

        disc = result['discrepancies'][0]
        assert disc['category'] == 'missing'
        assert disc['count'] == 1
        assert f'{tenant}/invoices/ast_003_deleted.pdf' in disc['examples']

    def test_stale_reference_detected(self, reconciliation, mock_db, mock_env):
        """When references point to non-existent entities, report includes them."""
        tenant = 'TestTenant'

        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation'
        ) as mock_recon:
            mock_recon.return_value = {
                'success': True,
                'tenant': tenant,
                'phase1': {
                    'unregistered': [],
                    'missing': [],
                    'total_s3': 3,
                    'total_registry': 3,
                },
                'phase2': {
                    'stale_removed': 3,
                    'newly_orphaned': 2,
                    'skipped_types': [],
                },
                'phase3': {'success': True, 'transitioned': 0},
                'summary': {
                    'administration': tenant,
                    'timestamp': '2026-08-11T10:00:00Z',
                    'total_assets': 3,
                    'consistent': 3,
                    'unregistered': 0,
                    'missing': 0,
                    'stale_references': 3,
                    'newly_eligible': 0,
                },
            }

            result = reconciliation.run_tenant_reconciliation(tenant)

        assert result['passed'] is False
        assert len(result['discrepancies']) == 1

        disc = result['discrepancies'][0]
        assert disc['category'] == 'stale'
        assert disc['count'] == 3
        assert disc['description'] == 'Stale references to non-existent entities'

    def test_multiple_discrepancy_types(self, reconciliation, mock_db, mock_env):
        """When multiple issue types exist, all are reported."""
        tenant = 'TestTenant'

        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation'
        ) as mock_recon:
            mock_recon.return_value = {
                'success': True,
                'tenant': tenant,
                'phase1': {
                    'unregistered': [
                        {'s3_key': f'{tenant}/invoices/unknown.pdf', 'bucket': 'myadmin-shared-test'},
                    ],
                    'missing': [
                        {'s3_key': f'{tenant}/branding/gone.png', 'bucket': 'myadmin-shared-test'},
                    ],
                    'total_s3': 5,
                    'total_registry': 5,
                },
                'phase2': {
                    'stale_removed': 2,
                    'newly_orphaned': 1,
                    'skipped_types': [],
                },
                'phase3': {'success': True, 'transitioned': 0},
                'summary': {
                    'administration': tenant,
                    'timestamp': '2026-08-11T10:00:00Z',
                    'total_assets': 5,
                    'consistent': 4,
                    'unregistered': 1,
                    'missing': 1,
                    'stale_references': 2,
                    'newly_eligible': 0,
                },
            }

            result = reconciliation.run_tenant_reconciliation(tenant)

        assert result['passed'] is False
        assert len(result['discrepancies']) == 3

        categories = [d['category'] for d in result['discrepancies']]
        assert 'unregistered' in categories
        assert 'missing' in categories
        assert 'stale' in categories

    def test_reconciliation_error_handling(self, reconciliation, mock_db, mock_env):
        """When reconciliation raises an exception, it's captured gracefully."""
        tenant = 'FailTenant'

        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation',
            side_effect=Exception("S3 connection timeout"),
        ):
            result = reconciliation.run_tenant_reconciliation(tenant)

        assert result['passed'] is False
        assert result['tenant'] == tenant
        assert 'error' in result
        assert 'S3 connection timeout' in result['error']

    def test_get_tenants_returns_from_db(self, reconciliation, mock_db, mock_env):
        """get_tenants() queries s3_assets for distinct administrations."""
        mock_db.execute_query.return_value = [
            {'administration': 'TenantA'},
            {'administration': 'TenantB'},
        ]

        tenants = reconciliation.get_tenants()

        assert tenants == ['TenantA', 'TenantB']
        mock_db.execute_query.assert_called_once()

    def test_get_tenants_with_filter(self, reconciliation, mock_db, mock_env):
        """When --tenant is specified, only that tenant is returned."""
        reconciliation.tenant_filter = 'SpecificTenant'

        tenants = reconciliation.get_tenants()

        assert tenants == ['SpecificTenant']
        mock_db.execute_query.assert_not_called()

    def test_run_produces_report_data(self, reconciliation, mock_db, mock_env):
        """run() populates results and get_report_data() returns structured data."""
        reconciliation.tenant_filter = 'TestTenant'

        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation'
        ) as mock_recon:
            mock_recon.return_value = {
                'success': True,
                'tenant': 'TestTenant',
                'phase1': {
                    'unregistered': [],
                    'missing': [],
                    'total_s3': 5,
                    'total_registry': 5,
                },
                'phase2': {
                    'stale_removed': 0,
                    'newly_orphaned': 0,
                    'skipped_types': [],
                },
                'phase3': {'success': True, 'transitioned': 0},
                'summary': {
                    'administration': 'TestTenant',
                    'timestamp': '2026-08-11T10:00:00Z',
                    'total_assets': 5,
                    'consistent': 5,
                    'unregistered': 0,
                    'missing': 0,
                    'stale_references': 0,
                    'newly_eligible': 0,
                },
            }

            # Mock get_tenants to avoid DB call
            mock_db.execute_query.return_value = [
                {'administration': 'TestTenant'},
            ]

            all_passed = reconciliation.run()

        assert all_passed is True

        report = reconciliation.get_report_data()
        assert report['all_passed'] is True
        assert report['tenant_count'] == 1
        assert report['passed_count'] == 1
        assert report['failed_count'] == 0
        assert len(report['tenants']) == 1
        assert report['tenants'][0]['tenant'] == 'TestTenant'

    def test_exit_code_1_on_discrepancies(self, reconciliation, mock_db, mock_env):
        """run() returns False when discrepancies are found (exit code 1)."""
        reconciliation.tenant_filter = 'TestTenant'

        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation'
        ) as mock_recon:
            mock_recon.return_value = {
                'success': True,
                'tenant': 'TestTenant',
                'phase1': {
                    'unregistered': [
                        {'s3_key': 'TestTenant/invoices/rogue.pdf', 'bucket': 'myadmin-shared-test'},
                    ],
                    'missing': [],
                    'total_s3': 3,
                    'total_registry': 2,
                },
                'phase2': {
                    'stale_removed': 0,
                    'newly_orphaned': 0,
                    'skipped_types': [],
                },
                'phase3': {'success': True, 'transitioned': 0},
                'summary': {
                    'administration': 'TestTenant',
                    'timestamp': '2026-08-11T10:00:00Z',
                    'total_assets': 2,
                    'consistent': 2,
                    'unregistered': 1,
                    'missing': 0,
                    'stale_references': 0,
                    'newly_eligible': 0,
                },
            }

            mock_db.execute_query.return_value = [
                {'administration': 'TestTenant'},
            ]

            all_passed = reconciliation.run()

        assert all_passed is False

        report = reconciliation.get_report_data()
        assert report['all_passed'] is False
        assert report['failed_count'] == 1

    def test_examples_capped_at_10(self, reconciliation, mock_db, mock_env):
        """When many unregistered objects exist, examples are capped at 10."""
        tenant = 'TestTenant'

        # Create 25 unregistered objects
        unregistered = [
            {'s3_key': f'{tenant}/invoices/file_{i}.pdf', 'bucket': 'myadmin-shared-test'}
            for i in range(25)
        ]

        with patch.object(
            reconciliation.asset_svc, 'run_reconciliation'
        ) as mock_recon:
            mock_recon.return_value = {
                'success': True,
                'tenant': tenant,
                'phase1': {
                    'unregistered': unregistered,
                    'missing': [],
                    'total_s3': 30,
                    'total_registry': 5,
                },
                'phase2': {
                    'stale_removed': 0,
                    'newly_orphaned': 0,
                    'skipped_types': [],
                },
                'phase3': {'success': True, 'transitioned': 0},
                'summary': {
                    'administration': tenant,
                    'timestamp': '2026-08-11T10:00:00Z',
                    'total_assets': 5,
                    'consistent': 5,
                    'unregistered': 25,
                    'missing': 0,
                    'stale_references': 0,
                    'newly_eligible': 0,
                },
            }

            result = reconciliation.run_tenant_reconciliation(tenant)

        disc = result['discrepancies'][0]
        assert disc['count'] == 25
        assert len(disc['examples']) == 10  # Capped at 10
