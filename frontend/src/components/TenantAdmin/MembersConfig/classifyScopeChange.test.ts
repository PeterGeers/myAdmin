/**
 * Unit tests for the AXIS-vs-VALUE scope gate (spec 03b BU-6, task 6.2, Req 4.3/4.5/4.6).
 *
 * The gate decides, from the baseline→working overlay diff, whether a scope edit is a routine
 * VALUE change (auto-apply on both planes) or a structural SCOPE-AXIS change (atomic refusal +
 * SysAdmin-project message). These pin the three outcomes and the "axis dominates a mixed write"
 * rule that keeps the two planes from diverging.
 */
import { describe, it, expect } from 'vitest';
import type { MembersConfigValue } from '../../../types/membersConfig';
import { classifyScopeChange } from './classifyScopeChange';

/** A scope-axis field entry with the given option values. */
function scopeField(values: string[]): MembersConfigValue {
  return {
    type: 'string',
    scope: { enabled: true },
    options: values.map((v) => ({ value: v, label: { nl: v, en: v } })),
  } as MembersConfigValue;
}

/** A non-scope field entry (plain enum). */
function plainField(values: string[]): MembersConfigValue {
  return {
    type: 'string',
    options: values.map((v) => ({ value: v })),
  } as MembersConfigValue;
}

function overlay(fields: Record<string, MembersConfigValue>, fixed: Record<string, MembersConfigValue> = {}): MembersConfigValue {
  return { fields, fixed_overrides: fixed } as MembersConfigValue;
}

describe('classifyScopeChange — axis-vs-value gate', () => {
  it('returns "none" when no scope-axis field changed', () => {
    const base = overlay({ region: scopeField(['A', 'B']), club: plainField(['x']) });
    const next = overlay({ region: scopeField(['A', 'B']), club: plainField(['x', 'y']) });
    // club is NOT a scope axis — its value change is not a scope change.
    expect(classifyScopeChange(base, next)).toBe('none');
  });

  it('returns "value" when a scope-axis field ADDS an option value (same axis set)', () => {
    const base = overlay({ region: scopeField(['A', 'B']) });
    const next = overlay({ region: scopeField(['A', 'B', 'C']) });
    expect(classifyScopeChange(base, next)).toBe('value');
  });

  it('returns "value" when a scope-axis field REMOVES an option value (same axis set)', () => {
    const base = overlay({ region: scopeField(['A', 'B', 'C']) });
    const next = overlay({ region: scopeField(['A', 'B']) });
    expect(classifyScopeChange(base, next)).toBe('value');
  });

  it('returns "axis" when a NEW field becomes a scope axis', () => {
    const base = overlay({ region: scopeField(['A']) });
    const next = overlay({ region: scopeField(['A']), age_group: scopeField(['young']) });
    expect(classifyScopeChange(base, next)).toBe('axis');
  });

  it('returns "axis" when scope is turned OFF (axis set shrinks to empty)', () => {
    const base = overlay({ region: scopeField(['A', 'B']) });
    // region no longer a scope axis (scope.enabled flipped off → plain enum).
    const next = overlay({ region: plainField(['A', 'B']) });
    expect(classifyScopeChange(base, next)).toBe('axis');
  });

  it('returns "axis" when the scope axis moves to a DIFFERENT field', () => {
    const base = overlay({ region: scopeField(['A']) });
    const next = overlay({ region: plainField(['A']), chapter: scopeField(['north']) });
    expect(classifyScopeChange(base, next)).toBe('axis');
  });

  it('AXIS DOMINATES a mixed edit: an axis change + a value change classifies as "axis"', () => {
    const base = overlay({ region: scopeField(['A', 'B']) });
    // region values changed AND a second axis was enabled — the structural change wins so the
    // two planes never diverge on a half-applied mixed write.
    const next = overlay({ region: scopeField(['A', 'B', 'C']), age_group: scopeField(['young']) });
    expect(classifyScopeChange(base, next)).toBe('axis');
  });

  it('detects scope-axis fields authored under fixed_overrides (dotted key → bare identity)', () => {
    const base = overlay({}, { 'personal.region': scopeField(['A']) });
    const next = overlay({}, { 'personal.region': scopeField(['A', 'B']) });
    // same bare axis key `region`, only values changed → "value".
    expect(classifyScopeChange(base, next)).toBe('value');
  });

  it('treats an empty/absent overlay on both sides as "none"', () => {
    expect(classifyScopeChange(null, null)).toBe('none');
    expect(classifyScopeChange({}, {})).toBe('none');
  });

  it('value order does not matter — reordering the same option set is "none"', () => {
    const base = overlay({ region: scopeField(['A', 'B', 'C']) });
    const next = overlay({ region: scopeField(['C', 'A', 'B']) });
    expect(classifyScopeChange(base, next)).toBe('none');
  });
});
