/**
 * Tests for vehicleService — request shaping (incl. is_active query param) and
 * response passthrough. apiService is mocked.
 */

import { vi } from 'vitest';
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedRequest,
} from './apiService';
import {
  getVehicles,
  createVehicle,
  updateVehicle,
  deactivateVehicle,
} from './vehicleService';
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

describe('vehicleService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getVehicles without a filter hits the bare base endpoint', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));

    await getVehicles();

    expect(mockGet).toHaveBeenCalledWith('/api/zzp/vehicles');
  });

  it('getVehicles with activeOnly=true appends is_active=true', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));

    await getVehicles(true);

    expect(mockGet).toHaveBeenCalledWith('/api/zzp/vehicles?is_active=true');
  });

  it('getVehicles with activeOnly=false appends is_active=false', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));

    await getVehicles(false);

    expect(mockGet).toHaveBeenCalledWith('/api/zzp/vehicles?is_active=false');
  });

  it('createVehicle POSTs the payload', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true, data: { id: 1 } } }));

    await createVehicle({ license_plate: 'AB-12-CD' });

    expect(mockPost).toHaveBeenCalledWith('/api/zzp/vehicles', { license_plate: 'AB-12-CD' });
  });

  it('updateVehicle PUTs to the id-scoped endpoint', async () => {
    mockPut.mockResolvedValue(createMockResponse({ body: { success: true, data: { id: 4 } } }));

    await updateVehicle(4, { make: 'Van' });

    expect(mockPut).toHaveBeenCalledWith('/api/zzp/vehicles/4', { make: 'Van' });
  });

  it('deactivateVehicle issues a DELETE', async () => {
    mockRequest.mockResolvedValue(createMockResponse({ body: { success: true } }));

    const result = await deactivateVehicle(4);

    expect(mockRequest).toHaveBeenCalledWith('/api/zzp/vehicles/4', { method: 'DELETE' });
    expect(result.success).toBe(true);
  });

  it('propagates rejected apiService calls (error handling)', async () => {
    mockPost.mockRejectedValue(new Error('boom'));
    await expect(createVehicle({})).rejects.toThrow('boom');
  });
});
