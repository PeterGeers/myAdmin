/**
 * Shared, parameter-driven FORM logic for the Members modals (s5c task 4.4, design C-SURFACE;
 * R5.5, R4.8, R4.9, R4.11, R4.12).
 *
 * The view/edit/add modals render WHATEVER the resolved field config
 * (`GET /members/field-config` → `FieldConfig`) lists — the fixed base ⊕ tenant overlay ⊕
 * calculated fields — SECTIONED by each field's parameter-driven `functional_group` (R4.9),
 * honoring field-level view/edit permissions, `show_when` conditional visibility (R4.12), and
 * value-level role-restricted enum options (R4.11/R4.12). This module is the ONE place that
 * turns the resolved field set + the current form values + the caller's roles into the shape the
 * modals render, so the add/edit/view modals all agree:
 *
 * - `groupFieldsBySection` buckets the editable/visible fields into ordered sections keyed by
 *   `functional_group` (falling back to a default section for a dangling/absent group);
 * - `evaluateShowWhen` implements the SAME predicate the server enforces
 *   (`evaluate_show_when` in `sam/members/domain/field_resolver.py`) so a field hidden client-side
 *   is exactly the field the server does not require;
 * - `optionsForCaller` filters an enum field's options to the caller's permitted values (the
 *   convenience gate — the domain rejects a disallowed value authoritatively);
 * - `memberNumberError` gives IMMEDIATE format feedback for the manual-entry `member_number`
 *   string (R4.8) — the server stays authoritative;
 * - `isEditableField` / `resolveLabel` centralize the read-only + i18n rules.
 *
 * Authority stays server-side (R2.3): everything here is presentation/convenience. The domain
 * layer re-validates required-ness, role-gated values, `member_number` format + uniqueness, and
 * `show_when` hidden-not-required.
 */

import type {
  EnumOptionConfig,
  FieldConfig,
  FieldConfigField,
  FunctionalGroup,
  LocalizedLabel,
} from '../../types/members';
import type { LazyOption } from '../common/lazySelect.types';

/** The key of the synthesized default section for fields with no (or a dangling) group. */
export const DEFAULT_SECTION_KEY = '__default__';

/** A resolved, ordered section of fields to render in a modal (design C-SURFACE, R4.9). */
export interface FieldSection {
  /** The functional-group key (or {@link DEFAULT_SECTION_KEY} for the fallback section). */
  key: string;
  /** The section heading label (localized), or `undefined` for the default section. */
  label?: LocalizedLabel;
  /** The fields in this section, in field `order`. */
  fields: FieldConfigField[];
}

/**
 * Resolve a possibly-localized label to a plain string for the current lang, else `fallback`.
 *
 * The missing-locale fallback chain is the Option-(b) i18n contract (R3.5, design §3): the active
 * locale, then `en`, then `nl`, then the canonical key (`fallback`) — NEVER blank. The
 * locale-independent tail (`en` → `nl`) matches the SAM artifact's recorded
 * `LABEL_FALLBACK_ORDER = ("en", "nl")` (`sam/members/domain/attribute_catalog.py`), so the
 * serializer and the frontend resolve a missing locale the SAME way. A blank/empty value at a
 * higher-precedence tier is treated as ABSENT so the next tier fills it (never render "").
 *
 * Re-exported from the ONE shared {@link resolveLabel} util (the `'en-first'` i18n contract,
 * the shared default) so this historical import path stays stable while the logic lives in
 * `components/members/labelResolver.ts` (code-quality-fixes-2026-10-28 task 1).
 */
export { resolveLabel } from './labelResolver';

/**
 * A field is EDITABLE when it is not read-only. Calculated fields (origin `calculated`) are
 * always read-only (R4.4); the server may also mark any field `read_only`. A read-only field is
 * shown in the view modal / disabled in edit, and never included in the write payload.
 */
export function isEditableField(field: FieldConfigField): boolean {
  return field.read_only !== true && field.origin !== 'calculated';
}

/**
 * A field is CALCULATED (derived / read-only) when it is NOT editable — the exact complement of
 * {@link isEditableField} over the same per-field flag (`origin === 'calculated'` or the
 * server-set `read_only`, R4.4). Defined as the complement so the edit/view partition can never
 * drift from the editable rule.
 *
 * The edit modal EXCLUDES these fields from display (members-overview-tweaks R2.2); the view modal
 * KEEPS them (R3.1) — the view renders the full resolved set, calculated fields included.
 */
export function isCalculatedField(field: FieldConfigField): boolean {
  return !isEditableField(field);
}

/**
 * Partition a resolved field list down to its EDITABLE fields, dropping every calculated field
 * (members-overview-tweaks R2.1, R2.2). This is the set the Edit_Modal renders: every editable
 * field is kept and every calculated field is excluded — not disabled, excluded. The view modal
 * does NOT use this (R3.1, R3.2): it keeps the full resolved set.
 *
 * Order and identity are preserved for the kept fields — this only removes the calculated ones.
 */
export function editableFields(fields: FieldConfigField[]): FieldConfigField[] {
  return fields.filter((f) => !isCalculatedField(f));
}

/**
 * Evaluate a field's `show_when` condition against the current form values (R4.12).
 *
 * Convention (shared verbatim with the server's `evaluate_show_when`): `show_when` is a map of
 * `{ controllingKey: expected }`, ALL of which must hold (implicit AND). `expected` may be a
 * single scalar (the value must equal it) or an array (the value must be one of them). A
 * controlling key is looked up in the flat form values (the modal keeps a flat value map). An
 * absent/empty `show_when` means the field is always shown.
 */
export function evaluateShowWhen(
  showWhen: Record<string, unknown> | null | undefined,
  values: Record<string, unknown>,
): boolean {
  if (!showWhen) return true;
  for (const [key, expected] of Object.entries(showWhen)) {
    const actual = lookupValue(values, key);
    if (Array.isArray(expected)) {
      if (!expected.map(String).includes(String(actual))) return false;
    } else if (String(actual) !== String(expected)) {
      return false;
    }
  }
  return true;
}

/** Look up a (possibly dotted) controlling key in the flat form values, tolerant of the bare key. */
function lookupValue(values: Record<string, unknown>, key: string): unknown {
  if (key in values) return values[key];
  // A dotted key (e.g. "membership.membership_type") maps to its bare tail in the flat form.
  if (key.includes('.')) {
    const tail = key.slice(key.lastIndexOf('.') + 1);
    if (tail in values) return values[tail];
  }
  return undefined;
}

/**
 * Whether a field is a rich enum with `{ value, label, roles? }` options (R4.11). A field whose
 * `options` is a bare `string[]` (or the `membership_type` catalog feed, handled by task 4.7) is
 * NOT treated as a rich-enum here.
 */
export function richEnumOptions(field: FieldConfigField): EnumOptionConfig[] | null {
  if (!Array.isArray(field.options) || field.options.length === 0) return null;
  const rich = field.options.filter(
    (o): o is EnumOptionConfig => typeof o === 'object' && o !== null && 'value' in o,
  );
  return rich.length > 0 ? rich : null;
}

/**
 * Adapt a rich-enum `EnumOptionConfig` to the `LazySelect` `LazyOption` shape. These are two
 * distinct option models that overlap but are not assignable: `EnumOptionConfig.label` is a
 * `LocalizedLabel` (an `{ [locale]: string | undefined }` map) whereas `LazyOption.label` is a
 * `string | Record<string, string>`, and `EnumOptionConfig.roles` is `string[] | null` whereas
 * `LazyOption.roles` is `string[] | undefined`. We therefore MAP rather than cast: the localized
 * label is narrowed to a `Record<string, string>` (dropping `undefined` locale entries so the
 * value type matches), and a `null` roles list becomes `undefined`. `LazySelect`'s own
 * `resolveOptionLabel` then handles locale selection at render time, matching the Members
 * `resolveLabel` convention.
 */
export function enumOptionToLazyOption(opt: EnumOptionConfig): LazyOption {
  const label = normalizeLocalizedLabel(opt.label);
  return {
    value: opt.value,
    ...(label !== undefined ? { label } : {}),
    ...(opt.roles ? { roles: opt.roles } : {}),
  };
}

/**
 * Narrow a `LocalizedLabel` (whose index signature permits `undefined` values) to a plain
 * `Record<string, string>` keeping only the defined locale entries, so it satisfies
 * `LazyOption.label`. Returns `undefined` when the input is absent or has no usable entries.
 */
function normalizeLocalizedLabel(
  label: LocalizedLabel | undefined,
): Record<string, string> | undefined {
  if (!label) return undefined;
  const out: Record<string, string> = {};
  for (const [locale, value] of Object.entries(label)) {
    if (typeof value === 'string') out[locale] = value;
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

/**
 * Filter an enum field's options to those the caller may SELECT (R4.12). An option with no
 * `roles` is open to anyone who may edit the field; a role-restricted option is kept only when
 * the caller holds one of its roles. This is CONVENIENCE filtering — the domain authoritatively
 * rejects a write that sets a disallowed value, so a stale/hand-crafted value is still caught.
 */
export function optionsForCaller(
  options: EnumOptionConfig[],
  callerRoles: string[],
): EnumOptionConfig[] {
  const roles = new Set(callerRoles);
  return options.filter(
    (o) => !o.roles || o.roles.length === 0 || o.roles.some((r) => roles.has(r)),
  );
}

/**
 * Immediate format feedback for the manual-entry `member_number` string (R4.8): returns an error
 * message key-agnostic string when `value` violates the tenant format, else `null`. The server is
 * authoritative (it also enforces uniqueness); this only gives the user early feedback.
 *
 * A blank value returns `null` here (the required-ness gate handles emptiness); a non-blank value
 * is checked against the effective `regex` from the field's `member_number_format`.
 */
export function memberNumberError(
  field: FieldConfigField,
  value: string,
  hint: string,
): string | null {
  const fmt = field.member_number_format;
  if (!fmt || !fmt.regex) return null;
  if (!value || !value.trim()) return null;
  let re: RegExp;
  try {
    re = new RegExp(fmt.regex);
  } catch {
    return null; // a malformed tenant regex is a server-side config concern; don't block typing
  }
  return re.test(value) ? null : hint;
}

/**
 * The editable fields of a resolved config, in `order`, honoring visibility + read-only rules.
 *
 * Excludes: fields explicitly `visible === false` (R5.1), and — when `editableOnly` — read-only
 * fields (calculated / server-marked). The `member_id` / system-timestamp fields are excluded
 * from EDIT (they are never user input) but a caller can still surface them read-only in a view.
 */
export function formFields(config: FieldConfig | null): FieldConfigField[] {
  const fields = config?.fields ?? [];
  return fields
    .filter((f) => f.visible !== false)
    .filter((f) => !NON_INPUT_KEYS.has(f.key))
    .slice()
    // Within-section field order = `(order, key)` — the `key` tiebreak makes equal-`order` ties
    // deterministic (R6.4, design §5): display position is stable across re-renders/re-projections
    // and permutation-invariant, rather than leaking the input order through a stable sort.
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.key.localeCompare(b.key));
}

/**
 * Keys handled separately (system-managed) — excluded from BOTH the sectioned form and view
 * body: `member_id` is surfaced explicitly, and the system timestamps are not member-facing.
 * Read-only / calculated fields are NOT excluded here — they render (disabled in edit, plain in
 * view); the schema/payload skip them.
 */
const NON_INPUT_KEYS = new Set<string>(['member_id', 'created_at', 'updated_at']);

/**
 * Bucket the given fields into ordered SECTIONS keyed by `functional_group` (R4.9, design
 * C-SURFACE). Section order follows the tenant's `functional_groups` catalog `(order, key)` — the
 * group `key` is the deterministic tiebreak for equal `order` (R6.4, design §5); a field
 * whose group is undefined or dangling (not in the catalog) falls into a single default section
 * appended last (Property 7 — never a crash). Sections with no fields are dropped.
 */
export function groupFieldsBySection(
  fields: FieldConfigField[],
  catalog: FunctionalGroup[] | undefined,
): FieldSection[] {
  const catalogByKey = new Map<string, FunctionalGroup>();
  (catalog ?? []).forEach((g) => catalogByKey.set(g.key, g));

  const buckets = new Map<string, FieldConfigField[]>();
  for (const f of fields) {
    const g = f.functional_group;
    const key = g && catalogByKey.has(g) ? g : DEFAULT_SECTION_KEY;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push(f);
  }

  const orderedCatalog = (catalog ?? [])
    .slice()
    // Section order = `(group.order, group.key)` — the `key` tiebreak makes equal-`order` group
    // ties deterministic (R6.4, design §5), so section order does not depend on the catalog's
    // input order.
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.key.localeCompare(b.key));

  const sections: FieldSection[] = [];
  for (const g of orderedCatalog) {
    const bucket = buckets.get(g.key);
    if (bucket && bucket.length > 0) {
      sections.push({ key: g.key, label: g.label, fields: bucket });
    }
  }
  const fallback = buckets.get(DEFAULT_SECTION_KEY);
  if (fallback && fallback.length > 0) {
    sections.push({ key: DEFAULT_SECTION_KEY, fields: fallback });
  }
  return sections;
}
