/**
 * Enum-subset picker SOURCE resolution — the R1.3 slice of the Application field modal (spec 12 —
 * Application Form Serving Redesign, task 4.2; design §C1 / redesign A).
 *
 * The per-field modal (`ApplicationFieldModal`) authors the `application_choices` subset for a
 * field that is ON the form. The subset is a strict subset of the field's CHOICES — but WHERE those
 * choices come from depends on the FIELD KIND (design §C1 / R1.2):
 *
 *  - **reference** field (e.g. `membership_type`) → the tenant's LIVE catalog
 *    (`GET /membership-types`, threaded as `membershipTypeCatalog`), NOT the field's static served
 *    choices. The public-safe subset is authored over the real catalog (R4.1/R4.3, carried from
 *    spec 11) — the server re-validates the reference authoritatively.
 *  - **scope** field (`scope.enabled`) → the scope DIMENSION values. Under the single-vocabulary
 *    model (R3.2/R3.3, `types/members.ts::FieldConfigField.scope`) the scope dimension values ARE
 *    the field's own enum values (`options`) — there is no separate `scope.values` list served
 *    back. So a scope field sources its subset from its OWN `options`, but it is choice-bearing by
 *    virtue of being a scope axis even if the server has not (yet) populated `options`.
 *  - **enum / choices** field (a non-scope field carrying `options`) → the field's OWN options.
 *  - **plain string** field (none of the above — no reference, no scope axis, no options) → NOT
 *    choice-bearing. The picker MUST NOT render (fixes the spec 11 choice-on-string bug, R1.3).
 *
 * These are small PURE functions so the field-kind rules are trivially unit-testable and the modal
 * stays thin (mirrors the `applicationMembershipType.ts` pattern). The modal composes them: it asks
 * {@link isChoiceBearingField} whether to render the picker at all, then {@link resolveChoiceSource}
 * for the options + the source kind.
 */
import type { EnumOptionConfig, FieldConfigField, MembershipType } from '../../../types/members';
import { catalogChoices, isMembershipTypeField } from './applicationMembershipType';

/** Which SOURCE the picker's options were drawn from (drives the modal's helper copy + tests). */
export type ChoiceSourceKind = 'reference' | 'scope' | 'enum';

/** A resolved choice normalised to `{ value, label{nl,en} }` for the subset picker. */
export interface ResolvedChoice {
  value: string;
  label: { nl: string; en: string };
}

/**
 * Normalise a field's served enum vocabulary (`options`) to `{ value, label{nl,en} }` (mirrors
 * `ApplicationFieldAttributes.resolveChoices` / `MembersFieldModal.optionsToChoices`). The server
 * serves enum/scope values under `options` — a rich `{ value, label{nl,en}, roles? }` list OR a
 * bare `string[]`. An absent / non-array `options` yields an empty list.
 */
export function optionsToChoices(
  options: Array<string | EnumOptionConfig> | null | undefined,
): ResolvedChoice[] {
  if (!Array.isArray(options)) return [];
  return options.map((opt) => {
    if (typeof opt === 'string') return { value: opt, label: { nl: opt, en: opt } };
    const value = typeof opt.value === 'string' ? opt.value : String(opt.value ?? '');
    return { value, label: { nl: opt.label?.nl ?? value, en: opt.label?.en ?? value } };
  });
}

/** Is this field a scope AXIS (R3.5/R3.6)? Its subset sources from the scope dimension values. */
export function isScopeField(field: FieldConfigField | null | undefined): boolean {
  return !!field && !!field.scope && field.scope.enabled === true;
}

/**
 * Does this field have its OWN static enum options (an `enum` / `choices` field)? A non-array /
 * empty `options` is NOT choice-bearing on this axis (a plain string field has no options).
 */
export function hasOwnOptions(field: FieldConfigField | null | undefined): boolean {
  return !!field && Array.isArray(field.options) && field.options.length > 0;
}

/**
 * Is this field CHOICE-BEARING — i.e. should the enum-subset picker render at all (R1.3)? True for a
 * reference field (membership-type → the live catalog), a scope axis (scope dimension values), or an
 * enum field with its own options. FALSE for a plain string field — the picker MUST NOT render for
 * it (the spec 11 choice-on-string bug this task fixes).
 *
 * The membership-type reference field is choice-bearing even when the live catalog is EMPTY (the
 * picker renders with an explanatory "no types yet" state rather than vanishing); likewise a scope
 * axis is choice-bearing by virtue of being a scope axis. An enum field is choice-bearing only when
 * it actually carries options.
 */
export function isChoiceBearingField(field: FieldConfigField | null | undefined): boolean {
  if (!field) return false;
  return isMembershipTypeField(field) || isScopeField(field) || hasOwnOptions(field);
}

/** The resolved picker SOURCE: where the options came from, and the options themselves. */
export interface ChoiceSource {
  /** The source kind — drives the modal's helper copy + is asserted by tests. */
  kind: ChoiceSourceKind;
  /** The selectable choices in display order. May be empty (e.g. an empty membership catalog). */
  choices: ResolvedChoice[];
}

/**
 * Resolve the enum-subset picker SOURCE for a field, adapting to its KIND (R1.2 / design §C1):
 *
 *  - reference (membership-type) → the LIVE catalog (`catalog`), NOT the field's static options;
 *  - scope axis → the scope dimension values = the field's own `options` (single-vocabulary);
 *  - enum → the field's own `options`.
 *
 * Returns `null` for a NON-choice-bearing (plain string) field — the caller renders NO picker
 * (R1.3). Precedence is reference → scope → enum, so the membership-type field always sources from
 * the live catalog even if it also (incidentally) carries static options, and a scope axis sources
 * from its own options as the scope dimension values.
 */
export function resolveChoiceSource(
  field: FieldConfigField | null | undefined,
  catalog: MembershipType[] | null | undefined,
  lang: 'nl' | 'en',
): ChoiceSource | null {
  if (!field) return null;
  // reference → the live catalog (R4.1/R4.3).
  if (isMembershipTypeField(field)) {
    return { kind: 'reference', choices: catalogChoices(catalog, lang) };
  }
  // scope axis → the scope DIMENSION values, which ARE the field's own options (R3.2/R3.3).
  if (isScopeField(field)) {
    return { kind: 'scope', choices: optionsToChoices(field.options) };
  }
  // enum → the field's own options.
  if (hasOwnOptions(field)) {
    return { kind: 'enum', choices: optionsToChoices(field.options) };
  }
  // plain string field → not choice-bearing; the picker does not render (R1.3).
  return null;
}
