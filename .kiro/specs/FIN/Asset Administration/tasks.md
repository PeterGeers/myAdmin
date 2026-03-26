# Asset Administration — Implementation Tasks

**Status:** Ready for Implementation
**Date:** 2026-03-26
**Design:** `findings.md`
**Data Model Reference:** `.kiro/specs/FIN/Data Model/mutaties_ref_fields.md`

---

## Phase 1: Database Schema

- [x] Create `assets` table (see `findings.md` for schema)
- [x] Create migration SQL: `backend/src/migrations/create_assets_table.sql`
- [x] Add `asset_account` to predefined parameter registry (see `.kiro/specs/FIN/Chart of Accounts Management/Ledger Parameters/findings.md`)
- [x] Add `"asset_account": true` to chart of accounts JSON templates (`nl.json`, `en.json`) for account 3060
- [x] Run migration on local Docker DB
- [x] Run migration on Railway DB

## Phase 2: Backend — Asset CRUD

- [x] Create `backend/src/services/asset_service.py`
  - `create_asset(administration, data)` — insert into `assets` + purchase transaction in `mutaties`
  - `get_assets(administration, filters)` — list with current book values
  - `get_asset(administration, asset_id)` — single asset with transaction history
  - `update_asset(administration, asset_id, data)` — update metadata (not financial fields after first depreciation)
  - `dispose_asset(administration, asset_id, disposal_date, disposal_amount)` — mark disposed + write-off transaction
- [x] Create `backend/src/routes/asset_routes.py` blueprint
  - `GET /api/assets` — list assets (with book values)
  - `POST /api/assets` — create asset
  - `GET /api/assets/<id>` — asset detail with transactions
  - `PUT /api/assets/<id>` — update asset metadata
  - `POST /api/assets/<id>/dispose` — dispose asset
- [x] Register blueprint in `app.py`
- [x] Add unit tests for `asset_service.py`

## Phase 3: Backend — Depreciation Generation

- [x] Add `generate_depreciation(administration, period, year)` to `asset_service.py`
  - Reads active assets with `depreciation_method != 'none'`
  - Calculates period amount based on `depreciation_frequency`
  - Idempotent: checks if depreciation for this period already exists in `mutaties`
  - Inserts depreciation transaction: debet expense account, credit asset account
  - Sets `Ref1 = 'ASSET-{id}'`, `Ref2 = period`, `ReferenceNumber = 'Afschrijving YYYY'`
- [x] Add `POST /api/assets/generate-depreciation` endpoint
  - Accepts `year`, `period` (e.g., `Q1`, `M03`, `annual`)
  - Returns results: how many assets processed, entries created vs skipped
- [x] Add unit tests for depreciation generation (including idempotency)

## Phase 4: Frontend — Asset Management UI

- [x] Create `frontend/src/components/Assets/AssetList.tsx`
  - Table with: description, category, purchase date, purchase amount, book value, status
  - Filters: category, status (active/disposed), ledger account
  - Sort by any column
- [x] Create `frontend/src/services/assetService.ts`
- [x] Create `frontend/src/components/Assets/AssetForm.tsx`
  - Create/edit form with all asset fields
  - Ledger account dropdown filtered by `asset_account` parameter
  - Depreciation method and frequency selectors
- [x] Create `frontend/src/components/Assets/AssetDetail.tsx`
  - Asset metadata
  - Transaction history (purchase, depreciation entries, disposal)
  - Current book value calculation
- [x] Create `frontend/src/services/assetService.ts`
- [x] Add navigation/menu entry for Asset Administration
- [x] Add NL and EN translations

## Phase 5: Frontend — Depreciation Generation UI

- [x] Add "Generate Depreciation" button/dialog to Asset List
  - Select year and period (annual / Q1-Q4 / M01-M12)
  - Preview: which assets will be depreciated, amounts
  - Confirm: generate entries
  - Results: created vs skipped
- [x] Add depreciation schedule view per asset (past + projected)

## Phase 6: Reporting

- [x] Asset register report (all assets with current book values)
- [x] Depreciation schedule report (per asset, per year)
- [x] Asset summary by category (included in register report)
- [x] Disposed assets report (AssetList with status filter = disposed)
- [ ] Integration with Aangifte IB (box 3 assets) — deferred, depends on existing IB report structure

## Phase 7: Testing & Validation

- [x] End-to-end test: create asset → generate depreciation → verify book value
- [x] Test: dispose asset → verify write-off transaction and remaining book value
- [ ] Test: idempotent depreciation generation (run twice, no duplicates)
- [ ] Test: quarterly and monthly depreciation frequency
- [ ] Test: asset with `depreciation_method = 'none'` is skipped
- [ ] Test: `asset_account` parameter filters correctly in UI dropdown
