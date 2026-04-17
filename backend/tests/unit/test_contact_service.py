"""Unit tests for ContactService."""

import pytest
from unittest.mock import Mock
from services.contact_service import ContactService


def _make_service(db=None, param_svc=None):
    db = db or Mock()
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return ContactService(db=db, parameter_service=param_svc)


def _contact_row(**overrides):
    base = {
        'id': 1, 'administration': 'T1', 'client_id': 'ACME',
        'contact_type': 'client', 'company_name': 'Acme Corp',
        'contact_person': None, 'street_address': None,
        'postal_code': None, 'city': None, 'country': 'NL',
        'vat_number': None, 'kvk_number': None, 'phone': None,
        'iban': None, 'is_active': True, 'created_by': 'test',
        'created_at': None, 'updated_at': None,
    }
    base.update(overrides)
    return base


# ── create_contact ──────────────────────────────────────────


def test_create_contact_valid_data_returns_contact():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [],       # _check_client_id_unique
        5,        # INSERT
        [_contact_row(id=5)],  # get_contact
        [],       # _get_emails
    ])
    svc = _make_service(db=db)
    result = svc.create_contact('T1', {
        'client_id': 'ACME', 'company_name': 'Acme Corp',
        'contact_type': 'client',
    }, created_by='test')
    assert result['client_id'] == 'ACME'


def test_create_contact_with_emails_saves_emails():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [],   # uniqueness
        5,    # INSERT contact
        None, # INSERT email 1
        None, # INSERT email 2
        [_contact_row(id=5)],  # get_contact
        [{'id': 1, 'email': 'a@b.nl', 'email_type': 'general', 'is_primary': True},
         {'id': 2, 'email': 'inv@b.nl', 'email_type': 'invoice', 'is_primary': False}],
    ])
    svc = _make_service(db=db)
    result = svc.create_contact('T1', {
        'client_id': 'ACME', 'company_name': 'Acme Corp',
        'contact_type': 'client',
        'emails': [
            {'email': 'a@b.nl', 'email_type': 'general', 'is_primary': True},
            {'email': 'inv@b.nl', 'email_type': 'invoice'},
        ],
    }, created_by='test')
    assert len(result['emails']) == 2


def test_create_contact_duplicate_client_id_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [{'id': 99}],  # uniqueness check finds existing
    ])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="already exists"):
        svc.create_contact('T1', {
            'client_id': 'ACME', 'company_name': 'Acme Corp',
            'contact_type': 'client',
        }, created_by='test')


def test_create_contact_invalid_client_id_raises_valueerror():
    svc = _make_service()
    with pytest.raises(ValueError, match="alphanumeric"):
        svc.create_contact('T1', {
            'client_id': 'AC ME!', 'company_name': 'Acme Corp',
            'contact_type': 'client',
        }, created_by='test')


def test_create_contact_empty_client_id_raises_valueerror():
    svc = _make_service()
    with pytest.raises(ValueError, match="alphanumeric"):
        svc.create_contact('T1', {
            'client_id': '', 'company_name': 'Acme Corp',
            'contact_type': 'client',
        }, created_by='test')


def test_create_contact_invalid_contact_type_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="Invalid contact_type"):
        svc.create_contact('T1', {
            'client_id': 'ACME', 'company_name': 'Acme Corp',
            'contact_type': 'invalid_type',
        }, created_by='test')


# ── list_contacts ───────────────────────────────────────────


def test_list_contacts_valid_tenant_returns_contacts():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_contact_row()],  # list query
        [],                # emails for contact 1
    ])
    svc = _make_service(db=db)
    result = svc.list_contacts('T1')
    assert len(result) == 1
    assert result[0]['client_id'] == 'ACME'


def test_list_contacts_with_type_filter_includes_filter_in_query():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_contact_row(contact_type='supplier')],
        [],
    ])
    svc = _make_service(db=db)
    svc.list_contacts('T1', contact_type='supplier')
    query = db.execute_query.call_args_list[0][0][0]
    assert 'contact_type' in query


# ── get_contact ─────────────────────────────────────────────


def test_get_contact_not_found_returns_none():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    assert svc.get_contact('T1', 999) is None


def test_get_contact_found_returns_contact_with_emails():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_contact_row()],
        [{'id': 1, 'email': 'a@b.nl', 'email_type': 'general', 'is_primary': True}],
    ])
    svc = _make_service(db=db)
    result = svc.get_contact('T1', 1)
    assert result['emails'][0]['email'] == 'a@b.nl'


# ── soft_delete_contact ─────────────────────────────────────


def test_soft_delete_contact_unused_returns_true():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_contact_row()],  # get_contact
        [],                # emails
        [],                # _check_contact_in_use
        None,              # UPDATE
    ])
    svc = _make_service(db=db)
    assert svc.soft_delete_contact('T1', 1) is True


def test_soft_delete_contact_in_use_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_contact_row()],  # get_contact
        [],                # emails
        [{'1': 1}],        # _check_contact_in_use
    ])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="referenced by existing invoices"):
        svc.soft_delete_contact('T1', 1)


def test_soft_delete_contact_not_found_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="not found"):
        svc.soft_delete_contact('T1', 999)


# ── get_invoice_email ───────────────────────────────────────


def test_get_invoice_email_invoice_type_returns_invoice_email():
    db = Mock()
    db.execute_query = Mock(return_value=[
        {'email': 'general@a.nl', 'email_type': 'general', 'is_primary': True},
        {'email': 'invoice@a.nl', 'email_type': 'invoice', 'is_primary': False},
    ])
    svc = _make_service(db=db)
    assert svc.get_invoice_email('T1', 1) == 'invoice@a.nl'


def test_get_invoice_email_no_invoice_type_falls_back_to_primary():
    db = Mock()
    db.execute_query = Mock(return_value=[
        {'email': 'other@a.nl', 'email_type': 'other', 'is_primary': False},
        {'email': 'primary@a.nl', 'email_type': 'general', 'is_primary': True},
    ])
    svc = _make_service(db=db)
    assert svc.get_invoice_email('T1', 1) == 'primary@a.nl'


def test_get_invoice_email_no_primary_falls_back_to_first():
    db = Mock()
    db.execute_query = Mock(return_value=[
        {'email': 'only@a.nl', 'email_type': 'other', 'is_primary': False},
    ])
    svc = _make_service(db=db)
    assert svc.get_invoice_email('T1', 1) == 'only@a.nl'


def test_get_invoice_email_no_emails_returns_none():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    assert svc.get_invoice_email('T1', 1) is None


# ── get_contact_types ───────────────────────────────────────


def test_get_contact_types_from_parameter_service_returns_custom():
    param_svc = Mock(get_param=Mock(return_value=['client', 'vendor']))
    svc = _make_service(param_svc=param_svc)
    assert svc.get_contact_types('T1') == ['client', 'vendor']


def test_get_contact_types_no_override_returns_registry_defaults():
    param_svc = Mock(get_param=Mock(return_value=None))
    svc = _make_service(param_svc=param_svc)
    types = svc.get_contact_types('T1')
    assert 'client' in types
    assert 'supplier' in types
