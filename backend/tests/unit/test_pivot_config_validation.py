"""
Property-based tests for pivot config validation.

Feature: dynamic-pivot-views
Properties 3 & 4 from the design document.

Property 3: Incomplete config rejection
    For any config with empty group_columns OR empty aggregate_measures,
    validation rejects.

Property 4: Column role overlap rejection
    For any config where the same column appears in multiple roles
    (row group, column pivot, column nest levels), validation rejects.

Validates: Requirements 1.6, 9.10
Reference: .kiro/specs/dynamic-pivot-views/design.md §Correctness Properties
"""

import sys
import os
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
    build_registry_from_db,
)


# ---------------------------------------------------------------------------
# Test infrastructure — mock DB + parameters
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
    'vw_bnb_total': [
        {'Field': 'channel', 'Type': 'varchar(50)'},
        {'Field': 'listing', 'Type': 'varchar(200)'},
        {'Field': 'checkinDate', 'Type': 'date'},
        {'Field': 'amountGross', 'Type': 'decimal(10,2)'},
        {'Field': 'year', 'Type': 'int'},
        {'Field': 'q', 'Type': 'int'},
        {'Field': 'administration', 'Type': 'varchar(100)'},
    ],
}

_PARAM_VALUES = {
    ('ui.pivot', 'registered_sources'): ['vw_mutaties', 'vw_bnb_total'],
    ('ui.pivot', 'exclude_columns.vw_mutaties'): [],
    ('ui.pivot', 'exclude_columns.vw_bnb_total'): [],
    ('ui.pivot', 'force_groupable.vw_mutaties'): ['jaar', 'kwartaal', 'maand', 'week'],
    ('ui.pivot', 'force_groupable.vw_bnb_total'): ['year', 'q'],
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
    db = _mock_db()
    ps = _mock_ps()
    return PivotService(db, ps)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

agg_function_st = st.sampled_from(['SUM', 'COUNT', 'AVG', 'MIN', 'MAX'])

# Valid groupable columns for vw_mutaties (after force_groupable applied)
_GROUPABLE = ['Aangifte', 'TransactionDate', 'Reknum', 'AccountName',
              'Parent', 'VW', 'jaar', 'kwartaal', 'maand', 'week',
              'ReferenceNumber', 'administration']
_AGGREGATABLE = ['Amount']

groupable_col_st = st.sampled_from(_GROUPABLE)
aggregatable_col_st = st.sampled_from(_AGGREGATABLE + ['*'])


# ---------------------------------------------------------------------------
# Property 3: Incomplete config rejection
# Feature: dynamic-pivot-views, Property 3: Incomplete config rejection
# Validates: Requirements 1.6
# ---------------------------------------------------------------------------

class TestIncompleteConfigRejection:
    """For any config with empty group_columns OR empty aggregate_measures,
    validation rejects."""

    @settings(max_examples=100)
    @given(
        agg_measures=st.lists(
            st.fixed_dictionaries({
                'function': agg_function_st,
                'column': aggregatable_col_st,
            }),
            min_size=1,
            max_size=5,
        ),
    )
    def test_empty_group_columns_rejected(self, agg_measures):
        """Empty group_columns should always be rejected."""
        svc = _make_service()
        with pytest.raises(ValueError, match="At least one group column"):
            svc._validate_config(
                'vw_mutaties', 'tenant1',
                [],  # empty group columns
                agg_measures,
                None, [],
            )

    @settings(max_examples=100)
    @given(
        group_cols=st.lists(groupable_col_st, min_size=1, max_size=5, unique=True),
    )
    def test_empty_aggregate_measures_rejected(self, group_cols):
        """Empty aggregate_measures should always be rejected."""
        svc = _make_service()
        with pytest.raises(ValueError, match="At least one group column"):
            svc._validate_config(
                'vw_mutaties', 'tenant1',
                group_cols,
                [],  # empty aggregate measures
                None, [],
            )

    @pytest.mark.unit
    def test_both_empty_rejected(self):
        """Both empty should be rejected."""
        svc = _make_service()
        with pytest.raises(ValueError, match="At least one group column"):
            svc._validate_config('vw_mutaties', 'tenant1', [], [], None, [])


# ---------------------------------------------------------------------------
# Property 4: Column role overlap rejection
# Feature: dynamic-pivot-views, Property 4: Column role overlap rejection
# Validates: Requirements 9.10
# ---------------------------------------------------------------------------

class TestColumnRoleOverlapRejection:
    """For any config where the same column appears in multiple roles,
    validation rejects."""

    @settings(max_examples=100)
    @given(
        shared_col=groupable_col_st,
        extra_group=st.lists(groupable_col_st, max_size=3),
    )
    def test_same_column_as_group_and_pivot_rejected(self, shared_col, extra_group):
        """A column used as both row group and column pivot should be rejected."""
        group_cols = list(set([shared_col] + extra_group))
        svc = _make_service()
        with pytest.raises(ValueError, match="cannot be used as both"):
            PivotService._validate_column_roles(
                group_cols,
                shared_col,  # same column as pivot
                [],
            )

    @settings(max_examples=100, database=None)
    @given(
        shared_col=groupable_col_st,
        extra_group=st.lists(groupable_col_st, max_size=3),
    )
    def test_same_column_as_group_and_nest_rejected(self, shared_col, extra_group):
        """A column used as both row group and nest level should be rejected."""
        group_cols = list(set([shared_col] + extra_group))
        svc = _make_service()
        with pytest.raises(ValueError, match="cannot be used as both"):
            PivotService._validate_column_roles(
                group_cols,
                None,
                [shared_col],  # same column as nest level
            )

    @settings(max_examples=100)
    @given(
        pivot_col=groupable_col_st,
    )
    def test_same_column_as_pivot_and_nest_rejected(self, pivot_col):
        """A column used as both column pivot and nest level should be rejected."""
        # Use a different column for group to avoid group/pivot overlap
        group_cols = [c for c in _GROUPABLE if c != pivot_col][:1]
        assume(len(group_cols) > 0)

        with pytest.raises(ValueError, match="cannot be used as both"):
            PivotService._validate_column_roles(
                group_cols,
                pivot_col,
                [pivot_col],  # same column as nest level
            )

    @settings(max_examples=100)
    @given(
        group_cols=st.lists(groupable_col_st, min_size=1, max_size=3, unique=True),
        pivot_col=st.one_of(st.none(), groupable_col_st),
        nest_cols=st.lists(groupable_col_st, max_size=2, unique=True),
    )
    def test_no_overlap_passes(self, group_cols, pivot_col, nest_cols):
        """When no column appears in multiple roles, validation passes."""
        group_set = set(group_cols)
        nest_set = set(nest_cols)

        # Ensure no overlaps
        if pivot_col and pivot_col in group_set:
            assume(False)
        if pivot_col and pivot_col in nest_set:
            assume(False)
        if group_set & nest_set:
            assume(False)

        # Should not raise
        PivotService._validate_column_roles(group_cols, pivot_col, nest_cols)
