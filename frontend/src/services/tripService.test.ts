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
import {
  getTrips,
  createTrip,
  updateTrip,
  cancelTrip,
  getTripHistory,
  getTripSummary,
  exportTrips,
  createGapFill,
  importTrips,
  commitImport,
  getGaps,
} from './tripService';
// Import the whole module too, so we can assert the billing surface is absent
// (removed exports can't be named-imported — that would be a compile error).
import * as tripService from './tripService';
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

  it('commitImport POSTs vehicle_id, rows and skip_error_rows', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true } }));
    const rows = [{ _row_number: 1, _status: 'ok', _messages: [] }] as unknown as Parameters<typeof commitImport>[1];
    await commitImport(3, rows, true);
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/trips/import/commit', {
      vehicle_id: 3,
      rows,
      skip_error_rows: true,
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

  // --- Trip-billing surface removal (Req 5.3, 5.4) ---
  describe('trip-billing surface is removed', () => {
    const exported = tripService as Record<string, unknown>;

    it('exposes no getUnbilledTrips operation (Req 5.4)', () => {
      expect(exported.getUnbilledTrips).toBeUndefined();
    });

    it('exposes no invoice-from-trips operation (Req 5.4)', () => {
      // No createInvoiceFromTrips (or any invoice-from-trips) path on the service.
      expect(exported.createInvoiceFromTrips).toBeUndefined();
      const billingNames = Object.keys(exported).filter((name) =>
        /invoice|unbilled|billable|billed|km_?rate/i.test(name),
      );
      expect(billingNames).toEqual([]);
    });

    it('returns no billing-derived rows from a trip retrieval (Req 5.3, 5.4)', async () => {
      // The service passes the backend payload through verbatim; it never
      // synthesises is_billable / km_rate / billing-derived fields.
      mockGet.mockResolvedValue(
        createMockResponse({
          body: {
            success: true,
            data: [{ id: 1, start_km: 100, end_km: 150, category: 'zakelijk' }],
          },
        }),
      );

      const result = await getTrips();

      const serialised = JSON.stringify(result);
      expect(serialised).not.toMatch(/is_billable/);
      expect(serialised).not.toMatch(/km_rate/);
      expect(serialised).not.toMatch(/0\.23/);
      result.data.forEach((row) => {
        const keys = Object.keys(row as unknown as Record<string, unknown>);
        expect(keys).not.toContain('is_billable');
        expect(keys).not.toContain('km_rate');
      });
    });
  });
});
