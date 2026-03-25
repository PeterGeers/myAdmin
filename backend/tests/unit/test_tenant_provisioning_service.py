"""
Unit tests for TenantProvisioningService

Tests the shared provisioning logic with mocked DatabaseManager.
Covers: tenant creation, module insertion, chart of accounts loading,
idempotency (rerun safety), locale fallback, and error handling.
"""

import pytest
import json
import os
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

from services.tenant_provisioning_service import TenantProvisioningService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mocked DatabaseManager"""
    db = MagicMock()
    # Default: no existing data (fresh tenant)
    db.execute_query.return_value = []
    return db


@pytest.fixture
def service(mock_db):
    """Create TenantProvisioningService with mocked DB"""
    return TenantProvisioningService(mock_db)


@pytest.fixture
def sample_chart_template():
    """Sample chart of accounts JSON template"""
    return [
        {
            "Account": "2001",
            "AccountLookup": None,
            "AccountName": "Tussenrekening",
            "SubParent": "200",
            "Parent": "2000",
            "VW": "N",
            "Belastingaangifte": "Tussenrekening",
            "Pattern": False,
            "parameters": {"roles": ["interim_opening_balance"]}
        },
        {
            "Account": "3099",
            "AccountLookup": None,
            "AccountName": "Eigen Vermogen",
            "SubParent": "309",
            "Parent": "3000",
            "VW": "N",
            "Belastingaangifte": "Ondernemingsvermogen",
            "Pattern": False,
            "parameters": None
        }
    ]


def _db_returns(mock_db, responses):
    """
    Configure mock_db.execute_query to return different values
    for successive calls. Each entry in responses is the return value
    for one call.
    """
    mock_db.execute_query.side_effect = list(responses)


# ============================================================================
# Tenant Creation
# ============================================================================

class TestInsertTenant:

    def test_creates_new_tenant(self, service, mock_db):
        _db_returns(mock_db, [
            [],                          # tenant doesn't exist
            None,                        # insert tenant
            [],                          # module TENADMIN doesn't exist
            None,                        # insert TENADMIN
            [{'cnt': 0}],               # no chart rows
        ])

        # No chart template file — chart will fail, but tenant should be created
        results = service.create_and_provision_tenant(
            administration='TestCorp',
            display_name='Test Corporation',
            contact_email='admin@test.com',
            modules=[],
            created_by='test@admin.com',
        )

        assert results['tenant'] == 'created'

    def test_skips_existing_tenant(self, service, mock_db):
        _db_returns(mock_db, [
            [{'administration': 'TestCorp'}],  # tenant already exists
            [],                                 # module TENADMIN doesn't exist
            None,                               # insert TENADMIN
            [{'cnt': 0}],                      # no chart rows
        ])

        results = service.create_and_provision_tenant(
            administration='TestCorp',
            display_name='Test Corporation',
            contact_email='admin@test.com',
            modules=[],
            created_by='test@admin.com',
        )

        assert results['tenant'] == 'skipped'


# ============================================================================
# Module Insertion
# ============================================================================

class TestInsertModules:

    def test_inserts_modules_and_always_adds_tenadmin(self, service, mock_db):
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # FIN doesn't exist
            None,    # insert FIN
            [],      # STR doesn't exist
            None,    # insert STR
            [],      # TENADMIN doesn't exist
            None,    # insert TENADMIN
            [{'cnt': 0}],  # no chart rows
        ])

        results = service.create_and_provision_tenant(
            administration='TestCorp',
            display_name='Test',
            contact_email='a@b.com',
            modules=['FIN', 'STR'],
            created_by='admin@test.com',
        )

        module_names = [m['name'] for m in results['modules']]
        assert 'FIN' in module_names
        assert 'STR' in module_names
        assert 'TENADMIN' in module_names
        assert all(m['status'] == 'created' for m in results['modules'])

    def test_skips_existing_modules(self, service, mock_db):
        _db_returns(mock_db, [
            [],                          # tenant doesn't exist
            None,                        # insert tenant
            [{'id': 1}],                # FIN already exists
            [],                          # TENADMIN doesn't exist
            None,                        # insert TENADMIN
            [{'cnt': 0}],              # no chart rows
        ])

        results = service.create_and_provision_tenant(
            administration='TestCorp',
            display_name='Test',
            contact_email='a@b.com',
            modules=['FIN'],
            created_by='admin@test.com',
        )

        fin = next(m for m in results['modules'] if m['name'] == 'FIN')
        tenadmin = next(m for m in results['modules'] if m['name'] == 'TENADMIN')
        assert fin['status'] == 'skipped'
        assert tenadmin['status'] == 'created'

    def test_does_not_duplicate_tenadmin(self, service, mock_db):
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # TENADMIN doesn't exist (from modules list)
            None,    # insert TENADMIN
            [{'cnt': 0}],  # no chart rows
        ])

        results = service.create_and_provision_tenant(
            administration='TestCorp',
            display_name='Test',
            contact_email='a@b.com',
            modules=['TENADMIN'],  # explicitly passed
            created_by='admin@test.com',
        )

        tenadmin_count = sum(1 for m in results['modules'] if m['name'] == 'TENADMIN')
        assert tenadmin_count == 1


# ============================================================================
# Chart of Accounts
# ============================================================================

class TestChartOfAccounts:

    def test_loads_chart_from_template(self, service, mock_db, sample_chart_template, tmp_path):
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # TENADMIN doesn't exist
            None,    # insert TENADMIN
            [{'cnt': 0}],  # no chart rows
            None,    # insert account 1
            None,    # insert account 2
        ])

        # Write template to tmp_path
        nl_template = tmp_path / 'nl.json'
        nl_template.write_text(json.dumps(sample_chart_template), encoding='utf-8')

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR', tmp_path):
            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test',
                contact_email='a@b.com',
                modules=[],
                created_by='admin@test.com',
                locale='nl',
            )

        assert results['chart'] == 'created'
        assert results['chart_rows'] == 2

    def test_skips_chart_if_rows_exist(self, service, mock_db):
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # TENADMIN doesn't exist
            None,    # insert TENADMIN
            [{'cnt': 25}],  # chart already has 25 rows
        ])

        results = service.create_and_provision_tenant(
            administration='TestCorp',
            display_name='Test',
            contact_email='a@b.com',
            modules=[],
            created_by='admin@test.com',
        )

        assert results['chart'] == 'skipped'
        assert results['chart_rows'] == 25

    def test_chart_failed_when_no_template(self, service, mock_db, tmp_path):
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # TENADMIN doesn't exist
            None,    # insert TENADMIN
            [{'cnt': 0}],  # no chart rows
        ])

        # Empty template dir — no nl.json
        with patch('services.tenant_provisioning_service._TEMPLATE_DIR', tmp_path):
            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test',
                contact_email='a@b.com',
                modules=[],
                created_by='admin@test.com',
            )

        assert results['chart'] == 'failed'
        assert results['chart_rows'] == 0
        assert len(results['warnings']) > 0

    def test_tenant_still_created_when_chart_fails(self, service, mock_db, tmp_path):
        """Chart failure should NOT roll back tenant creation"""
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # TENADMIN doesn't exist
            None,    # insert TENADMIN
            [{'cnt': 0}],  # no chart rows
        ])

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR', tmp_path):
            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test',
                contact_email='a@b.com',
                modules=[],
                created_by='admin@test.com',
            )

        assert results['tenant'] == 'created'
        assert results['chart'] == 'failed'

    def test_parameters_json_serialized(self, service, mock_db, sample_chart_template, tmp_path):
        """Verify parameters field is JSON-serialized when inserting"""
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # TENADMIN doesn't exist
            None,    # insert TENADMIN
            [{'cnt': 0}],  # no chart rows
            None,    # insert account 1
            None,    # insert account 2
        ])

        nl_template = tmp_path / 'nl.json'
        nl_template.write_text(json.dumps(sample_chart_template), encoding='utf-8')

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR', tmp_path):
            service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test',
                contact_email='a@b.com',
                modules=[],
                created_by='admin@test.com',
            )

        # Find the INSERT INTO rekeningschema calls
        insert_calls = [
            c for c in mock_db.execute_query.call_args_list
            if c[0][0].strip().startswith('INSERT INTO rekeningschema')
        ]
        assert len(insert_calls) == 2

        # First account has parameters with roles
        first_params = insert_calls[0][0][1][-1]  # last param = parameters
        assert first_params == '{"roles": ["interim_opening_balance"]}'

        # Second account has null parameters
        second_params = insert_calls[1][0][1][-1]
        assert second_params is None


# ============================================================================
# Locale Fallback
# ============================================================================

class TestLocaleFallback:

    def test_falls_back_to_nl_for_unknown_locale(self, service, mock_db, sample_chart_template, tmp_path):
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # TENADMIN doesn't exist
            None,    # insert TENADMIN
            [{'cnt': 0}],  # no chart rows
            None,    # insert account 1
            None,    # insert account 2
        ])

        # Only nl.json exists, not de.json
        nl_template = tmp_path / 'nl.json'
        nl_template.write_text(json.dumps(sample_chart_template), encoding='utf-8')

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR', tmp_path):
            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test',
                contact_email='a@b.com',
                modules=[],
                created_by='admin@test.com',
                locale='de',
            )

        assert results['chart'] == 'created'
        assert any('falling back' in w for w in results['warnings'])

    def test_uses_en_template_when_available(self, service, mock_db, tmp_path):
        _db_returns(mock_db, [
            [],      # tenant doesn't exist
            None,    # insert tenant
            [],      # TENADMIN doesn't exist
            None,    # insert TENADMIN
            [{'cnt': 0}],  # no chart rows
            None,    # insert account
        ])

        en_chart = [{"Account": "3099", "AccountLookup": None,
                      "AccountName": "Equity", "SubParent": "309",
                      "Parent": "3000", "VW": "N",
                      "Belastingaangifte": "Equity", "Pattern": False,
                      "parameters": None}]

        en_template = tmp_path / 'en.json'
        en_template.write_text(json.dumps(en_chart), encoding='utf-8')

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR', tmp_path):
            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test',
                contact_email='a@b.com',
                modules=[],
                created_by='admin@test.com',
                locale='en',
            )

        assert results['chart'] == 'created'
        assert results['chart_rows'] == 1
        assert len(results['warnings']) == 0


# ============================================================================
# Full Idempotency (Rerun)
# ============================================================================

class TestIdempotency:

    def test_full_rerun_skips_everything(self, service, mock_db):
        """Rerunning on a fully provisioned tenant skips all steps"""
        _db_returns(mock_db, [
            [{'administration': 'TestCorp'}],  # tenant exists
            [{'id': 1}],                        # FIN exists
            [{'id': 2}],                        # TENADMIN exists
            [{'cnt': 25}],                     # chart has 25 rows
        ])

        results = service.create_and_provision_tenant(
            administration='TestCorp',
            display_name='Test',
            contact_email='a@b.com',
            modules=['FIN'],
            created_by='admin@test.com',
        )

        assert results['tenant'] == 'skipped'
        assert all(m['status'] == 'skipped' for m in results['modules'])
        assert results['chart'] == 'skipped'

    def test_partial_rerun_fills_gaps(self, service, mock_db, sample_chart_template, tmp_path):
        """Rerunning after partial failure fills in the missing pieces"""
        _db_returns(mock_db, [
            [{'administration': 'TestCorp'}],  # tenant exists (from first run)
            [{'id': 1}],                        # FIN exists (from first run)
            [],                                  # STR doesn't exist (failed first time)
            None,                                # insert STR
            [],                                  # TENADMIN doesn't exist
            None,                                # insert TENADMIN
            [{'cnt': 0}],                       # no chart (failed first time)
            None,                                # insert account 1
            None,                                # insert account 2
        ])

        nl_template = tmp_path / 'nl.json'
        nl_template.write_text(json.dumps(sample_chart_template), encoding='utf-8')

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR', tmp_path):
            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test',
                contact_email='a@b.com',
                modules=['FIN', 'STR'],
                created_by='admin@test.com',
            )

        assert results['tenant'] == 'skipped'
        fin = next(m for m in results['modules'] if m['name'] == 'FIN')
        str_mod = next(m for m in results['modules'] if m['name'] == 'STR')
        assert fin['status'] == 'skipped'
        assert str_mod['status'] == 'created'
        assert results['chart'] == 'created'
