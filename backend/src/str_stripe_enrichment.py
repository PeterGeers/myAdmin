"""
Stripe enrichment module for dfDirect bookings.

Performs a 3-stage lookup strategy to find Stripe PaymentIntents matching
Guesty reservation codes, then extracts customer data (email, phone, country)
and the actual Stripe processing fee.

This module is self-contained and does not depend on other project modules.
"""

import time

import stripe


def enrich_direct_bookings(
    reservation_codes: list[str],
    amounts: dict[str, float] | None = None,
    api_key: str = "",
    metadata_key: str = "confirmationCode",
) -> dict:
    """
    Enrich dfDirect bookings with Stripe customer data.

    Args:
        reservation_codes: List of GY-XXXX confirmation codes to look up
        amounts: Optional dict of {reservation_code: amount_in_euros} for fallback search
        api_key: Stripe secret key for this tenant (required)
        metadata_key: Guesty metadata key name in Stripe (per-tenant configurable)

    Returns:
        dict with:
            - enrichments: list[dict] — successful lookups with email/phone/country/stripe_fee
            - not_found: list[str] — codes with no Stripe match
            - errors: list[str] — codes that failed due to API errors

    Raises:
        ValueError: If api_key is empty or not provided
    """
    if not api_key:
        raise ValueError("api_key is required")

    enrichments = []
    not_found = []
    errors = []

    for code in reservation_codes:
        try:
            customer_data = _lookup_payment(
                code,
                amounts.get(code) if amounts else None,
                api_key=api_key,
                metadata_key=metadata_key,
            )
            if customer_data:
                customer_data["reservationCode"] = code
                enrichments.append(customer_data)
            else:
                not_found.append(code)
            # Respect Stripe rate limits (25 req/s in live mode)
            time.sleep(0.05)
        except stripe.error.StripeError as e:
            errors.append(f"{code}: {e!s}")

    return {"enrichments": enrichments, "not_found": not_found, "errors": errors}


def _lookup_payment(
    reservation_code: str,
    amount_eur: float | None = None,
    api_key: str = "",
    metadata_key: str = "confirmationCode",
) -> dict | None:
    """
    Three-stage lookup strategy for a Guesty reservation in Stripe.

    Stage 1: Search PaymentIntents by metadata key (most reliable)
    Stage 2: Search PaymentIntents by description containing the code
    Stage 3: Search by exact amount in cents (least reliable, single match only)
    """
    # Stage 1: Metadata search
    result = _search_by_metadata(reservation_code, api_key=api_key, metadata_key=metadata_key)
    if result:
        return result

    # Stage 2: Description search
    result = _search_by_description(reservation_code, api_key=api_key)
    if result:
        return result

    # Stage 3: Amount-based fallback (only if amount provided)
    if amount_eur and amount_eur > 0:
        result = _search_by_amount(amount_eur, api_key=api_key)
        if result:
            return result

    return None


def _search_by_metadata(
    reservation_code: str,
    api_key: str = "",
    metadata_key: str = "confirmationCode",
) -> dict | None:
    """
    Search Stripe PaymentIntents by the configured Guesty metadata key.

    Uses Stripe's Search API with per-call api_key for tenant isolation.
    The metadata key is configurable per-tenant via the metadata_key parameter.
    """
    try:
        result = stripe.PaymentIntent.search(
            query=f'metadata["{metadata_key}"]:"{reservation_code}"',
            limit=1,
            api_key=api_key,
        )
        if result.data:
            return _extract_customer_data(result.data[0], api_key=api_key)
    except stripe.error.InvalidRequestError:
        pass
    return None


def _search_by_description(
    reservation_code: str,
    api_key: str = "",
) -> dict | None:
    """
    Search Stripe PaymentIntents where description contains the reservation code.

    Guesty often sets the payment description to something like:
    "Payment for reservation GY-XiBFAZHQ - Annemie Gertzen"

    Uses Stripe's fuzzy description search with per-call api_key.
    """
    try:
        result = stripe.PaymentIntent.search(
            query=f'description~"{reservation_code}"',
            limit=1,
            api_key=api_key,
        )
        if result.data:
            return _extract_customer_data(result.data[0], api_key=api_key)
    except stripe.error.InvalidRequestError:
        pass
    return None


def _search_by_amount(
    amount_eur: float,
    api_key: str = "",
) -> dict | None:
    """
    Fallback: search by exact amount in cents with status succeeded.

    Less reliable — only used when metadata and description searches fail.
    Returns data only if exactly one match (ambiguous if multiple).
    """
    amount_cents = int(amount_eur * 100)
    try:
        result = stripe.PaymentIntent.search(
            query=f'amount:{amount_cents} AND status:"succeeded"',
            limit=3,
            api_key=api_key,
        )
        # Only use if exactly one match (avoid false positives)
        if len(result.data) == 1:
            return _extract_customer_data(result.data[0], api_key=api_key)
    except stripe.error.InvalidRequestError:
        pass
    return None


def _country_from_phone(phone_str: str) -> str | None:
    """Derive ISO country code from phone number using phonenumbers library."""
    try:
        import phonenumbers

        # Ensure phone starts with + for parsing
        clean = phone_str.strip()
        if not clean.startswith("+"):
            clean = f"+{clean}"
        parsed = phonenumbers.parse(clean, None)
        country = phonenumbers.region_code_for_number(parsed)
        return country if country else None
    except Exception:
        return None


def _extract_customer_data(payment_intent, api_key: str = "") -> dict:
    """
    Extract email, phone, country, and Stripe fee from a matched PaymentIntent.

    Checks multiple data sources in priority order:
    1. Shipping details on the PaymentIntent (Guesty stores phone/address here)
    2. receipt_email on the PaymentIntent itself
    3. Customer object (if customer ID is attached)
    4. PaymentMethod billing_details (address.country, phone, email)
    5. Latest Charge object for Stripe processing fee (balance_transaction.fee)
    """
    data = {"email": None, "phone": None, "country": None, "stripe_fee": None}

    # Source 1: Shipping details (Guesty stores phone and address here)
    if payment_intent.shipping:
        shipping = payment_intent.shipping
        if shipping.phone:
            data["phone"] = shipping.phone
        if shipping.address and shipping.address.country:
            data["country"] = shipping.address.country

    # Source 2: receipt_email on PaymentIntent
    data["email"] = payment_intent.receipt_email

    # Source 3: Customer object (has email and phone)
    if payment_intent.customer:
        try:
            customer = stripe.Customer.retrieve(
                payment_intent.customer, api_key=api_key
            )
            if not data["email"]:
                data["email"] = customer.email
            if not data["phone"] and customer.phone:
                data["phone"] = customer.phone
        except stripe.error.StripeError:
            pass

    # Source 4: PaymentMethod billing_details
    if payment_intent.payment_method:
        try:
            pm = stripe.PaymentMethod.retrieve(
                payment_intent.payment_method, api_key=api_key
            )
            billing = pm.billing_details
            if billing:
                if not data["phone"] and billing.phone:
                    data["phone"] = billing.phone
                if not data["country"] and billing.address and billing.address.country:
                    data["country"] = billing.address.country
                if not data["email"] and billing.email:
                    data["email"] = billing.email
        except stripe.error.StripeError:
            pass

    # Source 5: Derive country from phone number if still missing
    if not data["country"] and data["phone"]:
        data["country"] = _country_from_phone(data["phone"])

    # Source 6: Stripe processing fee from the Charge's BalanceTransaction
    if payment_intent.latest_charge:
        try:
            charge = stripe.Charge.retrieve(
                payment_intent.latest_charge,
                expand=["balance_transaction"],
                api_key=api_key,
            )
            if charge.balance_transaction and charge.balance_transaction.fee:
                # fee is in cents, convert to euros
                data["stripe_fee"] = charge.balance_transaction.fee / 100.0
        except stripe.error.StripeError:
            pass

    return data
