# Frontend Test Failures — Fixed

**Result:** 0 failed, 834 passed, 37 skipped (60 suites passing, 1 skipped)
**Started at:** 46 failed, 725 passed

## Fixes applied

| Fix                                                                      | Tests fixed             |
| ------------------------------------------------------------------------ | ----------------------- |
| Chakra UI icons mock (`__mocks__/@chakra-ui/icons.tsx`)                  | 33 (unblocked 4 suites) |
| Chakra UI utils moduleNameMapper in Jest config                          | 4 suites could now run  |
| BtwReport: i18n mock, translation key assertions, renderAndSettle helper | 10                      |
| AangifteIbReport: same pattern + YearEndClosureSection mock              | 4                       |
| FilterPanel: Chakra FormControl/Input mocks, SearchFilterConfig type     | 3                       |
| i18n.test: fixed translation key paths to match actual JSON files        | 2                       |
| YearEndClosure: fixed API service mock (authenticatedGet/Post)           | 1                       |
| authentication-flow: i18n mock, Chakra mocks, authService exports        | 3                       |
| BnbActualsReport: API endpoint mocks, filter testid selectors            | 2                       |
| LanguageSelector: Chakra Menu mocks, i18n language state                 | 3                       |
| CredentialsManagement: modal interaction flow, button name matchers      | 12                      |
| UserManagement: translation key assertions, filter selectors             | 10                      |
