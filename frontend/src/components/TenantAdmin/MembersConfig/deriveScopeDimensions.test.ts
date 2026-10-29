/**
 * Unit tests for the scope DERIVE-ON-SAVE primitive (spec 03b BU-6, task 6.3, Req 4.1/4.2).
 *
 * `deriveScopeDimensions` is the one place that turns "a scope-axis field's own options" into the
 * `config#scope` dimension set — the ONE vocabulary both the authoritative SAM `config#scope` write
 * and the Flask `members.scope_dimensions` mirror consume on save. The axis-vs-value GATE that
 * decides WHETHER to run this is pinned in classifyScopeChange.test.ts (10 tests); the EDITOR WIRING
 * (two-call order, atomic axis refusal, mirror resync) is pinned in MembersConfigEditor.test.tsx.
 * These pin the DERIVATION itself — Property 5's "config#scope == the field's option values":
 *
 *  - the field editor is the SINGLE authoring surface: the dimension VALUES are the field's own
 *    option values, never a second independently-authored list (Req 4.1);
 *  - only `scope.enabled` fields become dimensions; a plain enum is skipped (Req 4.2);
 *  - the derived set is what the two-call save mirrors to both planes (Req 4.2).
 */
import { describe, it, expect } from 'vitest';
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import { deriveScopeDimensions } from './deriveScopeDimensions';

/** A resolved scope-axis field: `scope.enabled` with rich `{value,label}` options. */
function scopeField(
  key: string,
  values: string[],
  extra: Partial<FieldConfigField> = {},
): FieldConfigField {
  return {
    key,
    type: 'enum',
    scope: { enabled: true },
    options: values.map((v) => ({ value: v, label: { nl: v, en: v } })),
    ...extra,
  } as FieldConfigField;
}

/** A resolved plain (non-scope) enum field. */
function plainField(key: string, values: string[]): FieldConfigField {
  return {
    key,
    type: 'enum',
    options: values.map((v) => ({ value: v })),
  } as FieldConfigField;
}

function cfg(fields: FieldConfigField[]): FieldConfig {
  return { fields } as FieldConfig;
}

describe('deriveScopeDimensions — derive-on-save (Req 4.1/4.2)', () => {
  it('derives ONE dimension per scope-axis field, carrying the field\'s own option VALUES', () => {
    const dims = deriveScopeDimensions(cfg([scopeField('region', ['Noord', 'Zuid', 'Oost'])]));
    expect(dims).toHaveLength(1);
    expect(dims[0].key).toBe('region');
    expect(dims[0].enabled).toBe(true);
    // The dimension VALUES ARE the field's option values — the ONE vocabulary (Property 5).
    expect(dims[0].values).toEqual(['Noord', 'Zuid', 'Oost']);
  });

  it('skips a plain (non-scope) enum field — only scope.enabled fields become dimensions', () => {
    const dims = deriveScopeDimensions(
      cfg([scopeField('region', ['A', 'B']), plainField('status', ['active', 'died'])]),
    );
    // status is a normal enum, NOT a scope axis → it is not a dimension.
    expect(dims.map((d) => d.key)).toEqual(['region']);
  });

  it('skips a field whose scope.enabled is false or absent', () => {
    const offAxis = { key: 'club', type: 'enum', scope: { enabled: false }, options: [{ value: 'x' }] } as FieldConfigField;
    const noScope = plainField('chapter', ['north']);
    const dims = deriveScopeDimensions(cfg([offAxis, noScope]));
    expect(dims).toEqual([]);
  });

  it('a null/empty config yields [] — a valid tenant-wide scope the SAM writer accepts', () => {
    expect(deriveScopeDimensions(null)).toEqual([]);
    expect(deriveScopeDimensions(undefined)).toEqual([]);
    expect(deriveScopeDimensions(cfg([]))).toEqual([]);
  });

  it('a scope axis with NO authored options yields an empty values list (valid, offers nothing yet)', () => {
    const emptyAxis = { key: 'region', type: 'enum', scope: { enabled: true } } as FieldConfigField;
    const dims = deriveScopeDimensions(cfg([emptyAxis]));
    expect(dims).toHaveLength(1);
    expect(dims[0].values).toEqual([]);
  });

  it('accepts bare-string options as well as rich {value,label} entries (both carry the value key)', () => {
    const bareAxis = { key: 'region', type: 'enum', scope: { enabled: true }, options: ['A', 'B'] } as FieldConfigField;
    const dims = deriveScopeDimensions(cfg([bareAxis]));
    expect(dims[0].values).toEqual(['A', 'B']);
  });

  it('de-duplicates option values in option order (keeping first occurrence)', () => {
    const dupAxis = { key: 'region', type: 'enum', scope: { enabled: true }, options: ['A', 'B', 'A', 'C', 'B'] } as FieldConfigField;
    const dims = deriveScopeDimensions(cfg([dupAxis]));
    expect(dims[0].values).toEqual(['A', 'B', 'C']);
  });

  it('drops malformed/blank option entries', () => {
    const messyAxis = {
      key: 'region',
      type: 'enum',
      scope: { enabled: true },
      options: ['A', '  ', { value: '' }, { value: 'B' }, 42, null],
    } as unknown as FieldConfigField;
    const dims = deriveScopeDimensions(cfg([messyAxis]));
    expect(dims[0].values).toEqual(['A', 'B']);
  });

  it('orders multiple dimensions by field key for a stable, diff-friendly set', () => {
    const dims = deriveScopeDimensions(
      cfg([scopeField('region', ['A']), scopeField('age_group', ['young']), scopeField('chapter', ['n'])]),
    );
    expect(dims.map((d) => d.key)).toEqual(['age_group', 'chapter', 'region']);
  });

  it('carries the field label through to the dimension when present', () => {
    const dims = deriveScopeDimensions(
      cfg([scopeField('region', ['A'], { label: { nl: 'Regio', en: 'Region' } })]),
    );
    expect(dims[0].label).toEqual({ nl: 'Regio', en: 'Region' });
  });

  it('carries scope.required_for through to the dimension (the access readers\' roles gate)', () => {
    const dims = deriveScopeDimensions(
      cfg([scopeField('region', ['A'], { scope: { enabled: true, required_for: ['Members_CRUD'] } })]),
    );
    expect((dims[0] as { required_for?: string[] }).required_for).toEqual(['Members_CRUD']);
  });

  it('omits required_for when the field did not author it', () => {
    const dims = deriveScopeDimensions(cfg([scopeField('region', ['A'])]));
    expect((dims[0] as { required_for?: string[] }).required_for).toBeUndefined();
  });

  it('skips a field with no key (cannot key a dimension on it)', () => {
    const keyless = { type: 'enum', scope: { enabled: true }, options: [{ value: 'A' }] } as unknown as FieldConfigField;
    expect(deriveScopeDimensions(cfg([keyless, scopeField('region', ['A'])]))).toHaveLength(1);
  });
});
