/**
 * Property-based test for the Members view-modal field set (members-overview-tweaks, task 2.3).
 *
 * Feature: members-overview-tweaks, Property 2: View modal shows the complete field set
 * Validates: Requirements 3.1, 3.2
 *
 * The View_Modal renders `formFields(cfg)` — the FULL resolved VISIBLE field set (R3.1, R3.2):
 * it filters only `visible === false` and the system NON_INPUT_KEYS (`member_id`, `created_at`,
 * `updated_at`); it applies NO editable/calculated partition, so EVERY calculated field AND every
 * non-calculated field is kept. This contrasts with the Edit_Modal, which renders
 * `editableFields(formFields(cfg))` (calculated fields excluded, R2.1/R2.2).
 *
 * The property: for any field config with a MIX of calculated and non-calculated fields,
 * the view set `formFields(cfg)`
 *   (a) equals the full resolved visible set (the independently-computed `visible !== false`
 *       minus NON_INPUT_KEYS set), and
 *   (b) is a SUPERSET of the edit set `editableFields(formFields(cfg))` and additionally
 *       contains EVERY calculated field that survived the visibility/system filter — i.e. the
 *       view applies no editable/calculated partition.
 *
 * Uses fast-check 4.4.0 with 100 runs (fc.assert numRuns: 100). No rendering — these are the
 * pure field-set helpers in `./fieldForm`.
 */
import fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import type { FieldConfig, FieldConfigField } from '../../types/members';
import { formFields, editableFields, isCalculatedField } from './fieldForm';

// The system-managed keys `formFields` always drops (mirrors NON_INPUT_KEYS in fieldForm.ts).
const NON_INPUT_KEYS = new Set<string>(['member_id', 'created_at', 'updated_at']);

// ---------------------------------------------------------------------------
// Generators
//
// We constrain to the input space `formFields` actually partitions on: a field's `key`
// (drawn from a small pool that includes the system NON_INPUT_KEYS so those exclusion paths
// fire), its `origin` (so `calculated` fields recur), an explicit `read_only` flag (the other
// way a field becomes calculated), `visible` (so the `visible === false` drop fires), and an
// `order`. Keys are deduped so the resolved set has stable identity.
// ---------------------------------------------------------------------------

/** Key pool: ordinary fields + the three system keys that must be dropped. */
const keyArb = fc.constantFrom(
  'first_name',
  'last_name',
  'age',
  'balance',
  'tenure',
  'member_id', // NON_INPUT_KEY
  'created_at', // NON_INPUT_KEY
  'updated_at', // NON_INPUT_KEY
);

/** Origin — `calculated` makes the field calculated/read-only; the mix is what we want. */
const originArb = fc.constantFrom<FieldConfigField['origin']>(
  'fixed',
  'variable',
  'calculated',
  undefined,
);

/** A candidate field with a mix of calculated/editable, visible/hidden, and system keys. */
const fieldArb: fc.Arbitrary<FieldConfigField> = fc.record({
  key: keyArb,
  origin: originArb,
  read_only: fc.option(fc.boolean(), { nil: undefined }),
  visible: fc.option(fc.boolean(), { nil: undefined }),
  order: fc.option(fc.integer({ min: -5, max: 5 }), { nil: undefined }),
}) as fc.Arbitrary<FieldConfigField>;

/** A unique-by-key field list — the resolved config has one descriptor per key. */
const fieldsArb: fc.Arbitrary<FieldConfigField[]> = fc
  .array(fieldArb, { minLength: 0, maxLength: 10 })
  .map((fields) => {
    const seen = new Set<string>();
    return fields.filter((f) => (seen.has(f.key) ? false : (seen.add(f.key), true)));
  });

const configArb: fc.Arbitrary<FieldConfig> = fieldsArb.map((fields) => ({ fields }));

// ---------------------------------------------------------------------------

describe('fieldForm — Property 2: View modal shows the complete field set', () => {
  it('view set equals the full resolved visible set and applies no editable/calculated partition', () => {
    fc.assert(
      fc.property(configArb, (cfg) => {
        const viewSet = formFields(cfg);
        const viewKeys = new Set(viewSet.map((f) => f.key));

        // (a) The view set equals the full resolved VISIBLE set, computed independently:
        // every field that is not `visible === false` and not a system NON_INPUT_KEY.
        const expectedKeys = new Set(
          (cfg.fields ?? [])
            .filter((f) => f.visible !== false)
            .filter((f) => !NON_INPUT_KEYS.has(f.key))
            .map((f) => f.key),
        );
        expect(viewKeys).toEqual(expectedKeys);

        // (b) No editable/calculated partition is applied: the view set is a SUPERSET of the
        // edit set, and it ADDITIONALLY contains every calculated field in the resolved set.
        const editSet = editableFields(viewSet);
        const editKeys = new Set(editSet.map((f) => f.key));

        // Superset: every edit-set key is present in the view set.
        for (const k of editKeys) {
          expect(viewKeys.has(k)).toBe(true);
        }

        // The view set contains EVERY calculated field (which the edit set drops).
        const calculatedInView = viewSet.filter(isCalculatedField).map((f) => f.key);
        for (const k of calculatedInView) {
          expect(viewKeys.has(k)).toBe(true);
          expect(editKeys.has(k)).toBe(false);
        }

        // The view set is exactly the editable fields PLUS the calculated fields — a complete
        // partition recombined, proving nothing is dropped in the middle.
        const recombined = new Set([...editKeys, ...calculatedInView]);
        expect(recombined).toEqual(viewKeys);
      }),
      { numRuns: 100 },
    );
  });
});
