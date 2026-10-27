/**
 * fieldValue helper — s5c task 4.1 (design C-SURFACE / C-FIELDS; R5.1, R5.2)
 *
 * The single value-presentation seam the Members surface shares. Verifies:
 * - renderFieldValue honors the field `type` (dates localized; other types
 *   stringified) and never crashes on absent/odd values (→ dash);
 * - isColumnCandidate is the authoritative field-level `visible` gate (R5.1) —
 *   an explicit `visible === false` drops the field, omitted/`true` keeps it;
 * - isReadOnlyField marks calculated (derived) fields read-only (R5.2 / R4.4),
 *   so the surface has one definition of "calculated ⇒ read-only".
 *
 * **Validates: Requirements 5.1, 5.2**
 */

import { describe, it, expect } from 'vitest';
import type { FieldConfigField } from '../../types/members';
import {
  renderFieldValue,
  isColumnCandidate,
  isReadOnlyField,
  EMPTY_CELL,
} from './fieldValue';

const field = (over: Partial<FieldConfigField> = {}): FieldConfigField => ({
  key: 'k',
  ...over,
});

describe('fieldValue.renderFieldValue', () => {
  it('stringifies a plain value (parameter-driven overlay field)', () => {
    expect(renderFieldValue(field({ type: 'string' }), 'NL00BANK0123456789', 'nl'))
      .toBe('NL00BANK0123456789');
  });

  it('stringifies a numeric value (e.g. calculated years_member)', () => {
    expect(renderFieldValue(field({ type: 'string', origin: 'calculated' }), 12, 'nl'))
      .toBe('12');
  });

  it('renders the dash placeholder for null/undefined/empty', () => {
    expect(renderFieldValue(field(), null, 'nl')).toBe(EMPTY_CELL);
    expect(renderFieldValue(field(), undefined, 'nl')).toBe(EMPTY_CELL);
    expect(renderFieldValue(field(), '', 'nl')).toBe(EMPTY_CELL);
  });

  it('formats a date-typed value (fixed birth_date / overlay signature_date)', () => {
    // date-fns 'P' for nl is DD-MM-YYYY; assert the parts are present so the
    // test is locale-format-robust (not tied to a separator/TZ nuance).
    const out = renderFieldValue(field({ type: 'date' }), '2000-01-15', 'nl');
    expect(out).toContain('2000');
    expect(out).toContain('01');
    expect(out).toContain('15');
    // A localized date is NOT the raw ISO string.
    expect(out).not.toBe('2000-01-15');
  });

  it('falls back to the raw string for an unparseable date value', () => {
    expect(renderFieldValue(field({ type: 'date' }), 'not-a-date', 'nl'))
      .toBe('not-a-date');
  });

  describe('enum/reference value → localized label (status column bug)', () => {
    const statusField = (): FieldConfigField => field({
      key: 'status',
      type: 'enum',
      options: [
        { value: 'active', label: { nl: 'Actief', en: 'Active' } },
        { value: 'inactive', label: { nl: 'Inactief', en: 'Inactive' } },
      ],
    });

    it('resolves the stored key to its label for the active locale', () => {
      expect(renderFieldValue(statusField(), 'active', 'nl')).toBe('Actief');
      expect(renderFieldValue(statusField(), 'active', 'en')).toBe('Active');
      expect(renderFieldValue(statusField(), 'inactive', 'nl')).toBe('Inactief');
    });

    it('falls back to en then nl when the active locale label is missing', () => {
      const f = field({
        key: 'status',
        type: 'enum',
        options: [{ value: 'active', label: { en: 'Active', nl: 'Actief' } }],
      });
      // de is absent → en wins (en before nl).
      expect(renderFieldValue(f, 'active', 'de')).toBe('Active');
    });

    it('falls back to the raw value when no option matches the stored key', () => {
      expect(renderFieldValue(statusField(), 'archived', 'nl')).toBe('archived');
    });

    it('returns the raw value for a bare string[] options list (value IS its own label)', () => {
      const f = field({ key: 'status', type: 'enum', options: ['active', 'inactive'] });
      expect(renderFieldValue(f, 'active', 'nl')).toBe('active');
    });

    it('returns the raw value for an enum field with no options', () => {
      expect(renderFieldValue(field({ key: 'status', type: 'enum' }), 'active', 'nl'))
        .toBe('active');
    });

    it('uses the option value as the label fallback when the matched option has no label', () => {
      const f = field({ key: 'status', type: 'enum', options: [{ value: 'active' }] });
      expect(renderFieldValue(f, 'active', 'nl')).toBe('active');
    });

    it('still renders the dash for an absent enum value', () => {
      expect(renderFieldValue(statusField(), null, 'nl')).toBe(EMPTY_CELL);
      expect(renderFieldValue(statusField(), '', 'nl')).toBe(EMPTY_CELL);
    });
  });
});

describe('fieldValue.isColumnCandidate (R5.1 visibility gate)', () => {
  it('keeps a field with visible omitted or true', () => {
    expect(isColumnCandidate(field())).toBe(true);
    expect(isColumnCandidate(field({ visible: true }))).toBe(true);
  });

  it('drops a field explicitly marked not visible', () => {
    expect(isColumnCandidate(field({ visible: false }))).toBe(false);
  });
});

describe('fieldValue.isReadOnlyField (R5.2 calculated ⇒ read-only)', () => {
  it('marks a calculated field read-only', () => {
    expect(isReadOnlyField(field({ origin: 'calculated' }))).toBe(true);
  });

  it('does not mark fixed / variable fields read-only', () => {
    expect(isReadOnlyField(field({ origin: 'fixed' }))).toBe(false);
    expect(isReadOnlyField(field({ origin: 'variable' }))).toBe(false);
    expect(isReadOnlyField(field())).toBe(false);
  });
});
