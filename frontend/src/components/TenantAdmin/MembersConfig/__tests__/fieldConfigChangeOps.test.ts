/**
 * Tests for the config#fields CHANGE-OP builder (spec 03 — config-fields-foolproof-crud,
 * Phase 5 / task 5.1; steering 39).
 *
 * The builder is the heart of the Phase-5 switch: it DERIVES a Change-Op list BY IDENTITY from a
 * (baseline overlay → working overlay) diff, so the configurator / form-builder stop sending a
 * whole catalog and stop reconstructing `{group}.{key}` storage keys. These assert the invariants
 * that make the switch correct:
 *  - every op is keyed by a BARE identity (field `key` / group `group`) — never a dotted storage key;
 *  - an UNCHANGED group/field is NEVER re-sent (so a partial write can't clobber a sibling — the
 *    structural fix for the catalog-truncation bug, root-cause-analysis.md);
 *  - definition vs the four application attrs land on DISJOINT ops (set_field / set_field_application);
 *  - the flat `label_en`/`label_nl` inputs fold into the `label:{nl,en}` object the surface accepts;
 *  - a removed `fields` entry → delete_field; a removed `fixed_overrides` entry → reset_field.
 */
import { describe, it, expect } from 'vitest';
import {
  bareFieldKey,
  deriveFieldConfigChangeOps,
} from '../fieldConfigChangeOps';
import type { MembersConfigValue } from '../../../../types/membersConfig';

type Overlay = MembersConfigValue;

const emptyOverlay = (): Overlay => ({ fields: {}, fixed_overrides: {}, functional_groups: [] });

describe('bareFieldKey', () => {
  it('strips a dotted {group}.{key} storage key down to the bare key', () => {
    expect(bareFieldKey('personal.first_name')).toBe('first_name');
    expect(bareFieldKey('membership.type')).toBe('type');
  });
  it('leaves an already-bare key unchanged', () => {
    expect(bareFieldKey('nickname')).toBe('nickname');
  });
});

describe('deriveFieldConfigChangeOps — nothing changed', () => {
  it('returns an empty list when baseline and working are identical', () => {
    const o: Overlay = {
      functional_groups: [{ key: 'personal', order: 1 }],
      fields: { nickname: { type: 'string', functional_group: 'personal' } },
      fixed_overrides: {},
    };
    expect(deriveFieldConfigChangeOps(o, JSON.parse(JSON.stringify(o)))).toEqual([]);
  });

  it('returns an empty list for two empty overlays', () => {
    expect(deriveFieldConfigChangeOps(emptyOverlay(), emptyOverlay())).toEqual([]);
    expect(deriveFieldConfigChangeOps(undefined, undefined)).toEqual([]);
  });
});

describe('deriveFieldConfigChangeOps — groups (set_group / delete_group by identity)', () => {
  it('emits set_group for an ADDED group, folding label_en/label_nl into label{nl,en}', () => {
    const before = emptyOverlay();
    const after: Overlay = {
      ...emptyOverlay(),
      functional_groups: [{ key: 'address', label_en: 'Address', label_nl: 'Adres', order: 3 }],
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    expect(ops).toEqual([
      { op: 'set_group', group: 'address', attrs: { label: { en: 'Address', nl: 'Adres' }, order: 3 } },
    ]);
  });

  it('emits set_group for an EDITED base group (materialize via set_group), only the changed identity', () => {
    const before: Overlay = {
      ...emptyOverlay(),
      functional_groups: [
        { key: 'personal', order: 1 },
        { key: 'motor', order: 2 },
      ],
    };
    const after: Overlay = {
      ...emptyOverlay(),
      functional_groups: [
        { key: 'personal', order: 5 }, // changed
        { key: 'motor', order: 2 }, // unchanged
      ],
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    expect(ops).toEqual([{ op: 'set_group', group: 'personal', attrs: { order: 5 } }]);
    // The unchanged group is NEVER re-sent (the structural no-clobber guarantee).
    expect(ops.some((o) => 'group' in o && o.group === 'motor')).toBe(false);
  });

  it('emits delete_group for a REMOVED group', () => {
    const before: Overlay = { ...emptyOverlay(), functional_groups: [{ key: 'motor', order: 2 }] };
    const after = emptyOverlay();
    expect(deriveFieldConfigChangeOps(before, after)).toEqual([{ op: 'delete_group', group: 'motor' }]);
  });
});

describe('deriveFieldConfigChangeOps — fields (identity-keyed, disjoint def/app ops)', () => {
  it('emits set_field (definition) for an ADDED variable field, by its BARE key', () => {
    const before = emptyOverlay();
    const after: Overlay = {
      ...emptyOverlay(),
      fields: { nickname: { type: 'string', functional_group: 'personal', label_en: 'Nickname' } },
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    expect(ops).toEqual([
      {
        op: 'set_field',
        key: 'nickname',
        attrs: { label: { en: 'Nickname' }, type: 'string', functional_group: 'personal' },
      },
    ]);
  });

  it('splits an application-attribute edit into a DISJOINT set_field_application op (no definition attrs)', () => {
    const before: Overlay = {
      ...emptyOverlay(),
      fields: { email: { type: 'string', functional_group: 'personal' } },
    };
    const after: Overlay = {
      ...emptyOverlay(),
      fields: {
        email: { type: 'string', functional_group: 'personal', application_visible: true },
      },
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    // Only the application surface changed → ONE set_field_application op, no set_field.
    expect(ops).toEqual([
      { op: 'set_field_application', key: 'email', attrs: { application_visible: true } },
    ]);
  });

  it('keeps definition and application attrs on SEPARATE ops when both change', () => {
    const before: Overlay = { ...emptyOverlay(), fields: { email: { type: 'string' } } };
    const after: Overlay = {
      ...emptyOverlay(),
      fields: { email: { type: 'string', label_en: 'Email', application_required: true } },
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    const def = ops.find((o) => o.op === 'set_field' && o.key === 'email');
    const app = ops.find((o) => o.op === 'set_field_application' && o.key === 'email');
    expect(def).toBeTruthy();
    expect(app).toBeTruthy();
    // Disjoint surfaces: the definition op carries NO application_* attr, and vice versa.
    expect('attrs' in def! && (def!.attrs as Record<string, unknown>).application_required).toBeUndefined();
    expect('attrs' in app! && (app!.attrs as Record<string, unknown>).type).toBeUndefined();
  });

  it('emits a BARE-key op for a base-field override stored under a dotted fixed_overrides key (no {group}.{key} crosses the wire)', () => {
    const before = emptyOverlay();
    const after: Overlay = {
      ...emptyOverlay(),
      fixed_overrides: { 'personal.first_name': { label_en: 'Given name' } },
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    // The server owns placement — the client sends the BARE identity `first_name`, NOT the dotted key.
    expect(ops).toEqual([
      { op: 'set_field', key: 'first_name', attrs: { label: { en: 'Given name' } } },
    ]);
    expect(JSON.stringify(ops)).not.toContain('personal.first_name');
  });

  it('emits delete_field for a REMOVED variable field, reset_field for a REMOVED base override', () => {
    const before: Overlay = {
      functional_groups: [],
      fields: { nickname: { type: 'string' } },
      fixed_overrides: { 'personal.first_name': { label_en: 'First name' } },
    };
    const after = emptyOverlay();
    const ops = deriveFieldConfigChangeOps(before, after);
    expect(ops).toContainEqual({ op: 'delete_field', key: 'nickname' });
    // A removed base-field override is a REVERT (reset_field), by bare identity.
    expect(ops).toContainEqual({ op: 'reset_field', key: 'first_name' });
  });

  it('emits the enum vocabulary under the ONE canonical `options` key and NEVER `choices` (spec 03a / C1)', () => {
    const before = emptyOverlay();
    const after: Overlay = {
      ...emptyOverlay(),
      fields: {
        salutation: {
          type: 'enum',
          functional_group: 'personal',
          options: [
            { value: 'mr', label: { en: 'Mr', nl: 'Dhr' } },
            { value: 'mrs', label: { en: 'Mrs', nl: 'Mevr' } },
          ],
        },
      },
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    const def = ops.find((o) => o.op === 'set_field' && o.key === 'salutation');
    expect(def).toBeTruthy();
    const attrs = ('attrs' in def! ? def!.attrs : {}) as Record<string, unknown>;
    // The definition op carries the vocabulary under `options` …
    expect(attrs.options).toEqual([
      { value: 'mr', label: { en: 'Mr', nl: 'Dhr' } },
      { value: 'mrs', label: { en: 'Mrs', nl: 'Mevr' } },
    ]);
    // … and NEVER a `choices` key — it was dropped from DEFINITION_ATTRS (the write emits one vocabulary).
    expect(attrs.choices).toBeUndefined();
    expect(JSON.stringify(ops)).not.toContain('"choices"');
  });

  it('does NOT emit a retired `choices` attr even if the overlay entry still carries one (write surface rejects it)', () => {
    const before = emptyOverlay();
    // A stale overlay entry authored under the retired `choices` key.
    const after: Overlay = {
      ...emptyOverlay(),
      fields: {
        legacy: {
          type: 'enum',
          functional_group: 'personal',
          choices: [{ value: 'a', label: { en: 'A', nl: 'A' } }],
        } as unknown as MembersConfigValue,
      },
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    // `choices` is NOT in DEFINITION_ATTRS, so it never reaches the wire — the write emits only the
    // canonical attrs (here just `type`/`functional_group`); the retired vocabulary key is dropped.
    expect(JSON.stringify(ops)).not.toContain('"choices"');
  });

  it('leaves an UNCHANGED field unaddressed while writing only the edited one (no sibling clobber)', () => {
    const before: Overlay = {
      ...emptyOverlay(),
      fields: {
        a: { type: 'string', application_visible: true }, // prior selection
        b: { type: 'string' },
      },
    };
    const after: Overlay = {
      ...emptyOverlay(),
      fields: {
        a: { type: 'string', application_visible: true }, // unchanged
        b: { type: 'string', application_visible: true }, // the edit
      },
    };
    const ops = deriveFieldConfigChangeOps(before, after);
    expect(ops).toEqual([
      { op: 'set_field_application', key: 'b', attrs: { application_visible: true } },
    ]);
    // The prior selection `a` is NEVER addressed — the server leaves it physically untouched.
    expect(ops.some((o) => 'key' in o && o.key === 'a')).toBe(false);
  });
});
