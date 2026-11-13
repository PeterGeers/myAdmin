/**
 * Focused unit tests for membersColumnPreferencesApi.ts - the raw->typed
 * preference mapper (the API client is mocked; no network).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const api = vi.hoisted(() => ({ getJson: vi.fn(), putJson: vi.fn() }));
vi.mock('./membersApiClient', () => ({
  getJson: api.getJson,
  putJson: api.putJson,
  unwrapData: (payload: unknown) => payload,
}));

import { getColumnPreferences, saveColumnPreferences } from './membersColumnPreferencesApi';

beforeEach(() => {
  api.getJson.mockReset();
  api.putJson.mockReset();
});

describe('getColumnPreferences', () => {
  it('maps a stored record, filtering non-string columns and keeping a finite page_size', async () => {
    api.getJson.mockResolvedValue({
      sub: 's1',
      columns: ['a', '', 3, 'b'],
      page_size: 100,
      updated_at: 'T',
    });
    await expect(getColumnPreferences()).resolves.toEqual({
      sub: 's1',
      columns: ['a', 'b'],
      page_size: 100,
      updated_at: 'T',
    });
    expect(api.getJson).toHaveBeenCalledWith('/members/column-preferences');
  });

  it('falls back to safe defaults for a malformed/absent record', async () => {
    api.getJson.mockResolvedValue({ columns: 'nope', page_size: 'x', sub: 5, updated_at: 7 });
    await expect(getColumnPreferences()).resolves.toEqual({
      sub: '',
      columns: [],
      page_size: null,
      updated_at: '',
    });
  });

  it('maps a non-finite page_size to null', async () => {
    api.getJson.mockResolvedValue({ columns: [], page_size: Number.NaN });
    await expect(getColumnPreferences()).resolves.toMatchObject({ page_size: null });
    api.getJson.mockResolvedValue({ columns: [], page_size: Number.POSITIVE_INFINITY });
    await expect(getColumnPreferences()).resolves.toMatchObject({ page_size: null });
  });
});

describe('saveColumnPreferences', () => {
  it('PUTs { columns } and maps the returned record', async () => {
    api.putJson.mockResolvedValue({
      sub: 's',
      columns: ['a'],
      page_size: 250,
      updated_at: 'T',
    });
    await expect(saveColumnPreferences(['a'])).resolves.toEqual({
      sub: 's',
      columns: ['a'],
      page_size: 250,
      updated_at: 'T',
    });
    expect(api.putJson).toHaveBeenCalledWith('/members/column-preferences', { columns: ['a'] });
  });
});
