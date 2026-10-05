/**
 * Tests for yearEndConfigService — request shaping, response unwrapping, and
 * the HTTP-error → thrown Error branch for each function. apiService mocked.
 */

import { vi } from 'vitest';
import { authenticatedGet, authenticatedPost, authenticatedDelete } from './apiService';
import {
  getVATNettingConfig,
  configureVATNetting,
  removeVATNetting,
  getBalanceSheetAccounts,
} from './yearEndConfigService';
import { createMockResponse } from '@/test-utils/mockHelpers';

vi.mock('./apiService');
const mockGet = vi.mocked(authenticatedGet);
const mockPost = vi.mocked(authenticatedPost);
const mockDelete = vi.mocked(authenticatedDelete);

describe('yearEndConfigService', () => {
  beforeEach(() => vi.clearAllMocks());

  describe('getVATNettingConfig', () => {
    it('returns the parsed config on success', async () => {
      const body = { vat_accounts: [], primary_account: '1500' };
      mockGet.mockResolvedValue(createMockResponse({ body }));

      const result = await getVATNettingConfig();

      expect(mockGet).toHaveBeenCalledWith('/api/year-end-config/vat-netting');
      expect(result).toEqual(body);
    });

    it('throws the backend error message on a non-ok response', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ ok: false, status: 500, body: { error: 'db down' } }),
      );
      await expect(getVATNettingConfig()).rejects.toThrow('db down');
    });
  });

  describe('configureVATNetting', () => {
    it('POSTs the config payload', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: {} }));
      const config = { vat_accounts: ['1500', '1510'], primary_account: '1500' };

      await configureVATNetting(config);

      expect(mockPost).toHaveBeenCalledWith('/api/year-end-config/vat-netting', config);
    });

    it('throws on a non-ok response', async () => {
      mockPost.mockResolvedValue(
        createMockResponse({ ok: false, status: 400, body: { error: 'invalid' } }),
      );
      await expect(
        configureVATNetting({ vat_accounts: [], primary_account: '' }),
      ).rejects.toThrow('invalid');
    });
  });

  describe('removeVATNetting', () => {
    it('DELETEs the vat-netting endpoint', async () => {
      mockDelete.mockResolvedValue(createMockResponse({ body: {} }));

      await removeVATNetting();

      expect(mockDelete).toHaveBeenCalledWith('/api/year-end-config/vat-netting');
    });

    it('throws on a non-ok response', async () => {
      mockDelete.mockResolvedValue(
        createMockResponse({ ok: false, status: 500, body: { error: 'nope' } }),
      );
      await expect(removeVATNetting()).rejects.toThrow('nope');
    });
  });

  describe('getBalanceSheetAccounts', () => {
    it('unwraps the accounts array from the response', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ body: { accounts: [{ Account: '1500' }] } }),
      );

      const result = await getBalanceSheetAccounts();

      expect(mockGet).toHaveBeenCalledWith('/api/year-end-config/balance-sheet-accounts');
      expect(result).toEqual([{ Account: '1500' }]);
    });

    it('defaults to an empty array when accounts is missing', async () => {
      mockGet.mockResolvedValue(createMockResponse({ body: {} }));
      const result = await getBalanceSheetAccounts();
      expect(result).toEqual([]);
    });

    it('throws on a non-ok response', async () => {
      mockGet.mockResolvedValue(
        createMockResponse({ ok: false, status: 403, body: { error: 'forbidden' } }),
      );
      await expect(getBalanceSheetAccounts()).rejects.toThrow('forbidden');
    });
  });
});
