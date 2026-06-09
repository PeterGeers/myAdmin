# Remove Obsolete Salt Edge Integration — Tasks

## Phase 1: Exploratory Verification

- [x] 1.1 Search backend for `/api/saltedge` routes to confirm no backend endpoints exist
- [x] 1.2 Search frontend for all imports/references to `BankConnect` to confirm blast radius is limited to `App.tsx`
- [x] 1.3 Search frontend for all references to `saltEdge`, `salt-edge`, `bank-connect`, and `connectBank` to create a complete removal checklist

## Phase 2: Delete Dead Component

- [x] 2.1 Delete `frontend/src/components/BankConnect.tsx`

## Phase 3: Clean Up App.tsx

- [x] 3.1 Remove `import BankConnect from './components/BankConnect';` from `App.tsx`
- [x] 3.2 Remove `'bank-connect'` from the `PageType` union type in `App.tsx`
- [x] 3.3 Remove `currentPage === 'bank-connect'` from the FIN module access redirect check in `App.tsx`
- [x] 3.4 Remove the entire `case 'bank-connect':` route block from the `renderPage` switch in `App.tsx`

## Phase 4: Clean Up BankingProcessor

- [x] 4.1 Remove the Salt Edge `<Button>` element (the one calling `alert(t('messages.saltEdgeAlert'))` with label `t('labels.connectBank')`) from `BankingProcessor.tsx`
- [x] 4.2 Simplify the `<HStack>` wrapper around the file selection label if it no longer needs `justify="space-between"` after button removal

## Phase 5: Clean Up Help Links

- [x] 5.1 Remove the `'bank-connect': 'banking/',` entry from `helpLinks.ts`

## Phase 6: Clean Up Translation Files

- [x] 6.1 Remove `"saltEdgeAlert"` key from `frontend/src/locales/en/banking.json` messages object
- [x] 6.2 Remove `"connectBank"` key from `frontend/src/locales/en/banking.json` labels object
- [x] 6.3 Remove `"saltEdgeAlert"` key from `frontend/src/locales/nl/banking.json` messages object
- [x] 6.4 Remove `"connectBank"` key from `frontend/src/locales/nl/banking.json` labels object
- [x] 6.5 Remove `"connectBank"` key from `frontend/src/locales/en/common.json` navigation.modules object
- [x] 6.6 Remove `"connectBank"` key from `frontend/src/locales/nl/common.json` navigation.modules object

## Phase 7: Verification

- [x] 7.1 Run `npx tsc --noEmit` in the frontend directory to verify TypeScript compilation succeeds with zero errors
- [x] 7.2 Run `npm run build` in the frontend directory to verify the production build succeeds
- [x] 7.3 Grep the entire frontend for any remaining references to `saltedge`, `salt-edge`, `bank-connect`, `BankConnect`, `saltEdgeAlert`, or `connectBank` to confirm complete removal
- [x] 7.4 Validate all 4 modified JSON locale files parse correctly (e.g., `node -e "JSON.parse(require('fs').readFileSync('path'))"`)
