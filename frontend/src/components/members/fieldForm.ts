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
  MembershipType,
} from '../../types/members';

/** The key of the synthesized default section for fields with no (or a dangling) group. */
export const DEFAULT_SECTION_KEY = '__default__';

/** The bare field key of the catalog-backed membership-type dropdown (design C-SURFACE, R5.8). */
export const MEMBERSHIP_TYPE_FIELD_KEY = 'membership_type';

/**
 * Whether `field` is the catalog-backed `membership_type` reference (R5.8, enum-source #3). Its
 * dropdown options are the tenant's ACTIVE **Lidmaatschap Beheer** catalog entries — fetched via
 * `listMembershipTypes(true)` (`GET /membership-types?active_only=true`), NOT authored on the
 * field — so it is rendered from the injected catalog feed rather than the field's own `options`.
 */
export function isMembershipTypeField(field: FieldConfigField): boolean {
  return field.key === MEMBERSHIP_TYPE_FIELD_KEY;
}

/**
 * Turn the ACTIVE membership-type catalog feed (`listMembershipTypes(true)`) into `{ value, label }`
 * dropdown options (R5.8). Each entry's `key` is the reference `value` the member record stores; its
 * bilingual `label` (or plain string) is resolved for display by the caller. Only active entries are
 * ever fed in (the service returns active-only), so no client-side active filtering is needed here —
 * the domain re-validates the chosen type against the live active catalog authoritatively.
 */
export function membershipTypeOptions(
  types: MembershipType[] | null | undefined,
): EnumOptionConfig[] {
  return (types ?? [])
    // The API returns `type_code` (the reference value the member record stores); older
    // callers/tests used `key`. Prefer `type_code`, fall back to `key`.
    .map((mt) => ({ code: mt?.type_code ?? mt?.key, label: mt?.label }))
    .filter((mt): mt is { code: string; label: MembershipType['label'] } =>
      typeof mt.code === 'string' && mt.code.length > 0)
    .map((mt) => ({
      value: mt.code,
      label: typeof mt.label === 'string' ? { nl: mt.label, en: mt.label } : mt.label,
    }));
}

/** A resolved, ordered section of fields to render in a modal (design C-SURFACE, R4.9). */
export interface FieldSection {
  /** The functional-group key (or {@link DEFAULT_SECTION_KEY} for the fallback section). */
  key: string;
  /** The section heading label (localized), or `undefined` for the default section. */
  label?: LocalizedLabel;
  /** The fields in this section, in field `order`. */
  fields: FieldConfigField[];
}

/** Resolve a possibly-localized label to a plain string for the current lang, else `fallback`. */
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
 * A field is EDITABLE when it is not read-only. Calculated fields (origin `calculated`) are
 * always read-only (R4.4); the server may also mark any field `read_only`. A read-only field is
 * shown in the view modal / disabled in edit, and never included in the write payload.
 */
export function isEditableField(field: FieldConfigField): boolean {
  return field.read_only !== true && field.origin !== 'calculated';
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
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
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
 * C-SURFACE). Section order follows the tenant's `functional_groups` catalog `order`; a field
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
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

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
