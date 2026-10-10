/**
 * Tests for the pure label-line composer (labels sub-spec task 1.1,
 * Properties 1 / 2 / 4).
 *
 * `composeLabelLines(rows, fieldConfig, template)` turns a stored label template
 * (ordered `lines` of pivot-result field keys) into one `{ lines: string[] }`
 * per row — the analytics-free counterpart to `composeAddresses`. These assert:
 *
 *   - **Property 1** — a template with N lines yields N output lines, in order,
 *     for a row with every field present.
 *   - **Property 2** — a multi-key line joins its field values space-separated,
 *     in the template's field order.
 *   - empty/absent field values are dropped from their line; a line whose keys
 *     are ALL absent is dropped (no blank gap); an all-empty row → `{ lines: [] }`.
 *   - the composer reads values the SAME way the table does — nested storage
 *     group (via `groupForKey`) AND the flat fallback both resolve.
 *   - **Property 4** — the function signature takes NO `analytics`; no test here
 *     ever supplies one, and the composer reads only rows / fieldConfig / template.
 *
 * Pure module (no React, no I/O) so it is imported + asserted on directly.
 *
 * Validates: Requirements R-L3 (Properties 1, 2, 4)
 */
import { describe, it, expect } from 'vitest';

import {
  composeLabelLines,
  type LabelTemplateLines,
} from './addressLabelService';
import type { FieldConfig, MemberRow } from '../../../types/members';

// ---------------------------------------------------------------------------
// Fixtures. `last_name` is a NESTED fixed field (group `personal`) to exercise
// the nested-bucket read; `display_name` is flat to exercise the flat fallback.
// ---------------------------------------------------------------------------

const fieldConfig = {
  fields: [
    { key: 'display_name', group: 'personal' },
    { key: 'last_name', group: 'personal' },
    { key: 'street', group: 'personal' },
    { key: 'postal_code', group: 'personal' },
    { key: 'city', group: 'personal' },
    { key: 'country', group: 'personal' },
  ],
} as unknown as FieldConfig;

/** A row with every referenced field present (nested bucket + a flat alias). */
const fullRow = {
  member_id: 'm1',
  personal: { last_name: 'Jansen', street: 'Dorpsstraat 1', postal_code: '1234 AB', city: 'Utrecht', country: 'Nederland' },
  // display_name is a flat alias (not under personal) — flat fallback must find it.
  display_name: 'A. Jansen',
} as unknown as MemberRow;

describe('composeLabelLines', () => {
  it('Property 1: N template lines yield N output lines, in order', () => {
    const template: LabelTemplateLines = {
      lines: [['display_name'], ['street'], ['postal_code', 'city'], ['country']],
    };

    const [label] = composeLabelLines([fullRow], fieldConfig, template);

    expect(label.lines).toEqual([
      'A. Jansen',
      'Dorpsstraat 1',
      '1234 AB Utrecht',
      'Nederland',
    ]);
    expect(label.lines).toHaveLength(template.lines.length);
  });

  it('Property 2: a multi-field line joins its values space-separated in field order', () => {
    const template: LabelTemplateLines = { lines: [['postal_code', 'city']] };

    const [label] = composeLabelLines([fullRow], fieldConfig, template);

    expect(label.lines).toEqual(['1234 AB Utrecht']);
  });

  it('reads a nested group field AND a flat-alias field the same way the table does', () => {
    // last_name resolves via its nested personal bucket; display_name via flat fallback.
    const template: LabelTemplateLines = { lines: [['display_name', 'last_name']] };

    const [label] = composeLabelLines([fullRow], fieldConfig, template);

    expect(label.lines).toEqual(['A. Jansen Jansen']);
  });

  it('drops an empty/absent field from its line, keeping the surrounding values', () => {
    const row = {
      member_id: 'm2',
      personal: { postal_code: '', city: 'Breda', country: 'Nederland' },
      display_name: 'B. Bos',
    } as unknown as MemberRow;
    // postal_code is empty, city present → line keeps only the city.
    const template: LabelTemplateLines = { lines: [['display_name'], ['postal_code', 'city']] };

    const [label] = composeLabelLines([row], fieldConfig, template);

    expect(label.lines).toEqual(['B. Bos', 'Breda']);
  });

  it('drops a line whose keys are all absent (no blank gap)', () => {
    const row = {
      member_id: 'm3',
      personal: { city: 'Breda' },
      display_name: 'C. Cohen',
    } as unknown as MemberRow;
    // The middle line (street) is entirely absent → dropped, no empty line.
    const template: LabelTemplateLines = {
      lines: [['display_name'], ['street'], ['city']],
    };

    const [label] = composeLabelLines([row], fieldConfig, template);

    expect(label.lines).toEqual(['C. Cohen', 'Breda']);
  });

  it('an all-empty row yields a label with no lines', () => {
    const row = { member_id: 'm4', personal: {} } as unknown as MemberRow;
    const template: LabelTemplateLines = { lines: [['display_name'], ['street']] };

    const [label] = composeLabelLines([row], fieldConfig, template);

    expect(label.lines).toEqual([]);
  });

  it('composes one label per row, preserving row order', () => {
    const rowB = {
      member_id: 'm5',
      personal: {},
      display_name: 'D. Dekker',
    } as unknown as MemberRow;
    const template: LabelTemplateLines = { lines: [['display_name']] };

    const labels = composeLabelLines([fullRow, rowB], fieldConfig, template);

    expect(labels).toHaveLength(2);
    expect(labels[0].lines).toEqual(['A. Jansen']);
    expect(labels[1].lines).toEqual(['D. Dekker']);
  });

  it('Property 4: resolves with no field config (flat fallback) — never touches analytics', () => {
    // No fieldConfig at all: groupForKey → undefined, valueFor uses the flat key.
    // The composer takes no analytics argument, so this proves the analytics-free path.
    const flatRow = { member_id: 'm6', display_name: 'E. Evers' } as unknown as MemberRow;
    const template: LabelTemplateLines = { lines: [['display_name']] };

    const [label] = composeLabelLines([flatRow], undefined, template);

    expect(label.lines).toEqual(['E. Evers']);
  });

  it('does not mutate its inputs', () => {
    const template: LabelTemplateLines = { lines: [['display_name'], ['street']] };
    const templateSnapshot = JSON.stringify(template);
    const rowSnapshot = JSON.stringify(fullRow);

    composeLabelLines([fullRow], fieldConfig, template);

    expect(JSON.stringify(template)).toBe(templateSnapshot);
    expect(JSON.stringify(fullRow)).toBe(rowSnapshot);
  });
});
