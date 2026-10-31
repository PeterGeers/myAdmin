/**
 * SHARED field-config contract for the PUBLIC member-application form
 * (spec `Members/application-app`, Phase 9 — the single source consolidated in task 9.3).
 *
 * This is the ONE frontend shape of the public field-config read
 * (`GET /public/members/{slug}/field-config`, design §3.1 / R5.3). It is consumed by ALL three
 * Phase-9 seams so they cannot drift (R10a.2 parity):
 *   - the config-driven renderer (task 9.1, `ApplicationFormRenderer`);
 *   - the config-generated Yup schema (task 9.2, `applicationFormSchema`);
 *   - the submit wiring (task 9.3, `ApplicationFormPage`) + the readiness/404 handling (task 9.4).
 *
 * ## Consolidation note (task 9.3)
 *
 * Tasks 9.1 and 9.2 each defined this contract in their own module (9.1 as `PublicField` in
 * `services/applicationApi.ts`; 9.2 as `ApplicationField` in
 * `components/members/application/applicationFieldConfig.ts`). Task 9.3 collapses both onto THIS
 * module — the public application folder, co-located with the renderer that is the primary
 * consumer and where 9.4/9.5 continue the work. `services/applicationApi.ts` RE-EXPORTS these
 * types (so its own public surface + the task-9.1 tests are unchanged) and the schema generator
 * imports from here. The legacy `components/members/application/applicationFieldConfig.ts`
 * re-exports from here too, so no import site breaks while the single source lives here.
 *
 * ## Canonical form key = the DOTTED key (R10a.3 / R2.3 / design §3.2)
 *
 * The form-state / Formik value key for a field is its FULL DOTTED `key` (e.g.
 * `personal.first_name`, `overlay.iban`) — the SAME key the renderer keys its controlled state by
 * (task 9.1), the SAME key the server's 422 `errors[].field` carries (R1a → mapped into Formik by
 * dotted key, R10a.3), and the SAME flat `{ dotted_key: value }` submit shape (design §3.2). The
 * server is authoritative (R2.3/R6.6); keeping ONE key shape across renderer + schema + submit is
 * what lets a server-rejected field display through the identical `FormErrorMessage` wiring as a
 * client error.
 *
 * ## Applicant-safe SUBSET of the authenticated FieldConfig
 *
 * The public schema is deliberately a NARROW subset of the authenticated `FieldConfig`
 * (`types/members.ts`): only what a public applicant needs to SEE a field, pick from the
 * public-safe choice SUBSET (R4a), and have the form mirror the server rules — never staff-only
 * attributes (`read_only`, role-restricted options, internal origins). The server
 * (`ApplicationService.get_public_field_config`) emits exactly this shape and is authoritative.
 */

import type { LocalizedLabel } from '../../../types/members';

/** The platform-known `FieldFormat` checker tokens exposed on the public form (R7.6). */
export type ApplicationFormatChecker = 'EMAIL' | 'IBAN';

/**
 * A declarative field validator attached to a field (R7.1): a platform-known `checker` token plus
 * opaque `params`. The server defines the token SET (a tenant picks a known token, never authors
 * code — R7.7); an unknown/malformed token degrades to "no extra checker" (R7.3) both server- and
 * client-side.
 */
export interface PublicFieldFormat {
  /** Platform-known checker token (EMAIL, IBAN, … — R7.6). Unknown tokens are ignored (R7.3). */
  checker: string;
  /** Opaque checker parameters (reserved; EMAIL/IBAN take none in v1). */
  params?: Record<string, unknown> | null;
}

/** A rich enum option on a public field (application-subset already applied, R4a). */
export interface PublicFieldOption {
  value: string;
  label?: LocalizedLabel | string;
}

/** An enum choice entry as served: either a bare value or a rich `{ value, label }` entry. */
export type PublicChoiceEntry = string | PublicFieldOption;

/**
 * One applicant-facing field as served by the public field-config read (design §3.1) — the SUBSET
 * of the resolved field config the public form is allowed to see.
 *
 *   ResolvedPublicField = {
 *     key(dotted), type, label{nl,en}, functional_group, order,
 *     required(application-required), show_when?,
 *     options?(application-subset-applied — the ONE canonical key, spec 03a / F5), format?({checker,params})
 *   }
 */
export interface PublicField {
  /**
   * The field's DOTTED key (e.g. `personal.email`, `membership.membership_type`). This IS the flat
   * form-state key, the Formik value key, the 422 `errors[].field` key, and the submit key
   * (R4.7/R10a.3/R10a.4). Everything keys off this one id.
   */
  key: string;
  /** Widget driver: `string`/`text`→Input, `enum`/`reference`→Select, `date`→date input. */
  type: string;
  /** Bilingual label; the renderer selects by applicant locale, nl fallback (R6b). Optional. */
  label?: LocalizedLabel;
  /** The functional (display) group the renderer sections + orders by (R4.1). */
  functional_group?: string;
  /** Display order within the group (R4.6). */
  order?: number;
  /**
   * APPLICATION-required (R4b): whether the applicant MUST provide this field. Gated by `show_when`
   * — a field hidden by an unmet condition is neither required nor validated (R4b.5). The server
   * stays authoritative (R6.6); this drives the convenience client gate.
   */
  required?: boolean;
  /**
   * Conditional visibility (R6.3): a map of `{ controllingKey: expected }`, ALL of which must hold
   * (implicit AND). `expected` is a scalar (equality) or an array (membership). Absent/empty means
   * always shown. Same predicate the server enforces (`evaluate_show_when`).
   */
  show_when?: Record<string, unknown> | null;
  /**
   * The enum choice set ALREADY restricted to the application SUBSET (R4a.2) — the ONE canonical
   * key is `options` (the legacy `choices` alias is retired, spec 03a / F5). It may be a bare
   * `string[]` of values or rich `{ value, label }` entries; the schema generator restricts the
   * field to these via `.oneOf(...)` (mirrors server R4a.3) and the renderer draws a Select from them.
   */
  options?: ReadonlyArray<PublicChoiceEntry> | null;
  /** Optional declarative format checker (EMAIL / IBAN, R7). Absent = no extra checker. */
  format?: PublicFieldFormat | null;
}

/**
 * Back-compat alias for the 9.2 name. The schema generator and its tests referred to the field
 * contract as `ApplicationField`; it is the SAME type as {@link PublicField}. Kept so existing
 * imports read naturally after the consolidation.
 */
export type ApplicationField = PublicField;

/** Back-compat alias for the 9.2 format type name. */
export type ApplicationFieldFormat = PublicFieldFormat;

/** The versioned tenant consent notice served with the schema (D26, R12.1a/R12.1c). */
export interface PublicConsentNotice {
  /** Stable version id of the notice revision the applicant is shown/accepts. */
  version: string;
  /** Bilingual notice text (rendered in the applicant locale). */
  text?: LocalizedLabel;
}

/**
 * One entry of the tenant's functional-group DISPLAY CATALOG (spec 13 R2). The server resolves
 * these from the authored `functional_groups` catalog and sends them on the public field-config so
 * the renderer can SECTION the form in the admin-authored order and show the authored group LABEL —
 * not an order guessed from field order, and not a heading derived from the raw group key.
 */
export interface PublicFunctionalGroup {
  /** The group key — matches each field's `functional_group`. */
  key: string;
  /** Bilingual group heading; the renderer selects by applicant locale (nl fallback, R6b). */
  label?: LocalizedLabel;
  /** The admin-authored display order (the `#10/#20/...` sequence). Lower sorts first. */
  order: number;
}

/**
 * The 200 field-config body (design §3.1 `data`): the schema the renderer is driven by, the
 * locales the form offers, and the tenant's versioned consent notice.
 */
export interface PublicFieldConfig {
  /** The applicant-selected fields, each already application-subset / format-applied. */
  fields: PublicField[];
  /**
   * The tenant's functional-group display catalog (spec 13 R2) — the authored `{key,label,order}`
   * per group. Drives group SECTION order (by `order`) and headings (by `label`). Optional/empty
   * when the tenant authored no catalog; the renderer then falls back to key-derived headings and
   * its deterministic default ordering.
   */
  functional_groups?: PublicFunctionalGroup[];
  /** Supported applicant locales (e.g. `["nl","en"]`), default-first (R6b). */
  locales?: string[];
  /** The tenant's versioned consent/privacy notice (consumed by the consent step, task 9.3). */
  notice?: PublicConsentNotice | null;
}

/** Back-compat alias for the 9.2 config type name — identical to {@link PublicFieldConfig}. */
export type ApplicationFieldConfig = PublicFieldConfig;

/**
 * Resolve the application CHOICE SUBSET of an enum field to a bare `string[]` of VALUES, from the
 * ONE canonical `options` key, tolerating both bare-string and rich `{ value }` entries. Returns an
 * empty array when the field declares no options.
 *
 * The read is `options` ONLY — the legacy `?? field.choices` fallback is removed (spec 03a / F5):
 * these are already the public-safe subset served under the single canonical `options` (the server
 * filtered them, R4a.2) — the generator uses them directly as the `.oneOf(...)` allow-list (R4a.3).
 */
export function applicationChoiceValues(field: PublicField): string[] {
  const raw = field.options ?? [];
  const values: string[] = [];
  for (const entry of raw) {
    if (typeof entry === 'string') {
      values.push(entry);
    } else if (entry && typeof entry === 'object' && typeof entry.value === 'string') {
      values.push(entry.value);
    }
  }
  return values;
}

/** Whether a field carries an enum/choice subset (so the generator applies `.oneOf(...)`). */
export function isEnumField(field: PublicField): boolean {
  return applicationChoiceValues(field).length > 0;
}

/**
 * The canonical Formik value key for a field — its FULL DOTTED key (R10a.3 / design §3.2).
 *
 * This deliberately returns the dotted key (NOT the bare tail): the renderer keys its controlled
 * state by the dotted key, the submit shape is `{ dotted_key: value }`, and the server's 422
 * `errors[].field` is the dotted key — so the schema, the renderer, and the server all agree on
 * ONE key. Keeping this a single helper means the three never drift.
 */
export function formKey(field: PublicField): string {
  return field.key;
}
