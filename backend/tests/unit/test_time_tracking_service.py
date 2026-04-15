"""Unit tests for TimeTrackingService."""

import pytest
from unittest.mock import Mock
from services.time_tracking_service import TimeTrackingService


def _make_service(db=None, param_svc=None):
    db = db or Mock()
    param_svc = param_svc or Mock(get_param=Mock(return_value=None))
    return TimeTrackingService(db=db, parameter_service=param_svc)


def _entry_row(**overrides):
    base = {'id': 1, 'administration': 'T1', 'contact_id': 1,
            'product_id': None, 'project_name': 'Alpha',
            'entry_date': '2026-04-15', 'hours': 8.0, 'hourly_rate': 95.0,
            'description': 'Dev work', 'is_billable': True,
            'is_billed': False, 'invoice_id': None,
            'created_by': 'test', 'created_at': None, 'updated_at': None}
    base.update(overrides)
    return base


def _valid_data(**overrides):
    base = {'contact_id': 1, 'entry_date': '2026-04-15',
            'hours': 8.0, 'hourly_rate': 95.0}
    base.update(overrides)
    return base


# ── create_entry ────────────────────────────────────────────


def test_create_entry_valid_data_returns_entry():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [{'id': 1}],       # _validate_contact
        5,                  # INSERT
        [_entry_row(id=5)], # get_entry
    ])
    svc = _make_service(db=db)
    result = svc.create_entry('T1', _valid_data(), 'test')
    assert result['hours'] == 8.0


def test_create_entry_invalid_contact_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="Contact .* not found"):
        svc.create_entry('T1', _valid_data(), 'test')


def test_create_entry_missing_required_raises_valueerror():
    svc = _make_service()
    with pytest.raises(ValueError, match="Required fields missing"):
        svc.create_entry('T1', {'contact_id': 1}, 'test')


# ── update_entry ────────────────────────────────────────────


def test_update_entry_unbilled_allows_edit():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_entry_row()],     # get_entry (existing)
        None,               # UPDATE
        [_entry_row(hours=10.0)],  # get_entry (updated)
    ])
    svc = _make_service(db=db)
    result = svc.update_entry('T1', 1, {'hours': 10.0})
    assert result['hours'] == 10.0


def test_update_entry_billed_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[_entry_row(is_billed=True)])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="Cannot edit a billed"):
        svc.update_entry('T1', 1, {'hours': 10.0})


def test_update_entry_not_found_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="not found"):
        svc.update_entry('T1', 999, {'hours': 10.0})


# ── delete_entry ────────────────────────────────────────────


def test_delete_entry_unbilled_returns_true():
    db = Mock()
    db.execute_query = Mock(side_effect=[
        [_entry_row()],  # get_entry
        None,            # DELETE
    ])
    svc = _make_service(db=db)
    assert svc.delete_entry('T1', 1) is True


def test_delete_entry_billed_raises_valueerror():
    db = Mock()
    db.execute_query = Mock(return_value=[_entry_row(is_billed=True)])
    svc = _make_service(db=db)
    with pytest.raises(ValueError, match="Cannot delete a billed"):
        svc.delete_entry('T1', 1)


# ── get_unbilled_entries ────────────────────────────────────


def test_get_unbilled_entries_returns_unbilled_for_contact():
    db = Mock()
    db.execute_query = Mock(return_value=[_entry_row(), _entry_row(id=2)])
    svc = _make_service(db=db)
    result = svc.get_unbilled_entries('T1', 1)
    assert len(result) == 2


# ── mark_as_billed ──────────────────────────────────────────


def test_mark_as_billed_updates_entries_returns_count():
    db = Mock()
    db.execute_query = Mock(return_value=3)
    svc = _make_service(db=db)
    result = svc.mark_as_billed('T1', [1, 2, 3], invoice_id=42)
    assert result == 3


def test_mark_as_billed_empty_list_returns_zero():
    svc = _make_service()
    assert svc.mark_as_billed('T1', [], invoice_id=42) == 0


# ── get_summary ─────────────────────────────────────────────


def test_get_summary_by_contact_groups_correctly():
    db = Mock()
    db.execute_query = Mock(return_value=[
        {'contact_id': 1, 'total_hours': 40.0, 'total_amount': 3800.0},
    ])
    svc = _make_service(db=db)
    result = svc.get_summary('T1', group_by='contact')
    assert len(result) == 1
    assert result[0]['total_hours'] == 40.0


def test_get_summary_by_project_groups_correctly():
    db = Mock()
    db.execute_query = Mock(return_value=[
        {'project_name': 'Alpha', 'total_hours': 20.0, 'total_amount': 1900.0},
    ])
    svc = _make_service(db=db)
    result = svc.get_summary('T1', group_by='project')
    assert result[0]['project_name'] == 'Alpha'


def test_get_summary_by_period_month_groups_correctly():
    db = Mock()
    db.execute_query = Mock(return_value=[
        {'period': '2026-04', 'total_hours': 160.0, 'total_amount': 15200.0},
    ])
    svc = _make_service(db=db)
    result = svc.get_summary('T1', group_by='period', period='month')
    assert result[0]['period'] == '2026-04'


# ── is_enabled ──────────────────────────────────────────────


def test_is_enabled_default_returns_true():
    svc = _make_service()
    assert svc.is_enabled('T1') is True


def test_is_enabled_disabled_returns_false():
    param_svc = Mock(get_param=Mock(return_value=False))
    svc = _make_service(param_svc=param_svc)
    assert svc.is_enabled('T1') is False
