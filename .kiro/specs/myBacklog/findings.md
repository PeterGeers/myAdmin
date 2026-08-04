# Grouping modules FIN, STR, ZZP, Admin

## FIN Module — Navigation Restructure

Current menu is flat (Import Invoices, Import Banking, Reports, Assets, Budget). The new structure groups by activity type: produce → view → verify → plan → report.

```
FIN Module
├── 📥 Import                        (CREATE transactions)
│   ├── Invoices                     (AI extraction → mutaties)
│   │   ├── Check Invoices Exist
│   │   └── Generate Invoice
│   ├── Banking                      (CSV bank statements → mutaties)
│   ├── Assets                       (depreciation entries → mutaties)
│   └── STR Channel Revenue          (platform sums → 8003 → 2020 journal entries)
│
├── 📋 Transactions                  (VIEW/EDIT the mutaties table directly)
│
├── ✅ Validation                    (VERIFY transaction integrity — read-only checks)
│   ├── Check Accounts
│   │   • Balance vs Ledger
│   │   • Sequence check (gaps/duplicates)
│   └── Check Reference
│       • Creditors (1300) paid & booked
│       • Debtors (1600) received & booked
│       • Other reference/ledger checks
│       (single page, user picks check type via parameters)
│
├── 💰 Budget                        (planning layer)
│
└── 📊 Reports                       (consumption/aggregation — unchanged)
```

### Design decisions

- **Import** groups all producers — things that create transactions from external sources or rules
- **Transactions** is the raw `mutaties` table view (currently buried inside Banking), promoted to top-level
- **Validation** groups audit/verification tools that read transactions and flag issues (no writes)
- **STR Channel Revenue** sits under Import because it _creates_ journal entries (amounts_received → 8003, 8003 → 2020). It reads financial records of amounts received from platforms (Airbnb, Booking.com, etc.) and generates the corresponding revenue and VAT transactions
- **Assets** under Import because its primary purpose is generating depreciation transactions; the asset register is supporting config
- **Check Accounts** and **Check Reference** are each a single page with parameter-driven checks (not sub-pages)



## UI fixes
In the financial module
import and validate are very small icons and should be same layout as Transactions, Budget and FIN Reports

The sub items in import amd validate should be smaller as they are now and collapse after usage


### Workflow alignment

Import → Review in Transactions → Validate → Report. Budget sits alongside as the planning track.

---

## ZZP Module — Navigation Restructure

```
ZZP Module
├── 📋 Administration
│   ├── Products & Services
│   ├── Contacts
│   └── Debtors & Creditors
│
├── 🧾 Invoices
│   └── Time Tracking               (feeds invoice generation)
│
└── 🚗 Trip Registration
    ├── Trips
    ├── Quick Entry
    └── Import
```

---

## STR Module

No changes proposed — current structure (Import STR Bookings, Invoice Generator, Pricing Model, Reports) is fine.

---

## FIN Reports

No changes proposed — current structure is okay for now.
