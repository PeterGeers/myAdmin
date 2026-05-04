"""
Property-based tests for PivotService query builder.

Feature: dynamic-pivot-views
Properties 5, 6, 13 from the design document.

Property 5: Parameterized SQL structure
    For any valid config, generated SQL uses only %s placeholders,
    all filter values in params list, WHERE precedes GROUP BY.

Property 6: Tenant isolation
    For any config and user_tenants list, WHERE clause includes
    administration IN (...) with all tenant values in params.

Property 13: Column pivot conditional aggregation
    For any config with column_pivot, SQL contains CASE WHEN
    expressions for each pivot value and aggregate measure.

Validates: Requirements 2.4, 3.1, 3.2, 3.3, 9.7
Reference: .kiro/specs/dynamic-pivot-views/design.md §Correctness Properties
"""

import sys
import os
import re
import pytest
from unittest.mock import MagicMock
from hypothesis import given, strategies as st, settings, assume

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.pivot_service import (
    PivotService,
    SYSTEM_ALLOWED_COLUMNS,
    COLUMN_TYPE_MAP,
    DATA_SOURCE_LABELS,
    DATA_SOURCE_MODULES,
    TENANT_COLUMN,
    build_registry_from_db,
)


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_MOCK_DESCRIBE = {
    'vw_mutaties': [
        {'Field': 'Aangifte', 'Type': 'varchar(100)'},
        {'Field': 'TransactionDate', 'Type': 'date'},
        {'Field': 'Amount', 'Type': 'decimal(10,2)'},
        {'Field': 'Reknum', 'Type': 'varchar(20)'},
        {'Field': 'AccountName', 'Type': 'varchar(100)'},
        {'Field': 'Parent', 'Type': 'varchar(100)'},
        {'Field': 'VW', 'Type': 'varchar(1)'},
        {'Field': 'jaar', 'Type': 'int'},
        {'Field': 'kwartaal', 'Type': 'int'},
        {'Field': 'maand', 'Type': 'int'},
        {'Field': 'week', 'Type': 'int'},
        {'Field': 'ReferenceNumber', 'Type': 'varchar(50)'},
        {'Field': 'administration', 'Type': 'varchar(100)'},
    ],
}

_PARAM_VALUES = {
    ('ui.pivot', 'registered_sources'): ['vw_mutaties'],
    ('ui.pivot', 'exclude_columns.vw_mutaties'): [],
    ('ui.pivot', 'force_groupable.vw_mutaties'): ['jaar', 'kwartaal', 'maand', 'week'],
}


def _mock_db():
    db = MagicMock()
    def _eq(query, params=None, fetch=True, **kw):
        for name, rows in _MOCK_DESCRIBE.items():
            if name in query:
                return rows
        return []
    db.execute_query = MagicMock(side_effect=_eq)
    return db


def _mock_ps():
    ps = MagicMock()
    def _gp(namespace, key, **kw):
        return _PARAM_VALUES.get((namespace, key))
    ps.get_param = MagicMock(side_effect=_gp)
    return ps


@pytest.fixture(autouse=True)
def _populate_registry():
    build_registry_from_db(_mock_db(), _mock_ps())
    yield
    SYSTEM_ALLOWED_COLUMNS.clear()
    COLUMN_TYPE_MAP.clear()
    DATA_SOURCE_LABELS.clear()
    DATA_SOURCE_MODULES.clear()


def _make_service():
    return PivotService(_mock_db(), _mock_ps())


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Note: 'administration' is the TENANT_COLUMN and is excluded from the
# registry by derive_columns_from_schema — it is never user-selectable.
_GROUPABLE = ['Aangifte', 'TransactionDate', 'Reknum', 'AccountName',
              'Parent', 'VW', 'jaar', 'kwartaal', 'maand', 'week',
              'ReferenceNumber']
_AGGREGATABLE = ['Amount']

agg_function_st = st.sampled_from(['SUM', 'COUNT', 'AVG', 'MIN', 'MAX'])
groupable_col_st = st.sampled_from(_GROUPABLE)

tenant_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_'),
    min_size=1, max_size=30,
)


@st.composite
def valid_config_st(draw):
    """Generate a valid pivot config for vw_mutaties."""
    gc = draw(st.lists(groupable_col_st, min_size=1, max_size=5, unique=True))
    am = draw(st.lists(
        st.fixed_dictionaries({
            'function': agg_function_st,
            'column': st.sampled_from(_AGGREGATABLE + ['*']),
        }),
        min_size=1, max_size=5,
    ))

    # Optional filters on known columns
    filters = {}
    if draw(st.booleans()):
        filters['jaar'] = draw(st.lists(
            st.integers(min_value=2020, max_value=2030), min_size=1, max_size=3,
        ))
    if draw(st.booleans()):
        filters['VW'] = draw(st.sampled_from(['V', 'W']))

    return {
        'data_source': 'vw_mutaties',
        'group_columns': gc,
        'aggregate_measures': am,
        'filters': filters,
        'column_pivot': None,
        'column_nest_levels': [],
        'include_rollup': draw(st.booleans()),
    }


@st.composite
def valid_pivot_config_st(draw):
    """Generate a valid config with column_pivot set."""
    gc = draw(st.lists(groupable_col_st, min_size=1, max_size=3, unique=True))
    am = draw(st.lists(
        st.fixed_dictionaries({
            'function': agg_function_st,
            'column': st.sampled_from(_AGGREGATABLE + ['*']),
        }),
        min_size=1, max_size=3,
    ))

    # Pick a pivot column not in group columns
    remaining = [c for c in _GROUPABLE if c not in gc]
    assume(len(remaining) > 0)
    pivot_col = draw(st.sampled_from(remaining))

    # Generate pivot values (distinct values the pivot column would have)
    pivot_values = draw(st.lists(
        st.text(min_size=1, max_size=10,
                alphabet=st.characters(whitelist_categories=('L', 'N'))),
        min_size=1, max_size=4, unique=True,
    ))

    return {
        'data_source': 'vw_mutaties',
        'group_columns': gc,
        'aggregate_measures': am,
        'filters': {},
        'column_pivot': pivot_col,
        'pivot_values': pivot_values,
        'column_nest_levels': [],
        'include_rollup': False,
    }


# ---------------------------------------------------------------------------
# Property 5: Parameterized SQL structure
# Feature: dynamic-pivot-views, Property 5: Parameterized SQL structure
# Validates: Requirements 2.4, 3.1, 3.2
# ---------------------------------------------------------------------------

class TestParameterizedSqlStructure:
    """For any valid config, SQL uses only %s placeholders, WHERE before GROUP BY."""

    @settings(max_examples=100)
    @given(
        config=valid_config_st(),
        tenant=tenant_st,
    )
    def test_only_placeholder_params(self, config, tenant):
        """Generated SQL should only contain %s placeholders, no raw values."""
        svc = _make_service()
        query, params = svc.build_pivot_query(config, tenant)

        # All user values should be in params, not in the query string
        assert '%s' in query
        # No string interpolation patterns (f-string or .format leftovers)
        assert '{' not in query
        # Count placeholders matches params length
        placeholder_count = query.count('%s')
        assert placeholder_count == len(params)

    @settings(max_examples=100)
    @given(
        config=valid_config_st(),
        tenant=tenant_st,
    )
    def test_where_precedes_group_by(self, config, tenant):
        """WHERE clause should appear before GROUP BY in the query."""
        svc = _make_service()
        query, _ = svc.build_pivot_query(config, tenant)

        where_pos = query.upper().find('WHERE')
        group_pos = query.upper().find('GROUP BY')
        assert where_pos >= 0, "Query must contain WHERE"
        assert group_pos >= 0, "Query must contain GROUP BY"
        assert where_pos < group_pos, "WHERE must precede GROUP BY"

    @settings(max_examples=100)
    @given(
        config=valid_config_st(),
        tenant=tenant_st,
    )
    def test_filter_values_in_params(self, config, tenant):
        """All filter values should appear in the params list."""
        svc = _make_service()
        _, params = svc.build_pivot_query(config, tenant)

        # Tenant value should be in params (single-tenant = %s)
        assert tenant in params

        # Filter values should be in params
        for key, val in config.get('filters', {}).items():
            if val is None or val == '' or val == 'all':
                continue
            if isinstance(val, list):
                for v in val:
                    assert v in params
            else:
                assert val in params


# ---------------------------------------------------------------------------
# Property 6: Tenant isolation
# Feature: dynamic-pivot-views, Property 6: Tenant isolation
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """For any config and tenant, WHERE includes administration = %s."""

    @settings(max_examples=100)
    @given(
        config=valid_config_st(),
        tenant=tenant_st,
    )
    def test_tenant_filter_in_where(self, config, tenant):
        """WHERE clause must contain administration = %s with the tenant value."""
        svc = _make_service()
        query, params = svc.build_pivot_query(config, tenant)

        # Check the WHERE clause contains the tenant column
        assert f'`{TENANT_COLUMN}`' in query

        # Tenant value must be in params
        assert tenant in params

        # The WHERE clause should use = %s for single-tenant isolation
        pattern = re.compile(
            r'`administration`\s*=\s*%s',
            re.IGNORECASE,
        )
        match = pattern.search(query)
        assert match, "Query must contain `administration` = %s"

    @settings(max_examples=50)
    @given(config=valid_config_st())
    def test_empty_tenant_still_filters(self, config):
        """With empty string tenant, WHERE still contains administration = %s."""
        # Ensure registry is populated (guards against stale Hypothesis replays
        # where the autouse fixture teardown may have cleared globals)
        if not SYSTEM_ALLOWED_COLUMNS:
            build_registry_from_db(_mock_db(), _mock_ps())
        svc = _make_service()
        query, params = svc.build_pivot_query(config, '')
        # Even with empty tenant, the filter is present (prevents data leakage)
        assert f'`{TENANT_COLUMN}` = %s' in query
        assert '' in params


# ---------------------------------------------------------------------------
# Property 13: Column pivot conditional aggregation
# Feature: dynamic-pivot-views, Property 13: Column pivot conditional aggregation
# Validates: Requirements 9.7
# ---------------------------------------------------------------------------

class TestColumnPivotConditionalAggregation:
    """For any config with column_pivot, SQL contains CASE WHEN expressions."""

    @settings(max_examples=100)
    @given(
        config=valid_pivot_config_st(),
        tenant=tenant_st,
    )
    def test_case_when_for_each_pivot_value(self, config, tenant):
        """SQL should contain CASE WHEN for each pivot value."""
        svc = _make_service()
        query, params = svc.build_pivot_query(config, tenant)

        pivot_values = config['pivot_values']
        agg_measures = config['aggregate_measures']

        # Each pivot value should produce CASE WHEN expressions
        case_when_count = query.upper().count('CASE WHEN')
        expected_count = len(pivot_values) * len(agg_measures)
        assert case_when_count == expected_count, (
            f"Expected {expected_count} CASE WHEN expressions "
            f"({len(pivot_values)} pivots × {len(agg_measures)} measures), "
            f"got {case_when_count}"
        )

    @settings(max_examples=100)
    @given(
        config=valid_pivot_config_st(),
        tenant=tenant_st,
    )
    def test_pivot_values_in_params(self, config, tenant):
        """All pivot values should appear in the params list."""
        svc = _make_service()
        _, params = svc.build_pivot_query(config, tenant)

        for pv in config['pivot_values']:
            assert pv in params

    @settings(max_examples=100)
    @given(
        config=valid_pivot_config_st(),
        tenant=tenant_st,
    )
    def test_grand_total_columns_present(self, config, tenant):
        """Grand total columns should be appended for each aggregate measure."""
        svc = _make_service()
        query, _ = svc.build_pivot_query(config, tenant)

        for m in config['aggregate_measures']:
            func = m['function'].upper()
            col = m['column']
            # _agg_alias: col=='*' → func, else func_col
            # Grand total alias is always TOTAL_func_col
            total_alias = f'TOTAL_{func}_{col}'
            assert f'`{total_alias}`' in query, (
                f"Grand total column {total_alias} not found in query"
            )
