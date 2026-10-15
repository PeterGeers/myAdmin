/**
 * Members Overview — shared model constants, the label resolver, and the
 * unified column type. Extracted verbatim from `pages/MembersPage.tsx` during
 * the file-length split (code-quality-fixes 2026-10-15, task 6) with ZERO
 * behaviour change — the page and the extracted overview hooks/components all
 * import these from one place instead of redeclaring them.
 */

import type { FieldConfigField, LocalizedLabel } from '../../../types/members';

/** The always-visible (compact) fixed columns, in display order. Lidnummer (member_number)
 *  leads — it is the member's human-facing identifier (M00000…), NOT the internal member_id UUID. */
export const COMPACT_FIELD_KEYS = ['member_number', 'name', 'email', 'status', 'membership_type'] as const;

/** The leading, always-present fixed column (session-columns R7.1). Pinned first
 *  by the unified column model (design C3) and never removable. */
export const MEMBER_NUMBER_KEY = 'member_number';

/**
 * Legacy per-column label i18n keys for the fixed compact columns + region
 * (session-columns C3). The pre-unification render paths labeled these specific
 * keys from the `members` namespace (`columns.*` / `filters.*`) rather than the
 * field-config label, and the existing suites assert on those exact labels (e.g.
 * `Filter by filters.region`, `Sort by columns.name`). The unified column model
 * preserves them: a fixed key resolves to its legacy i18n label, every other
 * column to its field-config `resolveLabel`.
 */
export const FIXED_COLUMN_LABEL_KEYS: Record<string, string> = {
  member_number: 'columns.memberNumber',
  name: 'columns.name',
  email: 'columns.email',
  status: 'filters.status',
  membership_type: 'filters.type',
  region: 'filters.region',
};

/** Column filter keys — region/status/type plus the compact fixed fields. */
export const INITIAL_FILTERS: Record<string, string> = {
  member_number: '',
  name: '',
  email: '',
  status: '',
  membership_type: '',
  region: '',
};

/** Resolve a possibly-localized label to a plain string for the current lang. */
export function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label;
  return label[lang] || label.nl || label.en || fallback;
}

/**
 * One column in the unified column model (session-columns design C3). A thin
 * wrapper over a resolved `FieldConfigField` in render order — the single shape
 * the one header map + one cell map iterate, so fixed / session columns all flow
 * through identical FilterableHeader wiring (OQ-2).
 */
export type OverviewColumn = { field: FieldConfigField };
