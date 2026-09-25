/**
 * Shared MODEL helpers for the Members add/edit modals (s5c task 4.4, design C-SURFACE;
 * R5.5, R4.8, R4.9, R4.11, R4.12).
 *
 * These turn the RESOLVED field set (+ optionally a member being edited) into the three things
 * a modal needs and nothing more: the Formik `initialValues`, a `show_when`-aware Yup schema,
 * and the module's NESTED write payload shaped by each field's STORAGE group. Keeping this pure
 * + framework-light lets the add + edit modals share exactly one definition (and lets the tests
 * pin the behavior without rendering a modal).
 *
 * Authority stays server-side (R2.3): the schema/feedback here is convenience — the domain layer
 * re-validates required-ness (incl. `show_when` hidden-not-required), role-gated enum values, and
 * `member_number` format + uniqueness, and stamps the tenant.
 */

import * as Yup from 'yup';
import type {
  FieldConfig, FieldConfigField, LocalizedLabel, Member,
} from '../../types/members';
import { evaluateShowWhen, resolveLabel, isEditableField } from './fieldForm';

/** The flat Formik value map: every editable field keyed by its bare field key + `region`. */
export type FormValues = Record<string, string>;

/** The scope dimension key/values/label for the region control (from the field config). */
export interface ScopeInfo {
  dimensionKey: string;
  regionValues: string[];
  dimensionLabel?: string;
}

/** Resolve the (first enabled) scope dimension + its allowed values + label. */
export function scopeInfo(fieldConfig: FieldConfig | null, lang: string): ScopeInfo {
  const dimension = fieldConfig?.dimensions?.find((d) => d.enabled !== false);
  return {
    dimensionKey: dimension?.key ?? 'region',
    regionValues: dimension?.values ?? [],
    dimensionLabel: dimension
      ? resolveLabel(dimension.label as string | LocalizedLabel | undefined, lang, 'region')
      : undefined,
  };
}

/** Read a field's current value from a (nested or flat) member record. */
function memberValue(member: Member | null, field: FieldConfigField): string {
  if (!member) return '';
  // Scope dimension: the flattened row carries `region` (and the badge value).
  if (field.key === 'region') {
    const v = member.region;
    return v != null ? String(v) : '';
  }
  const bucket = field.group ? (member as Record<string, unknown>)[field.group] : undefined;
  if (bucket && typeof bucket === 'object' && field.key in (bucket as Record<string, unknown>)) {
    const v = (bucket as Record<string, unknown>)[field.key];
    return v != null ? String(v) : '';
  }
  const flat = (member as Record<string, unknown>)[field.key];
  return flat != null ? String(flat) : '';
}

/**
 * Build the flat Formik `initialValues`: every editable field (+ `region`) pre-filled from the
 * member being edited, or blank for a create. The `region` key is always present (the scope
 * control binds to it) even if no `region` field is in the resolved set.
 */
export function buildInitialValues(
  fields: FieldConfigField[],
  member: Member | null,
): FormValues {
  const base: FormValues = { region: member?.region != null ? String(member.region) : '' };
  for (const f of fields) {
    const name = f.key === 'region' ? 'region' : f.key;
    base[name] = memberValue(member, f);
  }
  return base;
}

interface SchemaDeps {
  t: (key: string) => string;
  /** Immediate `member_number` format check (returns an error message or null). */
  memberNumberError: (field: FieldConfigField, value: string, hint: string) => string | null;
}

/**
 * Build a `show_when`-aware Yup schema over the editable fields (R4.12): a required field is
 * ONLY required when it is currently shown (its `show_when` holds against the sibling values), so
 * a hidden field is never demanded client-side — the same rule the server enforces. `email` gets
 * an email check; `member_number` gets the tenant-format check.
 */
export function buildValidationSchema(
  fields: FieldConfigField[],
  { t, memberNumberError }: SchemaDeps,
): Yup.ObjectSchema<Record<string, unknown>> {
  const shape: Record<string, Yup.AnySchema> = {};

  for (const f of fields) {
    if (!isEditableField(f)) continue; // read-only / calculated fields are never validated
    const name = f.key === 'region' ? 'region' : f.key;
    let schema: Yup.StringSchema = Yup.string();

    if (f.key === 'email') {
      schema = schema.email(t('addModal.validation.emailInvalid'));
    }

    // member_number tenant-format check (convenience — server authoritative).
    if (f.key === 'member_number') {
      schema = schema.test(
        'member-number-format',
        t('addModal.validation.memberNumberFormat'),
        (value) => memberNumberError(f, value ?? '', 'x') === null,
      );
    }

    if (f.required) {
      // show_when-aware required: only require the field when it is currently shown.
      schema = schema.test(
        'required-when-shown',
        t('addModal.validation.required'),
        function requiredWhenShown(value) {
          const shown = evaluateShowWhen(f.show_when, this.parent as Record<string, unknown>);
          if (!shown) return true;
          return typeof value === 'string' ? value.trim().length > 0 : value != null;
        },
      );
    }

    shape[name] = schema;
  }

  return Yup.object().shape(shape) as unknown as Yup.ObjectSchema<Record<string, unknown>>;
}

interface PayloadDeps {
  dimensionKey: string;
  /**
   * The member being EDITED, when this is an update (the Add modal passes null). Used to detect
   * a field the user CLEARED: a now-blank field that HAD a value must be sent as `""` so the
   * server clears it. On a create (member null) blanks are simply omitted (nothing to clear).
   */
  member?: Member | null;
}

/**
 * Shape the module's NESTED write payload from the flat Formik values, honoring each field's
 * STORAGE group. A `personal`/`membership` fixed field lands under that nested block; an overlay
 * (variable) field lands under `overlay`; the scope dimension becomes `scope_values.<key>: [v]`.
 * A field HIDDEN by an unmet `show_when` is NOT sent (mirroring the server's hidden-not-required).
 *
 * Blank handling: on a CREATE a blank optional value is dropped (nothing to persist). On an EDIT,
 * a field the user CLEARED (now blank but the member had a value) is sent as `""` so the server
 * clears it — otherwise "wiping" an optional field like the Dutch `tussenvoegsel` would be a
 * silent no-op (a dropped blank means "leave unchanged"). NO tenant field is ever included — the
 * module stamps it authoritatively (Property 2).
 */
export function shapeWritePayload(
  fields: FieldConfigField[],
  values: FormValues,
  { dimensionKey, member }: PayloadDeps,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  const personal: Record<string, unknown> = {};
  const membership: Record<string, unknown> = {};
  const overlay: Record<string, unknown> = {};

  for (const f of fields) {
    // Read-only / calculated fields are never written (R4.4).
    if (!isEditableField(f)) continue;
    // Scope dimension: emitted as scope_values, not a nested field.
    if (f.key === 'region') {
      const v = values.region;
      if (v) body.scope_values = { [dimensionKey]: [v] };
      continue;
    }
    // Skip a field hidden by an unmet show_when (hidden-not-sent, R4.12).
    if (!evaluateShowWhen(f.show_when, values)) continue;

    const raw = values[f.key];
    const blank = raw === undefined || (typeof raw === 'string' && raw.trim() === '');
    let out: unknown = raw;
    if (blank) {
      // On EDIT, only send an explicit clear ("") when the field previously HELD a value; on
      // CREATE (or an already-blank field) drop it. Prevents over-sending empty keys on create.
      const had = member != null && String(memberValue(member, f)).trim() !== '';
      if (!had) continue;
      out = '';
    }

    if (f.group === 'personal') personal[f.key] = out;
    else if (f.group === 'membership') membership[f.key] = out;
    else overlay[f.key] = out;
  }

  if (Object.keys(personal).length > 0) body.personal = personal;
  if (Object.keys(membership).length > 0) body.membership = membership;
  if (Object.keys(overlay).length > 0) body.overlay = overlay;
  return body;
}
