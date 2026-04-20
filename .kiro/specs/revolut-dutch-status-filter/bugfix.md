# Bugfix Requirements Document

## Introduction

Revolut CSV bank statements can be exported in different locales (Dutch, English, potentially others). The current status filter in `processRevolutTransaction` only checks for English status values (`REVERTED`, `PENDING`), so non-completed transactions in other languages pass through unfiltered. This causes pending transactions to be processed and imported into the database. Additionally, because pending transactions have empty `Saldo` and `Datum voltooid` (completion date) fields, the generated Ref2 contains `NaN`, which prevents the duplicate checker from detecting them when the same transaction later appears as completed with a valid balance.

**Root cause decision**: Rather than maintaining a growing list of status translations per language, the fix uses a **language-independent approach** — filtering on structural data fields (`Datum voltooid` and `Saldo`) that are always empty for non-completed transactions, regardless of export language.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a Revolut CSV transaction is not completed (e.g., status `IN BEHANDELING`, `PENDING`, or any other non-completed status in any language) AND the completion date (`Datum voltooid` / `Completed Date`) is empty AND the balance (`Saldo` / `Balance`) is empty THEN the system processes and imports the transaction instead of filtering it out

1.2 WHEN a non-completed transaction (with empty `Saldo`) is processed THEN the system generates a Ref2 containing `NaN` (e.g., `Albert Heijn_NaN_2026-04-16 12:07:04`) because `parseFloat(''.replace(',', '.')).toFixed(2)` produces `NaN`

1.3 WHEN the same transaction later appears as completed (with a valid `Saldo`) THEN the duplicate checker does not detect it as a duplicate because the Ref2 values differ (`Albert Heijn_NaN_2026-04-16` vs `Albert Heijn_1053.36_2026-04-16`)

1.4 WHEN the status filter only checks English values (`REVERTED`, `PENDING`) THEN transactions exported in Dutch (`IN BEHANDELING`, `TERUGGEDRAAID`, `GEWEIGERD`) or any other language bypass the filter entirely

### Expected Behavior (Correct)

2.1 WHEN a Revolut CSV transaction has an empty completion date (`Datum voltooid` / `Completed Date`) OR an empty balance (`Saldo` / `Balance`) THEN the system SHALL filter it out and NOT process or import it — regardless of the status text or export language

2.2 WHEN a transaction is filtered out due to missing completion date or balance THEN the system SHALL NOT generate a Ref2 with `NaN`

2.3 WHEN a transaction is re-uploaded after changing from pending to completed (now having both completion date and balance filled) THEN the duplicate checker SHALL correctly identify it using the completed Ref2 value, preventing double imports

2.4 The existing English status checks (`REVERTED`, `PENDING`) SHALL be kept as an additional safety layer alongside the structural field checks

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a Revolut CSV transaction has a filled completion date AND a filled balance (indicating a completed transaction) THEN the system SHALL CONTINUE TO process and import the transaction normally — regardless of export language

3.2 WHEN a completed Revolut transaction has a valid `Saldo` value THEN the system SHALL generate a Ref2 using `[beschrijving]_[saldo]_[datum voltooid]` (changed from `startdatum` to `datum voltooid` for more accurate duplicate detection based on settlement date)

3.3 WHEN a completed Revolut transaction is uploaded a second time THEN the duplicate checker SHALL CONTINUE TO detect it as a duplicate via matching Ref2 values

3.4 WHEN a Revolut CSV transaction has English status `REVERTED` or `PENDING` THEN the system SHALL CONTINUE TO filter it out (existing behavior preserved as secondary check)

---

## Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type RevolutTransaction
  OUTPUT: boolean

  // Language-independent: returns true when structural completion fields are missing
  RETURN X.completionDate IS EMPTY OR X.balance IS EMPTY
END FUNCTION
```

## Property Specification

```pascal
// Property: Fix Checking — Transactions with missing completion date or balance are filtered out
FOR ALL X WHERE isBugCondition(X) DO
  result ← processRevolutTransaction'(X)
  ASSERT result = [] (empty transaction list, nothing processed)
END FOR
```

## Preservation Goal

```pascal
// Property: Preservation Checking — Completed transactions behave identically
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT processRevolutTransaction(X) = processRevolutTransaction'(X)
END FOR
```
