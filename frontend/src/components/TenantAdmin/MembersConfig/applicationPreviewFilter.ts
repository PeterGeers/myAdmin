/**
 * PURE client filter for the Application Form Builder's IN-BROWSER preview (spec 12 —
 * Application Form Serving Redesign, task 5.1; R3.1/R3.2, design §C2 / D4).
 *
 * The in-browser preview replaces the retired server round-trip (`POST /members/application-preview`,
 * deleted in task 5.2). Instead of POSTing the WORKING overlay to the server's
 * `get_public_field_config` filter and rendering the returned schema, the builder feeds its WORKING
 * (in-memory, UNSAVED) draft — the resolved `FieldConfig` ⊕ the one `field_overlay` object — through
 * THIS pure function, which reproduces the server filter's applicant-facing SELECTION entirely in the
 * browser, then hands the result to the shared spec-10 `ApplicationFormRenderer`. No network, so the
 * preview reflects unsaved edits live (R3.1) with no save and no server call.
 *
 * ## What the server filter does (reproduced here)
 *
 * `get_public_field_config` (`sam/members/domain/_membership_writes.py`):
 *   1. resolves the field set (fixed base ⊕ per-tenant overlay) — here the frontend already holds the
 *      RESOLVED `FieldConfig`, and the working overlay carries the UNSAVED application-attribute edits;
 *   2. filters to the application-SELECTED fields (`application_visible`) — nothing the tenant did not
 *      put on the form;
 *   3. projects each exposed field to the applicant-facing shape (`PublicField`): `key` (dotted),
 *      `type`, i18n `label`, `functional_group`, `order`, `show_when`, `required` (the
 *      APPLICATION-required flag, not the staff `required`), `options` (the enum SUBSET via
 *      `application_choices`), and the declarative `format` token.
 *
 * ## Parity (task 5.3, a LATER wave)
 *
 * This module is deliberately kept SEPARATE from the component so task 5.3 can PIN its output to the
 * server `get_public_field_config` via a shared fixture (so retiring the endpoint introduces no
 * drift). Everything here is a pure `(FieldConfig, overlay, …) → PublicFieldConfig` with no React / no
 * network — directly parity-testable.
 *
 * ## Attribute precedence (mirrors `applicationReadiness.fieldIsOnForm`)
 *
 * An application attribute is read from the WORKING overlay first (an unsaved edit wins — by the
 * origin-aware override key `fixed_overrides[{group}.{key}]` for a base field, else the bare
 * `fields[key]`), falling back to the resolved field's SERVED value, then the documented default. This
 * is the SAME precedence the readiness panel's field count uses, so the preview and the count can
 * never disagree.
 */
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig, FieldConfigField, LocalizedLabel, MembershipType } from '../../../types/members';
import type {
  PublicField,
  PublicFieldConfig,
  PublicFieldOption,
} from '../../public/application/applicationFieldConfig';
import { findField } from './overlayModel';
import { isMembershipTypeField, catalogChoices } from './applicationMembershipType';

/** The applicant locales the preview offers (mirrors the server `SUPPORTED_LOCALES`). */
const PREVIEW_LOCALES = ['nl', 'en'] as const;

/**
 * The origin-aware overlay key a field's application attribute is authored under — mirrors
 * `applicationReadiness.overlayKeyFor` / `ApplicationFieldList.writeTarget`. A base /
 * base_overridden field authors under `fixed_overrides[{group}.{key}]`; a tenant-added field under
 * `fields[key]`.
 */
function overlayKeyFor(field: FieldConfigField): string {
  const isBase =
    field.origin === 'fixed' ||
    field.provenance === 'base' ||
    field.provenance === 'base_overridden';
  if (isBase) {
    const group = typeof field.group === 'string' && field.group ? field.group : '';
    return group ? `${group}.${field.key}` : field.key;
  }
  return field.key;
}

/**
 * Read one application attribute off the WORKING overlay (unsaved edit wins), by the origin-aware
 * override key then the bare key. Returns `undefined` when neither overlay entry authors it, so the
 * caller can fall back to the served value.
 */
function overlayAttr<K extends 'application_visible' | 'application_required' | 'application_choices' | 'format'>(
  overlay: MembersConfigValue | undefined,
  field: FieldConfigField,
  attr: K,
): FieldConfigField[K] | undefined {
  const byOverride = findField(overlay, overlayKeyFor(field))?.field[attr];
  if (byOverride !== undefined) return byOverride as FieldConfigField[K];
  const byBare = findField(overlay, field.key)?.field[attr];
  return byBare as FieldConfigField[K] | undefined;
}

/**
 * Is this resolved field ON the public form? Precedence mirrors
 * `applicationReadiness.fieldIsOnForm` EXACTLY (overlay-authored ⊕ served ⊕ default-OFF) so the
 * preview's field set and the readiness count can never disagree.
 */
function fieldIsOnForm(overlay: MembersConfigValue | undefined, field: FieldConfigField): boolean {
  const authored = overlayAttr(overlay, field, 'application_visible');
  if (typeof authored === 'boolean') return authored;
  if (typeof field.application_visible === 'boolean') return field.application_visible;
  return false;
}

/** The effective APPLICATION-required flag (overlay-authored ⊕ served ⊕ default-false). */
function fieldRequired(overlay: MembersConfigValue | undefined, field: FieldConfigField): boolean {
  const authored = overlayAttr(overlay, field, 'application_required');
  if (typeof authored === 'boolean') return authored;
  return !!field.application_required;
}

/** The effective enum SUBSET (overlay-authored ⊕ served); `null`/absent = the full choice set. */
function fieldSubset(
  overlay: MembersConfigValue | undefined,
  field: FieldConfigField,
): string[] | null {
  const authored = overlayAttr(overlay, field, 'application_choices');
  if (authored !== undefined) return (authored as string[] | null) ?? null;
  return field.application_choices ?? null;
}

/** The effective format token (overlay-authored ⊕ served); `null`/absent = no checker. */
function fieldFormat(
  overlay: MembersConfigValue | undefined,
  field: FieldConfigField,
): { checker: string; params?: Record<string, unknown> } | null {
  const authored = overlayAttr(overlay, field, 'format');
  if (authored !== undefined) return (authored as { checker: string; params?: Record<string, unknown> } | null) ?? null;
  return field.format ?? null;
}

/**
 * The field's DOTTED key — the renderer/submit key (R10a.3). The resolved frontend field keys a base
 * field BARE (`membership_type`) with a storage `group` (`membership`), where the server emits the
 * dotted key; compose `{group}.{key}` when the key is not already dotted and a storage group exists,
 * so the preview keys fields the same way the live form does.
 */
function dottedKey(field: FieldConfigField): string {
  if (field.key.includes('.')) return field.key;
  const group = typeof field.group === 'string' && field.group ? field.group : '';
  return group ? `${group}.${field.key}` : field.key;
}

/** Normalise a served label (string | {nl,en}) to the `LocalizedLabel` the renderer selects from. */
function toLocalizedLabel(
  label: string | LocalizedLabel | undefined,
  fallback: string,
): LocalizedLabel {
  if (label && typeof label === 'object') {
    return { nl: label.nl ?? fallback, en: label.en ?? fallback };
  }
  if (typeof label === 'string' && label) return { nl: label, en: label };
  return { nl: fallback, en: fallback };
}

/**
 * Project a served enum field's options to the applicant-facing `{value,label}` list, with the
 * APPLICATION SUBSET applied (R4a.2) — mirrors the server `_public_field_options` for a non-reference
 * enum. `null` subset = the full set (back-compatible). A `membership_type` reference field sources
 * from the LIVE catalog instead (see {@link projectField}).
 */
function projectEnumOptions(
  field: FieldConfigField,
  subset: string[] | null,
): PublicFieldOption[] | undefined {
  const raw = field.options;
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const allowed = subset === null ? null : new Set(subset.map(String));
  const out: PublicFieldOption[] = [];
  for (const opt of raw) {
    if (typeof opt === 'string') {
      if (allowed === null || allowed.has(opt)) out.push({ value: opt, label: { nl: opt, en: opt } });
    } else if (opt && typeof opt === 'object') {
      const value = typeof opt.value === 'string' ? opt.value : String(opt.value ?? '');
      if (!value) continue;
      if (allowed === null || allowed.has(value)) {
        out.push({ value, label: toLocalizedLabel(opt.label, value) });
      }
    }
  }
  return out;
}

/**
 * Project one application-SELECTED resolved field to the applicant-facing {@link PublicField}
 * (mirrors the server `_serialize_public_field`). Reads the effective (overlay ⊕ served) application
 * attributes; a `membership_type` reference field sources its options from the LIVE catalog, filtered
 * to the declared subset (R4a.5) — every other enum from its own served options.
 */
function projectField(
  overlay: MembersConfigValue | undefined,
  field: FieldConfigField,
  catalog: MembershipType[] | null | undefined,
): PublicField {
  const key = dottedKey(field);
  const subset = fieldSubset(overlay, field);

  const out: PublicField = {
    key,
    type: typeof field.type === 'string' ? field.type : 'string',
    label: toLocalizedLabel(field.label, field.key),
    functional_group: field.functional_group || field.group,
    order: typeof field.order === 'number' ? field.order : undefined,
    required: fieldRequired(overlay, field),
  };

  if (field.show_when != null) out.show_when = field.show_when;

  if (isMembershipTypeField(field)) {
    // Reference field → the LIVE catalog, filtered to the declared subset (full set when none).
    const all = catalogChoices(catalog, 'nl').map(
      (c): PublicFieldOption => ({ value: c.value, label: c.label }),
    );
    out.options = subset === null ? all : all.filter((o) => subset.map(String).includes(o.value));
  } else {
    const options = projectEnumOptions(field, subset);
    if (options !== undefined) out.options = options;
  }

  const format = fieldFormat(overlay, field);
  if (format) out.format = format;

  return out;
}

/**
 * Build the applicant-facing {@link PublicFieldConfig} for the IN-BROWSER preview from the WORKING
 * draft — the RESOLVED `FieldConfig` ⊕ the one `field_overlay` object (R3.1 / design §C2). Reproduces
 * the server `get_public_field_config` SELECTION client-side:
 *   - keep only fields that are ON the form (`application_visible`, overlay ⊕ served);
 *   - project each to the applicant shape (type, label, group, order, required, options subset,
 *     format, show_when);
 *   - carry the applicant locales so the renderer's locale selector matches the live form.
 *
 * `notice` is intentionally omitted here (the versioned consent notice is resolved server-side; the
 * preview is an authoring aid and does not stamp a notice). Pure — no network, no React, no mutation.
 */
export function buildPreviewConfig(
  fieldConfig: FieldConfig | null | undefined,
  overlay: MembersConfigValue | undefined,
  membershipTypeCatalog?: MembershipType[] | null,
): PublicFieldConfig {
  const fields = Array.isArray(fieldConfig?.fields) ? fieldConfig!.fields : [];
  const projected = fields
    .filter((f) => fieldIsOnForm(overlay, f))
    .map((f) => projectField(overlay, f, membershipTypeCatalog));

  return {
    fields: projected,
    locales: [...PREVIEW_LOCALES],
    notice: null,
  };
}
