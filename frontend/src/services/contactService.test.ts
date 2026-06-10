/**
 * Contact Service - Unit Tests
 *
 * Tests for all contactService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getContacts,
  getContact,
  createContact,
  updateContact,
  deleteContact,
  getContactTypes,
} from './contactService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('contactService', () => {
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

  describe('getContacts', () => {
    it('should fetch contacts without params', async () => {
      const mockBody = { contacts: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getContacts();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/contacts'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should include contact_type query param when provided', async () => {
      const mockBody = { contacts: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getContacts('supplier');

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('contact_type=supplier');
    });

    it('should include include_inactive query param when true', async () => {
      const mockBody = { contacts: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getContacts(undefined, true);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('include_inactive=true');
    });

    it('should include both params when provided', async () => {
      const mockBody = { contacts: [{ id: 1, name: 'Test' }], count: 1 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getContacts('customer', true);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('contact_type=customer');
      expect(calledUrl).toContain('include_inactive=true');
      expect(result).toEqual(mockBody);
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(getContacts()).rejects.toThrow();
    });
  });

  describe('getContact', () => {
    it('should fetch a single contact by id', async () => {
      const mockBody = { contact: { id: 5, name: 'ACME Corp', contact_type: 'supplier' } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getContact(5);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/contacts/5');
      expect(result).toEqual(mockBody);
    });
  });

  describe('createContact', () => {
    it('should POST contact data and return result', async () => {
      const mockBody = { success: true, id: 10 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { name: 'New Contact', contact_type: 'supplier' };
      const result = await createContact(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/contacts'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${mockToken}`,
          }),
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('updateContact', () => {
    it('should PUT updated data for a given contact id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { name: 'Updated Name', email: 'new@example.com' };
      const result = await updateContact(3, data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/contacts/3'),
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('deleteContact', () => {
    it('should send DELETE request for given contact id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await deleteContact(7);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/contacts/7'),
        expect.objectContaining({
          method: 'DELETE',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('getContactTypes', () => {
    it('should fetch available contact types', async () => {
      const mockBody = { types: ['supplier', 'customer', 'employee'] };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getContactTypes();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/contacts/types');
      expect(result).toEqual(mockBody);
    });
  });
});
