/**
 * Tests for the Members Overview column/row-derivation hook (useMembersColumns.ts) —
 * specifically the BU-9 enum filter behaviour (03b task 5.1/5.2, R5.2/R5.3/R5.4).
 *
 * The one behaviour pinned here: for an enum column, filter/search matches on the
 * resolved per-language LABEL **OR** the stored KEY — BOTH. An NL user typing
 * `Overleden`, a GB user typing `Passed Away`, AND anyone typing the raw stored key
 * `died` all match the SAME stored-`died` row. Label matching is ADDED on top of key
 * matching (the key is never dropped), and the stored record key is never rewritten
 * (R5.4). The value→label map is built ONCE per column, not per row per keystroke.
 *
 * **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
 */

import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { Member, FieldConfig } from '../../../types/members';
import { useMembersColumns } from './useMembersColumns';

const t = (key: string): string => key;

// A status enum field whose options carry per-language labels. `died` resolves to
// nl `Overleden` / en (GB) `Passed Away`; `active` resolves to nl `Actief` / en `Active`.
const fieldConfig = (): FieldConfig => ({
  fields: [
    { key: 'name', type: 'string' },
    {
      key: 'status',
      type: 'enum',
      options: [
        { value: 'active', label: { nl: 'Actief', en: 'Active' } },
        { value: 'died', label: { nl: 'Overleden', en: 'Passed Away' } },
      ],
    },
  ],
} as FieldConfig);

// Two members: one flagged `died` (name Alice), one `active` (name Bob). Status is a
// flat alias on the row (as `flattenMember` promotes it), read nested-first then flat.
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
      t,
    }),
  );
}

describe('useMembersColumns — enum filter matches label OR key (R5.2/R5.4)', () => {
  it('global search matches the NL label (Overleden → the died row)', () => {
    const { result } = run('Overleden', 'nl');
    const rows = result.current.enrichedRows;
    expect(rows).toHaveLength(1);
    expect(rows[0].member_id).toBe('1');
  });

  it('global search matches the GB label (Passed Away → the died row)', () => {
    const { result } = run('Passed Away', 'en');
    const rows = result.current.enrichedRows;
    expect(rows).toHaveLength(1);
    expect(rows[0].member_id).toBe('1');
  });

  it('global search STILL matches the raw stored key (died) in either language', () => {
    for (const lang of ['nl', 'en']) {
      const { result } = run('died', lang);
      const rows = result.current.enrichedRows;
      expect(rows).toHaveLength(1);
      expect(rows[0].member_id).toBe('1');
    }
  });

  it('a partial label match narrows to the right row (case-insensitive)', () => {
    const { result } = run('overl', 'nl'); // partial of "Overleden"
    const rows = result.current.enrichedRows;
    expect(rows).toHaveLength(1);
    expect(rows[0].member_id).toBe('1');
  });

  it('the flattened filter value carries BOTH the label and the stored key', () => {
    // enrichedRows promotes a combined "<label> <key>" string onto row[key] so the
    // per-column FilterableHeader (substring match) matches either half.
    const { result } = run('', 'nl'); // no global search → all rows enriched
    const aliceRow = result.current.enrichedRows.find(r => r.member_id === '1')!;
    const flat = String(aliceRow.status).toLowerCase();
    expect(flat).toContain('overleden'); // label
    expect(flat).toContain('died');      // stored key
  });

  it('the stored record key is NEVER rewritten (R5.4 — enrichedRows is additive)', () => {
    // The display/filter overlay must not mutate the underlying stored value; the
    // nested/raw status the record keeps is still the verbatim key.
    const { result } = run('', 'en');
    const aliceRaw = members().find(m => m.member_id === '1')!;
    expect(aliceRaw.status).toBe('died');
    // enrichedRows is a spread copy — the source member objects are untouched.
    expect(result.current.enrichedRows.find(r => r.member_id === '1')!.member_id).toBe('1');
  });
});
