/**
 * Chart of Accounts Service - Unit Tests
 *
 * Tests for all chartOfAccountsService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  listAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  exportAccounts,
  importAccounts,
} from './chartOfAccountsService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('chartOfAccountsService', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'TestTenant';

  beforeEach(() => {
    vi.clearAllMocks();

    // Mock localStorage
    Storage.prototype.getItem = vi.fn((key) => {
      if (key === 'selectedTenant') return mockTenant;
      if (key === 'i18nextLng') return 'nl';
      return null;
    });

    // Mock fetchAuthSession
    mockFetchAuthSession.mockResolvedValue({
      tokens: {
        idToken: {
          toString: () => mockToken,
        },
      },
    } as any);

    // Mock fetch
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('listAccounts', () => {
    it('should fetch accounts without params', async () => {
      const mockBody = {
        success: true,
        accounts: [{ Account: '1000', AccountName: 'Cash', AccountLookup: 'Assets', Belastingaangifte: 'none' }],
        total: 1,
        page: 1,
        limit: 50,
        pages: 1,
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await listAccounts();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/chart-of-accounts'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should include query params when provided', async () => {
      const mockBody = { success: true, accounts: [], total: 0, page: 1, limit: 25, pages: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await listAccounts({ search: 'cash', sort_by: 'Account', sort_order: 'asc', page: 2, limit: 25 });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('search=cash');
      expect(calledUrl).toContain('sort_by=Account');
      expect(calledUrl).toContain('sort_order=asc');
      expect(calledUrl).toContain('page=2');
      expect(calledUrl).toContain('limit=25');
    });

    it('should throw on HTTP error response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: { error: 'Internal server error' } })
      );

      await expect(listAccounts()).rejects.toThrow('Internal server error');
    });

    it('should throw generic message when no error detail in response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: {} })
      );

      await expect(listAccounts()).rejects.toThrow('Failed to list accounts');
    });
  });

  describe('createAccount', () => {
    it('should POST account data and return the created account', async () => {
      const newAccount = { account: '2000', accountName: 'Revenue', belastingaangifte: 'omzet' };
      const mockBody = {
        success: true,
        account: { Account: '2000', AccountName: 'Revenue', AccountLookup: '', Belastingaangifte: 'omzet' },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await createAccount(newAccount);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/chart-of-accounts'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${mockToken}`,
          }),
          body: JSON.stringify(newAccount),
        })
      );
      expect(result).toEqual(mockBody.account);
    });

    it('should throw on validation error', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 400, body: { error: 'Account number already exists' } })
      );

      await expect(
        createAccount({ account: '1000', accountName: 'Duplicate', belastingaangifte: '' })
      ).rejects.toThrow('Account number already exists');
    });
  });

  describe('updateAccount', () => {
    it('should PUT updated data for a given account number', async () => {
      const updateData = { accountName: 'Updated Cash Account' };
      const mockBody = {
        success: true,
        account: { Account: '1000', AccountName: 'Updated Cash Account', AccountLookup: 'Assets', Belastingaangifte: 'none' },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await updateAccount('1000', updateData);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/chart-of-accounts/1000'),
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify(updateData),
        })
      );
      expect(result).toEqual(mockBody.account);
    });

    it('should encode special characters in account number', async () => {
      const mockBody = { success: true, account: { Account: 'NL12 RABO', AccountName: 'Bank', AccountLookup: '', Belastingaangifte: '' } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await updateAccount('NL12 RABO', { accountName: 'Bank' });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('NL12%20RABO');
    });

    it('should throw on HTTP error', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 404, body: { error: 'Account not found' } })
      );

      await expect(updateAccount('9999', { accountName: 'Missing' })).rejects.toThrow('Account not found');
    });
  });

  describe('deleteAccount', () => {
    it('should send DELETE request for given account number', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: { success: true } }));

      await deleteAccount('3000');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/chart-of-accounts/3000'),
        expect.objectContaining({
          method: 'DELETE',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
    });

    it('should throw on error with message fallback', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 409, body: { message: 'Account has transactions' } })
      );

      await expect(deleteAccount('1000')).rejects.toThrow('Account has transactions');
    });

    it('should throw generic message when no error detail', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: {} })
      );

      await expect(deleteAccount('1000')).rejects.toThrow('Failed to delete account');
    });
  });

  describe('exportAccounts', () => {
    it('should fetch export and return a blob', async () => {
      const mockBlob = new Blob(['excel-data'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      vi.mocked(global.fetch).mockResolvedValueOnce({
        ...createMockResponse({}),
        blob: async () => mockBlob,
      });

      const result = await exportAccounts();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/tenant-admin/chart-of-accounts/export');
      expect(result).toEqual(mockBlob);
    });

    it('should throw on export error', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: { error: 'Export failed' } })
      );

      await expect(exportAccounts()).rejects.toThrow('Export failed');
    });
  });

  describe('importAccounts', () => {
    it('should POST file as FormData and return import result', async () => {
      const mockFile = new File(['data'], 'accounts.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const mockBody = { success: true, imported: 5, updated: 2, total: 7 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await importAccounts(mockFile);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/chart-of-accounts/import'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
          body: expect.any(FormData),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should throw when not authenticated', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);
      const mockFile = new File(['data'], 'accounts.xlsx');

      await expect(importAccounts(mockFile)).rejects.toThrow('Authentication required');
    });

    it('should throw on import error response', async () => {
      const mockFile = new File(['data'], 'accounts.xlsx');
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 400, body: { error: 'Invalid file format' } })
      );

      await expect(importAccounts(mockFile)).rejects.toThrow('Invalid file format');
    });
  });
});
