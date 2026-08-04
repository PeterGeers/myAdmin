"""
Preservation Property Tests: Non-Zero VAT Amount Propagation Unchanged

These tests verify that the EXISTING (unfixed) code correctly handles non-zero
VAT amounts. This confirms baseline behavior that must be preserved after the fix.

Property 2: For all vendor_data with vat_amount > 0, the second prepared transaction
SHALL have TransactionAmount == vendor_data.vat_amount regardless of the template's
historical amount.

Additionally: Booking.com-specific fields (accommodation_name, commission_type,
invoice_number) correctly format descriptions and set Ref1/Ref2.

Validates: Requirements 3.1, 3.4, 3.5

EXPECTED OUTCOME: All tests PASS on unfixed code (confirms baseline behavior).
"""

import sys
import os

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from transaction_logic import TransactionLogic


class TestVatPreservationProperties:
    """Preservation: Non-zero VAT amounts propagate correctly through prepare_new_transactions."""

    @pytest.fixture
    def transaction_logic(self):
        """Create TransactionLogic instance for testing."""
        return TransactionLogic(test_mode=True)

    @pytest.fixture
    def base_template_transactions(self):
        """Template transactions with a historical BTW amount of 6.37."""
        return [
            {
                "ID": 201,
                "TransactionNumber": "BOOKING001",
                "TransactionDate": "2026-05-01",
                "TransactionDescription": "BOOKING001 invoice",
                "TransactionAmount": 50.00,
                "Debet": "4000",
                "Credit": "1300",
                "ReferenceNumber": "BOOKING001",
                "Administration": "TestAdmin",
            },
            {
                "ID": 202,
                "TransactionNumber": "BOOKING001",
                "TransactionDate": "2026-05-01",
                "TransactionDescription": "BOOKING001 invoice BTW",
                "TransactionAmount": 6.37,  # Historical stale VAT
                "Debet": "2010",
                "Credit": "4000",
                "ReferenceNumber": "BOOKING001",
                "Administration": "TestAdmin",
            },
        ]

    @pytest.fixture
    def base_new_data(self):
        """Base new_data structure for tests."""
        return {
            "folder_name": "BOOKING001",
            "description": "BOOKING001",
            "amount": 50.00,
            "drive_url": "https://drive.google.com/file/test",
            "filename": "invoice_2026_06.pdf",
            "administration": "TestAdmin",
        }

    # -------------------------------------------------------------------------
    # Property 2a: Non-zero VAT amounts propagate unchanged
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        "vat_amount,template_amount",
        [
            (19.85, 6.37),   # vat_amount: 19.85 overrides template 6.37
            (6.37, 6.37),    # vat_amount matches template (coincidence)
            (100.50, 6.37),  # vat_amount: 100.50 overrides template 6.37
            (0.01, 99.99),   # smallest non-zero vat overrides large template
            (250.00, 0.00),  # large vat with zero template
            (12.34, 56.78),  # arbitrary non-zero values
        ],
    )
    def test_nonzero_vat_amount_overrides_template(
        self, transaction_logic, base_template_transactions, base_new_data,
        vat_amount, template_amount
    ):
        """
        Property: For all vat_amount > 0 in vendor_data, the second prepared
        transaction SHALL have TransactionAmount == vendor_data.vat_amount
        regardless of the template's historical amount.

        Validates: Requirements 3.1
        """
        # Set up template with the specified historical amount
        base_template_transactions[1]["TransactionAmount"] = template_amount

        # Set up vendor_data with explicit non-zero vat_amount
        base_new_data["vendor_data"] = {
            "date": "2026-06-15",
            "total_amount": 50.00,
            "description": "BOOKING001",
            "vat_amount": vat_amount,
        }

        # Act
        result = transaction_logic.prepare_new_transactions(
            base_template_transactions, base_new_data
        )

        # Assert: BTW record uses vendor_data.vat_amount, not template amount
        assert len(result) == 2, f"Expected 2 transactions, got {len(result)}"
        btw_transaction = result[1]
        assert btw_transaction["TransactionAmount"] == vat_amount, (
            f"BTW transaction amount should be {vat_amount} (from vendor_data), "
            f"but got {btw_transaction['TransactionAmount']}. "
            f"Template amount was {template_amount}."
        )

    # -------------------------------------------------------------------------
    # Property 2b: Debet/Credit account assignments preserved
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        "vat_amount",
        [19.85, 6.37, 100.50, 0.01, 250.00],
    )
    def test_debet_credit_preserved_for_nonzero_vat(
        self, transaction_logic, base_template_transactions, base_new_data,
        vat_amount
    ):
        """
        Property: When vendor_data contains non-zero vat_amount, the template's
        Debet/Credit account assignments are preserved in the result.

        Validates: Requirements 3.4
        """
        base_new_data["vendor_data"] = {
            "date": "2026-06-15",
            "total_amount": 50.00,
            "description": "BOOKING001",
            "vat_amount": vat_amount,
        }

        # Act
        result = transaction_logic.prepare_new_transactions(
            base_template_transactions, base_new_data
        )

        # Assert: First transaction preserves template Debet/Credit
        assert result[0]["Debet"] == "4000"
        assert result[0]["Credit"] == "1300"

        # Assert: Second (BTW) transaction preserves template Debet/Credit
        assert result[1]["Debet"] == "2010"
        assert result[1]["Credit"] == "4000"

    # -------------------------------------------------------------------------
    # Property 2c: Booking.com description formatting and Ref1/Ref2 assignment
    # -------------------------------------------------------------------------

    def test_booking_description_formatting_with_commission_type(
        self, transaction_logic, base_template_transactions, base_new_data
    ):
        """
        Property: When vendor_data has accommodation_name, commission_type,
        and invoice_number, the description is formatted as:
        '{accommodation_name} {invoice_number} {commission_type} {date} BTW'
        and Ref1 = accommodation_name, Ref2 = invoice_number.

        Validates: Requirements 3.5
        """
        base_new_data["vendor_data"] = {
            "date": "2026-06-15",
            "total_amount": 120.00,
            "vat_amount": 19.85,
            "description": "BOOKING001",
            "accommodation_name": "Villa Sunset",
            "commission_type": "Commission",
            "invoice_number": "INV-2026-001",
        }

        # Act
        result = transaction_logic.prepare_new_transactions(
            base_template_transactions, base_new_data
        )

        # Assert: Ref1 is accommodation_name
        assert result[0]["Ref1"] == "Villa Sunset"
        assert result[1]["Ref1"] == "Villa Sunset"

        # Assert: Ref2 is invoice_number
        assert result[0]["Ref2"] == "INV-2026-001"
        assert result[1]["Ref2"] == "INV-2026-001"

        # Assert: Description includes all Booking.com fields for BTW record
        btw_description = result[1]["TransactionDescription"]
        assert "Villa Sunset" in btw_description
        assert "INV-2026-001" in btw_description
        assert "Commission" in btw_description
        assert "2026-06-15" in btw_description
        assert "BTW" in btw_description

        # Assert: First transaction description also formatted
        main_description = result[0]["TransactionDescription"]
        assert "Villa Sunset" in main_description
        assert "INV-2026-001" in main_description
        assert "Commission" in main_description
        assert "2026-06-15" in main_description
        assert "BTW" not in main_description

    def test_booking_ref1_uses_accommodation_number_fallback(
        self, transaction_logic, base_template_transactions, base_new_data
    ):
        """
        Property: When vendor_data has accommodation_number but not
        accommodation_name, Ref1 is formatted as 'Accommodation {number}'.

        Validates: Requirements 3.5
        """
        base_new_data["vendor_data"] = {
            "date": "2026-06-15",
            "total_amount": 80.00,
            "vat_amount": 12.50,
            "description": "BOOKING001",
            "accommodation_number": "12345",
            "invoice_number": "INV-2026-002",
        }

        # Act
        result = transaction_logic.prepare_new_transactions(
            base_template_transactions, base_new_data
        )

        # Assert: Ref1 uses accommodation_number fallback format
        assert result[0]["Ref1"] == "Accommodation 12345"
        assert result[1]["Ref1"] == "Accommodation 12345"

        # Assert: Ref2 is still invoice_number
        assert result[0]["Ref2"] == "INV-2026-002"
        assert result[1]["Ref2"] == "INV-2026-002"

    def test_booking_ref2_not_set_for_amazon(
        self, transaction_logic, base_template_transactions, base_new_data
    ):
        """
        Property: When folder_name is 'amazon' (case-insensitive), Ref2 is NOT
        set even if invoice_number is present.

        Validates: Requirements 3.5
        """
        base_new_data["folder_name"] = "Amazon"
        base_new_data["vendor_data"] = {
            "date": "2026-06-15",
            "total_amount": 45.00,
            "vat_amount": 7.50,
            "description": "Amazon",
            "accommodation_name": "Villa Test",
            "invoice_number": "AMZ-2026-001",
        }

        # Act
        result = transaction_logic.prepare_new_transactions(
            base_template_transactions, base_new_data
        )

        # Assert: Ref2 is None for Amazon
        assert result[0]["Ref2"] is None
        assert result[1]["Ref2"] is None

        # Assert: Ref1 is still set
        assert result[0]["Ref1"] == "Villa Test"

    @pytest.mark.parametrize(
        "accommodation_name,commission_type,invoice_number,vat_amount",
        [
            ("Beach House", "Commission", "BK-001", 15.00),
            ("Mountain Lodge", "Adjustment", "BK-002", 25.50),
            ("City Apartment", "Commission", "BK-003", 3.21),
        ],
    )
    def test_booking_fields_preserved_across_various_inputs(
        self, transaction_logic, base_template_transactions, base_new_data,
        accommodation_name, commission_type, invoice_number, vat_amount
    ):
        """
        Property: For all vendor_data with booking-specific fields,
        description formatting and Ref1/Ref2 assignment remain unchanged.

        Validates: Requirements 3.5
        """
        base_new_data["vendor_data"] = {
            "date": "2026-07-01",
            "total_amount": 200.00,
            "vat_amount": vat_amount,
            "description": "BOOKING001",
            "accommodation_name": accommodation_name,
            "commission_type": commission_type,
            "invoice_number": invoice_number,
        }

        # Act
        result = transaction_logic.prepare_new_transactions(
            base_template_transactions, base_new_data
        )

        # Assert: VAT amount from vendor_data
        assert result[1]["TransactionAmount"] == vat_amount

        # Assert: Ref1 = accommodation_name
        assert result[0]["Ref1"] == accommodation_name
        assert result[1]["Ref1"] == accommodation_name

        # Assert: Ref2 = invoice_number
        assert result[0]["Ref2"] == invoice_number
        assert result[1]["Ref2"] == invoice_number

        # Assert: BTW description contains all booking fields
        btw_desc = result[1]["TransactionDescription"]
        assert accommodation_name in btw_desc
        assert invoice_number in btw_desc
        assert commission_type in btw_desc
        assert "BTW" in btw_desc

        # Assert: Account assignments from template preserved
        assert result[1]["Debet"] == "2010"
        assert result[1]["Credit"] == "4000"
