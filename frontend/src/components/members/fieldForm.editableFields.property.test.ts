/**
 * Property-based test for the edit-modal field partition.
 *
 * Feature: members-overview-tweaks, Property 1: Edit modal shows exactly the editable fields
 *
 * Targets the pure partition `editableFields(fields)` / `isCalculatedField(f)`
 * in `./fieldForm`. For any resolved field config, the set of fields the
 * Edit_Modal renders equals EXACTLY the set of editable (non-calculated) fields:
 * every editable field is included, every calculated field (`read_only === true`
 * OR `origin === 'calculated'`) is excluded, and the kept fields preserve their
 * input order and identity.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 2.1, 2.2
 * Spec: `.kiro/specs/members-overview-tweaks` (design Property 1).
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { editableFields, isCalculatedField, isEditableField } from './fieldForm';
import type { FieldConfigField, FieldOrigin } from '../../types/members';

/**
 * A generator for a single field config carrying a MIX of calculated and
 * editable shapes. A field is calculated when `read_only === true` OR
 * `origin === 'calculated'`; it is editable otherwise. The generator
 * independently varies both flags (origin ∈ fixed/variable/calculated/absent,
 * read_only ∈ true/false/absent) so every combination of the calculated/editable
 * predicate is sampled, keyed by a unique index so identity is checkable.
 */
const fieldGen = (index: number): fc.Arbitrary<FieldConfigField> =>
  fc.record({
    origin: fc.constantFrom<FieldOrigin | undefined>(
      'fixed',
      'variable',
      'calculated',
      undefined,
    ),
    read_only: fc.constantFrom<boolean | undefined>(true, false, undefined),
  }).map(({ origin, read_only }) => {
    const f: FieldConfigField = { key: `f_${index}` };
    if (origin !== undefined) f.origin = origin;
    if (read_only !== undefined) f.read_only = read_only;
    return f;
  });

/**
 * A field list with a MIX of calculated and editable fields. Each field gets a
 * distinct key by position so order/identity preservation is assertable, and the
 * list length varies (including empty) up to a modest cap.
 */
const fieldsGen: fc.Arbitrary<FieldConfigField[]> = fc
  .array(fc.constant(null), { minLength: 0, maxLength: 12 })
  .chain((slots) =>
    slots.length === 0
      ? fc.constant<FieldConfigField[]>([])
      : fc.tuple(...slots.map((_, i) => fieldGen(i))),
  );

describe('Feature: members-overview-tweaks, Property 1: Edit modal shows exactly the editable fields', () => {
  it('equals exactly the editable (non-calculated) fields — all editable in, all calculated out (R2.1, R2.2)', () => {
    fc.assert(
      fc.property(fieldsGen, (fields) => {
        const kept = editableFields(fields);
        const expected = fields.filter((f) => !isCalculatedField(f));
        // Same set, same order, same identity (reference-equal elements).
        expect(kept).toEqual(expected);
      }),
      { numRuns: 100 },
    );
  });

  it('includes every editable field (R2.1)', () => {
    fc.assert(
      fc.property(fieldsGen, (fields) => {
        const kept = editableFields(fields);
        for (const f of fields) {
          if (isEditableField(f)) {
            expect(kept).toContain(f); // reference identity preserved
          }
        }
      }),
      { numRuns: 100 },
    );
  });

  it('excludes every calculated field (R2.2)', () => {
    fc.assert(
      fc.property(fieldsGen, (fields) => {
        const kept = editableFields(fields);
        expect(kept.some((f) => isCalculatedField(f))).toBe(false);
        for (const f of fields) {
          if (isCalculatedField(f)) {
            expect(kept).not.toContain(f);
          }
        }
      }),
      { numRuns: 100 },
    );
  });

  it('preserves the relative order and identity of the kept fields (R2.1)', () => {
    fc.assert(
      fc.property(fieldsGen, (fields) => {
        const kept = editableFields(fields);
        // The kept fields appear in the same relative order as in the input,
        // and are the SAME object references (identity preserved).
        const keptFromInput = fields.filter((f) => isEditableField(f));
        expect(kept).toEqual(keptFromInput);
        kept.forEach((f, i) => expect(f).toBe(keptFromInput[i]));
      }),
      { numRuns: 100 },
    );
  });
});
