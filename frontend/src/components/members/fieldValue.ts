/**
 * Shared, parameter-driven field-value presentation for the Members surface
 * (s5c task 4.1, design C-SURFACE / C-FIELDS; R5.1, R5.2).
 *
 * The Members table + modals render WHATEVER the resolved field config
 * (`GET /members/field-config` → `FieldConfig`) lists — the fixed base ⊕ the
 * tenant overlay (parameter-driven) ⊕ calculated (derived, read-only) fields —
 * UNIFORMLY. This module is the one place that turns a `FieldConfigField` + a
 * flat member row into a display string, so both the explicit-columns path and
 * the default/full path render a value the SAME way:
 *
 * - honors the field `type` (dates formatted via the shared `formatDate`
 *   locale helper; everything else stringified);
 * - is inherently READ-ONLY — a table cell / detail row is plain text, so a
 *   `calculated` field (origin `calculated`, R4.2/R4.4) is surfaced read-only
 *   exactly like any other value, never as an editable control;
 * - never crashes on a missing/typed-wrong value (an absent value renders as
 *   the placeholder dash).
 *
 * Authority stays server-side (R2.3): the frontend only presents. `visible`
 * (field-level, R5.1) is the authoritative candidate-column gate — a view
 * context only CHOOSES among visible fields; `isColumnCandidate` centralizes
 * that so both render paths agree.
 */

import type { FieldConfigField, Member } from '../../types/members';
import { formatDate } from '../../utils/formatting';

/** The read-only placeholder shown for an absent/blank value. */
export const EMPTY_CELL = '-';

/**
 * Read a member value by its STORAGE group then bare key — the single accessor
 * shared by the overview table cells AND the read-only view modal.
 *
 * A member record keeps its nested storage buckets (`personal`/`membership`/
 * `overlay`) plus flat convenience aliases (see `flattenMember`). Fixed fields
 * (`first_name`, `birth_date`, `joined_date`, ...) live under their group;
 * overlay/derived + convenience keys live flat. This reads the NESTED bucket
 * first (`member[group][key]`), then falls back to the FLAT key
 * (`member[key]`), so both fixed and flat fields resolve the same way and
 * neither render path can silently miss a value.
 */
export function valueFor(
  member: Member,
  group: string | undefined,
  key: string,
): unknown {
  const bucket = group ? (member as Record<string, unknown>)[group] : undefined;
  if (bucket && typeof bucket === 'object' && key in (bucket as Record<string, unknown>)) {
    return (bucket as Record<string, unknown>)[key];
  }
  return (member as Record<string, unknown>)[key];
}

/**
 * Is this field a visible column CANDIDATE (R5.1)? Field-level `visible` is the
 * authoritative gate: an explicit `visible === false` removes the field from the
 * column set regardless of whether a context references it. Omitted/`true` =
 * visible. (View/edit permissions remain server-enforced; this is the UI gate.)
 */
export function isColumnCandidate(field: FieldConfigField): boolean {
  return field.visible !== false;
}

/**
 * Is this field READ-ONLY? Calculated (derived) fields are never editable
 * (R4.4). Presentation cells are always read-only, so this is primarily a signal
 * for the edit modal (task 4.4) — surfaced here so the whole surface shares one
 * definition of "calculated ⇒ read-only".
 */
export function isReadOnlyField(field: FieldConfigField): boolean {
  return field.origin === 'calculated';
}

/**
 * Render a member field value for READ-ONLY display, honoring the field `type`.
 *
 * - `date` → localized date string (via `formatDate`); an unparseable value
 *   falls back to its raw string so nothing is lost.
 * - everything else → the stringified value.
 * - `null`/`undefined`/empty → the {@link EMPTY_CELL} dash.
 *
 * This is the single value formatter for parameter-driven overlay columns AND
 * calculated (read-only) columns, so a `birth_date` (fixed date), a
 * `signature_date` (overlay date), and `display_name`/`years_member`
 * (calculated) all present consistently.
 */
export function renderFieldValue(
  field: FieldConfigField,
  value: unknown,
  lang: string,
): string {
  if (value === null || value === undefined || value === '') {
    return EMPTY_CELL;
  }

  if (field.type === 'date') {
    const formatted = formatDateValue(value, lang);
    if (formatted !== null) return formatted;
    // Unparseable date: fall back to the raw string rather than hide it.
  }

  return String(value);
}

/**
 * Best-effort localized date formatting for a field-config `date` value.
 * Accepts an ISO `YYYY-MM-DD` (or full ISO timestamp) string or a `Date`.
 * Returns `null` when the value cannot be parsed to a valid date, so the caller
 * can fall back to the raw string.
 */
function formatDateValue(value: unknown, lang: string): string | null {
  const date =
    value instanceof Date ? value : new Date(String(value));
  if (Number.isNaN(date.getTime())) return null;
  try {
    return formatDate(date, lang);
  } catch {
    return null;
  }
}
