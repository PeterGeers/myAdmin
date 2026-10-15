/**
 * Members Module API — column-preferences resource group (task 5, pure move).
 *
 * Column preferences (Session Columns, R6) — a 1:1 mirror of the preferred-list
 * (`columns` ↔ `refs`). One ordered list of field-config KEYS per user, keyed
 * server-side by the authenticated Cognito `sub` (user ≠ member — R11.1; the
 * client never sends a `sub`). The backend returns `{ sub, columns, updated_at }`
 * wrapped in the `{ data }` envelope; an unset list comes back with
 * `columns: []` (empty is valid, not an error — R6.4). The persisted list holds
 * field keys only (never member data — R6.6/R6.7); `member_number` is
 * implied/always-first and need not be stored (R7.3).
 *
 * Extracted verbatim from `membersApiService.ts`; behaviour unchanged.
 */

import type { MemberColumnPreferences } from '../../types/members';
import { getJson, putJson, unwrapData } from './membersApiClient';

/** The raw backend column-preferences shape (`columns` ordered field keys). */
interface RawColumnPreferences {
  sub?: string;
  columns?: unknown;
  page_size?: unknown;
  updated_at?: string;
}

/** Coerce a raw backend record into the typed `MemberColumnPreferences`. */
function mapColumnPreferences(
  raw: RawColumnPreferences
): MemberColumnPreferences {
  const columns = Array.isArray(raw.columns)
    ? raw.columns.filter(
      (c): c is string => typeof c === 'string' && c.length > 0
    )
    : [];
  // The optional per-user rows-per-page preference (Phase 2 pagination re-home,
  // R2.3). Carried through only when it is a finite number; anything else
  // (absent, null, string, NaN) maps to `null` so the page-size resolver falls
  // through to the tenant default / platform default. The resolver itself still
  // guards for positivity — this map only preserves a well-typed value.
  const pageSize =
    typeof raw.page_size === 'number' && Number.isFinite(raw.page_size)
      ? raw.page_size
      : null;
  return {
    sub: typeof raw.sub === 'string' ? raw.sub : '',
    columns,
    page_size: pageSize,
    updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : '',
  };
}

/**
 * GET /members/column-preferences — the current user's chosen overview columns.
 *
 * Keyed server-side on the authenticated `sub`; returns `columns: []` when the
 * user has never saved column preferences (empty is valid, not an error — the
 * page falls back to the admin default, R6.4).
 */
export async function getColumnPreferences(): Promise<MemberColumnPreferences> {
  const payload = await getJson<unknown>('/members/column-preferences');
  return mapColumnPreferences(unwrapData<RawColumnPreferences>(payload));
}

/**
 * PUT /members/column-preferences — replace the current user's chosen columns
 * with `columns` (a FULL replace — exactly one list per user, R6.5). Pass `[]`
 * to clear. The backend drops blank/duplicate/non-candidate keys and stamps
 * `updated_at`.
 */
export async function saveColumnPreferences(
  columns: string[]
): Promise<MemberColumnPreferences> {
  const payload = await putJson<unknown>('/members/column-preferences', {
    columns,
  });
  return mapColumnPreferences(unwrapData<RawColumnPreferences>(payload));
}
