"""Unit tests for pdf_decision_helpers.py.

Tests cover:
- validate_duplicate_decision_inputs
- validate_transaction_data
- create_error_response
"""

import pytest
from pdf_decision_helpers import (
    validate_duplicate_decision_inputs,
    validate_transaction_data,
    create_error_response,
)


# ---------------------------------------------------------------------------
# validate_duplicate_decision_inputs
# ---------------------------------------------------------------------------

class TestValidateDuplicateDecisionInputs:
    """Tests for validate_duplicate_decision_inputs."""

    VALID_DUPLICATE_INFO = {'file_name': 'invoice.pdf', 'match_score': 0.95}
    VALID_TRANSACTIONS = [{'date': '2026-01-01', 'amount': 100, 'description': 'Test',
                           'debet': '4000', 'credit': '1300'}]
    VALID_FILE_DATA = {'url': 'https://drive.google.com/file/abc', 'name': 'invoice.pdf'}

    def test_valid_continue_decision(self):
        result = validate_duplicate_decision_inputs(
            'continue', self.VALID_DUPLICATE_INFO,
            self.VALID_TRANSACTIONS, self.VALID_FILE_DATA
        )
        assert result['valid'] is True

    def test_valid_cancel_decision(self):
        result = validate_duplicate_decision_inputs(
            'cancel', self.VALID_DUPLICATE_INFO,
            self.VALID_TRANSACTIONS, self.VALID_FILE_DATA
        )
        assert result['valid'] is True

    def test_case_insensitive_decision(self):
        result = validate_duplicate_decision_inputs(
            'CONTINUE', self.VALID_DUPLICATE_INFO,
            self.VALID_TRANSACTIONS, self.VALID_FILE_DATA
        )
        assert result['valid'] is True

    def test_invalid_decision_value(self):
        result = validate_duplicate_decision_inputs(
            'skip', self.VALID_DUPLICATE_INFO,
            self.VALID_TRANSACTIONS, self.VALID_FILE_DATA
        )
        assert result['valid'] is False
        assert 'invalid_decision_value' in result['error_response']['error_code']

    def test_empty_decision(self):
        result = validate_duplicate_decision_inputs(
            '', self.VALID_DUPLICATE_INFO,
            self.VALID_TRANSACTIONS, self.VALID_FILE_DATA
        )
        assert result['valid'] is False

    def test_none_decision(self):
        result = validate_duplicate_decision_inputs(
            None, self.VALID_DUPLICATE_INFO,
            self.VALID_TRANSACTIONS, self.VALID_FILE_DATA
        )
        assert result['valid'] is False

    def test_invalid_duplicate_info(self):
        result = validate_duplicate_decision_inputs(
            'continue', None,
            self.VALID_TRANSACTIONS, self.VALID_FILE_DATA
        )
        assert result['valid'] is False
        assert 'invalid_duplicate_info' in result['error_response']['error_code']

    def test_invalid_transactions(self):
        result = validate_duplicate_decision_inputs(
            'continue', self.VALID_DUPLICATE_INFO,
            None, self.VALID_FILE_DATA
        )
        assert result['valid'] is False
        assert 'invalid_transactions' in result['error_response']['error_code']

    def test_empty_transactions_list(self):
        result = validate_duplicate_decision_inputs(
            'continue', self.VALID_DUPLICATE_INFO,
            [], self.VALID_FILE_DATA
        )
        assert result['valid'] is False

    def test_invalid_file_data(self):
        result = validate_duplicate_decision_inputs(
            'continue', self.VALID_DUPLICATE_INFO,
            self.VALID_TRANSACTIONS, None
        )
        assert result['valid'] is False

    def test_missing_file_data_fields(self):
        result = validate_duplicate_decision_inputs(
            'continue', self.VALID_DUPLICATE_INFO,
            self.VALID_TRANSACTIONS, {'url': 'http://example.com'}  # missing 'name'
        )
        assert result['valid'] is False
        assert 'missing_file_data_fields' in result['error_response']['error_code']


# ---------------------------------------------------------------------------
# validate_transaction_data
# ---------------------------------------------------------------------------

class TestValidateTransactionData:
    """Tests for validate_transaction_data."""

    def test_valid_transactions(self):
        txns = [{'date': '2026-01-01', 'description': 'Rent', 'amount': 500,
                 'debet': '4000', 'credit': '1300'}]
        errors = validate_transaction_data(txns)
        assert errors == []

    def test_empty_list(self):
        errors = validate_transaction_data([])
        assert len(errors) == 1
        assert 'No transactions' in errors[0]

    def test_missing_required_fields(self):
        txns = [{'date': '2026-01-01'}]  # Missing description, amount, debet, credit
        errors = validate_transaction_data(txns)
        assert len(errors) == 1
        assert 'missing fields' in errors[0]

    def test_invalid_amount_format(self):
        txns = [{'date': '2026-01-01', 'description': 'Test', 'amount': 'abc',
                 'debet': '4000', 'credit': '1300'}]
        errors = validate_transaction_data(txns)
        assert any('invalid amount format' in e for e in errors)

    def test_negative_amount(self):
        txns = [{'date': '2026-01-01', 'description': 'Test', 'amount': -50,
                 'debet': '4000', 'credit': '1300'}]
        errors = validate_transaction_data(txns)
        assert any('invalid amount' in e for e in errors)

    def test_non_dict_transaction(self):
        txns = ['not a dict']
        errors = validate_transaction_data(txns)
        assert any('not a dictionary' in e for e in errors)

    def test_invalid_date(self):
        txns = [{'date': '', 'description': 'Test', 'amount': 100,
                 'debet': '4000', 'credit': '1300'}]
        errors = validate_transaction_data(txns)
        assert any('invalid date' in e for e in errors)


# ---------------------------------------------------------------------------
# create_error_response
# ---------------------------------------------------------------------------

class TestCreateErrorResponse:
    """Tests for create_error_response."""

    def test_basic_error_response(self):
        resp = create_error_response('test_error', 'Something went wrong')
        assert resp['success'] is False
        assert resp['error_code'] == 'test_error'
        assert resp['error_message'] == 'Something went wrong'
        assert resp['transactions'] == []
        assert resp['cleanup_performed'] is False
        assert 'timestamp' in resp

    def test_includes_errors_list(self):
        resp = create_error_response('err', 'msg', errors=['err1', 'err2'])
        assert resp['errors'] == ['err1', 'err2']

    def test_includes_warnings(self):
        resp = create_error_response('err', 'msg', warnings=['warn1'])
        assert resp['warnings'] == ['warn1']

    def test_custom_user_message(self):
        resp = create_error_response('err', 'msg', user_message='Please retry')
        assert resp['user_message'] == 'Please retry'

    def test_default_user_message(self):
        resp = create_error_response('err', 'msg')
        assert 'try again' in resp['user_message'].lower()
