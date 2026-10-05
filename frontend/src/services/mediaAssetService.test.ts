/**
 * Tests for mediaAssetService — request shaping (incl. search query params),
 * result.data unwrapping, and the HTTP-error → thrown Error branches.
 * apiService is mocked.
 */

import { vi } from 'vitest';
import { authenticatedGet, authenticatedPost, authenticatedPut } from './apiService';
import {
  fetchAssetDashboard,
  triggerScan,
  fetchDeletionEligible,
  approveDeletion,
  fetchUnregistered,
  importUnregistered,
  deleteUnregistered,
  fetchRetentionSettings,
  updateRetentionSettings,
  fetchDuplicates,
  mergeDuplicates,
} from './mediaAssetService';
import { createMockResponse } from '@/test-utils/mockHelpers';

// Keep the real buildEndpoint (pure URL helper); stub only the network fns.
vi.mock('./apiService', async () => {
  const actual = await vi.importActual<typeof import('./apiService')>('./apiService');
  return {
    ...actual,
    authenticatedGet: vi.fn(),
    authenticatedPost: vi.fn(),
    authenticatedPut: vi.fn(),
  };
});
const mockGet = vi.mocked(authenticatedGet);
const mockPost = vi.mocked(authenticatedPost);
const mockPut = vi.mocked(authenticatedPut);

describe('mediaAssetService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('fetchAssetDashboard unwraps result.data', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { data: { total: 5 } } }));
    const result = await fetchAssetDashboard();
    expect(mockGet).toHaveBeenCalledWith('/api/media-assets/dashboard');
    expect(result).toEqual({ total: 5 });
  });

  it('fetchAssetDashboard throws the backend error on a non-ok response', async () => {
    mockGet.mockResolvedValue(
      createMockResponse({ ok: false, status: 403, body: { error: 'denied' } }),
    );
    await expect(fetchAssetDashboard()).rejects.toThrow('denied');
  });

  it('fetchAssetDashboard throws HTTP status when the error body cannot be parsed', async () => {
    const resp = createMockResponse({ ok: false, status: 502 });
    resp.json = async () => {
      throw new Error('bad json');
    };
    mockGet.mockResolvedValue(resp);
    await expect(fetchAssetDashboard()).rejects.toThrow('HTTP 502');
  });

  it('triggerScan POSTs an empty body and returns the scan id', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { scan_id: 'scan_1' } }));
    const result = await triggerScan();
    expect(mockPost).toHaveBeenCalledWith('/api/media-assets/scan', {});
    expect(result.scan_id).toBe('scan_1');
  });

  it('fetchDeletionEligible builds search query params with status + pagination', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: [] } }));
    await fetchDeletionEligible(2, 50);
    const url = String(mockGet.mock.calls[0][0]);
    expect(url).toContain('/api/media-assets/search?');
    expect(url).toContain('status=DELETION_ELIGIBLE');
    expect(url).toContain('page=2');
    expect(url).toContain('page_size=50');
  });

  it('approveDeletion POSTs the asset_ids payload', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { deleted: 2 } }));
    await approveDeletion(['a1', 'a2']);
    expect(mockPost).toHaveBeenCalledWith('/api/media-assets/approve-delete', {
      asset_ids: ['a1', 'a2'],
    });
  });

  it('fetchUnregistered unwraps result.data', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { data: [{ key: 'x' }] } }));
    const result = await fetchUnregistered();
    expect(result).toEqual([{ key: 'x' }]);
  });

  it('importUnregistered POSTs the s3_keys payload', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { imported: 1 } }));
    await importUnregistered(['k1']);
    expect(mockPost).toHaveBeenCalledWith('/api/media-assets/import', { s3_keys: ['k1'] });
  });

  it('deleteUnregistered POSTs the s3_keys payload', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { deleted: 1 } }));
    await deleteUnregistered(['k2']);
    expect(mockPost).toHaveBeenCalledWith('/api/media-assets/delete-unregistered', {
      s3_keys: ['k2'],
    });
  });

  it('fetchRetentionSettings unwraps result.data', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { data: { invoices: 365 } } }));
    const result = await fetchRetentionSettings();
    expect(mockGet).toHaveBeenCalledWith('/api/media-assets/retention-settings');
    expect(result).toEqual({ invoices: 365 });
  });

  it('updateRetentionSettings PUTs the overrides map', async () => {
    mockPut.mockResolvedValue(createMockResponse({ body: { updated: ['invoices'] } }));
    await updateRetentionSettings({ invoices: 730 });
    expect(mockPut).toHaveBeenCalledWith('/api/media-assets/retention-settings', { invoices: 730 });
  });

  it('fetchDuplicates unwraps result.data', async () => {
    mockGet.mockResolvedValue(createMockResponse({ body: { data: [{ hash: 'h1' }] } }));
    const result = await fetchDuplicates();
    expect(result).toEqual([{ hash: 'h1' }]);
  });

  it('mergeDuplicates POSTs keep + duplicate ids and returns the raw result', async () => {
    mockPost.mockResolvedValue(
      createMockResponse({ body: { references_moved: 3, duplicates_deleted: 2 } }),
    );
    const result = await mergeDuplicates('keep1', ['dup1', 'dup2']);
    expect(mockPost).toHaveBeenCalledWith('/api/media-assets/merge-duplicates', {
      keep_asset_id: 'keep1',
      duplicate_asset_ids: ['dup1', 'dup2'],
    });
    expect(result.duplicates_deleted).toBe(2);
  });

  it('propagates rejected apiService calls (error handling)', async () => {
    mockPost.mockRejectedValue(new Error('offline'));
    await expect(approveDeletion(['a'])).rejects.toThrow('offline');
  });
});
