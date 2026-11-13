/**
 * Tests for the Members rows-per-page selector constants (membersPageSize.ts).
 * Covers the fixed numeric sizes, the `max` sentinel, and the platform default (R25).
 */

import { describe, it, expect } from 'vitest';
import {
  MEMBERS_FIXED_PAGE_SIZES,
  MEMBERS_PAGE_SIZE_MAX,
  MEMBERS_DEFAULT_PAGE_SIZE,
} from './membersPageSize';

describe('membersPageSize constants', () => {
  it('exposes the fixed numeric sizes in presentation order', () => {
    expect(MEMBERS_FIXED_PAGE_SIZES).toEqual([50, 100, 250, 500]);
  });

  it('exposes the max sentinel as a distinct option', () => {
    expect(MEMBERS_PAGE_SIZE_MAX).toBe('max');
    expect(MEMBERS_FIXED_PAGE_SIZES).not.toContain('max');
  });

  it('defaults to the platform fallback 50 (no tenant default, R25.9)', () => {
    expect(MEMBERS_DEFAULT_PAGE_SIZE).toBe(50);
    expect(MEMBERS_FIXED_PAGE_SIZES).toContain(MEMBERS_DEFAULT_PAGE_SIZE);
  });
});
