# Design: Navigation Restructure

## Current State

### FIN Menu (App.tsx)

Flat buttons: Import Invoices → Import Banking → FIN Reports → Assets → Budget

### BankingProcessor Tabs (currently bundled together)

Tabs: File Processing | Mutaties | Check Accounts | Check Reference | STR Channel Revenue

### ZZP Menu (App.tsx)

Flat buttons: Invoices → Contacts → Products → Time Tracking → Trips → Debtors

## Target State

### FIN Menu Structure

```
📥 Import (collapsible)
   ├── Invoices              → page: 'pdf'
   ├── Banking               → page: 'banking' (File Processing tab only)
   ├── Assets                → page: 'assets'
   └── STR Channel Revenue   → page: 'str-channel-revenue' (new)

📋 Transactions              → page: 'transactions' (new — standalone mutaties view)

✅ Validation (collapsible)
   ├── Check Accounts        → page: 'check-accounts' (new)
   └── Check Reference       → page: 'check-reference' (new)

💰 Budget                    → page: 'budget'

📊 Reports                   → page: 'fin-reports'
```

### ZZP Menu Structure

```
📋 Administration (collapsible)
   ├── Products & Services   → page: 'zzp-products'
   ├── Contacts              → page: 'zzp-contacts'
   └── Debtors & Creditors   → page: 'zzp-debtors'

🧾 Invoices (collapsible)
   ├── Invoices              → page: 'zzp-invoices'
   └── Time Tracking         → page: 'zzp-time-tracking'

🚗 Trip Registration (collapsible)
   ├── Trips                 → page: 'zzp-trips'
   ├── Quick Entry           → page: 'zzp-trip-quick'
   └── Import                → page: 'zzp-trip-import'
```

## Technical Approach

### 1. Extract Tabs from BankingProcessor

The BankingProcessor currently renders 5 tabs. After restructure:

- **BankingProcessor** keeps only the File Processing tab (CSV upload + pattern matching + save)
- **TransactionsPage** — new standalone page wrapping `BankingMutatiesTab`
- **CheckAccountsPage** — new standalone page wrapping `CheckAccountsTab`
- **CheckReferencePage** — new standalone page wrapping `CheckReferenceTab`
- **STRChannelRevenuePage** — new standalone page wrapping `STRChannelRevenueTab`

Each extracted page needs access to shared state currently managed by `useBankingProcessor` hook. Options:

- **Option A (recommended):** Each extracted tab component already receives props — make them self-contained with their own data fetching (they already call APIs independently)
- **Option B:** Share state via context — adds complexity, avoid unless needed

### 2. Collapsible Menu Groups

No collapsible pattern exists today. Introduce a `MenuGroup` component:

```tsx
interface MenuGroupProps {
  icon: string;
  label: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function MenuGroup({
  icon,
  label,
  defaultOpen = false,
  children,
}: MenuGroupProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <Box w="100%">
      <Button onClick={() => setIsOpen(!isOpen)} variant="ghost" w="100%">
        {icon} {label} {isOpen ? "▾" : "▸"}
      </Button>
      <Collapse in={isOpen}>
        <VStack pl={6} spacing={1}>
          {children}
        </VStack>
      </Collapse>
    </Box>
  );
}
```

Uses Chakra UI `Collapse` component (already available via Framer Motion dependency).

### 3. New PageTypes

Add to the `PageType` union:

- `'transactions'` — standalone mutaties view
- `'check-accounts'` — standalone check accounts
- `'check-reference'` — standalone check reference
- `'str-channel-revenue'` — standalone STR channel revenue

### 4. Translation Keys

New keys needed in `common.json` (EN/NL):

```json
"navigation": {
  "groups": {
    "import": "Import" / "Importeren",
    "transactions": "Transactions" / "Transacties",
    "validation": "Validation" / "Validatie",
    "administration": "Administration" / "Administratie",
    "invoices": "Invoices" / "Facturen",
    "tripRegistration": "Trip Registration" / "Rittenregistratie"
  },
  "modules": {
    "banking": "Banking" / "Bankieren",
    "strChannelRevenue": "STR Channel Revenue" / "STR Kanaal Omzet",
    "checkAccounts": "Check Accounts" / "Rekeningen Controleren",
    "checkReference": "Check Reference" / "Referentie Controleren",
    "transactions": "Transactions" / "Transacties"
  }
}
```

### 5. Role Gating (unchanged)

- Import group items: `Finance_CRUD` (existing)
- Transactions: `Finance_CRUD` + `Finance_Read` (view access)
- Validation: `Finance_CRUD` + `Finance_Read`
- STR Channel Revenue: `Finance_CRUD` + `hasFunction('str_channel_revenue')`
- ZZP items: `ZZP_Read` + `ZZP_CRUD` (existing)

### 6. BankingProcessor Simplification

After extraction, BankingProcessor becomes a single-purpose CSV import page:

- Upload CSV
- Pattern matching
- Review & save transactions

The Tabs component is removed entirely. This significantly reduces the component's complexity and line count.

## Dependencies

- Chakra UI `Collapse` (already available)
- No new npm packages required
- No backend changes required

## Risks

- **Shared state in useBankingProcessor**: The extracted tabs may depend on shared state (e.g., `mutaties` data loaded once and shared across tabs). Need to verify each tab's data independence.
- **Deep links**: Currently only `/banking` exists for the banking page. New pages need URL mappings in `urlPageMap`.
- **User muscle memory**: Existing users know where things are. Consider keeping the old Banking page functional (with all tabs) for a transition period, or not.

## File Impact

| File                                           | Change                                                        |
| ---------------------------------------------- | ------------------------------------------------------------- |
| `frontend/src/App.tsx`                         | New PageTypes, new menu rendering with groups, new page cases |
| `frontend/src/components/BankingProcessor.tsx` | Remove tabs, keep only File Processing                        |
| `frontend/src/pages/TransactionsPage.tsx`      | New — wraps BankingMutatiesTab                                |
| `frontend/src/pages/CheckAccountsPage.tsx`     | New — wraps CheckAccountsTab                                  |
| `frontend/src/pages/CheckReferencePage.tsx`    | New — wraps CheckReferenceTab                                 |
| `frontend/src/pages/STRChannelRevenuePage.tsx` | New — wraps STR Channel Revenue tab                           |
| `frontend/src/components/MenuGroup.tsx`        | New — collapsible menu group                                  |
| `frontend/src/locales/en/common.json`          | New translation keys                                          |
| `frontend/src/locales/nl/common.json`          | New translation keys                                          |
