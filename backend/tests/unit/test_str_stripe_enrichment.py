"""
Unit tests for str_stripe_enrichment.py — Stripe enrichment module for dfDirect bookings.

Tests cover:
- 3-stage fallback logic (_lookup_payment)
- _extract_customer_data with various data availability scenarios
- enrich_direct_bookings orchestration (API key check, success, errors, rate limiting)
- Amount search ambiguity handling
"""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from str_stripe_enrichment import (
    enrich_direct_bookings,
    _lookup_payment,
    _search_by_metadata,
    _search_by_description,
    _search_by_amount,
    _extract_customer_data,
)


# ---------------------------------------------------------------------------
# Helper: create a mock PaymentIntent
# ---------------------------------------------------------------------------
def _make_mock_pi(
    receipt_email=None,
    customer=None,
    payment_method=None,
    latest_charge=None,
    shipping=None,
):
    """Create a mock PaymentIntent with configurable fields.

    shipping must be explicitly provided (as a MagicMock with phone/address set)
    or left as None to prevent MagicMock auto-attribute creation.
    """
    pi = MagicMock()
    pi.receipt_email = receipt_email
    pi.customer = customer
    pi.payment_method = payment_method
    pi.latest_charge = latest_charge
    pi.shipping = shipping
    return pi


# ===========================================================================
# 3-stage fallback tests
# ===========================================================================
class TestLookupPaymentFallback:
    """Test the 3-stage fallback logic in _lookup_payment."""

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_metadata_found_first(self, mock_meta, mock_desc, mock_amount):
        """When metadata search returns result, description/amount are never called."""
        mock_meta.return_value = {"email": "guest@example.com", "phone": None, "country": None, "stripe_fee": None}

        result = _lookup_payment("GY-ABC123", amount_eur=150.0)

        assert result == {"email": "guest@example.com", "phone": None, "country": None, "stripe_fee": None}
        mock_meta.assert_called_once_with("GY-ABC123")
        mock_desc.assert_not_called()
        mock_amount.assert_not_called()

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_description_fallback(self, mock_meta, mock_desc, mock_amount):
        """When metadata returns nothing, description search succeeds."""
        mock_meta.return_value = None
        mock_desc.return_value = {"email": "found@desc.com", "phone": "+31612345678", "country": "NL", "stripe_fee": None}

        result = _lookup_payment("GY-DEF456", amount_eur=200.0)

        assert result == {"email": "found@desc.com", "phone": "+31612345678", "country": "NL", "stripe_fee": None}
        mock_meta.assert_called_once_with("GY-DEF456")
        mock_desc.assert_called_once_with("GY-DEF456")
        mock_amount.assert_not_called()

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_amount_fallback(self, mock_meta, mock_desc, mock_amount):
        """When metadata + description return nothing, amount search succeeds."""
        mock_meta.return_value = None
        mock_desc.return_value = None
        mock_amount.return_value = {"email": "amount@find.com", "phone": None, "country": "DE", "stripe_fee": 2.50}

        result = _lookup_payment("GY-GHI789", amount_eur=350.0)

        assert result == {"email": "amount@find.com", "phone": None, "country": "DE", "stripe_fee": 2.50}
        mock_meta.assert_called_once_with("GY-GHI789")
        mock_desc.assert_called_once_with("GY-GHI789")
        mock_amount.assert_called_once_with(350.0)

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_not_found_all_stages(self, mock_meta, mock_desc, mock_amount):
        """All 3 stages return nothing → None."""
        mock_meta.return_value = None
        mock_desc.return_value = None
        mock_amount.return_value = None

        result = _lookup_payment("GY-NOTFOUND", amount_eur=100.0)

        assert result is None
        mock_meta.assert_called_once()
        mock_desc.assert_called_once()
        mock_amount.assert_called_once()


# ===========================================================================
# _extract_customer_data tests
# ===========================================================================
class TestExtractCustomerData:
    """Test _extract_customer_data with various data availability scenarios."""

    @patch('str_stripe_enrichment.stripe')
    def test_extract_all_data_available(self, mock_stripe):
        """All sources present: receipt_email, customer, payment_method, balance_transaction."""
        # Build a shipping mock with phone and address.country
        mock_shipping = MagicMock()
        mock_shipping.phone = "+31687654321"
        mock_shipping.address.country = "NL"

        pi = _make_mock_pi(
            receipt_email="guest@direct.com",
            customer="cus_123",
            payment_method="pm_456",
            latest_charge="ch_789",
            shipping=mock_shipping,
        )

        # Mock Customer.retrieve
        mock_customer = MagicMock()
        mock_customer.email = "customer@stripe.com"
        mock_customer.phone = "+31687654321"
        mock_stripe.Customer.retrieve.return_value = mock_customer

        # Mock PaymentMethod.retrieve
        mock_pm = MagicMock()
        mock_pm.billing_details.phone = "+31699999999"
        mock_pm.billing_details.email = "billing@stripe.com"
        mock_pm.billing_details.address.country = "NL"
        mock_stripe.PaymentMethod.retrieve.return_value = mock_pm

        # Mock Charge.retrieve with balance_transaction
        mock_charge = MagicMock()
        mock_charge.balance_transaction.fee = 325  # €3.25 in cents
        mock_stripe.Charge.retrieve.return_value = mock_charge

        result = _extract_customer_data(pi)

        # receipt_email takes priority for email
        assert result["email"] == "guest@direct.com"
        # Customer phone takes priority
        assert result["phone"] == "+31687654321"
        # Country from billing_details
        assert result["country"] == "NL"
        # Stripe fee converted from cents to euros
        assert result["stripe_fee"] == 3.25

    @patch('str_stripe_enrichment.stripe')
    def test_extract_no_customer(self, mock_stripe):
        """Only receipt_email available, no customer or payment_method."""
        pi = _make_mock_pi(
            receipt_email="only@email.com",
            customer=None,
            payment_method=None,
            latest_charge=None,
        )

        result = _extract_customer_data(pi)

        assert result["email"] == "only@email.com"
        assert result["phone"] is None
        assert result["country"] is None
        assert result["stripe_fee"] is None
        mock_stripe.Customer.retrieve.assert_not_called()
        mock_stripe.PaymentMethod.retrieve.assert_not_called()

    @patch('str_stripe_enrichment.stripe')
    def test_extract_country_from_billing(self, mock_stripe):
        """Country extracted from PaymentMethod billing_details address."""
        pi = _make_mock_pi(
            receipt_email=None,
            customer=None,
            payment_method="pm_billing",
            latest_charge=None,
        )

        mock_pm = MagicMock()
        mock_pm.billing_details.phone = None
        mock_pm.billing_details.email = "billing@test.de"
        mock_pm.billing_details.address.country = "DE"
        mock_stripe.PaymentMethod.retrieve.return_value = mock_pm

        result = _extract_customer_data(pi)

        assert result["country"] == "DE"
        # email from billing_details (no receipt_email)
        assert result["email"] == "billing@test.de"
        assert result["phone"] is None
        assert result["stripe_fee"] is None

    @patch('str_stripe_enrichment.stripe')
    def test_extract_stripe_fee(self, mock_stripe):
        """Stripe fee extracted from Charge balance_transaction, converted from cents to euros."""
        pi = _make_mock_pi(
            receipt_email=None,
            customer=None,
            payment_method=None,
            latest_charge="ch_fee_test",
        )

        mock_charge = MagicMock()
        mock_charge.balance_transaction.fee = 450  # €4.50
        mock_stripe.Charge.retrieve.return_value = mock_charge

        result = _extract_customer_data(pi)

        assert result["stripe_fee"] == 4.50
        assert result["email"] is None
        assert result["phone"] is None
        assert result["country"] is None

    @patch('str_stripe_enrichment.stripe')
    def test_extract_no_data(self, mock_stripe):
        """Everything is None/empty — all fields return None."""
        pi = _make_mock_pi(
            receipt_email=None,
            customer=None,
            payment_method=None,
            latest_charge=None,
        )

        result = _extract_customer_data(pi)

        assert result == {"email": None, "phone": None, "country": None, "stripe_fee": None}


# ===========================================================================
# enrich_direct_bookings tests
# ===========================================================================
class TestEnrichDirectBookings:
    """Test the main enrich_direct_bookings function."""

    @patch.dict(os.environ, {}, clear=True)
    def test_no_api_key_returns_not_found(self):
        """When STRIPE_SECRET_KEY is not set, all codes go to not_found."""
        # Ensure no STRIPE_SECRET_KEY in env
        os.environ.pop("STRIPE_SECRET_KEY", None)

        codes = ["GY-CODE1", "GY-CODE2", "GY-CODE3"]
        result = enrich_direct_bookings(codes)

        assert result["enrichments"] == []
        assert result["not_found"] == codes
        assert "STRIPE_SECRET_KEY not configured" in result["errors"]

    @patch('str_stripe_enrichment.time.sleep')
    @patch('str_stripe_enrichment._lookup_payment')
    @patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_123"})
    def test_enrichment_success(self, mock_lookup, mock_sleep):
        """1 code found → enrichment dict includes reservationCode."""
        mock_lookup.return_value = {
            "email": "guest@found.com",
            "phone": "+4917612345",
            "country": "DE",
            "stripe_fee": 2.75,
        }

        result = enrich_direct_bookings(["GY-FOUND1"])

        assert len(result["enrichments"]) == 1
        enrichment = result["enrichments"][0]
        assert enrichment["reservationCode"] == "GY-FOUND1"
        assert enrichment["email"] == "guest@found.com"
        assert enrichment["phone"] == "+4917612345"
        assert enrichment["country"] == "DE"
        assert enrichment["stripe_fee"] == 2.75
        assert result["not_found"] == []
        assert result["errors"] == []

    @patch('str_stripe_enrichment.time.sleep')
    @patch('str_stripe_enrichment._lookup_payment')
    @patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_123"})
    def test_stripe_error_goes_to_errors(self, mock_lookup, mock_sleep):
        """StripeError → code goes to errors list."""
        import stripe as stripe_mod
        mock_lookup.side_effect = stripe_mod.error.StripeError("Rate limit exceeded")

        result = enrich_direct_bookings(["GY-ERROR1"])

        assert result["enrichments"] == []
        assert result["not_found"] == []
        assert len(result["errors"]) == 1
        assert "GY-ERROR1" in result["errors"][0]
        assert "Rate limit exceeded" in result["errors"][0]

    @patch('str_stripe_enrichment._lookup_payment')
    @patch('str_stripe_enrichment.time.sleep')
    @patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_123"})
    def test_rate_limiting(self, mock_sleep, mock_lookup):
        """Verify time.sleep(0.05) is called between iterations."""
        mock_lookup.return_value = None  # All not found

        codes = ["GY-A", "GY-B", "GY-C"]
        enrich_direct_bookings(codes)

        # time.sleep should be called once per code
        assert mock_sleep.call_count == 3
        mock_sleep.assert_called_with(0.05)


# ===========================================================================
# Amount search specific tests
# ===========================================================================
class TestAmountSearch:
    """Test _search_by_amount edge cases."""

    @patch('str_stripe_enrichment.stripe')
    def test_amount_search_single_match(self, mock_stripe):
        """1 result → returns extracted data."""
        pi = _make_mock_pi(receipt_email="single@match.com")

        mock_result = MagicMock()
        mock_result.data = [pi]
        mock_stripe.PaymentIntent.search.return_value = mock_result

        # Also need to mock that no customer/pm/charge calls happen
        # since pi has no customer/payment_method/latest_charge
        result = _search_by_amount(150.0)

        assert result is not None
        assert result["email"] == "single@match.com"
        # Verify search was called with correct amount in cents
        mock_stripe.PaymentIntent.search.assert_called_once_with(
            query='amount:15000 AND status:"succeeded"',
            limit=3,
        )

    @patch('str_stripe_enrichment.stripe')
    def test_amount_search_multiple_matches_skipped(self, mock_stripe):
        """2+ results → returns None (ambiguous)."""
        pi1 = _make_mock_pi(receipt_email="one@match.com")
        pi2 = _make_mock_pi(receipt_email="two@match.com")

        mock_result = MagicMock()
        mock_result.data = [pi1, pi2]
        mock_stripe.PaymentIntent.search.return_value = mock_result

        result = _search_by_amount(200.0)

        assert result is None
