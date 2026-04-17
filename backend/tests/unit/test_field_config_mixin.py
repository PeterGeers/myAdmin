"""Unit tests for FieldConfigMixin."""

import pytest
from unittest.mock import Mock
from services.field_config_mixin import FieldConfigMixin


class DummyService(FieldConfigMixin):
    """Concrete subclass for testing."""
    FIELD_CONFIG_KEY = 'contact_field_config'
    ALWAYS_REQUIRED = ['client_id', 'company_name']

    def __init__(self, parameter_service=None):
        self.parameter_service = parameter_service


# ── get_field_config ────────────────────────────────────────


def test_get_field_config_no_override_returns_defaults():
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=None)))
    config = svc.get_field_config('TestTenant')
    assert config['client_id'] == 'required'
    assert config['company_name'] == 'required'
    assert 'contact_person' in config


def test_get_field_config_tenant_override_applies_values():
    override = {
        'client_id': 'required',
        'company_name': 'required',
        'vat_number': 'hidden',
        'phone': 'optional',
    }
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=override)))
    config = svc.get_field_config('TestTenant')
    assert config['vat_number'] == 'hidden'
    assert config['phone'] == 'optional'


def test_get_field_config_always_required_cannot_be_overridden_to_hidden():
    override = {
        'client_id': 'hidden',
        'company_name': 'optional',
        'phone': 'optional',
    }
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=override)))
    config = svc.get_field_config('TestTenant')
    assert config['client_id'] == 'required'
    assert config['company_name'] == 'required'


def test_get_field_config_no_parameter_service_returns_defaults():
    svc = DummyService(parameter_service=None)
    config = svc.get_field_config('TestTenant')
    assert config['client_id'] == 'required'


# ── validate_fields ─────────────────────────────────────────


def test_validate_fields_all_required_present_passes():
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=None)))
    svc.validate_fields('TestTenant', {
        'client_id': 'ACME',
        'company_name': 'Acme Corp',
        'contact_type': 'client',
    })


def test_validate_fields_missing_required_raises_valueerror():
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=None)))
    with pytest.raises(ValueError, match='client_id'):
        svc.validate_fields('TestTenant', {
            'company_name': 'Acme Corp',
            'contact_type': 'client',
        })


def test_validate_fields_empty_required_raises_valueerror():
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=None)))
    with pytest.raises(ValueError, match='client_id'):
        svc.validate_fields('TestTenant', {
            'client_id': '',
            'company_name': 'Acme Corp',
            'contact_type': 'client',
        })


def test_validate_fields_multiple_missing_lists_all():
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=None)))
    with pytest.raises(ValueError, match='client_id') as exc_info:
        svc.validate_fields('TestTenant', {'contact_type': 'client'})
    assert 'company_name' in str(exc_info.value)


# ── strip_hidden_fields ─────────────────────────────────────


def test_strip_hidden_fields_removes_hidden():
    override = {
        'client_id': 'required',
        'company_name': 'required',
        'vat_number': 'hidden',
        'kvk_number': 'hidden',
        'phone': 'optional',
    }
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=override)))
    data = {
        'client_id': 'ACME',
        'company_name': 'Acme Corp',
        'vat_number': 'NL123',
        'kvk_number': '12345678',
        'phone': '+31612345678',
    }
    result = svc.strip_hidden_fields('TestTenant', data)
    assert 'client_id' in result
    assert 'phone' in result
    assert 'vat_number' not in result
    assert 'kvk_number' not in result


def test_strip_hidden_fields_nothing_hidden_keeps_all():
    svc = DummyService(parameter_service=Mock(get_param=Mock(return_value=None)))
    data = {'client_id': 'ACME', 'company_name': 'Acme Corp', 'phone': '+31612345678'}
    result = svc.strip_hidden_fields('TestTenant', data)
    assert result == data
