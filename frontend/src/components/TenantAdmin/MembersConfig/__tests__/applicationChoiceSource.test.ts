/**
 * Tests for the enum-subset picker SOURCE resolution (spec 12 — Application Form Serving Redesign,
 * task 4.2; R1.3, design §C1 / redesign A).
 *
 * The pure field-kind rules the modal composes: WHICH kind a resolved field is, whether it is
 * choice-bearing (→ render the picker), and WHERE the subset options come from:
 *  - reference (membership-type) → the field's OWN options (03b; live catalog retired);
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
  // Spec 03b: membership_type is a normal enum field that owns its vocabulary — the source is the
  // field's OWN options (the live catalog is retired).
  options: [
    { value: 'regular', label: { en: 'Regular', nl: 'Regulier' } },
    { value: 'student', label: { en: 'Student', nl: 'Student' } },
  ],
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

  it('a membership-type reference field is choice-bearing even with NO options yet (03b 9b.2)', () => {
    // Choice-bearing by kind; with an empty own-options list resolveChoiceSource yields an empty
    // choice list the modal surfaces as "no options yet" rather than hiding the picker.
    const emptyRef: FieldConfigField = { key: 'membership_type', group: 'membership', type: 'reference', options: [] };
    expect(isChoiceBearingField(emptyRef)).toBe(true);
    expect(resolveChoiceSource(emptyRef, null, 'en')).toEqual({ kind: 'reference', choices: [] });
  });
});

describe('resolveChoiceSource — SOURCE adapts to the field kind (R1.2 / design §C1)', () => {
  it('reference field → its OWN options (03b 9b.2; the live catalog is retired)', () => {
    const src = resolveChoiceSource(referenceField, null, 'en');
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
