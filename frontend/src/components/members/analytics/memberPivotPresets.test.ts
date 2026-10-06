/**
 * Unit tests for the predefined member-analytics presets (task 7.2, C4).
 *
 * Pins down the availability contract (R4.2 / R4.3 / R9.3):
 *   - fixed/calculated presets are ALWAYS present (and in display order);
 *   - role-backed presets are HIDDEN when their role is unmapped or mapped to a
 *     key that no longer resolves, and PRESENT (materialized with the tenant's
 *     resolved key) when the role resolves;
 *   - the Jubilees preset carries `usesJubileeRule` and stays available from the
 *     calculated `years_member` field regardless of config;
 *   - a preset whose fixed `requiresFields` are absent is hidden.
 *
 * Validates: Requirements R4.2, R4.3, R9.3, R6.1
 */
import { describe, it, expect } from 'vitest';

import {
  getAllPresets,
  getAvailablePresets,
  materializePreset,
  MEMBER_PIVOT_DATA_SOURCE,
} from './memberPivotPresets';
import * as presetsBarrel from './index';
import type { FieldConfig, FieldConfigField } from '../../../types/members';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** The fixed/calculated keys the always-available presets depend on. */
const FIXED_AND_CALCULATED_KEYS = [
  'membership_type',
  'birth_month',
  'years_member',
  'joined_date',
  'country',
];

function field(key: string): FieldConfigField {
  return { key, label: { nl: key, en: key } } as FieldConfigField;
}

/** A field config carrying only the fixed/calculated keys (no analytics config). */
function fixedOnlyConfig(): FieldConfig {
  return { fields: FIXED_AND_CALCULATED_KEYS.map(field) };
}

/**
 * A field config that additionally carries overlay keys and an analytics
 * field-role mapping resolving every role to a present key.
 */
function fullyMappedConfig(): FieldConfig {
  const overlayKeys = [
    'opzeg_datum', // cancellation_date
    'blad_papier', // clubblad_paper
    'blad_digi', //   clubblad_digital
    'hoe_gevonden', // referral_source
  ];
  return {
    fields: [...FIXED_AND_CALCULATED_KEYS, ...overlayKeys].map(field),
    analytics: {
      field_roles: {
        cancellation_date: 'opzeg_datum',
        clubblad_paper: 'blad_papier',
        clubblad_digital: 'blad_digi',
        referral_source: 'hoe_gevonden',
      },
    },
  };
}

const FIXED_PRESET_KEYS = [
  'membership-types',
  'birthday-birth-month',
  'jubilees',
  'new-members',
];
const ROLE_PRESET_KEYS = [
  'cancellations',
  'clubblad-paper-country',
  'clubblad-digital',
  'referral-source',
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('getAllPresets', () => {
  it('returns all eight predefined presets, each on the members data source', () => {
    const all = getAllPresets();
    expect(all).toHaveLength(8);
    for (const preset of all) {
      expect(preset.config.dataSource).toBe(MEMBER_PIVOT_DATA_SOURCE);
      expect(preset.labelKey).toMatch(/^analytics\.pivotViews\.presetNames\./);
    }
  });

  it('marks exactly the Jubilees preset as using the jubilee rule', () => {
    const usingRule = getAllPresets().filter((p) => p.usesJubileeRule);
    expect(usingRule.map((p) => p.key)).toEqual(['jubilees']);
  });
});

describe('getAvailablePresets — fixed/calculated presets are always present', () => {
  it('includes all four fixed/calculated presets with no analytics config', () => {
    const keys = getAvailablePresets(fixedOnlyConfig()).map((p) => p.key);
    for (const fixedKey of FIXED_PRESET_KEYS) {
      expect(keys).toContain(fixedKey);
    }
  });

  it('keeps the jubilee preset available (calculated field) even without config', () => {
    const jubilee = getAvailablePresets(fixedOnlyConfig()).find((p) => p.key === 'jubilees');
    expect(jubilee).toBeDefined();
    expect(jubilee?.usesJubileeRule).toBe(true);
  });

  it('preserves display order of the fixed presets', () => {
    const keys = getAvailablePresets(fixedOnlyConfig()).map((p) => p.key);
    const orderedFixed = keys.filter((k) => FIXED_PRESET_KEYS.includes(k));
    expect(orderedFixed).toEqual(FIXED_PRESET_KEYS);
  });
});

describe('getAvailablePresets — role-backed presets hidden when unmapped/unresolvable', () => {
  it('hides every role-backed preset when there is no analytics config at all', () => {
    const keys = getAvailablePresets(fixedOnlyConfig()).map((p) => p.key);
    for (const roleKey of ROLE_PRESET_KEYS) {
      expect(keys).not.toContain(roleKey);
    }
    // Only the four fixed/calculated presets remain.
    expect(keys).toHaveLength(FIXED_PRESET_KEYS.length);
  });

  it('hides a role-backed preset whose role is mapped to an absent key (stale mapping)', () => {
    const cfg: FieldConfig = {
      fields: FIXED_AND_CALCULATED_KEYS.map(field), // overlay key removed
      analytics: {
        field_roles: { cancellation_date: 'opzeg_datum' }, // key no longer present
      },
    };
    const keys = getAvailablePresets(cfg).map((p) => p.key);
    expect(keys).not.toContain('cancellations');
  });

  it('includes a role-backed preset once its role resolves to a present key', () => {
    const keys = getAvailablePresets(fullyMappedConfig()).map((p) => p.key);
    for (const roleKey of ROLE_PRESET_KEYS) {
      expect(keys).toContain(roleKey);
    }
    // All eight presets available when everything is mapped.
    expect(keys).toHaveLength(8);
  });
});

describe('materializePreset — substitutes the tenant key into the config', () => {
  it('rewrites a role placeholder in groupColumns to the resolved field key', () => {
    const referral = getAllPresets().find((p) => p.key === 'referral-source');
    expect(referral).toBeDefined();
    // The template placeholder is the role name.
    expect(referral?.config.groupColumns).toEqual(['referral_source']);

    const materialized = materializePreset(referral!, fullyMappedConfig());
    expect(materialized).toBeDefined();
    // Substituted with the tenant's resolved overlay key.
    expect(materialized?.config.groupColumns).toEqual(['hoe_gevonden']);
  });

  it('leaves fixed keys intact while substituting the role in a mixed preset', () => {
    const clubblad = getAllPresets().find((p) => p.key === 'clubblad-paper-country');
    const materialized = materializePreset(clubblad!, fullyMappedConfig());
    expect(materialized).toBeDefined();
    // Fixed `country` kept; role requirement resolved separately (not in groupColumns here).
    expect(materialized?.config.groupColumns).toEqual(['country']);
  });

  it('returns undefined when a required role is unresolvable', () => {
    const cancellations = getAllPresets().find((p) => p.key === 'cancellations');
    expect(materializePreset(cancellations!, fixedOnlyConfig())).toBeUndefined();
  });

  it('does not mutate the original preset template on materialization', () => {
    const referral = getAllPresets().find((p) => p.key === 'referral-source')!;
    const before = [...referral.config.groupColumns];
    materializePreset(referral, fullyMappedConfig());
    expect(referral.config.groupColumns).toEqual(before);
  });
});

describe('list presets carry curated listColumns (findings F-009)', () => {
  it('gives every filtered-list preset a non-empty listColumns (no raw dump)', () => {
    for (const preset of getAllPresets()) {
      if (preset.kind === 'list') {
        expect(Array.isArray(preset.config.listColumns)).toBe(true);
        expect(preset.config.listColumns!.length).toBeGreaterThan(0);
        // Identity columns lead every list set.
        expect(preset.config.listColumns).toEqual(
          expect.arrayContaining(['name', 'email']),
        );
      }
    }
  });

  it('curates the birthday list with birthday + address columns', () => {
    const birthday = getAllPresets().find((p) => p.key === 'birthday-birth-month')!;
    expect(birthday.config.listColumns).toEqual(
      expect.arrayContaining(['birthday', 'birth_month', 'street', 'postal_code', 'city', 'country']),
    );
  });

  it('substitutes a role placeholder inside listColumns on materialization', () => {
    // The clubblad-digital list preset names the `clubblad_digital` ROLE in its
    // listColumns; materialization must rewrite it to the tenant's resolved key.
    const digital = getAllPresets().find((p) => p.key === 'clubblad-digital')!;
    expect(digital.config.listColumns).toContain('clubblad_digital');

    const materialized = materializePreset(digital, fullyMappedConfig());
    expect(materialized).toBeDefined();
    // 'clubblad_digital' (role) → 'blad_digi' (tenant key); other columns intact.
    expect(materialized!.config.listColumns).toContain('blad_digi');
    expect(materialized!.config.listColumns).not.toContain('clubblad_digital');
    expect(materialized!.config.listColumns).toEqual(expect.arrayContaining(['name', 'email']));
  });

  it('substitutes the cancellation_date role placeholder inside listColumns', () => {
    const cancellations = getAllPresets().find((p) => p.key === 'cancellations')!;
    expect(cancellations.config.listColumns).toContain('cancellation_date');

    const materialized = materializePreset(cancellations, fullyMappedConfig());
    expect(materialized).toBeDefined();
    expect(materialized!.config.listColumns).toContain('opzeg_datum');
    expect(materialized!.config.listColumns).not.toContain('cancellation_date');
  });
});

describe('getAvailablePresets — requiresFields absence hides fixed presets', () => {
  it('hides membership-types when membership_type is absent', () => {
    const cfg: FieldConfig = {
      fields: FIXED_AND_CALCULATED_KEYS.filter((k) => k !== 'membership_type').map(field),
    };
    const keys = getAvailablePresets(cfg).map((p) => p.key);
    expect(keys).not.toContain('membership-types');
    // Other fixed presets unaffected.
    expect(keys).toContain('new-members');
  });

  it('returns an empty list when the field config has no fields', () => {
    const cfg = { fields: [] } as FieldConfig;
    expect(getAvailablePresets(cfg)).toEqual([]);
  });
});

describe('barrel exports', () => {
  it('re-exports the preset API from the analytics index', () => {
    expect(presetsBarrel.getAvailablePresets).toBe(getAvailablePresets);
    expect(presetsBarrel.getAllPresets).toBe(getAllPresets);
    expect(presetsBarrel.materializePreset).toBe(materializePreset);
  });
});
