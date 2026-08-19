"""
Preservation Property Tests — Stripe Enrichment Logic Unchanged

Property 2: Preservation — Enrichment Logic Unchanged

These tests observe and document the CURRENT (unfixed) behavior to ensure that
when we refactor for per-tenant credential isolation, the core enrichment logic
is preserved:
- 3-stage lookup order (metadata -> description -> amount)
- _extract_customer_data priority order
- Error handling (StripeError -> errors array)
- Rate limiting (time.sleep between iterations)
- Return structure {enrichments, not_found, errors}

These tests MUST PASS on the unfixed code (baseline) AND after the fix (preservation).
"""
import os
import sys
from unittest.mock import patch, MagicMock, call

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


def _make_mock_pi(
    receipt_email=None,
    customer=None,
    payment_method=None,
    latest_charge=None,
    shipping=None,
):
    """Create a mock PaymentIntent with configurable fields."""
    pi = MagicMock()
    pi.receipt_email = receipt_email
    pi.customer = customer
    pi.payment_method = payment_method
    pi.latest_charge = latest_charge
    pi.shipping = shipping
    return pi


class TestPreservation_LookupOrder:
    """Property 2a: The 3-stage lookup order is preserved."""

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_metadata_hit_short_circuits(self, mock_meta, mock_desc, mock_amount):
        """When metadata returns data, description and amount are never called."""
        mock_meta.return_value = {"email": "m@test.com", "phone": None, "country": None, "stripe_fee": None}
        result = _lookup_payment("GY-META", amount_eur=100.0, api_key="sk_test", metadata_key="confirmationCode")
        assert result is not None
        assert result["email"] == "m@test.com"
        mock_meta.assert_called_once_with("GY-META", api_key="sk_test", metadata_key="confirmationCode")
        mock_desc.assert_not_called()
        mock_amount.assert_not_called()

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_description_hit_short_circuits_amount(self, mock_meta, mock_desc, mock_amount):
        """When metadata misses but description hits, amount is never called."""
        mock_meta.return_value = None
        mock_desc.return_value = {"email": "d@test.com", "phone": "+31600000000", "country": "NL", "stripe_fee": None}
        result = _lookup_payment("GY-DESC", amount_eur=200.0, api_key="sk_test", metadata_key="confirmationCode")
        assert result is not None
        assert result["email"] == "d@test.com"
        mock_meta.assert_called_once_with("GY-DESC", api_key="sk_test", metadata_key="confirmationCode")
        mock_desc.assert_called_once_with("GY-DESC", api_key="sk_test")
        mock_amount.assert_not_called()

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_all_miss_returns_none(self, mock_meta, mock_desc, mock_amount):
        """All 3 stages miss -> None returned."""
        mock_meta.return_value = None
        mock_desc.return_value = None
        mock_amount.return_value = None
        result = _lookup_payment("GY-MISS", amount_eur=300.0, api_key="sk_test", metadata_key="confirmationCode")
        assert result is None
        mock_meta.assert_called_once()
        mock_desc.assert_called_once()
        mock_amount.assert_called_once_with(300.0, api_key="sk_test")

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_amount_not_called_when_no_amount(self, mock_meta, mock_desc, mock_amount):
        """Amount search skipped when amount_eur is None."""
        mock_meta.return_value = None
        mock_desc.return_value = None
        result = _lookup_payment("GY-NOAMT", amount_eur=None, api_key="sk_test", metadata_key="confirmationCode")
        assert result is None
        mock_amount.assert_not_called()

    @patch('str_stripe_enrichment._search_by_amount')
    @patch('str_stripe_enrichment._search_by_description')
    @patch('str_stripe_enrichment._search_by_metadata')
    def test_amount_not_called_when_zero(self, mock_meta, mock_desc, mock_amount):
        """Amount search skipped when amount_eur is 0."""
        mock_meta.return_value = None
        mock_desc.return_value = None
        result = _lookup_payment("GY-ZERO", amount_eur=0, api_key="sk_test", metadata_key="confirmationCode")
        assert result is None
        mock_amount.assert_not_called()


class TestPreservation_ExtractPriority:
    """Property 2b: _extract_customer_data follows priority order."""

    @patch('str_stripe_enrichment.stripe')
    def test_shipping_phone_takes_priority(self, mock_stripe):
        """Shipping phone used even when customer phone exists."""
        mock_shipping = MagicMock()
        mock_shipping.phone = "+31611111111"
        mock_shipping.address.country = "NL"
        pi = _make_mock_pi(
            receipt_email="r@test.com",
            customer="cus_1",
            shipping=mock_shipping,
        )
        mock_customer = MagicMock()
        mock_customer.email = "c@test.com"
        mock_customer.phone = "+31622222222"
        mock_stripe.Customer.retrieve.return_value = mock_customer
        result = _extract_customer_data(pi)
        assert result["phone"] == "+31611111111"
        assert result["country"] == "NL"
        assert result["email"] == "r@test.com"

    @patch('str_stripe_enrichment.stripe')
    def test_receipt_email_priority_over_customer(self, mock_stripe):
        """receipt_email used over Customer.email."""
        pi = _make_mock_pi(
            receipt_email="receipt@priority.com",
            customer="cus_2",
            payment_method=None,
            latest_charge=None,
        )
        mock_customer = MagicMock()
        mock_customer.email = "customer@fallback.com"
        mock_customer.phone = None
        mock_stripe.Customer.retrieve.return_value = mock_customer
        result = _extract_customer_data(pi)
        assert result["email"] == "receipt@priority.com"

    @patch('str_stripe_enrichment.stripe')
    def test_customer_email_fallback(self, mock_stripe):
        """When no receipt_email, Customer.email is used."""
        pi = _make_mock_pi(
            receipt_email=None,
            customer="cus_3",
            payment_method=None,
            latest_charge=None,
        )
        mock_customer = MagicMock()
        mock_customer.email = "customer@fallback.com"
        mock_customer.phone = "+4917612345678"
        mock_stripe.Customer.retrieve.return_value = mock_customer
        result = _extract_customer_data(pi)
        assert result["email"] == "customer@fallback.com"
        assert result["phone"] == "+4917612345678"

    @patch('str_stripe_enrichment.stripe')
    def test_stripe_fee_extraction(self, mock_stripe):
        """Stripe fee extracted from balance_transaction.fee (cents to euros)."""
        pi = _make_mock_pi(
            receipt_email=None,
            customer=None,
            payment_method=None,
            latest_charge="ch_fee",
        )
        mock_charge = MagicMock()
        mock_charge.balance_transaction.fee = 275
        mock_stripe.Charge.retrieve.return_value = mock_charge
        result = _extract_customer_data(pi)
        assert result["stripe_fee"] == 2.75

    @patch('str_stripe_enrichment.stripe')
    def test_all_none_returns_empty_structure(self, mock_stripe):
        """When all sources are None, returns dict with all None values."""
        pi = _make_mock_pi()
        result = _extract_customer_data(pi)
        assert result == {"email": None, "phone": None, "country": None, "stripe_fee": None}


class TestPreservation_ErrorHandling:
    """Property 2c: StripeError on individual codes goes to errors array."""

    @patch('str_stripe_enrichment.time.sleep')
    @patch('str_stripe_enrichment._lookup_payment')
    def test_stripe_error_captured_in_errors_array(self, mock_lookup, mock_sleep):
        """StripeError on a code puts it in errors, does not crash the batch."""
        import stripe as stripe_mod
        mock_lookup.side_effect = stripe_mod.error.StripeError("API error")
        result = enrich_direct_bookings(["GY-ERR1", "GY-ERR2"], api_key="sk_test_preserve")
        assert result["enrichments"] == []
        assert result["not_found"] == []
        assert len(result["errors"]) == 2
        assert "GY-ERR1" in result["errors"][0]
        assert "GY-ERR2" in result["errors"][1]

    @patch('str_stripe_enrichment.time.sleep')
    @patch('str_stripe_enrichment._lookup_payment')
    def test_mixed_results_partitioned_correctly(self, mock_lookup, mock_sleep):
        """Mix of found, not-found, and error codes partitioned correctly."""
        import stripe as stripe_mod

        def side_effect(code, amount, api_key="", metadata_key="confirmationCode"):
            if code == "GY-FOUND":
                return {"email": "f@t.com", "phone": None, "country": None, "stripe_fee": None}
            elif code == "GY-ERR":
                raise stripe_mod.error.StripeError("Timeout")
            else:
                return None

        mock_lookup.side_effect = side_effect
        result = enrich_direct_bookings(
            ["GY-FOUND", "GY-MISS", "GY-ERR"],
            amounts={"GY-FOUND": 100, "GY-MISS": 200, "GY-ERR": 300},
            api_key="sk_test_preserve",
        )
        assert len(result["enrichments"]) == 1
        assert result["enrichments"][0]["reservationCode"] == "GY-FOUND"
        assert result["not_found"] == ["GY-MISS"]
        assert len(result["errors"]) == 1
        assert "GY-ERR" in result["errors"][0]


class TestPreservation_RateLimiting:
    """Property 2d: time.sleep(0.05) called between each iteration."""

    @patch('str_stripe_enrichment._lookup_payment')
    @patch('str_stripe_enrichment.time.sleep')
    def test_sleep_called_per_code(self, mock_sleep, mock_lookup):
        """time.sleep(0.05) called once per reservation code."""
        mock_lookup.return_value = None
        enrich_direct_bookings(["GY-A", "GY-B", "GY-C", "GY-D"], api_key="sk_test_rate")
        assert mock_sleep.call_count == 4
        mock_sleep.assert_called_with(0.05)


class TestPreservation_ReturnStructure:
    """Property 2e: Return structure is always {enrichments, not_found, errors}."""

    @patch('str_stripe_enrichment.time.sleep')
    @patch('str_stripe_enrichment._lookup_payment')
    def test_return_has_three_keys(self, mock_lookup, mock_sleep):
        """Result always has exactly enrichments, not_found, errors keys."""
        mock_lookup.return_value = None
        result = enrich_direct_bookings(["GY-X"], api_key="sk_test_struct")
        assert set(result.keys()) == {"enrichments", "not_found", "errors"}
        assert isinstance(result["enrichments"], list)
        assert isinstance(result["not_found"], list)
        assert isinstance(result["errors"], list)

    def test_no_api_key_raises_value_error(self):
        """Empty api_key raises ValueError (tenant must provide credentials)."""
        with pytest.raises(ValueError, match="api_key is required"):
            enrich_direct_bookings(["GY-NOKEY"])
        with pytest.raises(ValueError, match="api_key is required"):
            enrich_direct_bookings(["GY-NOKEY"], api_key="")

    @patch('str_stripe_enrichment.time.sleep')
    @patch('str_stripe_enrichment._lookup_payment')
    def test_enrichment_includes_reservation_code(self, mock_lookup, mock_sleep):
        """Each enrichment dict has reservationCode field added."""
        mock_lookup.return_value = {"email": "e@t.com", "phone": None, "country": None, "stripe_fee": None}
        result = enrich_direct_bookings(["GY-CODE1"], api_key="sk_test_enriched")
        assert result["enrichments"][0]["reservationCode"] == "GY-CODE1"


class TestPreservation_AmountAmbiguity:
    """Property 2f: Amount search returns None when multiple matches."""

    @patch('str_stripe_enrichment.stripe')
    def test_single_amount_match_returns_data(self, mock_stripe):
        """Exactly 1 amount match returns extracted data."""
        pi = _make_mock_pi(receipt_email="single@match.com")
        mock_result = MagicMock()
        mock_result.data = [pi]
        mock_stripe.PaymentIntent.search.return_value = mock_result
        result = _search_by_amount(150.0)
        assert result is not None
        assert result["email"] == "single@match.com"

    @patch('str_stripe_enrichment.stripe')
    def test_multiple_amount_matches_returns_none(self, mock_stripe):
        """2+ amount matches returns None (ambiguous)."""
        pi1 = _make_mock_pi(receipt_email="a@m.com")
        pi2 = _make_mock_pi(receipt_email="b@m.com")
        mock_result = MagicMock()
        mock_result.data = [pi1, pi2]
        mock_stripe.PaymentIntent.search.return_value = mock_result
        result = _search_by_amount(200.0)
        assert result is None

    @patch('str_stripe_enrichment.stripe')
    def test_zero_amount_matches_returns_none(self, mock_stripe):
        """No amount matches returns None."""
        mock_result = MagicMock()
        mock_result.data = []
        mock_stripe.PaymentIntent.search.return_value = mock_result
        result = _search_by_amount(999.0)
        assert result is None
