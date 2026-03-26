# Ledger Account Parameters — Predefined Parameter Registry

**Status:** Analysis
**Date:** 2026-03-26
**Related:** `../20260317 Rekeningschema change pattern use to parameter/spec.md` (Phase 5 — Generic Parameter Editor)

---

## Context

The `rekeningschema` table has a `parameters` JSON column used by multiple features. Phase 5 of the Pattern-to-Parameter migration added a generic key-value editor to the Account Modal, with known keys getting type-aware inputs (boolean → switch, string → text).

Currently, known keys are hardcoded in the frontend (`AccountModal.tsx`). As more features add parameters (asset administration, future modules), we need a centralized registry of predefined parameters.

---

## Current known parameters

| Key            | Type     | Used by                            | Description                                                             |
| -------------- | -------- | ---------------------------------- | ----------------------------------------------------------------------- |
| `bank_account` | boolean  | Banking import, pattern analysis   | Account holds bank transactions (IBAN-linked)                           |
| `iban`         | string   | Banking import, vw_rekeningnummers | IBAN number for the bank account                                        |
| `roles`        | string[] | Year-end closure                   | Account roles: `interim_opening_balance`, `equity_result`, `pl_closing` |
| `vat_netting`  | boolean  | VAT netting, year-end              | Include in VAT netting group                                            |
| `vat_primary`  | string   | VAT netting                        | Primary account code for VAT net balance                                |

## New parameter to add

| Key             | Type    | Used by              | Description                      |
| --------------- | ------- | -------------------- | -------------------------------- |
| `asset_account` | boolean | Asset Administration | Account holds depreciable assets |

---

## Proposal: Predefined parameter table

Instead of hardcoding known keys in the frontend, define them in a configuration that both backend and frontend can use.

### Option A: JSON config file (recommended)

Store in `backend/src/config/ledger_parameters.json`:

```json
[
  {
    "key": "bank_account",
    "type": "boolean",
    "label_en": "Bank Account",
    "label_nl": "Bankrekening",
    "description_en": "Account holds bank transactions",
    "description_nl": "Rekening voor banktransacties",
    "module": "FIN"
  },
  {
    "key": "iban",
    "type": "string",
    "label_en": "IBAN",
    "label_nl": "IBAN",
    "description_en": "IBAN number for the bank account",
    "description_nl": "IBAN nummer van de bankrekening",
    "module": "FIN",
    "depends_on": "bank_account"
  },
  {
    "key": "asset_account",
    "type": "boolean",
    "label_en": "Asset Account",
    "label_nl": "Activarekening",
    "description_en": "Account holds depreciable assets",
    "description_nl": "Rekening voor afschrijfbare activa",
    "module": "FIN"
  },
  {
    "key": "roles",
    "type": "string[]",
    "label_en": "Account Roles",
    "label_nl": "Rekeningrollen",
    "description_en": "Year-end closure roles",
    "description_nl": "Jaarafsluiting rollen",
    "module": "FIN",
    "options": ["interim_opening_balance", "equity_result", "pl_closing"]
  },
  {
    "key": "vat_netting",
    "type": "boolean",
    "label_en": "VAT Netting",
    "label_nl": "BTW verrekening",
    "description_en": "Include in VAT netting group",
    "description_nl": "Opnemen in BTW verrekeningsgroep",
    "module": "FIN"
  },
  {
    "key": "vat_primary",
    "type": "string",
    "label_en": "VAT Primary Account",
    "label_nl": "BTW hoofdrekening",
    "description_en": "Primary account for VAT net balance",
    "description_nl": "Hoofdrekening voor BTW netto saldo",
    "module": "FIN",
    "depends_on": "vat_netting"
  }
]
```

### Option B: Database table

A `parameter_definitions` table. More flexible but adds DB complexity for something that rarely changes.

### Recommendation: Option A

The parameter list changes infrequently (only when new features are added). A JSON config file is:

- Version-controlled in git
- No DB migration needed to add a new parameter
- Loadable by both backend (for validation) and frontend (for UI rendering)
- Served via a simple API endpoint: `GET /api/config/ledger-parameters`

---

## Integration with Account Modal

The current Account Modal (Phase 5) has hardcoded known keys. The change:

1. Backend serves `GET /api/config/ledger-parameters` → returns the JSON config
2. Frontend loads the config on modal open
3. The parameter editor renders inputs based on the config:
   - `boolean` → toggle switch
   - `string` → text input
   - `string[]` → multi-select from `options`
4. `depends_on` controls visibility (e.g., `iban` only shows when `bank_account` is true)
5. Labels use the current locale (nl/en)

---

## Tasks

- [x] Create `backend/src/config/ledger_parameters.json` with all known parameters
- [x] Create `GET /api/config/ledger-parameters` endpoint (public, no auth needed)
- [x] Update `AccountModal.tsx` to load parameter definitions from API instead of hardcoded list
- [x] Add `asset_account` to the parameter definitions
- [x] Add `depends_on` logic to the parameter editor (show/hide based on parent parameter)
- [x] Add NL and EN labels from the config
- [x] Update chart of accounts JSON templates (`nl.json`, `en.json`) with `asset_account: true` on account 3060
- [x] Add account 3051 (Investeringen / Investments) with `asset_account: true` to both templates and probably 3051
- [x] Test: add `asset_account` parameter to an account via the modal
- [x] Test: asset creation form filters accounts by `asset_account` parameter
