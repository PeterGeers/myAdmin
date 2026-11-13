/**
 * Focused unit tests for memberPivotViewsHelpers.ts - the pure option-value /
 * aggregate-name parsing and the saved-set config resolution (API mocked).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const api = vi.hoisted(() => ({ getAnalyticsSet: vi.fn() }));
vi.mock('../../../services/membersApiService', () => ({
  getAnalyticsSet: api.getAnalyticsSet,
}));

import {
  MODEL_PREFIX,
  SET_PREFIX,
  optionValueToRef,
  parseAggregateName,
  resolveConfig,
  type SelectableSet,
} from './memberPivotViewsHelpers';
import type { PivotConfig } from '../../../types/pivot';

const set = (over: Partial<SelectableSet> = {}): SelectableSet => ({
  optionValue: 'model:x',
  label: 'X',
  source: 'model',
  ...over,
});

describe('optionValueToRef', () => {
  it('converts a model: option value into a set: ref', () => {
    expect(MODEL_PREFIX).toBe('model:');
    expect(SET_PREFIX).toBe('set:');
    expect(optionValueToRef('model:abc')).toBe('set:abc');
  });

  it('returns null for any non-model option value', () => {
    expect(optionValueToRef('set:abc')).toBeNull();
    expect(optionValueToRef('preset:x')).toBeNull();
    expect(optionValueToRef('')).toBeNull();
  });
});

describe('parseAggregateName', () => {
  it('parses an upper-case FUNC(column) expression into fn + inner', () => {
    expect(parseAggregateName('SUM(age)')).toEqual({ fn: 'SUM', inner: 'age' });
    expect(parseAggregateName('COUNT(*)')).toEqual({ fn: 'COUNT', inner: '*' });
  });

  it('returns null for a plain key or a malformed expression', () => {
    expect(parseAggregateName('region')).toBeNull();
    expect(parseAggregateName('sum(age)')).toBeNull();
    expect(parseAggregateName('SUM age')).toBeNull();
    expect(parseAggregateName('')).toBeNull();
  });
});

describe('resolveConfig', () => {
  beforeEach(() => api.getAnalyticsSet.mockReset());

  it('fetches and returns the saved set definition when a modelId is present', async () => {
    const definition = { groupColumns: ['a'] } as unknown as PivotConfig;
    api.getAnalyticsSet.mockResolvedValue({ definition });
    await expect(resolveConfig(set({ modelId: 'x' }))).resolves.toBe(definition);
    expect(api.getAnalyticsSet).toHaveBeenCalledWith('x');
  });

  it('returns undefined and skips the API call when there is no modelId', async () => {
    await expect(resolveConfig(set())).resolves.toBeUndefined();
    expect(api.getAnalyticsSet).not.toHaveBeenCalled();
  });
});
