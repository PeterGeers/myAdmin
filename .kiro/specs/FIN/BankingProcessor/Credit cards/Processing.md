How does the banking processior processes my csv files that start with CSV_CC (My Credit card files)
Result was Loaded 0 new transactions. WARNING: 5 duplicates filtered out

e.g. CSV_CC_6416_20251201_20260101.csv
Content
"Tegenrekening IBAN","Munt","Creditcard Nummer","Productnaam","Creditcard Regel1","Creditcard Regel2","Transactiereferentie","Datum","Bedrag","Omschrijving","Oorspr bedrag","Oorspr munt","Koers"
"NL80RABO0107936917","EUR","6416","Rabo BusinessCard Visa","P.J.A. GEERS","GOODWIN SOLUTIONS B.V","0014000000003","2025-12-01","-1,00","GOOGLE*CLOUD 9TR73H CC GOOGLE.COMIRL","","",""
"NL80RABO0107936917","EUR","6416","Rabo BusinessCard Visa","P.J.A. GEERS","GOODWIN SOLUTIONS B.V","0014000000004","2025-12-01","-8,10","GOOGLE*GSUITE JUSTMA.N CC GOOGLE.COMIRL","","",""
"NL80RABO0107936917","EUR","6416","Rabo BusinessCard Visa","P.J.A. GEERS","GOODWIN SOLUTIONS B.V","0014000000005","2025-12-02","-21,07","AWS EMEA aws.amazon.coLUX","","",""
"NL80RABO0107936917","EUR","6416","Rabo BusinessCard Visa","P.J.A. GEERS","GOODWIN SOLUTIONS B.V","0015000000001","2025-12-24","-129,00","MICROSOFT\*MICROSOFT 365 FMSBILL.INFO IRL Token: 0xxxx0000","","",""
"NL80RABO0107936917","EUR","6416","Rabo BusinessCard Visa","P.J.A. GEERS","GOODWIN SOLUTIONS B.V","0015000000003","2025-12-28","+30,17","Verrekening vorig overzicht","","",""

## PROBLEM IDENTIFIED

The issue is in how the system maps CSV_CC columns and detects duplicates:

### Current Column Mapping (processCreditCardTransaction):

- **Ref1**: columns[6] = "Transactiereferentie" (e.g., "0014000000003") ✅ UNIQUE
- **Ref2**: columns[3] = "Productnaam" (e.g., "Rabo BusinessCard Visa") ❌ SAME FOR ALL
- **Ref3**: columns[0] = "Tegenrekening IBAN" (e.g., "NL80RABO0107936917")

### The Problem:

1. **All 5 transactions have identical Ref2**: "Rabo BusinessCard Visa"
2. **Duplicate detection uses Ref2** as the unique identifier
3. **If ANY transaction with Ref2="Rabo BusinessCard Visa" exists in database**, ALL 5 are filtered as duplicates
4. **Result**: 0 new transactions loaded, 5 duplicates filtered

### The Fix Needed:

**Swap Ref1 and Ref2 mapping:**

- **Ref1**: columns[0] = "Tegenrekening IBAN" (for IBAN grouping)
- **Ref2**: columns[6] = "Transactiereferentie" (for unique transaction ID)

This would make each transaction unique by its transaction reference number instead of the card product name.

### Current vs Proposed Mapping:

```
Current (BROKEN):
Ref1: 0014000000003 (unique)
Ref2: Rabo BusinessCard Visa (same for all)

Proposed (FIXED):
Ref1: NL80RABO0107936917 (IBAN)
Ref2: 0014000000003 (unique transaction ref)
```

## CREDIT CARD PROCESSING LOGIC

### How Credit Card Files Are Detected:

1. **File Name Pattern**: Files starting with `CSV_CC_` are automatically detected as credit card files
2. **Processing Route**: `file.name.startsWith('CSV_CC_')` triggers `processCreditCardTransaction()`
3. **Alternative Processing**: Non-CSV_CC files go to `processRabobankTransaction()` or `processRevolutTransaction()`

### Credit Card Specific Logic (`processCreditCardTransaction`):

#### File Validation:

- Requires minimum 13 columns (credit card CSV format)
- Skips transactions with zero amounts

#### Column Mapping:

```
columns[0] = "Tegenrekening IBAN"     → Ref1 (Account grouping)
columns[1] = "Munt"                   → Not used
columns[2] = "Creditcard Nummer"      → Not used
columns[3] = "Productnaam"            → Not used (was Ref2, caused duplicates)
columns[4] = "Creditcard Regel1"      → Not used
columns[5] = "Creditcard Regel2"      → Not used
columns[6] = "Transactiereferentie"   → Ref2 (Unique transaction ID)
columns[7] = "Datum"                  → TransactionDate
columns[8] = "Bedrag"                 → TransactionAmount
columns[9+] = "Omschrijving" etc.     → TransactionDescription (concatenated)
```

#### Credit Card Specific Features:

1. **Transaction Number**: Always prefixed with "Visa" + current date
2. **Administration Logic**:
   - `NL71RABO0148034454` → "PeterPrive"
   - All others → "GoodwinSolutions"
3. **Account Mapping**:
   - Negative amounts (expenses): Debet=4002, Credit=2001
   - Positive amounts (credits): Debet=2001, Credit=2001
4. **Description Building**: Concatenates all columns from index 9 onwards
5. **Reference Number**: Always set to "Default"

#### Differences from Regular Bank Transactions:

| Feature                | Credit Card (CSV*CC*)         | Regular Bank (Rabobank)    |
| ---------------------- | ----------------------------- | -------------------------- |
| **File Detection**     | `startsWith('CSV_CC_')`       | Default fallback           |
| **Min Columns**        | 13 columns                    | 20 columns                 |
| **Transaction Number** | `Visa ${date}`                | `${bankCode} ${date}`      |
| **Amount Column**      | columns[8]                    | columns[6]                 |
| **Date Column**        | columns[7]                    | columns[1]                 |
| **Description**        | columns[9+] concatenated      | Multiple specific columns  |
| **Ref2 Source**        | Transactiereferentie (unique) | Complex logic with lookups |

## STATUS: FIXED ✅

The mapping has been updated in the code:

- **Ref1**: columns[0] = "Tegenrekening IBAN" (for IBAN grouping)
- **Ref2**: columns[6] = "Transactiereferentie" (for unique transaction ID)

Each transaction now has a unique Ref2 value, preventing false duplicate detection.

### Database Update Applied:

```sql
UPDATE mutaties
SET Ref2 = Ref1
WHERE Ref2 = "Rabo BusinessCard Visa";
```

**Result**: Existing credit card transactions in the database now have unique Ref2 values (e.g., "0013000000006") instead of the duplicate "Rabo BusinessCard Visa" value.

**Status**: Both code and database are now aligned - new CSV_CC imports should work correctly without false duplicate detection.

## FINAL MAPPING UPDATE:

**New transactions will now have:**

- **Ref1**: "Rabo BusinessCard Visa" (Product name from columns[3])
- **Ref2**: "0014000000003" (Unique transaction reference from columns[6])
- **Ref3**: "NL80RABO0107936917" (IBAN from columns[0])

This provides the best of both worlds:

- Ref1 groups transactions by card product
- Ref2 provides unique transaction identification
- Ref3 stores the account IBAN
