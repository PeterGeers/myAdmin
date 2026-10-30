/**
 * 03b (admin-driven field/form model) task 5.2 — BU-9 FILTER-PARITY pin (R5.1/R5.2/R5.3).
 *
 * This is the filter-parity test the design pairs with the `useMembersColumns` test: it pins the
 * ONE invariant BU-9 delivers — for an enum field, the DISPLAY and the FILTER resolve a stored key
 * to the SAME per-language label, and BOTH the label (in every language) AND the raw stored key
 * filter the SAME row. "Parity" here is two-sided:
 *
 *   1. display ⇄ filter parity — the text the table/modal SHOWS (`renderFieldValue` →
 *      `resolveEnumValueLabel`) and the text the filter MATCHES ON (`buildEnumLabelMap` +
 *      `enumValueToFilterText`) resolve the stored key through the identical resolution chain, so a
 *      user can always filter by exactly what they see;
 *   2. label ⇄ key parity — the NL label, the GB label, AND the raw stored key all select the same
 *      row (label matching is ADDED on top of key matching; the key is never dropped, R5.4).
 *
 * **Property 6 (design): every enum DISPLAY and FILTER resolves `label[locale] → en → nl → value`.**
 * The chain is asserted step-by-step below (active locale wins; then `en`; then `nl`; then the raw
 * value when no label exists) against BOTH the display helper and the filter helper, so the two can
 * never silently diverge on the fallback order.
 *
 * This does NOT duplicate `useMembersColumns.test.ts` (which pins the hook's row-filtering for a
 * single two-value status field); it pins the resolution ORDER and the display⇄filter parity that
 * Property 6 guards, plus the shared-label case (two keys → one label → both keys match).
 *
 * The stored `options.value` key is language-neutral and stored verbatim (R5.4); these helpers are
 * read-only presentation metadata and never rewrite it.
 *
 * **Validates: Requirements 5.1, 5.2, 5.3**
 */

import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { Member, FieldConfig, FieldConfigField } from '../../../types/members';
import {
  buildEnumLabelMap,
  enumValueToFilterText,
  renderFieldValue,
} from '../fieldValue';
import { useMembersColumns } from './useMembersColumns';

// ── A status enum whose options exercise EVERY rung of the resolution chain ──────────────
//   died   → full label{nl,en,gb}        → active locale wins
//   left   → label{en,nl} (no gb)        → falls back to en when locale is gb
//   paused → label{nl} only              → falls back to nl when neither locale nor en present
//   ghost  → NO label                    → falls back to the raw stored value (the key itself)
// `gb` is a distinct active locale from `en` so the "active locale wins over en" rung is real.
const statusField = (): FieldConfigField => ({
  key: 'status',
  type: 'enum',
  options: [
    { value: 'died', label: { nl: 'Overleden', en: 'Passed Away', gb: 'Deceased (GB)' } },
    { value: 'left', label: { nl: 'Vertrokken', en: 'Left' } },
    { value: 'paused', label: { nl: 'Gepauzeerd' } },
    { value: 'ghost', label: undefined },
  ],
} as FieldConfigField);

describe('BU-9 Property 6 — enum resolution chain label[locale] → en → nl → value', () => {
  const field = statusField();

  // The chain is: label[locale] → label.en → label.nl → raw value. Each case picks the FIRST
  // present rung for the given active locale. DISPLAY (renderFieldValue) and FILTER
  // (buildEnumLabelMap) MUST agree on the resolved label for the same (value, locale).
  const cases: Array<{ value: string; locale: string; expected: string; rung: string }> = [
    { value: 'died', locale: 'gb', expected: 'Deceased (GB)', rung: 'label[locale] wins' },
    { value: 'died', locale: 'nl', expected: 'Overleden', rung: 'label[locale] (nl) wins' },
    { value: 'left', locale: 'gb', expected: 'Left', rung: 'no gb → falls back to en' },
    { value: 'paused', locale: 'gb', expected: 'Gepauzeerd', rung: 'no gb/en → falls back to nl' },
    { value: 'paused', locale: 'en', expected: 'Gepauzeerd', rung: 'no en → falls back to nl' },
    { value: 'ghost', locale: 'nl', expected: 'ghost', rung: 'no label → falls back to raw value' },
  ];

  it.each(cases)(
    'DISPLAY resolves $value ($locale) → "$expected" ($rung)',
    ({ value, locale, expected }) => {
      expect(renderFieldValue(field, value, locale)).toBe(expected);
    },
  );

  it.each(cases)(
    'FILTER resolves $value ($locale) → matchable "$expected" ($rung)',
    ({ value, locale, expected }) => {
      const map = buildEnumLabelMap(field, locale);
      const text = enumValueToFilterText(map, value).toLowerCase();
      // The resolved label (what DISPLAY shows) is always a filter match for the stored key...
      expect(text).toContain(expected.toLowerCase());
      // ...and the raw stored key is ALSO always a match (label added on top of key, R5.4).
      expect(text).toContain(value.toLowerCase());
    },
  );

  it('DISPLAY and FILTER resolve to the SAME label for every case (display⇄filter parity)', () => {
    for (const { value, locale } of cases) {
      const shown = renderFieldValue(field, value, locale);
      const map = buildEnumLabelMap(field, locale);
      const matchText = enumValueToFilterText(map, value);
      // Whatever the table shows must be findable in the filter text for that same cell.
      expect(matchText.toLowerCase()).toContain(shown.toLowerCase());
    }
  });
});

describe('BU-9 Property 6 — two options sharing one label: both keys stay matchable (R5.3)', () => {
  // Two distinct stored keys resolving to the SAME displayed label. A filter on that shared label
  // must match BOTH keys; a filter on either specific key still matches only that key.
  const field: FieldConfigField = {
    key: 'status',
    type: 'enum',
    options: [
      { value: 'died', label: { nl: 'Inactief', en: 'Inactive' } },
      { value: 'left', label: { nl: 'Inactief', en: 'Inactive' } },
    ],
  } as FieldConfigField;

  it('the shared label resolves for both keys, and each key is still individually matchable', () => {
    const map = buildEnumLabelMap(field, 'nl');
    const diedText = enumValueToFilterText(map, 'died').toLowerCase();
    const leftText = enumValueToFilterText(map, 'left').toLowerCase();

    // Shared label matches BOTH keys' cells.
    expect(diedText).toContain('inactief');
    expect(leftText).toContain('inactief');
    // Each specific key only lives in its own cell's match text.
    expect(diedText).toContain('died');
    expect(diedText).not.toContain('left');
    expect(leftText).toContain('left');
    expect(leftText).not.toContain('died');
  });
});

// ── Integrated filter-parity through the REAL overview hook ───────────────────────────────
// The helper-level chain above is pinned end-to-end here: the NL label, the GB label, AND the raw
// stored key, fed to the actual `useMembersColumns` global-search path, each select the SAME row.

const fieldConfig = (): FieldConfig => ({
  fields: [
    { key: 'name', type: 'string' },
    {
      key: 'status',
      type: 'enum',
      options: [
        { value: 'active', label: { nl: 'Actief', en: 'Active', gb: 'Active (GB)' } },
        { value: 'died', label: { nl: 'Overleden', en: 'Passed Away', gb: 'Deceased (GB)' } },
      ],
    },
  ],
} as FieldConfig);

const members = (): Member[] => [
  { member_id: '1', member_number: 'M1', name: 'Alice', status: 'died' } as Member,
  { member_id: '2', member_number: 'M2', name: 'Bob', status: 'active' } as Member,
];

function run(globalSearch: string, lang: string) {
  return renderHook(() =>
    useMembersColumns({
      members: members(),
      fieldConfig: fieldConfig(),
      chosenKeys: ['name', 'status'],
      globalSearch,
      lang,
      t: (key: string) => key,
    }),
  );
}

describe('BU-9 filter parity — NL label, GB label, and the raw key all select the same row', () => {
  // The stored-`died` row (Alice, member_id 1). label[locale] resolution: nl→Overleden,
  // en→Passed Away, gb→Deceased (GB). All three, plus the raw key, pick ONLY Alice.
  const diedQueries: Array<{ query: string; lang: string; why: string }> = [
    { query: 'Overleden', lang: 'nl', why: 'NL label' },
    { query: 'Passed Away', lang: 'en', why: 'EN label' },
    { query: 'Deceased (GB)', lang: 'gb', why: 'GB label (label[locale] over en)' },
    { query: 'died', lang: 'nl', why: 'raw stored key (nl user)' },
    { query: 'died', lang: 'gb', why: 'raw stored key (gb user)' },
  ];

  it.each(diedQueries)('"$query" ($lang, $why) → the single stored-died row', ({ query, lang }) => {
    const { result } = run(query, lang);
    const rows = result.current.enrichedRows;
    expect(rows).toHaveLength(1);
    expect(rows[0].member_id).toBe('1');
  });

  it('a gb-locale user filtering the GB label does NOT also match the active row', () => {
    // Parity sanity: the gb label for `active` is "Active (GB)", distinct from "Deceased (GB)",
    // so the died-row filter stays precise under the active-locale rung.
    const { result } = run('Deceased', 'gb');
    expect(result.current.enrichedRows.map(r => r.member_id)).toEqual(['1']);
  });
});
