"""
Bug Condition Exploration Test — Onboarding Storage & Visibility Fix

Property 1: Bug Condition - Provisioning Fails to Seed Storage, Restricts Modules,
and Seeds Parameters.

This test encodes the EXPECTED behavior after the fix. It is written BEFORE the fix
and is expected to FAIL on unfixed code — failure confirms the bugs exist.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Tenant names: alphanumeric PascalCase identifiers
tenant_names = st.from_regex(r'[A-Z][a-zA-Z0-9]{2,15}', fullmatch=True)

# Storage providers relevant to the bug condition
storage_providers = st.sampled_from(['s3_shared', 's3_tenant'])

# Locales
locales = st.sampled_from(['nl', 'en'])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_db():
    """Create a mock DatabaseManager that tracks queries."""
    db = MagicMock()
    db._inserted_modules = []
    db._inserted_params = []
    db._queries = []

    def execute_query_side_effect(query, params=None, fetch=True, commit=False):
        db._queries.append((query, params, fetch, commit))

        # Tenant existence check — always say "not exists" for new provisioning
        if 'SELECT administration FROM tenants' in query:
            return []

        # Module existence check — always say "not exists"
        if 'SELECT id FROM tenant_modules' in query and fetch:
            return []

        # Module is_active check (has_module)
        if 'SELECT is_active' in query and 'tenant_modules' in query:
            # Check if we "inserted" this module
            if params and len(params) >= 2:
                tenant, module = params[0], params[1]
                for ins in db._inserted_modules:
                    if ins['tenant'] == tenant and ins['module'] == module:
                        return [{'is_active': True}]
            return []

        # INSERT into tenant_modules
        if 'INSERT INTO tenant_modules' in query and not fetch:
            if params and len(params) >= 2:
                db._inserted_modules.append({
                    'tenant': params[0],
                    'module': params[1],
                })
            return None

        # INSERT into tenants
        if 'INSERT INTO tenants' in query:
            return None

        # Parameter existence check
        if 'SELECT value, is_secret FROM parameters' in query and fetch:
            # Check if we already seeded this param
            if params and len(params) >= 4:
                scope, scope_id, namespace, key = params[0], params[1], params[2], params[3]
                for p in db._inserted_params:
                    if (p['scope'] == scope and p['scope_id'] == scope_id
                            and p['namespace'] == namespace and p['key'] == key):
                        return [{'value': p['value'], 'is_secret': False}]
            return []

        # INSERT/UPSERT into parameters (set_param)
        if 'INSERT INTO parameters' in query and not fetch:
            if params and len(params) >= 5:
                import json
                db._inserted_params.append({
                    'scope': params[0],
                    'scope_id': params[1],
                    'namespace': params[2],
                    'key': params[3],
                    'value': params[4],
                })
            return None

        # Chart of accounts count
        if 'SELECT COUNT' in query and 'rekeningschema' in query:
            return [{'cnt': 0}]

        # UPDATE queries
        if query.strip().upper().startswith('UPDATE'):
            return None

        return []

    db.execute_query = MagicMock(side_effect=execute_query_side_effect)
    return db


# ---------------------------------------------------------------------------
# Bug 1.2: Default modules should NOT include STR
# ---------------------------------------------------------------------------

class TestBug1_2_DefaultModulesExcludeSTR:
    """
    Bug 1.2: When provisioning without explicit modules, STR should NOT be
    in the default module list.

    **Validates: Requirements 1.2**
    """

    @given(tenant=tenant_names)
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_provision_without_modules_excludes_str(self, tenant):
        """
        Property: For any tenant provisioned without explicit modules,
        STR must NOT be in the enabled modules.

        On unfixed code this FAILS because default is ['FIN', 'STR', 'TENADMIN'].
        """
        import inspect
        import ast
        import routes.sysadmin_provisioning as prov_module

        source = inspect.getsource(prov_module.provision_signup)

        # Parse the source to find the default modules list
        # The pattern is: modules = data.get('modules', ['FIN', 'STR', 'TENADMIN'])
        # We extract the actual default value used in the code
        tree = ast.parse(source)

        default_modules = None
        for node in ast.walk(tree):
            # Look for: data.get('modules', <default>)
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'get'
                    and len(node.args) >= 2):
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and first_arg.value == 'modules':
                    # Found it — evaluate the default (second arg)
                    default_node = node.args[1]
                    default_modules = ast.literal_eval(default_node)
                    break

        assert default_modules is not None, (
            "Could not find data.get('modules', ...) in provision_signup source"
        )

        # Expected behavior: default modules should NOT include STR
        assert 'STR' not in default_modules, (
            f"Bug 1.2 confirmed: STR is in default modules. "
            f"Default modules list: {default_modules}. "
            f"Expected: ['FIN', 'TENADMIN'] without STR."
        )


# ---------------------------------------------------------------------------
# Bug 1.1: S3 shared bucket must be seeded at tenant scope
# ---------------------------------------------------------------------------

class TestBug1_1_StorageBucketSeeded:
    """
    Bug 1.1: When provisioning with s3_shared storage, the system must seed
    storage.s3_shared_bucket at tenant scope.

    **Validates: Requirements 1.1**
    """

    @given(tenant=tenant_names, locale=locales)
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_provision_seeds_s3_shared_bucket(self, tenant, locale):
        """
        Property: For any tenant provisioned with s3_shared storage,
        storage.s3_shared_bucket must have a tenant-scope value.

        On unfixed code this FAILS because create_and_provision_tenant
        never calls seed_module_params or seeds storage params.
        """
        from services.tenant_provisioning_service import TenantProvisioningService

        db = make_mock_db()
        service = TenantProvisioningService(db)

        with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-test'}):
            result = service.create_and_provision_tenant(
                administration=tenant,
                display_name=f'{tenant} Display',
                contact_email=f'{tenant.lower()}@example.com',
                modules=['FIN', 'TENADMIN'],
                created_by='sysadmin@example.com',
                locale=locale,
            )

        # Assert: storage.s3_shared_bucket must be seeded at tenant scope
        storage_bucket_params = [
            p for p in db._inserted_params
            if p['namespace'] == 'storage' and p['key'] == 's3_shared_bucket'
            and p['scope'] == 'tenant' and p['scope_id'] == tenant
        ]

        assert len(storage_bucket_params) > 0, (
            f"Bug 1.1 confirmed: storage.s3_shared_bucket not seeded for tenant '{tenant}'. "
            f"All inserted params: {db._inserted_params}"
        )


# ---------------------------------------------------------------------------
# Bug 1.4: Module params must be seeded at provisioning
# ---------------------------------------------------------------------------

class TestBug1_4_ModuleParamsSeeded:
    """
    Bug 1.4: When provisioning with FIN module, fin.default_currency must
    have a tenant-scope row (not just CODE_DEFAULT).

    **Validates: Requirements 1.4**
    """

    @given(tenant=tenant_names, locale=locales)
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_provision_seeds_fin_params(self, tenant, locale):
        """
        Property: For any tenant provisioned with FIN module,
        fin.default_currency must have a tenant-scope parameter row.

        On unfixed code this FAILS because create_and_provision_tenant
        never calls seed_module_params.
        """
        from services.tenant_provisioning_service import TenantProvisioningService

        db = make_mock_db()
        service = TenantProvisioningService(db)

        result = service.create_and_provision_tenant(
            administration=tenant,
            display_name=f'{tenant} Display',
            contact_email=f'{tenant.lower()}@example.com',
            modules=['FIN', 'TENADMIN'],
            created_by='sysadmin@example.com',
            locale=locale,
        )

        # Assert: fin.default_currency must be seeded at tenant scope
        fin_currency_params = [
            p for p in db._inserted_params
            if p['namespace'] == 'fin' and p['key'] == 'default_currency'
            and p['scope'] == 'tenant' and p['scope_id'] == tenant
        ]

        assert len(fin_currency_params) > 0, (
            f"Bug 1.4 confirmed: fin.default_currency not seeded for tenant '{tenant}'. "
            f"All inserted params: {db._inserted_params}"
        )


# ---------------------------------------------------------------------------
# Bug 1.5: activate_module must seed params after activation
# ---------------------------------------------------------------------------

class TestBug1_5_ActivateModuleSeedsParams:
    """
    Bug 1.5: When activating a module (e.g. ZZP), the system must seed
    the module's required parameters.

    **Validates: Requirements 1.5**
    """

    @given(tenant=tenant_names)
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_activate_zzp_seeds_params(self, tenant):
        """
        Property: For any tenant activating ZZP module,
        zzp.invoice_prefix must have a tenant-scope parameter row after activation.

        On unfixed code this FAILS because activate_module only inserts
        the tenant_modules row but never calls seed_module_params.
        """
        from services.module_registry import activate_module

        db = make_mock_db()

        # Pre-condition: FIN must be active (ZZP depends on FIN)
        db._inserted_modules.append({'tenant': tenant, 'module': 'FIN'})

        activate_module(db, tenant, 'ZZP', activated_by='admin@example.com')

        # Assert: zzp.invoice_prefix must be seeded at tenant scope
        zzp_prefix_params = [
            p for p in db._inserted_params
            if p['namespace'] == 'zzp' and p['key'] == 'invoice_prefix'
            and p['scope'] == 'tenant' and p['scope_id'] == tenant
        ]

        assert len(zzp_prefix_params) > 0, (
            f"Bug 1.5 confirmed: zzp.invoice_prefix not seeded after activating ZZP "
            f"for tenant '{tenant}'. All inserted params: {db._inserted_params}"
        )


# ---------------------------------------------------------------------------
# Bug 1.7: Branding fields must have visible_when for storage provider
# ---------------------------------------------------------------------------

class TestBug1_7_BrandingVisibility:
    """
    Bug 1.7: For S3 tenants, company_logo_file_id should be hidden or have
    a visible_when condition restricting it to google_drive.

    **Validates: Requirements 1.7**
    """

    @given(tenant_modules=st.just(['FIN', 'STR', 'TENADMIN']))
    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_schema_branding_has_visible_when(self, tenant_modules):
        """
        Property: For any tenant with STR module, the company_logo_file_id
        field in str_branding must have a visible_when condition that
        restricts it to google_drive provider.

        On unfixed code this FAILS because company_logo_file_id has no
        visible_when condition — it's always shown with "Google Drive" label.
        """
        from services.parameter_schema import get_schema_for_tenant

        schema = get_schema_for_tenant(tenant_modules)

        # str_branding should be in schema since STR is active
        assert 'str_branding' in schema, "str_branding not in schema for STR tenant"

        str_branding_params = schema['str_branding']['params']
        logo_param = str_branding_params.get('company_logo_file_id')

        assert logo_param is not None, "company_logo_file_id not found in str_branding"

        # Expected: visible_when should restrict to google_drive
        visible_when = logo_param.get('visible_when')
        assert visible_when is not None, (
            f"Bug 1.7 confirmed: company_logo_file_id in str_branding has no "
            f"visible_when condition. Label: '{logo_param.get('label')}'. "
            f"S3 tenants see Google Drive-specific field without restriction."
        )

        # The visible_when should reference invoice_provider = google_drive
        assert 'invoice_provider' in visible_when, (
            f"Bug 1.7: visible_when exists but doesn't reference invoice_provider. "
            f"Got: {visible_when}"
        )

    @given(tenant_modules=st.just(['FIN', 'ZZP', 'TENADMIN']))
    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_zzp_branding_has_visible_when(self, tenant_modules):
        """
        Property: For any tenant with ZZP module, the company_logo_file_id
        field in zzp_branding must have a visible_when condition.

        On unfixed code this FAILS because zzp_branding company_logo_file_id
        has no visible_when condition.
        """
        from services.parameter_schema import get_schema_for_tenant

        schema = get_schema_for_tenant(tenant_modules)

        assert 'zzp_branding' in schema, "zzp_branding not in schema for ZZP tenant"

        zzp_branding_params = schema['zzp_branding']['params']
        logo_param = zzp_branding_params.get('company_logo_file_id')

        assert logo_param is not None, "company_logo_file_id not found in zzp_branding"

        visible_when = logo_param.get('visible_when')
        assert visible_when is not None, (
            f"Bug 1.7 confirmed: company_logo_file_id in zzp_branding has no "
            f"visible_when condition. Label: '{logo_param.get('label')}'. "
            f"S3 tenants see Google Drive-specific field without restriction."
        )

        assert 'invoice_provider' in visible_when, (
            f"Bug 1.7: visible_when exists but doesn't reference invoice_provider. "
            f"Got: {visible_when}"
        )
