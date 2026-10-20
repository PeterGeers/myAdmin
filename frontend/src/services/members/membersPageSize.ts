/**
 * Members rows-per-page selector constants + type (spec 02, Task 1.17 / Req 25).
 *
 * Kept in a STANDALONE module (not the `membersApiService` barrel) so UI code
 * — `MembersPaginationBar` + `useMembersCursorPaging` — imports the option list
 * and the platform fallback DIRECTLY. The barrel re-exports these for callers,
 * but MembersPage integration tests `vi.mock('services/membersApiService')`
 * (auto-mock), which would blank out a const array re-exported through the
 * barrel; importing from here keeps the selector options real under that mock.
 */

/**
 * The runtime Rows_Per_Page_Selector options (R25.1): the fixed numeric sizes
 * applied as the DynamoDB Query `Limit`, plus the `'max'` sentinel (R25.3 — one
 * Query page with NO `Limit`, up to the natural ~1 MB boundary; NOT all rows).
 * There is no tenant `default_page_size` (retired, R25.9).
 */
export type MembersPageSize = 50 | 100 | 250 | 500 | 'max';

/** The fixed numeric options, in presentation order (the `'max'` option is separate). */
export const MEMBERS_FIXED_PAGE_SIZES: readonly MembersPageSize[] = [50, 100, 250, 500];

/** The `'max'` sentinel — one DynamoDB Query page, no `Limit` (R25.3). */
export const MEMBERS_PAGE_SIZE_MAX: MembersPageSize = 'max';

/** The platform-fallback initial pre-selected option (R25.9 — no tenant default). */
export const MEMBERS_DEFAULT_PAGE_SIZE: MembersPageSize = 50;
