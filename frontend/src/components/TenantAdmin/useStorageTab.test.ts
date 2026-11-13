/**
 * Focused tests for useStorageTab.ts - the derived helpers and the logo-asset
 * selection branches (services + toast mocked).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  getParameterSchema: vi.fn(),
  createParameter: vi.fn(),
  authenticatedGet: vi.fn(),
  authenticatedPost: vi.fn(),
  authenticatedFormData: vi.fn(),
}));
vi.mock('../../services/parameterSchemaService', () => ({
  getParameterSchema: mocks.getParameterSchema,
}));
vi.mock('../../services/parameterService', () => ({ createParameter: mocks.createParameter }));
vi.mock('../../services/apiService', () => ({
  authenticatedGet: mocks.authenticatedGet,
  authenticatedPost: mocks.authenticatedPost,
  authenticatedFormData: mocks.authenticatedFormData,
  buildEndpoint: (path: string) => path,
}));
vi.mock('@/hooks/useDuplicateNotification', () => ({
  useDuplicateNotification: () => ({ notifyDuplicate: vi.fn() }),
}));

import { useStorageTab } from './useStorageTab';

type Asset = Parameters<ReturnType<typeof useStorageTab>['handleLogoAssetSelect']>[0];
const asset = (over: Record<string, unknown> = {}): Asset =>
  ({ id: 'asset-1', original_filename: 'logo.png', ...over } as unknown as Asset);

beforeEach(() => {
  mocks.getParameterSchema.mockReset().mockResolvedValue({
    schema: { storage: { params: { invoice_provider: { options: [], current_value: 's3' } } } },
  });
  mocks.createParameter.mockReset();
  mocks.authenticatedGet.mockReset().mockResolvedValue({
    ok: true,
    json: async () => ({ credentials: [], config: {} }),
  });
  mocks.authenticatedPost.mockReset();
  mocks.authenticatedFormData.mockReset();
});

describe('useStorageTab', () => {
  it('formatDate returns N/A for a null date and a locale string otherwise', () => {
    const { result } = renderHook(() => useStorageTab('t1'));
    expect(result.current.formatDate(null)).toBe('N/A');
    const iso = '2026-01-02T03:04:05.000Z';
    expect(result.current.formatDate(iso)).toBe(new Date(iso).toLocaleString());
  });

  it('hasGdCreds is true only when a google_drive credential is present', async () => {
    mocks.authenticatedGet.mockResolvedValue({
      ok: true,
      json: async () => ({
        credentials: [{ type: 'google_drive_credentials', created_at: null, updated_at: null }],
        config: {},
      }),
    });
    const { result } = renderHook(() => useStorageTab('t1'));
    await waitFor(() => expect(result.current.hasGdCreds).toBe(true));
  });

  it('handleLogoAssetSelect derives the S3 key from a presigned_url', () => {
    const { result } = renderHook(() => useStorageTab('t1'));
    act(() =>
      result.current.handleLogoAssetSelect(
        asset({ presigned_url: 'https://bucket.s3.amazonaws.com/uploads/logo.png' }),
      ),
    );
    expect(result.current.logoS3Key).toBe('uploads/logo.png');
  });

  it('handleLogoAssetSelect falls back to the asset id when the url is absent or unparseable', () => {
    const { result } = renderHook(() => useStorageTab('t1'));
    act(() => result.current.handleLogoAssetSelect(asset()));
    expect(result.current.logoS3Key).toBe('asset-1');

    act(() =>
      result.current.handleLogoAssetSelect(asset({ id: 'asset-2', presigned_url: 'not a url' })),
    );
    expect(result.current.logoS3Key).toBe('asset-2');
  });
});
