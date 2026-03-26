# Asset Administration — Implementation Tasks

**Status:** Ready for Implementation
**Date:** 2026-03-26
**Design:** `findings.md`
**Data Model Reference:** `.kiro/specs/FIN/Data Model/mutaties_ref_fields.md`

---

## Phase 1: Database Schema

- [ ] Create `assets` table (see `findings.md` for schema)
- [ ] Create migration SQL: `backend/src/migrations/create_assets_table.sql`
- [ ] Add `asset_account` to predefined parameter registry (see `.kiro/specs/FIN/Chart of Accounts Management/Ledger Parameters/findings.md`)
- [ ] Add `"asset_account": true` to chart of accounts JSON templates (`nl.json`, `en.json`) for account 3060
- [ ] Run migration on local Docker DB
- [ ] Run migration on Railway DB

## Phase 2: Backend — Asset CRUD

- [ ] Create `backend/src/services/asset_service.py`
  - `create_asset(administration, data)` — insert into `assets` + purchase transaction in `mutaties`
  - `get_assets(administration, filters)` — list with current book values
  - `get_asset(administration, asset_id)` — single asset with transaction history
  - `update_asset(administration, asset_id, data)` — update metadata (not financial fields after first depreciation)
  - `dispose_asset(administration, asset_id, disposal_date, disposal_amount)` — mark disposed + write-off transaction
- [ ] Create `backend/src/routes/asset_routes.py` blueprint
  - `GET /api/assets` — list assets (with book values)
  - `POST /api/assets` — create asset
  - `GET /api/assets/<id>` — asset detail with transactions
  - `PUT /api/assets/<id>` — update asset metadata
  - `POST /api/assets/<id>/dispose` — dispose asset
- [ ] Register blueprint in `app.py`
- [ ] Add unit tests for `asset_service.py`

## Phase 3: Backend — Depreciation Generation

- [ ] Add `generate_depreciation(administration, period, year)` to `asset_service.py`
  - Reads active assets with `depreciation_method != 'none'`
  - Calculates period amount based on `depreciation_frequency`
  - Idempotent: checks if depreciation for this period already exists in `mutaties`
  - Inserts depreciation transaction: debet expense account, credit asset account
  - Sets `Ref1 = 'ASSET-{id}'`, `Ref2 = period`, `ReferenceNumber = 'Afschrijving YYYY'`
- [ ] Add `POST /api/assets/generate-depreciation` endpoint
  - Accepts `year`, `period` (e.g., `Q1`, `M03`, `annual`)
  - Returns results: how many assets processed, entries created vs skipped
- [ ] Add unit tests for depreciation generation (including idempotency)

## Phase 4: Frontend — Asset Management UI

- [ ] Create `frontend/src/components/Assets/AssetList.tsx`
  - Table with: description, category, purchase date, purchase amount, book value, status
  - Filters: category, status (active/disposed), ledger account
  - Sort by any column
- [ ] Create `frontend/src/components/Assets/AssetForm.tsx`
  - Create/edit form with all asset fields
  - Ledger account dropdown filtered by `asset_account` parameter
  - Depreciation method and frequency selectors
- [ ] Create `frontend/src/components/Assets/AssetDetail.tsx`
  - Asset metadata
  - Transaction history (purchase, depreciation entries, disposal)
  - Current book value calculation
- [ ] Create `frontend/src/services/assetService.ts`
- [ ] Add navigation/menu entry for Asset Administration
- [ ] Add NL and EN translations

## Phase 5: Frontend — Depreciation Generation UI

- [ ] Add "Generate Depreciation" button/dialog to Asset List
  - Select year and period (annual / Q1-Q4 / M01-M12)
  - Preview: which assets will be depreciated, amounts
  - Confirm: generate entries
  - Results: created vs skipped
- [ ] Add depreciation schedule view per asset (past + projected)

## Phase 6: Reporting

- [ ] Asset register report (all assets with current book values)
- [ ] Depreciation schedule report (per asset, per year)
- [ ] Asset summary by category
- [ ] Disposed assets report
- [ ] Integration with Aangifte IB (box 3 assets)

## Phase 7: Testing & Validation

- [ ] End-to-end test: create asset → generate depreciation → verify book value
- [ ] Test: dispose asset → verify write-off transaction and remaining book value
- [ ] Test: idempotent depreciation generation (run twice, no duplicates)
- [ ] Test: quarterly and monthly depreciation frequency
- [ ] Test: asset with `depreciation_method = 'none'` is skipped
- [ ] Test: `asset_account` parameter filters correctly in UI dropdown
