/**
 * Tests for tripService — request shaping (filter → query params, id-scoped
 * endpoints, multipart import), blob export, and the error branch on export.
 * apiService is mocked.
 */

import { vi } from 'vitest';
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedRequest,
  authenticatedFormData,
} from './apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getTrips,
  createTrip,
  updateTrip,
  cancelTrip,
  getTripHistory,
  getUnbilledTrips,
  getTripSummary,
  exportTrips,
  createGapFill,
  importTrips,
  commitImport,
  getGaps,
} from './tripService';

// Keep the real buildEndpoint (pure URL helper); stub only the network fns.
vi.mock('./apiService', async () => {
  const actual = await vi.importActual<typeof import('./apiService')>('./apiService');
  return {
    ...actual,
    authenticatedGet: vi.fn(),
    authenticatedPost: vi.fn(),
    authenticatedPut: vi.fn(),
    authenticatedRequest: vi.fn(),
    authenticatedFormData: vi.fn(),
  };
});
const mockGet = vi.mocked(authenticatedGet);
const mockPost = vi.mocked(authenticatedPost);
const mockPut = vi.mocked(authenticatedPut);
const mockRequest = vi.mocked(authenticatedRequest);
const mockFormData = vi.mocked(authenticatedFormData);

describe('tripService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getTrips without filters hits the bare base endpoint', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));
    await getTrips();
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/trips');
  });

  it('getTrips serialises filters into query params and skips null/undefined', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));

    await getTrips({ vehicle_id: 3, category: 'zakelijk', year: undefined } as never);

    const url = String(mockGet.mock.calls[0][0]);
    expect(url).toContain('/api/zzp/trips?');
    expect(url).toContain('vehicle_id=3');
    expect(url).toContain('category=zakelijk');
    expect(url).not.toContain('year=');
  });

  it('createTrip POSTs the payload to the base endpoint', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true, data: { id: 1 } } }));
    await createTrip({ start_km: 100 } as never);
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/trips', { start_km: 100 });
  });

  it('updateTrip PUTs to the id-scoped endpoint', async () => {
    mockPut.mockResolvedValue(createMockResponse({ body: { success: true, data: { id: 2 } } }));
    await updateTrip(2, { correction_reason: 'typo' } as never);
    expect(mockPut).toHaveBeenCalledWith('/api/zzp/trips/2', { correction_reason: 'typo' });
  });

  it('cancelTrip DELETEs with the cancel reason in the body', async () => {
    mockRequest.mockResolvedValue(createMockResponse({ body: { success: true } }));
    await cancelTrip(5, 'duplicate');
    expect(mockRequest).toHaveBeenCalledWith('/api/zzp/trips/5', {
      method: 'DELETE',
      body: JSON.stringify({ cancel_reason: 'duplicate' }),
    });
  });

  it('getTripHistory GETs the history sub-resource', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));
    await getTripHistory(8);
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/trips/8/history');
  });

  it('getUnbilledTrips scopes by contact_id', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));
    await getUnbilledTrips(11);
    const url = String(mockGet.mock.calls[0][0]);
    expect(url).toContain('/api/zzp/trips/unbilled?');
    expect(url).toContain('contact_id=11');
  });

  it('getTripSummary passes vehicle_id and year', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: {} } }));
    await getTripSummary(3, 2025);
    const url = String(mockGet.mock.calls[0][0]);
    expect(url).toContain('vehicle_id=3');
    expect(url).toContain('year=2025');
  });

  it('exportTrips returns a blob on success', async () => {
    const blob = new Blob(['pdf']);
    const resp = createMockResponse({ ok: true, body: {} });
    resp.blob = async () => blob;
    mockGet.mockResolvedValue(resp);

    const result = await exportTrips(3, 2025, 'pdf');

    expect(result).toBe(blob);
    const url = String(mockGet.mock.calls[0][0]);
    expect(url).toContain('format=pdf');
  });

  it('exportTrips throws with the backend error when the response is not ok', async () => {
    mockGet.mockResolvedValue(
      createMockResponse({ ok: false, status: 500, body: { error: 'export broke' } }),
    );
    await expect(exportTrips(1, 2025, 'csv')).rejects.toThrow('export broke');
  });

  it('createGapFill POSTs to the gap-fill endpoint', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true, data: { id: 1 } } }));
    await createGapFill({ start_odometer: 1, end_odometer: 2 } as never);
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/trips/gap-fill', { start_odometer: 1, end_odometer: 2 });
  });

  it('importTrips sends a multipart form with the file and vehicle_id', async () => {
    mockFormData.mockResolvedValue(createMockResponse({ body: { success: true, data: {} } }));
    const file = new File(['a,b'], 'trips.csv', { type: 'text/csv' });

    await importTrips(file, 3);

    expect(mockFormData).toHaveBeenCalledWith('/api/zzp/trips/import', expect.any(FormData));
    const fd = mockFormData.mock.calls[0][1] as FormData;
    expect(fd.get('file')).toBe(file);
    expect(fd.get('vehicle_id')).toBe('3');
  });

  it('commitImport POSTs vehicle_id and column mapping', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true } }));
    await commitImport(3, { date: 'A', start_km: 'B' });
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/trips/import/commit', {
      vehicle_id: 3,
      column_mapping: { date: 'A', start_km: 'B' },
    });
  });

  it('getGaps GETs the gaps endpoint', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));
    await getGaps();
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/trips/gaps');
  });

  it('propagates rejected apiService calls (error handling)', async () => {
    mockGet.mockRejectedValue(new Error('offline'));
    await expect(getTrips()).rejects.toThrow('offline');
  });
});
