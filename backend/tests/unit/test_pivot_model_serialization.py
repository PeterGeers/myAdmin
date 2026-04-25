"""
Property-based tests for PivotModelStore serialization.

Feature: dynamic-pivot-views
Properties 1 & 2 from the design document.

Property 1: Pivot model serialization round-trip
    For any valid definition, serialize then deserialize produces
    an equivalent definition.

Property 2: Malformed JSON rejection
    For any invalid/incomplete JSON, deserialization raises a
    descriptive error.

Validates: Requirements 4.2, 4.5, 10.1, 10.2, 10.3, 10.4
Reference: .kiro/specs/dynamic-pivot-views/design.md §Correctness Properties
"""

import sys
import os
import json
import pytest
from hypothesis import given, strategies as st, settings, assume

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from unittest.mock import MagicMock

from services.pivot_model_store import PivotModelStore
from services.pivot_service import (
    SYSTEM_ALLOWED_COLUMNS,
    COLUMN_TYPE_MAP,
    DATA_SOURCE_LABELS,
    DATA_SOURCE_MODULES,
    build_registry_from_db,
)

# ---------------------------------------------------------------------------
# Mock DESCRIBE results for registry initialisation
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
        {'Field': 'nights', 'Type': 'int'},
        {'Field': 'guests', 'Type': 'int'},
        {'Field': 'amountGross', 'Type': 'decimal(10,2)'},
        {'Field': 'amountNett', 'Type': 'decimal(10,2)'},
        {'Field': 'amountChannelFee', 'Type': 'decimal(10,2)'},
        {'Field': 'amountTouristTax', 'Type': 'decimal(10,2)'},
        {'Field': 'amountVat', 'Type': 'decimal(10,2)'},
        {'Field': 'pricePerNight', 'Type': 'decimal(10,2)'},
        {'Field': 'daysBeforeReservation', 'Type': 'int'},
        {'Field': 'year', 'Type': 'int'},
        {'Field': 'q', 'Type': 'int'},
        {'Field': 'm', 'Type': 'int'},
        {'Field': 'country', 'Type': 'varchar(5)'},
        {'Field': 'countryName', 'Type': 'varchar(100)'},
        {'Field': 'countryRegion', 'Type': 'varchar(100)'},
        {'Field': 'source_type', 'Type': 'varchar(20)'},
        {'Field': 'status', 'Type': 'varchar(20)'},
        {'Field': 'administration', 'Type': 'varchar(100)'},
    ],
}

_PARAM_VALUES = {
    ('ui.pivot', 'registered_sources'): ['vw_mutaties', 'vw_bnb_total'],
    ('ui.pivot', 'exclude_columns.vw_mutaties'): [],
    ('ui.pivot', 'exclude_columns.vw_bnb_total'): [],
    ('ui.pivot', 'force_groupable.vw_mutaties'): ['jaar', 'kwartaal', 'maand', 'week'],
    ('ui.pivot', 'force_groupable.vw_bnb_total'): [
        'year', 'q', 'm', 'nights', 'guests', 'daysBeforeReservation',
    ],
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
# Custom Hypothesis strategies
# ---------------------------------------------------------------------------

DATA_SOURCES = ['vw_mutaties', 'vw_bnb_total']

# Strategy for a valid data source
data_source_st = st.sampled_from(DATA_SOURCES)


def _columns_for_source(data_source: str, role: str):
    """Return the column list for a given data source and role."""
    return SYSTEM_ALLOWED_COLUMNS[data_source][role]


# Strategy for a valid aggregate measure
agg_function_st = st.sampled_from(['SUM', 'COUNT', 'AVG', 'MIN', 'MAX'])


def aggregate_measure_st(data_source: str):
    """Strategy for a single aggregate measure for the given data source."""
    agg_cols = _columns_for_source(data_source, 'aggregatable')
    # Include '*' for COUNT(*)
    col_st = st.sampled_from(agg_cols + ['*'])
    return st.fixed_dictionaries({
        'function': agg_function_st,
        'column': col_st,
    })


# Strategy for a valid pivot model definition
@st.composite
def valid_definition_st(draw):
    """Generate a valid PivotModelDefinition."""
    ds = draw(data_source_st)
    groupable = _columns_for_source(ds, 'groupable')

    # At least 1 group column, up to 5
    group_cols = draw(
        st.lists(
            st.sampled_from(groupable),
            min_size=1,
            max_size=min(5, len(groupable)),
            unique=True,
        )
    )

    # At least 1 aggregate measure, up to 10
    agg_measures = draw(
        st.lists(
            aggregate_measure_st(ds),
            min_size=1,
            max_size=10,
        )
    )

    # Optional filters
    filters = draw(st.fixed_dictionaries({
        'years': st.lists(
            st.integers(min_value=2020, max_value=2030),
            max_size=5,
        ),
    }))

    # Optional column pivot (must be groupable and not in group_cols)
    remaining_groupable = [c for c in groupable if c not in group_cols]
    if remaining_groupable:
        column_pivot = draw(
            st.one_of(st.none(), st.sampled_from(remaining_groupable))
        )
    else:
        column_pivot = None

    # Optional column nest levels (must not overlap with group_cols or pivot)
    used = set(group_cols)
    if column_pivot:
        used.add(column_pivot)
    nest_candidates = [c for c in groupable if c not in used]
    if nest_candidates:
        column_nest_levels = draw(
            st.lists(
                st.sampled_from(nest_candidates),
                max_size=min(5, len(nest_candidates)),
                unique=True,
            )
        )
    else:
        column_nest_levels = []

    display_mode = draw(st.sampled_from(['flat', 'hierarchical']))

    return {
        'data_source': ds,
        'group_columns': group_cols,
        'aggregate_measures': agg_measures,
        'filters': filters,
        'column_pivot': column_pivot,
        'column_nest_levels': column_nest_levels,
        'display_mode': display_mode,
    }


# ---------------------------------------------------------------------------
# Property 1: Pivot model serialization round-trip
# Feature: dynamic-pivot-views, Property 1: Pivot model serialization round-trip
# Validates: Requirements 4.2, 4.5, 10.1, 10.2, 10.3
# ---------------------------------------------------------------------------

class TestSerializationRoundTrip:
    """For any valid definition, serialize → deserialize produces equivalent."""

    @settings(max_examples=100)
    @given(definition=valid_definition_st())
    def test_round_trip_preserves_definition(self, definition):
        serialized = PivotModelStore.serialize(definition)
        deserialized = PivotModelStore.deserialize(serialized)
        assert deserialized == definition

    @settings(max_examples=100)
    @given(definition=valid_definition_st())
    def test_serialize_produces_valid_json(self, definition):
        serialized = PivotModelStore.serialize(definition)
        assert isinstance(serialized, str)
        # Must be parseable JSON
        parsed = json.loads(serialized)
        assert isinstance(parsed, dict)

    @settings(max_examples=100)
    @given(definition=valid_definition_st())
    def test_deserialize_preserves_all_fields(self, definition):
        serialized = PivotModelStore.serialize(definition)
        deserialized = PivotModelStore.deserialize(serialized)

        assert deserialized['data_source'] == definition['data_source']
        assert deserialized['group_columns'] == definition['group_columns']
        assert deserialized['aggregate_measures'] == definition['aggregate_measures']

    @settings(max_examples=50)
    @given(definition=valid_definition_st())
    def test_double_round_trip(self, definition):
        """Serialize → deserialize → serialize → deserialize is stable."""
        s1 = PivotModelStore.serialize(definition)
        d1 = PivotModelStore.deserialize(s1)
        s2 = PivotModelStore.serialize(d1)
        d2 = PivotModelStore.deserialize(s2)
        assert d1 == d2


# ---------------------------------------------------------------------------
# Property 2: Malformed JSON rejection
# Feature: dynamic-pivot-views, Property 2: Malformed JSON rejection
# Validates: Requirements 10.4
# ---------------------------------------------------------------------------

class TestMalformedJsonRejection:
    """For any invalid/incomplete JSON, deserialization raises descriptive error."""

    @settings(max_examples=100)
    @given(
        bad_json=st.text(
            alphabet=st.characters(
                whitelist_categories=('L', 'N', 'P', 'S'),
            ),
            min_size=1,
            max_size=200,
        )
    )
    def test_syntactically_invalid_json_rejected(self, bad_json):
        """Random text that isn't valid JSON should be rejected."""
        # Skip strings that happen to be valid JSON objects with required fields
        try:
            parsed = json.loads(bad_json)
            if isinstance(parsed, dict):
                if all(
                    k in parsed and parsed[k]
                    for k in ('data_source', 'group_columns', 'aggregate_measures')
                ):
                    assume(False)  # Skip — this is actually valid
        except (json.JSONDecodeError, TypeError):
            pass  # Expected — this is what we want to test

        with pytest.raises(ValueError):
            PivotModelStore.deserialize(bad_json)

    @settings(max_examples=100)
    @given(
        missing_field=st.sampled_from([
            'data_source', 'group_columns', 'aggregate_measures',
        ])
    )
    def test_missing_required_field_rejected(self, missing_field):
        """A definition missing any required field should be rejected."""
        definition = {
            'data_source': 'vw_mutaties',
            'group_columns': ['Aangifte'],
            'aggregate_measures': [{'function': 'SUM', 'column': 'Amount'}],
        }
        del definition[missing_field]
        json_str = json.dumps(definition)

        with pytest.raises(ValueError):
            PivotModelStore.deserialize(json_str)

    @settings(max_examples=100)
    @given(
        empty_field=st.sampled_from([
            'group_columns', 'aggregate_measures',
        ])
    )
    def test_empty_required_list_rejected(self, empty_field):
        """A definition with an empty required list should be rejected."""
        definition = {
            'data_source': 'vw_mutaties',
            'group_columns': ['Aangifte'],
            'aggregate_measures': [{'function': 'SUM', 'column': 'Amount'}],
        }
        definition[empty_field] = []
        json_str = json.dumps(definition)

        with pytest.raises(ValueError):
            PivotModelStore.deserialize(json_str)

    @pytest.mark.unit
    def test_empty_data_source_rejected(self):
        """An empty data_source string should be rejected."""
        definition = {
            'data_source': '',
            'group_columns': ['Aangifte'],
            'aggregate_measures': [{'function': 'SUM', 'column': 'Amount'}],
        }
        with pytest.raises(ValueError, match="data_source"):
            PivotModelStore.deserialize(json.dumps(definition))

    @pytest.mark.unit
    def test_non_dict_json_rejected(self):
        """A JSON array or primitive should be rejected."""
        with pytest.raises(ValueError):
            PivotModelStore.deserialize('[1, 2, 3]')

    @pytest.mark.unit
    def test_non_string_non_dict_rejected(self):
        """A non-string, non-dict input should be rejected."""
        with pytest.raises(ValueError, match="Expected JSON string or dict"):
            PivotModelStore.deserialize(12345)
