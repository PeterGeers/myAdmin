/**
 * Tests for the Members Overview shared model (membersOverviewModel.ts).
 *
 * Covers:
 *  - resolveLabel delegation to the shared resolver with the 'nl-first'
 *    (checklist/analytics) order: active-locale → nl → en → fallback, with a
 *    non-empty plain string passed through and a falsy label → fallback.
 *  - the exported model constants (compact keys / fixed-column i18n map /
 *    initial filters) staying in sync with each other.
 *
 * Pure logic — no network, no React, no mocks. These pin the behaviour the
 * page and the overview hooks depend on after the task-1 label consolidation.
 */

import { describe, it, expect } from 'vitest';
import type { LocalizedLabel } from '../../../types/members';
import {
  resolveLabel,
  COMPACT_FIELD_KEYS,
  MEMBER_NUMBER_KEY,
  FIXED_COLUMN_LABEL_KEYS,
  INITIAL_FILTERS,
} from './membersOverviewModel';

describe('membersOverviewModel.resolveLabel', () => {
  const label: LocalizedLabel = { nl: 'Naam', en: 'Name' };

  it('returns the active-language label when present', () => {
    expect(resolveLabel(label, 'nl', 'key')).toBe('Naam');
    expect(resolveLabel(label, 'en', 'key')).toBe('Name');
  });

  it('falls back nl-first when the active locale is missing (checklist order)', () => {
    // active locale 'fr' absent → nl preferred over en (nl-first order)
    expect(resolveLabel(label, 'fr', 'key')).toBe('Naam');
  });

  it('falls back to en when nl is absent and active locale is missing', () => {
    expect(resolveLabel({ en: 'Name' }, 'fr', 'key')).toBe('Name');
  });

  it('falls back to the provided key when no locale resolves', () => {
    expect(resolveLabel({}, 'nl', 'the.key')).toBe('the.key');
  });

  it('passes a non-empty plain string through verbatim', () => {
    expect(resolveLabel('Plain', 'nl', 'key')).toBe('Plain');
  });

  it('returns the fallback for an undefined or empty-string label', () => {
    expect(resolveLabel(undefined, 'nl', 'fallback')).toBe('fallback');
    expect(resolveLabel('', 'nl', 'fallback')).toBe('fallback');
  });
});

describe('membersOverviewModel constants', () => {
  it('member_number leads the compact columns and matches MEMBER_NUMBER_KEY', () => {
    expect(COMPACT_FIELD_KEYS[0]).toBe('member_number');
    expect(MEMBER_NUMBER_KEY).toBe('member_number');
    expect(COMPACT_FIELD_KEYS[0]).toBe(MEMBER_NUMBER_KEY);
  });

  it('every compact field key has a legacy i18n label and an initial filter slot', () => {
    for (const key of COMPACT_FIELD_KEYS) {
      expect(FIXED_COLUMN_LABEL_KEYS[key]).toBeTruthy();
      expect(INITIAL_FILTERS[key]).toBe('');
    }
  });

  it('region is a filterable fixed column even though it is not a compact key', () => {
    // region is label-mapped and filter-initialised but not in the always-visible set
    expect(FIXED_COLUMN_LABEL_KEYS.region).toBe('filters.region');
    expect(INITIAL_FILTERS.region).toBe('');
    expect(COMPACT_FIELD_KEYS as readonly string[]).not.toContain('region');
  });

  it('INITIAL_FILTERS starts every filter blank', () => {
    expect(Object.values(INITIAL_FILTERS).every(v => v === '')).toBe(true);
  });
});
