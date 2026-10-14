/**
 * Member Analytics — generic definition-filter + email-field consumption helpers.
 *
 * The analytics-role / jubilee-rule / address-mapping machinery that once lived
 * here has been removed (superseded by the generic Dynamic Pivot Views
 * mechanism). What remains are the two pure helpers the generic surface still
 * needs:
 *
 *   1. `resolveEmailField(fieldConfig)` — resolve the recipient EMAIL field key
 *      from the tenant's field config alone (a field typed `email`, then one of
 *      the conventional email keys). No role indirection.
 *
 *   2. `applyDefinitionFilters(rows, filters, fieldConfig)` — narrow member rows
 *      by a saved set's GENERIC equality definition filters (e.g.
 *      `{ clubblad: 'Papier' }`), the mechanism through which every subset the
 *      removed presets used to offer is now rebuilt generically.
 *
 * Pure + unit-tested. No React, no I/O. Spec:
 * `.kiro/specs/Members/members-analytics-role-removal`.
 */
import type {
  FieldConfig,
  FieldConfigField,
  MemberRow,
} from '../../../types/members';
import { valueFor } from '../fieldValue';

/**
 * Is `key` a field that is present in the resolved field config?
 *
 * Presence means a `fieldConfig.fields` entry carries that exact `key`. An empty
 * / non-string key is never present.
 */
function isFieldPresent(fieldConfig: FieldConfig | undefined, key: unknown): boolean {
  if (typeof key !== 'string' || key === '') {
    return false;
  }
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return false;
  }
  return fields.some((field) => field?.key === key);
}

/**
 * The conventional member email field keys, in resolution priority order. These
 * mirror the backend `members_mail._extract_emails` candidate keys so the field
 * the compose UI resolves is the SAME one the mail route reads off each row
 * (R4.12). The recipient email field is resolved from the tenant's own field
 * config.
 */
export const CONVENTIONAL_EMAIL_KEYS: readonly string[] = [
  'email',
  'e_mail',
  'emailaddress',
  'email_address',
];

/**
 * Resolve the recipient EMAIL field key for a member set (R4.12) from the field
 * config alone.
 *
 * Precedence:
 *   1. a `fieldConfig.fields` entry typed `email`;
 *   2. a `fieldConfig.fields` entry whose key matches one of
 *      {@link CONVENTIONAL_EMAIL_KEYS}, in priority order.
 *
 * Returns the resolved field key, or `undefined` when no email field resolves —
 * the compose UI then disables the send with a bilingual reason rather than
 * mailing an unresolvable set. The result is always a key present in
 * `fieldConfig.fields` (never a dangling key).
 */
export function resolveEmailField(
  fieldConfig: FieldConfig | undefined,
): string | undefined {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return undefined;
  }

  // 1. A field explicitly typed `email`.
  const typedEmail = fields.find(
    (f) => f?.type === 'email' && typeof f.key === 'string' && f.key !== '',
  );
  if (typedEmail?.key) {
    return typedEmail.key;
  }

  // 2. A field whose key is a conventional email key, in priority order.
  for (const candidate of CONVENTIONAL_EMAIL_KEYS) {
    const match = fields.find((f) => f?.key?.toLowerCase() === candidate);
    if (match?.key) {
      return match.key;
    }
  }

  return undefined;
}

/**
 * Resolve the storage group for a field key from the field config, mirroring the
 * pivot adapter's `groupForKey` so a value is read the SAME way everywhere
 * (nested bucket first via {@link valueFor}, then the flat alias).
 */
function groupForKey(
  fieldConfig: FieldConfig | undefined,
  key: string,
): string | undefined {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return undefined;
  }
  const field: FieldConfigField | undefined = fields.find((f) => f?.key === key);
  return field?.group;
}

/**
 * Apply a saved set's GENERIC definition filters to a set of member rows
 * (findings: "field picker cannot save a definition filter"; R4.4).
 *
 * A saved set may carry plain equality filters in `config.filters`, e.g.
 * `{ clubblad: 'Papier' }` (the "clubblad Nederland / paper" set) — one entry
 * per field key, the value the member's field must equal. This narrows the rows
 * to members whose value for each filtered key equals the configured value:
 *
 *   - the member value is read through the shared nested-or-flat {@link valueFor}
 *     accessor (resolving the storage group from the field config first), so a
 *     fixed/overlay/calculated field all resolve the same way the adapter reads
 *     them;
 *   - comparison is as STRINGS, case-insensitive, trimmed, so `'Papier'` matches
 *     a stored `' papier '` and a numeric `1` matches `'1'` — robust to the
 *     stringy shape member values arrive in;
 *   - a BLANK filter value (`''`/`null`/`undefined`) is treated as "no narrowing"
 *     for that key (an unset filter never hides everyone);
 *   - ALL remaining filter entries must match (AND semantics).
 *
 * Row order is preserved and inputs are never mutated (pure). Applied in the
 * Pivot Views panel BEFORE `executeMemberPivot`, because the client adapter
 * aggregates/lists its input rows as-is and does not itself apply
 * `config.filters`. A jubilee / new-member list is reached by the user filtering
 * the calculated years-member / `joined_date` field through this same generic
 * mechanism — there is no dedicated year-selector filter.
 */
export function applyDefinitionFilters(
  rows: MemberRow[],
  filters: Record<string, unknown> | undefined,
  fieldConfig: FieldConfig | undefined,
): MemberRow[] {
  const safeRows = Array.isArray(rows) ? rows : [];
  if (!filters) {
    return safeRows;
  }

  // The active (non-blank) equality filters, pre-resolved to their storage group
  // + normalized comparison value so the row loop stays cheap.
  const active: { group: string | undefined; key: string; expected: string }[] = [];
  for (const [key, raw] of Object.entries(filters)) {
    if (raw === null || raw === undefined) {
      continue;
    }
    const expected = String(raw).trim().toLowerCase();
    if (expected === '') {
      continue; // blank filter → no narrowing for this key
    }
    active.push({ group: groupForKey(fieldConfig, key), key, expected });
  }

  if (active.length === 0) {
    return safeRows;
  }

  return safeRows.filter((row) =>
    active.every(({ group, key, expected }) => {
      const value = valueFor(row, group, key);
      if (value === null || value === undefined) {
        return false;
      }
      return String(value).trim().toLowerCase() === expected;
    }),
  );
}
