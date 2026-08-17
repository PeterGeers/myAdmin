# Design Document

## Architecture Overview

This feature replaces the legacy `_process_direct` method (Excel-based, `typeTrade` channel routing) with a dedicated Guesty CSV parser module. Following the project's established pattern of extracting platform parsers into separate files (see `str_airbnb_parser.py`, `str_booking_parser.py`), the new logic lives in `str_direct_parser.py`.

The upload route gains a file-extension validation gate for the `direct` platform (CSV only), and the frontend `ImportLinksPopup` gets a new section with the Guesty link and filter prompt.

```
┌──────────────────┐     POST /api/str/upload (platform=direct)
│  Frontend        │────────────────────────────────────────────────►┌─────────────────────┐
│  STRProcessor.tsx│                                                 │ str_routes.py       │
│  ImportLinksPopup│◄───── JSON response ───────────────────────────│ str_upload_wrapper  │
└──────────────────┘                                                 └─────────┬───────────┘
                                                                               │
                                                                    file extension check
                                                                    (.csv only for direct)
                                                                               │
                                                                    ┌──────────▼──────────┐
                                                                    │ STRProcessor        │
                                                                    │ _process_direct()   │
                                                                    └──────────┬──────────┘
                                                                               │ delegates
                                                                    ┌──────────▼──────────┐
                                                                    │ str_direct_parser.py│
                                                                    │ process_direct_csv()│
                                                                    └──────────┬──────────┘
                                                                               │
                                                           ┌───────────────────┼───────────────────┐
                                                           │                   │                   │
                                                  ┌────────▼───────┐  ┌────────▼───────┐  ┌───────▼────────┐
                                                  │ str_utils.py   │  │ str_utils.py   │  │ str_utils.py   │
                                                  │ calculate_     │  │ normalize_     │  │ parse_amount() │
                                                  │ str_taxes()    │  │ listing_name() │  │                │
                                                  └────────────────┘  └────────────────┘  └────────────────┘
```

## Data Flow

1. User opens Import Links Popup → sees Guesty link with filter prompt → navigates to Guesty → applies filter → exports CSV
2. User selects platform "direct", picks the downloaded CSV, clicks Process
3. Frontend sends `POST /api/str/upload` with `platform=direct` and the CSV file
4. Route handler validates file extension (only `.csv` accepted for direct)
5. `STRProcessor._process_direct()` delegates to `str_direct_parser.process_direct_csv()`
6. Parser validates headers, filters by status, calculates financials, maps fields
7. Returns booking list + processing summary (skipped counts, skip reasons)
8. Route handler separates by status (realised/planned/already_loaded) and returns JSON
9. Frontend displays results in the standard booking review table

## New Module: `str_direct_parser.py`

### Public Interface

```python
def process_direct_csv(
    file_path: str,
    tax_rate_service=None,
    tenant: str | None = None,
) -> dict:
    """
    Parse a Guesty CSV export for dfDirect channel.

    Args:
        file_path: Path to the uploaded CSV file
        tax_rate_service: Optional TaxRateService for dynamic tax rates
        tenant: Optional tenant identifier

    Returns:
        dict with keys:
            - bookings: list[dict] — processed booking records
            - summary: dict — processing statistics
                - total_rows: int
                - processed_count: int
                - skipped_count: int
                - skipped_reasons: dict[str, int]
    """
```

### Internal Functions

```python
def _validate_headers(df_columns: list[str]) -> list[str]:
    """
    Validate that all 13 required columns are present (case-insensitive, whitespace-trimmed).
    Returns list of missing column names. Empty list = valid.
    """

def _parse_guesty_date(date_str: str) -> str | None:
    """
    Parse "YYYY-MM-DD HH:MM AM/PM" or "YYYY-MM-DD" format.
    Returns date portion as "YYYY-MM-DD" string, or None if unparsable.
    Validates the extracted date is a real calendar date.
    """

def _calculate_direct_row(
    row: pd.Series,
    col_map: dict[str, str],
    source_file: str,
    row_number: int,
    tax_rate_service=None,
    tenant: str | None = None,
) -> dict | None:
    """
    Process a single Guesty CSV row into a booking dict.
    Returns None if the row should be skipped (with reason logged).
    """
```

### Column Mapping

The parser normalizes CSV headers to lowercase/stripped for lookup:

| Guesty CSV Column | Internal Booking Field | Transform                                                      |
| ----------------- | ---------------------- | -------------------------------------------------------------- | ------------ | ----------- |
| CHECK-IN          | checkinDate            | `_parse_guesty_date()` → YYYY-MM-DD                            |
| CHECK-OUT         | checkoutDate           | `_parse_guesty_date()` → YYYY-MM-DD                            |
| CONFIRMATION CODE | reservationCode        | strip whitespace                                               |
| LISTING           | listing                | `normalize_listing_name()`                                     |
| GUEST             | guestName              | strip whitespace                                               |
| CREATION DATE     | reservationDate        | `_parse_guesty_date()` → YYYY-MM-DD                            |
| NUMBER OF NIGHTS  | nights                 | int, default 0                                                 |
| NUMBER OF GUESTS  | guests                 | int, default 0                                                 |
| STATUS            | (filter field)         | case-insensitive "confirmed" check                             |
| TOTAL PAYOUT      | amountGross            | float, 2dp                                                     |
| —                 | channel                | hardcoded "dfDirect"                                           |
| —                 | amountChannelFee       | amountGross × 0.04                                             |
| —                 | amountVat              | via `calculate_str_taxes()`                                    |
| —                 | amountTouristTax       | via `calculate_str_taxes()`                                    |
| —                 | amountNett             | gross − fee − vat − tourist_tax                                |
| —                 | pricePerNight          | amountNett / nights                                            |
| —                 | year, q, m             | derived from checkinDate                                       |
| —                 | daysBeforeReservation  | checkinDate − reservationDate (days)                           |
| —                 | sourceFile             | "YYYY-MM-DD filename.csv"                                      |
| —                 | status                 | "planned" if checkin > today, else "realised"                  |
| —                 | phone                  | `""` (not available in Guesty CSV)                             |
| —                 | country                | via `detect_country("dfDirect", phone="", addinfo=guest_name)` |
| —                 | addInfo                | `"{confirmation_code}                                          | {guest_name} | {listing}"` |

### Financial Calculation Logic

```python
amount_gross = float(total_payout)  # from TOTAL PAYOUT column
channel_fee = round(amount_gross * 0.04, 2)  # fixed 4%
tax_calc = calculate_str_taxes(amount_gross, checkin_date, channel_fee, tax_rate_service, tenant)
amount_vat = tax_calc["amount_vat"]
amount_tourist_tax = tax_calc["amount_tourist_tax"]
amount_nett = tax_calc["amount_nett"]
price_per_night = round(amount_nett / nights, 2) if nights > 0 else 0
```

### Row Skip Conditions

| Condition                                        | Skip Reason Key             | Action                                                 |
| ------------------------------------------------ | --------------------------- | ------------------------------------------------------ |
| STATUS ≠ "confirmed" (case-insensitive, trimmed) | `"non_confirmed_status"`    | Skip silently                                          |
| STATUS empty/whitespace-only                     | `"non_confirmed_status"`    | Skip silently                                          |
| TOTAL PAYOUT ≤ 0                                 | `"zero_or_negative_payout"` | Skip silently                                          |
| TOTAL PAYOUT non-numeric                         | `"invalid_payout"`          | Skip + log warning                                     |
| NUMBER OF NIGHTS = 0 or missing                  | `"zero_nights"`             | Skip + log warning                                     |
| Date unparsable or invalid                       | `"unparsable_date"`         | Skip + log warning with row number + confirmation code |

## Route Changes: `str_routes.py`

### File Extension Validation

Add validation before processing for `direct` platform:

```python
# In str_upload_authenticated, after platform detection:
if platform == "direct":
    filename = uploaded_files[0].filename.lower()
    if filename.endswith(('.xls', '.xlsx')):
        return jsonify({
            "success": False,
            "error": "Only CSV files are supported for the direct platform. Excel files (.xls/.xlsx) are no longer accepted."
        }), 400
    if not filename.endswith('.csv'):
        return jsonify({
            "success": False,
            "error": f"Unsupported file type for direct platform. Please upload a .csv file."
        }), 400
```

### Enhanced Summary Response

For dfDirect imports, the summary object extends the standard format:

```python
{
    "success": True,
    "realised": [...],
    "planned": [...],
    "already_loaded": [...],  # duplicates that would be updated
    "summary": {
        "total_bookings": 6,
        "total_rows": 7,
        "realised_count": 2,
        "planned_count": 4,
        "skipped_count": 1,
        "updated_count": 0,
        "skipped_reasons": {
            "non_confirmed_status": 1
        },
        # ...existing summary fields (total_nights, total_gross, etc.)
    },
    "platform": "direct",
    "administration": "tenant_name"
}
```

## Processor Changes: `str_processor.py`

### Replace `_process_direct` Method

```python
from str_direct_parser import process_direct_csv

def _process_direct(self, file_path: str) -> list[dict]:
    """Process direct bookings from Guesty CSV."""
    result = process_direct_csv(file_path, self.tax_rate_service, self.tenant)
    # Store processing summary for route-level access
    self._direct_processing_summary = result.get("summary", {})
    return result.get("bookings", [])
```

The old `_calculate_direct_row` method is removed entirely.

## Duplicate Handling: `str_database.py`

### New Method: `upsert_direct_bookings`

```python
def upsert_direct_bookings(self, bookings: list[dict]) -> dict:
    """
    Insert or update dfDirect bookings using reservationCode as composite key.

    Args:
        bookings: List of booking dicts from the parser

    Returns:
        dict with 'inserted': int, 'updated': int
    """
```

Logic:

1. Query existing reservation codes for channel "dfDirect"
2. For each booking:
   - If `reservationCode` exists in `bnb` table for "dfDirect": UPDATE fields
   - Otherwise: INSERT new record
3. Return counts of inserted/updated records

The UPDATE query touches: `checkinDate`, `checkoutDate`, `listing`, `guestName`, `nights`, `guests`, `amountGross`, `amountNett`, `amountChannelFee`, `amountVat`, `amountTouristTax`, `status`, `pricePerNight`, `sourceFile`.

### Handling Non-Confirmed Re-imports

When a previously imported booking reappears with status ≠ "confirmed", the parser skips it (no booking dict produced). However, Requirement 8.5 says the existing record's status should be updated. This requires a two-pass approach:

1. **Pass 1 (in parser)**: Process confirmed rows → booking dicts
2. **Pass 2 (in parser)**: Collect non-confirmed rows that have a reservationCode → return as `status_updates` list

The parser return structure becomes:

```python
{
    "bookings": [...],           # confirmed rows → full booking dicts
    "status_updates": [...],     # non-confirmed rows → {"reservationCode": "...", "status": "canceled"}
    "summary": {...}
}
```

The route/save layer applies status updates to existing records during the save operation.

## Frontend Changes: `STRProcessor.tsx`

### ImportLinksPopup — dfDirect Section

Replace the current static text box:

```tsx
<Box>
  <Text fontWeight="bold" mb={2}>
    {t("processor.importDataLinks.dfDirect")}
  </Text>
  <Link
    href="https://app.guesty.com/reservations?viewId=6a72237ce377681f84e3746c"
    isExternal
    w="full"
    p={2}
    bg="teal.600"
    borderRadius="md"
    textDecoration="none"
    _hover={{ bg: "teal.500" }}
    display="block"
  >
    {t("processor.importDataLinks.guestyReservations")}
  </Link>
  <Text color="gray.300" fontSize="xs" mt={1}>
    {t("processor.importDataLinks.guestyFilterPrompt")}
  </Text>
</Box>
```

### File Input Restriction

For `direct` platform, restrict the file input to CSV only:

```tsx
accept={selectedPlatform === 'direct' ? '.csv' : '.csv,.tsv,.xlsx,.xls'}
```

## Translation Keys

New i18n keys under `str` namespace:

```json
{
  "processor.importDataLinks.dfDirect": "Guesty Direct:",
  "processor.importDataLinks.guestyReservations": "Guesty Reservations",
  "processor.importDataLinks.guestyFilterPrompt": "Checkin is between 2 months ago and 1 year into the future for Platform Manual"
}
```

## Error Handling

| Scenario                             | HTTP Status | Response                                                                    |
| ------------------------------------ | ----------- | --------------------------------------------------------------------------- |
| Missing required columns in CSV      | 400         | `{"success": false, "error": "Missing required columns: CHECK-IN, STATUS"}` |
| Excel file uploaded for direct       | 400         | `{"success": false, "error": "Only CSV files are supported..."}`            |
| Unsupported file extension           | 400         | `{"success": false, "error": "Unsupported file type..."}`                   |
| All rows skipped (no valid bookings) | 200         | Success response with empty arrays + summary showing skip counts            |
| CSV parse error (malformed)          | 500         | `{"success": false, "error": "Failed to parse CSV: ..."}`                   |

## Optional Stripe Enrichment (Post-Import)

After the CSV import completes, an optional enrichment step fetches email, phone, and country from Stripe for each booking. This runs as a separate post-processing call, keeping the core CSV import independent and fast.

### Architecture

```
CSV Import (fast, no external deps)
        │
        ▼
   Bookings returned to frontend
        │
        ▼ (automatic after save, or user-triggered)
   POST /api/str/enrich-direct
        │
        ├── For each booking.reservationCode:
        │     1. Search Stripe PaymentIntents by metadata key
        │     2. Fallback: search by description containing the code
        │     3. Fallback: search by amount (cents, single match only)
        │     Extract: email, phone, billing country
        │     Update bnb record
        │
        ▼
   Enriched booking records (phone, country, email in addInfo)
```

### Discovery Step (One-Time Setup)

Before implementing, inspect one Guesty-created payment in the Stripe Dashboard to determine the exact metadata key name:

1. Stripe Dashboard → Payments → find a known Guesty booking payment
2. Expand the payment details → scroll to "Metadata" section
3. Note the key name (e.g., `reservationId`, `confirmationCode`, `guestyReservationId`)

Store this key name as a configuration constant. The Stripe Search API supports searching by metadata using the syntax `metadata["key"]:"value"` ([Stripe docs](https://docs.stripe.com/search)).

### How Guesty Stores Data in Stripe

When Guesty processes a payment through a connected Stripe account, it typically:

- Creates a PaymentIntent with metadata linking back to the reservation
- Sets the payment `description` to include the confirmation code and/or guest name
- May create a Stripe Customer object with email and phone

The exact metadata key varies by Guesty configuration. Common patterns observed:

- `metadata["reservationId"]` — Guesty's internal ID
- `metadata["confirmationCode"]` — the GY-XXXXX code visible in exports
- `metadata["guestyReservationId"]` — alternative naming

### Implementation: `str_stripe_enrichment.py`

```python
import os
import time

import stripe

# Configurable metadata key — determined by inspecting Stripe Dashboard
GUESTY_METADATA_KEY = os.getenv("STRIPE_GUESTY_METADATA_KEY", "confirmationCode")


def enrich_direct_bookings(
    reservation_codes: list[str],
    amounts: dict[str, float] | None = None,
) -> dict:
    """
    Enrich dfDirect bookings with Stripe customer data.

    Args:
        reservation_codes: List of GY-XXXX confirmation codes to look up
        amounts: Optional dict of {reservation_code: amount_in_euros} for fallback search

    Returns:
        dict with:
            - enrichments: list[dict] — successful lookups with email/phone/country
            - not_found: list[str] — codes with no Stripe match
            - errors: list[str] — codes that failed due to API errors
    """
    api_key = os.getenv("STRIPE_SECRET_KEY")
    if not api_key:
        return {
            "enrichments": [],
            "not_found": reservation_codes,
            "errors": ["STRIPE_SECRET_KEY not configured"],
        }

    stripe.api_key = api_key
    enrichments = []
    not_found = []
    errors = []

    for code in reservation_codes:
        try:
            customer_data = _lookup_payment(
                code, amounts.get(code) if amounts else None
            )
            if customer_data:
                customer_data["reservationCode"] = code
                enrichments.append(customer_data)
            else:
                not_found.append(code)
            # Respect Stripe rate limits (25 req/s in live mode)
            time.sleep(0.05)
        except stripe.error.StripeError as e:
            errors.append(f"{code}: {str(e)}")

    return {"enrichments": enrichments, "not_found": not_found, "errors": errors}


def _lookup_payment(
    reservation_code: str, amount_eur: float | None = None
) -> dict | None:
    """
    Three-stage lookup strategy for a Guesty reservation in Stripe.

    Stage 1: Search PaymentIntents by metadata key (most reliable)
    Stage 2: Search PaymentIntents by description containing the code
    Stage 3: Search by exact amount in cents (least reliable, single match only)
    """
    # Stage 1: Metadata search
    result = _search_by_metadata(reservation_code)
    if result:
        return result

    # Stage 2: Description search
    result = _search_by_description(reservation_code)
    if result:
        return result

    # Stage 3: Amount-based fallback (only if amount provided)
    if amount_eur and amount_eur > 0:
        result = _search_by_amount(amount_eur)
        if result:
            return result

    return None


def _search_by_metadata(reservation_code: str) -> dict | None:
    """
    Search Stripe PaymentIntents by the configured Guesty metadata key.

    Uses Stripe's Search API:
        stripe.PaymentIntent.search(query='metadata["key"]:"value"')

    The metadata key is configurable via STRIPE_GUESTY_METADATA_KEY env var,
    defaulting to "confirmationCode". Inspect Stripe Dashboard to confirm
    the actual key Guesty uses in your account.
    """
    try:
        result = stripe.PaymentIntent.search(
            query=f'metadata["{GUESTY_METADATA_KEY}"]:"{reservation_code}"',
            limit=1,
        )
        if result.data:
            return _extract_customer_data(result.data[0])
    except stripe.error.InvalidRequestError:
        pass
    return None


def _search_by_description(reservation_code: str) -> dict | None:
    """
    Search Stripe PaymentIntents where description contains the reservation code.

    Guesty often sets the payment description to something like:
    "Payment for reservation GY-XiBFAZHQ - Annemie Gertzen"

    Uses Stripe's fuzzy description search:
        stripe.PaymentIntent.search(query='description~"GY-XiBFAZHQ"')
    """
    try:
        result = stripe.PaymentIntent.search(
            query=f'description~"{reservation_code}"',
            limit=1,
        )
        if result.data:
            return _extract_customer_data(result.data[0])
    except stripe.error.InvalidRequestError:
        pass
    return None


def _search_by_amount(amount_eur: float) -> dict | None:
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
        )
        # Only use if exactly one match (avoid false positives)
        if len(result.data) == 1:
            return _extract_customer_data(result.data[0])
    except stripe.error.InvalidRequestError:
        pass
    return None


def _extract_customer_data(payment_intent) -> dict:
    """
    Extract email, phone, country, and Stripe fee from a matched PaymentIntent.

    Checks multiple data sources in priority order:
    1. receipt_email on the PaymentIntent itself
    2. Customer object (if customer ID is attached)
    3. PaymentMethod billing_details (address.country, phone, email)
    4. Latest Charge object for Stripe processing fee (balance_transaction.fee)
    """
    data = {"email": None, "phone": None, "country": None, "stripe_fee": None}

    # Source 1: receipt_email on PaymentIntent
    data["email"] = payment_intent.receipt_email

    # Source 2: Customer object (has email and phone)
    if payment_intent.customer:
        try:
            customer = stripe.Customer.retrieve(payment_intent.customer)
            if not data["email"]:
                data["email"] = customer.email
            data["phone"] = customer.phone
        except stripe.error.StripeError:
            pass

    # Source 3: PaymentMethod billing_details
    if payment_intent.payment_method:
        try:
            pm = stripe.PaymentMethod.retrieve(payment_intent.payment_method)
            billing = pm.billing_details
            if billing:
                if not data["phone"] and billing.phone:
                    data["phone"] = billing.phone
                if billing.address and billing.address.country:
                    data["country"] = billing.address.country  # ISO 2-letter (NL, DE, etc.)
                if not data["email"] and billing.email:
                    data["email"] = billing.email
        except stripe.error.StripeError:
            pass

    # Source 4: Stripe processing fee from the Charge's BalanceTransaction
    # The fee is what Stripe actually deducted (e.g., 1.5% + €0.25 for EU cards)
    if payment_intent.latest_charge:
        try:
            charge = stripe.Charge.retrieve(
                payment_intent.latest_charge,
                expand=["balance_transaction"],
            )
            if charge.balance_transaction and charge.balance_transaction.fee:
                # fee is in cents, convert to euros
                data["stripe_fee"] = charge.balance_transaction.fee / 100.0
        except stripe.error.StripeError:
            pass

    return data
```

### Route: `POST /api/str/enrich-direct`

```python
@str_bp.route("/api/str/enrich-direct", methods=["POST"])
@cognito_required(required_permissions=["str_create"])
@tenant_required()
def str_enrich_direct(user_email, user_roles, tenant, user_tenants):
    """
    Enrich recently imported dfDirect bookings with Stripe customer data.

    Request body (optional):
        {"reservation_codes": ["GY-XiBFAZHQ", "GY-6mKjJWRn"]}

    If no body provided, enriches all dfDirect bookings with empty phone field.
    """
    from str_stripe_enrichment import enrich_direct_bookings

    data = request.get_json(silent=True) or {}
    codes = data.get("reservation_codes")

    if not codes:
        # Fetch all dfDirect bookings missing phone data
        str_db = STRDatabase(test_mode=test_mode)
        codes = str_db.get_unenriched_direct_codes(tenant)

    if not codes:
        return jsonify({"success": True, "message": "No bookings to enrich", "enriched": 0})

    # Perform Stripe lookups
    result = enrich_direct_bookings(codes)

    # Apply enrichments to database
    if result["enrichments"]:
        str_db = STRDatabase(test_mode=test_mode)
        str_db.apply_stripe_enrichments(result["enrichments"], tenant)

    return jsonify({
        "success": True,
        "enriched": len(result["enrichments"]),
        "not_found": len(result["not_found"]),
        "errors": result["errors"],
    })
```

### Database Methods: `str_database.py`

```python
def get_unenriched_direct_codes(self, tenant: str) -> list[str]:
    """Get dfDirect reservation codes that have no phone/country data."""
    query = """
        SELECT reservationCode FROM bnb
        WHERE channel = 'dfDirect'
          AND administration = %s
          AND (phone IS NULL OR phone = '')
          AND (country IS NULL OR country = '')
        ORDER BY checkinDate DESC
        LIMIT 50
    """
    result = self.execute_query(query, (tenant,), fetch=True)
    return [row["reservationCode"] for row in result] if result else []


def apply_stripe_enrichments(self, enrichments: list[dict], tenant: str) -> int:
    """Apply Stripe-sourced customer data and actual fee to bnb records.

    When stripe_fee is available, it replaces the estimated 4% channel fee
    and triggers recalculation of amountNett and pricePerNight.
    """
    # Query for enrichments WITH actual Stripe fee
    update_with_fee_query = """
        UPDATE bnb
        SET phone = COALESCE(NULLIF(%s, ''), phone),
            country = COALESCE(NULLIF(%s, ''), country),
            amountChannelFee = %s,
            amountNett = amountGross - %s - amountVat - amountTouristTax,
            pricePerNight = CASE
                WHEN nights > 0 THEN ROUND((amountGross - %s - amountVat - amountTouristTax) / nights, 2)
                ELSE 0
            END,
            addInfo = CASE
                WHEN %s IS NOT NULL AND %s != ''
                THEN CONCAT(COALESCE(addInfo, ''), ' | email:', %s)
                ELSE addInfo
            END
        WHERE reservationCode = %s
          AND channel = 'dfDirect'
          AND administration = %s
    """
    # Query for enrichments WITHOUT Stripe fee (contact data only)
    update_no_fee_query = """
        UPDATE bnb
        SET phone = COALESCE(NULLIF(%s, ''), phone),
            country = COALESCE(NULLIF(%s, ''), country),
            addInfo = CASE
                WHEN %s IS NOT NULL AND %s != ''
                THEN CONCAT(COALESCE(addInfo, ''), ' | email:', %s)
                ELSE addInfo
            END
        WHERE reservationCode = %s
          AND channel = 'dfDirect'
          AND administration = %s
                THEN CONCAT(COALESCE(addInfo, ''), ' | email:', %s)
                ELSE addInfo
            END
        WHERE reservationCode = %s
          AND channel = 'dfDirect'
          AND administration = %s
    """
    updated = 0
    for e in enrichments:
        email = e.get("email") or ""
        phone = e.get("phone") or ""
        country = e.get("country") or ""
        stripe_fee = e.get("stripe_fee")
        code = e["reservationCode"]

        if stripe_fee is not None:
            # Use actual Stripe fee → recalculate nett and pricePerNight
            fee = round(stripe_fee, 2)
            self.execute_query(
                update_with_fee_query,
                (phone, country, fee, fee, fee, email, email, email, code, tenant),
                fetch=False, commit=True
            )
        else:
            # Contact data only, keep estimated 4% fee
            self.execute_query(
                update_no_fee_query,
                (phone, country, email, email, email, code, tenant),
                fetch=False, commit=True
            )
        updated += 1
    return updated
```

### Configuration

| Environment Variable         | Purpose                                                   | Default                                |
| ---------------------------- | --------------------------------------------------------- | -------------------------------------- |
| `STRIPE_SECRET_KEY`          | Stripe API secret key (sk*live*... or sk*test*...)        | (none — enrichment disabled if absent) |
| `STRIPE_GUESTY_METADATA_KEY` | The metadata key Guesty uses when creating PaymentIntents | `"confirmationCode"`                   |

### Frontend Integration

After a successful dfDirect CSV save, the frontend automatically triggers enrichment:

```tsx
// After successful save of dfDirect bookings
const codes = [...realisedBookings, ...plannedBookings]
  .filter((b) => b.channel === "dfDirect")
  .map((b) => b.reservationCode);

if (codes.length > 0) {
  // Fire and forget — enrichment happens in background
  authenticatedPost("/api/str/enrich-direct", { reservation_codes: codes })
    .then((res) => res.json())
    .then((data) => {
      if (data.enriched > 0) {
        setMessage(
          (prev) =>
            `${prev} | Enriched ${data.enriched} bookings with Stripe data.`,
        );
      }
    })
    .catch(() => {}); // Silent failure — enrichment is optional
}
```

### Error Handling

| Scenario                            | Behavior                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------- |
| `STRIPE_SECRET_KEY` not set         | Returns immediately with empty results, no error to user                    |
| Metadata key wrong / not found      | Falls through to description search, then amount search                     |
| No match found after all 3 stages   | Code added to `not_found` list, no DB update                                |
| Stripe rate limit hit               | `time.sleep(0.05)` between calls prevents hitting limit for typical batches |
| Stripe auth error (invalid key)     | Error logged, returned in response `errors` array                           |
| Multiple amount matches (ambiguous) | Skipped — only exact single matches used in amount fallback                 |
| Enrichment already applied (re-run) | `COALESCE(NULLIF(...), phone)` preserves existing non-empty values          |

## Security Considerations

- File extension validated server-side (not relying on frontend `accept` attribute)
- CSV parsing uses pandas `read_csv` with no `eval` or code execution
- All string values stripped/sanitized before database insertion
- Tenant isolation maintained: `administration` field set from authenticated session
- Parameterized queries for all database operations (no string interpolation)
- Stripe API key stored in environment variable, never hardcoded or logged
- Stripe enrichment endpoint requires `str_create` permission (same as upload)
- Customer PII (email, phone) stored only in tenant-scoped records

## Performance Considerations

- Guesty exports are typically small (< 100 rows for a single property portfolio)
- Single-pass iteration over DataFrame rows — O(n) processing
- No batch size concerns at this scale
- Existing `separate_by_status` does one DB query per channel to check duplicates (already optimized)
- Stripe enrichment: ~3 API calls per booking (metadata + description + customer/PM retrieval). For 10 bookings ≈ 30 calls, well within rate limits

## Testing Strategy

- **Unit tests** (`test_str_direct_parser.py`): header validation, date parsing, row filtering, financial calculations, field mapping, edge cases
- **Unit tests** (`test_str_stripe_enrichment.py`): mock Stripe API responses, verify lookup cascade, extraction logic
- **Integration test**: upload endpoint with sample CSV file, verify response structure
- **Test data**: use the provided `testdate.csv` (7 rows: 1 canceled + 6 confirmed) as the reference fixture
