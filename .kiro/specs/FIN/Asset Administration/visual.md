# Asset Administration — Spec Overview

**Status:** Analysis
**Date:** 2026-03-26
**Module:** FIN

---

## Scope for myAdmin

myAdmin is a financial administration tool for small businesses and rental property owners. Not all 9 areas of generic asset administration apply. The table below shows what's relevant:

| #   | Area                      | Relevant for myAdmin | Notes                                                                    |
| --- | ------------------------- | -------------------- | ------------------------------------------------------------------------ |
| 1   | Identification            | ✅ Yes               | Asset register with unique ID, category, location                        |
| 2   | Inventory & Registry      | ✅ Yes               | Central asset list with status and specifications                        |
| 3   | Lifecycle Management      | ✅ Partial           | Acquisition and disposal — no industrial deployment/installation         |
| 4   | Maintenance & Monitoring  | ❌ No                | Out of scope — myAdmin is financial, not operational                     |
| 5   | Financial Management      | ✅ Yes (core)        | Depreciation, cost tracking, book value — integrates with rekeningschema |
| 6   | Compliance & Risk         | ✅ Partial           | Tax compliance (Belastingdienst), insurance tracking                     |
| 7   | Security & Access Control | ❌ No                | Handled by tenant/role system, not asset-specific                        |
| 8   | Reporting & Analytics     | ✅ Yes               | Asset list, depreciation schedule, book value reports                    |
| 9   | Governance & Policy       | ❌ No                | Out of scope for a small-business tool                                   |

---

## Architecture

```
                        ┌──────────────────────────┐
                        │    Asset Administration   │
                        └─────────────┬────────────┘
                                      │
      ┌──────────────────────────────┼──────────────────────────────┐
      │                              │                              │
      ▼                              ▼                              ▼
 1. Identification         2. Inventory & Registry        3. Lifecycle (partial)
      │                              │                              │
      ▼                              ▼                              ▼
 5. Financial Management   6. Compliance (partial)        8. Reporting & Analytics
     (core)
```

---

## Existing myAdmin integration

The chart of accounts (rekeningschema) already has fixed asset and equity accounts:

| Account | Name               | Category               |
| ------- | ------------------ | ---------------------- |
| 3060    | Vervoersmiddelen   | Materiële vaste activa |
| 3080    | Oude dag reserve   | Ondernemingsvermogen   |
| 3081    | Egalisatie reserve | Ondernemingsvermogen   |
| 3099    | Eigen Vermogen     | Ondernemingsvermogen   |

What's missing: an `assets` table to track individual assets linked to these accounts.

---

## 1. Identification

Every asset needs a unique identity:

- Asset name and description
- Category (vehicles, real estate, equipment, financial, IT)
- Serial number or registration (e.g., license plate, cadastral number)
- Location (address, property name)
- Linked rekeningschema account (e.g., 3060 for vehicles)

## 2. Inventory & Registry

Central repository of all asset information:

- Asset type and specifications
- Acquisition details (date, supplier, purchase price)
- Current status (active, disposed, under maintenance)
- Assigned tenant/administration
- Documents (purchase invoice, warranty, insurance policy — linked to Google Drive)

## 3. Lifecycle Management (partial)

Managing the asset from acquisition to disposal:

- Acquisition: purchase date, cost, supplier, invoice reference
- Operation: in-use period, assigned purpose
- Disposal: sale date, sale price, write-off reason
- Not in scope: industrial deployment, installation, refurbishment

## 5. Financial Management (core)

The primary reason for asset administration in myAdmin:

- Purchase cost and acquisition date
- Depreciation method (straight-line, declining balance)
- Useful life (years)
- Residual value
- Annual depreciation amount (calculated)
- Current book value (calculated)
- Total Cost of Ownership (purchase + maintenance costs)
- Link to rekeningschema accounts for automated journal entries

### Depreciation methods

| Method            | Formula                         | Use case                 |
| ----------------- | ------------------------------- | ------------------------ |
| Straight-line     | (Cost - Residual) / Useful life | Most common, simple      |
| Declining balance | Book value × Rate%              | Accelerated depreciation |
| No depreciation   | —                               | Land, financial assets   |

### Integration with bookkeeping

Depreciation entries are posted to:

- Debit: expense account (e.g., 4017 Transport Afschrijvingen)
- Credit: asset account (e.g., 3060 Vervoersmiddelen)

## 6. Compliance & Risk (partial)

Relevant for Dutch tax compliance:

- Belastingdienst asset reporting (Aangifte IB — box 3 assets)
- Not in scope: insurance management, safety inspections, certifications, risk assessments

## 8. Reporting & Analytics

Asset reports for the business owner:

- Asset register (full list with current book values)
- Depreciation schedule (per asset, per year)
- Asset summary by category
- Disposed assets report
- Integration with Aangifte IB for tax declaration

---

## 10. Implementation Considerations

### Current data model

In the current myAdmin implementation:

- An asset is acquired and booked as a transaction in `mutaties` with date, debet, and credit
- Ledger accounts relevant for assets get a `parameters` field with `"assets": true`
- Financial records for an asset can be retrieved by: `SELECT * FROM mutaties WHERE debet = <ledger_account> OR credit = <ledger_account>`
- Assets can be grouped/filtered by `ReferenceNumber` and/or `Ref1`
- Adding a new asset means adding the purchase transaction in `mutaties` and also adding the future depreciation records

### Depreciation strategy

Depreciation is calculated on-the-fly from the `assets` table, not pre-generated as future rows in `mutaties`.

**Why not pre-generate future depreciation rows (current approach):**

- Selling an asset early means finding and deleting future rows
- Changing depreciation method or useful life means delete + regenerate
- Future rows show up in reports for years that haven't happened yet

**New approach: generate depreciation entries on demand**

- Past depreciation entries stay in `mutaties` (they're real, booked transactions)
- Future depreciation is never stored — it's calculated when needed
- At period close (year-end, quarter-end, or month-end), generate that period's depreciation entry from the `assets` table
- Reports calculate remaining book value from: `purchase_amount - SUM(past depreciation transactions)`

### Depreciation frequency

| Frequency | Entries per year | Use case                                       |
| --------- | ---------------- | ---------------------------------------------- |
| Annual    | 1                | Simple, small businesses with annual reporting |
| Quarterly | 4                | Businesses that review quarterly P&L           |
| Monthly   | 12               | Accurate monthly P&L, larger businesses        |

- `depreciation_frequency` is stored per asset in the `assets` table (default: `annual`)
- The generation function divides the annual amount by the frequency
- Generation is triggered manually ("Generate depreciation for Q1 2026") or as part of a periodic close
- Example: car with €12,000 annual depreciation + quarterly frequency = 4 entries of €3,000

Depreciation entries are posted to:

- Debit: expense account (e.g., 4017 Transport Afschrijvingen)
- Credit: asset account (e.g., 3060 Vervoersmiddelen)

### Do we need an asset table?

Using only `mutaties` is tempting because the data is already there, but it has limitations:

| Aspect                 | Transactions only                   | Asset table + transactions             |
| ---------------------- | ----------------------------------- | -------------------------------------- |
| Purchase cost          | ✅ In the transaction               | ✅ Stored once                         |
| Depreciation method    | ❌ Nowhere to store                 | ✅ Per asset                           |
| Useful life (years)    | ❌ Nowhere to store                 | ✅ Per asset                           |
| Residual value         | ❌ Nowhere to store                 | ✅ Per asset                           |
| Asset name/description | ❌ Only transaction description     | ✅ Dedicated field                     |
| Disposal date/reason   | ❌ Hard to distinguish              | ✅ Clear status                        |
| Generate depreciation  | ❌ Missing method + life + residual | ✅ All metadata available              |
| Reporting              | ⚠️ Complex multi-transaction joins  | ✅ Simple: asset + linked transactions |

**Decision: lightweight asset table for metadata, transactions stay in `mutaties`.**

### Proposed `assets` table (minimal)

```sql
CREATE TABLE assets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    description VARCHAR(255) NOT NULL,
    category VARCHAR(50),                          -- vehicle, real_estate, equipment, financial, IT
    ledger_account VARCHAR(10) NOT NULL,            -- links to rekeningschema.Account (e.g., 3060)
    depreciation_account VARCHAR(10),               -- expense account (e.g., 4017)
    purchase_date DATE NOT NULL,
    purchase_amount DECIMAL(12,2) NOT NULL,
    depreciation_method ENUM('straight_line', 'declining_balance', 'none') DEFAULT 'straight_line',
    depreciation_frequency ENUM('annual', 'quarterly', 'monthly') DEFAULT 'annual',
    useful_life_years INT,
    residual_value DECIMAL(12,2) DEFAULT 0,
    status ENUM('active', 'disposed') DEFAULT 'active',
    disposal_date DATE NULL,
    disposal_amount DECIMAL(12,2) NULL,
    reference_number VARCHAR(50),                   -- optional: original invoice reference
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_administration (administration),
    INDEX idx_ledger_account (ledger_account),
    INDEX idx_status (status),
    FOREIGN KEY (administration) REFERENCES tenants(administration)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Data flow

```
1. User registers asset
   └── Insert into `assets` table (metadata)
   └── Insert purchase transaction into `mutaties` (debet: asset account, credit: bank)

2. Period close (year/quarter/month) — generate depreciation
   └── Read `assets` where status = 'active' and depreciation_method != 'none'
   └── Check if depreciation for this period already exists in `mutaties` (idempotent)
   └── Calculate period amount: (purchase_amount - residual_value) / useful_life_years / frequency
   └── Insert depreciation transaction into `mutaties`
       (debet: depreciation_account, credit: ledger_account)

3. User disposes asset
   └── Update `assets` status = 'disposed', disposal_date, disposal_amount
   └── Insert disposal transaction into `mutaties`
   └── Calculate and book any remaining book value write-off

4. Reporting
   └── Book value = purchase_amount - SUM(depreciation transactions in mutaties)
   └── No future rows to filter out — only real, booked entries
```

### Linking transactions to assets

Transactions in `mutaties` are linked to assets via `Ref1` using the pattern `ASSET-{asset_id}`.

See `.kiro/specs/FIN/mutaties_ref_fields.md` for the full Ref field usage guide.

| Transaction type | ReferenceNumber | Ref1         | Ref2                     | Ref3             | Ref4             |
| ---------------- | --------------- | ------------ | ------------------------ | ---------------- | ---------------- |
| Asset purchase   | Invoice number  | `ASSET-{id}` | —                        | Google Drive URL | Invoice filename |
| Depreciation     | `Asset-{id}`    | `ASSET-{id}` | Period (e.g., `2026-Q1`) | —                | —                |
| Disposal         | `Disposal-{id}` | `ASSET-{id}` | —                        | —                | —                |

Query all transactions for an asset:

```sql
SELECT * FROM mutaties
WHERE Ref1 = 'ASSET-42'
AND administration = 'GoodwinSolutions'
ORDER BY TransactionDate;
```

Calculate current book value:

```sql
SELECT a.purchase_amount - COALESCE(SUM(ABS(m.TransactionAmount)), 0) as book_value
FROM assets a
LEFT JOIN mutaties m ON m.Ref1 = CONCAT('ASSET-', a.id)
    AND m.administration = a.administration
    AND m.ReferenceNumber LIKE 'Asset-%'
WHERE a.id = 42;
```

Why `Ref1` and not a foreign key or link table:

- `ReferenceNumber` is already used for invoice numbers — can't overwrite
- `Ref3` / `Ref4` are reserved for Google Drive URLs and filenames
- A foreign key on `mutaties.id` breaks when transactions are re-imported (IDs change)
- A link table has the same ID stability problem
- `Ref1` is context-sensitive by design — for asset transactions it holds the asset reference

---

## Generic reference: All 9 areas

For completeness, here's the full framework. Areas not relevant for myAdmin are included for reference only.

### 4. Maintenance & Monitoring (not in scope)

- Preventive maintenance schedules
- Condition monitoring and repair logs
- Performance KPIs

### 7. Security & Access Control (not in scope)

- Physical security measures
- Cybersecurity for digital assets
- Asset-specific access permissions

### 9. Governance & Policy (not in scope)

- Asset management policies and procedures
- Roles and responsibilities
- Standards and best practices

### 10. Implemantation considerations

- In the current implementation an asset is acquired and booked as a transaction withj date debet and credit
- ledger accounts that are relevant will get a parameter "Assets"
- Financial records can be retrieved by select from mutaties(transactions) where debet = ledgeraccount or credit = ledgeraccount
- Assets can be grouped / filtered by referencenumber and/or Ref1
- Adding a new assets will be done by adding the purchase of the asset in the mutaties(transactions) and also add the depreciation records in the future
  --- It would be nice if these records can be generated as a function after the asset
  --- Question do we need an asset table or is the data in the transaction table with the link to invoices enough
