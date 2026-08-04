# Implementation Plan: Navigation Restructure

## Overview

Reorganize the FIN and ZZP module navigation from flat button lists into logical grouped menus. The main work is extracting 4 tabs currently embedded in BankingProcessor into standalone pages, then rewiring the menu in App.tsx to use collapsible groups.

## Tasks

- [x] 1. Extract BankingMutatiesTab into standalone TransactionsPage
  - [x] 1.1 Create `frontend/src/pages/TransactionsPage.tsx`
    - Wrap `BankingMutatiesTab` component with its own data fetching
    - Call `/api/banking/mutaties` directly (currently parent fetches via `useBankingState`)
    - Include edit/insert modal (`BankingTransactionModal`) with save handler
    - Include `copyToClipboard` and `handleRef3Click` handlers
    - _Requirements: US-2_
  - [x] 1.2 Add standalone hooks for Transactions data
    - Extract mutaties-specific state from `useBankingState` into `useTransactions` hook or reuse existing fetch logic
    - Include filter options, filter state, chart accounts for modal
    - _Requirements: US-2_

- [x] 2. Extract CheckAccountsTab into standalone CheckAccountsPage
  - [x] 2.1 Create `frontend/src/pages/CheckAccountsPage.tsx`
    - Extract inline `CheckAccountsTab` (~190 lines) from BankingProcessor.tsx
    - Needs: endDate, selectedAccount, sequenceStartDate, openingBalanceDate, bankingBalances, expandedRows, sequenceResult, lookupData, checkingAccounts, checkingSequence + setters
    - Needs API calls: `checkBankingAccounts`, `checkSequenceNumbers`
    - _Requirements: US-3_
  - [x] 2.2 Create `useCheckAccounts` hook
    - Encapsulate balance check state, sequence check state, and API calls
    - Extract from `useBankingUpload` the relevant logic
    - _Requirements: US-3_

- [x] 3. Extract CheckReferenceTab into standalone CheckReferencePage
  - [x] 3.1 Create `frontend/src/pages/CheckReferencePage.tsx`
    - Extract inline `CheckReferenceTab` (~90 lines) from BankingProcessor.tsx
    - Needs: checkRefFilters, availableLedgers, refSummaryData, selectedReferenceDetails, selectedReference, filter/sort state
    - Needs API calls: `fetchCheckRefData`, `fetchReferenceDetails`
    - _Requirements: US-3_
  - [x] 3.2 Create `useCheckReference` hook
    - Encapsulate reference check state, summary/detail data, filter/sort logic, and API calls
    - _Requirements: US-3_

- [x] 4. Extract StrChannelRevenueTab into standalone STRChannelRevenuePage
  - [x] 4.1 Create `frontend/src/pages/STRChannelRevenuePage.tsx`
    - Extract inline `StrChannelRevenueTab` (~100 lines) from BankingProcessor.tsx
    - Needs: strChannelFilters, strChannelPreview, strChannelTransactions, strChannelSummary, currentTenant, loading
    - Needs API calls: `fetchStrChannelPreview`, `calculateStrChannelRevenue`, `saveStrChannelTransactions`
    - _Requirements: US-4_
  - [x] 4.2 Create `useStrChannelRevenue` hook
    - Encapsulate STR channel state and API calls
    - Gate page visibility on `hasFunction('str_channel_revenue')`
    - _Requirements: US-4_

- [x] 5. Checkpoint — All standalone pages working
  - Verify each new page renders without errors
  - Verify all CRUD/action operations work on each standalone page
  - Verify BankingProcessor still works with all tabs (parallel period)

- [x] 6. Create MenuGroup component
  - [x] 6.1 Create `frontend/src/components/MenuGroup.tsx`
    - Use Chakra UI `Collapse` for expand/collapse behavior
    - Props: icon, label, defaultOpen, children
    - Match existing button styling (variant, size, colorScheme)
    - Add expand/collapse indicator (chevron)
    - _Requirements: US-1, US-5_
  - [x] 6.2 Add navigation translation keys
    - Add group labels to `frontend/src/locales/en/common.json`: Import, Transactions, Validation, Administration, Invoices, Trip Registration
    - Add group labels to `frontend/src/locales/nl/common.json`: Importeren, Transacties, Validatie, Administratie, Facturen, Rittenregistratie
    - Add module names: Banking, STR Channel Revenue, Check Accounts, Check Reference, Transactions
    - _Requirements: US-1, US-5_

- [x] 7. Restructure FIN navigation in App.tsx
  - [x] 7.1 Add new PageTypes and lazy imports
    - Add to PageType union: `'transactions'`, `'check-accounts'`, `'check-reference'`, `'str-channel-revenue'`
    - Add lazy imports for new pages
    - Add render cases in `renderPage()` switch statement
    - Add URL mappings in `urlPageMap` for deep-link support
    - _Requirements: US-1, US-2, US-3, US-4_
  - [x] 7.2 Rebuild FIN menu section with MenuGroup
    - Import group: Invoices (`pdf`), Banking (`banking`), Assets (`assets`), STR Channel Revenue (`str-channel-revenue`)
    - Transactions: direct button (`transactions`)
    - Validation group: Check Accounts (`check-accounts`), Check Reference (`check-reference`)
    - Budget: direct button (`budget`)
    - Reports: direct button (`fin-reports`)
    - Maintain role gating: `Finance_CRUD`, `Finance_Read`
    - Maintain function gating: `hasFunction('assets')`, `hasFunction('budget')`, `hasFunction('str_channel_revenue')`
    - _Requirements: US-1_
  - [x] 7.3 Simplify BankingProcessor
    - Remove Tabs wrapper — keep only File Processing content (CSV upload + pattern matching + save)
    - Remove inline tab components (CheckAccountsTab, CheckReferenceTab, StrChannelRevenueTab)
    - Remove tab-related Chakra imports (Tab, TabList, TabPanel, TabPanels, Tabs)
    - Keep BankingTransactionModal and BankingPatternPanel (used by File Processing)
    - _Requirements: US-1_

- [x] 8. Restructure ZZP navigation in App.tsx
  - [x] 8.1 Rebuild ZZP menu section with MenuGroup
    - Administration group: Products & Services (`zzp-products`), Contacts (`zzp-contacts`), Debtors & Creditors (`zzp-debtors`)
    - Invoices group: Invoices (`zzp-invoices`), Time Tracking (`zzp-time-tracking`)
    - Trip Registration group: Trips (`zzp-trips`), Quick Entry (`zzp-trip-quick`), Import (`zzp-trip-import`)
    - Maintain role gating: `ZZP_Read`, `ZZP_CRUD`
    - _Requirements: US-5_
  - [x] 8.2 Verify existing deep links still work
    - `/zzp/ritten/quick`, `/zzp/ritten`, `/zzp/ritten/import` unchanged
    - New deep links added for FIN pages
    - _Requirements: US-5_

- [x] 9. Cleanup and polish
  - [x] 9.1 Remove dead code
    - Remove unused imports from BankingProcessor
    - Remove any transition/parallel code
    - _Requirements: US-1_
  - [x] 9.2 Visual verification
    - Test menu collapsed and expanded states
    - Test with single-module tenants (only FIN, only ZZP)
    - Verify consistent spacing and alignment
    - _Requirements: US-1, US-5_

- [x] 10. Final checkpoint
  - All menu items navigate correctly
  - All existing functionality preserved (no regression)
  - Deep links work for new and existing pages
  - Role and function gating enforced

## Task Dependency Graph

```json
{
  "waves": [
    { "tasks": ["1", "2", "3", "4", "6"] },
    { "tasks": ["5"] },
    { "tasks": ["7", "8"] },
    { "tasks": ["9"] },
    { "tasks": ["10"] }
  ]
}
```

Tasks 1-4 and 6 can run in parallel (wave 1). Task 5 (checkpoint) verifies extracted pages work. Tasks 7 and 8 both depend on task 6 (MenuGroup). Task 7 also depends on tasks 1-4 (needs standalone pages). Task 8 only needs task 6.

## Notes

- No backend changes required — this is purely frontend navigation restructure
- No new npm dependencies — Chakra UI `Collapse` is already available via Framer Motion
- BankingProcessor drops from ~559 lines to ~150 lines after extraction
- Each extracted page needs its own hook to be self-sufficient (no shared parent state)
- The `useBankingProcessor` hook is already split into 3 composable sub-hooks internally, making extraction feasible
- Total estimate: ~9 hours across all phases
