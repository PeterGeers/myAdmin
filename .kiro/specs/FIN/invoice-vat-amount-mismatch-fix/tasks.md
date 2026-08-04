# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - VAT Amount Ignored When Zero (Template Fallback)
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the system uses a stale template VAT amount instead of the parsed €0.00
  - **Scoped PBT Approach**: Scope the property to the concrete failing case: AI extraction returns `vat_amount: 0.0`, no VAT transaction in the formatted list, but template transactions exist with a non-zero historical VAT amount
  - **Bug Condition**: `isBugCondition(input)` where `input.parsed_vat_amount == 0.0 AND len(formatted_transactions) == 1 (no VAT line) AND template_transactions[1].TransactionAmount > 0`
  - Test that `prepare_new_transactions` with `vendor_data` missing `vat_amount` key AND a template with non-zero BTW amount produces a BTW record with amount != 0.0 (demonstrating the bug)
  - Specifically: build `vendor_data` without `vat_amount` key (simulating the omission in `invoice_service.py`), pass template with `TransactionAmount: 6.37` for the second record, assert the second prepared transaction has `TransactionAmount == 0.0` (expected behavior — will FAIL on unfixed code)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (the BTW record gets 6.37 from template instead of 0.0 — this proves the bug exists)
  - Document counterexample: `prepare_new_transactions([{...}, {TransactionAmount: 6.37}], {vendor_data: {date: "2026-07-10", total_amount: 6.52, description: "SV2SU1ZT0006"}})` → second transaction amount is 6.37 instead of 0.0
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Zero VAT Amount Propagation Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: `prepare_new_transactions` with `vendor_data` containing `vat_amount: 19.85` correctly uses 19.85 for BTW record on unfixed code
  - Observe: `prepare_new_transactions` with `vendor_data` containing `vat_amount: 6.37` correctly uses 6.37 for BTW record on unfixed code
  - Observe: Booking.com vendor_data with `accommodation_name`, `commission_type`, `invoice_number` correctly formats descriptions and references on unfixed code
  - Write property-based test using fast-check: for all `vat_amount > 0` in `vendor_data`, the second prepared transaction SHALL have `TransactionAmount == vendor_data.vat_amount` regardless of template's historical amount
  - Write preservation test: for all `vendor_data` with booking-specific fields, description formatting and Ref1/Ref2 assignment remain unchanged
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior for non-zero VAT amounts is already correct)
  - _Requirements: 3.1, 3.4, 3.5_

- [x] 3. Fix VAT amount mismatch bug
  - [x] 3.1 Fix vat_amount propagation in invoice_service.py (template path)
    - In `process_invoice_file`, template path (~line 400): always set `vat_amount` in `vendor_data` from the AI extraction result
    - Change the `vendor_data` construction to include `vat_amount` unconditionally: `vendor_data["vat_amount"] = first_tx.get("vat_amount", 0)`
    - Keep the existing override from second VAT-description transaction as a refinement (if a VAT line exists, use its amount), but ensure the key is always present with at least 0
    - _Bug_Condition: isBugCondition(input) where parsed_vat_amount == 0.0 AND no VAT transaction in formatted list_
    - _Expected_Behavior: vendor_data always contains vat_amount key from parsed extraction data_
    - _Preservation: Non-zero VAT amounts continue to work; booking-specific fields unchanged_
    - _Requirements: 2.1, 2.2, 3.1, 3.5_

  - [x] 3.2 Remove unsafe template fallback in transaction_logic.py
    - In `prepare_new_transactions`, for `i == 1` (VAT transaction): change fallback from `template.get("TransactionAmount", 0)` to just `0`
    - Current: `amount = vendor_data.get("vat_amount", template.get("TransactionAmount", 0))`
    - Fixed: `amount = vendor_data.get("vat_amount", 0)`
    - This ensures that even if `vat_amount` is somehow missing from `vendor_data`, the system defaults to 0 rather than a stale template value
    - _Bug_Condition: vendor_data missing vat_amount key AND template has historical non-zero BTW amount_
    - _Expected_Behavior: VAT amount comes from parsed data, never from template history_
    - _Preservation: When vendor_data contains vat_amount (normal case), behavior is identical_
    - _Requirements: 2.3, 3.1, 3.4_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - VAT Amount Correctly Propagated
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (BTW record uses parsed €0.00)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — BTW record now gets 0.0 from vendor_data)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Zero VAT Amount Propagation Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — non-zero VAT amounts still work correctly)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest tests/unit/test_transaction_logic.py -v`
  - Verify no other tests broken by the changes
  - Ensure all tests pass, ask the user if questions arise
