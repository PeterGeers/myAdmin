"""
Unit tests for Phase 12: Ledger Parameters & Invoice Revenue Account.

Covers:
- ledger_parameters.json contains all three ZZP entries (Req 17.1, 19.1)
- Invoice ledger API returns flagged accounts (Req 17.3)
- Invoice ledger API fallback when no accounts flagged (Req 17.4)
- _get_param() raises ValueError when parameter not configured (Req 19.2, 19.3, 19.5)
- book_outgoing_invoice() uses invoice-level revenue_account (Req 18.4, 18.5)
- book_outgoing_invoice() falls back to parameter when revenue_account is None (Req 18.3)
- book_credit_note() uses original invoice's revenue_account (Req 18.6)
- Booking account validation rejects unflagged accounts (Req 19.6)

Reference: .kiro/specs/zzp-module/tasks.md Task 12.9
"""

import json
import os
import pytest
from unittest.mock import Mock
from datetime import date

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.invoice_booking_helper import InvoiceBookingHelper


# ── Path to ledger_parameters.json ──────────────────────────

_LEDGER_PARAMS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'src', 'config', 'ledger_parameters.json'
)


# ── Helpers ─────────────────────────────────────────────────

_DEFAULT_PARAMS = {
    'debtor_account': '1300',
    'creditor_account': '1600',
    'revenue_account': '8001',
    'expense_account': '4000',
    'btw_debit_account': '2010',
}


def _make_param_svc(overrides: dict = None):
    """Create a mock ParameterService returning configured account values."""
    params = {**_DEFAULT_PARAMS, **(overrides or {})}

    def _get_param(namespace, key, tenant=None):
        return params.get(key)

    svc = Mock()
    svc.get_param = Mock(side_effect=_get_param)
    return svc


def _make_helper(txn_logic=None, tax_svc=None, param_svc=None):
    db = Mock()
    txn_logic = txn_logic or Mock(
        save_approved_transactions=Mock(side_effect=lambda t: t)
    )
    tax_svc = tax_svc or Mock(get_tax_rate=Mock(return_value={
        'rate': 21.0, 'ledger_account': '2021',
    }))
    param_svc = param_svc if param_svc is not None else _make_param_svc()
    return InvoiceBookingHelper(
        db=db, transaction_logic=txn_logic,
        tax_rate_service=tax_svc, parameter_service=param_svc,
    )


def _outgoing_invoice(**overrides):
    base = {
        'invoice_number': 'INV-2026-0001',
        'invoice_type': 'invoice',
        'invoice_date': '2026-04-15',
        'grand_total': 18392.0,
        'vat_total': 3192.0,
        'exchange_rate': 1.0,
        'contact': {'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'},
        'vat_summary': [
            {'vat_code': 'high', 'vat_rate': 21.0,
             'base_amount': 15200.0, 'vat_amount': 3192.0},
        ],
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════
# 1. Ledger Parameters JSON Registry (Req 17.1, 19.1)
# ═══════════════════════════════════════════════════════════


class TestLedgerParametersJson:
    """Verify ledger_parameters.json contains all three ZZP entries."""

    @pytest.fixture(autouse=True)
    def load_registry(self):
        with open(_LEDGER_PARAMS_PATH, 'r') as f:
            self.registry = json.load(f)
        self.keys = {entry['key']: entry for entry in self.registry}

    def test_registry_is_valid_json_array(self):
        assert isinstance(self.registry, list)
        assert len(self.registry) > 0

    def test_zzp_invoice_ledger_entry_exists(self):
        """Req 17.1: zzp_invoice_ledger must be in the registry."""
        assert 'zzp_invoice_ledger' in self.keys

    def test_zzp_debtor_account_entry_exists(self):
        """Req 19.1: zzp_debtor_account must be in the registry."""
        assert 'zzp_debtor_account' in self.keys

    def test_zzp_creditor_account_entry_exists(self):
        """Req 19.1: zzp_creditor_account must be in the registry."""
        assert 'zzp_creditor_account' in self.keys

    # ── zzp_invoice_ledger structure ────────────────────────

    def test_zzp_invoice_ledger_type_is_boolean(self):
        assert self.keys['zzp_invoice_ledger']['type'] == 'boolean'

    def test_zzp_invoice_ledger_module_is_zzp(self):
        assert self.keys['zzp_invoice_ledger']['module'] == 'ZZP'

    def test_zzp_invoice_ledger_has_english_label(self):
        entry = self.keys['zzp_invoice_ledger']
        assert 'label_en' in entry
        assert len(entry['label_en']) > 0

    def test_zzp_invoice_ledger_has_dutch_label(self):
        entry = self.keys['zzp_invoice_ledger']
        assert 'label_nl' in entry
        assert len(entry['label_nl']) > 0

    def test_zzp_invoice_ledger_has_english_description(self):
        entry = self.keys['zzp_invoice_ledger']
        assert 'description_en' in entry
        assert len(entry['description_en']) > 0

    def test_zzp_invoice_ledger_has_dutch_description(self):
        entry = self.keys['zzp_invoice_ledger']
        assert 'description_nl' in entry
        assert len(entry['description_nl']) > 0

    # ── zzp_debtor_account structure ────────────────────────

    def test_zzp_debtor_account_type_is_boolean(self):
        assert self.keys['zzp_debtor_account']['type'] == 'boolean'

    def test_zzp_debtor_account_module_is_zzp(self):
        assert self.keys['zzp_debtor_account']['module'] == 'ZZP'

    def test_zzp_debtor_account_has_english_label(self):
        entry = self.keys['zzp_debtor_account']
        assert 'label_en' in entry
        assert len(entry['label_en']) > 0

    def test_zzp_debtor_account_has_dutch_label(self):
        entry = self.keys['zzp_debtor_account']
        assert 'label_nl' in entry
        assert len(entry['label_nl']) > 0

    # ── zzp_creditor_account structure ──────────────────────

    def test_zzp_creditor_account_type_is_boolean(self):
        assert self.keys['zzp_creditor_account']['type'] == 'boolean'

    def test_zzp_creditor_account_module_is_zzp(self):
        assert self.keys['zzp_creditor_account']['module'] == 'ZZP'

    def test_zzp_creditor_account_has_english_label(self):
        entry = self.keys['zzp_creditor_account']
        assert 'label_en' in entry
        assert len(entry['label_en']) > 0

    def test_zzp_creditor_account_has_dutch_label(self):
        entry = self.keys['zzp_creditor_account']
        assert 'label_nl' in entry
        assert len(entry['label_nl']) > 0

    # ── Structural consistency with existing entries ─────────

    def test_all_zzp_entries_follow_same_structure_as_bank_account(self):
        """ZZP entries should have the same required fields as bank_account."""
        bank = self.keys.get('bank_account')
        if not bank:
            pytest.skip("bank_account entry not found for comparison")
        required_fields = {'key', 'type', 'label_en', 'label_nl', 'module'}
        for zzp_key in ('zzp_invoice_ledger', 'zzp_debtor_account', 'zzp_creditor_account'):
            entry = self.keys[zzp_key]
            missing = required_fields - set(entry.keys())
            assert not missing, f"{zzp_key} missing fields: {missing}"

    def test_no_duplicate_keys_in_registry(self):
        """Each key should appear exactly once."""
        all_keys = [entry['key'] for entry in self.registry]
        assert len(all_keys) == len(set(all_keys)), \
            f"Duplicate keys found: {[k for k in all_keys if all_keys.count(k) > 1]}"


# ═══════════════════════════════════════════════════════════
# 2. _get_param raises ValueError (Req 19.2, 19.3, 19.5)
# ═══════════════════════════════════════════════════════════


class TestGetParamRaisesOnMissing:
    """_get_param must raise ValueError with descriptive message when not configured."""

    def test_raises_for_debtor_account(self):
        param_svc = _make_param_svc({'debtor_account': None})
        helper = _make_helper(param_svc=param_svc)
        with pytest.raises(ValueError, match="zzp.debtor_account"):
            helper._get_param('T1', 'debtor_account')

    def test_raises_for_creditor_account(self):
        param_svc = _make_param_svc({'creditor_account': None})
        helper = _make_helper(param_svc=param_svc)
        with pytest.raises(ValueError, match="zzp.creditor_account"):
            helper._get_param('T1', 'creditor_account')

    def test_raises_for_revenue_account(self):
        param_svc = _make_param_svc({'revenue_account': None})
        helper = _make_helper(param_svc=param_svc)
        with pytest.raises(ValueError, match="zzp.revenue_account"):
            helper._get_param('T1', 'revenue_account')

    def test_raises_for_expense_account(self):
        param_svc = _make_param_svc({'expense_account': None})
        helper = _make_helper(param_svc=param_svc)
        with pytest.raises(ValueError, match="zzp.expense_account"):
            helper._get_param('T1', 'expense_account')

    def test_raises_for_btw_debit_account(self):
        param_svc = _make_param_svc({'btw_debit_account': None})
        helper = _make_helper(param_svc=param_svc)
        with pytest.raises(ValueError, match="zzp.btw_debit_account"):
            helper._get_param('T1', 'btw_debit_account')

    def test_error_message_includes_tenant_name(self):
        param_svc = _make_param_svc({'debtor_account': None})
        helper = _make_helper(param_svc=param_svc)
        with pytest.raises(ValueError, match="tenant 'MyTenant'"):
            helper._get_param('MyTenant', 'debtor_account')

    def test_error_message_includes_parameter_admin_hint(self):
        param_svc = _make_param_svc({'debtor_account': None})
        helper = _make_helper(param_svc=param_svc)
        with pytest.raises(ValueError, match="Tenant Administration"):
            helper._get_param('T1', 'debtor_account')

    def test_raises_when_parameter_service_is_none(self):
        """No silent fallback even without a parameter_service."""
        helper = _make_helper()
        helper.parameter_service = None
        with pytest.raises(ValueError, match="zzp.debtor_account"):
            helper._get_param('T1', 'debtor_account')

    def test_returns_value_when_configured(self):
        """Sanity check: returns the value when parameter is configured."""
        helper = _make_helper()
        assert helper._get_param('T1', 'debtor_account') == '1300'

    def test_returns_string_type(self):
        """_get_param always returns a string."""
        helper = _make_helper()
        result = helper._get_param('T1', 'debtor_account')
        assert isinstance(result, str)

    def test_unknown_key_raises_with_zzp_prefix(self):
        """Unknown keys still raise with a zzp.{key} formatted message."""
        param_svc = Mock()
        param_svc.get_param = Mock(return_value=None)
        helper = _make_helper(param_svc=param_svc)
        with pytest.raises(ValueError, match="zzp.unknown_key"):
            helper._get_param('T1', 'unknown_key')


# ═══════════════════════════════════════════════════════════
# 3. Invoice-Level Revenue Account (Req 18.4, 18.5)
# ═══════════════════════════════════════════════════════════


class TestOutgoingInvoiceRevenueAccount:
    """book_outgoing_invoice uses invoice-level revenue_account when set."""

    def test_uses_invoice_level_revenue_account_for_main_entry(self):
        """Req 18.4: Main entry credits the invoice's revenue account."""
        helper = _make_helper()
        invoice = _outgoing_invoice(revenue_account='8010')
        result = helper.book_outgoing_invoice('T1', invoice)
        main = result[0]
        assert main['Credit'] == '8010'

    def test_uses_invoice_level_revenue_account_for_vat_entry(self):
        """Req 18.5: VAT entry debits the invoice's revenue account."""
        helper = _make_helper()
        invoice = _outgoing_invoice(revenue_account='8010')
        result = helper.book_outgoing_invoice('T1', invoice)
        vat = result[1]
        assert vat['Debet'] == '8010'

    def test_falls_back_to_param_when_revenue_account_missing(self):
        """Req 18.3: Falls back to zzp.revenue_account parameter."""
        helper = _make_helper()
        invoice = _outgoing_invoice()  # no revenue_account key
        result = helper.book_outgoing_invoice('T1', invoice)
        main = result[0]
        assert main['Credit'] == '8001'  # from parameter

    def test_falls_back_to_param_when_revenue_account_is_none(self):
        helper = _make_helper()
        invoice = _outgoing_invoice(revenue_account=None)
        result = helper.book_outgoing_invoice('T1', invoice)
        main = result[0]
        assert main['Credit'] == '8001'

    def test_falls_back_to_param_when_revenue_account_is_empty_string(self):
        helper = _make_helper()
        invoice = _outgoing_invoice(revenue_account='')
        result = helper.book_outgoing_invoice('T1', invoice)
        main = result[0]
        # Empty string is falsy, so falls back to parameter
        assert main['Credit'] == '8001'

    def test_invoice_level_overrides_custom_tenant_param(self):
        """Invoice-level takes precedence over custom tenant parameter."""
        param_svc = _make_param_svc({'revenue_account': '8100'})
        helper = _make_helper(param_svc=param_svc)
        invoice = _outgoing_invoice(revenue_account='8200')
        result = helper.book_outgoing_invoice('T1', invoice)
        main = result[0]
        assert main['Credit'] == '8200'  # invoice-level wins
        vat = result[1]
        assert vat['Debet'] == '8200'

    def test_debtor_account_unaffected_by_revenue_override(self):
        """Debtor account always comes from parameter, not invoice."""
        helper = _make_helper()
        invoice = _outgoing_invoice(revenue_account='8010')
        result = helper.book_outgoing_invoice('T1', invoice)
        main = result[0]
        assert main['Debet'] == '1300'  # debtor from param, unchanged


# ═══════════════════════════════════════════════════════════
# 4. Credit Note Revenue Account (Req 18.6)
# ═══════════════════════════════════════════════════════════


class TestCreditNoteRevenueAccount:
    """book_credit_note uses the original invoice's revenue_account."""

    def _make_credit_note(self, **overrides):
        base = {
            'invoice_number': 'CN-2026-0001',
            'invoice_type': 'credit_note',
            'invoice_date': '2026-04-20',
            'grand_total': -18392.0,
            'vat_total': -3192.0,
            'exchange_rate': 1.0,
            'contact': {'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'},
            'vat_summary': [
                {'vat_code': 'high', 'vat_rate': 21.0,
                 'base_amount': -15200.0, 'vat_amount': -3192.0},
            ],
        }
        base.update(overrides)
        return base

    def test_uses_original_invoice_revenue_account(self):
        """Req 18.6: Reversal uses the original invoice's revenue account."""
        helper = _make_helper()
        original = _outgoing_invoice(revenue_account='8010')
        cn = self._make_credit_note()
        result = helper.book_credit_note('T1', cn, original)
        main = result[0]
        assert main['Debet'] == '8010'  # original's revenue (reversed)

    def test_falls_back_to_param_when_original_has_no_revenue_account(self):
        helper = _make_helper()
        original = _outgoing_invoice()  # no revenue_account
        cn = self._make_credit_note()
        result = helper.book_credit_note('T1', cn, original)
        main = result[0]
        assert main['Debet'] == '8001'  # from parameter

    def test_falls_back_to_param_when_original_revenue_account_is_none(self):
        helper = _make_helper()
        original = _outgoing_invoice(revenue_account=None)
        cn = self._make_credit_note()
        result = helper.book_credit_note('T1', cn, original)
        main = result[0]
        assert main['Debet'] == '8001'

    def test_credit_note_debtor_account_from_param(self):
        """Debtor account always comes from parameter."""
        helper = _make_helper()
        original = _outgoing_invoice(revenue_account='8010')
        cn = self._make_credit_note()
        result = helper.book_credit_note('T1', cn, original)
        main = result[0]
        assert main['Credit'] == '1300'  # debtor from param

    def test_original_revenue_overrides_custom_tenant_param(self):
        """Original invoice's revenue account takes precedence over tenant param."""
        param_svc = _make_param_svc({'revenue_account': '8100'})
        helper = _make_helper(param_svc=param_svc)
        original = _outgoing_invoice(revenue_account='8200')
        cn = self._make_credit_note()
        result = helper.book_credit_note('T1', cn, original)
        main = result[0]
        assert main['Debet'] == '8200'  # original's revenue wins


# ═══════════════════════════════════════════════════════════
# 5. Booking Account Validation (Req 19.6)
# ═══════════════════════════════════════════════════════════


class TestValidateBookingAccount:
    """_validate_booking_account rejects accounts without the required flag."""

    @pytest.fixture(autouse=True)
    def setup_routes(self):
        """Import the validation function from zzp_routes."""
        from routes.zzp_routes import _validate_booking_account, _BOOKING_ACCOUNT_FLAG_MAP
        self.validate = _validate_booking_account
        self.flag_map = _BOOKING_ACCOUNT_FLAG_MAP

    def test_flag_map_contains_debtor_account(self):
        assert 'debtor_account' in self.flag_map
        assert self.flag_map['debtor_account'] == 'zzp_debtor_account'

    def test_flag_map_contains_creditor_account(self):
        assert 'creditor_account' in self.flag_map
        assert self.flag_map['creditor_account'] == 'zzp_creditor_account'

    def test_flag_map_contains_revenue_account(self):
        assert 'revenue_account' in self.flag_map
        assert self.flag_map['revenue_account'] == 'zzp_invoice_ledger'

    def test_rejects_unflagged_debtor_account(self):
        """Account without zzp_debtor_account flag raises ValueError."""
        with pytest.raises(ValueError, match="zzp_debtor_account"):
            with unittest_mock_db([]):  # No matching rows
                self.validate('TestTenant', 'debtor_account', '1300')

    def test_rejects_unflagged_creditor_account(self):
        with pytest.raises(ValueError, match="zzp_creditor_account"):
            with unittest_mock_db([]):
                self.validate('TestTenant', 'creditor_account', '1600')

    def test_rejects_unflagged_revenue_account(self):
        with pytest.raises(ValueError, match="zzp_invoice_ledger"):
            with unittest_mock_db([]):
                self.validate('TestTenant', 'revenue_account', '8001')

    def test_accepts_flagged_account(self):
        """Account with the required flag should not raise."""
        with unittest_mock_db([{'nummer': '1300'}]):
            self.validate('TestTenant', 'debtor_account', '1300')
            # No exception = pass

    def test_unknown_key_skips_validation(self):
        """Unknown keys are silently accepted (no flag to check)."""
        with unittest_mock_db([]):
            self.validate('TestTenant', 'unknown_key', '9999')
            # No exception = pass

    def test_error_message_includes_account_code(self):
        with pytest.raises(ValueError, match="9999"):
            with unittest_mock_db([]):
                self.validate('TestTenant', 'debtor_account', '9999')

    def test_error_message_includes_flag_name(self):
        with pytest.raises(ValueError, match="zzp_debtor_account"):
            with unittest_mock_db([]):
                self.validate('TestTenant', 'debtor_account', '1300')


# ═══════════════════════════════════════════════════════════
# 6. REQUIRED_BOOKING_PARAMS constant (Req 19.2)
# ═══════════════════════════════════════════════════════════


class TestRequiredBookingParams:
    """Verify the REQUIRED_BOOKING_PARAMS constant is complete."""

    def test_contains_debtor_account(self):
        assert 'debtor_account' in InvoiceBookingHelper.REQUIRED_BOOKING_PARAMS

    def test_contains_creditor_account(self):
        assert 'creditor_account' in InvoiceBookingHelper.REQUIRED_BOOKING_PARAMS

    def test_contains_revenue_account(self):
        assert 'revenue_account' in InvoiceBookingHelper.REQUIRED_BOOKING_PARAMS

    def test_values_use_zzp_namespace_prefix(self):
        for key, display_name in InvoiceBookingHelper.REQUIRED_BOOKING_PARAMS.items():
            assert display_name.startswith('zzp.'), \
                f"Display name for '{key}' should start with 'zzp.' but got '{display_name}'"


# ═══════════════════════════════════════════════════════════
# Context manager for mocking DatabaseManager in zzp_routes
# ═══════════════════════════════════════════════════════════

import contextlib
from unittest.mock import patch


@contextlib.contextmanager
def unittest_mock_db(return_value):
    """Mock DatabaseManager in zzp_routes for _validate_booking_account tests."""
    mock_db = Mock()
    mock_db.execute_query.return_value = return_value
    with patch('routes.zzp_routes.DatabaseManager', return_value=mock_db):
        yield mock_db
