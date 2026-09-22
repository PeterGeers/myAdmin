/**
 * Tests for the useMemberFieldConfig hook.
 *
 * Mirrors useFieldConfig.test.ts: mocks the data source (here
 * `../services/membersApiService`'s `getFieldConfig`) and asserts the
 * loading -> resolved-config transition plus error handling on a rejected
 * promise (no throw, null config, error string set).
 *
 * _Requirements: R7.6, R7.8_
 */
import { vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useMemberFieldConfig } from '../hooks/useMemberFieldConfig';
import type { FieldConfig } from '../types/members';

vi.mock('../services/membersApiService', () => ({
  getFieldConfig: vi.fn(),
}));

import { getFieldConfig } from '../services/membersApiService';

describe('useMemberFieldConfig', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns loading true initially', () => {
    vi.mocked(getFieldConfig).mockReturnValue(new Promise(() => { })); // never resolves
    const { result } = renderHook(() => useMemberFieldConfig());
    expect(result.current.loading).toBe(true);
    expect(result.current.fieldConfig).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('loads and exposes the resolved field config', async () => {
    const config: FieldConfig = {
      fields: [
        { key: 'name', label: { nl: 'Naam', en: 'Name' }, order: 1, compact: true },
        { key: 'motor_type', label: { nl: 'Motor', en: 'Motorcycle' }, order: 10 },
      ],
      dimensions: [
        { key: 'region', enabled: true, values: ['Noord', 'Zuid'] },
      ],
    };
    vi.mocked(getFieldConfig).mockResolvedValue(config);

    const { result } = renderHook(() => useMemberFieldConfig());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.fieldConfig).toEqual(config);
    expect(result.current.error).toBeNull();
  });

  it('sets null config when the resolved payload is null/undefined', async () => {
    vi.mocked(getFieldConfig).mockResolvedValue(undefined as unknown as FieldConfig);

    const { result } = renderHook(() => useMemberFieldConfig());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.fieldConfig).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('sets error and null config on a rejected promise without throwing', async () => {
    vi.mocked(getFieldConfig).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useMemberFieldConfig());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Failed to load field config');
    expect(result.current.fieldConfig).toBeNull();
  });

  it('refetch re-invokes the service', async () => {
    vi.mocked(getFieldConfig).mockResolvedValue({ fields: [] });

    const { result } = renderHook(() => useMemberFieldConfig());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getFieldConfig).toHaveBeenCalledTimes(1);

    await result.current.refetch();
    expect(getFieldConfig).toHaveBeenCalledTimes(2);
  });
});
