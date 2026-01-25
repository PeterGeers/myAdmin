**Current Issues**:

- All parsing logic in one large component (`BankingProcessor.tsx`)
- Hard to add new banks (need to modify main component)
- Difficult to test individual bank parsers
- Tenant validation mixed with parsing logic


- [ ] The logic how the patterns Referencenumber and Debet or Credit are determined need better explanation:
Current table structure (has already over 3256 freciords) :
SELECT COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'finance' 
  AND TABLE_NAME = 'pattern_verb_patterns'
ORDER BY ORDINAL_POSITION;

id,
administration
bank_account
verb
verb_company
verb_reference
is_compound
reference_number        Need to be predicted
debet_account           Is given or need to be oredicted
credit_account          Is given or need to be oredicted
occurrences
confidence
last_seen
sample_description
created_at
updated_at

### Proposed Architecture

#### 1. Modular File Structure

```
frontend/src/
├── components/
│   └── BankingProcessor.tsx              # Main component (simplified)
├── services/
│   └── bankParsers/
│       ├── types.ts                      # TypeScript interfaces
│       ├── baseBankParser.ts             # Base class & utilities
│       ├── tenantValidator.ts            # Centralized validation
│       ├── bankParserRegistry.ts         # Auto-detect & register parsers
│       ├── parsers/
│       │   ├── rabobankParser.ts         # Rabobank CSV parser
│       │   ├── revolutParser.ts          # Revolut TSV parser
│       │   ├── creditCardParser.ts       # Credit card parser
│       │   ├── ingParser.ts              # Future: ING bank
│       │   └── abnAmroParser.ts          # Future: ABN AMRO
│       └── index.ts                      # Export all
└── types/
    └── banking.ts                         # Shared types

backend/src/
├── app.py                                 # Save endpoint with validation
└── banking_processor.py                   # Backup/utility functions
```

#### 2. Core Interfaces

**BankParser Interface**:

```typescript
interface BankParser {
  name: string; // "Rabobank", "Revolut", etc.
  filePattern: RegExp; // /^CSV_[OA].*\.csv$/i
  supportedFormats: string[]; // ['.csv', '.tsv']

  // Parse file into transactions
  parse(file: File, lookupData: LookupData): Promise<Transaction[]>;

  // Validate transactions belong to tenant
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

#### 3. Bank Parser Registry

**Auto-detect bank from filename**:

```typescript
// bankParserRegistry.ts
const bankParsers: BankParser[] = [
  rabobankParser,
  revolutParser,
  creditCardParser,
  // Easy to add new banks here
];

export function detectBankParser(filename: string): BankParser | null {
  return bankParsers.find((parser) => parser.filePattern.test(filename));
}

export function getAllParsers(): BankParser[] {
  return bankParsers;
}
```

#### 4. Centralized Tenant Validation

**Single validation function for all banks**:

```typescript
// tenantValidator.ts
export function validateBankingFile(
  transactions: Transaction[],
  currentTenant: string,
  bankAccounts: BankAccount[],
): ValidationResult {
  // Extract unique IBANs
  const ibans = [...new Set(transactions.map((t) => t.Ref1).filter(Boolean))];

  const invalidIBANs: string[] = [];
  let suggestedTenant: string | undefined;

  // Check each IBAN
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

#### 5. Example Bank Parser

**Rabobank Parser**:

```typescript
// parsers/rabobankParser.ts
export const rabobankParser: BankParser = {
  name: "Rabobank",
  filePattern: /^CSV_[OA].*\.csv$/i,
  supportedFormats: [".csv"],

  async parse(file: File, lookupData: LookupData): Promise<Transaction[]> {
    const text = await file.text();
    const rows = text
      .split("\n")
      .filter((row) => row.trim())
      .slice(1); // Skip header

    return rows
      .map((row, index) => {
        const columns = parseCSVRow(row);
        return this.parseRow(columns, index, lookupData, file.name);
      })
      .filter(Boolean);
  },

  parseRow(
    columns: string[],
    index: number,
    lookupData: LookupData,
    fileName: string,
  ): Transaction | null {
    if (columns.length < 20) return null;

    const amountStr = columns[6] || "0";
    const isNegative = amountStr.startsWith("-");
    const amount = parseFloat(amountStr.replace(/[+-]/g, "").replace(",", "."));

    if (amount === 0) return null;

    const iban = columns[0] || "";
    const bankLookup = lookupData.bank_accounts.find(
      (ba) => ba.rekeningNummer === iban,
    );

    // ... rest of parsing logic

    return {
      row_id: index,
      TransactionNumber: `RABO ${new Date().toISOString().split("T")[0]}`,
      TransactionDate: columns[4] || "",
      TransactionDescription: this.buildDescription(columns),
      TransactionAmount: amount,
      Debet: isNegative ? "" : bankLookup?.Account || "1002",
      Credit: isNegative ? bankLookup?.Account || "1002" : "",
      ReferenceNumber: "",
      Ref1: iban,
      Ref2: parseInt(columns[3] || "0").toString(),
      Ref3: "",
      Ref4: fileName,
      administration: bankLookup?.administration || "GoodwinSolutions",
    };
  },

  buildDescription(columns: string[]): string {
    return [columns[9], columns[19], columns[20], columns[21]]
      .filter((field) => field?.trim() && field.trim() !== "NA")
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
  },

  validateTenant(transactions, currentTenant, bankAccounts) {
    return validateBankingFile(transactions, currentTenant, bankAccounts);
  },
};
```

#### 6. Simplified Main Component

**BankingProcessor.tsx** (simplified):

```typescript
const processFiles = useCallback(async () => {
  if (selectedFiles.length === 0) {
    setMessage("Please select at least one file to process");
    return;
  }

  try {
    setLoading(true);

    // Load lookup data if needed
    if (lookupData.bank_accounts.length === 0) {
      const response = await authenticatedGet("/api/banking/lookups");
      const data = await response.json();
      if (data.success) setLookupData(data);
    }

    const currentTenant = localStorage.getItem("selectedTenant");
    if (!currentTenant) {
      setMessage("Error: No tenant selected");
      setLoading(false);
      return;
    }

    const allTransactions: Transaction[] = [];

    // Process each file
    for (const file of selectedFiles) {
      // Auto-detect bank parser
      const parser = detectBankParser(file.name);

      if (!parser) {
        setMessage(`Unsupported file format: ${file.name}`);
        setLoading(false);
        return;
      }

      // Parse file
      const transactions = await parser.parse(file, lookupData);

      // Validate tenant
      const validation = parser.validateTenant(
        transactions,
        currentTenant,
        lookupData.bank_accounts,
      );

      if (!validation.valid) {
        setMessage(validation.error!);
        setLoading(false);
        return;
      }

      allTransactions.push(...transactions);
    }

    // Check for duplicates
    const duplicateCheck = await checkDuplicates(allTransactions);

    // Display for review
    setTransactions(duplicateCheck.filtered);
    setMessage(duplicateCheck.message);
  } catch (error) {
    setMessage(`Error: ${error}`);
  } finally {
    setLoading(false);
  }
}, [selectedFiles, lookupData]);
```

### Implementation Task List

#### Phase 2.1: Setup Infrastructure (2-3 hours)

- [ ] Create folder structure: `frontend/src/services/bankParsers/`
- [ ] Create `types.ts` with all TypeScript interfaces
- [ ] Create `baseBankParser.ts` with common utilities
- [ ] Create `tenantValidator.ts` with centralized validation
- [ ] Create `bankParserRegistry.ts` with auto-detection logic
- [ ] Create `parsers/` subfolder for individual bank parsers

#### Phase 2.2: Extract Rabobank Parser (1-2 hours)

- [ ] Create `parsers/rabobankParser.ts`
- [ ] Move Rabobank parsing logic from `BankingProcessor.tsx`
- [ ] Implement `BankParser` interface
- [ ] Add unit tests for Rabobank parser
- [ ] Test with existing Rabobank CSV files

#### Phase 2.3: Extract Revolut Parser (1-2 hours)

- [ ] Create `parsers/revolutParser.ts`
- [ ] Move Revolut parsing logic from `BankingProcessor.tsx`
- [ ] Implement `BankParser` interface
- [ ] Add unit tests for Revolut parser
- [ ] Test with existing Revolut TSV files

#### Phase 2.4: Extract Credit Card Parser (1 hour)

- [ ] Create `parsers/creditCardParser.ts`
- [ ] Move credit card parsing logic from `BankingProcessor.tsx`
- [ ] Implement `BankParser` interface
- [ ] Add unit tests for credit card parser
- [ ] Test with existing credit card CSV files

#### Phase 2.5: Refactor Main Component (2-3 hours)

- [ ] Simplify `BankingProcessor.tsx` to use parser registry
- [ ] Remove old parsing logic (now in individual parsers)
- [ ] Update to use `detectBankParser()` for auto-detection
- [ ] Update to use centralized `validateBankingFile()`
- [ ] Test all existing functionality still works

#### Phase 2.6: Backend Save Validation (1-2 hours)

- [ ] Update `/api/banking/save-transactions` endpoint
- [ ] Add IBAN tenant validation on save
- [ ] Return 403 if IBAN doesn't belong to tenant
- [ ] Add audit logging for validation failures
- [ ] Test security validation works

#### Phase 2.7: Testing & Documentation (2-3 hours)

- [ ] Test all three bank types (Rabobank, Revolut, Credit Card)
- [ ] Test tenant validation for each bank
- [ ] Test with multiple files from different banks
- [ ] Update user documentation
- [ ] Update developer documentation
- [ ] Create "Adding a New Bank" guide

### Benefits After Refactoring

✅ **Easy to Add New Banks**:

```typescript
// Just create a new parser file and register it
// Takes ~30 minutes instead of hours
```

✅ **Easy to Test**:

```typescript
// Each parser can be unit tested independently
// No need to test entire component
```

✅ **Easy to Maintain**:

```typescript
// Bug in Rabobank parser? Only touch rabobankParser.ts
// No risk of breaking other banks
```

✅ **Better Code Organization**:

```typescript
// Clear separation of concerns
// Each file has single responsibility
```

✅ **Type Safety**:

```typescript
// TypeScript interfaces ensure consistency
// Compile-time checks for all parsers
```

### Adding a New Bank (After Refactoring)

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

2. Register in `index.ts`:

```typescript
export { ingParser } from "./parsers/ingParser";
```

3. Add to registry in `bankParserRegistry.ts`:

```typescript
import { ingParser } from "./parsers/ingParser";

const bankParsers: BankParser[] = [
  rabobankParser,
  revolutParser,
  creditCardParser,
  ingParser, // ← Just add this line
];
```

**That's it!** The main component automatically detects and uses the new parser.

### Estimated Total Effort

- **Phase 2.1-2.5**: 8-12 hours (refactoring)
- **Phase 2.6**: 1-2 hours (backend validation)
- **Phase 2.7**: 2-3 hours (testing & docs)
- **Total**: 11-17 hours (~2-3 days)

### When to Start

**Recommended Trigger**: When adding the 3rd bank type (e.g., ING, ABN AMRO)

**Why Wait**:

- Current solution works well
- Refactoring takes time
- Better to refactor when you have 3+ examples (pattern becomes clear)

**Alternative**: Start now if you know you'll be adding multiple banks soon

### Success Criteria

- [ ] All existing functionality works (Rabobank, Revolut, Credit Card)
- [ ] Tenant validation works for all banks
- [ ] Adding a new bank takes < 1 hour
- [ ] Each parser has unit tests
- [ ] Code is easier to understand and maintain
- [ ] Backend validates tenant on save

### Risks & Mitigation

**Risk**: Breaking existing functionality during refactoring  
**Mitigation**:

- Keep old code until new code is tested
- Test each bank type thoroughly
- Use feature flag to switch between old/new implementation

**Risk**: Time investment without immediate benefit  
**Mitigation**:

- Only refactor when adding 3rd bank
- Refactor incrementally (one bank at a time)

**Risk**: TypeScript complexity  
**Mitigation**:

- Start with simple interfaces
- Add complexity only when needed
- Document with examples

### Decision

**Current Decision**: ✅ Keep existing implementation, add to backlog

**Revisit When**: Adding 3rd bank type or experiencing maintenance issues

**Priority**: Medium (nice to have, not urgent)

---

## Summary

**Phase 1** (Current): ✅ COMPLETE

- Tenant validation working
- All bugs fixed
- Production ready

**Phase 2** (Future): 📋 PLANNED

- Modular architecture
- Easy to extend
- Better maintainability
- Implement when adding 3rd bank

The current solution is solid and appropriate for your needs. The refactoring plan is documented here for when you're ready to scale to more banks.