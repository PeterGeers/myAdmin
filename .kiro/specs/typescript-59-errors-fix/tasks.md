# Implementation Plan

## Overview

Fix all TypeScript 5.9.3 compilation errors across 28 frontend files. Errors stem from stricter type narrowing, union type handling, and inference in TS 5.9. Only type-level corrections — no runtime behavioral changes, no relaxing of strict compiler settings.

The implementation is organized in 4 waves. Tasks within a wave can be executed in parallel. Each wave completes before the next starts.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 1, "tasks": ["1", "2", "3"] },
    { "id": 2, "tasks": ["4", "5", "6", "7", "8"] },
    { "id": 3, "tasks": ["9", "10", "11", "12", "13"] },
    { "id": 4, "tasks": ["14"] }
  ]
}
```

## Tasks

### Wave 1: Type Definitions and Service Interfaces

---

- [x] 1. Fix Banking and Shared Type Interfaces
  - [x] 1.1 Add pattern_filled optional boolean to Transaction interface in frontend/src/components/BankingProcessor.types.ts
  - [x] 1.2 In frontend/src/hooks/useBankingState.ts, ensure BankingLookupData is structurally compatible with LookupData for SetStateAction usage
  - [x] 1.3 Run tsc --noEmit and verify zero errors in BankingProcessor.types.ts and useBankingState.ts

---

- [x] 2. Fix ZZP and Debtor Service Response Types
  - [x] 2.1 In frontend/src/services/zzpInvoiceService.ts, add typed response interfaces InvoiceListResponse and InvoiceItemResponse with proper data types
  - [x] 2.2 In frontend/src/services/debtorService.ts, add updated, matched, partial, unmatched optional number fields to DebtorApiResponse
  - [x] 2.3 In frontend/src/services/timeTrackingService.ts, add error optional string to ApiItemResponse and ApiDeleteResponse
  - [x] 2.4 Run tsc --noEmit and verify zero errors in zzpInvoiceService, debtorService, and timeTrackingService

---

- [x] 3. Fix TenantAdmin API Response Types
  - [x] 3.1 In frontend/src/services/tenantAdminApi.ts, add typed response interfaces TenantDetailResponse, UserCreateResponse, CredentialResponse, AccessCheckResponse extending ApiResponse
  - [x] 3.2 Update function return types in tenantAdminApi.ts to use the new specific response interfaces
  - [x] 3.3 Run tsc --noEmit and verify zero errors in tenantAdminApi.ts

---

### Wave 2: Service Files, Utilities and Hooks

---

- [x] 4. Fix pivotService.ts Type Errors
  - [x] 4.1 In fromBackendConfig add explicit type assertions on each property using as-casts for string, string[], AggregateMeasure[], DisplayMode etc
  - [x] 4.2 Change raw.definition cast to use double assertion (as unknown as Record)
  - [x] 4.3 Run tsc --noEmit and verify zero errors in pivotService.ts

---

- [x] 5. Fix pivotTreeBuilder.ts Type Errors
  - [x] 5.1 Filter or coerce boolean values on lines 160 and 164 before passing to functions expecting string or number or null
  - [x] 5.2 Filter array on line 184 to exclude boolean values before passing to function
  - [x] 5.3 Run tsc --noEmit and verify zero errors in pivotTreeBuilder.ts

---

- [x] 6. Fix Hook Type Errors in usePDFUpload and useTableConfig
  - [x] 6.1 In frontend/src/hooks/usePDFUpload.ts line 274, replace empty object state type with properly typed initial value
  - [x] 6.2 In frontend/src/hooks/useTableConfig.ts line 89, change empty object default to null or use as unknown as T cast
  - [x] 6.3 Run tsc --noEmit and verify zero errors in usePDFUpload.ts and useTableConfig.ts

---

- [x] 7. Fix contactService.test.ts Type Errors
  - [x] 7.1 On line 132, cast contact_type value to ContactType
  - [x] 7.2 On line 155, add required Contact interface properties or use Partial cast
  - [x] 7.3 Run tsc --noEmit and verify zero errors in contactService.test.ts

---

- [x] 8. Fix Test File Type Errors in debtorService and zzpInvoiceService tests
  - [x] 8.1 In debtorService.test.ts add non-null assertions and type assertions for data property access
  - [x] 8.2 In zzpInvoiceService.test.ts add non-null assertions and cast data for property access
  - [x] 8.3 Run tsc --noEmit and verify zero errors in debtorService.test.ts and zzpInvoiceService.test.ts

---

### Wave 3: Components and Pages

---

- [x] 9. Fix PDFUploadForm.tsx Type Errors
  - [x] 9.1 Add missing setSearchTerm state declaration or fix variable reference on line 137
  - [x] 9.2 Add typed Formik values interface PDFFormValues with all form fields as string and update useFormik call
  - [x] 9.3 Cast Formik values field access to string where rendered in JSX
  - [x] 9.4 Fix DuplicateInfo type mismatch on line 510 with null guard or type update
  - [x] 9.5 Run tsc --noEmit and verify zero errors in PDFUploadForm.tsx

---

- [x] 10. Fix BnbActualsReport.tsx and BnbActualsCharts.tsx Type Errors
  - [x] 10.1 In BnbActualsReport.tsx add early guards for undefined config fields then use non-null assertions
  - [x] 10.2 Apply non-null assertions for all object index accesses after guards
  - [x] 10.3 In BnbActualsCharts.tsx add same guard pattern for config fields
  - [x] 10.4 Fix PieLabel type callback signature to match PieLabelRenderProps
  - [x] 10.5 Fix arithmetic on possibly-undefined values with null coalescing
  - [x] 10.6 Fix Object is of type unknown error by adding type annotation
  - [x] 10.7 Run tsc --noEmit and verify zero errors in BnbActualsReport.tsx and BnbActualsCharts.tsx

---

- [x] 11. Fix BankingProcessor.tsx Type Errors
  - [x] 11.1 Wrap value with Number() for string-or-number to number conversion on line 407
  - [x] 11.2 Add undefined guard before new Date(value) call on line 433
  - [x] 11.3 Cast or assert the unknown value to number on line 434
  - [x] 11.4 Add type annotations for destructured transaction fields on lines 502-506
  - [x] 11.5 Wrap value with Number() for string-or-number-or-undefined to number on line 550
  - [x] 11.6 Run tsc --noEmit and verify zero errors in BankingProcessor.tsx

---

- [x] 12. Fix ZZP Pages Type Errors
  - [x] 12.1 In ZZPInvoiceDetail.tsx use typed API responses and add null guards for ledger data and fix t prop type
  - [x] 12.2 In ZZPInvoices.tsx use typed InvoiceListResponse and add null guard before setInvoices
  - [x] 12.3 In ZZPDebtors.tsx use updated DebtorApiResponse and add null guards for data access
  - [x] 12.4 In ZZPTimeTracking.tsx the error field is now available from task 2.3
  - [x] 12.5 In ZZPTripImport.tsx cast preview to ImportRow array via double assertion
  - [x] 12.6 Run tsc --noEmit and verify zero errors in ZZP files

---

- [x] 13. Fix Remaining Components and Tests
  - [x] 13.1 In BudgetNewVersionModal.tsx cast string-or-null to DimensionType-or-null
  - [x] 13.2 In BudgetPage.tsx ensure detail_dimension_type is typed as DimensionType-or-null
  - [x] 13.3 In BudgetPage.test.tsx remove stale ts-expect-error directive and cast mock toast
  - [x] 13.4 In BudgetLinesPage.test.tsx cast mock toast and add missing CopyBudgetData properties
  - [x] 13.5 Verify BankingProcessorTable.test.tsx compiles after task 1.1 pattern_filled addition
  - [x] 13.6 In SysAdmin/TenantManagement.tsx fix useRef type for Chakra AlertDialog compatibility
  - [x] 13.7 In TenantAdmin/ParameterManagement.tsx cast object values or narrow with typeof
  - [x] 13.8 In TenantAdmin/TenantDetails.tsx use updated typed response from task 3.1
  - [x] 13.9 In TenantAdmin integration.test.tsx use typed responses and add null guards
  - [x] 13.10 In TenantAwareComponent.example.tsx add index signature or cast argument
  - [x] 13.11 Verify TimeEntryModal.tsx compiles after task 2.3 error field addition
  - [x] 13.12 Run tsc --noEmit and verify zero total TS errors remain

---

### Wave 4: Final Verification

---

- [x] 14. Full Build and Test Verification
  - [x] 14.1 Run tsc --noEmit must exit 0 with zero errors
  - [x] 14.2 Run vitest run and confirm all existing tests pass
  - [x] 14.3 Run vite build and confirm production bundle builds successfully
  - [x] 14.4 Confirm no ts-ignore or new ts-expect-error directives were introduced
  - [x] 14.5 Confirm tsconfig.json strict settings unchanged

---

## Notes

### Key Principles

- No ts-ignore or ts-expect-error directives added
- Prefer typed interfaces over as-casts in production code
- As-casts acceptable in test files and JSON boundaries
- No runtime behavior changes — only type annotations
- No changes to tsconfig.json strict settings
