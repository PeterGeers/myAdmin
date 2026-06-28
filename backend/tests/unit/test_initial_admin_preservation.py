"""
Preservation Property Tests — Existing Provisioning Infrastructure Unchanged

Property 2: Preservation — For any provisioning request (with or without
initial_admin_email), the fixed provisioning flow SHALL produce the same
tenant record, modules, and chart of accounts as the original flow,
preserving all existing infrastructure creation behavior including
idempotent skip logic.

These tests are written BEFORE the fix and MUST PASS on UNFIXED code.
They capture the baseline behavior that must be preserved after the fix.

Observation-first methodology:
- Observed: create_and_provision_tenant() returns dict with keys
  'tenant', 'modules', 'chart', 'chart_rows', 'warnings'
- Observed: results['tenant'] is 'created' or 'skipped'
- Observed: results['modules'] is a list of dicts with 'name' and 'status',
  TENADMIN is always present
- Observed: results['chart'] is 'created', 'skipped', or 'failed'
- Observed: calling twice with same administration produces 'skipped' on
  second call (idempotent)

Requirements: 3.1, 3.2, 3.3, 3.7, 3.8
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, settings, assume, HealthCheck
import hypothesis.strategies as st

from services.tenant_provisioning_service import TenantProvisioningService

pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Administration names: PascalCase alphanumeric, 3-21 chars, starts uppercase
admin_names = st.from_regex(r'[A-Z][a-zA-Z0-9]{2,20}', fullmatch=True)

# Display names: 2-50 printable chars, no leading/trailing whitespace
display_names = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs'),
                           whitelist_characters='-_.&'),
    min_size=2, max_size=50,
).map(str.strip).filter(lambda s: len(s) >= 2)

# Valid email addresses
emails = st.emails()

# Module lists: subset of known modules (may be empty — TENADMIN auto-added)
KNOWN_MODULES = ['FIN', 'STR', 'ZZP', 'BNB', 'INVOICE']
module_lists = st.lists(
    st.sampled_from(KNOWN_MODULES),
    min_size=0, max_size=len(KNOWN_MODULES),
    unique=True,
)

# Locales
locales = st.sampled_from(['nl', 'en'])


# ---------------------------------------------------------------------------
# Sample chart template for tests that need chart loading
# ---------------------------------------------------------------------------

SAMPLE_CHART = [
    {
        "Account": "2001",
        "AccountLookup": None,
        "AccountName": "Tussenrekening",
        "SubParent": "200",
        "Parent": "2000",
        "VW": "N",
        "Belastingaangifte": "Tussenrekening",
        "Pattern": False,
        "parameters": {"roles": ["interim_opening_balance"]},
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
        "parameters": None,
    },
]


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_fresh_db():
    """
    Create a mock DatabaseManager that simulates a fresh tenant:
    - No existing tenant record
    - No existing modules
    - No existing chart rows

    Query routing:
      SELECT administration FROM tenants WHERE ...  -> []
      INSERT INTO tenants ...                       -> None
      SELECT id FROM tenant_modules WHERE ...       -> []
      INSERT INTO tenant_modules ...                -> None
      SELECT COUNT(*) as cnt FROM rekeningschema    -> [{'cnt': 0}]
      INSERT INTO rekeningschema ...                -> None
    """
    db = MagicMock()

    def side_effect(query, params=None, fetch=False, commit=False):
        q = query.strip().upper()
        if q.startswith('SELECT') and 'TENANTS' in q and 'ADMINISTRATION' in q:
            return []
        if q.startswith('SELECT') and 'TENANT_MODULES' in q:
            return []
        if q.startswith('SELECT') and 'REKENINGSCHEMA' in q and 'COUNT' in q:
            return [{'cnt': 0}]
        if q.startswith('INSERT'):
            return None
        return []

    db.execute_query.side_effect = side_effect
    return db


def _make_existing_db(administration, modules):
    """
    Create a mock DatabaseManager that simulates an already-provisioned tenant:
    - Tenant record exists
    - All modules exist
    - Chart rows exist
    """
    db = MagicMock()
    all_modules = set(modules) | {'TENADMIN'}

    def side_effect(query, params=None, fetch=False, commit=False):
        q = query.strip().upper()
        if q.startswith('SELECT') and 'TENANTS' in q and 'ADMINISTRATION' in q:
            return [{'administration': administration}]
        if q.startswith('SELECT') and 'TENANT_MODULES' in q:
            # All modules exist
            return [{'id': 1}]
        if q.startswith('SELECT') and 'REKENINGSCHEMA' in q and 'COUNT' in q:
            return [{'cnt': 25}]
        if q.startswith('INSERT'):
            return None
        return []

    db.execute_query.side_effect = side_effect
    return db


# ---------------------------------------------------------------------------
# Property 2a: Result dict always has the expected keys
# ---------------------------------------------------------------------------

class TestResultDictStructure:
    """
    Preservation: create_and_provision_tenant() returns a dict with keys
    'tenant', 'modules', 'chart', 'chart_rows', 'warnings' for any valid
    input combination.
    """

    REQUIRED_KEYS = {'tenant', 'modules', 'chart', 'chart_rows', 'warnings'}

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_result_has_required_keys(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For all valid (administration, display_name, contact_email, modules,
        locale) tuples, create_and_provision_tenant() returns a dict with
        keys: tenant, modules, chart, chart_rows, warnings.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        assert isinstance(results, dict), (
            f"Expected dict, got {type(results).__name__}"
        )
        missing = self.REQUIRED_KEYS - set(results.keys())
        assert not missing, (
            f"Result dict missing keys: {missing}. "
            f"Present keys: {set(results.keys())}"
        )


# ---------------------------------------------------------------------------
# Property 2b: results['tenant'] is 'created' or 'skipped'
# ---------------------------------------------------------------------------

class TestTenantStatus:
    """
    Preservation: results['tenant'] is always 'created' or 'skipped'.
    """

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_tenant_status_created_on_fresh_db(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For a fresh tenant (no existing record), results['tenant'] is
        'created'.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        assert results['tenant'] == 'created', (
            f"Expected 'created' for fresh tenant, got '{results['tenant']}'"
        )

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_tenant_status_skipped_on_existing_db(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For an existing tenant, results['tenant'] is 'skipped'.
        """
        db = _make_existing_db(administration, modules)
        service = TenantProvisioningService(db)

        results = service.create_and_provision_tenant(
            administration=administration,
            display_name=display_name,
            contact_email=contact_email,
            modules=modules,
            created_by='sysadmin@system.com',
            locale=locale,
        )

        assert results['tenant'] == 'skipped', (
            f"Expected 'skipped' for existing tenant, got '{results['tenant']}'"
        )

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_tenant_status_is_valid_value(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For any input, results['tenant'] is one of 'created' or 'skipped'.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        assert results['tenant'] in ('created', 'skipped'), (
            f"results['tenant'] should be 'created' or 'skipped', "
            f"got '{results['tenant']}'"
        )


# ---------------------------------------------------------------------------
# Property 2c: results['modules'] structure and TENADMIN always present
# ---------------------------------------------------------------------------

class TestModulesStructure:
    """
    Preservation: results['modules'] is a list where each entry has 'name'
    and 'status' keys, and TENADMIN is always present regardless of input.
    """

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_modules_list_has_name_and_status(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For all valid inputs, results['modules'] is a list of dicts each
        with 'name' and 'status' keys.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        assert isinstance(results['modules'], list), (
            f"Expected list, got {type(results['modules']).__name__}"
        )
        for entry in results['modules']:
            assert 'name' in entry, (
                f"Module entry missing 'name' key: {entry}"
            )
            assert 'status' in entry, (
                f"Module entry missing 'status' key: {entry}"
            )
            assert entry['status'] in ('created', 'skipped'), (
                f"Module status should be 'created' or 'skipped', "
                f"got '{entry['status']}'"
            )

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_tenadmin_always_present(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For all valid inputs, TENADMIN is always present in the modules
        list, even if not explicitly requested.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        module_names = [m['name'] for m in results['modules']]
        assert 'TENADMIN' in module_names, (
            f"TENADMIN must always be present in modules list. "
            f"Got: {module_names}"
        )

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_requested_modules_all_present(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For all valid inputs, every requested module appears in the result
        list (plus TENADMIN if not already requested).
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        module_names = [m['name'] for m in results['modules']]
        for mod in modules:
            assert mod in module_names, (
                f"Requested module '{mod}' not in results. Got: {module_names}"
            )


# ---------------------------------------------------------------------------
# Property 2d: results['chart'] is 'created', 'skipped', or 'failed'
# ---------------------------------------------------------------------------

class TestChartStatus:
    """
    Preservation: results['chart'] is one of 'created', 'skipped', 'failed'.
    """

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_chart_status_is_valid_value(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For any input, results['chart'] is one of 'created', 'skipped',
        or 'failed'.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        assert results['chart'] in ('created', 'skipped', 'failed'), (
            f"results['chart'] should be 'created', 'skipped', or 'failed', "
            f"got '{results['chart']}'"
        )

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_chart_rows_is_non_negative_int(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For any input, results['chart_rows'] is a non-negative integer.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        assert isinstance(results['chart_rows'], int), (
            f"chart_rows should be int, got {type(results['chart_rows']).__name__}"
        )
        assert results['chart_rows'] >= 0, (
            f"chart_rows should be >= 0, got {results['chart_rows']}"
        )

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_chart_skipped_when_rows_exist(
        self, administration, display_name, contact_email, modules
    ):
        """
        When chart rows already exist, results['chart'] is 'skipped'.
        """
        db = _make_existing_db(administration, modules)
        service = TenantProvisioningService(db)

        results = service.create_and_provision_tenant(
            administration=administration,
            display_name=display_name,
            contact_email=contact_email,
            modules=modules,
            created_by='sysadmin@system.com',
        )

        assert results['chart'] == 'skipped', (
            f"Expected 'skipped' when chart rows exist, got '{results['chart']}'"
        )

    def test_chart_created_with_template(self, tmp_path):
        """
        When a valid chart template exists and no chart rows exist,
        results['chart'] is 'created' with correct row count.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        nl_template = tmp_path / 'nl.json'
        nl_template.write_text(json.dumps(SAMPLE_CHART), encoding='utf-8')

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR', tmp_path):
            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='test@example.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                locale='nl',
            )

        assert results['chart'] == 'created'
        assert results['chart_rows'] == len(SAMPLE_CHART)


# ---------------------------------------------------------------------------
# Property 2e: Idempotent rerun — second call produces 'skipped'
# ---------------------------------------------------------------------------

class TestIdempotentRerun:
    """
    Preservation: calling create_and_provision_tenant() twice with the same
    administration produces 'skipped' for tenant and all modules on the
    second call.
    """

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_second_call_skips_tenant_and_modules(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For any valid input, calling twice with the same administration
        produces 'skipped' for tenant and all modules on the second call.
        """
        # --- First call: fresh DB ---
        db1 = _make_fresh_db()
        service1 = TenantProvisioningService(db1)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            first_results = service1.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        assert first_results['tenant'] == 'created'

        # --- Second call: existing DB (simulates post-first-call state) ---
        db2 = _make_existing_db(administration, modules)
        service2 = TenantProvisioningService(db2)

        second_results = service2.create_and_provision_tenant(
            administration=administration,
            display_name=display_name,
            contact_email=contact_email,
            modules=modules,
            created_by='sysadmin@system.com',
            locale=locale,
        )

        assert second_results['tenant'] == 'skipped', (
            f"Second call should skip tenant, got '{second_results['tenant']}'"
        )
        for mod in second_results['modules']:
            assert mod['status'] == 'skipped', (
                f"Second call should skip module '{mod['name']}', "
                f"got '{mod['status']}'"
            )
        assert second_results['chart'] == 'skipped', (
            f"Second call should skip chart, got '{second_results['chart']}'"
        )


# ---------------------------------------------------------------------------
# Property 2f: warnings is always a list
# ---------------------------------------------------------------------------

class TestWarningsStructure:
    """
    Preservation: results['warnings'] is always a list (possibly empty).
    """

    @given(
        administration=admin_names,
        display_name=display_names,
        contact_email=emails,
        modules=module_lists,
        locale=locales,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_warnings_is_list(
        self, administration, display_name, contact_email, modules, locale
    ):
        """
        For any input, results['warnings'] is a list.
        """
        db = _make_fresh_db()
        service = TenantProvisioningService(db)

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=display_name,
                contact_email=contact_email,
                modules=modules,
                created_by='sysadmin@system.com',
                locale=locale,
            )

        assert isinstance(results['warnings'], list), (
            f"warnings should be a list, got {type(results['warnings']).__name__}"
        )
