# Implementation Plan: Credit Card Processing

## Overview

Replace the hardcoded `processCreditCardTransaction` function in `BankingProcessor.tsx` with a parameter-driven, modular credit card processor. Implementation spans backend (DatabaseManager lookup methods, BankingService extension, Ref2-based duplicate detection) and frontend (new `CreditCardProcessor.ts` module, LookupData extension, BankingProcessor delegation). The approach follows the same patterns established by `processRabobankTransaction` and `processRevolutTransaction`.

## Tasks

- [x] 1. Backend: Add credit card and exchange rate lookup methods to DatabaseManager
  - [x] 1.1 Implement `get_credit_card_lookups(administration=None)` in `backend/src/database.py`
    - Add method to `DatabaseManager` class following the `get_bank_account_lookups` pattern
    - Query `rekeningschema` where `JSON_EXTRACT(parameters, '$.credit_card') = true`
    - SELECT columns: `JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.iban')) AS iban`, `Account`, `JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.card_number')) AS card_number`, `administration`
    - Filter by `administration = %s` when parameter is provided, using parameterized query with `%s`
    - Return list of dicts with keys: `iban`, `Account`, `card_number`, `administration`
    - _Requirements: 1.4, 1.5_

  - [x] 1.2 Implement `get_exchange_rate_account(administration=None)` in `backend/src/database.py`
    - Add method to `DatabaseManager` class
    - Query `rekeningschema` where `JSON_EXTRACT(parameters, '$.exchange_rate_account') = true`
    - SELECT columns: `Account`, `administration`
    - Filter by `administration = %s` when parameter is provided
    - _Requirements: 3.4_

  - [x] 1.3 Write backend unit tests for new DatabaseManager methods in `backend/tests/unit/test_credit_card_lookups.py`
    - Use `mock_db` fixture from `conftest.py`, never import `mysql.connector` directly
    - Test `get_credit_card_lookups()` returns correct keys: `iban`, `Account`, `card_number`, `administration`
    - Test `get_credit_card_lookups(administration='TestTenant')` adds `AND administration = %s` filter
    - Test `get_exchange_rate_account()` returns correct keys: `Account`, `administration`
    - Test `get_exchange_rate_account(administration='TestTenant')` adds filter
    - Test empty result sets return empty lists
    - _Requirements: 1.4, 1.5, 3.4_

- [x] 2. Backend: Extend `get_lookups()` and add Ref2-based duplicate detection
  - [x] 2.1 Extend `BankingService.get_lookups()` in `backend/src/services/banking_service.py`
    - Add `credit_card_accounts = db.get_credit_card_lookups(administration=tenant)` call
    - Add `exchange_rate_accounts = db.get_exchange_rate_account(administration=tenant)` call
    - Add `'credit_card_accounts': credit_card_accounts` to the return dict
    - Add `'exchange_rate_account': exchange_rate_accounts[0]['Account'] if exchange_rate_accounts else None` to the return dict
    - _Requirements: 1.6, 3.4_

  - [x] 2.2 Add Ref2-based duplicate detection to `save_approved_transactions` in `backend/src/banking_processor.py`
    - Insert a Ref2 check BEFORE the existing fuzzy `TransactionAmount + TransactionDate + administration` duplicate check
    - When `Ref2` is non-empty after `.strip()`: execute `SELECT ID FROM mutaties WHERE Ref2 = %s AND administration = %s LIMIT 1`
    - If match found: `print(f"Skipping duplicate (Ref2 match): {ref2}")` and `continue`
    - If no match: fall through to existing fuzzy duplicate check
    - Use parameterized queries with `%s` placeholders, never f-string interpolation for values
    - _Requirements: 4.2, 4.3_

  - [x] 2.3 Write backend unit tests for Ref2 duplicate detection in `backend/tests/unit/test_banking_processor.py`
    - Test that a transaction with a Ref2 matching an existing record is skipped
    - Test that a transaction with a Ref2 NOT matching any existing record proceeds to save
    - Test that a transaction with empty Ref2 falls through to the existing fuzzy check
    - Test that `_FX` suffixed Ref2 values are also deduplicated correctly
    - Use `mock_db` fixture and `mock_connection` pattern from existing tests in the file
    - _Requirements: 4.2, 4.3_

- [x] 3. Backend: Register new parameter flags in ledger parameter definitions
  - [x] 3.1 Add `credit_card`, `card_number`, and `exchange_rate_account` definitions to `backend/src/config/ledger_parameters.json`
    - Add `credit_card` (type: boolean, module: FIN, label: "Credit Card Account" / "Creditcardrekening")
    - Add `card_number` (type: string, module: FIN, depends_on: "credit_card", label: "Card Number (last 4 digits)" / "Kaartnummer (laatste 4 cijfers)")
    - Note: `iban` already exists and is reused for credit card accounts (depends_on: "bank_account" — verify this also works when `credit_card` is true, or add a second iban entry with depends_on: "credit_card")
    - Add `exchange_rate_account` (type: boolean, module: FIN, label: "Exchange Rate Account" / "Koersverschillenrekening")
    - The AccountModal and chart_of_accounts_routes.py raw parameters mode already handle arbitrary parameter keys dynamically — no code changes needed in those files
    - _Requirements: 1.1, 1.2, 1.3, 3.4_

  - [x] 3.2 Verify `iban` dependency works for credit card accounts
    - The existing `iban` parameter has `depends_on: "bank_account"` — it only shows when `bank_account` is true
    - For credit card accounts, `iban` must also be visible when `credit_card` is true
    - If the AccountModal `depends_on` logic only supports a single key: either change `iban.depends_on` to support both, or add a separate `cc_iban` parameter with `depends_on: "credit_card"`
    - Check the AccountModal rendering logic for `depends_on` and adjust if needed
    - _Requirements: 1.2_

- [x] 4. Checkpoint — Ensure all backend tests pass
  - Run `pytest backend/tests/unit/test_credit_card_lookups.py backend/tests/unit/test_banking_processor.py -v`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Frontend: Extend LookupData interface and create CreditCardProcessor module
  - [x] 5.1 Extend `LookupData` interface in `frontend/src/components/BankingProcessor.tsx`
    - Add `CreditCardAccount` interface: `{ iban: string; Account: string; card_number: string; administration: string }`
    - Add `credit_card_accounts: CreditCardAccount[]` to `LookupData`
    - Add `exchange_rate_account: string | null` to `LookupData`
    - Export the `CreditCardAccount` interface
    - _Requirements: 1.6_

  - [x] 5.2 Create `frontend/src/components/banking/CreditCardProcessor.ts` module
    - Import `Transaction`, `LookupData`, `CreditCardAccount` from `../BankingProcessor`
    - Define and export `CreditCardProcessorResult` interface: `{ transactions: Transaction[]; warnings: string[] }`
    - Implement `processCreditCardTransactions(columns, index, lookupData, fileName)` returning `CreditCardProcessorResult`
    - Implement CSV row validation: return empty result for `columns.length < 13` or zero amount
    - Parse amount with comma-as-decimal (`columns[8].replace(',', '.')`) and round to 2 decimals
    - Resolve credit card account via `lookupData.credit_card_accounts.find(cc => cc.iban === columns[0])`
    - Throw descriptive Error when IBAN not found: `"Credit card rekening ${iban} is niet geconfigureerd voor deze tenant. Voeg deze toe in het Rekeningschema met de credit_card vlag."`
    - Build main transaction: negative amount = expense (Debet empty, Credit = ccLookup.Account), positive = credit (Debet = ccLookup.Account, Credit empty)
    - Set `ReferenceNumber` to empty string (for pattern matcher), `Ref1` = column 3, `Ref2` = column 6, `Ref3` = IBAN, `Ref4` = fileName
    - Implement `buildDescription()` helper: column 9 + optional `[{currency} {amount}]` suffix for foreign transactions
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.3, 5.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [x] 5.3 Implement exchange rate difference calculation in `CreditCardProcessor.ts`
    - Detect foreign transactions: columns 10, 11, 12 all populated with valid values
    - Calculate: `calculatedEurAmount = round(originalAmount / exchangeRate, 2)`, `exchangeRateDiff = round(absAmount - abs(calculatedEurAmount), 2)`
    - Use 0.005 threshold to avoid floating point noise
    - When exchange rate account not configured: add warning to `result.warnings`, skip FX transaction
    - When configured: create exchange rate transaction with `row_id = index + 5000`, `Ref2 = "${columns[6]}_FX"`
    - Positive diff (gain): `Credit = exchange_rate_account`; Negative diff (loss): `Debet = exchange_rate_account`
    - Description: `"Koersverschil ${currency} ${originalAmount} @ ${rate}"`
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8, 3.9_

- [x] 6. Frontend: Update BankingProcessor to delegate to CreditCardProcessor
  - [x] 6.1 Update IBAN validation in `processFiles()` for credit card files
    - In the IBAN validation loop, add a branch for `file.name.startsWith('CSV_CC_')` files
    - For credit card files: look up IBAN in `lookupData.credit_card_accounts` instead of `lookupData.bank_accounts`
    - If found in `credit_card_accounts`: validation passed (skip `bank_accounts` check)
    - If not found in either: show error message and return
    - _Requirements: 2.1, 2.2_

  - [x] 6.2 Update CSV_CC file processing delegation in `processFiles()`
    - Replace the `processCreditCardTransaction` call with `processCreditCardTransactions` from the new module
    - Import `processCreditCardTransactions` from `./banking/CreditCardProcessor`
    - Handle the `CreditCardProcessorResult` return type: spread `result.transactions` into `allTransactions`
    - Collect `result.warnings` and display as non-blocking notifications
    - _Requirements: 6.3_

  - [x] 6.3 Remove the old `processCreditCardTransaction` function from `BankingProcessor.tsx`
    - Delete the hardcoded function (lines ~210-241) that uses `'4002'`, `'2001'`, and IBAN-to-tenant mapping
    - Verify no other code references the old function
    - _Requirements: 2.5, 6.1_

- [x] 7. Checkpoint — Ensure frontend compiles and existing tests pass
  - Run `npx vitest --run` from `frontend/` directory
  - Verify TypeScript compilation with `npx tsc --noEmit` from `frontend/`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Frontend: Property-based tests for CreditCardProcessor
  - [x] 8.1 Create test generators and setup in `frontend/src/components/banking/__tests__/CreditCardProcessor.property.test.ts`
    - Import `fc` from `fast-check` and `processCreditCardTransactions` from `../CreditCardProcessor`
    - Implement `arbitraryIban()`: generates NL-format IBAN strings
    - Implement `arbitraryCsvRow(iban)`: generates valid 13-column arrays with YYYY-MM-DD dates, comma-decimal amounts (non-zero), random strings for descriptions
    - Implement `arbitraryForeignCsvRow(iban)`: extends `arbitraryCsvRow` with populated columns 10 (original amount), 11 (currency code), 12 (exchange rate > 0)
    - Implement `arbitraryLookupData(iban)`: generates `LookupData` with at least one `credit_card_accounts` entry matching the given IBAN, and an `exchange_rate_account`
    - Use minimum 100 iterations per property (`{ numRuns: 100 }`)
    - _Requirements: 6.4_

  - [x] 8.2 Write Property 1: CSV Parsing Validity
    - **Property 1: CSV Parsing Validity**
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.7**
    - For any valid 13-column CSV row with non-zero amount and configured IBAN: result has at least 1 transaction, `TransactionAmount > 0`, `TransactionDate` equals column 7, `Ref2` equals column 6
    - _Requirements: 7.2, 7.3, 7.4, 7.7_

  - [x] 8.3 Write Property 2: Lookup Resolution Determines Account Fields
    - **Property 2: Lookup Resolution Determines Account Fields**
    - **Validates: Requirements 2.1, 2.3, 2.4, 2.5**
    - For any CSV row where IBAN exists in `credit_card_accounts`: `Administration` equals lookup's `administration`, and `Credit` (expense) or `Debet` (credit) equals lookup's `Account` — never hardcoded values like `'4002'`, `'2001'`, `'PeterPrive'`
    - _Requirements: 2.1, 2.3, 2.4, 2.5_

  - [x] 8.4 Write Property 3: Missing IBAN Throws Descriptive Error
    - **Property 3: Missing IBAN Throws Descriptive Error**
    - **Validates: Requirements 2.2**
    - For any IBAN not in `credit_card_accounts`: `processCreditCardTransactions` throws Error whose message contains the missing IBAN string
    - _Requirements: 2.2_

  - [x] 8.5 Write Property 4: Exchange Rate Difference Calculation
    - **Property 4: Exchange Rate Difference Calculation**
    - **Validates: Requirements 3.2, 3.3**
    - For any foreign currency transaction: exchange rate diff = `abs(settlement) - abs(original / rate)`, and `mainAmount + exchangeRateDiff ≈ abs(settlement)` (within rounding tolerance)
    - _Requirements: 3.2, 3.3_

  - [x] 8.6 Write Property 5: Exchange Rate Transaction Debit/Credit Direction
    - **Property 5: Exchange Rate Transaction Debit/Credit Direction**
    - **Validates: Requirements 3.5, 3.6, 3.7**
    - For any non-zero exchange rate diff with configured account: positive diff → `Credit = exchange_rate_account`; negative diff → `Debet = exchange_rate_account`
    - _Requirements: 3.5, 3.6, 3.7_

  - [x] 8.7 Write Property 6: Reference Field Mapping
    - **Property 6: Reference Field Mapping**
    - **Validates: Requirements 4.1, 4.4, 5.3, 5.4, 7.5, 7.6**
    - For any CSV row producing a transaction: `Ref1` = column 3, `Ref2` = column 6, `Ref3` = column 0, `ReferenceNumber` = empty, `Debet` = empty for expense transactions
    - _Requirements: 4.1, 4.4, 5.3, 5.4, 7.5, 7.6_

- [x] 9. Frontend: Example-based unit tests for CreditCardProcessor
  - [x] 9.1 Create `frontend/src/components/banking/__tests__/CreditCardProcessor.test.ts`
    - Test EUR expense transaction: negative amount → `TransactionAmount` = absolute value, `Credit` = lookup Account, `Debet` = empty
    - Test EUR credit transaction: positive amount → `Debet` = lookup Account, `Credit` = empty
    - Test foreign currency transaction generates 2 transactions (main + exchange rate diff)
    - Test header row detection: row with `columns[0] === "Tegenrekening IBAN"` is skipped by caller (< 13 valid columns or zero amount)
    - Test row with < 13 columns returns empty result
    - Test row with zero amount returns empty result
    - Test comma decimal parsing: `"-20,58"` → amount 20.58
    - Test missing exchange rate account: main transaction created, warning added, no FX transaction
    - Test description building: EUR transaction gets plain description, foreign transaction gets `[USD 25,00]` suffix
    - Test IBAN not found throws Error with IBAN in message
    - Test `Ref1`, `Ref2`, `Ref3`, `Ref4` field mapping from correct CSV columns
    - _Requirements: 2.2, 3.1, 3.2, 3.9, 4.1, 4.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

- [x] 10. Checkpoint — Ensure all tests pass
  - Run `npx vitest --run` from `frontend/` directory
  - Run `pytest backend/tests/unit/test_credit_card_lookups.py backend/tests/unit/test_banking_processor.py -v`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Final checkpoint — Full test suite verification
  - Run full frontend test suite: `npx vitest --run` from `frontend/`
  - Run full backend unit test suite: `pytest backend/tests/unit/ -v`
  - Verify TypeScript compilation: `npx tsc --noEmit` from `frontend/`
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks are required — no optional tasks in this plan
- Each task references specific requirements for traceability
- Backend uses `DatabaseManager.execute_query()` with `%s` parameterized queries, never raw `mysql.connector`
- Frontend uses `fast-check` 4.4.0 via `import fc from 'fast-check'` for property-based tests
- Frontend uses Vitest for unit tests
- Backend uses pytest with `mock_db` fixture from `conftest.py`
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Checkpoints ensure incremental validation throughout implementation
