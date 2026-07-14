# Design Document — Fix 153 TypeScript 5.9 Type Errors

## Overview

This design addresses 153 TypeScript compilation errors reported by `tsc --noEmit` after the TypeScript 5.9.3 upgrade. The errors span 28 files and fall into 7 distinct categories. The fix strategy prioritizes proper typing over suppressions, and interface extensions over casts.

## Error Inventory by File

| File                                                        | Error Count | Primary Error Types                              |
| ----------------------------------------------------------- | ----------- | ------------------------------------------------ |
| `src/components/reports/BnbActualsReport.tsx`               | ~30         | TS2538 (undefined as index)                      |
| `src/components/PDFUploadForm.tsx`                          | ~25         | TS2322 (`{}` not assignable / `unknown` types)   |
| `src/components/BankingProcessor.tsx`                       | ~10         | TS2345 (string\|number → number), TS2769, TS2322 |
| `src/components/reports/BnbActualsCharts.tsx`               | ~12         | TS2538, TS2571, TS2322, TS2362                   |
| `src/__tests__/zzpInvoiceService.test.ts`                   | 8           | TS18048, TS2339                                  |
| `src/__tests__/debtorService.test.ts`                       | 6           | TS18048, TS2339                                  |
| `src/pages/ZZPInvoiceDetail.tsx`                            | ~10         | TS2345, TS18048, TS2322                          |
| `src/pages/ZZPDebtors.tsx`                                  | 7           | TS2339, TS2345                                   |
| `src/services/pivotService.ts`                              | 8           | TS2322, TS2740, TS2352                           |
| `src/utils/pivotTreeBuilder.ts`                             | 3           | TS2345 (boolean → string\|number\|null)          |
| `src/pages/ZZPInvoices.tsx`                                 | 3           | TS2345, TS2339                                   |
| `src/pages/ZZPTimeTracking.tsx`                             | 1           | TS2339                                           |
| `src/pages/ZZPTripImport.tsx`                               | 1           | TS2345                                           |
| `src/pages/BudgetPage.tsx`                                  | 1           | TS2345 (DimensionType)                           |
| `src/pages/BudgetNewVersionModal.tsx`                       | 1           | TS2322 (DimensionType)                           |
| `src/__tests__/BankingProcessorTable.test.tsx`              | 1           | TS2353                                           |
| `src/__tests__/BudgetLinesPage.test.tsx`                    | 2           | TS2345, TS2739                                   |
| `src/__tests__/BudgetPage.test.tsx`                         | 2           | TS2578, TS2345                                   |
| `src/services/contactService.test.ts`                       | 2           | TS2345, TS2559                                   |
| `src/hooks/useBankingState.ts`                              | 1           | TS2345                                           |
| `src/hooks/usePDFUpload.ts`                                 | 1           | TS7053                                           |
| `src/hooks/useTableConfig.ts`                               | 1           | TS2322                                           |
| `src/components/SysAdmin/TenantManagement.tsx`              | 1           | TS2322 (RefObject)                               |
| `src/components/TenantAdmin/ParameterManagement.tsx`        | 3           | TS2322                                           |
| `src/components/TenantAdmin/TenantDetails.tsx`              | 2           | TS2339                                           |
| `src/components/TenantAdmin/__tests__/integration.test.tsx` | 5           | TS2339, TS18048                                  |
| `src/components/examples/TenantAwareComponent.example.tsx`  | 1           | TS2345                                           |
| `src/components/zzp/TimeEntryModal.tsx`                     | 2           | TS2339                                           |

## Fix Strategies by Error Category

### Category A: Service Response Type Narrowing (TS18048 + TS2339)

**Problem**: Service functions return `{ data?: Record<string, unknown> | Array<Record<string, unknown>> }` — TS 5.9 correctly refuses to access specific properties without narrowing.

**Solution**: Add typed response generics or specific response interfaces to service functions. For test files, use type assertions with `as` after null checks.

```typescript
// Before (causes TS18048 + TS2339):
const r = await getReceivables();
expect(r.data.total_outstanding).toBe(100);

// After — Option A: Type assertion in test
const r = await getReceivables();
expect((r.data as { total_outstanding: number }).total_outstanding).toBe(100);

// After — Option B (preferred): Typed response interface
interface ReceivablesResponse {
  success: boolean;
  data?: { total_outstanding: number; invoices: Invoice[] };
  error?: string;
}
```

For this bugfix, **Option A** (assertions in tests) is used for test files to minimize scope. For production code (pages), we'll add proper typed interfaces to the service layer.

### Category B: Undefined-as-Index (TS2538)

**Problem**: In `BnbActualsReport.tsx` and `BnbActualsCharts.tsx`, config fields (`config.revenueKey`, `config.expenseKey`, etc.) are typed as optional (`string | undefined`) but used directly as object index keys.

**Solution**: Add early guard checks or provide default values before using as index:

```typescript
// Before:
const revenue = row[config.revenueKey];

// After:
const revenueKey = config.revenueKey ?? "";
const revenue = revenueKey ? row[revenueKey] : undefined;
// Or use non-null assertion where config is guaranteed valid:
const revenue = row[config.revenueKey!];
```

The preferred approach: add runtime guards at the function entry that early-return if required config fields are undefined, then use non-null assertions after the guard.

### Category C: `{}` and `unknown` Type Assignments (TS2322)

**Problem**: In `PDFUploadForm.tsx`, Formik field values typed as `{}` or `unknown` are passed to React components expecting `string`, `ReactNode`, etc. In `pivotService.ts`, the `??` operator with `{}` defaults produces `{} | null` which doesn't match `string | null`.

**Solution**:

- **PDFUploadForm**: Cast Formik `values[field]` with `as string` or use `String(values[field])` where the field type is known.
- **pivotService.ts**: Use typed default values instead of `{}`:

```typescript
// Before:
dataSource: def.data_source ?? def.dataSource ?? {},

// After:
dataSource: (def.data_source ?? def.dataSource ?? '') as string,
```

### Category D: Mock Type Mismatches in Tests (TS2345)

**Problem**: `vi.fn()` returns `Mock<Procedure>` which doesn't satisfy the full `useToast` return type.

**Solution**: Cast mocks through `unknown`:

```typescript
// Before:
const mockToast = vi.fn();

// After:
const mockToast = vi.fn() as unknown as ReturnType<typeof useToast>;
```

### Category E: Missing Interface Properties (TS2353, TS2739)

**Problem**: Object literals have properties not in the interface (`pattern_filled` on `Transaction`) or are missing required properties (`CopyBudgetData`).

**Solution**:

- **TS2353**: Extend the `Transaction` interface to include `pattern_filled?: boolean`
- **TS2739**: Add missing required properties to test object literals, or use `as Partial<T> as T` pattern

### Category F: Stale `@ts-expect-error` Directives (TS2578)

**Problem**: TS 5.9 resolved the underlying issues these directives suppressed.

**Solution**: Simply remove the directives.

### Category G: Type Narrowing for Specific Patterns

**Problem**: Various cases where TS 5.9 needs explicit narrowing:

- `string | number` → `number` (use `Number()`)
- `string | null` → `DimensionType | null` (use `as DimensionType`)
- `boolean` in union not assignable to `string | number | null` (filter or convert)
- `RefObject<HTMLButtonElement | null>` → `RefObject<HTMLButtonElement>` (use non-null cast)
- `BankingLookupData` missing `LookupData` properties (extend interface or map)

**Solution**: Apply appropriate narrowing per case — `as` casts for known-safe code, `Number()` for numeric conversions, interface extensions for structural mismatches.

## Approach Principles

1. **No `// @ts-ignore` or `// @ts-expect-error` added** — fix root causes
2. **Prefer interface extensions over type assertions** for production code
3. **Type assertions (`as`) are acceptable** in test files where the mock data shape is controlled
4. **No runtime behavioral changes** — only type-level corrections
5. **No relaxation of `tsconfig.json` strict settings**
6. **Group fixes by file proximity** to minimize context switching during review

## Verification

- `npx tsc --noEmit` exits 0 with 0 errors
- `npx vitest run` passes all existing tests
- `npx vite build` succeeds (production bundle)
