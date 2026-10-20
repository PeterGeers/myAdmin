/**
 * Members Module API Service
 *
 * The single frontend seam reaching the Members module API (component C7).
 *
 * IMPORTANT: The Members module is a SEPARATE SAM app, NOT the Flask backend.
 * All requests therefore target `MEMBERS_API_BASE_URL` (from
 * `import.meta.env.VITE_MEMBERS_API_BASE_URL`) instead of the Flask
 * `API_BASE_URL` used by `apiService.ts`.
 *
 * Header semantics mirror `frontend/src/services/apiService.ts` exactly:
 *   - `Authorization: Bearer <Cognito ID token>` via `getCurrentAuthTokens()`
 *   - `X-Tenant`   from `localStorage['selectedTenant']` (or a per-call override)
 *   - `X-Language` from `localStorage['i18nextLng']` (default `nl`)
 *   - a single 401 -> refresh-token -> retry-once path
 *
 * The Members API is authenticated purely by the Bearer token — it does NOT
 * use cookies, so requests are sent WITHOUT `credentials: 'include'`.
 *
 * Response envelope: the module wraps every 2xx body as `{ "data": <result> }`.
 * The wrappers unwrap that envelope so callers receive the payload, not the
 * envelope, and `listMembers`/`getMember` additionally flatten the nested
 * member record to the flat `Member` shape the page/types expect.
 *
 * ---------------------------------------------------------------------------
 * STRUCTURE (task 5, pure move — zero behavior change)
 *
 * This module is now a thin BARREL that re-exports the per-resource client
 * groups so every existing import path (`from '.../membersApiService'`) keeps
 * working unchanged. The implementation lives under `./members/`:
 *   - `membersApiClient.ts`             — shared request plumbing (base URL,
 *                                          `membersRequest`, header build, the
 *                                          401 retry, the JSON helpers, envelope
 *                                          unwrap).
 *   - `membersResourceApi.ts`           — member CRUD + export, memberships,
 *                                          analytics-sets (+ delivery / deliver /
 *                                          ad-hoc mail), mail-runs, schedules,
 *                                          preferred list.
 *   - `membersColumnPreferencesApi.ts`  — the per-user column preferences
 *                                          (Session Columns, R6).
 *   - `membersConfigApi.ts`             — field-config + membership-type catalog.
 *
 * _Requirements: R7.3, R7.4_
 */

// --- Shared request plumbing (public surface: `membersRequest` + its options) ---
export { membersRequest } from './members/membersApiClient';
export type { MembersRequestOptions } from './members/membersApiClient';

// --- Members resource group (CRUD, memberships, analytics-sets, mail, schedules, preferred list) ---
export {
  listMembers,
  listMembersPage,
  MEMBERS_FIXED_PAGE_SIZES,
  MEMBERS_PAGE_SIZE_MAX,
  MEMBERS_DEFAULT_PAGE_SIZE,
  searchMembers,
  getMember,
  createMember,
  updateMember,
  deleteMember,
  exportMembers,
  createMembership,
  deliveryFromBackend,
  deliveryToBackend,
  listAnalyticsSets,
  getAnalyticsSet,
  saveAnalyticsSet,
  updateAnalyticsSet,
  deleteAnalyticsSet,
  putAnalyticsSetDelivery,
  deleteAnalyticsSetDelivery,
  deliverAnalyticsSet,
  sendAdHocMail,
  listMailRuns,
  getMailRun,
  deleteMailRun,
  CADENCE_CRON,
  SCHEDULE_CADENCES,
  cadenceToCron,
  cronToCadence,
  listSchedulesForSet,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  getPreferredList,
  savePreferredList,
} from './members/membersResourceApi';
export type {
  AdHocMailBody,
  MembersPageSize,
  MembersCursorPage,
  ListMembersPageOptions,
} from './members/membersResourceApi';

// --- Column-preferences resource group (Session Columns, R6) ---
export {
  getColumnPreferences,
  saveColumnPreferences,
} from './members/membersColumnPreferencesApi';

// --- Config resource group (field-config + membership-type catalog + SAM config write) ---
export {
  getFieldConfig,
  listMembershipTypes,
  createMembershipType,
  updateMembershipType,
  deactivateMembershipType,
  writeConfig,
  writeFieldConfig,
  writeScopeConfig,
} from './members/membersConfigApi';
export type {
  MembersWritableConfigId,
  MembersConfigWriteResult,
} from './members/membersConfigApi';
