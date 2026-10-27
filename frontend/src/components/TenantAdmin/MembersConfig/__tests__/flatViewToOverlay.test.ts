/**
 * Tests for flatViewToOverlay — reconstructing the authoring overlay from the resolved Flat_View
 * (spec 03 bugfix: the 5.1↔5.3 seam that left the editor buffer empty, breaking move-to-group).
 */
import { describe, it, expect } from 'vitest';
import { flatViewToOverlay } from '../flatViewToOverlay';
import { deriveFieldConfigChangeOps } from '../fieldConfigChangeOps';
import { moveFieldToGroup } from '../overlayModel';
import type { FieldConfig } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';

function cfg(): FieldConfig {
  return {
    fields: [
      // a base field (resolved) in personal
      { key: 'street', origin: 'fixed', functional_group: 'personal', group: 'personal', type: 'string', label: { en: 'Street', nl: 'Straat' }, order: 90 },
      // a base-overridden field
      { key: 'email', origin: 'fixed', functional_group: 'personal', group: 'personal', application_visible: true },
      // a tenant-added variable field
      { key: 'motor_brand', origin: 'variable', functional_group: 'motor', type: 'string' },
      // a calculated field — must be OMITTED
      { key: 'age', origin: 'calculated', functional_group: 'personal', type: 'number' },
    ],
    functional_groups: [
      { key: 'personal', label: { en: 'Personal', nl: 'Persoonlijk' }, order: 10 },
      { key: 'address', label: { en: 'Address', nl: 'Adres' }, order: 20 },
      { key: 'motor', label: { en: 'Motorcycle', nl: 'Motor' }, order: 40 },
    ],
  } as unknown as FieldConfig;
}

describe('flatViewToOverlay', () => {
  it('buckets variable fields under fields[key] and base fields under fixed_overrides[{group}.{key}]', () => {
    const o = flatViewToOverlay(cfg()) as Record<string, Record<string, unknown>>;
    expect(Object.keys(o.fields)).toContain('motor_brand');
    expect(Object.keys(o.fixed_overrides)).toContain('personal.street');
    expect(Object.keys(o.fixed_overrides)).toContain('personal.email');
  });

  it('OMITS calculated fields (read-only, never authored)', () => {
    const o = flatViewToOverlay(cfg()) as Record<string, Record<string, unknown>>;
    const allKeys = [...Object.keys(o.fields), ...Object.keys(o.fixed_overrides)];
    expect(allKeys.some((k) => k.includes('age'))).toBe(false);
  });

  it('carries the full functional_groups catalog', () => {
    const o = flatViewToOverlay(cfg()) as Record<string, unknown>;
    const groups = o.functional_groups as Array<{ key: string }>;
    expect(groups.map((g) => g.key).sort()).toEqual(['address', 'motor', 'personal']);
  });

  it('seeding baseline==working yields NO ops (editor not dirty on load)', () => {
    const seed = flatViewToOverlay(cfg());
    const baseline = JSON.parse(JSON.stringify(seed)) as MembersConfigValue;
    const ops = deriveFieldConfigChangeOps(baseline, seed);
    expect(ops).toEqual([]);
  });

  it('a move-to-group on the reconstructed overlay produces exactly one set_field op for the moved field', () => {
    const seed = flatViewToOverlay(cfg());
    const baseline = JSON.parse(JSON.stringify(seed)) as MembersConfigValue;
    // move the base field `street` from personal -> address
    const moved = moveFieldToGroup(seed, 'street', 'address');
    const ops = deriveFieldConfigChangeOps(baseline, moved);
    const setStreet = ops.filter((o) => o.op === 'set_field' && o.key === 'street');
    expect(setStreet).toHaveLength(1);
    expect((setStreet[0] as { attrs: Record<string, unknown> }).attrs.functional_group).toBe('address');
    // nothing else changed
    expect(ops.filter((o) => o.key !== 'street' && 'key' in o)).toEqual([]);
  });
});
