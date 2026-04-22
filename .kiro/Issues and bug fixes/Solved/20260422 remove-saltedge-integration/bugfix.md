# Bugfix Requirements Document

## Introduction

The "Bank verbinden (Salt Edge)" integration is obsolete dead code that should be removed entirely. The Salt Edge feature was an attempt to connect bank accounts directly via the Salt Edge API, but it never became functional — the backend API endpoints (`/api/saltedge/*`) were never implemented, and the button in BankingProcessor only shows a placeholder alert. The `BankConnect.tsx` page, its route, navigation entry, translation keys, and the alert button all need to be cleaned up to avoid user confusion and reduce code maintenance burden.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user navigates to the main dashboard THEN the system previously showed a "Bank Verbinden (Salt Edge)" menu button (now removed from the dashboard menu, but the route and component still exist in code)

1.2 WHEN a user clicks the "Bank Verbinden (Salt Edge)" button in BankingProcessor's file processing section THEN the system shows a misleading alert saying "Salt Edge integration ready! Waiting for account approval (2 business days)" even though no integration exists

1.3 WHEN a user navigates to the `bank-connect` page THEN the system renders a `BankConnect` component that makes API calls to non-existent `/api/saltedge/*` backend endpoints, resulting in errors

1.4 WHEN the codebase is maintained THEN the system contains dead code: the `BankConnect.tsx` component, its import in `App.tsx`, the `bank-connect` page type, route case, FIN access redirect check, help link mapping, and Salt Edge translation keys across 4 locale files — all referencing functionality that does not work

### Expected Behavior (Correct)

2.1 WHEN a user navigates to the main dashboard THEN the system SHALL NOT show any Salt Edge or "Bank Verbinden" menu entry

2.2 WHEN a user views the BankingProcessor file processing section THEN the system SHALL NOT show a "Bank Verbinden (Salt Edge)" button or any Salt Edge alert

2.3 WHEN the `bank-connect` page type is referenced THEN the system SHALL NOT have this route — it SHALL be removed from the `PageType` union, the route switch case, and the FIN access redirect check

2.4 WHEN the codebase is inspected THEN the system SHALL NOT contain the `BankConnect.tsx` component file, its import, Salt Edge translation keys (`saltEdgeAlert`, `connectBank` in banking.json; `connectBank` in common.json navigation.modules), or the `bank-connect` help link mapping

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user navigates to the Banking Processor page THEN the system SHALL CONTINUE TO display the file processing section with CSV/TSV file selection and all other banking functionality intact

3.2 WHEN a user navigates to any other page (pdf, banking, str, str-invoice, str-pricing, fin-reports, str-reports, assets, system-admin, tenant-admin, zzp-\*, settings, migration) THEN the system SHALL CONTINUE TO route and render those pages correctly

3.3 WHEN a user with FIN module access loses that access (e.g., tenant switch) THEN the system SHALL CONTINUE TO redirect from FIN pages (pdf, banking, powerbi, fin-reports, assets) to the menu — the redirect check SHALL still work correctly after removing `bank-connect` from it

3.4 WHEN translation files are loaded THEN the system SHALL CONTINUE TO provide all other banking, common, and locale translations without errors

3.5 WHEN the help system resolves a page to a documentation URL THEN the system SHALL CONTINUE TO map all remaining pages correctly in `helpLinks.ts`
