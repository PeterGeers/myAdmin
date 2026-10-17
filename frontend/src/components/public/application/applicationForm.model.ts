/**
 * Config-driven model helpers for the PUBLIC member-application renderer
 * (spec Members/application-app, task 9.1).
 *
 * Pure, framework-light functions that turn the public field-config
 * ({@link PublicFieldConfig}) into the things the renderer needs and nothing more: the ordered
 * groups to section by, the applicant-locale label, the `show_when` visibility predicate, and the
 * flat initial form state. Keeping them pure lets the tests pin the behaviour without rendering.
 *
 * These deliberately mirror the AUTHENTICATED Members form helpers
 * (`components/members/fieldForm.ts`) — `resolveLabel`, `evaluateShowWhen`, group-and-order — so
 * the two field renderers agree on the shared field model. The public contract differs only in
 * that each field carries its DOTTED `key` and its `functional_group` as a plain string (there is
 * no separate functional-group catalog with labels on the public schema, design §3.1), so grouping
 * is by the `functional_group` value directly.
 *
 * Authority is server-side (R6.6): everything here is presentation. The Yup generation (task 9.2),
 * the 422→Formik merge (task 9.3), and the readiness/404 handling (task 9.4) layer on top — this
 * module leaves those seams (it does not generate validation or submit).
 *
 * _Requirements: R4, R4.1, R4.6, R6.3, R6b, R10a.4_
 */

import type { LocalizedLabel } from '../../../types/members';
import type { PublicField, PublicFieldOption } from './applicationFieldConfig';
import { applicationChoiceValues } from './applicationFieldConfig';

/** The applicant locale set the form understands; everything else falls back to `nl` (R6b). */
export const SUPPORTED_LOCALES = ['nl', 'en'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

/** The default + fallback locale (R6b.2) — never an error on an absent/invalid value. */
export const DEFAULT_LOCALE: SupportedLocale = 'nl';

/**
 * Normalise an arbitrary locale input to a supported locale, falling back to `nl` (R6b.2).
 * An absent, blank, or unsupported value is NOT an error — it resolves to the default.
 */
export function resolveLocale(input: string | null | undefined): SupportedLocale {
  const lang = (input ?? '').slice(0, 2).toLowerCase();
  return (SUPPORTED_LOCALES as readonly string[]).includes(lang)
    ? (lang as SupportedLocale)
    : DEFAULT_LOCALE;
}

/**
 * Resolve a bilingual label to a plain string for the applicant locale, with the shared i18n
 * fallback chain (R6b): the active locale, then `en`, then `nl`, then the field key — NEVER blank.
 * A blank entry at a higher tier is treated as ABSENT so the next tier fills it (never render "").
 * Matches `components/members/fieldForm.ts::resolveLabel` and the SAM `LABEL_FALLBACK_ORDER`.
 */
export function resolveLabel(
  label: LocalizedLabel | string | undefined,
  locale: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label || fallback;
  return label[locale as keyof LocalizedLabel] || label.en || label.nl || fallback;
}

/**
 * Evaluate a field's `show_when` against the flat form values (R6.3), using the SAME predicate the
 * server enforces (`evaluate_show_when`): a map of `{ controllingKey: expected }`, ALL of which
 * must hold (implicit AND). `expected` is a scalar (equality) or an array (membership). A
 * controlling key is looked up by its exact (dotted) key, tolerating a bare-tail key. An
 * absent/empty `show_when` means always-shown.
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

/** Look up a (possibly dotted) controlling key in the flat values, tolerant of the bare tail. */
function lookupValue(values: Record<string, unknown>, key: string): unknown {
  if (key in values) return values[key];
  if (key.includes('.')) {
    const tail = key.slice(key.lastIndexOf('.') + 1);
    if (tail in values) return values[tail];
  }
  return undefined;
}

/** One ordered section the renderer draws: a functional group and its ordered fields. */
export interface FieldGroup {
  /** The `functional_group` value (the section key). */
  key: string;
  /** The fields in this group, in `(order, key)` order. */
  fields: PublicField[];
}

/**
 * Group the public fields by `functional_group` then order them, deterministically (R4.1/R4.6).
 *
 * Group order follows the order of FIRST appearance of each group across the input, with fields
 * inside a group ordered by `(field.order, field.key)` — the `key` tiebreak keeps equal-`order`
 * ties stable and permutation-invariant rather than leaking the input order. A field with no
 * `functional_group` falls into a single trailing default group so it is surfaced, never dropped.
 */
export function groupFieldsByFunctionalGroup(fields: PublicField[]): FieldGroup[] {
  const DEFAULT_GROUP = '__default__';
  const buckets = new Map<string, PublicField[]>();
  // Preserve first-appearance group order; the default bucket sorts last regardless.
  const groupOrder: string[] = [];

  for (const f of fields) {
    const key = f.functional_group || DEFAULT_GROUP;
    if (!buckets.has(key)) {
      buckets.set(key, []);
      if (key !== DEFAULT_GROUP) groupOrder.push(key);
    }
    buckets.get(key)!.push(f);
  }
  if (buckets.has(DEFAULT_GROUP)) groupOrder.push(DEFAULT_GROUP);

  const byOrderThenKey = (a: PublicField, b: PublicField): number =>
    (a.order ?? 0) - (b.order ?? 0) || a.key.localeCompare(b.key);

  return groupOrder.map((key) => ({
    key,
    fields: buckets.get(key)!.slice().sort(byOrderThenKey),
  }));
}

/**
 * Build the FLAT initial form state keyed by each field's DOTTED key (R10a.4): every field present
 * with an empty string so the control is always controlled from first render. This flat map IS the
 * submit shape (`{ dotted_key: value }`, design §3.2) — `unflattenFields` (applicationApi) converts
 * it to the nested member shape when needed for a parity check.
 */
export function buildInitialValues(fields: PublicField[]): Record<string, string> {
  const values: Record<string, string> = {};
  for (const f of fields) values[f.key] = '';
  return values;
}

/** Map a public field `type` to an HTML input type (string→text, number→number, date→date). */
export function inputTypeFor(field: PublicField): string {
  if (field.type === 'number') return 'number';
  if (field.type === 'date') return 'date';
  return 'text';
}

/** Whether a field is rendered as a Select (enum/reference with options) vs a plain Input. */
export function isSelectField(field: PublicField): boolean {
  return (
    (field.type === 'enum' || field.type === 'reference') &&
    applicationChoiceValues(field).length > 0
  );
}

/**
 * Normalise a field's choice set (modern `options` or legacy `choices`, bare-string OR rich
 * `{ value, label }`) into rich {@link PublicFieldOption} entries the renderer draws. A bare string
 * becomes `{ value }` with no label, so the label resolver falls back to the value itself (R4a).
 */
export function optionEntries(field: PublicField): PublicFieldOption[] {
  const raw = field.options ?? field.choices ?? [];
  return raw.map((entry) =>
    typeof entry === 'string' ? { value: entry } : { value: entry.value, label: entry.label },
  );
}
