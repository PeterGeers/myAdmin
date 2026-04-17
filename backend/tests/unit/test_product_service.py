"""Unit tests for ProductService."""

import pytest
from unittest.mock import Mock
from services.product_service import ProductService


def _make_service(db=None, tax_svc=None, param_svc=None):
    db = db or Mock()
    tax_svc = tax_svc or Mock(get_tax_rate=Mock(return_value={'rate': 21.0}))
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return ProductService(db=db, tax_rate_service=tax_svc, parameter_service=param_svc)


def _product_row(**overrides):
    base = {
        'id': 1, 'administration': 'T1', 'product_code': 'DEV-HR',
        'external_reference': None, 'name': 'Software Development',
        'description': None, 'product_type': 'service',
        'unit_price': 95.00, 'vat_code': 'high',
        'unit_of_measure': 'uur', 'is_active': True,
        'created_by': 'test', 'created_at': None, 'updated_at': None,
    }
    base.update(overrides)
    return base


def _valid_data(**overrides):
    base = {
        'product_code': 'DEV-HR', 'name': 'Software Development',
        'product_type': 'service', 'unit_price': 95.00, 'vat_code': 'high',
    }
    base.update(overrides)
    return base


# ── create_product ──────────────────────────────────────────


def test_create_product_valid_data_returns_product():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [],                    # uniqueness check
        5,                     # INSERT
        [_product_row(id=5)],  # get_product
    ])
    svc = _make_service(db=db)
    result = svc.create_product('T1', _valid_data(), created_by='test')
    assert result['product_code'] == 'DEV-HR'


def test_create_product_missing_required_raises_valueerror():
    svc = _make_service()
    with pytest.raises(ValueError, match="Required fields missing"):
        svc.create_product('T1', {'product_code': 'X'}, created_by='test')


def test_create_product_duplicate_code_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[{'id': 99}])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="already exists"):
        svc.create_product('T1', _valid_data(), created_by='test')


# ── list_products ───────────────────────────────────────────


def test_list_products_valid_tenant_returns_products():
    db = Mock()
    db.execute_query = Mock(return_value=[_product_row()])
    svc = _make_service(db=db)
    result = svc.list_products('T1')
    assert len(result) == 1
    assert result[0]['name'] == 'Software Development'


def test_list_products_default_excludes_inactive():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    svc.list_products('T1')
    query = db.execute_query.call_args[0][0]
    assert 'is_active = TRUE' in query


# ── get_product ─────────────────────────────────────────────


def test_get_product_not_found_returns_none():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    assert svc.get_product('T1', 999) is None


# ── _validate_vat_code ──────────────────────────────────────


def test_validate_vat_code_high_passes():
    db = Mock()
    db.execute_query = Mock(side_effect=[[], 5, [_product_row(id=5)]])
    svc = _make_service(db=db)
    svc.create_product('T1', _valid_data(vat_code='high'), created_by='test')


def test_validate_vat_code_invalid_raises_valueerror():
    svc = _make_service()
    with pytest.raises(ValueError, match="Invalid vat_code"):
        svc.create_product('T1', _valid_data(vat_code='reduced'), created_by='test')


def test_validate_vat_code_no_rate_found_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    tax_svc = Mock(get_tax_rate=Mock(return_value=None))
    svc = _make_service(db=db, tax_svc=tax_svc)
    with pytest.raises(ValueError, match="No BTW rate found"):
        svc.create_product('T1', _valid_data(vat_code='high'), created_by='test')


# ── _validate_product_type ──────────────────────────────────


def test_validate_product_type_valid_passes():
    db = Mock()
    db.execute_query = Mock(side_effect=[[], 5, [_product_row(id=5)]])
    svc = _make_service(db=db)
    svc.create_product('T1', _valid_data(product_type='service'), created_by='test')


def test_validate_product_type_invalid_raises_valueerror():
    svc = _make_service()
    with pytest.raises(ValueError, match="Invalid product_type"):
        svc.create_product('T1', _valid_data(product_type='unknown'), created_by='test')


def test_get_product_types_tenant_override_returns_custom():
    param_svc = Mock(get_param=Mock(return_value=['consulting', 'hosting']))
    svc = _make_service(param_svc=param_svc)
    assert svc.get_product_types('T1') == ['consulting', 'hosting']


def test_get_product_types_no_override_returns_registry_defaults():
    param_svc = Mock(get_param=Mock(return_value=None))
    svc = _make_service(param_svc=param_svc)
    types = svc.get_product_types('T1')
    assert 'service' in types
    assert 'product' in types


# ── soft_delete_product ─────────────────────────────────────


def test_soft_delete_product_unused_returns_true():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_product_row()],  # get_product
        [],                # _check_product_in_use
        None,              # UPDATE
    ])
    svc = _make_service(db=db)
    assert svc.soft_delete_product('T1', 1) is True


def test_soft_delete_product_in_use_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_product_row()],  # get_product
        [{'1': 1}],       # _check_product_in_use
    ])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="referenced by existing invoice lines"):
        svc.soft_delete_product('T1', 1)


def test_soft_delete_product_not_found_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="not found"):
        svc.soft_delete_product('T1', 999)
