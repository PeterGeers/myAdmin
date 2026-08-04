# Requirements: Navigation Restructure

## Context

The FIN module navigation is currently a flat list of 5 buttons. Key functions (Transactions view, Check Accounts, Check Reference, STR Channel Revenue) are hidden inside BankingProcessor as tabs. The ZZP module is also flat with no logical grouping.

## User Stories

### US-1: FIN Grouped Navigation

As a financial administrator, I want the FIN menu organized by activity type (Import, Transactions, Validation, Budget, Reports) so I can quickly find the function I need without navigating through unrelated tabs.

**Acceptance Criteria:**

- FIN menu shows 5 collapsible groups: Import, Transactions, Validation, Budget, Reports
- Import group contains: Invoices, Banking, Assets, STR Channel Revenue
- Transactions is a direct link to the mutaties table view
- Validation group contains: Check Accounts, Check Reference
- Budget and Reports remain as direct links (no sub-items)
- All existing functionality is preserved — no feature regression

### US-2: Promote Transactions to Top-Level

As a user, I want to access the Transactions (mutaties) table directly from the main menu without first opening Banking and finding a tab.

**Acceptance Criteria:**

- Transactions page accessible from FIN main menu in one click
- The mutaties table view (currently `BankingMutatiesTab`) works standalone
- Edit/insert modal functionality preserved
- All existing filters and parameter-driven column config preserved

### US-3: Promote Validation Functions

As a financial administrator, I want Check Accounts and Check Reference accessible from the main menu so I don't have to navigate through the Banking import page to perform validations.

**Acceptance Criteria:**

- Check Accounts accessible from FIN menu under Validation group
- Check Reference accessible from FIN menu under Validation group
- All existing check functionality preserved

### US-4: Promote STR Channel Revenue

As a financial administrator, I want STR Channel Revenue accessible from the FIN Import group since it creates financial transactions.

**Acceptance Criteria:**

- STR Channel Revenue appears under FIN > Import (when tenant has `str_channel_revenue` function)
- Creates journal entries as before (amounts_received → 8003, 8003 → 2020)
- Existing functionality preserved

### US-5: ZZP Grouped Navigation

As a freelance administrator, I want ZZP menu items grouped logically (Administration, Invoices, Trip Registration) so related functions are together.

**Acceptance Criteria:**

- ZZP menu shows 3 groups: Administration, Invoices, Trip Registration
- Administration contains: Products & Services, Contacts, Debtors & Creditors
- Invoices contains: Invoices, Time Tracking
- Trip Registration contains: Trips, Quick Entry, Import
- All existing functionality preserved

## Out of Scope

- Backend API changes (this is purely frontend navigation)
- New features — only reorganization of existing pages
- Routing overhaul (keep state-based navigation, extend with new PageTypes)
- STR module navigation (no changes needed)
- Mobile/responsive layout changes beyond what the new groups require

## Success Metrics

- All existing functions accessible with ≤2 clicks from main menu
- No broken navigation paths
- Translation keys updated for both EN and NL
