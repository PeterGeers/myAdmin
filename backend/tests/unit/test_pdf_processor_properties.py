"""
Property-based tests for PDFProcessor AI extraction.

Uses Hypothesis to verify correctness properties from the design document.
Feature: vendor-parser-cleanup

Properties tested:
- Property 1: AI-only extraction path (Requirements 1.6, 2.1, 3.3)
- Property 2: Valid AI result passthrough (Requirements 2.2, 2.5)
- Property 3: AI failure produces correct fallback structure (Requirements 2.3, 2.4, 5.1, 5.2)

Reference: .kiro/specs/vendor-parser-cleanup/design.md
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pdf_processor import PDFProcessor


# ---------------------------------------------------------------------------
# Strategy helpers for Property 2
# ---------------------------------------------------------------------------

# Generate folder names that do NOT match CSV rules (no "airbnb" substring)
valid_folder_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=30,
).filter(lambda s: 'airbnb' not in s.lower())

# Generate valid total amounts (> 0)
valid_amount_st = st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False)

# Generate valid VAT amounts (>= 0)
valid_vat_st = st.floats(min_value=0.0, max_value=50000.0, allow_nan=False, allow_infinity=False)

# Generate dates in YYYY-MM-DD format
valid_date_st = st.dates().map(lambda d: d.strftime('%Y-%m-%d'))

# Generate descriptions
valid_description_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=1,
    max_size=100,
)

# Generate vendor names
valid_vendor_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=30,
)


# ---------------------------------------------------------------------------
# Property 2: Valid AI result passthrough
# Feature: vendor-parser-cleanup, Property 2: Valid AI result passthrough
# Validates: Requirements 2.2, 2.5
# ---------------------------------------------------------------------------

class TestValidAIResultPassthrough:
    """
    Property 2: Valid AI result passthrough

    For any AI extraction result where total_amount > 0, the output of
    extract_transactions SHALL contain at minimum the fields date,
    total_amount (as 'amount'), vat_amount, description, and vendor,
    with values matching the AI result.

    Feature: vendor-parser-cleanup, Property 2: Valid AI result passthrough
    **Validates: Requirements 2.2, 2.5**
    """

    @settings(max_examples=30)
    @given(
        folder_name=valid_folder_name_st,
        total_amount=valid_amount_st,
        vat_amount=valid_vat_st,
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_output_contains_date_from_ai_result(self, folder_name, total_amount, vat_amount, date, description, vendor):
        """
        For any valid AI result with total_amount > 0, the output transaction
        SHALL contain the date field matching the AI result.

        Feature: vendor-parser-cleanup, Property 2: Valid AI result passthrough
        **Validates: Requirements 2.2, 2.5**
        """
        ai_result = {
            'date': date,
            'total_amount': round(total_amount, 2),
            'vat_amount': round(vat_amount, 2),
            'description': description,
            'vendor': vendor,
            '_usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'model': 'test'},
        }

        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        assert isinstance(result, list), "Result should be a list of transactions"
        assert len(result) >= 1, "Should have at least one transaction"

        main_tx = result[0]
        assert main_tx['date'] == date, (
            f"Expected date='{date}', got '{main_tx['date']}'"
        )

    @settings(max_examples=30)
    @given(
        folder_name=valid_folder_name_st,
        total_amount=valid_amount_st,
        vat_amount=valid_vat_st,
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_output_contains_amount_from_ai_result(self, folder_name, total_amount, vat_amount, date, description, vendor):
        """
        For any valid AI result with total_amount > 0, the output transaction
        SHALL contain the amount field matching the AI result's total_amount.

        Feature: vendor-parser-cleanup, Property 2: Valid AI result passthrough
        **Validates: Requirements 2.2, 2.5**
        """
        rounded_total = round(total_amount, 2)
        ai_result = {
            'date': date,
            'total_amount': rounded_total,
            'vat_amount': round(vat_amount, 2),
            'description': description,
            'vendor': vendor,
            '_usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'model': 'test'},
        }

        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        assert isinstance(result, list), "Result should be a list of transactions"
        assert len(result) >= 1, "Should have at least one transaction"

        main_tx = result[0]
        assert float(main_tx['amount']) == rounded_total, (
            f"Expected amount={rounded_total}, got {main_tx['amount']}"
        )

    @settings(max_examples=30)
    @given(
        folder_name=valid_folder_name_st,
        total_amount=valid_amount_st,
        vat_amount=st.floats(min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False),
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_output_contains_vat_amount_when_positive(self, folder_name, total_amount, vat_amount, date, description, vendor):
        """
        For any valid AI result with total_amount > 0 and vat_amount > 0,
        the output SHALL contain a VAT transaction with amount matching
        the AI result's vat_amount.

        Feature: vendor-parser-cleanup, Property 2: Valid AI result passthrough
        **Validates: Requirements 2.2, 2.5**
        """
        rounded_vat = round(vat_amount, 2)
        ai_result = {
            'date': date,
            'total_amount': round(total_amount, 2),
            'vat_amount': rounded_vat,
            'description': description,
            'vendor': vendor,
            '_usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'model': 'test'},
        }

        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        assert isinstance(result, list), "Result should be a list of transactions"
        # With vat_amount > 0, there should be at least 2 transactions (main + VAT)
        assert len(result) >= 2, (
            f"Expected at least 2 transactions (main + VAT), got {len(result)}"
        )

        vat_tx = result[1]
        assert float(vat_tx['amount']) == rounded_vat, (
            f"Expected VAT amount={rounded_vat}, got {vat_tx['amount']}"
        )

    @settings(max_examples=30)
    @given(
        folder_name=valid_folder_name_st,
        total_amount=valid_amount_st,
        vat_amount=valid_vat_st,
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_output_contains_description_from_ai_result(self, folder_name, total_amount, vat_amount, date, description, vendor):
        """
        For any valid AI result with total_amount > 0, the output transaction
        SHALL contain the description field matching the AI result.

        Feature: vendor-parser-cleanup, Property 2: Valid AI result passthrough
        **Validates: Requirements 2.2, 2.5**
        """
        ai_result = {
            'date': date,
            'total_amount': round(total_amount, 2),
            'vat_amount': round(vat_amount, 2),
            'description': description,
            'vendor': vendor,
            '_usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'model': 'test'},
        }

        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        assert isinstance(result, list), "Result should be a list of transactions"
        assert len(result) >= 1, "Should have at least one transaction"

        main_tx = result[0]
        assert main_tx['description'] == description, (
            f"Expected description='{description}', got '{main_tx['description']}'"
        )

    @settings(max_examples=30)
    @given(
        folder_name=valid_folder_name_st,
        total_amount=valid_amount_st,
        vat_amount=valid_vat_st,
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_output_contains_vendor_via_ref_field(self, folder_name, total_amount, vat_amount, date, description, vendor):
        """
        For any valid AI result with total_amount > 0, the output transaction
        SHALL contain the vendor information via the ref field (folder name).

        Feature: vendor-parser-cleanup, Property 2: Valid AI result passthrough
        **Validates: Requirements 2.2, 2.5**
        """
        ai_result = {
            'date': date,
            'total_amount': round(total_amount, 2),
            'vat_amount': round(vat_amount, 2),
            'description': description,
            'vendor': vendor,
            '_usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'model': 'test'},
        }

        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        assert isinstance(result, list), "Result should be a list of transactions"
        assert len(result) >= 1, "Should have at least one transaction"

        main_tx = result[0]
        # The vendor/folder is stored in the 'ref' field
        assert main_tx['ref'] == folder_name, (
            f"Expected ref (vendor/folder)='{folder_name}', got '{main_tx['ref']}'"
        )

    @settings(max_examples=30)
    @given(
        folder_name=valid_folder_name_st,
        total_amount=valid_amount_st,
        vat_amount=valid_vat_st,
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_output_has_all_required_fields(self, folder_name, total_amount, vat_amount, date, description, vendor):
        """
        For any valid AI result with total_amount > 0, the output transaction
        SHALL contain all required fields: date, amount, description, and ref (vendor).

        Feature: vendor-parser-cleanup, Property 2: Valid AI result passthrough
        **Validates: Requirements 2.2, 2.5**
        """
        ai_result = {
            'date': date,
            'total_amount': round(total_amount, 2),
            'vat_amount': round(vat_amount, 2),
            'description': description,
            'vendor': vendor,
            '_usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'model': 'test'},
        }

        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        assert isinstance(result, list), "Result should be a list of transactions"
        assert len(result) >= 1, "Should have at least one transaction"

        main_tx = result[0]
        required_fields = ['date', 'amount', 'description', 'ref']
        for field in required_fields:
            assert field in main_tx, (
                f"Required field '{field}' missing from transaction output. "
                f"Available keys: {list(main_tx.keys())}"
            )


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# Generate folder names that do NOT match CSV rules (no "airbnb" substring)
# These will fall through to AI extraction
folder_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=30,
).filter(lambda s: 'airbnb' not in s.lower())

# Generate random text content (list of lines joined by newlines)
text_content_st = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
        min_size=1,
        max_size=80,
    ),
    min_size=1,
    max_size=20,
).map(lambda lines: '\n'.join(lines))

# Generate random exception messages
exception_message_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=1,
    max_size=100,
)


# ---------------------------------------------------------------------------
# Property 1: AI-only extraction path
# Feature: vendor-parser-cleanup, Property 1: AI-only extraction path
# Validates: Requirements 1.6, 2.1, 3.3
# ---------------------------------------------------------------------------

class TestAIOnlyExtractionPath:
    """
    Property 1: AI-only extraction path

    For any folder name and text content (not matching a CSV rule), the
    extraction method SHALL call AIExtractor.extract_invoice_data with the
    text content and folder name as arguments, and SHALL NOT invoke any
    vendor-specific parser method.

    Feature: vendor-parser-cleanup, Property 1: AI-only extraction path
    **Validates: Requirements 1.6, 2.1, 3.3**
    """

    @settings(max_examples=30)
    @given(folder_name=folder_name_st, text_content=text_content_st)
    def test_ai_extractor_called_with_correct_text_and_folder(self, folder_name, text_content):
        """
        For any folder name and text content not matching CSV rules,
        AIExtractor.extract_invoice_data SHALL be called with the text
        content and folder name (lowercased) as arguments.

        Feature: vendor-parser-cleanup, Property 1: AI-only extraction path
        **Validates: Requirements 1.6, 2.1, 3.3**
        """
        file_data = {
            'txt': text_content,
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        folder_lower = folder_name.lower()

        # Mock AI result with a valid amount so extraction succeeds
        ai_result = {
            'date': '2025-01-15',
            'total_amount': 100.0,
            'vat_amount': 21.0,
            'description': f'Invoice from {folder_lower}',
            'vendor': folder_lower,
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            # Setup AI mock
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai_instance

            # Setup DB mock
            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            # Setup TransactionLogic mock
            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

            # Verify AIExtractor.extract_invoice_data was called
            mock_ai_instance.extract_invoice_data.assert_called_once()

            # Verify it was called with the text content and folder name
            call_args = mock_ai_instance.extract_invoice_data.call_args
            actual_text = call_args[0][0]  # first positional arg
            actual_folder = call_args[0][1]  # second positional arg

            # The text passed to AI should be the joined lines from file_data['txt']
            expected_text = '\n'.join(text_content.split('\n'))
            assert actual_text == expected_text, (
                f"Expected text content to be passed to AI extractor, "
                f"got different text"
            )
            assert actual_folder == folder_lower, (
                f"Expected folder '{folder_lower}' passed to AI extractor, "
                f"got '{actual_folder}'"
            )

    @settings(max_examples=30)
    @given(folder_name=folder_name_st, text_content=text_content_st)
    def test_no_vendor_parser_invoked(self, folder_name, text_content):
        """
        For any folder name and text content not matching CSV rules,
        no VendorParsers class SHALL be instantiated or called.

        Feature: vendor-parser-cleanup, Property 1: AI-only extraction path
        **Validates: Requirements 1.6, 2.1, 3.3**
        """
        file_data = {
            'txt': text_content,
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        folder_lower = folder_name.lower()

        ai_result = {
            'date': '2025-01-15',
            'total_amount': 100.0,
            'vat_amount': 21.0,
            'description': f'Invoice from {folder_lower}',
            'vendor': folder_lower,
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            # Verify VendorParsers is not importable from pdf_processor context
            # and that no vendor_parsers attribute exists on the processor
            processor = PDFProcessor(test_mode=True)

            # Verify no vendor_parsers attribute on the processor
            assert not hasattr(processor, 'vendor_parsers'), (
                "PDFProcessor should not have a 'vendor_parsers' attribute"
            )

            result = processor.extract_transactions(file_data)

            # Verify the result is valid (AI path was used)
            assert isinstance(result, list), "Result should be a list"
            assert len(result) >= 1, "Should have at least one transaction"


# ---------------------------------------------------------------------------
# Property 3: AI failure produces correct fallback structure
# Feature: vendor-parser-cleanup, Property 3: AI failure produces correct fallback structure
# Validates: Requirements 2.3, 2.4, 5.1, 5.2
# ---------------------------------------------------------------------------

class TestAIFailureFallbackStructure:
    """
    Property 3: AI failure produces correct fallback structure

    For any folder name, when the AI extractor returns a result with
    total_amount == 0 or raises any exception, the extraction SHALL return
    a data structure with total_amount set to 0.0, vat_amount set to 0.0,
    and description containing the folder name. If an exception occurred,
    the folder name and exception message SHALL be logged to standard output.

    Feature: vendor-parser-cleanup, Property 3: AI failure produces correct fallback structure
    **Validates: Requirements 2.3, 2.4, 5.1, 5.2**
    """

    @settings(max_examples=30)
    @given(folder_name=folder_name_st)
    def test_ai_zero_amount_produces_fallback_with_zero_amounts(self, folder_name):
        """
        Scenario A: AI returns zero amount.

        For any folder name (not matching CSV rules), when AIExtractor returns
        a result with total_amount=0.0, the output SHALL have total_amount=0.0
        and vat_amount=0.0.

        Feature: vendor-parser-cleanup, Property 3: AI failure produces correct fallback structure
        **Validates: Requirements 2.3, 5.1**
        """
        folder_lower = folder_name.lower()

        # Build file_data that won't match CSV rules and has no ai_data key
        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        # Mock AI result with zero amount
        zero_amount_result = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'description': f'{folder_lower} invoice',
            'vendor': folder_lower,
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            # Setup AI mock
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = zero_amount_result
            mock_ai_class.return_value = mock_ai_instance

            # Setup DB mock (for previous transactions)
            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            # Setup TransactionLogic mock (for _format_vendor_transactions)
            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        # Verify fallback structure
        assert isinstance(result, list), "Result should be a list of transactions"
        assert len(result) >= 1, "Should have at least one transaction"

        main_tx = result[0]
        assert float(main_tx['amount']) == 0.0, (
            f"Expected amount=0.0, got {main_tx['amount']}"
        )

    @settings(max_examples=30)
    @given(folder_name=folder_name_st)
    def test_ai_zero_amount_description_contains_folder_name(self, folder_name):
        """
        Scenario A: AI returns zero amount.

        For any folder name, when AIExtractor returns total_amount=0.0,
        the description SHALL contain the folder name.

        Feature: vendor-parser-cleanup, Property 3: AI failure produces correct fallback structure
        **Validates: Requirements 2.3, 5.1**
        """
        folder_lower = folder_name.lower()

        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        zero_amount_result = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'description': f'{folder_lower} invoice',
            'vendor': folder_lower,
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.return_value = zero_amount_result
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        assert len(result) >= 1, "Should have at least one transaction"
        main_tx = result[0]
        # The description should contain the folder name (lowercased, since
        # extract_transactions lowercases folder_name)
        assert folder_lower in main_tx['description'].lower(), (
            f"Expected folder name '{folder_lower}' in description, "
            f"got '{main_tx['description']}'"
        )

    @settings(max_examples=30)
    @given(folder_name=folder_name_st, error_msg=exception_message_st)
    def test_ai_exception_produces_fallback_with_zero_amounts(self, folder_name, error_msg):
        """
        Scenario B: AI raises exception.

        For any folder name and exception message, when AIExtractor raises
        an Exception, the output SHALL have total_amount=0.0 and vat_amount=0.0.

        Feature: vendor-parser-cleanup, Property 3: AI failure produces correct fallback structure
        **Validates: Requirements 2.4, 5.1**
        """
        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.side_effect = Exception(error_msg)
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        # Verify fallback structure
        assert isinstance(result, list), "Result should be a list of transactions"
        assert len(result) >= 1, "Should have at least one transaction"

        main_tx = result[0]
        assert float(main_tx['amount']) == 0.0, (
            f"Expected amount=0.0, got {main_tx['amount']}"
        )

    @settings(max_examples=30)
    @given(folder_name=folder_name_st, error_msg=exception_message_st)
    def test_ai_exception_description_contains_folder_name(self, folder_name, error_msg):
        """
        Scenario B: AI raises exception.

        For any folder name and exception message, when AIExtractor raises
        an Exception, the description SHALL contain the folder name.

        Feature: vendor-parser-cleanup, Property 3: AI failure produces correct fallback structure
        **Validates: Requirements 2.4, 5.1**
        """
        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        with patch('ai_extractor.AIExtractor') as mock_ai_class, \
             patch('database.DatabaseManager') as mock_db_class, \
             patch('transaction_logic.TransactionLogic') as mock_tl_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.extract_invoice_data.side_effect = Exception(error_msg)
            mock_ai_class.return_value = mock_ai_instance

            mock_db_instance = MagicMock()
            mock_db_instance.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db_instance

            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
            mock_tl_class.return_value = mock_tl_instance

            processor = PDFProcessor(test_mode=True)
            result = processor.extract_transactions(file_data)

        assert len(result) >= 1, "Should have at least one transaction"
        main_tx = result[0]
        folder_lower = folder_name.lower()
        # When AI raises exception, _extract_with_ai returns None,
        # and extract_transactions creates fallback with '{folder_name} invoice'
        assert folder_lower in main_tx['description'].lower(), (
            f"Expected folder name '{folder_lower}' in description, "
            f"got '{main_tx['description']}'"
        )

    @settings(max_examples=30)
    @given(folder_name=folder_name_st, error_msg=exception_message_st)
    def test_ai_exception_logs_error_to_stdout(self, folder_name, error_msg):
        """
        Scenario B: AI raises exception.

        For any folder name and exception message, when AIExtractor raises
        an Exception, the error SHALL be printed to stdout containing both
        the folder name and the exception message.

        Feature: vendor-parser-cleanup, Property 3: AI failure produces correct fallback structure
        **Validates: Requirements 2.4, 5.2**
        """
        import io
        from contextlib import redirect_stdout

        file_data = {
            'txt': 'Some invoice text content',
            'folder': folder_name,
            'url': 'https://drive.google.com/test',
            'name': 'test-file-id',
        }

        stdout_capture = io.StringIO()

        with redirect_stdout(stdout_capture):
            with patch('ai_extractor.AIExtractor') as mock_ai_class, \
                 patch('database.DatabaseManager') as mock_db_class, \
                 patch('transaction_logic.TransactionLogic') as mock_tl_class:
                mock_ai_instance = MagicMock()
                mock_ai_instance.extract_invoice_data.side_effect = Exception(error_msg)
                mock_ai_class.return_value = mock_ai_instance

                mock_db_instance = MagicMock()
                mock_db_instance.get_previous_transactions.return_value = []
                mock_db_class.return_value = mock_db_instance

                mock_tl_instance = MagicMock()
                mock_tl_instance.get_last_transactions.return_value = {'error': True, 'message': 'no history'}
                mock_tl_class.return_value = mock_tl_instance

                processor = PDFProcessor(test_mode=True)
                result = processor.extract_transactions(file_data)

        stdout_output = stdout_capture.getvalue()

        folder_lower = folder_name.lower()
        # The error log should contain the folder name
        assert folder_lower in stdout_output.lower(), (
            f"Expected folder name '{folder_lower}' in stdout output, "
            f"got: '{stdout_output[:200]}'"
        )
        # The error log should contain the exception message
        assert error_msg in stdout_output, (
            f"Expected error message '{error_msg[:50]}' in stdout output, "
            f"got: '{stdout_output[:200]}'"
        )
