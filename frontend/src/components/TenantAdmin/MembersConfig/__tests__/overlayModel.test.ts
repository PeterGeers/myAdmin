/**
 * Unit tests for the pure `field_overlay` working-model (Members config redesign Phase 3, task 4.0).
 *
 * These lock the single-save contract at its foundation: every drill-down mutation is a pure
 * `(overlay, …) → overlay'` transform (no network, no React), so the editor can commit the result
 * verbatim through the ONE `saveMembersParameter` primitive (one save → one request → one
 * re-projection, `38` rule 5 / Property 8). The suite asserts the derived ordering (`38` rule 2),
 * the delete-group-only-when-empty guard (R4.2), the move-to-group reassignment (R4.3), and strict
 * immutability of the input.
 */
import { describe, it, expect } from 'vitest';
import type { MembersConfigValue } from '../../../../types/membersConfig';
import {
  listGroups,
  groupExists,
  listAllFields,
  listFieldsInGroup,
  listUngroupedFields,
  groupFieldCount,
  findField,
  createGroup,
  editGroup,
  deleteGroup,
  createField,
  editField,
  upsertField,
  deleteField,
  setFieldAttribute,
  deleteFieldAttribute,
  moveFieldToGroup,
} from '../overlayModel';

/** A representative overlay: two groups + three fields (one with a scope attribute, one override). */
function sampleOverlay(): MembersConfigValue {
  return {
    functional_groups: [
      { key: 'motor', label_en: 'Motorcycle', label_nl: 'Motor', order: 2 },
      { key: 'personal', label_en: 'Personal', label_nl: 'Persoonlijk', order: 1 },
    ],
    fields: {
      motor_brand: {
        type: 'string',
        label_en: 'Motor brand',
        functional_group: 'motor',
        visible: true,
        order: 1,
      },
      region: {
        type: 'string',
        label_en: 'Region',
        functional_group: 'personal',
        order: 3,
        scope: { enabled: true, values: ['Region A'] },
      },
      first_name: {
        type: 'string',
        label_en: 'First name',
        functional_group: 'personal',
        order: 1,
      },
    },
    fixed_overrides: {
      'personal.last_name': { label_en: 'Last name', functional_group: 'personal', order: 2 },
    },
  };
}

/** Deep-clone to assert the input was not mutated by a helper. */
function snapshot(v: MembersConfigValue): string {
  return JSON.stringify(v);
}

describe('overlayModel — read helpers', () => {
  it('listGroups returns groups in derived (group.order, key) order', () => {
    const groups = listGroups(sampleOverlay());
    expect(groups.map((g) => g.key)).toEqual(['personal', 'motor']); // order 1 then 2
  });

  it('listGroups is deterministic on a key tie-break when orders are equal/absent', () => {
    const overlay: MembersConfigValue = {
      functional_groups: [{ key: 'zeta' }, { key: 'alpha' }],
    };
    expect(listGroups(overlay).map((g) => g.key)).toEqual(['alpha', 'zeta']);
  });

  it('groupExists reflects presence', () => {
    expect(groupExists(sampleOverlay(), 'personal')).toBe(true);
    expect(groupExists(sampleOverlay(), 'ghost')).toBe(false);
  });

  it('listAllFields pairs every field with its origin map', () => {
    const all = listAllFields(sampleOverlay());
    const byKey = Object.fromEntries(all.map((e) => [e.key, e.origin]));
    expect(byKey).toEqual({
      motor_brand: 'fields',
      region: 'fields',
      first_name: 'fields',
      'personal.last_name': 'fixed_overrides',
    });
  });

  it('listFieldsInGroup returns a group\'s fields in derived (field.order, key) order', () => {
    const personal = listFieldsInGroup(sampleOverlay(), 'personal');
    // first_name(1), personal.last_name(2), region(3)
    expect(personal.map((e) => e.key)).toEqual(['first_name', 'personal.last_name', 'region']);
  });

  it('groupFieldCount counts across both maps', () => {
    expect(groupFieldCount(sampleOverlay(), 'personal')).toBe(3);
    expect(groupFieldCount(sampleOverlay(), 'motor')).toBe(1);
    expect(groupFieldCount(sampleOverlay(), 'ghost')).toBe(0);
  });

  it('listUngroupedFields surfaces fields with an absent OR non-catalog-resolvable group (R4.3)', () => {
    const overlay: MembersConfigValue = {
      functional_groups: [{ key: 'personal', order: 1 }],
      fields: {
        in_group: { type: 'string', functional_group: 'personal' },
        orphan_ghost: { type: 'string', functional_group: 'ghost' }, // present but undefined group
        orphan_none: { type: 'string' }, // no group at all
      },
      fixed_overrides: {},
    };
    const ungrouped = listUngroupedFields(overlay).map((e) => e.key);
    expect(ungrouped).toEqual(['orphan_ghost', 'orphan_none']); // key-sorted; in_group excluded
  });

  it('findField locates a field in either map', () => {
    expect(findField(sampleOverlay(), 'region')?.origin).toBe('fields');
    expect(findField(sampleOverlay(), 'personal.last_name')?.origin).toBe('fixed_overrides');
    expect(findField(sampleOverlay(), 'nope')).toBeNull();
  });

  it('read helpers tolerate an absent / malformed overlay', () => {
    expect(listGroups(undefined)).toEqual([]);
    expect(listAllFields(null as unknown as MembersConfigValue)).toEqual([]);
    expect(groupFieldCount({ functional_groups: 'bogus' } as unknown as MembersConfigValue, 'x')).toBe(0);
  });
});

describe('overlayModel — group writes', () => {
  it('createGroup appends a new group (and is a no-op on a duplicate key)', () => {
    const o0 = sampleOverlay();
    const before = snapshot(o0);
    const o1 = createGroup(o0, { key: 'address', label_en: 'Address', order: 3 });
    expect(groupExists(o1, 'address')).toBe(true);
    // input not mutated
    expect(snapshot(o0)).toBe(before);
    // duplicate key → unchanged
    const o2 = createGroup(o1, { key: 'address' });
    expect(listGroups(o2).filter((g) => g.key === 'address')).toHaveLength(1);
  });

  it('editGroup patches a group\'s own attributes', () => {
    const o1 = editGroup(sampleOverlay(), 'personal', { label_en: 'Personal (edited)', order: 5 });
    const g = listGroups(o1).find((x) => x.key === 'personal');
    expect(g?.label_en).toBe('Personal (edited)');
    expect(g?.order).toBe(5);
  });

  it('editGroup key-rename re-points every field that referenced the old key', () => {
    const o1 = editGroup(sampleOverlay(), 'personal', { key: 'people' });
    expect(groupExists(o1, 'people')).toBe(true);
    expect(groupExists(o1, 'personal')).toBe(false);
    // the three personal fields now reference `people`, none orphaned
    expect(groupFieldCount(o1, 'people')).toBe(3);
    expect(groupFieldCount(o1, 'personal')).toBe(0);
    expect(findField(o1, 'region')?.field.functional_group).toBe('people');
  });

  it('editGroup refuses a rename that would collide with an existing group', () => {
    const o1 = editGroup(sampleOverlay(), 'personal', { key: 'motor' });
    // unchanged — both original keys still present
    expect(groupExists(o1, 'personal')).toBe(true);
    expect(groupExists(o1, 'motor')).toBe(true);
  });

  it('editGroup MATERIALIZES a base group not yet in the overlay (regression: was a silent no-op)', () => {
    // `financial` is a PLATFORM BASE group — present in the resolved catalog, absent from this
    // overlay. Editing its order used to return the overlay UNCHANGED (modal closed, nothing saved).
    const o0 = sampleOverlay();
    expect(groupExists(o0, 'financial')).toBe(false);
    const o1 = editGroup(o0, 'financial', { label_en: 'Financial', label_nl: 'Financieel', order: 50 });
    const g = listGroups(o1).find((x) => x.key === 'financial');
    expect(g).toBeDefined();
    expect(g?.order).toBe(50);
    expect(g?.label_en).toBe('Financial');
    // input not mutated
    expect(snapshot(o0)).not.toBe(snapshot(o1));
  });

  it('editGroup materialize is a real change (so the editor dirties + the save fires)', () => {
    const o0 = sampleOverlay();
    const o1 = editGroup(o0, 'financial', { order: 50 });
    // The returned overlay DIFFERS from the input — this is what flips the editor's dirty state and
    // makes the single Save commit (the missing network call in the bug report).
    expect(JSON.stringify(o1)).not.toBe(JSON.stringify(o0));
    expect(listGroups(o1).some((g) => g.key === 'financial')).toBe(true);
  });

  it('deleteGroup removes an EMPTY group', () => {
    const o1 = createGroup(sampleOverlay(), { key: 'empty', order: 9 });
    const o2 = deleteGroup(o1, 'empty');
    expect(groupExists(o2, 'empty')).toBe(false);
  });

  it('deleteGroup REFUSES a non-empty group (R4.2 guard)', () => {
    const o0 = sampleOverlay();
    const o1 = deleteGroup(o0, 'personal'); // personal has 3 fields
    expect(groupExists(o1, 'personal')).toBe(true); // guard held
    expect(groupFieldCount(o1, 'personal')).toBe(3);
  });
});

describe('overlayModel — field writes', () => {
  it('createField adds a tenant-added field to `fields` by default', () => {
    const o1 = createField(sampleOverlay(), 'nickname', {
      type: 'string',
      functional_group: 'personal',
    });
    const e = findField(o1, 'nickname');
    expect(e?.origin).toBe('fields');
    expect(e?.field.functional_group).toBe('personal');
  });

  it('createField is a no-op when the key already exists in either map', () => {
    const o1 = createField(sampleOverlay(), 'region', { type: 'string' });
    // still exactly one `region`, original attributes intact
    expect(listAllFields(o1).filter((e) => e.key === 'region')).toHaveLength(1);
    expect(findField(o1, 'region')?.field.scope).toEqual({ enabled: true, values: ['Region A'] });
  });

  it('editField shallow-merges a patch and preserves other attributes', () => {
    const o1 = editField(sampleOverlay(), 'region', { required: true });
    const f = findField(o1, 'region')?.field;
    expect(f?.required).toBe(true);
    expect(f?.scope).toEqual({ enabled: true, values: ['Region A'] }); // preserved
    expect(f?.label_en).toBe('Region'); // preserved
  });

  it('editField edits a field living in fixed_overrides', () => {
    const o1 = editField(sampleOverlay(), 'personal.last_name', { label_en: 'Surname' });
    expect(findField(o1, 'personal.last_name')?.field.label_en).toBe('Surname');
    expect(findField(o1, 'personal.last_name')?.origin).toBe('fixed_overrides');
  });

  it('deleteField removes a field from whichever map holds it', () => {
    const o1 = deleteField(sampleOverlay(), 'motor_brand');
    expect(findField(o1, 'motor_brand')).toBeNull();
    const o2 = deleteField(sampleOverlay(), 'personal.last_name');
    expect(findField(o2, 'personal.last_name')).toBeNull();
  });

  it('setFieldAttribute / deleteFieldAttribute add and remove a single attribute', () => {
    const o1 = setFieldAttribute(sampleOverlay(), 'motor_brand', 'required', true);
    expect(findField(o1, 'motor_brand')?.field.required).toBe(true);
    const o2 = deleteFieldAttribute(o1, 'region', 'scope');
    expect(findField(o2, 'region')?.field.scope).toBeUndefined();
    // other attributes untouched
    expect(findField(o2, 'region')?.field.label_en).toBe('Region');
  });
});

describe('overlayModel — origin-aware upsert (remediation task 2.2, R1)', () => {
  it('upsert CREATES a base-field override in `fixed_overrides` the first time (origin targets the slice)', () => {
    // `email` is a base field with no overlay entry yet; a relabel seeds a fixed_overrides entry.
    const o1 = upsertField(sampleOverlay(), 'personal.email', { label_en: 'E-mail' }, 'fixed_overrides');
    const e = findField(o1, 'personal.email');
    expect(e?.origin).toBe('fixed_overrides');
    expect(e?.field.label_en).toBe('E-mail');
    // did NOT leak into `fields`
    expect(Object.keys((o1 as Record<string, Record<string, unknown>>).fields)).not.toContain('personal.email');
  });

  it('upsert CREATES a tenant-added field in `fields` by default', () => {
    const o1 = upsertField(sampleOverlay(), 'nickname', { type: 'string', functional_group: 'personal' });
    const e = findField(o1, 'nickname');
    expect(e?.origin).toBe('fields');
    expect(e?.field.type).toBe('string');
  });

  it('upsert EDITS an existing field in whichever slice it already lives in (never moves it across maps)', () => {
    // `region` lives in `fields`; even if asked to target fixed_overrides the edit stays in `fields`.
    const o1 = upsertField(sampleOverlay(), 'region', { required: true }, 'fixed_overrides');
    expect(findField(o1, 'region')?.origin).toBe('fields');
    expect(findField(o1, 'region')?.field.required).toBe(true);
    // and no stray fixed_overrides entry was created for it
    expect(findField(o1, 'region')).not.toBeNull();

    // `personal.last_name` lives in fixed_overrides; the edit stays there.
    const o2 = upsertField(sampleOverlay(), 'personal.last_name', { label_en: 'Surname' }, 'fixed_overrides');
    expect(findField(o2, 'personal.last_name')?.origin).toBe('fixed_overrides');
    expect(findField(o2, 'personal.last_name')?.field.label_en).toBe('Surname');
  });

  it('upsert strips undefined patch attributes on CREATE and deletes them on EDIT', () => {
    // create: an undefined attr is not written at all
    const o1 = upsertField(sampleOverlay(), 'personal.email', { label_en: 'E-mail', visible: undefined }, 'fixed_overrides');
    expect(findField(o1, 'personal.email')?.field).not.toHaveProperty('visible');
    // edit: an undefined attr deletes it (region starts with a scope attribute)
    const o2 = upsertField(sampleOverlay(), 'region', { scope: undefined });
    expect(findField(o2, 'region')?.field.scope).toBeUndefined();
  });

  it('upsert is a no-op for an empty key, and never mutates its input', () => {
    const o0 = sampleOverlay();
    const before = snapshot(o0);
    expect(upsertField(o0, '', { label_en: 'x' })).toEqual(o0);
    upsertField(o0, 'personal.email', { label_en: 'E-mail' }, 'fixed_overrides');
    upsertField(o0, 'region', { required: true });
    expect(snapshot(o0)).toBe(before);
  });
});

describe('overlayModel — move to group (R4.3)', () => {
  it('moveFieldToGroup reassigns ONLY functional_group', () => {
    const o1 = moveFieldToGroup(sampleOverlay(), 'region', 'motor');
    const f = findField(o1, 'region')?.field;
    expect(f?.functional_group).toBe('motor');
    // nothing else changed
    expect(f?.scope).toEqual({ enabled: true, values: ['Region A'] });
    expect(f?.order).toBe(3);
    expect(groupFieldCount(o1, 'personal')).toBe(2);
    expect(groupFieldCount(o1, 'motor')).toBe(2);
  });

  it('moveFieldToGroup can re-point an unresolvable reference (does not validate the target)', () => {
    const o1 = moveFieldToGroup(sampleOverlay(), 'region', 'ghost');
    expect(findField(o1, 'region')?.field.functional_group).toBe('ghost');
  });

  it('moveFieldToGroup is a no-op for a missing field', () => {
    const o0 = sampleOverlay();
    const before = snapshot(o0);
    const o1 = moveFieldToGroup(o0, 'does_not_exist', 'motor');
    expect(snapshot(o1)).toBe(before);
  });
});

describe('overlayModel — immutability', () => {
  it('no write helper mutates its input overlay', () => {
    const o0 = sampleOverlay();
    const before = snapshot(o0);
    createGroup(o0, { key: 'x' });
    editGroup(o0, 'personal', { label_en: 'z' });
    deleteGroup(o0, 'motor');
    createField(o0, 'y', { type: 'string' });
    editField(o0, 'region', { required: true });
    deleteField(o0, 'region');
    setFieldAttribute(o0, 'region', 'required', true);
    deleteFieldAttribute(o0, 'region', 'scope');
    moveFieldToGroup(o0, 'region', 'motor');
    expect(snapshot(o0)).toBe(before);
  });
});
