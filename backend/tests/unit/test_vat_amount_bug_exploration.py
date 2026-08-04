"""
Bug Condition Exploration Test: VAT Amount Ignored When Zero (Template Fallback)

This test confirms the bug described in the bugfix spec:
When vendor_data does NOT contain the 'vat_amount' key (because invoice_service.py
only sets it when a VAT line exists in the formatted transactions), the
prepare_new_transactions method falls back to the template's historical
TransactionAmount for the BTW record — using a stale value instead of 0.0.

Validates: Requirements 1.1, 1.2, 1.3

EXPECTED: This test FAILS on unfixed code (proving the bug exists).
The BTW record gets 6.37 from the template instead of 0.0.
"""

import sys
import os

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from transaction_logic import TransactionLogic


class TestVatAmountBugExploration:
    """Bug condition exploration: VAT amount ignored when zero (template fallback)."""

    @pytest.fixture
    def transaction_logic(self):
        """Create TransactionLogic instance for testing."""
        return TransactionLogic(test_mode=True)

    def test_prepare_new_transactions_uses_zero_vat_when_key_missing(
        self, transaction_logic
    ):
        """
        Bug Condition Property:
        GIVEN template_transactions with a second BTW record having TransactionAmount 6.37
        AND vendor_data does NOT contain 'vat_amount' key
            (simulating the omission in invoice_service.py when no VAT transaction exists)
        WHEN prepare_new_transactions is called
        THEN the second prepared transaction SHALL have TransactionAmount == 0.0
            (expected correct behavior: no VAT means zero amount)

        ON UNFIXED CODE: This test FAILS because the code falls back to
        template.get("TransactionAmount", 0) which is 6.37 — the stale historical value.

        Validates: Requirements 1.1, 1.2, 1.3
        """
        # Template transactions simulating a vendor with historical BTW of 6.37
        template_transactions = [
            {
                "ID": 101,
                "TransactionNumber": "SV2SU1ZT0006",
                "TransactionDate": "2026-06-15",
                "TransactionDescription": "SV2SU1ZT0006 invoice",
                "TransactionAmount": 6.52,
                "Debet": "4000",
                "Credit": "1300",
                "ReferenceNumber": "SV2SU1ZT0006",
                "Administration": "TestAdmin",
            },
            {
                "ID": 102,
                "TransactionNumber": "SV2SU1ZT0006",
                "TransactionDate": "2026-06-15",
                "TransactionDescription": "SV2SU1ZT0006 invoice BTW",
                "TransactionAmount": 6.37,  # Historical stale VAT amount
                "Debet": "2010",
                "Credit": "4000",
                "ReferenceNumber": "SV2SU1ZT0006",
                "Administration": "TestAdmin",
            },
        ]

        # vendor_data WITHOUT 'vat_amount' key — simulates the bug in invoice_service.py
        # when AI extraction returns vat_amount: 0.0 but no VAT transaction exists
        # in the formatted list, so the key is never set
        new_data = {
            "folder_name": "SV2SU1ZT0006",
            "description": "SV2SU1ZT0006",
            "amount": 6.52,
            "drive_url": "https://drive.google.com/file/test",
            "filename": "invoice_2026_07.pdf",
            "vendor_data": {
                "date": "2026-07-10",
                "total_amount": 6.52,
                "description": "SV2SU1ZT0006",
                # NOTE: 'vat_amount' key is intentionally MISSING
                # This is the bug condition — invoice_service.py doesn't set it
                # when there's no VAT line in the formatted transactions
            },
            "administration": "TestAdmin",
        }

        # Act
        result = transaction_logic.prepare_new_transactions(
            template_transactions, new_data
        )

        # Assert: The second transaction (BTW) should have amount 0.0
        # because no VAT was parsed from the invoice.
        # ON UNFIXED CODE: This will be 6.37 (from template) instead of 0.0
        assert len(result) == 2, f"Expected 2 transactions, got {len(result)}"

        btw_transaction = result[1]
        assert btw_transaction["TransactionAmount"] == 0.0, (
            f"Bug confirmed: BTW transaction amount is "
            f"{btw_transaction['TransactionAmount']} (from stale template) "
            f"instead of 0.0 (expected correct behavior). "
            f"The system used the template's historical VAT amount instead of "
            f"recognizing that no VAT was parsed for this invoice."
        )
