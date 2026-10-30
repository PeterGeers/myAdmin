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
import fc from 'fast-check';
import {
  bareFieldKey,
  deriveFieldConfigChangeOps,
} from '../fieldConfigChangeOps';
import type { FieldConfigChangeOp } from '../../../../services/members/membersConfigApi';
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

/**
 * Round-trip-every-boolean (spec 03b BU-5 / task 4.2; Req 2.1/2.2/2.3/2.4 — the toggle-persistence
 * root cause). The 03b root fix diffs each boolean field attribute against the LOADED baseline so a
 * true→false transition emits an EXPLICIT `false` op (never a dropped `undefined` that silently
 * reverts on reload). 03a fixed `required`; 03b fixes `application_visible`/`application_required`;
 * these tests iterate ALL FOUR booleans so a FUTURE boolean cannot regress the same way (Req 2.4).
 *
 * The four booleans split across two DISJOINT op surfaces (see fieldConfigChangeOps.ts):
 *  - `required`, `visible`               → DEFINITION surface  (`set_field`)
 *  - `application_visible`, `application_required` → APPLICATION surface (`set_field_application`)
 *
 * **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
 */
describe('deriveFieldConfigChangeOps — round-trip EVERY boolean (true→false emits explicit false)', () => {
  /** The four boolean field attributes and the op surface each OFF must land on. */
  const BOOLEAN_ATTRS = [
    { attr: 'required', op: 'set_field' as const },
    { attr: 'visible', op: 'set_field' as const },
    { attr: 'application_visible', op: 'set_field_application' as const },
    { attr: 'application_required', op: 'set_field_application' as const },
  ];

  /** A single-field overlay carrying `attr`=`value` (plus a stable base so only the attr varies). */
  const overlayWithBool = (attr: string, value: boolean): MembersConfigValue => ({
    fields: {
      field_x: { type: 'string', functional_group: 'personal', [attr]: value } as MembersConfigValue,
    },
    fixed_overrides: {},
    functional_groups: [],
  });

  /** Find the op on `surface` for `field_x` and return its attrs (or undefined if not emitted). */
  const attrsOn = (
    ops: FieldConfigChangeOp[],
    surface: 'set_field' | 'set_field_application',
  ): Record<string, unknown> | undefined => {
    const hit = ops.find((o) => o.op === surface && 'key' in o && o.key === 'field_x');
    return hit && 'attrs' in hit ? (hit.attrs as Record<string, unknown>) : undefined;
  };

  it('PROPERTY: for EVERY boolean attr, true→false emits an EXPLICIT false on its surface (not a dropped undefined)', () => {
    fc.assert(
      fc.property(fc.constantFrom(...BOOLEAN_ATTRS), ({ attr, op }) => {
        const baseline = overlayWithBool(attr, true); // last loaded from server: ON
        const working = overlayWithBool(attr, false); // admin toggled it OFF
        const ops = deriveFieldConfigChangeOps(baseline, working);

        const attrs = attrsOn(ops, op);
        // The OFF reaches the wire as a deliberate `false` on the correct disjoint surface …
        expect(attrs).toBeDefined();
        expect(attrs![attr]).toBe(false);
        // … NOT silently dropped (the pre-03b bug: undefined meant both "unchanged" and "off").
        expect(attrs![attr]).not.toBeUndefined();
      }),
    );
  });

  it('PROPERTY: an explicit false ROUND-TRIPS — reloading the OFF state re-derives nothing (reload shows OFF, no spurious re-emit)', () => {
    fc.assert(
      fc.property(fc.constantFrom(...BOOLEAN_ATTRS), ({ attr }) => {
        // Simulate the server having PERSISTED the explicit false: the reloaded baseline now
        // carries attr=false. A fresh edit that leaves it OFF must emit NOTHING for field_x —
        // the value is stable at OFF, not re-toggled, and certainly not reverted to ON.
        const reloaded = overlayWithBool(attr, false);
        const working = overlayWithBool(attr, false);
        const ops = deriveFieldConfigChangeOps(reloaded, working);
        expect(ops.some((o) => 'key' in o && o.key === 'field_x')).toBe(false);
      }),
    );
  });

  it('PROPERTY: toggling a boolean back ON (false→true) emits an explicit true on its surface', () => {
    fc.assert(
      fc.property(fc.constantFrom(...BOOLEAN_ATTRS), ({ attr, op }) => {
        const baseline = overlayWithBool(attr, false); // reloaded OFF
        const working = overlayWithBool(attr, true); // admin toggled it back ON
        const ops = deriveFieldConfigChangeOps(baseline, working);
        const attrs = attrsOn(ops, op);
        expect(attrs).toBeDefined();
        expect(attrs![attr]).toBe(true);
      }),
    );
  });

  it('PROPERTY: a NEW field that OMITS the boolean does NOT get a spurious synthesized false (OFF-diff only fires against a truthy baseline)', () => {
    // Nothing was ON to turn OFF, so the OFF-diff (`emitExplicitBooleanOff`) must not SYNTHESIZE an
    // `{attr: false}` when the working entry does not carry the attr at all. A new field that simply
    // never mentions the boolean leaves it ABSENT — absent-means-unchanged, not an injected false.
    fc.assert(
      fc.property(fc.constantFrom(...BOOLEAN_ATTRS), ({ attr, op }) => {
        const baseline = emptyOverlay(); // field_x does not exist yet
        const working: MembersConfigValue = {
          fields: { field_x: { type: 'string', functional_group: 'personal' } }, // no boolean attr
          fixed_overrides: {},
          functional_groups: [],
        };
        const ops = deriveFieldConfigChangeOps(baseline, working);
        const attrs = attrsOn(ops, op);
        // Whether or not a def op exists (it does for the definition surface, carrying type/group),
        // the boolean attr must be ABSENT — the OFF-diff never synthesizes a false here.
        if (attrs) expect(attrs[attr]).toBeUndefined();
      }),
    );
  });

  it('a NEW field that DECLARES the boolean false carries that false verbatim (the working entry authored it, not the OFF-diff)', () => {
    // Distinct from the synthesized-false case above: when the admin explicitly authors the boolean
    // as false on a brand-new field, that false is a real declared attribute and is written as-is.
    fc.assert(
      fc.property(fc.constantFrom(...BOOLEAN_ATTRS), ({ attr, op }) => {
        const ops = deriveFieldConfigChangeOps(emptyOverlay(), overlayWithBool(attr, false));
        const attrs = attrsOn(ops, op);
        expect(attrs).toBeDefined();
        expect(attrs![attr]).toBe(false);
      }),
    );
  });

  // Concrete, readable example per boolean (complements the property sweep) — ON→OFF→reload OFF.
  for (const { attr, op } of BOOLEAN_ATTRS) {
    it(`EXAMPLE: ${attr} ON→OFF emits { ${attr}: false } on ${op}, and the reloaded OFF state re-derives nothing`, () => {
      const offOps = deriveFieldConfigChangeOps(overlayWithBool(attr, true), overlayWithBool(attr, false));
      const offAttrs = attrsOn(offOps, op);
      expect(offAttrs).toBeDefined();
      expect(offAttrs![attr]).toBe(false);

      // Reload: the server persisted false; editing without touching it writes nothing.
      const reloadOps = deriveFieldConfigChangeOps(overlayWithBool(attr, false), overlayWithBool(attr, false));
      expect(reloadOps.some((o) => 'key' in o && o.key === 'field_x')).toBe(false);
    });
  }
});
