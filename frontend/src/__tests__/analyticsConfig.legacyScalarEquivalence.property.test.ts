/**
 * Property-based test for legacy-scalar backward compatibility.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 8: Legacy scalar is
 * equivalent to object-eq (backward compatibility)
 *
 * For any filters map containing a legacy scalar entry `{ key: scalar }` (scalar
 * non-blank, for ANY key — including `years_member` / `joined_after_year`), the
 * pure engine `applyDefinitionFilters` narrows rows IDENTICALLY to the same map
 * rewritten as `{ key: { op: 'eq', value: String(scalar) } }`, and the picker
 * helper `toFilterDrafts` reads the scalar entry as an editable row with operator
 * `eq` and the stringified value — so a pre-feature set (including a jubilee /
 * new-member list) loads, runs, and re-saves with equivalent narrowing.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * **Validates: Requirements 8.1, 8.2, 8.8**
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { applyDefinitionFilters } from '../components/members/analytics/analyticsConfig';
import { toFilterDrafts } from '../components/members/analytics/memberFieldPicker.helpers';
import type { FieldConfig, MemberRow } from '../types/members';

// Candidate filter keys. Includes the two keys that were reserved/special-cased
// in the pre-feature code (`years_member`, `joined_after_year`) alongside an
// ordinary field, to prove NO key is special-cased by the legacy-scalar path.
const KEYS = ['clubblad', 'years_member', 'joined_after_year'] as const;
const keyArb: fc.Arbitrary<string> = fc.constantFrom(...KEYS);

/** A field config carrying every candidate key as a flat (untyped) field, so
 *  `valueFor` reads each as a flat `row[key]`. */
const FIELD_CONFIG: FieldConfig = {
  fields: KEYS.map((key) => ({ key })),
} as FieldConfig;

/**
 * A legacy scalar value: a non-blank string OR a number. The legacy form is
 * `{ key: scalar }`, which `normalizeClause` reads as `{ op: 'eq', value:
 * String(scalar) }`.
 */
const scalarArb: fc.Arbitrary<string | number> = fc.oneof(
  fc.string({ minLength: 1, maxLength: 12 }).filter((s) => s.trim() !== ''),
  fc.integer({ min: 0, max: 200 }),
);

/**
 * A candidate cell value: absent (key omitted), blank-ish, or an arbitrary
 * string with varied casing / whitespace so the trim + case-insensitive eq
 * contract is genuinely exercised. Numbers are also offered so a numeric legacy
 * scalar is compared against stringified cells.
 */
const ABSENT = Symbol('absent');
const cellArb: fc.Arbitrary<string | number | typeof ABSENT> = fc.oneof(
  fc.constant<string | number | typeof ABSENT>(ABSENT),
  fc.string({ maxLength: 10 }),
  fc.integer({ min: 0, max: 200 }),
  fc.string({ minLength: 1, maxLength: 6 }).map((s) => `  ${s.toUpperCase()}  `),
);

/** Build a one-field member row carrying `cell` under `key` (omit the key when
 *  `cell` is the absent sentinel). */
function makeRow(
  id: string,
  key: string,
  cell: string | number | typeof ABSENT,
): MemberRow {
  const row: Record<string, unknown> = { member_id: id };
  if (cell !== ABSENT) {
    row[key] = cell;
  }
  return row as unknown as MemberRow;
}

/** Extract the stable member_id set from an engine result. */
function idsOf(rows: MemberRow[]): string[] {
  return rows.map((r) => String((r as Record<string, unknown>).member_id));
}

describe('Feature: member-analytics-pivot-filter-operators, Property 8: Legacy scalar is equivalent to object-eq (backward compatibility)', () => {
  /**
   * ENGINE equivalence (R8.1, R8.8): the legacy scalar map narrows the SAME rows,
   * in the SAME order, as the object-eq rewrite `{ op: 'eq', value: String(scalar) }`
   * — for ANY key, including `years_member` / `joined_after_year`.
   */
  it('narrows identically to the object-eq rewrite for any key (R8.1, R8.8)', () => {
    fc.assert(
      fc.property(
        keyArb,
        scalarArb,
        fc.array(cellArb, { maxLength: 25 }),
        (key, scalar, cells) => {
          const rows = cells.map((cell, i) => makeRow(String(i), key, cell));

          const legacyKept = applyDefinitionFilters(
            rows,
            { [key]: scalar },
            FIELD_CONFIG,
          );
          const objectKept = applyDefinitionFilters(
            rows,
            { [key]: { op: 'eq', value: String(scalar) } },
            FIELD_CONFIG,
          );

          // Same surviving rows, same order (engine is order-preserving).
          expect(idsOf(legacyKept)).toEqual(idsOf(objectKept));
        },
      ),
      { numRuns: 200 },
    );
  });

  /**
   * HELPERS read (R8.2): `toFilterDrafts` reads a legacy scalar entry as an
   * editable row with operator `eq` and the stringified value — no key is
   * skipped or special-cased.
   */
  it('toFilterDrafts reads a legacy scalar entry as an editable eq row with the stringified value (R8.2)', () => {
    fc.assert(
      fc.property(keyArb, scalarArb, (key, scalar) => {
        const drafts = toFilterDrafts({ [key]: scalar });

        // Exactly one editable row for the single legacy entry (no key skipped).
        expect(drafts).toHaveLength(1);
        const [draft] = drafts;
        expect(draft.field).toBe(key);
        expect(draft.op).toBe('eq');
        expect(draft.value).toBe(String(scalar));
      }),
      { numRuns: 200 },
    );
  });

  /**
   * END-TO-END backward compatibility (R8.8): the drafts read from a legacy
   * scalar entry, when fed to the engine as the equivalent object-eq clause,
   * narrow identically to the original legacy map — the load → run round-trip is
   * behavior-preserving.
   */
  it('legacy scalar drafts drive the engine identically to the legacy map (R8.8)', () => {
    fc.assert(
      fc.property(
        keyArb,
        scalarArb,
        fc.array(cellArb, { maxLength: 25 }),
        (key, scalar, cells) => {
          const rows = cells.map((cell, i) => makeRow(String(i), key, cell));

          const [draft] = toFilterDrafts({ [key]: scalar });
          const fromDraftKept = applyDefinitionFilters(
            rows,
            { [draft.field]: { op: draft.op, value: draft.value } },
            FIELD_CONFIG,
          );
          const legacyKept = applyDefinitionFilters(
            rows,
            { [key]: scalar },
            FIELD_CONFIG,
          );

          expect(idsOf(fromDraftKept)).toEqual(idsOf(legacyKept));
        },
      ),
      { numRuns: 200 },
    );
  });
});
