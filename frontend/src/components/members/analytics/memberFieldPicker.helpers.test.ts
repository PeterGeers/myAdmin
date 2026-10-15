/**
 * Co-located unit tests for the PURE filter-draft transforms in
 * {@link memberFieldPicker.helpers} — `toFilterDrafts` / `fromFilterDrafts`.
 *
 * Covers the task-4.2 behavior (R8.2, R8.5, R8.9) AFTER the reserved-key
 * carve-out was retired in task 4.1:
 *   - a legacy scalar entry reads as an editable `{ op: 'eq', value }` row;
 *   - the new object clause form reads back as-is (op + value);
 *   - a legacy scalar `years_member: 25` is now an ORDINARY editable `eq` row
 *     (NOT skipped, NOT carried through untouched) and composes GENERICALLY —
 *     the former RESERVED_FILTER_KEYS carve-out is gone;
 *   - a blank value-taking row (and an empty-field row) is dropped on compose;
 *   - a valueless `empty` / `notEmpty` row is kept (no `value` emitted).
 *
 * These are framework-free data transforms, so there is no React/Chakra render
 * here — just the helpers under test.
 */
import { describe, it, expect } from 'vitest';

import {
  toFilterDrafts,
  fromFilterDrafts,
  type FilterDraft,
} from './memberFieldPicker.helpers';

/** Build a FilterDraft, defaulting the stable id (irrelevant to compose). */
function draft(partial: Omit<FilterDraft, 'id'> & { id?: string }): FilterDraft {
  return { id: partial.id ?? 'test-row', ...partial };
}

describe('memberFieldPicker.helpers.toFilterDrafts', () => {
  it('reads a legacy scalar entry as an editable op=eq row', () => {
    const drafts = toFilterDrafts({ clubblad: 'Papier' });
    expect(drafts).toHaveLength(1);
    expect(drafts[0]).toMatchObject({ field: 'clubblad', op: 'eq', value: 'Papier' });
  });

  it('reads a legacy numeric scalar as an op=eq row with the stringified value', () => {
    const drafts = toFilterDrafts({ count: 25 });
    expect(drafts).toHaveLength(1);
    expect(drafts[0]).toMatchObject({ field: 'count', op: 'eq', value: '25' });
  });

  it('reads the new object clause form as-is (operator + value preserved)', () => {
    const drafts = toFilterDrafts({ years_member: { op: 'gte', value: '25' } });
    expect(drafts).toHaveLength(1);
    expect(drafts[0]).toMatchObject({ field: 'years_member', op: 'gte', value: '25' });
  });

  it('reads a valueless empty/notEmpty object clause with an empty value string', () => {
    const drafts = toFilterDrafts({
      clubblad: { op: 'empty' },
      email: { op: 'notEmpty' },
    });
    expect(drafts).toEqual([
      expect.objectContaining({ field: 'clubblad', op: 'empty', value: '' }),
      expect.objectContaining({ field: 'email', op: 'notEmpty', value: '' }),
    ]);
  });

  it('skips null / undefined entries (no narrowing)', () => {
    const drafts = toFilterDrafts({
      clubblad: 'Papier',
      a: null,
      b: undefined,
    });
    expect(drafts.map((d) => d.field)).toEqual(['clubblad']);
  });

  it('clamps an unknown stored operator to eq', () => {
    const drafts = toFilterDrafts({ clubblad: { op: 'bogus', value: 'x' } } as unknown as Record<
      string,
      unknown
    >);
    expect(drafts[0]).toMatchObject({ field: 'clubblad', op: 'eq', value: 'x' });
  });

  it('returns [] for an undefined filters map', () => {
    expect(toFilterDrafts(undefined)).toEqual([]);
  });

  // --- FLIPPED behavior: year keys are now ORDINARY editable rows -----------
  // Previously `years_member` (a RESERVED_FILTER_KEYS entry) was skipped so it
  // never appeared as an editable row. The carve-out is retired: a legacy
  // scalar `years_member: 25` MUST now read as an ordinary editable eq row.
  it('reads a legacy scalar years_member as an ordinary editable eq row (no carve-out)', () => {
    const drafts = toFilterDrafts({ clubblad: 'Papier', years_member: 25 });

    // years_member is NOT skipped — it IS an editable row alongside clubblad.
    expect(drafts.map((d) => d.field).sort()).toEqual(['clubblad', 'years_member']);

    const yearRow = drafts.find((d) => d.field === 'years_member');
    expect(yearRow).toMatchObject({ field: 'years_member', op: 'eq', value: '25' });
  });

  it('reads a legacy scalar joined_after_year as an ordinary editable eq row (no carve-out)', () => {
    const drafts = toFilterDrafts({ joined_after_year: 2020 });
    expect(drafts).toHaveLength(1);
    expect(drafts[0]).toMatchObject({ field: 'joined_after_year', op: 'eq', value: '2020' });
  });
});

describe('memberFieldPicker.helpers.fromFilterDrafts', () => {
  it('composes a value-taking row into the object clause form', () => {
    const result = fromFilterDrafts([draft({ field: 'clubblad', op: 'eq', value: 'Papier' })]);
    expect(result).toEqual({ clubblad: { op: 'eq', value: 'Papier' } });
  });

  it('drops a row with an empty field key', () => {
    const result = fromFilterDrafts([draft({ field: '', op: 'eq', value: 'x' })]);
    expect(result).toEqual({});
  });

  it('drops a value-taking row with a blank value', () => {
    const result = fromFilterDrafts([
      draft({ field: 'clubblad', op: 'eq', value: '   ' }),
      draft({ field: 'name', op: 'contains', value: '' }),
    ]);
    expect(result).toEqual({});
  });

  it('keeps a valueless empty / notEmpty row with no value emitted', () => {
    const result = fromFilterDrafts([
      draft({ field: 'clubblad', op: 'empty', value: '' }),
      draft({ field: 'email', op: 'notEmpty', value: 'ignored' }),
    ]);
    expect(result).toEqual({
      clubblad: { op: 'empty' },
      email: { op: 'notEmpty' },
    });
    // No `value` key leaks onto a presence operator.
    expect('value' in (result.clubblad as object)).toBe(false);
    expect('value' in (result.email as object)).toBe(false);
  });

  it('lets the last row win on a duplicate field key', () => {
    const result = fromFilterDrafts([
      draft({ field: 'clubblad', op: 'eq', value: 'Papier' }),
      draft({ field: 'clubblad', op: 'contains', value: 'dig' }),
    ]);
    expect(result).toEqual({ clubblad: { op: 'contains', value: 'dig' } });
  });

  // --- FLIPPED behavior: year keys compose GENERICALLY, no carry-through ----
  // Previously `fromFilterDrafts(drafts, base)` carried reserved year keys from
  // `base` untouched. The `base` parameter is gone and the map is built PURELY
  // from the editor rows: a years_member row composes like any other field.
  it('composes a years_member row generically (gte jubilee), not via a carve-out', () => {
    const result = fromFilterDrafts([draft({ field: 'years_member', op: 'gte', value: '25' })]);
    expect(result).toEqual({ years_member: { op: 'gte', value: '25' } });
  });
});

describe('memberFieldPicker.helpers round-trip', () => {
  it('round-trips a legacy scalar through the object form with identical field/op/value', () => {
    const composed = fromFilterDrafts(toFilterDrafts({ clubblad: 'Papier' }));
    expect(composed).toEqual({ clubblad: { op: 'eq', value: 'Papier' } });
  });

  it('round-trips a years_member legacy scalar as an ordinary eq clause', () => {
    const composed = fromFilterDrafts(toFilterDrafts({ years_member: 25 }));
    expect(composed).toEqual({ years_member: { op: 'eq', value: '25' } });
  });

  it('round-trips a mixed map preserving every kept row (field, op, value)', () => {
    const map = {
      clubblad: { op: 'contains', value: 'pap' },
      years_member: 25,
      email: { op: 'notEmpty' },
    };
    const back = fromFilterDrafts(toFilterDrafts(map));
    expect(back).toEqual({
      clubblad: { op: 'contains', value: 'pap' },
      years_member: { op: 'eq', value: '25' },
      email: { op: 'notEmpty' },
    });
  });
});
