"""
Unit tests for PivotModelStore.

Example-based tests for serialization, deserialization, validation,
and CRUD operations with mocked DatabaseManager.

Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 5.1–5.6, 10.1–10.4
Reference: .kiro/specs/dynamic-pivot-views/design.md §2 PivotModelStore
"""

import sys
import os
import json
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.pivot_model_store import PivotModelStore, REQUIRED_DEFINITION_FIELDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_DEFINITION = {
    'data_source': 'vw_mutaties',
    'group_columns': ['Aangifte', 'jaar'],
    'aggregate_measures': [{'function': 'SUM', 'column': 'Amount'}],
    'filters': {'years': [2024]},
    'column_pivot': None,
    'column_nest_levels': [],
    'display_mode': 'flat',
}


def _make_store():
    """Return a PivotModelStore with a mocked DatabaseManager."""
    db = MagicMock()
    return PivotModelStore(db), db


# ---------------------------------------------------------------------------
# Serialization / Deserialization
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_serialize_produces_json_string():
    result = PivotModelStore.serialize(VALID_DEFINITION)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed == VALID_DEFINITION


@pytest.mark.unit
def test_deserialize_valid_json():
    json_str = json.dumps(VALID_DEFINITION)
    result = PivotModelStore.deserialize(json_str)
    assert result == VALID_DEFINITION


@pytest.mark.unit
def test_deserialize_dict_passthrough():
    result = PivotModelStore.deserialize(dict(VALID_DEFINITION))
    assert result == VALID_DEFINITION


@pytest.mark.unit
def test_deserialize_invalid_json_raises():
    with pytest.raises(ValueError, match="Invalid JSON"):
        PivotModelStore.deserialize("{not valid json!!")


@pytest.mark.unit
def test_deserialize_missing_data_source_raises():
    bad = {
        'group_columns': ['Aangifte'],
        'aggregate_measures': [{'function': 'SUM', 'column': 'Amount'}],
    }
    with pytest.raises(ValueError, match="data_source"):
        PivotModelStore.deserialize(json.dumps(bad))


@pytest.mark.unit
def test_deserialize_empty_group_columns_raises():
    bad = {
        'data_source': 'vw_mutaties',
        'group_columns': [],
        'aggregate_measures': [{'function': 'SUM', 'column': 'Amount'}],
    }
    with pytest.raises(ValueError, match="group_columns"):
        PivotModelStore.deserialize(json.dumps(bad))


@pytest.mark.unit
def test_deserialize_empty_aggregate_measures_raises():
    bad = {
        'data_source': 'vw_mutaties',
        'group_columns': ['Aangifte'],
        'aggregate_measures': [],
    }
    with pytest.raises(ValueError, match="aggregate_measures"):
        PivotModelStore.deserialize(json.dumps(bad))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_validate_definition_valid():
    # Should not raise
    PivotModelStore.validate_definition(VALID_DEFINITION)


@pytest.mark.unit
def test_validate_definition_missing_fields():
    for field in REQUIRED_DEFINITION_FIELDS:
        incomplete = dict(VALID_DEFINITION)
        del incomplete[field]
        with pytest.raises(ValueError, match=field):
            PivotModelStore.validate_definition(incomplete)


# ---------------------------------------------------------------------------
# CRUD — save_model
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_save_model_calls_db():
    store, db = _make_store()
    # No existing model with same name
    db.execute_query.return_value = []

    result = store.save_model(
        tenant='admin1',
        user_email='user@example.com',
        name='My Model',
        definition=VALID_DEFINITION,
    )

    assert result['success'] is True
    # First call: duplicate check SELECT
    # Second call: INSERT
    assert db.execute_query.call_count == 2

    # Verify the INSERT call
    insert_call = db.execute_query.call_args_list[1]
    insert_sql = insert_call[0][0]
    insert_params = insert_call[0][1]
    assert 'INSERT INTO pivot_models' in insert_sql
    assert insert_params[0] == 'admin1'          # tenant
    assert insert_params[1] == 'My Model'         # name
    assert insert_params[2] == 'vw_mutaties'      # data_source
    assert insert_params[4] == 'user@example.com'  # created_by
    # params[3] is the JSON definition string
    assert json.loads(insert_params[3]) == VALID_DEFINITION


@pytest.mark.unit
def test_save_model_duplicate_raises():
    store, db = _make_store()
    # Simulate existing row returned by duplicate check
    db.execute_query.return_value = [{'id': 42}]

    with pytest.raises(ValueError, match="already exists"):
        store.save_model(
            tenant='admin1',
            user_email='user@example.com',
            name='Duplicate Name',
            definition=VALID_DEFINITION,
        )


# ---------------------------------------------------------------------------
# CRUD — list_models
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_list_models_returns_summaries():
    store, db = _make_store()
    db.execute_query.return_value = [
        {
            'id': 1,
            'name': 'Model A',
            'data_source': 'vw_mutaties',
            'created_by': 'alice@example.com',
            'created_at': '2024-01-15 10:00:00',
        },
        {
            'id': 2,
            'name': 'Model B',
            'data_source': 'vw_bnb_total',
            'created_by': 'bob@example.com',
            'created_at': None,
        },
    ]

    result = store.list_models(tenant='admin1')

    assert len(result) == 2
    assert result[0]['id'] == 1
    assert result[0]['name'] == 'Model A'
    assert result[0]['data_source'] == 'vw_mutaties'
    assert result[0]['created_by'] == 'alice@example.com'
    assert result[0]['created_at'] == '2024-01-15 10:00:00'
    assert result[1]['created_at'] is None


# ---------------------------------------------------------------------------
# CRUD — delete_model
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_delete_model_returns_true():
    store, db = _make_store()
    db.execute_query.return_value = 1  # 1 row affected

    assert store.delete_model(tenant='admin1', model_id=42) is True


@pytest.mark.unit
def test_delete_model_returns_false():
    store, db = _make_store()
    db.execute_query.return_value = 0  # 0 rows affected

    assert store.delete_model(tenant='admin1', model_id=999) is False
