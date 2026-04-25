"""
Unit tests for AllowedColumnsRegistry, schema introspection,
and parameter-driven pivot configuration.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
Reference: .kiro/specs/dynamic-pivot-views/design.md
"""

import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.pivot_service import (
    AllowedColumnsRegistry,
    SYSTEM_ALLOWED_COLUMNS,
    COLUMN_TYPE_MAP,
    DATA_SOURCE_LABELS,
    DATA_SOURCE_MODULES,
    TENANT_COLUMN,
    build_registry_from_db,
)


# ---------------------------------------------------------------------------
# Mock DESCRIBE results
# ---------------------------------------------------------------------------

_MOCK_DESCRIBE = {
    'vw_mutaties': [
        {'Field': 'Aangifte',              'Type': 'varchar(100)'},
        {'Field': 'TransactionNumber',     'Type': 'varchar(50)'},
        {'Field': 'TransactionDate',       'Type': 'date'},
        {'Field': 'TransactionDescription','Type': 'varchar(500)'},
        {'Field': 'Amount',                'Type': 'decimal(10,2)'},
        {'Field': 'Reknum',               'Type': 'varchar(20)'},
        {'Field': 'AccountName',          'Type': 'varchar(100)'},
        {'Field': 'Parent',               'Type': 'varchar(100)'},
        {'Field': 'VW',                   'Type': 'varchar(1)'},
        {'Field': 'jaar',                 'Type': 'int'},
        {'Field': 'kwartaal',             'Type': 'int'},
        {'Field': 'maand',                'Type': 'int'},
        {'Field': 'week',                 'Type': 'int'},
        {'Field': 'ReferenceNumber',      'Type': 'varchar(50)'},
        {'Field': 'administration',       'Type': 'varchar(100)'},
        {'Field': 'Ref3',                 'Type': 'varchar(255)'},
        {'Field': 'Ref4',                 'Type': 'varchar(255)'},
    ],
    'vw_bnb_total': [
        {'Field': 'channel',               'Type': 'varchar(50)'},
        {'Field': 'listing',               'Type': 'varchar(200)'},
        {'Field': 'checkinDate',           'Type': 'date'},
        {'Field': 'checkoutDate',          'Type': 'date'},
        {'Field': 'nights',               'Type': 'int'},
        {'Field': 'guests',               'Type': 'int'},
        {'Field': 'amountGross',          'Type': 'decimal(10,2)'},
        {'Field': 'amountNett',           'Type': 'decimal(10,2)'},
        {'Field': 'amountChannelFee',     'Type': 'decimal(10,2)'},
        {'Field': 'amountTouristTax',     'Type': 'decimal(10,2)'},
        {'Field': 'amountVat',            'Type': 'decimal(10,2)'},
        {'Field': 'pricePerNight',        'Type': 'decimal(10,2)'},
        {'Field': 'daysBeforeReservation','Type': 'int'},
        {'Field': 'year',                 'Type': 'int'},
        {'Field': 'q',                    'Type': 'int'},
        {'Field': 'm',                    'Type': 'int'},
        {'Field': 'country',              'Type': 'varchar(5)'},
        {'Field': 'countryName',          'Type': 'varchar(100)'},
        {'Field': 'countryRegion',        'Type': 'varchar(100)'},
        {'Field': 'source_type',          'Type': 'varchar(20)'},
        {'Field': 'status',               'Type': 'varchar(20)'},
        {'Field': 'administration',       'Type': 'varchar(100)'},
    ],
}

# Parameter values matching CODE_DEFAULTS in parameter_service.py
_PARAM_VALUES = {
    ('ui.pivot', 'registered_sources'): ['vw_mutaties', 'vw_bnb_total'],
    ('ui.pivot', 'exclude_columns.vw_mutaties'): [
        'TransactionNumber', 'TransactionDescription', 'Ref3', 'Ref4',
    ],
    ('ui.pivot', 'exclude_columns.vw_bnb_total'): ['checkoutDate'],
    ('ui.pivot', 'force_groupable.vw_mutaties'): [
        'jaar', 'kwartaal', 'maand', 'week',
    ],
    ('ui.pivot', 'force_groupable.vw_bnb_total'): [
        'year', 'q', 'm', 'nights', 'guests', 'daysBeforeReservation',
    ],
    ('ui.pivot', 'datasource_label.vw_mutaties'): 'Financial Transactions',
    ('ui.pivot', 'datasource_label.vw_bnb_total'): 'STR Revenue',
    ('ui.pivot', 'datasource_module.vw_mutaties'): 'FIN',
    ('ui.pivot', 'datasource_module.vw_bnb_total'): 'STR',
}


def _mock_describe_db():
    db = MagicMock()
    def _eq(query, params=None, fetch=True, **kw):
        for name, rows in _MOCK_DESCRIBE.items():
            if name in query:
                return rows
        return []
    db.execute_query = MagicMock(side_effect=_eq)
    return db


def _mock_parameter_service():
    ps = MagicMock()
    def _get_param(namespace, key, **kw):
        return _PARAM_VALUES.get((namespace, key))
    ps.get_param = MagicMock(side_effect=_get_param)
    return ps


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _populate_registry():
    """Populate registry from mock DESCRIBE + parameters before each test."""
    build_registry_from_db(_mock_describe_db(), _mock_parameter_service())
    yield
    SYSTEM_ALLOWED_COLUMNS.clear()
    COLUMN_TYPE_MAP.clear()
    DATA_SOURCE_LABELS.clear()
    DATA_SOURCE_MODULES.clear()


def _make_registry():
    param_svc = MagicMock()
    return AllowedColumnsRegistry(param_svc), param_svc


# ---------------------------------------------------------------------------
# get_available_columns
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_get_available_columns_no_tenant_restriction():
    registry, ps = _make_registry()
    ps.get_param.return_value = None

    result = registry.get_available_columns('vw_mutaties', 'admin1')

    assert result['groupable'] == SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['groupable']
    assert result['aggregatable'] == SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['aggregatable']


@pytest.mark.unit
def test_get_available_columns_with_tenant_restriction():
    registry, ps = _make_registry()
    ps.get_param.return_value = {
        'groupable': ['Aangifte', 'jaar'],
        'aggregatable': ['Amount'],
    }

    result = registry.get_available_columns('vw_mutaties', 'admin1')

    assert result['groupable'] == ['Aangifte', 'jaar']
    assert result['aggregatable'] == ['Amount']


@pytest.mark.unit
def test_get_available_columns_unknown_source_raises():
    registry, _ = _make_registry()

    with pytest.raises(ValueError, match="Unknown data source"):
        registry.get_available_columns('mysql.user', 'admin1')


# ---------------------------------------------------------------------------
# Schema introspection + parameter-driven config
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_excluded_columns_not_in_registry():
    excluded = _PARAM_VALUES[('ui.pivot', 'exclude_columns.vw_mutaties')]
    all_cols = (
        SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['groupable']
        + SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['aggregatable']
    )
    for col in excluded:
        assert col not in all_cols


@pytest.mark.unit
def test_force_groupable_columns_are_groupable():
    forced = _PARAM_VALUES[('ui.pivot', 'force_groupable.vw_mutaties')]
    groupable = SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['groupable']
    for col in forced:
        assert col in groupable


@pytest.mark.unit
def test_numeric_columns_are_aggregatable():
    assert 'Amount' in SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['aggregatable']


@pytest.mark.unit
def test_labels_from_parameters():
    assert DATA_SOURCE_LABELS['vw_mutaties'] == 'Financial Transactions'
    assert DATA_SOURCE_LABELS['vw_bnb_total'] == 'STR Revenue'


@pytest.mark.unit
def test_build_registry_raises_on_db_failure():
    db = MagicMock()
    db.execute_query.side_effect = Exception("Connection refused")

    with pytest.raises(RuntimeError, match="FATAL"):
        build_registry_from_db(db, _mock_parameter_service())


@pytest.mark.unit
def test_build_registry_without_parameter_service():
    """Without parameter_service, all columns included, no exclusions."""
    SYSTEM_ALLOWED_COLUMNS.clear()
    COLUMN_TYPE_MAP.clear()
    DATA_SOURCE_LABELS.clear()
    DATA_SOURCE_MODULES.clear()

    build_registry_from_db(_mock_describe_db(), parameter_service=None)

    all_cols = (
        SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['groupable']
        + SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['aggregatable']
    )
    assert 'TransactionNumber' in all_cols  # not excluded
    assert 'jaar' in SYSTEM_ALLOWED_COLUMNS['vw_mutaties']['aggregatable']  # not forced groupable


@pytest.mark.unit
def test_unregistered_source_rejected():
    """A data source not in registered_sources cannot be queried."""
    assert 'mysql.user' not in SYSTEM_ALLOWED_COLUMNS


# ---------------------------------------------------------------------------
# get_registered_sources
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_get_registered_sources():
    registry, _ = _make_registry()
    sources = registry.get_registered_sources()

    names = [s['name'] for s in sources]
    assert 'vw_mutaties' in names
    assert 'vw_bnb_total' in names

    for src in sources:
        assert 'name' in src
        assert 'label' in src
        assert 'module' in src

    # Verify module tags are populated from datasource_module parameters
    by_name = {s['name']: s for s in sources}
    assert by_name['vw_mutaties']['module'] == 'FIN'
    assert by_name['vw_bnb_total']['module'] == 'STR'


# ---------------------------------------------------------------------------
# validate_columns
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_validate_columns_valid():
    registry, ps = _make_registry()
    ps.get_param.return_value = None

    registry.validate_columns(
        data_source='vw_mutaties', tenant='admin1',
        group_columns=['Aangifte', 'jaar'],
        aggregate_columns=['Amount'],
    )


@pytest.mark.unit
def test_validate_columns_invalid_group_raises():
    registry, ps = _make_registry()
    ps.get_param.return_value = None

    with pytest.raises(ValueError, match="not allowed"):
        registry.validate_columns(
            data_source='vw_mutaties', tenant='admin1',
            group_columns=['FAKE_COLUMN'],
            aggregate_columns=['Amount'],
        )


@pytest.mark.unit
def test_validate_columns_star_aggregate_allowed():
    registry, ps = _make_registry()
    ps.get_param.return_value = None

    registry.validate_columns(
        data_source='vw_mutaties', tenant='admin1',
        group_columns=['Aangifte'],
        aggregate_columns=['*'],
    )


# ---------------------------------------------------------------------------
# _quote_column
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_quote_column_mysql():
    assert AllowedColumnsRegistry._quote_column('Aangifte') == '`Aangifte`'


@pytest.mark.unit
def test_quote_column_postgres():
    assert AllowedColumnsRegistry._quote_column('Aangifte', quote_char='"') == '"Aangifte"'


@pytest.mark.unit
def test_quote_column_strips_injection():
    result = AllowedColumnsRegistry._quote_column('col`; DROP TABLE--', quote_char='`')
    assert '`' not in result[1:-1]
