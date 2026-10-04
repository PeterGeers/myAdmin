/**
 * Tests for landingPageApi — slug/draft/publish/version/branding/image-upload
 * request shaping, result unwrapping, and HTTP-error branches. apiService mocked.
 */

import { vi } from 'vitest';
import {
  authenticatedGet,
  authenticatedPut,
  authenticatedPost,
  authenticatedDelete,
  authenticatedFormData,
} from './apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getSlug,
  setSlug,
  validateSlug,
  getDraft,
  saveDraft,
  publishLandingPage,
  unpublishLandingPage,
  getVersions,
  rollbackToVersion,
  getVersionDetail,
  deleteVersion,
  getBrandingSettings,
  saveBrandingSettings,
  uploadImage,
  type Section,
} from './landingPageApi';

vi.mock('./apiService');
const mockGet = vi.mocked(authenticatedGet);
const mockPut = vi.mocked(authenticatedPut);
const mockPost = vi.mocked(authenticatedPost);
const mockDelete = vi.mocked(authenticatedDelete);
const mockFormData = vi.mocked(authenticatedFormData);

describe('landingPageApi', () => {
  beforeEach(() => vi.clearAllMocks());

  describe('slug management', () => {
    it('getSlug GETs the slug endpoint', async () => {
      mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data: { slug: 'me' } } }));
      const result = await getSlug();
      expect(mockGet).toHaveBeenCalledWith('/api/landing/slug');
      expect(result.data.slug).toBe('me');
    });

    it('setSlug PUTs the slug', async () => {
      mockPut.mockResolvedValue(createMockResponse({ body: { success: true, slug: 'me' } }));
      await setSlug('me');
      expect(mockPut).toHaveBeenCalledWith('/api/landing/slug', { slug: 'me' });
    });

    it('validateSlug POSTs the slug to the validate endpoint', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: { valid: true } }));
      const result = await validateSlug('cool');
      expect(mockPost).toHaveBeenCalledWith('/api/landing/slug/validate', { slug: 'cool' });
      expect(result.valid).toBe(true);
    });

    it('getSlug throws the backend error on a non-ok response', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ ok: false, status: 500, statusText: 'err', body: { error: 'slug fail' } }),
      );
      await expect(getSlug()).rejects.toThrow('slug fail');
    });
  });

  describe('draft management', () => {
    it('getDraft GETs the draft endpoint', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ body: { success: true, data: { version: 1, sections: [] } } }),
      );
      await getDraft();
      expect(mockGet).toHaveBeenCalledWith('/api/landing/draft');
    });

    it('saveDraft PUTs sections', async () => {
      mockPut.mockResolvedValue(createMockResponse({ body: { success: true, version: 2 } }));
      const sections = [{ id: 's1', type: 'hero', layout: 'a', properties: {} }] as Section[];
      await saveDraft(sections);
      expect(mockPut).toHaveBeenCalledWith('/api/landing/draft', { sections });
    });
  });

  describe('publishing', () => {
    it('publishLandingPage POSTs to the publish endpoint', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: { success: true, version: 1 } }));
      await publishLandingPage();
      expect(mockPost).toHaveBeenCalledWith('/api/landing/publish');
    });

    it('unpublishLandingPage POSTs to the unpublish endpoint', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: { success: true, message: 'off' } }));
      await unpublishLandingPage();
      expect(mockPost).toHaveBeenCalledWith('/api/landing/unpublish');
    });
  });

  describe('versions', () => {
    it('getVersions unwraps result.data', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ body: { success: true, data: [{ version: 1 }] } }),
      );
      const result = await getVersions();
      expect(result).toEqual([{ version: 1 }]);
    });

    it('getVersions throws when success is false', async () => {
      mockGet.mockResolvedValue(createMockResponse({ body: { success: false, data: [] } }));
      await expect(getVersions()).rejects.toThrow('Failed to load versions');
    });

    it('rollbackToVersion POSTs the version number', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: { success: true, version: 3 } }));
      await rollbackToVersion(3);
      expect(mockPost).toHaveBeenCalledWith('/api/landing/rollback', { version: 3 });
    });

    it('getVersionDetail GETs the version-scoped endpoint and unwraps data', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ body: { success: true, data: { version: 4, sections: [] } } }),
      );
      const result = await getVersionDetail(4);
      expect(mockGet).toHaveBeenCalledWith('/api/landing/version/4');
      expect(result.version).toBe(4);
    });

    it('deleteVersion DELETEs the version-scoped endpoint', async () => {
      mockDelete.mockResolvedValue(createMockResponse({ body: { success: true, message: 'ok' } }));
      await deleteVersion(4);
      expect(mockDelete).toHaveBeenCalledWith('/api/landing/version/4');
    });
  });

  describe('branding settings', () => {
    it('getBrandingSettings unwraps result.data', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ body: { success: true, data: { company_name: 'ACME' } } }),
      );
      const result = await getBrandingSettings();
      expect(result.company_name).toBe('ACME');
    });

    it('getBrandingSettings throws when success is false', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ body: { success: false, error: 'settings fail' } }),
      );
      await expect(getBrandingSettings()).rejects.toThrow('settings fail');
    });

    it('saveBrandingSettings PUTs the partial settings', async () => {
      mockPut.mockResolvedValue(createMockResponse({ body: { success: true } }));
      await saveBrandingSettings({ company_name: 'ACME' });
      expect(mockPut).toHaveBeenCalledWith('/api/landing/branding', { company_name: 'ACME' });
    });

    it('saveBrandingSettings throws when the backend reports failure', async () => {
      mockPut.mockResolvedValue(createMockResponse({ body: { success: false, error: 'save fail' } }));
      await expect(saveBrandingSettings({})).rejects.toThrow('save fail');
    });
  });

  describe('image upload', () => {
    it('uploads a multipart form and returns the merged data + duplicate_of', async () => {
      mockFormData.mockResolvedValue(
        createMockResponse({
          body: {
            success: true,
            data: { image_key: 'k1', url: 'https://x/k1' },
            duplicate_of: { asset_id: 'a1', original_filename: 'logo.png' },
          },
        }),
      );
      const file = new File(['img'], 'logo.png', { type: 'image/png' });

      const result = await uploadImage(file);

      expect(mockFormData).toHaveBeenCalledWith(
        '/api/landing/images/upload',
        expect.any(FormData),
        expect.objectContaining({ onUploadProgress: undefined }),
      );
      const fd = mockFormData.mock.calls[0][1] as FormData;
      expect(fd.get('file')).toBe(file);
      expect(result).toEqual({
        image_key: 'k1',
        url: 'https://x/k1',
        duplicate_of: { asset_id: 'a1', original_filename: 'logo.png' },
      });
    });

    it('throws when the upload HTTP response is not ok', async () => {
      mockFormData.mockResolvedValue(
        createMockResponse({ ok: false, status: 413, body: { error: 'too big' } }),
      );
      const file = new File(['img'], 'big.png', { type: 'image/png' });
      await expect(uploadImage(file)).rejects.toThrow('too big');
    });

    it('throws a generic error when success is false', async () => {
      mockFormData.mockResolvedValue(createMockResponse({ body: { success: false } }));
      const file = new File(['img'], 'x.png', { type: 'image/png' });
      await expect(uploadImage(file)).rejects.toThrow('Upload failed');
    });
  });
});
