# VRBO Import — Design

**Status:** Ready for Implementation
**Date:** 2026-03-27
**Module:** STR
**Related:** `requirements.md`, existing Airbnb/Booking.com import in `str_processor.py`

---

## Overview

Add VRBO as a third STR channel alongside Airbnb and Booking.com. VRBO provides two separate CSV exports that need to be combined:

1. **Reservations CSV** — booking details (dates, guests, listing, status)
2. **Upcoming Payouts CSV** — financial data (payout amounts per booking)

The challenge: the Reservations CSV has no financial data, and the Payouts CSV has no booking details. They must be joined on `Reservation ID` / `Boekingsnummer`.

---

## Data Sources

### Reservations CSV (English headers)

Downloaded from: `https://www.vrbo.com/nl-nl/p/calendar/{listing}/rail/downloadBookingDetails`

| Column         | Example                            | Maps to                      |
| -------------- | ---------------------------------- | ---------------------------- |
| Reservation ID | HA-MSBK7M                          | `reservationCode`            |
| Listing Number | 10744968                           | (used for listing lookup)    |
| Property Name  | JaBaKi Red Studio (617 - 10744968) | `listing`                    |
| Created On     | 2026-02-20                         | `reservationDate`            |
| Email          | guest@example.com                  | `addInfo`                    |
| Inquirer       | Jacqueline Johansen                | `guestName`                  |
| Phone          | 1 907-841-5191                     | `phone`                      |
| Check-in       | 2026-05-07                         | `checkinDate`                |
| Check-out      | 2026-05-12                         | `checkoutDate`               |
| Nights Stay    | 5                                  | `nights`                     |
| Adults         | 2                                  | `guests` (adults + children) |
| Children       | 0                                  | `guests`                     |
| Status         | Booked                             | `status`                     |
| Source         | VRBO                               | `channel` = 'vrbo'           |

Note: one CSV per listing — multiple files may need to be imported.

### Upcoming Payouts CSV (Dutch headers)

Downloaded from: `https://www.vrbo.com/nl-nl/supply/financial-reporting?tab=upcoming-payouts`

| Column             | Example             | Maps to                                            |
| ------------------ | ------------------- | -------------------------------------------------- |
| Naam gast          | Jacqueline Johansen | (used for matching)                                |
| Boekingsnummer     | HA-MSBK7M           | join key → `reservationCode`                       |
| Accommodatienummer | 10744968            | (listing reference)                                |
| Uitbetalingsdatum  | 8 mei 2026          | (payout date, informational)                       |
| Status             | Gepland             | (payout status)                                    |
| Bedrag             | € 559,36            | payout amount (= `amountGross - amountChannelFee`) |

Note: last row is a total line — must be skipped.

### Financial breakdown (from payment detail screen)

Per booking, VRBO shows:

- **Totaal betaald door gast** = `amountGross` (e.g., €116.42)
- **Betaald aan Vrbo** = `amountChannelFee` (e.g., -€29.02)
- **Uw totale uitbetaling** = payout = `amountGross - amountChannelFee` (e.g., €87.40)

The Payouts CSV only contains the payout amount. To get `amountGross` and `amountChannelFee` separately, we need to reverse-calculate:

- `paidOut` = Bedrag from CSV
- `amountChannelFee` = estimated (VRBO fee varies, typically ~25% of gross)
- `amountGross` = `paidOut + amountChannelFee`

Or: use the payout as `amountNett` equivalent and estimate the gross.

---

## Approach: Two-file merge

```
Reservations CSV(s)          Payouts CSV
(booking details)            (financial data)
       │                           │
       └─────── JOIN ON ───────────┘
              reservationCode = Boekingsnummer
                      │
                      ▼
              Merged booking records
              (details + amounts)
                      │
                      ▼
              Tax calculation
              (VAT, tourist tax)
                      │
                      ▼
              Standard booking format
              (same as Airbnb/Booking.com)
```

### Merge logic

1. Parse all Reservations CSVs → dict keyed by `Reservation ID`
2. Parse Payouts CSV → dict keyed by `Boekingsnummer`
3. For each reservation:
   - Look up payout amount from Payouts CSV
   - If found: calculate financial fields
   - If not found: booking exists but no payout yet (planned/future)
4. For each payout without a reservation: log warning (orphan payout)

### Financial calculation

Since VRBO only provides the payout amount (not gross + fee separately):

```python
paid_out = payout_amount                    # from Payouts CSV
channel_fee_factor = 0.25                   # VRBO typical fee ~25% of gross
# Reverse: paidOut = gross - fee = gross - (gross * 0.25) = gross * 0.75
amount_gross = paid_out / (1 - channel_fee_factor)
amount_channel_fee = amount_gross - paid_out

# Then standard tax calculation
tax_calc = calculate_str_taxes(amount_gross, checkin_date, amount_channel_fee)
```

Note: the 25% fee factor is an estimate. The actual fee varies per booking. If exact amounts are needed, they must be entered manually or scraped from the payment detail screen.

---

## Implementation

### New method: `_process_vrbo()` in `str_processor.py`

```python
def _process_vrbo(self, file_paths: List[str]) -> List[Dict]:
    """
    Process VRBO CSV exports.

    Expects multiple files:
    - One or more Reservations CSVs (English headers, one per listing)
    - One Payouts CSV (Dutch headers, "Naam gast" column identifies it)

    Auto-detects file type by header row.
    """
```

### File type detection

| First header     | File type        |
| ---------------- | ---------------- |
| `Reservation ID` | Reservations CSV |
| `Naam gast`      | Payouts CSV      |

### Output format

Same dict structure as Airbnb/Booking.com — all fields from `insert_realised_bookings`:

```python
{
    'sourceFile': '2026-03-27 Reservations.csv',
    'channel': 'vrbo',
    'listing': 'JaBaKi Red Studio',
    'checkinDate': '2026-05-07',
    'checkoutDate': '2026-05-12',
    'nights': 5,
    'guests': 2,
    'amountGross': 745.81,
    'amountChannelFee': 186.45,
    'amountNett': ...,          # calculated
    'amountVat': ...,           # calculated
    'amountTouristTax': ...,    # calculated
    'guestName': 'Jacqueline Johansen',
    'phone': '1 907-841-5191',
    'reservationCode': 'HA-MSBK7M',
    'reservationDate': '2026-02-20',
    'status': 'realised' | 'planned',
    'pricePerNight': ...,       # calculated
    'year': 2026,
    'q': 2,
    'm': 5,
    'daysBeforeReservation': 76,
    'addInfo': '...',           # all CSV fields concatenated
    'country': '...',           # detected from phone
}
```

---

## Frontend changes

### STR Import page

Add "VRBO" as a platform option alongside Airbnb and Booking.com:

- File upload accepts multiple files (reservations + payouts)
- Platform selector: Airbnb | Booking.com | VRBO
- Preview shows merged results before saving

### No new pages needed

VRBO bookings go into the same `bnb` / `bnbplanned` tables and appear in all existing STR reports.

---

## Edge cases

| Case                         | Handling                                                       |
| ---------------------------- | -------------------------------------------------------------- |
| Reservation without payout   | Include with `amountGross = 0`, status = 'planned'             |
| Payout without reservation   | Log warning, skip (orphan payout)                              |
| Cancelled booking            | Status = 'Cancelled' in Reservations CSV → skip if no earnings |
| Multiple listings            | Multiple Reservations CSVs, one per listing — all merged       |
| Total row in Payouts CSV     | Skip rows where `Boekingsnummer` is empty                      |
| Dutch date format in Payouts | Parse "8 mei 2026" → `2026-05-08`                              |
| Euro amount format           | Parse "€ 559,36" → 559.36                                      |

---

## Tasks

### Phase 1: Backend

- [ ] Add `_process_vrbo()` method to `str_processor.py`
- [ ] Add file type auto-detection (Reservations vs Payouts by header)
- [ ] Implement two-file merge on `Reservation ID` / `Boekingsnummer`
- [ ] Add Dutch date parsing ("8 mei 2026" format)
- [ ] Add Euro amount parsing ("€ 559,36" format)
- [ ] Calculate financial fields from payout amount
- [ ] Add 'vrbo' to platform options in STR routes
- [ ] Add unit tests for VRBO processing

### Phase 2: Frontend

- [ ] Add 'VRBO' option to platform selector on STR import page
- [ ] Support multi-file upload (reservations + payouts)
- [ ] Show merge results in preview (matched/unmatched counts)

### Phase 3: Testing

- [ ] Test with sample data from requirements
- [ ] Test merge: reservation with payout → correct amounts
- [ ] Test merge: reservation without payout → planned status
- [ ] Test: cancelled booking skipped
- [ ] Test: total row in payouts skipped
- [ ] Test: multiple listing files merged correctly
