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
import type { FilterClause, FilterOperator } from '../../../types/pivot';
import { normalizeClause } from '../../../types/pivot';
import { valueFor } from '../fieldValue';

// ---------------------------------------------------------------------------
// Type → operator mapping (pure helpers)
// ---------------------------------------------------------------------------

/**
 * The operators every field type offers, regardless of type (the universal set).
 * `empty` / `notEmpty` are presence checks (no value input); `eq` / `ne` are the
 * always-valid equality operators (`eq` is also the reset target when a field's
 * type change invalidates the current operator).
 */
const UNIVERSAL_OPERATORS: readonly FilterOperator[] = [
  'eq',
  'ne',
  'empty',
  'notEmpty',
];

/**
 * The ordering operators offered for `number` / `date` fields (numeric/date
 * comparison; no substring/regex on numbers or dates).
 */
const NUMERIC_DATE_OPERATORS: readonly FilterOperator[] = [
  'eq',
  'ne',
  'gt',
  'gte',
  'lt',
  'lte',
  'empty',
  'notEmpty',
];

/**
 * The text operators offered for `string` / `enum` / `reference` / `email` /
 * absent/other fields: equality plus substring + regex, each with its negated
 * form. `notContains` / `notRegex` are value-TAKING (they compare a present
 * value), so they are NOT presence checks.
 */
const TEXT_OPERATORS: readonly FilterOperator[] = [
  'eq',
  'ne',
  'contains',
  'notContains',
  'regex',
  'notRegex',
  'empty',
  'notEmpty',
];

/** The operators that take NO value input — the presence checks only. */
const NO_VALUE_OPERATORS: ReadonlySet<FilterOperator> = new Set<FilterOperator>([
  'empty',
  'notEmpty',
]);

/**
 * The resolved {@link FieldConfigField.type} values that use the numeric/date
 * ordering operator set. Every other type (including `string`, `enum`,
 * `reference`, `email`, and an absent/unknown type) uses the text set.
 */
const NUMERIC_DATE_TYPES: ReadonlySet<string> = new Set(['number', 'date']);

/**
 * The operators a filter row offers for `field`, derived from the field's
 * resolved `type` per the design's type→operator mapping (a pure function of the
 * field type):
 *
 *   - `number` / `date`  → `eq, ne, gt, gte, lt, lte, empty, notEmpty`
 *     (numeric/date ordering; no substring/regex);
 *   - `string` / `enum` / `reference` / `email` / absent/other
 *                        → `eq, ne, contains, notContains, regex, notRegex, empty, notEmpty`
 *     (text ops incl. substring + regex, each with its negated form);
 *   - EVERY type always includes `eq, ne, empty, notEmpty` (the universal ops).
 *
 * The `fieldConfig` argument is accepted for signature parity with the design's
 * `operatorsForField(field, fieldConfig)` contract and the other
 * config-consuming helpers (so a caller can resolve the field from a key); the
 * mapping itself depends only on the resolved field type. It is prefixed `_` to
 * mark it intentionally unused by the body (repo `no-unused-vars` convention).
 *
 * Pure: returns a fresh array, never mutates its inputs.
 */
export function operatorsForField(
  field: FieldConfigField | undefined,
  _fieldConfig?: FieldConfig | undefined,
): FilterOperator[] {
  const type = typeof field?.type === 'string' ? field.type : undefined;
  if (type !== undefined && NUMERIC_DATE_TYPES.has(type)) {
    return [...NUMERIC_DATE_OPERATORS];
  }
  return [...TEXT_OPERATORS];
}

/**
 * Whether `op` is a presence check that takes NO value input (`empty` /
 * `notEmpty`). All other operators — INCLUDING the negated text operators
 * `notContains` / `notRegex` — are value-taking and return `false`.
 *
 * Pure: no side effects.
 */
export function operatorTakesNoValue(op: FilterOperator): boolean {
  return NO_VALUE_OPERATORS.has(op);
}

// Re-export so the universal set is importable where the picker needs the
// always-valid reset target without re-deriving it.
export { UNIVERSAL_OPERATORS };

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
 * Resolve the declared `type` for a field key from the field config (e.g.
 * `'number'`, `'date'`, `'string'`). Drives the typed-ordering comparison in
 * {@link applyDefinitionFilters} (numeric for `number`, date for `date`, locale
 * string otherwise). Returns `undefined` when the key is absent or carries no
 * type.
 */
function typeForKey(
  fieldConfig: FieldConfig | undefined,
  key: string,
): string | undefined {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return undefined;
  }
  const field: FieldConfigField | undefined = fields.find((f) => f?.key === key);
  return typeof field?.type === 'string' ? field.type : undefined;
}

/**
 * Compile `pattern` to a case-insensitive {@link RegExp}, or return `null` when
 * the pattern is invalid — the never-match sentinel shared by BOTH `regex` and
 * `notRegex`. A `null` sentinel means neither form matches any row (regex never
 * matches; notRegex never excludes-and-returns), so an invalid pattern yields no
 * narrowing-by-exclusion and the engine never throws.
 */
function tryCompileRegex(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern, 'i');
  } catch {
    return null;
  }
}

/** The value-taking comparison operators (everything but `empty`/`notEmpty`). */
const VALUE_TAKING_OPERATORS: ReadonlySet<FilterOperator> = new Set<FilterOperator>([
  'eq',
  'ne',
  'gt',
  'gte',
  'lt',
  'lte',
  'contains',
  'notContains',
  'regex',
  'notRegex',
]);

/** The ordering operators that use the typed (numeric/date/string) comparison. */
const ORDERING_OPERATORS: ReadonlySet<FilterOperator> = new Set<FilterOperator>([
  'gt',
  'gte',
  'lt',
  'lte',
]);

/** A single active clause, pre-resolved to its storage group, type, and
 *  (for regex/notRegex) its compiled never-match-guarded pattern. */
interface ActiveClause {
  group: string | undefined;
  key: string;
  op: FilterOperator;
  /** Trimmed comparison value (empty for presence ops). */
  value: string;
  /** Resolved field type (drives typed ordering), or `undefined`. */
  fieldType: string | undefined;
  /** Compiled RegExp for regex/notRegex, or `null` (never-match sentinel). */
  compiled: RegExp | null;
}

/** trim + lowercase — the exact legacy `eq`/`ne` normalization. */
function norm(value: string): string {
  return value.trim().toLowerCase();
}

/**
 * Compare the row cell and clause values under an ordering operator, typed by
 * the field's resolved type:
 *   - `number` + both finite-numeric  → numeric compare;
 *   - `date`   + both valid dates      → Date-ms compare;
 *   - otherwise                        → locale string compare of trimmed values.
 */
function compareOrdering(
  op: FilterOperator,
  cell: string,
  expected: string,
  fieldType: string | undefined,
): boolean {
  let cmp: number;

  const cellTrim = cell.trim();
  const expTrim = expected.trim();

  if (fieldType === 'number') {
    const a = Number(cellTrim);
    const b = Number(expTrim);
    if (
      cellTrim !== '' &&
      expTrim !== '' &&
      Number.isFinite(a) &&
      Number.isFinite(b)
    ) {
      cmp = a - b;
    } else {
      cmp = cellTrim.localeCompare(expTrim);
    }
  } else if (fieldType === 'date') {
    const a = new Date(cellTrim).getTime();
    const b = new Date(expTrim).getTime();
    if (!Number.isNaN(a) && !Number.isNaN(b)) {
      cmp = a - b;
    } else {
      cmp = cellTrim.localeCompare(expTrim);
    }
  } else {
    cmp = cellTrim.localeCompare(expTrim);
  }

  switch (op) {
    case 'gt':
      return cmp > 0;
    case 'gte':
      return cmp >= 0;
    case 'lt':
      return cmp < 0;
    case 'lte':
      return cmp <= 0;
    default:
      return false;
  }
}

/**
 * Does a member's `cellValue` for a field match a single active `clause`?
 *
 * Presence (`empty`/`notEmpty`) is decided purely on whether the cell has a
 * non-blank trimmed value. For every value-taking operator an ABSENT cell is
 * excluded (never matches) BEFORE any comparison — so `notContains` / `notRegex`
 * exclude an absent cell too (the negation applies only to the comparison of a
 * PRESENT value, not to presence).
 */
function matchesClause(cellValue: unknown, clause: ActiveClause): boolean {
  const present =
    cellValue !== null &&
    cellValue !== undefined &&
    String(cellValue).trim() !== '';

  switch (clause.op) {
    case 'empty':
      return !present;
    case 'notEmpty':
      return present;
    default:
      break;
  }

  // Value-taking ops never match an absent cell.
  if (!present) {
    return false;
  }

  const cell = String(cellValue);
  switch (clause.op) {
    case 'eq':
      return norm(cell) === norm(clause.value);
    case 'ne':
      return norm(cell) !== norm(clause.value);
    case 'contains':
      return cell.toLowerCase().includes(clause.value.trim().toLowerCase());
    case 'notContains':
      return !cell.toLowerCase().includes(clause.value.trim().toLowerCase());
    case 'regex':
      return clause.compiled !== null && clause.compiled.test(cell);
    case 'notRegex':
      // Invalid pattern → compiled is null → matches NO row (same guard as
      // regex; never "match everything").
      return clause.compiled !== null && !clause.compiled.test(cell);
    case 'gt':
    case 'gte':
    case 'lt':
    case 'lte':
      return compareOrdering(clause.op, cell, clause.value, clause.fieldType);
    default:
      return false;
  }
}

/**
 * Apply a saved set's definition filters to a set of member rows, with the
 * operator-aware, type-adaptive semantics of the member-analytics filter
 * contract (R5.1–5.13, R6.1–6.4, R7.1/7.2/7.5/7.6, R8.1/8.3).
 *
 * Each filters entry is read through {@link normalizeClause}, so BOTH the new
 * object form (`{ clubblad: { op: 'gte', value: '25' } }`) AND the legacy scalar
 * form (`{ clubblad: 'Papier' }` → `{ op: 'eq', value: 'Papier' }`, including
 * year keys like `years_member`) flow through the same engine, and an unknown
 * stored op clamps to `eq`.
 *
 * Per-operator semantics (all defined regardless of the field's type, so a
 * hand-edited/legacy clause with an unexpected op still behaves):
 *   - `eq` / `ne` — trimmed, case-insensitive string (in)equality (the legacy
 *     default; `' papier '` matches `'Papier'`, numeric `1` matches `'1'`);
 *   - `contains` / `notContains` — case-insensitive substring (`notContains` the
 *     exact negation of `contains` on a PRESENT value);
 *   - `gt` / `gte` / `lt` / `lte` — typed ordering: numeric on a `number` field
 *     when both parse finite, by date on a `date` field when both parse valid,
 *     else locale string compare of the trimmed values;
 *   - `regex` / `notRegex` — case-insensitive {@link RegExp} match / non-match,
 *     guarded by {@link tryCompileRegex}: an INVALID pattern compiles to a
 *     never-match sentinel so BOTH forms match NO row (never "match everything")
 *     and the engine never throws;
 *   - `empty` / `notEmpty` — presence checks (no value input).
 *
 * The member value is read through the shared nested-or-flat {@link valueFor}
 * accessor (resolving the storage group from the field config first), so a
 * fixed/overlay/calculated field all resolve the same way the adapter reads them.
 *
 * Activation / narrowing rules:
 *   - a value-taking op with a BLANK value (`''`/`null`/`undefined`, legacy or
 *     object) is inactive — it applies no narrowing (an unset filter never hides
 *     everyone); `empty`/`notEmpty` and `regex`/`notRegex` are always kept (a bad
 *     pattern is pre-compiled to the never-match sentinel);
 *   - a value-taking op NEVER matches an absent cell (so `notContains`/`notRegex`
 *     EXCLUDE an absent cell too — the negation is on the comparison of a present
 *     value, not on presence);
 *   - ALL active clauses must match (AND semantics).
 *
 * Row order is preserved and inputs are never mutated (pure); a non-array `rows`
 * input yields `[]`, an absent/empty `filters` yields all rows. Applied in the
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

  // Build the active clauses, pre-resolving each entry's storage group, field
  // type, and (for regex/notRegex) its never-match-guarded compiled pattern so
  // the row loop stays cheap. Order of entries is preserved (object insertion
  // order) — AND semantics make the order immaterial to the result.
  const active: ActiveClause[] = [];
  for (const [key, raw] of Object.entries(filters)) {
    const clause: FilterClause | null = normalizeClause(raw);
    if (clause === null) {
      continue; // null/undefined entry → no narrowing
    }

    const op = clause.op;
    const value = (clause.value ?? '').trim();

    // A value-taking op with a blank value is inactive (no narrowing).
    if (VALUE_TAKING_OPERATORS.has(op) && value === '') {
      continue;
    }

    const compiled =
      op === 'regex' || op === 'notRegex' ? tryCompileRegex(value) : null;

    active.push({
      group: groupForKey(fieldConfig, key),
      key,
      op,
      value,
      fieldType: ORDERING_OPERATORS.has(op)
        ? typeForKey(fieldConfig, key)
        : undefined,
      compiled,
    });
  }

  if (active.length === 0) {
    return safeRows;
  }

  return safeRows.filter((row) =>
    active.every((clause) =>
      matchesClause(valueFor(row, clause.group, clause.key), clause),
    ),
  );
}
