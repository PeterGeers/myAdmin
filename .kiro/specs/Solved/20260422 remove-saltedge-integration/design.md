# Remove Obsolete Salt Edge Integration — Bugfix Design

## Overview

The Salt Edge bank connection feature is dead code — the backend API endpoints (`/api/saltedge/*`) were never implemented, and the frontend components reference non-existent services. This bugfix removes all Salt Edge references from the frontend: the `BankConnect.tsx` component, its route in `App.tsx`, the placeholder alert button in `BankingProcessor.tsx`, translation keys in 4 locale files, the help link mapping, and the `connectBank` navigation module entry. The fix is purely subtractive (code deletion) with no new logic introduced.

## Glossary

- **Bug_Condition (C)**: Any code path that references Salt Edge functionality — the `BankConnect` component, `bank-connect` page type, Salt Edge button/alert in BankingProcessor, Salt Edge translation keys, and the `bank-connect` help link
- **Property (P)**: After the fix, no Salt Edge references exist in the codebase and no user-facing UI exposes Salt Edge functionality
- **Preservation**: All existing banking, routing, translation, and help functionality unrelated to Salt Edge continues to work identically
- **BankConnect.tsx**: Dead React component in `frontend/src/components/BankConnect.tsx` that renders a multi-step Salt Edge bank connection wizard calling non-existent `/api/saltedge/*` endpoints
- **PageType**: TypeScript union type in `App.tsx` that defines all valid page routes in the application
- **helpLinks**: Record mapping in `frontend/src/components/help/helpLinks.ts` that maps PageType values to MkDocs documentation sections

## Bug Details

### Bug Condition

The bug manifests when any code path references Salt Edge functionality. The `BankConnect` component makes API calls to non-existent endpoints, the "Bank Verbinden (Salt Edge)" button in BankingProcessor shows a misleading placeholder alert, and the `bank-connect` route renders a broken page. All of this is dead code that confuses users and adds maintenance burden.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type CodeReference
  OUTPUT: boolean

  RETURN input.referencesComponent('BankConnect')
         OR input.referencesPageType('bank-connect')
         OR input.referencesTranslationKey('saltEdgeAlert')
         OR input.referencesTranslationKey('labels.connectBank')
         OR input.referencesTranslationKey('navigation.modules.connectBank')
         OR input.referencesHelpLink('bank-connect')
         OR input.rendersElement('Salt Edge button in BankingProcessor')
END FUNCTION
```

### Examples

- **BankConnect page**: User navigates to `bank-connect` → component renders and calls `/api/saltedge/providers?country=NL` → request fails because no backend endpoint exists → user sees error
- **BankingProcessor button**: User clicks "🏦 Bank Verbinden (Salt Edge)" button → sees misleading alert "Salt Edge integration ready! Waiting for account approval (2 business days)" → no actual integration exists
- **Navigation entry**: Translation key `common:navigation.modules.connectBank` exists with value "Bank Verbinden (Salt Edge)" / "Connect Bank (Salt Edge)" → referenced in code but the dashboard menu button was already removed, leaving orphaned translations
- **Help link**: `bank-connect` maps to `banking/` in helpLinks → route no longer makes sense since the page should not exist

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- The BankingProcessor file processing section (CSV/TSV file selection, process, pattern apply, save) must continue to work exactly as before
- All other routes (pdf, banking, str, str-invoice, str-pricing, fin-reports, str-reports, assets, system-admin, tenant-admin, zzp-\*, settings, migration) must continue to render correctly
- The FIN module access redirect must still correctly redirect from FIN pages (pdf, banking, powerbi, fin-reports, assets) to menu when access is lost
- All non-Salt-Edge translation keys in banking.json and common.json must continue to resolve correctly
- The help system must continue to map all remaining pages to their documentation URLs

**Scope:**
All code paths that do NOT reference Salt Edge functionality should be completely unaffected by this fix. This includes:

- All banking file processing operations (upload, process, pattern matching, save)
- All other page routes and their rendering
- All non-Salt-Edge translation keys across all locale files
- All non-Salt-Edge help link mappings
- Backend code (no changes needed — no Salt Edge endpoints exist)

## Hypothesized Root Cause

This is not a traditional bug with a single root cause — it is accumulated dead code from an incomplete feature implementation:

1. **Incomplete Feature Implementation**: The Salt Edge integration was started on the frontend but the backend API endpoints (`/api/saltedge/*`) were never created. The `BankConnect.tsx` component references 6+ non-existent endpoints.

2. **Placeholder Alert Left Behind**: The "Bank Verbinden (Salt Edge)" button in `BankingProcessor.tsx` (lines ~1117-1122) was added as a placeholder that shows a misleading alert message suggesting the integration is "ready" and "waiting for account approval."

3. **Orphaned Code Artifacts**: The route definition (`bank-connect` in PageType union, switch case, FIN redirect check), translation keys (`saltEdgeAlert`, `connectBank` in banking.json; `connectBank` in common.json), and help link mapping were all created in anticipation of a feature that never materialized.

4. **No Cleanup Performed**: When the dashboard menu button for Salt Edge was removed at some point, the underlying route, component, translations, and help link were not cleaned up.

## Correctness Properties

Property 1: Bug Condition — No Salt Edge References Remain

_For any_ code path in the frontend codebase where a Salt Edge reference previously existed (isBugCondition returns true), the fixed codebase SHALL have that reference completely removed: `BankConnect.tsx` deleted, `bank-connect` removed from PageType union and switch case and FIN redirect check, Salt Edge button removed from BankingProcessor, `saltEdgeAlert` and `labels.connectBank` removed from banking.json (both locales), `navigation.modules.connectBank` removed from common.json (both locales), and `bank-connect` removed from helpLinks.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation — All Non-Salt-Edge Functionality Unchanged

_For any_ code path that does NOT reference Salt Edge functionality (isBugCondition returns false), the fixed codebase SHALL produce exactly the same behavior as the original codebase, preserving all banking file processing, routing, translation resolution, help link mapping, and FIN module access redirect functionality.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Since this is dead code removal, the root cause is clear and the fix is purely subtractive.

**File**: `frontend/src/components/BankConnect.tsx`

**Action**: Delete entire file (268 lines of dead code)

---

**File**: `frontend/src/App.tsx`

**Function**: Module-level imports, `PageType` type, `AppContent` component

**Specific Changes**:

1. **Remove import**: Delete `import BankConnect from './components/BankConnect';` (line 5)
2. **Remove from PageType**: Remove `'bank-connect'` from the PageType union type
3. **Remove from FIN redirect check**: Remove `currentPage === 'bank-connect'` from the `hasFIN` redirect condition
4. **Remove route case**: Delete the entire `case 'bank-connect':` block (~lines 131-142) from the `renderPage` switch statement

---

**File**: `frontend/src/components/BankingProcessor.tsx`

**Specific Changes**:

1. **Remove Salt Edge button**: Delete the `<Button>` element (~lines 1117-1122) that calls `alert(t('messages.saltEdgeAlert'))` with label `t('labels.connectBank')`
2. **Clean up HStack**: The `<HStack justify="space-between" mb={2}>` wrapper may need adjustment since it currently spaces the label and the Salt Edge button — after removing the button, the `justify="space-between"` and `<HStack>` wrapper around the `<FormLabel>` can be simplified

---

**File**: `frontend/src/components/help/helpLinks.ts`

**Specific Changes**:

1. **Remove mapping**: Delete the `'bank-connect': 'banking/',` entry from the `helpLinks` record

---

**File**: `frontend/src/locales/en/banking.json`

**Specific Changes**:

1. **Remove `messages.saltEdgeAlert`**: Delete the `"saltEdgeAlert"` key from the `messages` object
2. **Remove `labels.connectBank`**: Delete the `"connectBank"` key from the `labels` object

---

**File**: `frontend/src/locales/nl/banking.json`

**Specific Changes**:

1. **Remove `messages.saltEdgeAlert`**: Delete the `"saltEdgeAlert"` key from the `messages` object
2. **Remove `labels.connectBank`**: Delete the `"connectBank"` key from the `labels` object

---

**File**: `frontend/src/locales/en/common.json`

**Specific Changes**:

1. **Remove `navigation.modules.connectBank`**: Delete the `"connectBank"` key from the `navigation.modules` object

---

**File**: `frontend/src/locales/nl/common.json`

**Specific Changes**:

1. **Remove `navigation.modules.connectBank`**: Delete the `"connectBank"` key from the `navigation.modules` object

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, confirm the dead code exists and is non-functional (exploratory), then verify the removal is complete and existing functionality is preserved.

### Exploratory Bug Condition Checking

**Goal**: Confirm that the Salt Edge code is indeed dead and non-functional BEFORE removing it. Verify there are no hidden dependencies.

**Test Plan**: Search the codebase for all Salt Edge references and verify that no backend endpoints exist. Run the app and confirm the BankConnect page fails and the alert button is misleading.

**Test Cases**:

1. **Backend Endpoint Check**: Search backend routes for `/api/saltedge` — expect no matches (confirms no backend exists)
2. **BankConnect Component Test**: Render `BankConnect` component — expect API calls to fail since endpoints don't exist (confirms dead code)
3. **Salt Edge Button Test**: Click the "Bank Verbinden" button in BankingProcessor — expect only a placeholder alert, no real functionality
4. **Import Dependency Check**: Search for imports of `BankConnect` — expect only `App.tsx` imports it (confirms limited blast radius)

**Expected Counterexamples**:

- BankConnect component fails to load providers because `/api/saltedge/providers` doesn't exist
- The alert message is hardcoded placeholder text with no actual integration behind it

### Fix Checking

**Goal**: Verify that for all Salt Edge references (bug condition), the code has been completely removed.

**Pseudocode:**

```
FOR ALL reference WHERE isBugCondition(reference) DO
  result := searchCodebase(reference)
  ASSERT result.count == 0
END FOR
```

**Test Cases**:

1. Verify `BankConnect.tsx` file does not exist
2. Verify `PageType` union does not contain `'bank-connect'`
3. Verify `App.tsx` has no `BankConnect` import
4. Verify `App.tsx` switch has no `case 'bank-connect'` block
5. Verify `BankingProcessor.tsx` has no Salt Edge button or alert reference
6. Verify `helpLinks.ts` has no `'bank-connect'` entry
7. Verify `en/banking.json` has no `saltEdgeAlert` or `connectBank` keys
8. Verify `nl/banking.json` has no `saltEdgeAlert` or `connectBank` keys
9. Verify `en/common.json` has no `connectBank` in `navigation.modules`
10. Verify `nl/common.json` has no `connectBank` in `navigation.modules`

### Preservation Checking

**Goal**: Verify that for all non-Salt-Edge functionality, the application behaves identically after the fix.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalBehavior(input) = fixedBehavior(input)
END FOR
```

**Testing Approach**: Since this is purely subtractive (no new logic), preservation checking focuses on verifying that remaining code compiles, routes work, and translations resolve. Property-based testing is less applicable here because the changes are structural deletions rather than logic modifications. Static verification (TypeScript compilation, JSON validation) provides the strongest guarantees.

**Test Cases**:

1. **TypeScript Compilation**: Verify the frontend compiles without errors after all removals — this catches any missed references
2. **Route Preservation**: Verify all remaining PageType values ('pdf', 'banking', 'str', etc.) still have corresponding switch cases
3. **FIN Redirect Preservation**: Verify the FIN redirect check still includes 'pdf', 'banking', 'powerbi', 'fin-reports', 'assets'
4. **Translation Integrity**: Verify all 4 locale JSON files parse correctly and all non-Salt-Edge keys still exist
5. **Help Link Preservation**: Verify all remaining help link mappings are intact

### Unit Tests

- Verify `BankConnect.tsx` file does not exist (file system check)
- Verify `App.tsx` PageType does not include `bank-connect` (grep/static check)
- Verify `BankingProcessor.tsx` does not reference `saltEdgeAlert` or `connectBank` (grep check)
- Verify all 4 locale JSON files are valid JSON after key removal
- Verify `helpLinks.ts` does not contain `bank-connect`

### Property-Based Tests

- Generate random subsets of remaining PageType values and verify each has a valid route handler
- Generate random translation key lookups from the remaining key set and verify they resolve to non-empty strings
- Generate random help link lookups from remaining page types and verify they return valid URLs

### Integration Tests

- Build the frontend (`npm run build`) and verify zero compilation errors — this is the strongest integration test for a code removal task
- Verify the BankingProcessor page renders correctly without the Salt Edge button
- Verify navigation between all remaining pages works end-to-end
