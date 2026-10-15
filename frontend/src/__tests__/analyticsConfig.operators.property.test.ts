/**
 * Property-based test for the type→operator mapping helpers.
 *
 * Feature: member-analytics-pivot-filter-operators, Property 11: Operator
 * availability by field type.
 *
 * Targets the pure helpers `operatorsForField` / `operatorTakesNoValue` in
 * `../components/members/analytics/analyticsConfig`. The reset-to-eq-on-
 * incompatible-field-change leg of the acceptance criteria (R3.6) is a picker
 * concern wired in a later task; here we lock the pure mapping these helpers
 * define, which is what every operator-select renders from.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations per property.
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4
 * Spec: `.kiro/specs/Members/member-analytics-pivot-filter-operators`.
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import {
  operatorsForField,
  operatorTakesNoValue,
} from '../components/members/analytics/analyticsConfig';
import type { FieldConfigField } from '../types/members';
import type { FilterOperator } from '../types/pivot';

// The expected operator sets straight from the design's type→operator table.
const NUMERIC_DATE_SET: readonly FilterOperator[] = [
  'eq',
  'ne',
  'gt',
  'gte',
  'lt',
  'lte',
  'empty',
  'notEmpty',
];

const TEXT_SET: readonly FilterOperator[] = [
  'eq',
  'ne',
  'contains',
  'notContains',
  'regex',
  'notRegex',
  'empty',
  'notEmpty',
];

// Always-present universal operators (every type offers these).
const UNIVERSAL: readonly FilterOperator[] = ['eq', 'ne', 'empty', 'notEmpty'];

// The field types that select the numeric/date ordering set.
const NUMERIC_DATE_TYPES = ['number', 'date'] as const;

// The field types that select the text set per the table (plus absent/other,
// generated separately below).
const TEXT_TYPES = ['string', 'enum', 'reference', 'email'] as const;

/** Build a resolved field descriptor with the given (optional) type. */
function fieldWithType(type: string | undefined): FieldConfigField {
  return { key: 'f', type } as FieldConfigField;
}

/** Order-insensitive multiset equality for operator lists. */
function sameOperators(
  actual: readonly FilterOperator[],
  expected: readonly FilterOperator[],
): boolean {
  return (
    actual.length === expected.length &&
    [...actual].sort().join(',') === [...expected].sort().join(',')
  );
}

describe('Feature: member-analytics-pivot-filter-operators, Property 11: Operator availability by field type', () => {
  it('offers the numeric/date set for number- and date-typed fields (R3.1, R3.2)', () => {
    fc.assert(
      fc.property(fc.constantFrom(...NUMERIC_DATE_TYPES), (type) => {
        const ops = operatorsForField(fieldWithType(type));
        return sameOperators(ops, NUMERIC_DATE_SET);
      }),
      { numRuns: 100 },
    );
  });

  it('offers the text set for string/enum/reference/email and any absent/other type (R3.3)', () => {
    // A generator that produces the named text types, an absent type, and
    // arbitrary "other" strings that must all fall through to the text set.
    const otherType = fc.oneof(
      fc.constantFrom<string>(...TEXT_TYPES),
      fc.constant(undefined),
      fc
        .string()
        .filter(
          (s) =>
            s !== 'number' &&
            s !== 'date',
        ),
    );
    fc.assert(
      fc.property(otherType, (type) => {
        const ops = operatorsForField(fieldWithType(type as string | undefined));
        return sameOperators(ops, TEXT_SET);
      }),
      { numRuns: 100 },
    );
  });

  it('always includes the universal operators eq, ne, empty, notEmpty for every type (R3.4)', () => {
    const anyType = fc.oneof(
      fc.constantFrom<string>(...NUMERIC_DATE_TYPES, ...TEXT_TYPES),
      fc.constant(undefined),
      fc.string(),
    );
    fc.assert(
      fc.property(anyType, (type) => {
        const ops = operatorsForField(fieldWithType(type as string | undefined));
        return UNIVERSAL.every((u) => ops.includes(u));
      }),
      { numRuns: 100 },
    );
  });

  it('exposes exactly empty/notEmpty as the no-value operators across every offered operator', () => {
    const anyType = fc.oneof(
      fc.constantFrom<string>(...NUMERIC_DATE_TYPES, ...TEXT_TYPES),
      fc.constant(undefined),
      fc.string(),
    );
    fc.assert(
      fc.property(anyType, (type) => {
        const ops = operatorsForField(fieldWithType(type as string | undefined));
        return ops.every(
          (op) => operatorTakesNoValue(op) === (op === 'empty' || op === 'notEmpty'),
        );
      }),
      { numRuns: 100 },
    );
  });

  it('returns a fresh array and never mutates (purity)', () => {
    const field = fieldWithType('number');
    const a = operatorsForField(field);
    const b = operatorsForField(field);
    expect(a).not.toBe(b);
    a.push('eq');
    // The second call is unaffected by mutating the first result.
    expect(operatorsForField(field)).toHaveLength(NUMERIC_DATE_SET.length);
  });
});
