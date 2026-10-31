/**
 * Unit tests for the PURE public-application model helpers (spec 13 task 1.2; R2.1, R2.2, R2.3).
 *
 * These pin `groupFieldsByFunctionalGroup` — the one pure transform the renderer sections by —
 * WITHOUT rendering. Spec 13 R2 made GROUP order a function of the authored field sequence:
 * groups appear in ascending `min(field.order)` order, with a stable tiebreak on the group KEY
 * when two groups share a minimum, the synthesized `__default__` bucket pinned LAST, and the
 * field order WITHIN a group left as `(order, key)`. The renderer render test
 * (`src/__tests__/ApplicationFormRenderer.test.tsx`) continues to cover the DOM-level grouping;
 * this file isolates the ordering contract on the pure helper.
 *
 * Authority is server-side (R6.6) — this is presentation ordering only.
 */

import { describe, it, expect } from 'vitest';
import type { PublicField } from './applicationFieldConfig';
import { groupFieldsByFunctionalGroup, isWideField } from './applicationForm.model';

/** Minimal field factory — only the keys the grouping helper reads. */
const field = (
  key: string,
  functional_group: string | undefined,
  order: number | undefined,
): PublicField => ({ key, type: 'string', functional_group, order });

describe('groupFieldsByFunctionalGroup — group + field ordering (spec 13 R2)', () => {
  it('orders groups by the minimum field.order per group (R2.2)', () => {
    // membership's earliest field has order 5; personal's earliest has order 10 → membership first,
    // even though a personal field appears first in the input list.
    const fields = [
      field('personal.last_name', 'personal', 20),
      field('personal.first_name', 'personal', 10),
      field('membership.type', 'membership', 5),
      field('membership.iban', 'membership', 30),
    ];

    const groups = groupFieldsByFunctionalGroup(fields);

    expect(groups.map((g) => g.key)).toEqual(['membership', 'personal']);
  });

  it('does NOT order groups by first appearance in the field list (R2.2 — the old behavior)', () => {
    // `address` appears first in the list but its earliest order (40) is higher than `contact` (10),
    // so by min-field-order `contact` must come first — the opposite of first-appearance order.
    const fields = [
      field('address.street', 'address', 40),
      field('address.city', 'address', 50),
      field('contact.email', 'contact', 10),
      field('contact.phone', 'contact', 20),
    ];

    const groups = groupFieldsByFunctionalGroup(fields);

    expect(groups.map((g) => g.key)).toEqual(['contact', 'address']);
  });

  it('breaks a min-order tie by group key, stably (R2.2)', () => {
    // Both groups have a minimum field.order of 10 → tiebreak on the group KEY: `alpha` < `beta`.
    const fields = [
      field('beta.one', 'beta', 10),
      field('beta.two', 'beta', 99),
      field('alpha.one', 'alpha', 10),
      field('alpha.two', 'alpha', 50),
    ];

    const groups = groupFieldsByFunctionalGroup(fields);

    expect(groups.map((g) => g.key)).toEqual(['alpha', 'beta']);
  });

  it('is permutation-invariant on the input order for equal-min groups (stable tiebreak)', () => {
    const base = [
      field('beta.one', 'beta', 10),
      field('alpha.one', 'alpha', 10),
    ];
    const forward = groupFieldsByFunctionalGroup(base).map((g) => g.key);
    const reversed = groupFieldsByFunctionalGroup([...base].reverse()).map((g) => g.key);

    // Same result regardless of input order → the key tiebreak does not leak input order.
    expect(forward).toEqual(['alpha', 'beta']);
    expect(reversed).toEqual(['alpha', 'beta']);
  });

  it('pins the synthesized __default__ bucket LAST regardless of its field orders (R2.2)', () => {
    // The ungrouped field has order 1 — lower than every grouped field — yet __default__ trails.
    const fields = [
      field('loose.note', undefined, 1),
      field('personal.first_name', 'personal', 10),
      field('membership.type', 'membership', 20),
    ];

    const groups = groupFieldsByFunctionalGroup(fields);

    expect(groups.map((g) => g.key)).toEqual(['personal', 'membership', '__default__']);
    // The default bucket surfaces the ungrouped field (never dropped).
    expect(groups.at(-1)!.fields.map((f) => f.key)).toEqual(['loose.note']);
  });

  it('keeps field order WITHIN a group as (order, key), independent of group ordering (R2.1)', () => {
    const fields = [
      field('personal.last_name', 'personal', 20),
      field('personal.first_name', 'personal', 10),
      // Two fields share order 10 → tiebreak on key: `a_extra` before `middle_name`.
      field('personal.middle_name', 'personal', 10),
      field('personal.a_extra', 'personal', 10),
    ];

    const [personal] = groupFieldsByFunctionalGroup(fields);

    expect(personal.key).toBe('personal');
    expect(personal.fields.map((f) => f.key)).toEqual([
      'personal.a_extra', // order 10, key sorts first
      'personal.first_name', // order 10
      'personal.middle_name', // order 10
      'personal.last_name', // order 20
    ]);
  });

  it('treats a missing field.order as 0 for both group-min and intra-group ordering', () => {
    // `zeroish` has an order-less field (→ 0) so its min is 0, below `later` (min 5) → it sorts first.
    const fields = [
      field('later.a', 'later', 5),
      field('zeroish.no_order', 'zeroish', undefined),
      field('zeroish.has_order', 'zeroish', 3),
    ];

    const groups = groupFieldsByFunctionalGroup(fields);

    expect(groups.map((g) => g.key)).toEqual(['zeroish', 'later']);
    // Within `zeroish`, the order-less field (treated as 0) precedes the order-3 field.
    expect(groups[0].fields.map((f) => f.key)).toEqual(['zeroish.no_order', 'zeroish.has_order']);
  });

  it('is a pure transform: does not mutate the input array or its field objects (R2.3)', () => {
    const fields = [
      field('b.two', 'b', 20),
      field('a.one', 'a', 10),
    ];
    const snapshot = fields.map((f) => ({ ...f }));

    groupFieldsByFunctionalGroup(fields);

    // Input order and each field object are untouched.
    expect(fields.map((f) => f.key)).toEqual(['b.two', 'a.one']);
    fields.forEach((f, i) => expect(f).toEqual(snapshot[i]));
  });

  it('returns an empty list for no fields (degenerate input)', () => {
    expect(groupFieldsByFunctionalGroup([])).toEqual([]);
  });
});

describe('isWideField — intrinsically-wide field identification (spec 13 task 4.2, R4.3)', () => {
  it('flags intrinsically-wide free-text field types as wide (full-row span)', () => {
    for (const type of ['textarea', 'text_area', 'long_text', 'multiline']) {
      expect(isWideField({ key: 'notes', type })).toBe(true);
    }
  });

  it('does NOT flag ordinary single-column field types as wide', () => {
    for (const type of ['string', 'text', 'number', 'date', 'enum', 'reference']) {
      expect(isWideField({ key: 'f', type })).toBe(false);
    }
  });

  it('is generic over the config — an unknown type is not wide (HC1, no per-field hard-coding)', () => {
    expect(isWideField({ key: 'f', type: 'something_new' })).toBe(false);
  });
});


describe('groupFieldsByFunctionalGroup — AUTHORED catalog ordering (spec 13 R2, the round-1 fix)', () => {
  // The exact finding: fields are in the right order, but the GROUPS were not in the authored
  // functional-group order. The authored catalog (h-dcn: Personal #10 ... Administrative #60) is
  // the single source of group order; min(field.order) is NOT.
  const catalog = [
    { key: 'personal', label: { nl: 'Persoonlijk', en: 'Personal' }, order: 10 },
    { key: 'address', label: { nl: 'Adres', en: 'Address' }, order: 20 },
    { key: 'membership', label: { nl: 'Lidmaatschap', en: 'Membership' }, order: 30 },
    { key: 'motor', label: { nl: 'Motor', en: 'Motorcycle' }, order: 40 },
    { key: 'financial', label: { nl: 'Financieel', en: 'Financial' }, order: 50 },
    { key: 'administrative', label: { nl: 'Administratief', en: 'Administrative' }, order: 60 },
  ];

  it('orders groups by the authored catalog order, NOT by min(field.order)', () => {
    // Field orders are deliberately chosen so a min(field.order) heuristic would REORDER the
    // groups: administrative has the lowest field order (1) and would wrongly sort FIRST, while
    // personal (authored #10) has a high field order (99). The catalog must win.
    const fields = [
      field('administrative.note', 'administrative', 1),
      field('financial.iban', 'financial', 2),
      field('motor.plate', 'motor', 3),
      field('membership.type', 'membership', 4),
      field('address.city', 'address', 5),
      field('personal.first_name', 'personal', 99),
    ];

    const groups = groupFieldsByFunctionalGroup(fields, catalog);

    expect(groups.map((g) => g.key)).toEqual([
      'personal',
      'address',
      'membership',
      'motor',
      'financial',
      'administrative',
    ]);
  });

  it('carries the authored label onto each group for the heading', () => {
    const fields = [field('personal.first_name', 'personal', 10)];
    const [g] = groupFieldsByFunctionalGroup(fields, catalog);
    expect(g.label).toEqual({ nl: 'Persoonlijk', en: 'Personal' });
  });

  it('keeps field order WITHIN a group as (order, key) independent of catalog order', () => {
    const fields = [
      field('personal.last_name', 'personal', 20),
      field('personal.first_name', 'personal', 10),
    ];
    const [g] = groupFieldsByFunctionalGroup(fields, catalog);
    expect(g.fields.map((f) => f.key)).toEqual(['personal.first_name', 'personal.last_name']);
  });

  it('sorts a group ABSENT from the catalog after catalog groups, and __default__ LAST', () => {
    const fields = [
      field('personal.first_name', 'personal', 10), // catalog #10
      field('mystery.x', 'mystery', 1), // not in catalog → after catalog groups
      field('loose.note', undefined, 1), // no group → __default__, pinned last
    ];
    const groups = groupFieldsByFunctionalGroup(fields, catalog);
    expect(groups.map((g) => g.key)).toEqual(['personal', 'mystery', '__default__']);
  });

  it('falls back to min(field.order) when NO catalog is supplied (back-compat)', () => {
    const fields = [
      field('address.city', 'address', 40),
      field('contact.email', 'contact', 10),
    ];
    // No catalog → the old heuristic: contact (min 10) before address (min 40).
    const groups = groupFieldsByFunctionalGroup(fields);
    expect(groups.map((g) => g.key)).toEqual(['contact', 'address']);
  });
});
