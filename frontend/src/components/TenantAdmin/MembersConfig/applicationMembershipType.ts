/**
 * Membership-type coherence helpers — the R4 slice of the Application Form Builder (spec 11,
 * R4.1–R4.3, design §3 table / §9 / spec-10 D21).
 *
 * The membership-type field is SPECIAL on the public application form. These are the small PURE
 * functions the per-field attributes panel (`ApplicationFieldAttributes`) special-cases on top of
 * the generic R3 controls. Keeping the logic here (not in the component) makes the coherence rules
 * trivially unit-testable and keeps the builder edit minimal (the collision note on tasks 3.4/4.1).
 *
 * The three rules this module encodes:
 *
 *  - **Identify the membership-type field (R4).** The canonical field is the `membership` storage
 *    group's `membership_type` key — dotted key `membership.membership_type` on the SAM plane
 *    (`sam/members/domain/_membership_errors.py::MEMBERSHIP_TYPE_FIELD_KEY`). On the resolved
 *    frontend field its `key` is `membership_type` and its storage `group` is `membership`.
 *  - **Subset over the LIVE catalog (R4.1/R4.3).** When the membership-type field is on the form the
 *    public-safe subset is authored over the tenant's LIVE membership-type catalog
 *    (`GET /membership-types`, `listMembershipTypes`) — NOT just the static field choices — and a
 *    subset value MUST be a code in that live catalog (the server re-validates via
 *    `_validate_membership_type_reference`, R4.3 / R8; the UI guards it as convenience).
 *  - **Non-empty-when-exposed-required (R4.2).** An exposed membership-type field is
 *    application-required with a non-empty subset (spec 10 D21). An EMPTY authored subset on an
 *    exposed-required membership-type field is INCOHERENT — the UI surfaces a validation state
 *    (the server also rejects via task 1.1's subset ⊆ choices; the UI flags it as convenience).
 */
import type { FieldConfigField, MembershipType } from '../../../types/members';
import { resolveFieldConfigLabel } from '../../../services/membersConfigService';

/** The canonical storage group + key of the membership-type field (mirrors the SAM constant). */
const MEMBERSHIP_STORAGE_GROUP = 'membership';
const MEMBERSHIP_TYPE_KEY = 'membership_type';

/** A catalog code normalised to `{ value, label{nl,en} }` for the subset picker over the LIVE set. */
export interface CatalogChoice {
  value: string;
  label: { nl: string; en: string };
}

/**
 * Is this resolved field the tenant's membership-type field (R4)? The canonical key is the
 * `membership`-storage-group `membership_type` field. We accept either the storage-group-qualified
 * identity (`group === 'membership'` AND `key === 'membership_type'`) or the bare canonical key
 * (`key === 'membership_type'`) so a config that serves the field without the storage group still
 * resolves — the membership-type field is identified by its well-known key, not a per-tenant flag.
 */
export function isMembershipTypeField(field: FieldConfigField | null | undefined): boolean {
  if (!field) return false;
  if (field.key !== MEMBERSHIP_TYPE_KEY) return false;
  // A field keyed `membership_type` is the catalog reference field; the storage group, when
  // served, confirms it (and never contradicts — the SAM field lives in the `membership` group).
  return field.group === undefined || field.group === MEMBERSHIP_STORAGE_GROUP;
}

/** The authoritative catalog code for an entry — `type_code` is authoritative, `key` a legacy alias. */
export function catalogCodeOf(entry: MembershipType): string {
  return entry.type_code ?? entry.key ?? '';
}

/**
 * The membership-type field's selectable subset values sourced from the LIVE catalog (R4.1), NOT
 * the field's static served `options`. ALL catalog entries are offered (incl. retired) so an admin
 * can see every value; the server's `_validate_membership_type_reference` is the authority on which
 * values are acceptable (R4.3). Ordered as the catalog is passed (the manager sorts `(order,
 * type_code)`); a blank code is skipped. Returns `{ value, label{nl,en} }` for the picker.
 */
export function catalogChoices(
  catalog: MembershipType[] | null | undefined,
  lang: 'nl' | 'en',
): CatalogChoice[] {
  if (!Array.isArray(catalog)) return [];
  return catalog
    .map((entry) => {
      const value = catalogCodeOf(entry);
      if (!value) return null;
      const resolved = resolveFieldConfigLabel(entry.label, lang, value);
      // `resolveFieldConfigLabel` returns the locale-resolved string; mirror it to both locales so
      // the picker renders a stable label regardless of the active language.
      return { value, label: { nl: resolved, en: resolved } } as CatalogChoice;
    })
    .filter((c): c is CatalogChoice => c !== null);
}

/** The set of valid catalog codes (R4.3 — the live catalog the subset is validated against). */
export function catalogCodeSet(catalog: MembershipType[] | null | undefined): Set<string> {
  return new Set(catalogChoices(catalog, 'en').map((c) => c.value));
}

/**
 * Validate an authored subset against the live catalog (R4.2/R4.3), for an EXPOSED membership-type
 * field. The outcome drives the UI's validation state (and mirrors what the SAM write enforces):
 *
 *  - `empty` — an exposed-required membership-type field with an authored-but-empty subset is
 *    INCOHERENT (R4.2). `null`/absent means "the full catalog" (the coherent default), which is NOT
 *    empty; only an explicit empty list is flagged.
 *  - `unknownValues` — subset entries that are NOT codes in the live catalog (R4.3). A subset value
 *    not in the catalog is rejected by the server (`_validate_membership_type_reference`); the UI
 *    flags it so the admin cannot save an invalid value.
 *
 * `ok` is `true` only when neither problem holds. A non-array `subset` (null/absent = full set) is
 * always `ok` — the admin has not authored a (possibly empty/invalid) explicit subset.
 */
export interface MembershipSubsetValidation {
  ok: boolean;
  empty: boolean;
  unknownValues: string[];
}

export function validateMembershipSubset(
  subset: unknown[] | null | undefined,
  catalog: MembershipType[] | null | undefined,
): MembershipSubsetValidation {
  // null/absent subset = the full catalog = coherent (never flagged).
  if (!Array.isArray(subset)) {
    return { ok: true, empty: false, unknownValues: [] };
  }
  const known = catalogCodeSet(catalog);
  const values = subset.map((v) => String(v));
  const empty = values.length === 0;
  const unknownValues = values.filter((v) => !known.has(v));
  return { ok: !empty && unknownValues.length === 0, empty, unknownValues };
}
