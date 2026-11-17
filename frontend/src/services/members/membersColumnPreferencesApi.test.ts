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
  it('maps a stored record, filtering non-string columns', async () => {
    api.getJson.mockResolvedValue({
      sub: 's1',
      columns: ['a', '', 3, 'b'],
      updated_at: 'T',
    });
    await expect(getColumnPreferences()).resolves.toEqual({
      sub: 's1',
      columns: ['a', 'b'],
      updated_at: 'T',
    });
    expect(api.getJson).toHaveBeenCalledWith('/members/column-preferences');
  });

  it('falls back to safe defaults for a malformed/absent record', async () => {
    api.getJson.mockResolvedValue({ columns: 'nope', sub: 5, updated_at: 7 });
    await expect(getColumnPreferences()).resolves.toEqual({
      sub: '',
      columns: [],
      updated_at: '',
    });
  });
});

describe('saveColumnPreferences', () => {
  it('PUTs { columns } and maps the returned record', async () => {
    api.putJson.mockResolvedValue({
      sub: 's',
      columns: ['a'],
      updated_at: 'T',
    });
    await expect(saveColumnPreferences(['a'])).resolves.toEqual({
      sub: 's',
      columns: ['a'],
      updated_at: 'T',
    });
    expect(api.putJson).toHaveBeenCalledWith('/members/column-preferences', { columns: ['a'] });
  });
});
