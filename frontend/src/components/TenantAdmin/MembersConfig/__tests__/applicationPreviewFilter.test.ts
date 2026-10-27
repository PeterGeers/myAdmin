/**
 * Unit tests for the PURE in-browser preview filter (spec 12 — Application Form Serving Redesign,
 * task 5.1; R3.1/R3.2, design §C2 / D4).
 *
 * `buildPreviewConfig` reproduces the server `get_public_field_config`'s applicant-facing SELECTION
 * entirely in the browser over the WORKING draft (resolved `FieldConfig` ⊕ the one `field_overlay`).
 * These pin its selection + projection rules; task 5.3 (a later wave) additionally parity-pins the
 * output to the real server filter via a shared fixture. Fixtures use the bare `key` + `group`
 * server shape (R2.3).
 */
import { describe, it, expect } from 'vitest';
import { buildPreviewConfig } from '../applicationPreviewFilter';
import type { FieldConfig, FieldConfigField, MembershipType } from '../../../../types/members';
import type { MembersConfigValue } from '../../../../types/membersConfig';

function field(key: string, group: string, extra: Partial<FieldConfigField> = {}): FieldConfigField {
  return {
    key,
    group,
    type: 'string',
    label: { nl: `NL ${key}`, en: `EN ${key}` },
    functional_group: group,
    origin: 'fixed',
    provenance: 'base',
    ...extra,
  };
}

function cfg(fields: FieldConfigField[]): FieldConfig {
  return { fields } as FieldConfig;
}

describe('buildPreviewConfig — selection (application_visible)', () => {
  it('keeps only fields that are ON the form (served)', () => {
    const config = cfg([
      field('email', 'personal', { application_visible: true }),
      field('note', 'personal', { application_visible: false }),
      field('other', 'personal'), // default OFF
    ]);
    const out = buildPreviewConfig(config, {});
    expect(out.fields.map((f) => f.key)).toEqual(['personal.email']);
  });

  it('an UNSAVED overlay toggle wins over the served value (origin-aware override key)', () => {
    const config = cfg([field('email', 'personal', { application_visible: false })]);
    const overlay: MembersConfigValue = {
      fixed_overrides: { 'personal.email': { application_visible: true } },
    };
    const out = buildPreviewConfig(config, overlay);
    expect(out.fields.map((f) => f.key)).toEqual(['personal.email']);
  });

  it('an overlay toggle OFF hides a served-ON field (unsaved edit wins both ways)', () => {
    const config = cfg([field('email', 'personal', { application_visible: true })]);
    const overlay: MembersConfigValue = {
      fixed_overrides: { 'personal.email': { application_visible: false } },
    };
    expect(buildPreviewConfig(config, overlay).fields).toHaveLength(0);
  });

  it('a tenant-added field is toggled via the bare `fields[key]` key', () => {
    const config = cfg([
      field('custom', 'overlay', { origin: 'variable', provenance: 'tenant_added' }),
    ]);
    const overlay: MembersConfigValue = { fields: { custom: { application_visible: true } } };
    expect(buildPreviewConfig(config, overlay).fields.map((f) => f.key)).toEqual(['overlay.custom']);
  });
});

describe('buildPreviewConfig — projection (R5.3 shape)', () => {
  it('projects key (dotted), type, label, group, order, required', () => {
    const config = cfg([
      field('email', 'personal', {
        application_visible: true,
        application_required: true,
        type: 'string',
        order: 3,
      }),
    ]);
    const [f] = buildPreviewConfig(config, {}).fields;
    expect(f.key).toBe('personal.email');
    expect(f.type).toBe('string');
    expect(f.label).toEqual({ nl: 'NL email', en: 'EN email' });
    expect(f.functional_group).toBe('personal');
    expect(f.order).toBe(3);
    expect(f.required).toBe(true);
  });

  it('carries the APPLICATION-required flag, defaulting to false (not the staff required)', () => {
    const config = cfg([field('email', 'personal', { application_visible: true, required: true })]);
    // staff `required` is true but no application_required → application form is NOT required.
    expect(buildPreviewConfig(config, {}).fields[0].required).toBe(false);
  });

  it('applies the application_choices SUBSET to an enum field (overlay wins)', () => {
    const config = cfg([
      field('colour', 'overlay', {
        type: 'enum',
        application_visible: true,
        options: ['red', 'green', 'blue'],
        origin: 'variable',
        provenance: 'tenant_added',
      }),
    ]);
    const overlay: MembersConfigValue = {
      fields: { colour: { application_visible: true, application_choices: ['red', 'blue'] } },
    };
    const [f] = buildPreviewConfig(config, overlay).fields;
    expect((f.options ?? []).map((o) => (typeof o === 'string' ? o : o.value))).toEqual([
      'red',
      'blue',
    ]);
  });

  it('a null/absent subset exposes the full choice set (back-compatible)', () => {
    const config = cfg([
      field('colour', 'overlay', {
        type: 'enum',
        application_visible: true,
        options: ['red', 'green'],
        origin: 'variable',
        provenance: 'tenant_added',
      }),
    ]);
    const [f] = buildPreviewConfig(config, {}).fields;
    expect((f.options ?? []).map((o) => (typeof o === 'string' ? o : o.value))).toEqual([
      'red',
      'green',
    ]);
  });

  it('does NOT attach options to a plain string field (no choice-on-string)', () => {
    const config = cfg([field('name', 'personal', { application_visible: true })]);
    expect(buildPreviewConfig(config, {}).fields[0].options).toBeUndefined();
  });

  it('carries a declarative format token when present', () => {
    const config = cfg([
      field('iban', 'personal', {
        application_visible: true,
        format: { checker: 'IBAN' },
      }),
    ]);
    expect(buildPreviewConfig(config, {}).fields[0].format).toEqual({ checker: 'IBAN' });
  });

  it('carries show_when when present', () => {
    const config = cfg([
      field('spouse', 'personal', {
        application_visible: true,
        show_when: { married: true },
      }),
    ]);
    expect(buildPreviewConfig(config, {}).fields[0].show_when).toEqual({ married: true });
  });
});

describe('buildPreviewConfig — membership_type reference field', () => {
  const catalog: MembershipType[] = [
    { type_code: 'student', label: { nl: 'Student', en: 'Student' } } as MembershipType,
    { type_code: 'regular', label: { nl: 'Gewoon', en: 'Regular' } } as MembershipType,
    { type_code: 'honorary', label: { nl: 'Erelid', en: 'Honorary' } } as MembershipType,
  ];

  it('sources options from the LIVE catalog, filtered to the declared subset', () => {
    const config = cfg([
      field('membership_type', 'membership', {
        type: 'reference',
        application_visible: true,
        application_choices: ['student', 'regular'],
      }),
    ]);
    const [f] = buildPreviewConfig(config, {}, catalog).fields;
    expect((f.options ?? []).map((o) => (typeof o === 'string' ? o : o.value))).toEqual([
      'student',
      'regular',
    ]);
  });

  it('offers the whole catalog when no subset is declared', () => {
    const config = cfg([
      field('membership_type', 'membership', { type: 'reference', application_visible: true }),
    ]);
    const [f] = buildPreviewConfig(config, {}, catalog).fields;
    expect((f.options ?? []).map((o) => (typeof o === 'string' ? o : o.value))).toEqual([
      'student',
      'regular',
      'honorary',
    ]);
  });
});

describe('buildPreviewConfig — envelope', () => {
  it('carries the applicant locales and a null notice', () => {
    const out = buildPreviewConfig(cfg([]), {});
    expect(out.locales).toEqual(['nl', 'en']);
    expect(out.notice).toBeNull();
    expect(out.fields).toEqual([]);
  });

  it('tolerates a null field config', () => {
    expect(buildPreviewConfig(null, {}).fields).toEqual([]);
  });
});
