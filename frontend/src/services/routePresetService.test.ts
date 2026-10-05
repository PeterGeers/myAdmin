/**
 * Tests for routePresetService — request shaping (endpoint + method + body)
 * and response passthrough. apiService is mocked.
 */

import { vi } from 'vitest';
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedRequest,
} from './apiService';
import {
  getRoutePresets,
  createRoutePreset,
  updateRoutePreset,
  deleteRoutePreset,
} from './routePresetService';
import { createMockResponse } from '@/test-utils/mockHelpers';

// Keep the real buildEndpoint (pure URL helper); stub only the network fns.
vi.mock('./apiService', async () => {
  const actual = await vi.importActual<typeof import('./apiService')>('./apiService');
  return {
    ...actual,
    authenticatedGet: vi.fn(),
    authenticatedPost: vi.fn(),
    authenticatedPut: vi.fn(),
    authenticatedRequest: vi.fn(),
  };
});
const mockGet = vi.mocked(authenticatedGet);
const mockPost = vi.mocked(authenticatedPost);
const mockPut = vi.mocked(authenticatedPut);
const mockRequest = vi.mocked(authenticatedRequest);

describe('routePresetService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getRoutePresets GETs the base endpoint and returns the parsed body', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [{ id: 1 }] } }));

    const result = await getRoutePresets();

    expect(mockGet).toHaveBeenCalledWith('/api/zzp/route-presets');
    expect(result).toEqual({ success: true, data: [{ id: 1 }] });
  });

  it('createRoutePreset POSTs the payload to the base endpoint', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true, data: { id: 2 } } }));
    const payload = { from_address: 'Home → Office' };

    const result = await createRoutePreset(payload);

    expect(mockPost).toHaveBeenCalledWith('/api/zzp/route-presets', payload);
    expect(result.data).toEqual({ id: 2 });
  });

  it('updateRoutePreset PUTs to the id-scoped endpoint', async () => {
    mockPut.mockResolvedValue(createMockResponse({ body: { success: true, data: { id: 7 } } }));

    await updateRoutePreset(7, { from_address: 'x' });

    expect(mockPut).toHaveBeenCalledWith('/api/zzp/route-presets/7', { from_address: 'x' });
  });

  it('deleteRoutePreset issues a DELETE request to the id-scoped endpoint', async () => {
    mockRequest.mockResolvedValue(createMockResponse({ body: { success: true } }));

    const result = await deleteRoutePreset(9);

    expect(mockRequest).toHaveBeenCalledWith('/api/zzp/route-presets/9', { method: 'DELETE' });
    expect(result.success).toBe(true);
  });

  it('propagates rejected apiService calls (error handling)', async () => {
    mockGet.mockRejectedValue(new Error('network'));
    await expect(getRoutePresets()).rejects.toThrow('network');
  });
});
