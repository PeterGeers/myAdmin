/**
 * Tests for the enum-subset picker SOURCE resolution (spec 12 — Application Form Serving Redesign,
 * task 4.2; R1.3, design §C1 / redesign A).
 *
 * The pure field-kind rules the modal composes: WHICH kind a resolved field is, whether it is
 * choice-bearing (→ render the picker), and WHERE the subset options come from:
 *  - reference (membership-type) → the LIVE catalog;
 *  - scope axis → the scope DIMENSION values (= the field's own options, single-vocabulary);
 *  - enum → the field's own options;
 *  - plain string → NOT choice-bearing (no picker).
 *
 * Fixtures use the bare `key` + `group` server shape (R2.3).
 */
import { describe, it, expect } from 'vitest';
import type { FieldConfigField, MembershipType } from '../../../../types/members';
import {
  hasOwnOptions,
  isChoiceBearingField,
  isScopeField,
  optionsToChoices,
  resolveChoiceSource,
} from '../applicationChoiceSource';

const CATALOG: MembershipType[] = [
  { type_code: 'regular', label: { en: 'Regular', nl: 'Regulier' } } as MembershipType,
  { type_code: 'student', label: { en: 'Student', nl: 'Student' } } as MembershipType,
];

const referenceField: FieldConfigField = {
  key: 'membership_type',
  group: 'membership',
  type: 'reference',
  // Even if the reference field also (incidentally) carries static options, the source is the
  // live catalog — reference wins the precedence.
  options: ['stale_a', 'stale_b'],
};

const scopeField: FieldConfigField = {
  key: 'region',
  type: 'enum',
  scope: { enabled: true, required_for: ['Member'] },
  options: [
    { value: 'north', label: { en: 'North', nl: 'Noord' } },
    { value: 'south', label: { en: 'South', nl: 'Zuid' } },
  ],
};

const enumField: FieldConfigField = {
  key: 'salutation',
  type: 'enum',
  options: ['mr', 'mrs', 'mx'],
};

const stringField: FieldConfigField = {
  key: 'first_name',
  type: 'string',
};

describe('optionsToChoices — normalises bare and rich option lists', () => {
  it('maps a bare string[] to { value, label{nl,en} }', () => {
    expect(optionsToChoices(['a', 'b'])).toEqual([
      { value: 'a', label: { nl: 'a', en: 'a' } },
      { value: 'b', label: { nl: 'b', en: 'b' } },
    ]);
  });

  it('maps rich options, falling back to value for missing labels', () => {
    expect(
      optionsToChoices([{ value: 'north', label: { en: 'North', nl: 'Noord' } }, { value: 'x' }]),
    ).toEqual([
      { value: 'north', label: { nl: 'Noord', en: 'North' } },
      { value: 'x', label: { nl: 'x', en: 'x' } },
    ]);
  });

  it('yields an empty list for absent / non-array options', () => {
    expect(optionsToChoices(null)).toEqual([]);
    expect(optionsToChoices(undefined)).toEqual([]);
  });
});

describe('field-kind predicates', () => {
  it('isScopeField is true only for an enabled scope axis', () => {
    expect(isScopeField(scopeField)).toBe(true);
    expect(isScopeField(enumField)).toBe(false);
    expect(isScopeField({ key: 'x', scope: { enabled: false } })).toBe(false);
    expect(isScopeField(null)).toBe(false);
  });

  it('hasOwnOptions is true only for a non-empty options list', () => {
    expect(hasOwnOptions(enumField)).toBe(true);
    expect(hasOwnOptions(stringField)).toBe(false);
    expect(hasOwnOptions({ key: 'x', options: [] })).toBe(false);
  });

  it('isChoiceBearingField is true for reference / scope / enum, false for a plain string', () => {
    expect(isChoiceBearingField(referenceField)).toBe(true);
    expect(isChoiceBearingField(scopeField)).toBe(true);
    expect(isChoiceBearingField(enumField)).toBe(true);
    expect(isChoiceBearingField(stringField)).toBe(false);
    expect(isChoiceBearingField(null)).toBe(false);
  });

  it('a membership-type reference field is choice-bearing even with an EMPTY live catalog', () => {
    // The field is choice-bearing by kind; resolveChoiceSource yields an empty choice list the
    // modal surfaces as "no types yet" rather than hiding the picker.
    expect(isChoiceBearingField(referenceField)).toBe(true);
    expect(resolveChoiceSource(referenceField, [], 'en')).toEqual({ kind: 'reference', choices: [] });
  });
});

describe('resolveChoiceSource — SOURCE adapts to the field kind (R1.2 / design §C1)', () => {
  it('reference field → the LIVE catalog (NOT its static options)', () => {
    const src = resolveChoiceSource(referenceField, CATALOG, 'en');
    expect(src?.kind).toBe('reference');
    expect(src?.choices.map((c) => c.value)).toEqual(['regular', 'student']);
  });

  it('scope axis → the scope DIMENSION values (= its own options)', () => {
    const src = resolveChoiceSource(scopeField, CATALOG, 'en');
    expect(src?.kind).toBe('scope');
    expect(src?.choices.map((c) => c.value)).toEqual(['north', 'south']);
  });

  it('enum field → its OWN options', () => {
    const src = resolveChoiceSource(enumField, CATALOG, 'en');
    expect(src?.kind).toBe('enum');
    expect(src?.choices.map((c) => c.value)).toEqual(['mr', 'mrs', 'mx']);
  });

  it('plain string field → null (NOT choice-bearing; the picker does not render)', () => {
    expect(resolveChoiceSource(stringField, CATALOG, 'en')).toBeNull();
    expect(resolveChoiceSource(null, CATALOG, 'en')).toBeNull();
  });
});
