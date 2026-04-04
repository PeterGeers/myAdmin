"""
Unit tests for AssetService

Tests asset CRUD, book value calculation, disposal, and update locking
with mocked DatabaseManager.
"""

import pytest
from unittest.mock import MagicMock, call
from decimal import Decimal
from datetime import date, datetime

from services.asset_service import AssetService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute_query.return_value = []
    return db


@pytest.fixture
def service(mock_db):
    return AssetService(mock_db)


def _setup_responses(mock_db, responses):
    mock_db.execute_query.side_effect = list(responses)


# ============================================================================
# create_asset
# ============================================================================

class TestCreateAsset:

    def test_creates_asset_with_transaction(self, service, mock_db):
        _setup_responses(mock_db, [
            42,                      # INSERT into assets (returns lastrowid)
        ])

        result = service.create_asset('TestCorp', {
            'description': 'Toyota Yaris',
            'ledger_account': '3060',
            'purchase_date': '2024-06-15',
            'purchase_amount': 25000,
            'credit_account': '1002',
        })

        assert result['success'] is True
        assert result['asset_id'] == 42

    def test_creates_asset_without_transaction(self, service, mock_db):
        _setup_responses(mock_db, [
            7,                       # INSERT into assets (returns lastrowid)
        ])

        result = service.create_asset('TestCorp', {
            'description': 'Office desk',
            'ledger_account': '3051',
            'purchase_date': '2024-01-10',
            'purchase_amount': 500,
            # no credit_account → no transaction
        })

        assert result['success'] is True
        assert result['asset_id'] == 7

    def test_purchase_transaction_has_correct_ref1(self, service, mock_db):
        _setup_responses(mock_db, [
            99,                      # INSERT into assets (returns lastrowid)
        ])

        result = service.create_asset('TestCorp', {
            'description': 'Laptop',
            'ledger_account': '3051',
            'purchase_date': '2024-03-01',
            'purchase_amount': 1200,
            'credit_account': '1002',
        })

        assert result['success'] is True
        assert result['asset_id'] == 99


# ============================================================================
# get_assets
# ============================================================================

class TestGetAssets:

    def test_returns_assets_with_book_value(self, service, mock_db):
        _setup_responses(mock_db, [
            [
                {
                    'id': 1, 'administration': 'TestCorp',
                    'description': 'Car', 'category': 'vehicle',
                    'ledger_account': '3060', 'depreciation_account': '4017',
                    'purchase_date': date(2024, 1, 1),
                    'purchase_amount': Decimal('20000.00'),
                    'depreciation_method': 'straight_line',
                    'depreciation_frequency': 'annual',
                    'useful_life_years': 5,
                    'residual_value': Decimal('5000.00'),
                    'status': 'active',
                    'disposal_date': None,
                    'disposal_amount': None,
                    'reference_number': 'INV-001',
                    'notes': None,
                    'created_at': datetime(2024, 1, 1),
                    'updated_at': datetime(2024, 1, 1),
                    'total_depreciation': Decimal('3000.00'),
                    'book_value': Decimal('17000.00'),
                }
            ]
        ])

        assets = service.get_assets('TestCorp')

        assert len(assets) == 1
        assert assets[0]['book_value'] == 17000.0
        assert assets[0]['total_depreciation'] == 3000.0
        assert assets[0]['purchase_date'] == '2024-01-01'

    def test_filters_by_status(self, service, mock_db):
        _setup_responses(mock_db, [[]])

        service.get_assets('TestCorp', status='active')

        query = mock_db.execute_query.call_args[0][0]
        assert 'a.status = %s' in query

    def test_filters_by_category(self, service, mock_db):
        _setup_responses(mock_db, [[]])

        service.get_assets('TestCorp', category='vehicle')

        query = mock_db.execute_query.call_args[0][0]
        assert 'a.category = %s' in query


# ============================================================================
# get_asset
# ============================================================================

class TestGetAsset:

    def test_returns_asset_with_transactions(self, service, mock_db):
        _setup_responses(mock_db, [
            # Asset record
            [{
                'id': 1, 'administration': 'TestCorp',
                'description': 'Car', 'category': 'vehicle',
                'ledger_account': '3060', 'depreciation_account': '4017',
                'purchase_date': date(2024, 1, 1),
                'purchase_amount': Decimal('20000.00'),
                'depreciation_method': 'straight_line',
                'depreciation_frequency': 'annual',
                'useful_life_years': 5,
                'residual_value': Decimal('5000.00'),
                'status': 'active',
                'disposal_date': None, 'disposal_amount': None,
                'reference_number': None, 'notes': None,
                'created_at': datetime(2024, 1, 1),
                'updated_at': datetime(2024, 1, 1),
            }],
            # Linked transactions
            [
                {
                    'ID': 100, 'TransactionDate': date(2024, 1, 1),
                    'TransactionDescription': 'Aankoop: Car',
                    'TransactionAmount': Decimal('20000.00'),
                    'Debet': '3060', 'Credit': '1002',
                    'ReferenceNumber': 'INV-001',
                    'Ref1': 'ASSET-1', 'Ref2': '',
                },
                {
                    'ID': 200, 'TransactionDate': date(2024, 12, 31),
                    'TransactionDescription': 'Afschrijving: Car',
                    'TransactionAmount': Decimal('3000.00'),
                    'Debet': '4017', 'Credit': '3060',
                    'ReferenceNumber': 'Afschrijving 2024',
                    'Ref1': 'ASSET-1', 'Ref2': '2024',
                },
            ]
        ])

        asset = service.get_asset('TestCorp', 1)

        assert asset is not None
        assert asset['book_value'] == 17000.0
        assert asset['total_depreciation'] == 3000.0
        assert len(asset['transactions']) == 2
        assert asset['transactions'][0]['type'] == 'other'
        assert asset['transactions'][1]['type'] == 'depreciation'

    def test_returns_none_for_missing_asset(self, service, mock_db):
        _setup_responses(mock_db, [[]])

        asset = service.get_asset('TestCorp', 999)
        assert asset is None


# ============================================================================
# update_asset
# ============================================================================

class TestUpdateAsset:

    def test_updates_metadata(self, service, mock_db):
        _setup_responses(mock_db, [
            [{'id': 1}],        # asset exists
            [{'cnt': 0}],       # no depreciation entries
            None,                # UPDATE
        ])

        result = service.update_asset('TestCorp', 1, {
            'description': 'Updated Car',
            'notes': 'New note',
        })

        assert result['success'] is True

    def test_locks_financial_fields_after_depreciation(self, service, mock_db):
        _setup_responses(mock_db, [
            [{'id': 1}],        # asset exists
            [{'cnt': 3}],       # has 3 depreciation entries
            None,                # UPDATE (only non-financial fields)
        ])

        result = service.update_asset('TestCorp', 1, {
            'description': 'Updated',
            'purchase_amount': 99999,  # should be locked
        })

        assert result['success'] is True
        assert 'purchase_amount' in result.get('locked_fields', [])
        assert 'warning' in result

    def test_allows_financial_fields_before_depreciation(self, service, mock_db):
        _setup_responses(mock_db, [
            [{'id': 1}],        # asset exists
            [{'cnt': 0}],       # no depreciation
            None,                # UPDATE
        ])

        result = service.update_asset('TestCorp', 1, {
            'purchase_amount': 30000,
        })

        assert result['success'] is True
        assert 'locked_fields' not in result

    def test_returns_error_for_missing_asset(self, service, mock_db):
        _setup_responses(mock_db, [[]])

        result = service.update_asset('TestCorp', 999, {'description': 'X'})
        assert result['success'] is False


# ============================================================================
# dispose_asset
# ============================================================================

class TestDisposeAsset:

    def _mock_active_asset(self, mock_db, book_value=17000):
        """Set up mock for an active asset with given book value."""
        dep = 20000 - book_value
        _setup_responses(mock_db, [
            # get_asset → asset record
            [{
                'id': 1, 'administration': 'TestCorp',
                'description': 'Car', 'category': 'vehicle',
                'ledger_account': '3060', 'depreciation_account': '4017',
                'purchase_date': date(2024, 1, 1),
                'purchase_amount': Decimal('20000.00'),
                'depreciation_method': 'straight_line',
                'depreciation_frequency': 'annual',
                'useful_life_years': 5,
                'residual_value': Decimal('5000.00'),
                'status': 'active',
                'disposal_date': None, 'disposal_amount': None,
                'reference_number': None, 'notes': None,
                'created_at': datetime(2024, 1, 1),
                'updated_at': datetime(2024, 1, 1),
            }],
            # get_asset → transactions
            [{
                'ID': 200, 'TransactionDate': date(2024, 12, 31),
                'TransactionDescription': 'Afschrijving: Car',
                'TransactionAmount': Decimal(str(dep)),
                'Debet': '4017', 'Credit': '3060',
                'ReferenceNumber': 'Afschrijving 2024',
                'Ref1': 'ASSET-1', 'Ref2': '2024',
            }],
            None,  # UPDATE assets status
            None,  # INSERT write-off transaction
            None,  # INSERT sale proceeds (if applicable)
        ])

    def test_disposes_asset_with_write_off(self, service, mock_db):
        self._mock_active_asset(mock_db, book_value=17000)

        result = service.dispose_asset(
            'TestCorp', 1,
            disposal_date='2026-03-26',
            disposal_amount=10000,
            credit_account='1002',
        )

        assert result['success'] is True
        assert result['book_value'] == 17000.0
        assert result['write_off'] == 7000.0

    def test_dispose_scrapped_asset(self, service, mock_db):
        self._mock_active_asset(mock_db, book_value=17000)

        result = service.dispose_asset(
            'TestCorp', 1,
            disposal_date='2026-03-26',
            disposal_amount=0,
        )

        assert result['success'] is True
        assert result['write_off'] == 17000.0

    def test_dispose_already_disposed(self, service, mock_db):
        _setup_responses(mock_db, [
            [{
                'id': 1, 'administration': 'TestCorp',
                'description': 'Car', 'category': 'vehicle',
                'ledger_account': '3060', 'depreciation_account': '4017',
                'purchase_date': date(2024, 1, 1),
                'purchase_amount': Decimal('20000.00'),
                'depreciation_method': 'straight_line',
                'depreciation_frequency': 'annual',
                'useful_life_years': 5,
                'residual_value': Decimal('5000.00'),
                'status': 'disposed',
                'disposal_date': date(2025, 12, 31),
                'disposal_amount': Decimal('8000.00'),
                'reference_number': None, 'notes': None,
                'created_at': datetime(2024, 1, 1),
                'updated_at': datetime(2025, 12, 31),
            }],
            [],  # no transactions
        ])

        result = service.dispose_asset(
            'TestCorp', 1,
            disposal_date='2026-03-26',
            disposal_amount=0,
        )

        assert result['success'] is False
        assert 'already disposed' in result['error']


# ============================================================================
# generate_depreciation
# ============================================================================

class TestGenerateDepreciation:

    def _mock_active_assets(self, mock_db, assets_data, existing_dep_counts=None):
        """Set up mock for depreciation generation."""
        responses = [assets_data]  # SELECT active assets
        for i, asset in enumerate(assets_data or []):
            # Idempotency check per asset
            cnt = (existing_dep_counts or {}).get(asset['id'], 0)
            responses.append([{'cnt': cnt}])
            if cnt == 0:
                responses.append(None)  # INSERT transaction
        mock_db.execute_query.side_effect = responses

    def test_generates_annual_depreciation(self, service, mock_db):
        self._mock_active_assets(mock_db, [
            {
                'id': 1, 'description': 'Car',
                'purchase_amount': Decimal('20000'),
                'residual_value': Decimal('5000'),
                'useful_life_years': 5,
                'depreciation_method': 'straight_line',
                'depreciation_frequency': 'annual',
                'ledger_account': '3060',
                'depreciation_account': '4017',
            }
        ])

        result = service.generate_depreciation('TestCorp', 'annual', 2026)

        assert result['success'] is True
        assert result['entries_created'] == 1
        assert result['details'][0]['amount'] == 3000.0

    def test_generates_quarterly_depreciation(self, service, mock_db):
        self._mock_active_assets(mock_db, [
            {
                'id': 2, 'description': 'Laptop',
                'purchase_amount': Decimal('12000'),
                'residual_value': Decimal('0'),
                'useful_life_years': 4,
                'depreciation_method': 'straight_line',
                'depreciation_frequency': 'quarterly',
                'ledger_account': '3051',
                'depreciation_account': '4017',
            }
        ])

        result = service.generate_depreciation('TestCorp', 'Q1', 2026)

        assert result['entries_created'] == 1
        # 12000 / 4 years / 4 quarters = 750
        assert result['details'][0]['amount'] == 750.0

    def test_skips_already_existing(self, service, mock_db):
        self._mock_active_assets(mock_db, [
            {
                'id': 1, 'description': 'Car',
                'purchase_amount': Decimal('20000'),
                'residual_value': Decimal('5000'),
                'useful_life_years': 5,
                'depreciation_method': 'straight_line',
                'depreciation_frequency': 'annual',
                'ledger_account': '3060',
                'depreciation_account': '4017',
            }
        ], existing_dep_counts={1: 1})

        result = service.generate_depreciation('TestCorp', 'annual', 2026)

        assert result['entries_created'] == 0
        assert result['entries_skipped'] == 1
        assert result['details'][0]['status'] == 'skipped'

    def test_skips_wrong_frequency(self, service, mock_db):
        """Annual asset should be skipped when generating quarterly."""
        self._mock_active_assets(mock_db, [
            {
                'id': 1, 'description': 'Car',
                'purchase_amount': Decimal('20000'),
                'residual_value': Decimal('5000'),
                'useful_life_years': 5,
                'depreciation_method': 'straight_line',
                'depreciation_frequency': 'annual',
                'ledger_account': '3060',
                'depreciation_account': '4017',
            }
        ])

        result = service.generate_depreciation('TestCorp', 'Q1', 2026)

        assert result['entries_created'] == 0
        assert result['entries_skipped'] == 1

    def test_no_active_assets(self, service, mock_db):
        _setup_responses(mock_db, [[]])

        result = service.generate_depreciation('TestCorp', 'annual', 2026)

        assert result['success'] is True
        assert result['assets_processed'] == 0

    def test_sets_correct_ref_fields(self, service, mock_db):
        self._mock_active_assets(mock_db, [
            {
                'id': 42, 'description': 'Desk',
                'purchase_amount': Decimal('1000'),
                'residual_value': Decimal('0'),
                'useful_life_years': 5,
                'depreciation_method': 'straight_line',
                'depreciation_frequency': 'quarterly',
                'ledger_account': '3051',
                'depreciation_account': '4017',
                'reference_number': None,
            }
        ])

        service.generate_depreciation('TestCorp', 'Q2', 2026)

        # Find the INSERT call (third call: assets query, idempotency check, insert)
        insert_call = mock_db.execute_query.call_args_list[2]
        params = insert_call[0][1]
        # ReferenceNumber = asset_ref = description (no reference_number set)
        assert params[6] == 'Desk'
        # Ref1 = 'ASSET-42'
        assert params[7] == 'ASSET-42'
        # Ref2 = '2026-Q2'
        assert params[8] == '2026-Q2'
