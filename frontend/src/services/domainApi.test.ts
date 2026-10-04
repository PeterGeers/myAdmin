/**
 * Tests for domainApi — request shaping, the result.data unwrapping on
 * getDomains, and the HTTP-error branches. apiService is mocked.
 */

import { vi } from 'vitest';
import { authenticatedGet, authenticatedPost, authenticatedDelete } from './apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getDomains,
  enableJabaki,
  disableJabaki,
  registerCustomDomain,
  verifyCustomDomain,
  removeCustomDomain,
} from './domainApi';

vi.mock('./apiService');
const mockGet = vi.mocked(authenticatedGet);
const mockPost = vi.mocked(authenticatedPost);
const mockDelete = vi.mocked(authenticatedDelete);

describe('domainApi', () => {
  beforeEach(() => vi.clearAllMocks());

  describe('getDomains', () => {
    it('unwraps result.data on success', async () => {
      const data = { jabaki: { enabled: true }, custom: { domain: null } };
      mockGet.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

      const result = await getDomains();

      expect(mockGet).toHaveBeenCalledWith('/api/landing/domains');
      expect(result).toEqual(data);
    });

    it('throws when the HTTP response is not ok', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ ok: false, status: 500, body: { error: 'server' } }),
      );
      await expect(getDomains()).rejects.toThrow('server');
    });

    it('throws when success is false despite a 200', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ body: { success: false, error: 'no slug' } }),
      );
      await expect(getDomains()).rejects.toThrow('no slug');
    });
  });

  it('enableJabaki POSTs to the enable endpoint', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true, domain: 'x.jabaki.nl' } }));
    const result = await enableJabaki();
    expect(mockPost).toHaveBeenCalledWith('/api/landing/domains/jabaki/enable');
    expect(result.domain).toBe('x.jabaki.nl');
  });

  it('disableJabaki POSTs to the disable endpoint', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true, message: 'ok' } }));
    await disableJabaki();
    expect(mockPost).toHaveBeenCalledWith('/api/landing/domains/jabaki/disable');
  });

  it('registerCustomDomain POSTs the domain in the body', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true, data: {} } }));
    await registerCustomDomain('example.com');
    expect(mockPost).toHaveBeenCalledWith('/api/landing/domains/custom', { domain: 'example.com' });
  });

  it('verifyCustomDomain POSTs to the verify endpoint', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: true, data: {} } }));
    await verifyCustomDomain();
    expect(mockPost).toHaveBeenCalledWith('/api/landing/domains/custom/verify');
  });

  it('removeCustomDomain DELETEs the custom domain', async () => {
    mockDelete.mockResolvedValue(createMockResponse({ body: { success: true, message: 'gone' } }));
    const result = await removeCustomDomain();
    expect(mockDelete).toHaveBeenCalledWith('/api/landing/domains/custom');
    expect(result.message).toBe('gone');
  });

  it('registerCustomDomain throws on a non-ok response', async () => {
    mockPost.mockResolvedValue(
      createMockResponse({ ok: false, status: 409, body: { error: 'taken' } }),
    );
    await expect(registerCustomDomain('taken.com')).rejects.toThrow('taken');
  });
});
