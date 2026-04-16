"""
Unit tests for Phase 13: Invoice PDF Header Details & Branding Namespace.

Covers:
- parameter_schema.py contains zzp_branding namespace with all required keys (Req 20.1)
- parameter_schema.py has str_branding (not branding) with module STR (Req 20.2)
- PDF generator reads from zzp_branding namespace (Req 20.3)
- Missing zzp_branding params result in empty strings, no placeholders (Req 20.5)
- zzp_invoice is registered as a template type (Req 20.7)

Reference: .kiro/specs/zzp-module/tasks.md Task 13.7
"""

import os
import sys
import pytest
from unittest.mock import Mock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.parameter_schema import PARAMETER_SCHEMA
from services.pdf_generator_service import PDFGeneratorService
from services.template_service import TemplateService


# ── Helpers ─────────────────────────────────────────────────


def _make_pdf_service(param_svc=None, template_svc=None, db=None):
    """Create a PDFGeneratorService with mocked dependencies."""
    db = db or Mock()
    template_svc = template_svc or Mock(
        get_template_metadata=Mock(return_value=None)
    )
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return PDFGeneratorService(
        db=db, template_service=template_svc, parameter_service=param_svc
    )


def _sample_invoice(**overrides):
    """Minimal invoice dict for rendering tests."""
    base = {
        'invoice_number': 'INV-2026-0001',
        'invoice_type': 'invoice',
        'invoice_date': '2026-04-15',
        'due_date': '2026-05-15',
        'payment_terms_days': 30,
        'currency': 'EUR',
        'subtotal': 1000.0,
        'vat_total': 210.0,
        'grand_total': 1210.0,
        'notes': '',
        'contact': {
            'id': 1,
            'client_id': 'ACME',
            'company_name': 'Acme Corp B.V.',
            'contact_person': 'Jan de Vries',
            'street_address': 'Keizersgracht 100',
            'postal_code': '1015 AA',
            'city': 'Amsterdam',
            'country': 'NL',
            'vat_number': 'NL123456789B01',
        },
        'lines': [
            {
                'description': 'Consulting',
                'quantity': 10.0,
                'unit_price': 100.0,
                'vat_rate': 21.0,
                'line_total': 1000.0,
            },
        ],
        'vat_summary': [
            {
                'vat_code': 'high',
                'vat_rate': 21.0,
                'base_amount': 1000.0,
                'vat_amount': 210.0,
            },
        ],
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════
# 1. parameter_schema.py — zzp_branding namespace (Req 20.1)
# ═══════════════════════════════════════════════════════════


class TestZzpBrandingNamespace:
    """Verify zzp_branding namespace exists with all required keys."""

    def test_zzp_branding_exists_in_schema(self):
        """Req 20.1: zzp_branding namespace must exist."""
        assert 'zzp_branding' in PARAMETER_SCHEMA

    def test_zzp_branding_module_is_zzp(self):
        """Req 20.1: zzp_branding must be scoped to ZZP module."""
        assert PARAMETER_SCHEMA['zzp_branding']['module'] == 'ZZP'

    def test_zzp_branding_has_label(self):
        assert 'label' in PARAMETER_SCHEMA['zzp_branding']
        assert len(PARAMETER_SCHEMA['zzp_branding']['label']) > 0

    def test_zzp_branding_has_dutch_label(self):
        assert 'label_nl' in PARAMETER_SCHEMA['zzp_branding']
        assert len(PARAMETER_SCHEMA['zzp_branding']['label_nl']) > 0

    def test_zzp_branding_has_company_logo_file_id(self):
        """Req 20.1: company_logo_file_id key required."""
        assert 'company_logo_file_id' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_has_company_name(self):
        """Req 20.1: company_name key required."""
        assert 'company_name' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_has_company_address(self):
        """Req 20.1: company_address key required."""
        assert 'company_address' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_has_company_postal_city(self):
        """Req 20.1: company_postal_city key required."""
        assert 'company_postal_city' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_has_company_country(self):
        """Req 20.1: company_country key required."""
        assert 'company_country' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_has_company_vat(self):
        """Req 20.1: company_vat key required."""
        assert 'company_vat' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_has_company_coc(self):
        """Req 20.1: company_coc key required."""
        assert 'company_coc' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_has_company_phone(self):
        """Req 20.1: company_phone key required (new for ZZP)."""
        assert 'company_phone' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_does_not_have_company_iban(self):
        """company_iban is resolved from rekeningschema, not a branding param."""
        assert 'company_iban' not in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_has_contact_email(self):
        """Req 20.1: contact_email key required."""
        assert 'contact_email' in PARAMETER_SCHEMA['zzp_branding']['params']

    def test_zzp_branding_all_required_keys_present(self):
        """Req 20.1: All 9 required branding keys must be present.
        Note: company_iban is not a branding param — it comes from rekeningschema."""
        required_keys = {
            'company_logo_file_id',
            'company_name',
            'company_address',
            'company_postal_city',
            'company_country',
            'company_vat',
            'company_coc',
            'company_phone',
            'contact_email',
        }
        actual_keys = set(PARAMETER_SCHEMA['zzp_branding']['params'].keys())
        missing = required_keys - actual_keys
        assert not missing, f"Missing keys in zzp_branding: {missing}"

    def test_zzp_branding_params_have_labels(self):
        """Each param should have label and label_nl."""
        for key, param in PARAMETER_SCHEMA['zzp_branding']['params'].items():
            assert 'label' in param, f"zzp_branding.{key} missing label"
            assert 'label_nl' in param, f"zzp_branding.{key} missing label_nl"

    def test_zzp_branding_params_have_type(self):
        """Each param should have a type."""
        for key, param in PARAMETER_SCHEMA['zzp_branding']['params'].items():
            assert 'type' in param, f"zzp_branding.{key} missing type"


# ═══════════════════════════════════════════════════════════
# 2. parameter_schema.py — str_branding (not branding) (Req 20.2)
# ═══════════════════════════════════════════════════════════


class TestStrBrandingNamespace:
    """Verify branding was renamed to str_branding with module STR."""

    def test_old_branding_namespace_does_not_exist(self):
        """Req 20.2: The old 'branding' namespace must not exist."""
        assert 'branding' not in PARAMETER_SCHEMA

    def test_str_branding_exists(self):
        """Req 20.2: str_branding namespace must exist."""
        assert 'str_branding' in PARAMETER_SCHEMA

    def test_str_branding_module_is_str(self):
        """Req 20.2: str_branding must be scoped to STR module."""
        assert PARAMETER_SCHEMA['str_branding']['module'] == 'STR'

    def test_str_branding_has_label(self):
        assert PARAMETER_SCHEMA['str_branding']['label'] == 'STR Branding'

    def test_str_branding_has_dutch_label(self):
        assert PARAMETER_SCHEMA['str_branding']['label_nl'] == 'STR Huisstijl'

    def test_str_branding_has_company_name(self):
        """str_branding should retain the original branding keys."""
        assert 'company_name' in PARAMETER_SCHEMA['str_branding']['params']

    def test_str_branding_has_company_logo_file_id(self):
        assert 'company_logo_file_id' in PARAMETER_SCHEMA['str_branding']['params']

    def test_str_branding_has_contact_email(self):
        assert 'contact_email' in PARAMETER_SCHEMA['str_branding']['params']


# ═══════════════════════════════════════════════════════════
# 3. PDF generator reads from zzp_branding namespace (Req 20.3)
# ═══════════════════════════════════════════════════════════


class TestPdfGeneratorBrandingNamespace:
    """Verify PDFGeneratorService reads branding from zzp_branding."""

    def test_get_branding_calls_zzp_branding_namespace(self):
        """Req 20.3: _get_branding must read from zzp_branding namespace."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        svc._get_branding('TestTenant')

        # All calls should use 'zzp_branding' namespace
        for c in param_svc.get_param.call_args_list:
            namespace = c[0][0]
            assert namespace == 'zzp_branding', (
                f"Expected namespace 'zzp_branding', got '{namespace}'"
            )

    def test_get_branding_reads_all_keys(self):
        """Req 20.3: _get_branding must read all branding keys."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        svc._get_branding('TestTenant')

        called_keys = [c[0][1] for c in param_svc.get_param.call_args_list]
        expected_keys = [
            'company_name', 'company_address', 'company_postal_city',
            'company_country', 'company_vat', 'company_coc',
            'company_iban', 'company_phone', 'contact_email',
        ]
        for key in expected_keys:
            assert key in called_keys, f"_get_branding did not read key '{key}'"

    def test_get_branding_returns_configured_values(self):
        """Req 20.3: Configured values should be returned in the dict."""
        def mock_get_param(ns, key, tenant=None):
            if ns == 'zzp_branding' and key == 'company_name':
                return 'Test Company B.V.'
            if ns == 'zzp_branding' and key == 'company_vat':
                return 'NL123456789B01'
            return None

        param_svc = Mock()
        param_svc.get_param = Mock(side_effect=mock_get_param)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        branding = svc._get_branding('TestTenant')

        assert branding['company_name'] == 'Test Company B.V.'
        assert branding['company_vat'] == 'NL123456789B01'

    def test_get_tenant_logo_reads_from_zzp_branding(self):
        """Req 20.3: _get_tenant_logo must read from zzp_branding namespace."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        svc = _make_pdf_service(param_svc=param_svc)

        svc._get_tenant_logo('TestTenant')

        param_svc.get_param.assert_called_with(
            'zzp_branding', 'company_logo_file_id', tenant='TestTenant'
        )

    def test_render_html_includes_branding_in_output(self):
        """Req 20.3: Rendered HTML should contain branding values."""
        def mock_get_param(ns, key, tenant=None):
            mapping = {
                'company_name': 'My ZZP Company',
                'company_vat': 'NL999888777B01',
                'company_coc': '12345678',
                'company_phone': '+31612345678',
                'contact_email': 'info@myzzp.nl',
            }
            if ns == 'zzp_branding':
                return mapping.get(key)
            return None

        param_svc = Mock()
        param_svc.get_param = Mock(side_effect=mock_get_param)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        html = svc._render_html('TestTenant', _sample_invoice())

        assert 'My ZZP Company' in html
        assert 'NL999888777B01' in html
        assert '12345678' in html
        assert '+31612345678' in html
        assert 'info@myzzp.nl' in html

    def test_get_branding_resolves_iban_from_rekeningschema(self):
        """company_iban is resolved from rekeningschema, not zzp_branding params."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        db = Mock()
        # Simulate rekeningschema returning an IBAN for the invoice bank account
        db.execute_query = Mock(return_value=[{'iban': 'NL80RABO0107936917'}])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        branding = svc._get_branding('TestTenant')

        assert branding.get('company_iban') == 'NL80RABO0107936917'

    def test_get_branding_iban_empty_when_no_ledger_account(self):
        """No invoice bank account flagged → no company_iban in branding."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        branding = svc._get_branding('TestTenant')

        assert branding.get('company_iban') is None


# ═══════════════════════════════════════════════════════════
# 4. Missing zzp_branding params → empty strings (Req 20.5)
# ═══════════════════════════════════════════════════════════


class TestMissingBrandingParams:
    """Verify missing branding params produce empty strings, not placeholders."""

    def test_get_branding_returns_empty_dict_when_no_params(self):
        """Req 20.5: No configured params → empty dict (no placeholders)."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        branding = svc._get_branding('TestTenant')

        # Should be empty — no placeholder values
        assert branding.get('company_name') is None or branding.get('company_name') == ''
        assert branding.get('company_vat') is None or branding.get('company_vat') == ''

    def test_render_html_no_branding_no_placeholder_text(self):
        """Req 20.5: Missing branding should not show placeholder text like '[Company Name]'."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        html = svc._render_html('TestTenant', _sample_invoice())

        # No placeholder patterns should appear
        assert '{{' not in html, "Unreplaced template placeholders found"
        assert '}}' not in html, "Unreplaced template placeholders found"
        assert '[Company' not in html
        assert '[company' not in html
        assert 'N/A' not in html

    def test_render_html_tenant_fields_are_empty_when_no_branding(self):
        """Req 20.5: Tenant fields should be empty strings when not configured."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        html = svc._render_html('TestTenant', _sample_invoice())

        # The template should still render (no errors)
        assert 'INV-2026-0001' in html
        # Contact details should still be present
        assert 'Acme Corp B.V.' in html

    def test_render_html_partial_branding_only_shows_configured(self):
        """Req 20.5: Only configured fields appear; others are empty."""
        def mock_get_param(ns, key, tenant=None):
            if ns == 'zzp_branding' and key == 'company_name':
                return 'Partial Company'
            return None

        param_svc = Mock()
        param_svc.get_param = Mock(side_effect=mock_get_param)
        db = Mock()
        db.execute_query = Mock(return_value=[])
        svc = _make_pdf_service(param_svc=param_svc, db=db)

        html = svc._render_html('TestTenant', _sample_invoice())

        assert 'Partial Company' in html
        # No placeholder patterns
        assert '{{' not in html


# ═══════════════════════════════════════════════════════════
# 5. zzp_invoice registered as template type (Req 20.7)
# ═══════════════════════════════════════════════════════════


class TestZzpInvoiceTemplateType:
    """Verify zzp_invoice is registered in TemplateService."""

    def test_zzp_invoice_in_local_defaults(self):
        """Req 20.7: zzp_invoice must be in TemplateService._LOCAL_DEFAULTS."""
        assert 'zzp_invoice' in TemplateService._LOCAL_DEFAULTS

    def test_zzp_invoice_has_template_path(self):
        """Req 20.7: zzp_invoice entry must specify a template file."""
        entry = TemplateService._LOCAL_DEFAULTS['zzp_invoice']
        assert 'template' in entry
        assert len(entry['template']) > 0

    def test_zzp_invoice_has_field_mappings(self):
        """Req 20.7: zzp_invoice entry must specify field mappings."""
        entry = TemplateService._LOCAL_DEFAULTS['zzp_invoice']
        assert 'field_mappings' in entry
        assert len(entry['field_mappings']) > 0

    def test_pdf_generator_loads_zzp_invoice_template(self):
        """Req 20.7: PDFGeneratorService._load_template calls TemplateService
        with 'zzp_invoice' type."""
        template_svc = Mock()
        template_svc.get_template_metadata = Mock(return_value=None)
        svc = _make_pdf_service(template_svc=template_svc)

        svc._load_template('TestTenant')

        template_svc.get_template_metadata.assert_called_once_with(
            'TestTenant', 'zzp_invoice'
        )
