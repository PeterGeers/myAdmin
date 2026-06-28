"""
Preservation Property Tests — Onboarding Storage & Visibility Fix

Property 2: Preservation - Explicit STR, Google Drive, Idempotent Re-provisioning,
and Dependencies Unchanged.

These tests capture EXISTING correct behavior on the UNFIXED code. They must PASS
on unfixed code and continue to PASS after the fix is applied (no regressions).

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

pytestmark = pytest.mark.slow

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Tenant names: alphanumeric PascalCase identifiers
tenant_names = st.from_regex(r'[A-Z][a-zA-Z0-9]{2,15}', fullmatch=True)

# Locales
locales = st.sampled_from(['nl', 'en'])

# Module lists that explicitly include STR (preservation: STR stays enabled)
module_lists_with_str = st.lists(
    st.sampled_from(['FIN', 'STR', 'ZZP']),
    min_size=1,
    max_size=3,
).filter(lambda mods: 'STR' in mods).map(lambda mods: list(set(mods)))

# Module lists that do NOT include TENADMIN (preservation: auto-added)
module_lists_without_tenadmin = st.lists(
    st.sampled_from(['FIN', 'STR', 'ZZP']),
    min_size=1,
    max_size=3,
).map(lambda mods: [m for m in set(mods) if m != 'TENADMIN'])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_db(existing_tenant=False, existing_modules=None):
    """
    Create a mock DatabaseManager that tracks queries.

    Args:
        existing_tenant: If True, simulate tenant already exists (for idempotent tests)
        existing_modules: List of module names already inserted (for idempotent tests)
    """
    db = MagicMock()
    db._inserted_modules = []
    db._inserted_params = []
    db._queries = []

    if existing_modules:
        for mod in existing_modules:
            db._inserted_modules.append({'tenant': '__existing__', 'module': mod})

    def execute_query_side_effect(query, params=None, fetch=True, commit=False):
        db._queries.append((query, params, fetch, commit))

        # Tenant existence check
        if 'SELECT administration FROM tenants' in query:
            if existing_tenant and params:
                return [{'administration': params[0]}]
            return []

        # Module existence check (for _insert_modules idempotent guard)
        if 'SELECT id FROM tenant_modules' in query and fetch:
            if existing_modules and params and len(params) >= 2:
                tenant, module = params[0], params[1]
                if module in existing_modules:
                    return [{'id': 1}]
            return []

        # Module is_active check (has_module)
        if 'SELECT is_active' in query and 'tenant_modules' in query:
            if params and len(params) >= 2:
                tenant, module = params[0], params[1]
                for ins in db._inserted_modules:
                    if ins['module'] == module and (
                        ins['tenant'] == tenant or ins['tenant'] == '__existing__'
                    ):
                        return [{'is_active': True}]
            return []

        # INSERT into tenant_modules
        if 'INSERT INTO tenant_modules' in query:
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
# Preservation 3.1: Explicit STR remains enabled after provisioning
# ---------------------------------------------------------------------------

class TestPreservation_ExplicitSTR:
    """
    Preservation 3.1: When STR is explicitly included in the modules list,
    it must remain enabled after provisioning.

    **Validates: Requirements 3.1**
    """

    @given(tenant=tenant_names, modules=module_lists_with_str, locale=locales)
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_explicit_str_remains_enabled(self, tenant, modules, locale):
        """
        Property: For all module lists that explicitly include STR,
        STR remains enabled after provisioning.
        """
        from services.tenant_provisioning_service import TenantProvisioningService

        db = make_mock_db()
        service = TenantProvisioningService(db)

        result = service.create_and_provision_tenant(
            administration=tenant,
            display_name=f'{tenant} Display',
            contact_email=f'{tenant.lower()}@example.com',
            modules=modules,
            created_by='sysadmin@example.com',
            locale=locale,
        )

        # STR must be in the inserted modules
        inserted_module_names = [m['module'] for m in db._inserted_modules]
        assert 'STR' in inserted_module_names, (
            f"Preservation violation: STR was explicitly in modules={modules} "
            f"but was not inserted. Inserted: {inserted_module_names}"
        )

        # STR must show as 'created' in results
        module_results = {m['name']: m['status'] for m in result['modules']}
        assert 'STR' in module_results, (
            f"Preservation violation: STR not in provisioning results. "
            f"Results: {module_results}"
        )


# ---------------------------------------------------------------------------
# Preservation 3.2, 3.7: Google Drive tenants see Google Drive params
# ---------------------------------------------------------------------------

class TestPreservation_GoogleDrive:
    """
    Preservation 3.2, 3.7: Tenants with Google Drive as storage provider
    continue to see Google Drive parameters and labels.

    **Validates: Requirements 3.2, 3.7**
    """

    @given(
        tenant_modules=st.just(['FIN', 'STR', 'TENADMIN']),
    )
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_google_drive_params_visible_in_schema(self, tenant_modules):
        """
        Property: For all tenants with google_drive provider,
        Google Drive params are visible in the schema.
        """
        from services.parameter_schema import get_schema_for_tenant

        schema = get_schema_for_tenant(tenant_modules)

        # Storage section must be present
        assert 'storage' in schema, "Storage section missing from schema"

        storage_params = schema['storage']['params']

        # Google Drive folder params must exist with visible_when = google_drive
        gd_params = ['google_drive_folder_id', 'google_drive_root_folder_id',
                     'google_drive_templates_folder_id', 'google_drive_invoices_folder_id']

        for param_name in gd_params:
            assert param_name in storage_params, (
                f"Google Drive param '{param_name}' missing from storage schema"
            )
            param = storage_params[param_name]
            visible_when = param.get('visible_when', {})
            assert visible_when.get('invoice_provider') == 'google_drive', (
                f"Google Drive param '{param_name}' should be visible when "
                f"invoice_provider=google_drive. Got visible_when={visible_when}"
            )

    @given(
        tenant_modules=st.just(['FIN', 'STR', 'TENADMIN']),
    )
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_s3_bucket_not_seeded_without_env_var(self, tenant_modules):
        """
        Property: When S3_SHARED_BUCKET env var is not set, no S3 bucket
        parameter is seeded during provisioning.

        S3 shared is the default storage provider for all new tenants.
        Seeding only occurs when the S3_SHARED_BUCKET env var is configured
        (i.e., the infrastructure is available).  Without the env var,
        no storage params are written.
        """
        from services.tenant_provisioning_service import TenantProvisioningService

        db = make_mock_db()
        service = TenantProvisioningService(db)

        # Explicitly unset S3_SHARED_BUCKET to simulate env without S3 infra
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('S3_SHARED_BUCKET', None)
            result = service.create_and_provision_tenant(
                administration='NoS3EnvTenant',
                display_name='No S3 Env Tenant',
                contact_email='nos3@example.com',
                modules=tenant_modules,
                created_by='sysadmin@example.com',
                locale='nl',
            )

        # Without S3_SHARED_BUCKET env var, no S3 bucket param should be seeded
        s3_bucket_params = [
            p for p in db._inserted_params
            if p['namespace'] == 'storage' and p['key'] == 's3_shared_bucket'
        ]

        assert len(s3_bucket_params) == 0, (
            f"S3 bucket was seeded without S3_SHARED_BUCKET env var. "
            f"Params: {s3_bucket_params}"
        )


# ---------------------------------------------------------------------------
# Preservation 3.3: Idempotent re-provisioning skips without errors
# ---------------------------------------------------------------------------

class TestPreservation_Idempotent:
    """
    Preservation 3.3: Re-provisioning an existing tenant skips already-existing
    records without errors or duplicates.

    **Validates: Requirements 3.3**
    """

    @given(tenant=tenant_names, locale=locales)
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_reprovision_existing_tenant_skips(self, tenant, locale):
        """
        Property: For all re-provisioning of existing tenants,
        no errors occur and existing records are skipped.
        """
        from services.tenant_provisioning_service import TenantProvisioningService

        modules = ['FIN', 'STR', 'TENADMIN']

        # Simulate existing tenant with existing modules
        db = make_mock_db(existing_tenant=True, existing_modules=modules)
        service = TenantProvisioningService(db)

        # This should NOT raise any exception
        result = service.create_and_provision_tenant(
            administration=tenant,
            display_name=f'{tenant} Display',
            contact_email=f'{tenant.lower()}@example.com',
            modules=modules,
            created_by='sysadmin@example.com',
            locale=locale,
        )

        # Tenant should be 'skipped' (already exists)
        assert result['tenant'] == 'skipped', (
            f"Preservation violation: existing tenant was not skipped. "
            f"Got: {result['tenant']}"
        )

        # All modules should be 'skipped' (already exist)
        for mod_result in result['modules']:
            assert mod_result['status'] == 'skipped', (
                f"Preservation violation: existing module '{mod_result['name']}' "
                f"was not skipped. Got: {mod_result['status']}"
            )

    @given(tenant=tenant_names, locale=locales)
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_provision_twice_no_duplicates(self, tenant, locale):
        """
        Property: Provisioning the same tenant twice produces no duplicate modules.
        """
        from services.tenant_provisioning_service import TenantProvisioningService

        modules = ['FIN', 'TENADMIN']

        # First provisioning
        db = make_mock_db()
        service = TenantProvisioningService(db)

        result1 = service.create_and_provision_tenant(
            administration=tenant,
            display_name=f'{tenant} Display',
            contact_email=f'{tenant.lower()}@example.com',
            modules=modules,
            created_by='sysadmin@example.com',
            locale=locale,
        )

        # Count modules inserted
        first_run_modules = [m['module'] for m in db._inserted_modules]

        # Second provisioning with same db (now has existing records)
        db2 = make_mock_db(existing_tenant=True, existing_modules=first_run_modules)
        service2 = TenantProvisioningService(db2)

        result2 = service2.create_and_provision_tenant(
            administration=tenant,
            display_name=f'{tenant} Display',
            contact_email=f'{tenant.lower()}@example.com',
            modules=modules,
            created_by='sysadmin@example.com',
            locale=locale,
        )

        # Second run should skip everything
        assert result2['tenant'] == 'skipped'
        for mod_result in result2['modules']:
            assert mod_result['status'] == 'skipped', (
                f"Duplicate detected: module '{mod_result['name']}' was "
                f"'{mod_result['status']}' on second run"
            )


# ---------------------------------------------------------------------------
# Preservation 3.5: TENADMIN auto-included when missing
# ---------------------------------------------------------------------------

class TestPreservation_TenAdminAutoInclude:
    """
    Preservation 3.5: When TENADMIN is not explicitly included in the
    provisioning request, it is automatically added.

    **Validates: Requirements 3.5**
    """

    @given(tenant=tenant_names, modules=module_lists_without_tenadmin, locale=locales)
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_tenadmin_auto_added_when_missing(self, tenant, modules, locale):
        """
        Property: For all module lists missing TENADMIN,
        TENADMIN is auto-included in the provisioned modules.
        """
        assume(len(modules) > 0)  # Need at least one module

        from services.tenant_provisioning_service import TenantProvisioningService

        db = make_mock_db()
        service = TenantProvisioningService(db)

        result = service.create_and_provision_tenant(
            administration=tenant,
            display_name=f'{tenant} Display',
            contact_email=f'{tenant.lower()}@example.com',
            modules=modules,
            created_by='sysadmin@example.com',
            locale=locale,
        )

        # TENADMIN must be in the results
        module_names_in_result = [m['name'] for m in result['modules']]
        assert 'TENADMIN' in module_names_in_result, (
            f"Preservation violation: TENADMIN not auto-added. "
            f"Input modules: {modules}. Result modules: {module_names_in_result}"
        )

        # TENADMIN must be in the inserted modules
        inserted_module_names = [m['module'] for m in db._inserted_modules]
        assert 'TENADMIN' in inserted_module_names, (
            f"Preservation violation: TENADMIN not inserted into DB. "
            f"Input modules: {modules}. Inserted: {inserted_module_names}"
        )


# ---------------------------------------------------------------------------
# Preservation 3.6: Module dependency checks enforced
# ---------------------------------------------------------------------------

class TestPreservation_DependencyChecks:
    """
    Preservation 3.6: Module activation with unmet dependencies raises ValueError.

    **Validates: Requirements 3.6**
    """

    @given(tenant=tenant_names)
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_activate_zzp_without_fin_raises_error(self, tenant):
        """
        Property: For all module activations where ZZP depends on FIN
        and FIN is not active, ValueError is raised.
        """
        from services.module_registry import activate_module

        # DB with NO FIN module active
        db = make_mock_db()

        with pytest.raises(ValueError, match="FIN.*must be active"):
            activate_module(db, tenant, 'ZZP', activated_by='admin@example.com')

    @given(tenant=tenant_names)
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_activate_unknown_module_raises_error(self, tenant):
        """
        Property: Activating an unknown module raises ValueError.
        """
        from services.module_registry import activate_module

        db = make_mock_db()

        with pytest.raises(ValueError, match="Unknown module"):
            activate_module(db, tenant, 'NONEXISTENT', activated_by='admin@example.com')


# ---------------------------------------------------------------------------
# Preservation 3.4: Schema filtering by active modules
# ---------------------------------------------------------------------------

class TestPreservation_SchemaFiltering:
    """
    Preservation 3.4: get_schema_for_tenant correctly shows/hides sections
    based on active modules.

    **Validates: Requirements 3.4**
    """

    @given(
        modules=st.lists(
            st.sampled_from(['FIN', 'STR', 'ZZP', 'TENADMIN']),
            min_size=1,
            max_size=4,
        ).map(lambda mods: list(set(mods)))
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_schema_shows_only_active_module_sections(self, modules):
        """
        Property: For all module combinations, only sections matching
        active modules (or no module filter) are returned.
        """
        from services.parameter_schema import get_schema_for_tenant

        schema = get_schema_for_tenant(modules)

        # 'storage' has no module filter — always present
        assert 'storage' in schema, "Storage section should always be present"

        # 'fin' section requires FIN module
        if 'FIN' in modules:
            assert 'fin' in schema, "FIN section missing when FIN is active"
        else:
            assert 'fin' not in schema, "FIN section present when FIN is not active"

        # 'str' section requires STR module
        if 'STR' in modules:
            assert 'str' in schema, "STR section missing when STR is active"
            assert 'str_branding' in schema, "str_branding missing when STR is active"
        else:
            assert 'str' not in schema, "STR section present when STR is not active"
            assert 'str_branding' not in schema, "str_branding present when STR is not active"

        # 'zzp_branding' section requires ZZP module
        if 'ZZP' in modules:
            assert 'zzp_branding' in schema, "zzp_branding missing when ZZP is active"
        else:
            assert 'zzp_branding' not in schema, "zzp_branding present when ZZP is not active"

    @given(tenant_modules=st.just(['FIN', 'STR', 'TENADMIN']))
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_google_drive_tenant_sees_logo_field(self, tenant_modules):
        """
        Property: For Google Drive tenants with STR, company_logo_file_id
        is visible in str_branding (no visible_when restriction currently).

        **Validates: Requirements 3.7**
        """
        from services.parameter_schema import get_schema_for_tenant

        schema = get_schema_for_tenant(tenant_modules)

        assert 'str_branding' in schema
        str_branding_params = schema['str_branding']['params']

        # company_logo_file_id must exist
        assert 'company_logo_file_id' in str_branding_params, (
            "company_logo_file_id missing from str_branding"
        )

        # On unfixed code: no visible_when (shown to everyone including GD tenants)
        # After fix: visible_when={'invoice_provider': 'google_drive'} — still visible for GD
        # Either way, the field exists in the schema for Google Drive tenants
        logo_param = str_branding_params['company_logo_file_id']
        assert logo_param.get('type') == 'string', (
            f"company_logo_file_id should be type 'string', got: {logo_param.get('type')}"
        )
