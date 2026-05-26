# Findings: Airbnb Financial Calculation Model (Hospitable/Guesty CSV Export)

## Source

- **File**: Hospitable CSV export (e.g. `542786_2026-05-08_14_34_04.csv`)
- **Validation date**: 2026-05-08
- **Validated against**: Airbnb host dashboard (confirmed reservations April 2026)
- **Result**: 6 reservations verified — all match ✅

## Key Financial Fields in CSV

| CSV Column             | Meaning                                                   |
| ---------------------- | --------------------------------------------------------- |
| TOTAL PAYOUT           | Amount received by host (after commission deduction)      |
| CHANNEL COMMISSION     | Airbnb host service fee (15.5%)                           |
| PROCESSING FEES        | Payment processing fees (typically empty for Airbnb)      |
| NET ACCOMMODATION FARE | Nightly rate × nights (after adjustments/discounts)       |
| CLEANING FARE          | Cleaning fee charged to guest                             |
| TOTAL TAXES            | All taxes combined (VAT + local tax + tourism tax)        |
| TOTAL PAID             | **Misleading** — equals host payout, NOT what client paid |

## AmountNett (What the Host Receives)

```
AmountNett = TOTAL PAYOUT
```

- Directly available in the CSV, no calculation needed.
- `TOTAL PAID` column is either 0 or equals `TOTAL PAYOUT` — never represents client payment. Use `TOTAL PAYOUT` as the reliable source.

## AmountChannelFee (Platform Commission)

```
AmountChannelFee = CHANNEL COMMISSION + PROCESSING FEES
                 = AmountGross - AmountNett
```

- For Airbnb: PROCESSING FEES is always 0, so `AmountChannelFee = CHANNEL COMMISSION`
- For Booking.com: both fields may have values

## AmountGross Calculation (What the Client Pays)

Two equivalent formulas, both verified to produce identical results:

### Model A (from host perspective)

```
AmountGross = TOTAL PAYOUT + CHANNEL COMMISSION + PROCESSING FEES
```

### Model B (from guest perspective)

```
AmountGross = NET ACCOMMODATION FARE + CLEANING FARE + TOTAL TAXES
```

### Netherlands-specific note

In the Netherlands, the Airbnb guest service fee is **0% by law**. This means the AmountGross calculated above equals the actual amount debited from the guest's payment method.

## Verified Example: HMDTWN9D3H (Louis Poirier, Apr 25 2026)

**Airbnb host dashboard:**

- Host receives: €151.74
- Host commission (15.5%): €20.93
- Accommodation (€150 - €15 adjustment): €135.00
- Taxes (doorloop): €37.67
- Client paid: €172.67

**CSV data:**

- TOTAL PAYOUT: 151.74
- CHANNEL COMMISSION: 20.93
- NET ACCOMMODATION FARE: 135.00
- TOTAL TAXES: 37.67

**Calculation:**

- Model A: 151.74 + 20.93 = **172.67** ✅
- Model B: 135.00 + 0.00 + 37.67 = **172.67** ✅

## Important Warning: TOTAL PAID Column

The `TOTAL PAID` column in the Hospitable CSV does **NOT** represent what the client paid. It contains the host payout amount (same as `TOTAL PAYOUT`). Do not use this field for AmountGross.

## VAT and Tourist Tax

Calculation of VAT and tourist tax remains unchanged from the current implementation — these are not affected by the new source.

---

# Findings: Booking.com Financial Calculation Model

## Source

- **Validated against**: Booking.com extranet (confirmed reservations April 2026, Green Studio)
- **Result**: 2 reservations verified — all match ✅

## Key Difference from Airbnb

For Booking.com, the meaning of `TOTAL PAYOUT` is **different** from Airbnb:

| Field              | Airbnb                                             | Booking.com                                 |
| ------------------ | -------------------------------------------------- | ------------------------------------------- |
| TOTAL PAYOUT       | AmountNett (what host receives)                    | **AmountGross** (what guest pays)           |
| CHANNEL COMMISSION | Excl. VAT (no VAT applies - EU law, Irish company) | Excl. VAT (21% VAT applies - Dutch company) |
| PROCESSING FEES    | Always 0                                           | Payment Service Fee excl. VAT (1.3%)        |

## Booking.com Calculation Model

```
AmountGross = TOTAL PAYOUT
AmountChannelFee = (CHANNEL COMMISSION + PROCESSING FEES) × 1.21
AmountNett = AmountGross - AmountChannelFee
```

The CSV shows commission and processing fees **excl. VAT**, but Booking.com actually deducts these fees **incl. 21% VAT** from the host payout.

## Verified Example 1: BC-yzvV25oRE (Agnese Tarraran, Apr 26 2026)

**Booking.com extranet:**

- AmountGross: €445.52
- AmountNett: €383.38
- Commission: €51.35 (excl. VAT)
- Of which: commission €45.56 + payment service fee €5.79

**CSV data:**

- TOTAL PAYOUT: 445.52
- CHANNEL COMMISSION: 45.56
- PROCESSING FEES: 5.79

**Calculation:**

- AmountGross = 445.52 ✅
- AmountChannelFee = (45.56 + 5.79) × 1.21 = 51.35 × 1.21 = **62.13** ≈ 62.14
- AmountNett = 445.52 - 62.14 = **383.38** ✅

## Verified Example 2: BC-ZD0YGpMz5 (Janet Pritchard, Apr 13 2026)

**Booking.com extranet:**

- AmountGross: €334.80
- AmountNett: €288.11
- Commission: €34.23 + Payment Service Fee: €4.35 (both excl. VAT)

**CSV data:**

- TOTAL PAYOUT: 334.80
- CHANNEL COMMISSION: 34.23
- PROCESSING FEES: 4.35

**Calculation:**

- AmountGross = 334.80 ✅
- AmountChannelFee = (34.23 + 4.35) × 1.21 = 38.58 × 1.21 = **46.68** ≈ 46.69
- AmountNett = 334.80 - 46.69 = **288.11** ✅

## Why 21% VAT on Commission?

- **Airbnb**: Irish company, no VAT on commission due to EU reverse charge mechanism
- **Booking.com**: Dutch company, charges 21% Dutch VAT on commission to Dutch hosts

---

# Summary: Unified Mapping per Channel

## Airbnb

```
AmountGross = TOTAL PAYOUT + CHANNEL COMMISSION
AmountNett = TOTAL PAYOUT
AmountChannelFee = CHANNEL COMMISSION
```

## Booking.com

```
AmountGross = TOTAL PAYOUT
AmountNett = TOTAL PAYOUT - (CHANNEL COMMISSION + PROCESSING FEES) × 1.21
AmountChannelFee = (CHANNEL COMMISSION + PROCESSING FEES) × 1.21
```

## VRBO

```
AmountNett = TOTAL PAYOUT
AmountGross = Cannot be reliably calculated from CSV
AmountChannelFee = Cannot be fully calculated from CSV
```

### VRBO Limitation

The Hospitable CSV export does **not** contain sufficient data to calculate the true AmountGross for VRBO reservations. The following fees are missing from the CSV:

- **Guest service fee** (charged by VRBO to the guest, not passed to host)
- **Payment processing fee** (deducted from host payout, but not in PROCESSING FEES column)

Only `TOTAL PAYOUT` (AmountNett) and `CHANNEL COMMISSION` (VRBO commission excl. processing and guest fee) are available.

### Verified Example: VRB-HA-MSBK7M-F78DC (Jacqueline Johansen, May 07 2026)

**VRBO extranet:**

- Nightly rates (5 nights): €608.00
- Guest service fee: €87.00
- Total paid by guest: **€695.00**
- Vrbo commission: -€30.40
- Guest service fee (kept by VRBO): -€87.00
- Payment processing: -€18.24
- Your payout: **€559.36**

**CSV data:**

- TOTAL PAYOUT: 559.36 (= payout ✅)
- CHANNEL COMMISSION: 30.40 (= VRBO commission only ✅)
- PROCESSING FEES: (empty) ❌ should be 18.24
- NET ACCOMMODATION FARE: 589.76 (= payout + commission, not real nightly rate)
- TOTAL TAXES: 0
- Guest service fee (€87.00): **not in CSV** ❌

**Actual deductions from guest payment:**

- VRBO commission: €30.40
- Guest service fee: €87.00
- Payment processing: €18.24
- Total deductions: €135.64
- CSV only captures: €30.40 (24% of actual deductions)

### VRBO Recommendation

For VRBO reservations, only AmountNett (TOTAL PAYOUT) can be reliably extracted from this CSV source. AmountGross would need to come from the VRBO extranet directly or from a different export.

## Website / Manual (Direct Bookings via Guesty)

```
AmountGross = TOTAL PAYOUT
AmountNett = TOTAL PAYOUT × (1 - 0.043)
AmountChannelFee = TOTAL PAYOUT × 0.043
```

### Notes

- No channel commission (CHANNEL COMMISSION = 0, PROCESSING FEES = 0)
- Payment is processed via **Stripe** (credit cards only)
- Stripe fee is **not captured in the CSV** — only the gross amount (what guest pays) appears as TOTAL PAYOUT
- Assumed Stripe fee: **4.3%** (based on verified transaction, includes non-EU card surcharges)

### Verified Example: GY-vE5QFDVf (Arthur Bean, Apr 18 2027)

**Stripe dashboard:**

- Guest pays: €477.00
- Stripe fee: €20.52 (4.3%)
- Host receives: €456.48

**CSV data:**

- TOTAL PAYOUT: 477.00 (= what guest paid, NOT what host receives)
- CHANNEL COMMISSION: 0
- PROCESSING FEES: 0

**Calculation:**

- AmountGross = 477.00 ✅
- AmountChannelFee = 477.00 × 0.043 = 20.51 ≈ €20.52
- AmountNett = 477.00 - 20.52 = €456.48 ✅

### Website/Manual Limitation

The Stripe fee (4.3%) is an approximation. Actual fees vary per transaction depending on card type (EU vs non-EU) and payment method. For exact AmountNett, Stripe transaction data would be needed.

## VAT and Tourist Tax

Calculation from AmountGross, using date-dependent rates (rate change on 2026-01-01):

### Tax Rates

| Period            | VAT Rate | VAT Base | Tourist Tax Rate | Tourist Tax Base |
| ----------------- | -------- | -------- | ---------------- | ---------------- |
| Before 2026-01-01 | 9%       | 109      | 6.02%            | 106.02           |
| From 2026-01-01   | 21%      | 121      | 6.9%             | 106.9            |

### Calculation Steps (from AmountGross)

```
Step 1: Calculate VAT
  amountVat = (AmountGross / vat_base) × vat_rate

Step 2: Calculate Tourist Tax on VAT-exclusive amount
  vat_exclusive_amount = AmountGross - amountVat
  amountTouristTax = (vat_exclusive_amount / tourist_tax_base) × tourist_tax_rate
```

### Example: AmountGross = €172.67 (check-in Apr 25 2026, post rate change)

```
vat_rate = 21%, vat_base = 121, tourist_tax_rate = 6.9%, tourist_tax_base = 106.9

Step 1: amountVat = (172.67 / 121) × 21 = 29.97
Step 2: vat_exclusive = 172.67 - 29.97 = 142.70
         amountTouristTax = (142.70 / 106.9) × 6.9 = 9.21
```

### Note

These rates are already supported in the app via `TaxRateService` (database-driven) with a fallback to hardcoded rates based on the check-in date. The calculation logic remains unchanged from the current implementation.

---

# CSV Column to Database Field Mapping

## Target Tables: `bnb` (realised) and `bnbplanned` (future)

Both tables have identical schemas. Records go to `bnb` if checkout is in the past, `bnbplanned` if checkout is in the future.

### Required CSV Columns

| DB Field                | CSV Column        | Notes                                                                                                        |
| ----------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------ |
| `channel`               | SOURCE            | Map: "airbnb2" → "AirBnB", "Booking.com" → "Booking.com", "vrboLite" → "VRBO", "website"/"manual" → "Direct" |
| `listing`               | LISTING           | Extract short name (e.g., "Garden House", "Red Studio", "Green Studio")                                      |
| `checkinDate`           | CHECK-IN          | Parse date from "YYYY-MM-DD HH:MM AM/PM" format                                                              |
| `checkoutDate`          | CHECK-OUT         | Parse date from "YYYY-MM-DD HH:MM AM/PM" format                                                              |
| `nights`                | NUMBER OF NIGHTS  | Direct mapping                                                                                               |
| `guests`                | NUMBER OF GUESTS  | Direct mapping                                                                                               |
| `amountGross`           | _Calculated_      | Per channel formula (see Summary above)                                                                      |
| `amountNett`            | _Calculated_      | Per channel formula (see Summary above)                                                                      |
| `amountChannelFee`      | _Calculated_      | Per channel formula (see Summary above)                                                                      |
| `amountTouristTax`      | _Calculated_      | From AmountGross using tax rates                                                                             |
| `amountVat`             | _Calculated_      | From AmountGross using tax rates                                                                             |
| `guestName`             | GUEST             | Direct mapping (trim whitespace)                                                                             |
| `reservationCode`       | CONFIRMATION CODE | Direct mapping                                                                                               |
| `reservationDate`       | Creation Date                | Creation Date                                                                             |
| `status`                | STATUS            | Map: "confirmed" → "realised"/"planned", "canceled" → skip, "inquiry" → skip                                 |
| `pricePerNight`         | _Calculated_      | amountNett / nights                                                                                          |
| `daysBeforeReservation` | _Calculated_      | Days between Checkin date and reaservation date                                                                   |
| `country`               | GUEST'S COUNTRY   | Map country name to ISO 3166-1 alpha-2 code                                                                  |
| `year`                  | _Derived_         | Year from checkinDate                                                                                        |
| `q`                     | _Derived_         | Quarter from checkinDate                                                                                     |
| `m`                     | _Derived_         | Month from checkinDate                                                                                       |
| `sourceFile`            | —                 | Set to CSV filename                                                                                          |
| `administration`        | —                 | Set from tenant context                                                                                      |

### Columns NOT needed from CSV

| CSV Column                                         | Reason                        |
| -------------------------------------------------- | ----------------------------- |
| CHECK-IN FORM SUBMISSION STATUS                    | Not used                      |
| WEBSITE NAME                                       | Not used                      |
| GUEST'S EMAIL                                      | Not stored in bnb table       |
| NUMBER OF ADULTS                                   | Not used (only total guests)  |
| TOTAL PAID                                         | Misleading — do not use       |
| Individual tax columns (CITY TAX, STATE TAX, etc.) | Recalculated from AmountGross |

### Filter Criteria

Only import records where:

- `STATUS` = "confirmed", OR
- `STATUS` = "canceled" AND `TOTAL PAYOUT` > 0 (partial payout from cancellation)

Skip: "inquiry", "closed", "declined", and canceled records with zero payout.

---

# Decisions

## Operational Decisions

| Question                                    | Decision                                                                |
| ------------------------------------------- | ----------------------------------------------------------------------- |
| Duplicate handling                          | Match on `reservationCode`, update existing record                      |
| Realised vs Planned split                   | Based on check-in date (past = `bnb`, future = `bnbplanned`)            |
| Listing "JaBaKi Temp / JaBaKi Garden House" | Maps to "Child Friendly"                                                |
| reservationDate                             | Available as "Creation Date" in Guesty — must be included in CSV export |
| Country mapping                             | Use existing MySQL `country` table (country name → ISO alpha-2)         |
| Import frequency                            | Bi-weekly, covering last month + future bookings                        |

## Remaining Gaps (Accepted)

| Gap                              | Acceptance Rationale                                      |
| -------------------------------- | --------------------------------------------------------- |
| Country empty for Airbnb         | Analytics only — can be enriched later from other sources |
| VRBO AmountGross incomplete      | Few VRBO bookings — approximation acceptable              |
| Website/Manual Stripe fee (4.3%) | Few direct bookings — approximation acceptable            |
| addInfo not available            | Not needed for regular operational imports                |
| phone not available              | Not critical — country deduction handled differently      |

## Open Question: Import Priority / Field Ownership

This Guesty CSV import would coexist with existing channel-specific imports (Airbnb payout files, Booking.com reservation statements). A decision is needed on:

- **Which import is the "source of truth" per field?**
- **Should Guesty import only fill empty fields, or overwrite?**
- **Should Guesty replace the channel-specific imports entirely, or complement them?**

This needs to be resolved before building the spec. The financial fields (AmountGross, AmountNett, AmountChannelFee) from Guesty are verified and reliable for Airbnb and Booking.com. But channel-specific imports provide richer data (country, phone, reservationDate, addInfo).

### Possible strategies:

1. **Guesty as primary** — use for all financial fields + basic booking data. Channel-specific imports only for enrichment (country, phone).
2. **Guesty as secondary** — channel-specific imports remain primary. Guesty only fills gaps or serves as validation.
3. **Guesty replaces all** — stop channel-specific imports entirely. Accept the data gaps.

No decision made yet — needs further consideration.
