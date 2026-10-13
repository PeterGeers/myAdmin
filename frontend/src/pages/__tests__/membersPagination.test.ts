/**
 * Unit tests for the Members table page-size precedence resolver (Members config
 * redesign Phase 2, step (a)).
 *
 * Covers the 4-way (userPreference present/absent × tenantDefault present/absent)
 * matrix of the precedence `userPreference ?? default_page_size ??
 * platformDefault`, plus the positive-integer guarantee (the resolved value is
 * NEVER blank and NEVER zero, mirroring the backend read-side guard). The
 * exhaustive random-input property is task 2.2; this is the focused
 * example/edge-case companion required by the Change-With-Tests contract.
 *
 * **Validates: Requirements 2.2, 2.3, 2.4, 9.4**
 */

import { describe, it, expect } from 'vitest';
import { resolvePageSize, PLATFORM_DEFAULT_PAGE_SIZE } from '../membersPagination';

describe('resolvePageSize — precedence matrix', () => {
  it('userPreference present + tenantDefault present → userPreference wins', () => {
    expect(resolvePageSize(10, 50)).toBe(10);
  });

  it('userPreference present + tenantDefault absent → userPreference wins', () => {
    expect(resolvePageSize(10, null)).toBe(10);
    expect(resolvePageSize(10, undefined)).toBe(10);
  });

  it('userPreference absent + tenantDefault present → tenantDefault wins', () => {
    expect(resolvePageSize(null, 50)).toBe(50);
    expect(resolvePageSize(undefined, 50)).toBe(50);
  });

  it('userPreference absent + tenantDefault absent → platform default', () => {
    expect(resolvePageSize(null, null)).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
    expect(resolvePageSize(undefined, undefined)).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
  });
});

describe('resolvePageSize — positive-int guard (never 0/blank, falls through)', () => {
  it('treats zero as absent and falls through', () => {
    expect(resolvePageSize(0, 50)).toBe(50);
    expect(resolvePageSize(0, 0)).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
  });

  it('treats negatives as absent and falls through', () => {
    expect(resolvePageSize(-5, 50)).toBe(50);
    expect(resolvePageSize(-5, -1)).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
  });

  it('treats non-integers (fractions, NaN, Infinity) as absent and falls through', () => {
    expect(resolvePageSize(12.5, 50)).toBe(50);
    expect(resolvePageSize(Number.NaN, 50)).toBe(50);
    expect(resolvePageSize(Number.POSITIVE_INFINITY, 50)).toBe(50);
    expect(resolvePageSize(10.1, 7.7)).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
  });

  it('always resolves to a positive integer across the whole matrix', () => {
    const candidates = [null, undefined, 0, -3, 12.5, Number.NaN, 25, 50];
    for (const user of candidates) {
      for (const tenant of candidates) {
        const resolved = resolvePageSize(user, tenant);
        expect(Number.isInteger(resolved)).toBe(true);
        expect(resolved).toBeGreaterThan(0);
      }
    }
  });

  it('guards a bad platform default too (total/positive even then)', () => {
    expect(resolvePageSize(null, null, 0)).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
    expect(resolvePageSize(null, null, -1)).toBe(PLATFORM_DEFAULT_PAGE_SIZE);
    expect(resolvePageSize(null, null, 40)).toBe(40);
  });
});
