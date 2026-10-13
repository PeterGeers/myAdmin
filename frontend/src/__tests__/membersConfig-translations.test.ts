/**
 * Members config shipped-label i18n: completeness + EN/NL parity.
 *
 * Phase 1 — Catalog Backbone, task 5.1 (R3.1, R3.7, R2). The i18n label model
 * is Option (b): shipped field/group/enum-option labels resolve from resource
 * keys under the `admin` namespace, `membersConfig.*` category, per
 * `TRANSLATION_KEY_CONVENTIONS.md` + steering `32-frontend-ui.md`:
 *
 *   fields → admin:membersConfig.field.<fieldKey>
 *   groups → admin:membersConfig.group.<groupKey>
 *   enums  → admin:membersConfig.enum.<fieldKey>.<optionValue>
 *
 * This test is the frontend-plane half of the rule-5 "guard a shared vocabulary
 * with a test" pattern (steering 36 / design §6): it does NOT import `sam.*`.
 * It transcribes the canonical field/group/enum vocabulary from the SAM
 * registries (`sam/members/domain/{fixed_fields,calculated_fields,attribute_catalog}.py`)
 * and asserts the seeded `admin` resource files cover every entry in BOTH
 * languages. If the registries grow a field/group/enum option, add its label
 * here AND in the resource files in the same change (Change-With-Tests contract);
 * a missing seed fails this test rather than drifting silently.
 */

import enAdmin from '../locales/en/admin.json';
import nlAdmin from '../locales/nl/admin.json';

// ---------------------------------------------------------------------------
// Locally-transcribed canonical vocabulary (mirrors the SAM registries — do NOT
// import sam.*; keep in lock-step with fixed_fields.py / calculated_fields.py /
// attribute_catalog.BASE_FUNCTIONAL_GROUPS).
// ---------------------------------------------------------------------------

/** FIXED_FIELDS + CALCULATED_FIELDS canonical keys (unqualified field key). */
const EXPECTED_FIELD_KEYS = [
  // FIXED_FIELDS — personal
  'first_name',
  'last_name',
  'name_infix',
  'initials',
  'birth_date',
  'gender',
  'email',
  'phone',
  'street',
  'postal_code',
  'city',
  'country',
  // FIXED_FIELDS — membership
  'member_number',
  'status',
  'membership_type',
  'joined_date',
  'created_at',
  'updated_at',
  // CALCULATED_FIELDS
  'display_name',
  'age',
  'birthday',
  'birth_day',
  'birth_month',
  'birth_year',
  'birth_quarter',
  'years_member',
  'application_year',
] as const;

/** BASE_FUNCTIONAL_GROUPS keys (attribute_catalog.py). */
const EXPECTED_GROUP_KEYS = ['personal', 'address', 'membership', 'administrative'] as const;

/**
 * Shipped enum option values per enum field (fixed_fields.py `options`). Only
 * `status` ships a canonical option set; `gender` is an OPEN enum (tenant config,
 * no shipped options), so it carries no shipped enum labels.
 */
const EXPECTED_ENUM_OPTIONS: Record<string, readonly string[]> = {
  status: ['application', 'pending', 'active', 'suspended', 'lapsed', 'left'],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type Dict = Record<string, unknown>;

function membersConfigOf(ns: Dict): Dict {
  const mc = ns['membersConfig'];
  expect(mc && typeof mc === 'object' && !Array.isArray(mc)).toBe(true);
  return mc as Dict;
}

function sectionOf(mc: Dict, name: 'field' | 'group' | 'enum'): Dict {
  const s = mc[name];
  expect(s && typeof s === 'object' && !Array.isArray(s)).toBe(true);
  return s as Dict;
}

function expectNonEmptyString(value: unknown): void {
  expect(typeof value).toBe('string');
  expect((value as string).trim().length).toBeGreaterThan(0);
}

const enMc = membersConfigOf(enAdmin as Dict);
const nlMc = membersConfigOf(nlAdmin as Dict);

// ---------------------------------------------------------------------------
// Completeness: every canonical field / group / enum option has a label
// ---------------------------------------------------------------------------

describe('membersConfig i18n: shipped-label completeness (R3.1)', () => {
  it('every FIXED + CALCULATED field key has a non-empty label in nl and en', () => {
    const enField = sectionOf(enMc, 'field');
    const nlField = sectionOf(nlMc, 'field');
    for (const key of EXPECTED_FIELD_KEYS) {
      expectNonEmptyString(enField[key]);
      expectNonEmptyString(nlField[key]);
    }
  });

  it('every BASE_FUNCTIONAL_GROUPS key has a non-empty label in nl and en', () => {
    const enGroup = sectionOf(enMc, 'group');
    const nlGroup = sectionOf(nlMc, 'group');
    for (const key of EXPECTED_GROUP_KEYS) {
      expectNonEmptyString(enGroup[key]);
      expectNonEmptyString(nlGroup[key]);
    }
  });

  it('every shipped enum option value has a non-empty label in nl and en', () => {
    const enEnum = sectionOf(enMc, 'enum');
    const nlEnum = sectionOf(nlMc, 'enum');
    for (const [fieldKey, values] of Object.entries(EXPECTED_ENUM_OPTIONS)) {
      const enOpts = enEnum[fieldKey] as Dict;
      const nlOpts = nlEnum[fieldKey] as Dict;
      expect(enOpts && typeof enOpts === 'object').toBe(true);
      expect(nlOpts && typeof nlOpts === 'object').toBe(true);
      for (const value of values) {
        expectNonEmptyString(enOpts[value]);
        expectNonEmptyString(nlOpts[value]);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Parity: nl and en carry EXACTLY the same key set (no orphan either side)
// ---------------------------------------------------------------------------

describe('membersConfig i18n: EN/NL key parity (R3.7, R2)', () => {
  it('field keys are identical between nl and en', () => {
    expect(Object.keys(sectionOf(nlMc, 'field')).sort()).toEqual(
      Object.keys(sectionOf(enMc, 'field')).sort(),
    );
  });

  it('group keys are identical between nl and en', () => {
    expect(Object.keys(sectionOf(nlMc, 'group')).sort()).toEqual(
      Object.keys(sectionOf(enMc, 'group')).sort(),
    );
  });

  it('enum option keys are identical between nl and en', () => {
    const enEnum = sectionOf(enMc, 'enum');
    const nlEnum = sectionOf(nlMc, 'enum');
    expect(Object.keys(nlEnum).sort()).toEqual(Object.keys(enEnum).sort());
    for (const fieldKey of Object.keys(enEnum)) {
      expect(Object.keys(nlEnum[fieldKey] as Dict).sort()).toEqual(
        Object.keys(enEnum[fieldKey] as Dict).sort(),
      );
    }
  });

  it('field section has no key the registry vocabulary does not declare', () => {
    const expected = new Set<string>(EXPECTED_FIELD_KEYS);
    for (const key of Object.keys(sectionOf(enMc, 'field'))) {
      expect(expected.has(key)).toBe(true);
    }
  });
});
