"""
Unit tests for parameter_schema module.

Tests the schema filtering logic in get_schema_for_tenant, verifying that
tenant module configurations produce correct schema subsets.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'services'))

from services.parameter_schema import get_schema_for_tenant, PARAMETER_SCHEMA


@pytest.mark.unit
class TestGetSchemaForTenantAllModules:
    """Test schema returned for tenant with all modules active."""

    def test_all_modules_returns_full_schema(self):
        """When all modules are active, all sections are returned."""
        all_modules = ['STR', 'ZZP', 'FIN', 'MEMBERS']
        result = get_schema_for_tenant(all_modules)

        assert set(result.keys()) == set(PARAMETER_SCHEMA.keys())

    def test_all_modules_preserves_section_content(self):
        """Returned sections are the same objects as in PARAMETER_SCHEMA."""
        all_modules = ['STR', 'ZZP', 'FIN', 'MEMBERS']
        result = get_schema_for_tenant(all_modules)

        for ns, section in result.items():
            assert section is PARAMETER_SCHEMA[ns]


@pytest.mark.unit
class TestGetSchemaForTenantLimitedModules:
    """Test schema returned for tenant with limited modules."""

    def test_str_only_includes_str_sections(self):
        """STR-only tenant gets storage + STR-related sections."""
        result = get_schema_for_tenant(['STR'])

        assert 'storage' in result
        assert 'str_branding' in result
        assert 'str' in result
        assert 'zzp_branding' not in result
        assert 'fin' not in result

    def test_zzp_only_includes_zzp_section(self):
        """ZZP-only tenant gets storage + ZZP branding."""
        result = get_schema_for_tenant(['ZZP'])

        assert 'storage' in result
        assert 'zzp_branding' in result
        assert 'str_branding' not in result
        assert 'str' not in result
        assert 'fin' not in result

    def test_fin_only_includes_fin_section(self):
        """FIN-only tenant gets storage + financial settings."""
        result = get_schema_for_tenant(['FIN'])

        assert 'storage' in result
        assert 'fin' in result
        assert 'str_branding' not in result
        assert 'zzp_branding' not in result
        assert 'str' not in result


@pytest.mark.unit
class TestGetSchemaForTenantNoModules:
    """Test schema returned for tenant with no modules (empty list)."""

    def test_empty_modules_returns_only_global_sections(self):
        """With no modules active, only module-less sections are returned."""
        result = get_schema_for_tenant([])

        assert 'storage' in result
        assert len(result) == 1

    def test_empty_modules_excludes_all_module_sections(self):
        """All module-gated sections are excluded when modules is empty."""
        result = get_schema_for_tenant([])

        for ns, section in PARAMETER_SCHEMA.items():
            if section.get('module'):
                assert ns not in result


@pytest.mark.unit
class TestSchemaIncludesExpectedParameters:
    """Test schema includes expected parameter definitions."""

    def test_storage_section_has_invoice_provider(self):
        """Storage section includes invoice_provider parameter."""
        result = get_schema_for_tenant([])

        assert 'invoice_provider' in result['storage']['params']

    def test_str_section_has_rooms_and_beds(self):
        """STR section includes rooms and beds parameters."""
        result = get_schema_for_tenant(['STR'])

        str_params = result['str']['params']
        assert 'aantal_kamers' in str_params
        assert 'aantal_slaapplaatsen' in str_params

    def test_fin_section_has_currency_and_fiscal_year(self):
        """FIN section includes currency and fiscal year parameters."""
        result = get_schema_for_tenant(['FIN'])

        fin_params = result['fin']['params']
        assert 'default_currency' in fin_params
        assert 'fiscal_year_start_month' in fin_params


@pytest.mark.unit
class TestSchemaStructureValidity:
    """Test schema structure is valid (has expected keys/types)."""

    def test_all_sections_have_label(self):
        """Every section must have a label key."""
        result = get_schema_for_tenant(['STR', 'ZZP', 'FIN'])

        for ns, section in result.items():
            assert 'label' in section, f"Section '{ns}' missing 'label'"
            assert isinstance(section['label'], str)

    def test_all_sections_have_params_dict(self):
        """Every section must have a params dict."""
        result = get_schema_for_tenant(['STR', 'ZZP', 'FIN'])

        for ns, section in result.items():
            assert 'params' in section, f"Section '{ns}' missing 'params'"
            assert isinstance(section['params'], dict)

    def test_all_params_have_type_field(self):
        """Every parameter must define a type."""
        result = get_schema_for_tenant(['STR', 'ZZP', 'FIN'])

        for ns, section in result.items():
            for param_name, param_def in section['params'].items():
                assert 'type' in param_def, (
                    f"Param '{param_name}' in '{ns}' missing 'type'"
                )
                assert param_def['type'] in ('string', 'number', 'json', 'secret')

    def test_all_params_have_label(self):
        """Every parameter must define a label."""
        result = get_schema_for_tenant(['STR', 'ZZP', 'FIN'])

        for ns, section in result.items():
            for param_name, param_def in section['params'].items():
                assert 'label' in param_def, (
                    f"Param '{param_name}' in '{ns}' missing 'label'"
                )


@pytest.mark.unit
class TestDifferentModuleCombinations:
    """Test different module combinations produce different schemas."""

    def test_str_and_fin_differs_from_str_only(self):
        """STR+FIN combination includes more sections than STR alone."""
        str_only = get_schema_for_tenant(['STR'])
        str_fin = get_schema_for_tenant(['STR', 'FIN'])

        assert 'fin' not in str_only
        assert 'fin' in str_fin
        assert len(str_fin) > len(str_only)

    def test_zzp_and_str_includes_both_brandings(self):
        """ZZP+STR combination includes both branding sections."""
        result = get_schema_for_tenant(['ZZP', 'STR'])

        assert 'zzp_branding' in result
        assert 'str_branding' in result

    def test_each_combination_is_deterministic(self):
        """Same input always produces the same output."""
        modules = ['STR', 'FIN']
        result1 = get_schema_for_tenant(modules)
        result2 = get_schema_for_tenant(modules)

        assert result1.keys() == result2.keys()


@pytest.mark.unit
class TestMembersNamespaceGating:
    """Test the MEMBERS-gated `members` namespace (s5c task 2.1, R3.1, C-SCHEMA)."""

    def test_members_active_includes_namespace(self):
        """MEMBERS in active modules -> `members` namespace is present."""
        result = get_schema_for_tenant(['MEMBERS'])

        assert 'members' in result
        assert result['members'] is PARAMETER_SCHEMA['members']

    def test_members_inactive_excludes_namespace(self):
        """MEMBERS not active -> `members` namespace is absent (module gating)."""
        assert 'members' not in get_schema_for_tenant([])
        assert 'members' not in get_schema_for_tenant(['STR', 'ZZP', 'FIN'])

    def test_members_namespace_declares_expected_params(self):
        """`members` declares the json config params, the mail-enabled gate, and the mail params.

        field_overlay / scope_dimensions / view_contexts are json; mail_enabled is the
        boolean per-tenant "mail-enabled / SES-certified" gate (pivot-output-actions R0,
        projected as config#mail) that fails closed to False. mail_domain / mail_local_part /
        mail_certified (mail spec Phase 0, R4/§5f) feed the per-tenant From + the fail-closed
        pre-send certification gate in the SAME config#mail row.
        """
        result = get_schema_for_tenant(['MEMBERS'])
        params = result['members']['params']

        assert set(params.keys()) == {
            'field_overlay', 'scope_dimensions', 'view_contexts', 'mail_enabled',
            'mail_domain', 'mail_local_part', 'mail_certified',
        }
        for key in ('field_overlay', 'scope_dimensions', 'view_contexts'):
            assert params[key]['type'] == 'json', f"{key} must be a json param"

        mail = params['mail_enabled']
        assert mail['type'] == 'boolean'
        assert mail['default'] is False  # fail-closed: the gate opens only on explicit True

    def test_members_mail_params_shape(self):
        """mail_domain / mail_local_part / mail_certified have the expected types + defaults.

        mail_domain is a string; mail_local_part is a string DEFAULTING to 'noreply';
        mail_certified is a boolean DEFAULTING to False (fail-closed pre-send gate).
        """
        params = get_schema_for_tenant(['MEMBERS'])['members']['params']

        assert params['mail_domain']['type'] == 'string'

        assert params['mail_local_part']['type'] == 'string'
        assert params['mail_local_part']['default'] == 'noreply'

        assert params['mail_certified']['type'] == 'boolean'
        assert params['mail_certified']['default'] is False

    def test_members_namespace_gated_by_members_module(self):
        """The namespace's module gate is exactly 'MEMBERS'."""
        assert PARAMETER_SCHEMA['members'].get('module') == 'MEMBERS'

    def test_members_params_have_bilingual_labels(self):
        """Each members param carries both label and label_nl."""
        params = PARAMETER_SCHEMA['members']['params']
        for key, param_def in params.items():
            assert 'label' in param_def, f"{key} missing label"
            assert 'label_nl' in param_def, f"{key} missing label_nl"
