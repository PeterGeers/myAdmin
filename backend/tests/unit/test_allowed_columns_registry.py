"""
Property-based tests for AllowedColumnsRegistry.

Feature: dynamic-pivot-views
Properties 7 & 8 from the design document.

Property 7: Column resolution is intersection
    For any system max and tenant restriction (subset of system max),
    resolved columns equal intersection; no tenant restriction returns
    full system set.

Property 8: Disallowed columns rejected
    For any request with column not in resolved registry, validation
    raises error.

Validates: Requirements 6.2, 6.3, 6.5
Reference: .kiro/specs/dynamic-pivot-views/design.md §Correctness Properties
"""

import sys
import os
import pytest
from unittest.mock import MagicMock
from hypothesis import given, strategies as st, settings, assume

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.pivot_service import (
    AllowedColumnsRegistry,
    SYSTEM_ALLOWED_COLUMNS,
    COLUMN_TYPE_MAP,
    DATA_SOURCE_LABELS,
    DATA_SOURCE_MODULES,
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


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# After registry is populated, these are the system-level columns
_GROUPABLE = ['Aangifte', 'TransactionDate', 'Reknum', 'AccountName',
              'Parent', 'VW', 'jaar', 'kwartaal', 'maand', 'week',
              'ReferenceNumber', 'administration']
_AGGREGATABLE = ['Amount']

groupable_col_st = st.sampled_from(_GROUPABLE)
aggregatable_col_st = st.sampled_from(_AGGREGATABLE)

# Strategy for a tenant restriction that is a subset of system max
@st.composite
def tenant_restriction_st(draw):
    """Generate a tenant restriction that is a subset of the system max."""
    g_subset = draw(st.lists(
        groupable_col_st, max_size=len(_GROUPABLE), unique=True,
    ))
    a_subset = draw(st.lists(
        aggregatable_col_st, max_size=len(_AGGREGATABLE), unique=True,
    ))
    return {'groupable': g_subset, 'aggregatable': a_subset}


# Strategy for a column name NOT in the allowed set
disallowed_col_st = st.text(
    alphabet=st.characters(whitelist_categories=('L',)),
    min_size=5, max_size=20,
).filter(lambda c: c not in _GROUPABLE and c not in _AGGREGATABLE and c != '*')


# ---------------------------------------------------------------------------
# Property 7: Column resolution is intersection
# Feature: dynamic-pivot-views, Property 7: Column resolution is intersection
# Validates: Requirements 6.2, 6.3
# ---------------------------------------------------------------------------

class TestColumnResolutionIntersection:
    """Resolved columns = intersection of system max and tenant restriction."""

    @settings(max_examples=100)
    @given(restriction=tenant_restriction_st())
    def test_with_tenant_restriction(self, restriction):
        """With a tenant restriction, result is intersection."""
        ps = MagicMock()
        ps.get_param.return_value = restriction
        registry = AllowedColumnsRegistry(ps)

        result = registry.get_available_columns('vw_mutaties', 'tenant1')

        # Groupable: intersection of system and restriction
        expected_g = [c for c in _GROUPABLE if c in restriction['groupable']]
        assert result['groupable'] == expected_g

        # Aggregatable: intersection of system and restriction
        expected_a = [c for c in _AGGREGATABLE if c in restriction['aggregatable']]
        assert result['aggregatable'] == expected_a

    @settings(max_examples=100)
    @given(data=st.data())
    def test_without_tenant_restriction(self, data):
        """Without tenant restriction, full system set is returned."""
        ps = MagicMock()
        ps.get_param.return_value = None  # no restriction
        registry = AllowedColumnsRegistry(ps)

        result = registry.get_available_columns('vw_mutaties', 'tenant1')

        assert result['groupable'] == _GROUPABLE
        assert result['aggregatable'] == _AGGREGATABLE

    @settings(max_examples=100)
    @given(restriction=tenant_restriction_st())
    def test_result_is_subset_of_system(self, restriction):
        """Resolved columns are always a subset of the system max."""
        ps = MagicMock()
        ps.get_param.return_value = restriction
        registry = AllowedColumnsRegistry(ps)

        result = registry.get_available_columns('vw_mutaties', 'tenant1')

        assert set(result['groupable']).issubset(set(_GROUPABLE))
        assert set(result['aggregatable']).issubset(set(_AGGREGATABLE))

    @settings(max_examples=100)
    @given(restriction=tenant_restriction_st())
    def test_result_is_subset_of_restriction(self, restriction):
        """Resolved columns are always a subset of the tenant restriction."""
        ps = MagicMock()
        ps.get_param.return_value = restriction
        registry = AllowedColumnsRegistry(ps)

        result = registry.get_available_columns('vw_mutaties', 'tenant1')

        assert set(result['groupable']).issubset(set(restriction['groupable']))
        assert set(result['aggregatable']).issubset(set(restriction['aggregatable']))


# ---------------------------------------------------------------------------
# Property 8: Disallowed columns rejected
# Feature: dynamic-pivot-views, Property 8: Disallowed columns rejected
# Validates: Requirements 6.5
# ---------------------------------------------------------------------------

class TestDisallowedColumnsRejected:
    """Any column not in the resolved registry raises ValueError."""

    @settings(max_examples=100)
    @given(bad_col=disallowed_col_st)
    def test_disallowed_group_column_rejected(self, bad_col):
        """A group column not in the allowed set should be rejected."""
        ps = MagicMock()
        ps.get_param.return_value = None  # full system set
        registry = AllowedColumnsRegistry(ps)

        with pytest.raises(ValueError, match="not allowed"):
            registry.validate_columns(
                'vw_mutaties', 'tenant1',
                group_columns=[bad_col],
                aggregate_columns=['Amount'],
            )

    @settings(max_examples=100)
    @given(bad_col=disallowed_col_st)
    def test_disallowed_aggregate_column_rejected(self, bad_col):
        """An aggregate column not in the allowed set should be rejected."""
        ps = MagicMock()
        ps.get_param.return_value = None
        registry = AllowedColumnsRegistry(ps)

        with pytest.raises(ValueError, match="not allowed"):
            registry.validate_columns(
                'vw_mutaties', 'tenant1',
                group_columns=['Aangifte'],
                aggregate_columns=[bad_col],
            )

    @settings(max_examples=100)
    @given(bad_col=disallowed_col_st)
    def test_disallowed_pivot_column_rejected(self, bad_col):
        """A column pivot not in the allowed set should be rejected."""
        ps = MagicMock()
        ps.get_param.return_value = None
        registry = AllowedColumnsRegistry(ps)

        with pytest.raises(ValueError, match="not allowed"):
            registry.validate_columns(
                'vw_mutaties', 'tenant1',
                group_columns=['Aangifte'],
                aggregate_columns=['Amount'],
                column_pivot=bad_col,
            )

    @settings(max_examples=100)
    @given(
        group_cols=st.lists(groupable_col_st, min_size=1, max_size=3, unique=True),
        agg_cols=st.lists(
            st.sampled_from(_AGGREGATABLE + ['*']),
            min_size=1, max_size=2,
        ),
    )
    def test_allowed_columns_pass(self, group_cols, agg_cols):
        """Columns in the allowed set should pass validation."""
        ps = MagicMock()
        ps.get_param.return_value = None
        registry = AllowedColumnsRegistry(ps)

        # Should not raise
        registry.validate_columns(
            'vw_mutaties', 'tenant1',
            group_columns=group_cols,
            aggregate_columns=agg_cols,
        )
