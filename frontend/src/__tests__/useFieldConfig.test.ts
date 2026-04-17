/**
 * Tests for useFieldConfig hook logic.
 * Tests the isVisible/isRequired helpers directly since Chakra UI
 * component rendering is complex to mock in this project.
 */
import { renderHook, waitFor } from '@testing-library/react';
import { useFieldConfig } from '../hooks/useFieldConfig';

jest.mock('../services/fieldConfigService', () => ({
  getFieldConfig: jest.fn(),
}));

import { getFieldConfig } from '../services/fieldConfigService';

describe('useFieldConfig', () => {
  beforeEach(() => jest.clearAllMocks());

  it('returns loading true initially', () => {
    (getFieldConfig as jest.Mock).mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useFieldConfig('contacts'));
    expect(result.current.loading).toBe(true);
  });

  it('loads config and exposes isVisible/isRequired', async () => {
    (getFieldConfig as jest.Mock).mockResolvedValue({
      success: true,
      data: { client_id: 'required', vat_number: 'hidden', phone: 'optional' },
    });

    const { result } = renderHook(() => useFieldConfig('contacts'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.isRequired('client_id')).toBe(true);
    expect(result.current.isRequired('phone')).toBe(false);
    expect(result.current.isVisible('client_id')).toBe(true);
    expect(result.current.isVisible('vat_number')).toBe(false);
    expect(result.current.isVisible('phone')).toBe(true);
  });

  it('sets error on failed response', async () => {
    (getFieldConfig as jest.Mock).mockResolvedValue({
      success: false,
      error: 'Not found',
    });

    const { result } = renderHook(() => useFieldConfig('products'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Not found');
  });

  it('sets error on exception', async () => {
    (getFieldConfig as jest.Mock).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useFieldConfig('invoices'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Failed to load field config');
  });
});
