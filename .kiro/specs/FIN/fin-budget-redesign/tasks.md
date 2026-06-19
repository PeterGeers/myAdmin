# Tasks: Budget Module Redesign

## Phase 1: Backend Simplification (~4h)

- [x] 1.1 Simplify `activate_version` in `budget_service.py`
  - Remove logic that deactivates other versions for the same fiscal year
  - Accept `active` boolean parameter (true/false) for toggle behavior
  - Keep validation: only Approved/Revised can be activated
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 1.2 Update `budget_routes.py` activate endpoint
  - Accept `{ "active": true/false }` in request body
  - Update permission to `finance_write` (Finance_CRUD)
  - _Requirements: 3.1, 3.2_

- [x] 1.3 Modify dashboard endpoint to use `version_id`
  - Change from `year` (required) to `version_id` (required) parameter
  - Look up version's fiscal_year internally
  - Validate version exists and belongs to tenant
  - Backward compatible: still accepts `year` parameter as fallback
  - _Requirements: 2.2, 2.3, 2.6_

- [x] 1.4 Remove template routes from `budget_routes.py`
  - Delete: list_templates, get_template, create_template, update_template, delete_template routes
  - Delete: generate_draft route
  - Delete: ai/template-recommend route
  - _Requirements: 4.3, 4.4_

- [x] 1.5 Remove template methods from `budget_service.py`
  - Delete: `get_template`, `list_templates`, `create_template`, `update_template`, `delete_template`
  - Delete: `generate_draft`, `_compute_monthly_amounts`
  - Keep: all version/line/dashboard/copy methods
  - _Requirements: 4.3_

- [x] 1.6 Add AI generate-lines endpoint
  - New route: `POST /api/budget/ai/generate-lines`
  - Calls `budget_ai_service.generate_lines(chart_of_accounts, prior_actuals, fiscal_year, context_notes, administration)`
  - Returns proposed lines (not saved to DB)
  - _Requirements: 5.1, 5.2_

- [x] 1.7 Implement `generate_lines` in `budget_ai_service.py`
  - Fetch chart of accounts for tenant
  - Fetch prior-year actuals summary (grouped by account/month)
  - Send to AI with context notes
  - Parse response into structured proposed lines
  - Remove `recommend_template` method
  - _Requirements: 5.1, 5.2_

- [x] 1.8 Update backend tests
  - Remove template-related test classes (TestCreateTemplate, TestGetTemplate, TestListTemplates, TestUpdateTemplate, TestDeleteTemplate, TestGenerateDraft)
  - Remove template-related tenant isolation tests
  - Remove recommend_template AI tests
  - Update activate_version tests for new toggle behavior (no deactivation of others)
  - Update dashboard tests for new `get_dashboard(admin, level, period, year=...)` signature
  - Update property tests: TestActiveVersionUniqueness for multi-active, remove template tenant isolation tests
  - Keep \_compute_monthly_amounts and Property 7 (annualization) — utility for AI features
  - All 175 tests passing (128 service + 20 AI + 27 properties)
  - _Requirements: all_

## Phase 2: Frontend — New Budget Page (~5h)

- [x] 2.1 Create `BudgetPage.tsx` — version selector and line table
  - Version dropdown (all versions, showing name + year + status + active indicator)
  - "New Version" button
  - Budget lines table with: account code, dimension, period mode, total
  - Row click opens edit modal
  - Delete line button (trash icon, only on Draft versions)
  - "Add Line" button (only on Draft versions)
  - Status bar: Approve, Revise, Activate, Delete (contextual by status)
  - Read-only display for non-Draft versions
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.8, 1.9, 1.10_

- [x] 2.2 Reuse existing `BudgetLineModal.tsx` for line editing
  - Account code + name (read-only on edit, selectable on create)
  - Period mode toggle (Monthly / Annual)
  - Monthly: 12 labeled input fields + computed total
  - Annual: 1 input field, display computed monthly
  - Optional dimension type + value fields
  - Save calls createLine or updateLine
  - _Requirements: 1.3, 1.4_

- [x] 2.3 Create `BudgetNewVersionModal.tsx`
  - Name input, fiscal year input
  - Method selection: Empty / Copy from existing
  - Copy: version selector dropdown
  - "Create" button: creates version or copies
  - _Requirements: 1.5, 1.6_

- [ ] 2.4 AI Suggest Adjustments integration
  - Button on BudgetPage (only for Draft versions)
  - Opens modal with context notes input
  - Shows suggestions with accept/reject per suggestion
  - Accepted suggestions update the corresponding lines
  - _Requirements: 5.5_

## Phase 3: Frontend — Dashboard Tab (~3h)

- [x] 3.1 Create `BudgetDashboardTab.tsx`
  - Active version dropdown (fetches versions where is_active=true)
  - Period selector (month/quarter/ytd/full)
  - Drill-down table: Parent → SubParent → Account
  - Breadcrumb navigation for drill levels
  - Variance color coding (green/red)
  - "No active budget" notification when dropdown is empty
  - AI narrative button + AI query input
  - _Requirements: 2.1–2.8_

- [x] 3.2 Add tab to `FinancialReportsGroup.tsx`
  - Add "📉 Budget vs Actuals" tab (8th tab)
  - Import and render BudgetDashboardTab
  - _Requirements: 2.1_

- [x] 3.3 AI features in dashboard tab
  - AI Narrative button → generates summary text
  - AI Query input → natural language questions
  - Adapted to version_id-based API
  - _Requirements: 2.1_

## Phase 4: Wiring & Cleanup (~3h)

- [x] 4.1 Update `App.tsx`
  - Remove page types: `budget-versions`, `budget-templates`, `budget-lines`, `budget-dashboard`
  - Add single page type: `budget`
  - Update the budget case to render `BudgetPage`
  - Update the redirect logic for FIN module access
  - Update menu navigation to point to `budget` instead of `budget-dashboard`
  - _Requirements: 1.1_

- [x] 4.2 Update `budgetService.ts`
  - Modify: `getDashboard` params — use `version_id` (optional) and `year` (optional)
  - Modify: `activateVersion` — accept `active` boolean parameter
  - _Requirements: 4.3, 4.4, 5.1_

- [ ] 4.3 Update `types/budget.ts`
  - Remove: `BudgetTemplate`, `BudgetTemplateLine`, `BudgetTemplateWithLines`, `TemplateLineRequest`, `CreateTemplateRequest`
  - Remove: `GenerateDraftRequest`, `GenerateDraftData`, `AITemplateRecommendRequest`, `AITemplateRecommendData`, `AITemplateRecommendation`
  - Add: `GenerateLinesRequest`, `GenerateLinesData`, `ProposedBudgetLine`
  - Modify: `DashboardParams` — `version_id` instead of `year`
  - _Requirements: 4.3_

- [ ] 4.4 Update translation files
  - Remove template-related keys
  - Add keys for new UI elements (method selection, review table, etc.)
  - _Requirements: 1.1_

- [ ] 4.5 Delete old files
  - `pages/BudgetVersionsPage.tsx`
  - `pages/BudgetTemplatesPage.tsx`
  - `pages/BudgetLinesPage.tsx`
  - `pages/BudgetDashboard.tsx`
  - `pages/GenerateDraftModal.tsx`
  - `pages/CopyBudgetModal.tsx`
  - `__tests__/BudgetVersionsPage.test.tsx`
  - `__tests__/BudgetLinesPage.test.tsx`
  - _Requirements: 4.3_

## Phase 5: Database Migration (~1h)

- [ ] 5.1 Create migration script to drop template tables
  - `DROP TABLE IF EXISTS budget_template_lines;`
  - `DROP TABLE IF EXISTS budget_templates;`
  - Record in database_migrations table
  - _Requirements: 4.1, 4.2_

- [ ] 5.2 Update `create_budget_tables.py`
  - Remove DDL for `budget_templates` and `budget_template_lines`
  - Keep DDL for `budget_versions` and `budget_lines`
  - _Requirements: 4.1, 4.2_

## Phase 6: Verification (~2h)

- [ ] 6.1 Test budget preparation page end-to-end
  - Create empty version, add lines, edit amounts, delete lines
  - Copy version flow
  - AI draft flow (if API key configured)
  - Status transitions: Draft → Approve → Activate
  - Read-only enforcement on non-Draft versions

- [ ] 6.2 Test dashboard tab
  - Version dropdown shows active versions
  - Selecting version shows budget vs actuals
  - Drill-down navigation works
  - Period filter works
  - No year selector present

- [ ] 6.3 Verify old pages are removed
  - No route to budget-versions, budget-templates, budget-lines, budget-dashboard
  - Menu navigates to single `budget` page
  - FIN Reports has Budget vs Actuals tab

- [ ] 6.4 Run existing backend tests (adapted)
  - budget_service tests pass (template tests removed)
  - budget_routes tests pass
  - Property-based tests still pass (rounding, rollups, tenant isolation)
