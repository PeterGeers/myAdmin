# Frontend Organization — Current State Analysis & Recommendations

## ChatGPT's Idea: Separating "Doing the Work" from "Reporting"

The suggestion of a layered split (Transaction Processing → Accounting Structure → Reporting Model → Presentation) is solid accounting theory. However, **your frontend already reflects this split naturally** — you just don't have it organized consistently in the folder structure.

---

## Current State: What's Working, What's Messy

### The Good

- **Module separation in App.tsx** is clear: FIN, STR, ZZP, Admin — each with proper role gates
- **Services layer** is well-organized (one service per domain)
- **Hooks** are extracted for reusable logic (banking, filters, tables)
- **Lazy loading** is in place for all feature pages

### The Problems

1. **Flat component dumping ground**: `src/components/` has 50+ files at root level. Banking, STR, PDF, Reports — all mixed together alongside their tests.
2. **Inconsistent grouping**: Some features have subdirectories (`banking/`, `reports/`, `zzp/`, `Assets/`) while others don't (`BankingProcessor.tsx` lives at root AND there's a `banking/` folder).
3. **Pages vs Components blurred**: Budget pages are in `pages/` but Banking/STR pages live in `components/`. There's no consistent rule for what goes where.
4. **Reports are scattered**: `FINReports.tsx` at root, `ProfitLoss.tsx` at root, while other reports are in `components/reports/`.
5. **No "doing the work" vs "reporting" structural split** — but this is fine conceptually since the module grouping already implies it.

---

## Recommended Organization

I'd organize by **domain module first**, with a consistent internal structure per module. The "doing work vs reporting" split becomes a sub-layer inside each module rather than a top-level concern.

```
frontend/src/
├── components/
│   ├── common/              # Truly shared UI components
│   │   ├── AccountSelect.tsx
│   │   ├── ErrorBoundary.tsx
│   │   ├── FilterErrorBoundary.tsx
│   │   ├── PlotlyChart.tsx
│   │   └── ProtectedRoute.tsx
│   │
│   ├── layout/              # App shell, navigation, tenant/user chrome
│   │   ├── TenantSelector.tsx
│   │   ├── UserMenu.tsx
│   │   ├── LanguageSelector.tsx
│   │   └── HelpButton.tsx
│   │
│   ├── fin/                 # FIN module — "doing the work"
│   │   ├── invoices/        # PDF upload, invoice extraction
│   │   │   ├── PDFUploadForm.tsx
│   │   │   ├── PDFValidation.tsx
│   │   │   ├── MissingInvoices.tsx
│   │   │   └── InvoiceGenerator.tsx
│   │   ├── banking/         # Bank processing
│   │   │   ├── BankingProcessor.tsx
│   │   │   ├── BankingProcessorTable.tsx
│   │   │   ├── BankingTransactionModal.tsx
│   │   │   ├── BankingFileUpload.tsx
│   │   │   ├── BankingPatternPanel.tsx
│   │   │   ├── BankingMutatiesTab.tsx
│   │   │   └── DuplicateWarningDialog.tsx
│   │   ├── assets/          # Asset administration
│   │   │   └── AssetList.tsx
│   │   ├── budget/          # Budget management
│   │   │   └── (budget components)
│   │   └── reports/         # FIN reporting
│   │       ├── FINReports.tsx
│   │       ├── ProfitLoss.tsx
│   │       ├── ProfitLossChartPanel.tsx
│   │       ├── ProfitLossFilterPanel.tsx
│   │       ├── BalanceReport.tsx
│   │       ├── BtwReport.tsx
│   │       ├── AangifteIbReport.tsx
│   │       ├── MutatiesReport.tsx
│   │       ├── ReferenceAnalysisReport.tsx
│   │       ├── ToeristenbelastingReport.tsx
│   │       └── YearEndClosureSection.tsx
│   │
│   ├── str/                 # STR module — "doing the work"
│   │   ├── processor/       # Booking import
│   │   │   └── STRProcessor.tsx
│   │   ├── invoices/        # STR invoice generation
│   │   │   └── STRInvoice.tsx
│   │   ├── pricing/         # Pricing optimizer
│   │   │   ├── STRPricing.tsx
│   │   │   └── STRPricingTable.tsx
│   │   └── reports/         # STR reporting
│   │       ├── STRReports.tsx
│   │       ├── STRSummaryPanel.tsx
│   │       ├── STRBookingTable.tsx
│   │       ├── BnbActualsReport.tsx
│   │       ├── BnbFutureReport.tsx
│   │       ├── BnbRevenueReport.tsx
│   │       ├── BnbViolinsReport.tsx
│   │       └── ...
│   │
│   ├── zzp/                 # ZZP module
│   │   ├── invoices/
│   │   ├── contacts/
│   │   ├── products/
│   │   ├── time-tracking/
│   │   └── debtors/
│   │
│   ├── admin/               # System & Tenant admin
│   │   ├── SysAdminDashboard.tsx
│   │   ├── TenantAdminDashboard.tsx
│   │   └── PasskeySettings.tsx
│   │
│   ├── filters/             # Generic filter framework (shared)
│   └── shared/              # Shared domain components (pivot, charts)
│       └── pivot/
│
├── hooks/                   # (unchanged — already well-organized)
├── services/                # (unchanged — already well-organized)
├── context/                 # (unchanged)
├── types/                   # (unchanged)
├── utils/                   # (unchanged)
├── locales/                 # (unchanged)
└── pages/                   # Auth/error pages ONLY
    ├── Login.tsx
    ├── Callback.tsx
    ├── NotFound.tsx
    ├── ServerError.tsx
    ├── ServiceUnavailable.tsx
    └── Unauthorized.tsx
```

---

## Why This Structure (Not a Flat "Work vs Reports" Split)

ChatGPT's suggestion of separating the transaction layer from the reporting layer makes perfect sense in a **backend data model**. But in a frontend, the better axis of separation is **user workflow / domain module**, because:

1. **Developers work on one module at a time** — when you're fixing STR pricing, you don't want to navigate between `src/processing/str/` and `src/reports/str/`. Having `str/pricing/` and `str/reports/` next to each other is more ergonomic.

2. **Reports already depend on their module's types and services** — a BnbViolinsReport imports STR types and uses STR services. Separating it physically from the rest of STR just adds import distance without benefit.

3. **The split still exists, just one level down** — within each module you have `invoices/`, `banking/`, `processor/` (doing the work) and `reports/` (understanding the work). You get the conceptual separation without the practical inconvenience.

4. **Lazy loading boundaries align with modules** — you already lazy-load by module. This structure keeps that boundary clean.

---

## Pragmatic Migration Path

You don't need to do this all at once. A low-risk approach:

| Phase                                                                             | Effort | Impact                                |
| --------------------------------------------------------------------------------- | ------ | ------------------------------------- |
| 1. Move root-level components into `fin/` subdirectories                          | Medium | Eliminates the 50-file dumping ground |
| 2. Consolidate `pages/Budget*` into `components/fin/budget/`                      | Small  | Consistent pattern                    |
| 3. Move STR/BNB reports from `components/reports/` into `components/str/reports/` | Small  | Domain grouping                       |
| 4. Create `components/layout/` for app chrome                                     | Small  | Cleaner root                          |
| 5. Rename `pages/` to only hold auth/error views                                  | Small  | Clear boundary                        |

Each phase is independently deployable and doesn't require changing any business logic — just `import` paths (which your IDE can auto-update).

---

## Summary

- **ChatGPT's layered model** → great for your backend data architecture (and it largely exists there already)
- **Frontend** → organize by domain module, with "work" and "reports" as sub-layers within each module
- **Current pain point** → the flat `src/components/` dumping ground, not the work/reporting split
- **Key principle** → group by what developers modify together, not by abstract architectural layers
