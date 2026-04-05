# Debet/Credit Account Validation Issue

## Problem

The `Debet` and `Credit` columns in the `mutaties` table can contain account numbers that don't exist in the `rekeningschema` table for that tenant. This is not enforced anywhere.

## What Happens in the Views

### vw_debetmutaties

```sql
FROM mutaties m
LEFT JOIN rekeningschema r ON m.Debet = r.Account AND m.administration = r.administration
```

### vw_creditmutaties

```sql
FROM mutaties m
LEFT JOIN rekeningschema r ON m.Credit = r.Account AND m.administration = r.administration
```

### vw_mutaties

```sql
-- Debet side
SELECT r.Belastingaangifte AS Aangifte, ..., d.Reknum, d.AccountName, d.Parent, d.VW, ...
FROM vw_debetmutaties d
LEFT JOIN rekeningschema r ON d.Reknum = r.Account AND d.administration = r.administration
UNION ALL
-- Credit side
SELECT r.Belastingaangifte AS Aangifte, ..., c.Reknum, c.AccountName, c.Parent, c.VW, ...
FROM vw_creditmutaties c
LEFT JOIN rekeningschema r ON c.Reknum = r.Account AND c.administration = r.administration
```

### Impact When Account Doesn't Exist in rekeningschema

Because all joins are `LEFT JOIN`, when a Debet or Credit account doesn't exist in `rekeningschema`:

| Column                         | Value                                          |
| ------------------------------ | ---------------------------------------------- |
| `Reknum`                       | The account number from mutaties (still shows) |
| `AccountName`                  | `NULL`                                         |
| `Parent`                       | `NULL`                                         |
| `VW`                           | `NULL`                                         |
| `Aangifte` (Belastingaangifte) | `NULL`                                         |

This means:

- The transaction still appears in `vw_mutaties` but with NULL metadata
- Reports that group by `Parent`, `VW`, or `Aangifte` will have an "unknown" bucket
- P&L and balance sheet reports will miss these transactions (they filter on `VW = 'Y'` or `VW = 'N'`)
- Tax declarations (BTW, IB) that filter on `Aangifte` will silently exclude these transactions
- **Transactions with invalid accounts effectively become invisible in reports**

## Options to Improve

### Option 1: Application-Level Validation on Insert (moderate effort)

Validate Debet and Credit accounts against `rekeningschema` before inserting into `mutaties`. Reject or flag transactions with unknown accounts.

Where to add:

- `database.py` → `save_transactions()` and `save_single_transaction()`
- `banking_processor.py` → during CSV import
- Pattern analyzer → when applying patterns

Pros: Prevents bad data from entering the system, immediate user feedback
Cons: Requires changes in multiple insert paths, existing bad data not fixed

### Option 2: Database-Level Foreign Key Constraint (Recommended — cleanest)

Add a foreign key from `mutaties.Debet` → `rekeningschema.Account` (scoped by `administration`). Same for `Credit`.

**Railway fully supports this** — it runs standard MySQL 8.0, so FK constraints work identically to local Docker.

#### Prerequisites

1. Add a `UNIQUE` key on `rekeningschema(Account, administration)` — currently only has a non-unique index `AccountCode`
2. Clean up existing invalid data in `mutaties` (rows where Debet/Credit don't match any account in rekeningschema)
3. NULL values in Debet/Credit are fine — MySQL FKs allow NULLs by default

#### Migration Steps

```sql
-- Step 1: Find existing violations (run first to assess scope)
SELECT m.ID, m.Debet, m.Credit, m.administration
FROM mutaties m
LEFT JOIN rekeningschema r1 ON m.Debet = r1.Account AND m.administration = r1.administration
LEFT JOIN rekeningschema r2 ON m.Credit = r2.Account AND m.administration = r2.administration
WHERE (m.Debet IS NOT NULL AND m.Debet != '' AND r1.Account IS NULL)
   OR (m.Credit IS NOT NULL AND m.Credit != '' AND r2.Account IS NULL);

-- Step 2: Add unique key on rekeningschema
ALTER TABLE rekeningschema
ADD UNIQUE KEY uk_account_admin (Account, administration);

-- Step 3: Add FK constraints (only after violations are resolved)
ALTER TABLE mutaties
ADD CONSTRAINT fk_mutaties_debet
  FOREIGN KEY (Debet, administration)
  REFERENCES rekeningschema(Account, administration);

ALTER TABLE mutaties
ADD CONSTRAINT fk_mutaties_credit
  FOREIGN KEY (Credit, administration)
  REFERENCES rekeningschema(Account, administration);
```

#### Handling Violations

Options for existing bad data:

- **Add missing accounts** to `rekeningschema` (preferred if they're real accounts)
- **Move to a holding account** (e.g., set Debet/Credit to a generic "Unknown" account in rekeningschema)
- **Delete** if they're test/garbage data

Pros: Enforced at database level, impossible to bypass, works on Railway
Cons: Requires data cleanup first, breaks any import flow that doesn't pre-validate

### Option 3: Validation Report / Dashboard Warning (low effort, no prevention)

Add a query/endpoint that finds transactions with accounts not in `rekeningschema`. Show as a warning in the banking module or admin dashboard.

Pros: Quick to implement, surfaces existing problems, no risk of breaking imports
Cons: Doesn't prevent new bad data

### Option 4: Change Views to INNER JOIN (not recommended)

Change `LEFT JOIN` to `INNER JOIN` so transactions with invalid accounts are excluded entirely.

Pros: Clean reports, no NULL values
Cons: Transactions silently disappear — worse than the current situation

## Implementation Status

### ✅ Phase 1: Database Constraints (2026-04-05) — DONE

1. **Violation check**: Zero violations found across all 3 administrations (52,731 transactions)
2. **UNIQUE key added**: `uk_account_admin (Account, administration)` on `rekeningschema` — no duplicates
3. **FK constraint Debet**: `fk_mutaties_debet` — tested and working
4. **FK constraint Credit**: `fk_mutaties_credit` — tested and working
5. **Verification**: Invalid Debet `9999` → Rejected (Error 1452) / Valid accounts → Accepted

### ✅ Phase 2: Backend Error Handling (2026-04-05) — DONE

- [x] `database.py` → `execute_query()` catches `IntegrityError` errno 1452 and raises `ValueError` with user-friendly message ("Debet/Credit account does not exist in the chart of accounts")
- [x] All route handlers already catch `Exception` and return `str(e)` — message flows to frontend automatically

### 🔧 Phase 3: Frontend AccountSelect Component — IN PROGRESS

Reusable `AccountSelect` dropdown that replaces free-text `<Input>` fields for Debet/Credit with a searchable select showing only valid accounts from `rekeningschema`.

#### Backend

- [x] New lightweight endpoint `GET /api/accounts/lookup` — returns `Account` + `AccountName` for current tenant (no admin role required, just authenticated). Added to `chart_of_accounts_routes.py`.

#### Frontend

- [x] Create `frontend/src/hooks/useAccountLookup.ts` — custom hook that fetches and caches accounts from `/api/accounts/lookup` per tenant
- [x] Create `frontend/src/components/common/AccountSelect.tsx` — reusable searchable select component (Chakra UI datalist). Shows `Account - AccountName`, filters as user types
- [x] Replace Debet/Credit `<Input>` in `BankingProcessor.tsx` transaction table with `<AccountSelect>`
- [x] Replace Debet/Credit `<Input>` in `BankingProcessor.tsx` edit modal with `<AccountSelect>`
- [x] Replace Debet/Credit `<Input>` in `PDFUploadForm.tsx` invoice approval with `<AccountSelect>`
- [ ] Test: verify dropdown loads accounts, search works, selection updates transaction

### 📋 Phase 4: Docker Databases

- [x] Take fresh backup from Railway production (includes FK constraints)
- [x] Reload backup Railway 20260405.sql into Docker `finance and `testfinance` databases
