# Banking Processor Refactoring - Impact Analysis

**Status**: Draft  
**Priority**: Medium  
**Estimated Effort**: 3-4 days  
**Trigger**: When adding 3rd bank type OR when maintenance becomes difficult

---

## Executive Summary

`BankingProcessor.tsx` is **2,179 lines** - more than 2x the maximum recommended size (1,000 lines). This document outlines a comprehensive refactoring plan to improve maintainability, testability, and extensibility.

**Current Status**: ✅ Production-ready but needs refactoring for long-term maintainability

---

## Problem Statement

### File Size Issues

- **2,179 lines** in single component
- 30+ state variables
- 25+ functions
- 4 tabs with mixed concerns
- Hard to maintain, test, and extend

### Current Issues

1. ✅ **FIXED**: Custom year filter (now uses generic `FilterPanel`)
2. ✅ **FIXED**: Records limit dropdown (now in `FilterPanel`)
3. ✅ **FIXED**: Unnecessary refresh button (removed)
4. ⚠️ **REMAINING**: All parsing logic in one component
5. ⚠️ **REMAINING**: Hard to add new banks (need to modify main component)
6. ⚠️ **REMAINING**: Difficult to test individual bank parsers
7. ⚠️ **REMAINING**: Tenant validation mixed with parsing logic

### Pattern Analysis Logic

Current table structure (`pattern_verb_patterns` - 3,256+ records):

```sql
id, administration, bank_account, verb, verb_company, verb_reference,
is_compound, reference_number, debet_account, credit_account,
occurrences, confidence, last_seen, sample_description,
created_at, updated_at
```

**Needs better documentation**:

- How `reference_number` is predicted
- How `debet_account` / `credit_account` are determined (given vs predicted)

---

## Current Architecture

### File Structure

```
BankingProcessor.tsx (2,179 lines)
├── Utility Functions (3)
│   ├── parseCSVRow
│   ├── processRevolutTransaction
│   ├── processCreditCardTransaction
│   └── processRabobankTransaction
│
└── BankingProcessor Component
    ├── State (30+ variables)
    ├── Functions (25+)
    └── UI (4 tabs)
        ├── Upload & Process
        ├── Mutaties (Transactions)
        ├── Check Banking Accounts
        └── STR Channel Revenue
```

### Supported Banks

1. **Rabobank** - CSV format (`CSV_[OA]*.csv`)
2. **Revolut** - TSV format
3. **Credit Card** - CSV format

---

## Proposed Architecture

### Phase 1: Extract Utilities (1 day)

**Goal**: Move utility functions to separate files

**New Structure**:

```
frontend/src/utils/banking/
├── csvParser.ts              # CSV parsing utilities
└── transactionProcessors.ts  # Bank-specific processors
```

**Benefits**:

- Reusable across components
- Easier to test
- Clearer separation of concerns

---

### Phase 2: Modular Bank Parsers (2-3 days)

**Goal**: Create extensible bank parser system

**New Structure**:

```
frontend/src/services/bankParsers/
├── types.ts                      # TypeScript interfaces
├── baseBankParser.ts             # Base class & utilities
├── tenantValidator.ts            # Centralized validation
├── bankParserRegistry.ts         # Auto-detect & register parsers
├── parsers/
│   ├── rabobankParser.ts         # Rabobank CSV parser
│   ├── revolutParser.ts          # Revolut TSV parser
│   ├── creditCardParser.ts       # Credit card parser
│   ├── ingParser.ts              # Future: ING bank
│   └── abnAmroParser.ts          # Future: ABN AMRO
└── index.ts                      # Export all
```

#### Core Interfaces

**BankParser Interface**:

```typescript
interface BankParser {
  name: string; // "Rabobank", "Revolut", etc.
  filePattern: RegExp; // /^CSV_[OA].*\.csv$/i
  supportedFormats: string[]; // ['.csv', '.tsv']

  parse(file: File, lookupData: LookupData): Promise<Transaction[]>;

  validateTenant(
    transactions: Transaction[],
    currentTenant: string,
    bankAccounts: BankAccount[],
  ): ValidationResult;
}
```

**ValidationResult Interface**:

```typescript
interface ValidationResult {
  valid: boolean;
  error?: string;
  suggestedTenant?: string;
  invalidIBANs?: string[];
}
```

#### Bank Parser Registry

**Auto-detect bank from filename**:

```typescript
const bankParsers: BankParser[] = [
  rabobankParser,
  revolutParser,
  creditCardParser,
  // Easy to add new banks here
];

export function detectBankParser(filename: string): BankParser | null {
  return bankParsers.find((parser) => parser.filePattern.test(filename));
}
```

#### Centralized Tenant Validation

**Single validation function for all banks**:

```typescript
export function validateBankingFile(
  transactions: Transaction[],
  currentTenant: string,
  bankAccounts: BankAccount[],
): ValidationResult {
  const ibans = [...new Set(transactions.map((t) => t.Ref1).filter(Boolean))];
  const invalidIBANs: string[] = [];
  let suggestedTenant: string | undefined;

  for (const iban of ibans) {
    const account = bankAccounts.find((ba) => ba.rekeningNummer === iban);
    if (account && account.administration !== currentTenant) {
      invalidIBANs.push(iban);
      suggestedTenant = account.administration;
    }
  }

  if (invalidIBANs.length > 0) {
    return {
      valid: false,
      error: `Account(s) ${invalidIBANs.join(", ")} belong to ${suggestedTenant}`,
      suggestedTenant,
      invalidIBANs,
    };
  }

  return { valid: true };
}
```

**Benefits**:

- Easy to add new banks (30 min vs hours)
- Each parser independently testable
- Clear separation of concerns
- Type-safe with TypeScript
- Centralized validation logic

---

### Phase 3: Extract Components (1-2 days)

**Goal**: Split large component into smaller, focused components

**New Structure**:

```
frontend/src/components/banking/
├── BankingProcessor.tsx (200 lines)    # Main container
├── BankingUploadTab.tsx (300 lines)    # File upload & processing
├── BankingMutatiesTab.tsx (400 lines)  # Transactions table
├── BankingAccountsTab.tsx (300 lines)  # Account checking
├── STRChannelTab.tsx (400 lines)       # STR revenue
├── hooks/
│   ├── useBankingData.ts               # Data fetching logic
│   └── useBankingFilters.ts            # Filter state management
└── utils/
    ├── csvParser.ts
    └── transactionProcessors.ts
```

**Benefits**:

- Each component < 500 lines (target) or < 1,000 lines (max)
- Easier to understand and maintain
- Better testability
- Clearer responsibilities

---

### Phase 4: Backend Validation (1-2 hours)

**Goal**: Add server-side tenant validation

**Changes**:

- Update `/api/banking/save-transactions` endpoint
- Add IBAN tenant validation on save
- Return 403 if IBAN doesn't belong to tenant
- Add audit logging for validation failures

**Benefits**:

- Security: Can't bypass client-side validation
- Audit trail for security incidents
- Consistent validation logic

---

## Implementation Plan

### Phase 1: Extract Utilities (1 day)

- [ ] Create `frontend/src/utils/banking/` folder
- [ ] Create `csvParser.ts` with CSV parsing utilities
- [ ] Create `transactionProcessors.ts` with bank processors
- [ ] Move utility functions from `BankingProcessor.tsx`
- [ ] Update imports in `BankingProcessor.tsx`
- [ ] Test all existing functionality

### Phase 2: Modular Bank Parsers (2-3 days)

#### Phase 2.1: Setup Infrastructure (2-3 hours)

- [ ] Create `frontend/src/services/bankParsers/` folder structure
- [ ] Create `types.ts` with TypeScript interfaces
- [ ] Create `baseBankParser.ts` with common utilities
- [ ] Create `tenantValidator.ts` with centralized validation
- [ ] Create `bankParserRegistry.ts` with auto-detection
- [ ] Create `parsers/` subfolder

#### Phase 2.2: Extract Rabobank Parser (1-2 hours)

- [ ] Create `parsers/rabobankParser.ts`
- [ ] Move Rabobank parsing logic
- [ ] Implement `BankParser` interface
- [ ] Add unit tests
- [ ] Test with existing CSV files

#### Phase 2.3: Extract Revolut Parser (1-2 hours)

- [ ] Create `parsers/revolutParser.ts`
- [ ] Move Revolut parsing logic
- [ ] Implement `BankParser` interface
- [ ] Add unit tests
- [ ] Test with existing TSV files

#### Phase 2.4: Extract Credit Card Parser (1 hour)

- [ ] Create `parsers/creditCardParser.ts`
- [ ] Move credit card parsing logic
- [ ] Implement `BankParser` interface
- [ ] Add unit tests
- [ ] Test with existing CSV files

#### Phase 2.5: Refactor Main Component (2-3 hours)

- [ ] Simplify `BankingProcessor.tsx` to use parser registry
- [ ] Remove old parsing logic
- [ ] Update to use `detectBankParser()`
- [ ] Update to use centralized `validateBankingFile()`
- [ ] Test all functionality

### Phase 3: Extract Components (1-2 days)

- [ ] Create `components/banking/` folder
- [ ] Extract `BankingUploadTab.tsx`
- [ ] Extract `BankingMutatiesTab.tsx`
- [ ] Extract `BankingAccountsTab.tsx`
- [ ] Extract `STRChannelTab.tsx`
- [ ] Create `useBankingData.ts` hook
- [ ] Create `useBankingFilters.ts` hook
- [ ] Simplify main `BankingProcessor.tsx` to container
- [ ] Test all tabs work correctly

### Phase 4: Backend Validation (1-2 hours)

- [ ] Update `/api/banking/save-transactions` endpoint
- [ ] Add IBAN tenant validation
- [ ] Add audit logging
- [ ] Test security validation
- [ ] Update API documentation

### Phase 5: Testing & Documentation (2-3 hours)

- [ ] Test all three bank types
- [ ] Test tenant validation for each bank
- [ ] Test with multiple files from different banks
- [ ] Update user documentation
- [ ] Update developer documentation
- [ ] Create "Adding a New Bank" guide

---

## Adding a New Bank (After Refactoring)

**Example: Adding ING Bank Support**

1. Create `parsers/ingParser.ts`:

```typescript
export const ingParser: BankParser = {
  name: "ING Bank",
  filePattern: /^ING_.*\.csv$/i,
  supportedFormats: [".csv"],

  async parse(file, lookupData) {
    // ING-specific parsing logic
  },

  validateTenant(transactions, tenant, accounts) {
    return validateBankingFile(transactions, tenant, accounts);
  },
};
```

2. Register in `bankParserRegistry.ts`:

```typescript
const bankParsers: BankParser[] = [
  rabobankParser,
  revolutParser,
  creditCardParser,
  ingParser, // ← Just add this line
];
```

**That's it!** Takes ~30 minutes instead of hours.

---

## Benefits After Refactoring

### Maintainability

- ✅ Each file < 1,000 lines (target: 500 lines)
- ✅ Clear separation of concerns
- ✅ Easy to find and fix bugs
- ✅ Single responsibility per file

### Testability

- ✅ Each parser independently testable
- ✅ Unit tests for utilities
- ✅ Component tests for UI
- ✅ Integration tests for workflows

### Extensibility

- ✅ Add new bank in ~30 minutes
- ✅ No risk of breaking existing banks
- ✅ Type-safe with TypeScript
- ✅ Auto-detection of bank type

### Code Quality

- ✅ Better code organization
- ✅ Reusable utilities
- ✅ Consistent validation logic
- ✅ Improved developer experience

---

## Estimated Effort

| Phase     | Description             | Time         |
| --------- | ----------------------- | ------------ |
| Phase 1   | Extract Utilities       | 1 day        |
| Phase 2   | Modular Bank Parsers    | 2-3 days     |
| Phase 3   | Extract Components      | 1-2 days     |
| Phase 4   | Backend Validation      | 1-2 hours    |
| Phase 5   | Testing & Documentation | 2-3 hours    |
| **Total** |                         | **4-6 days** |

---

## When to Start

### Recommended Trigger

**Option 1**: When adding 3rd bank type (e.g., ING, ABN AMRO)

- Pattern becomes clear with 3+ examples
- Immediate benefit from extensibility

**Option 2**: When maintenance becomes difficult

- Frequent bugs in parsing logic
- Hard to understand code flow
- Slow to make changes

**Option 3**: Scheduled technical debt sprint

- Allocate dedicated time
- No pressure from feature deadlines
- Can focus on quality

### Why Wait?

- Current solution works well ✅
- Refactoring takes time (4-6 days)
- Better to refactor when you have 3+ examples
- No immediate business need

### Why Start Now?

- File is already 2x maximum size
- Will only get harder to refactor later
- Improves developer productivity
- Reduces bug risk

---

## Success Criteria

- [ ] All existing functionality works (Rabobank, Revolut, Credit Card)
- [ ] Tenant validation works for all banks
- [ ] Adding a new bank takes < 1 hour
- [ ] Each parser has unit tests
- [ ] All files < 1,000 lines (target: 500 lines)
- [ ] Code is easier to understand and maintain
- [ ] Backend validates tenant on save
- [ ] Documentation updated

---

## Risks & Mitigation

### Risk: Breaking existing functionality

**Mitigation**:

- Keep old code until new code is tested
- Test each bank type thoroughly
- Use feature flag to switch between old/new implementation
- Incremental rollout (one bank at a time)

### Risk: Time investment without immediate benefit

**Mitigation**:

- Only refactor when adding 3rd bank OR maintenance issues arise
- Refactor incrementally (one phase at a time)
- Measure time saved on future changes

### Risk: TypeScript complexity

**Mitigation**:

- Start with simple interfaces
- Add complexity only when needed
- Document with examples
- Pair programming for complex parts

---

## Decision

**Current Status**: ✅ Production-ready, filters fixed

**Recommendation**: 📋 Add to backlog, start when:

1. Adding 3rd bank type, OR
2. Maintenance becomes difficult, OR
3. Scheduled technical debt sprint

**Priority**: Medium (nice to have, not urgent)

---

## Related Documents

- Bug Report (Solved): `.kiro/bug reports/Solved/20260207 1747 Import Banking Accounts Mutaties SOLVED.md`
- Generic Filter Spec: `.kiro/specs/Common/Filters a generic approach/`
- File Size Guidelines: `.kiro/steering/tech.md` (500 lines target, 1,000 max)

---

## Revision History

| Date       | Change                       | Author  |
| ---------- | ---------------------------- | ------- |
| 2026-02-07 | Initial analysis             | Kiro AI |
| 2026-02-07 | Filter fixes applied         | Kiro AI |
| 2026-02-07 | Consolidated impact analysis | Kiro AI |
