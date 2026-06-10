/**
 * Time Tracking Service - Unit Tests
 *
 * Tests for all timeTrackingService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getTimeEntries,
  createTimeEntry,
  updateTimeEntry,
  deleteTimeEntry,
  getTimeSummary,
} from './timeTrackingService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('timeTrackingService', () => {
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

  describe('getTimeEntries', () => {
    it('should fetch time entries without filters', async () => {
      const mockBody = { time_entries: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getTimeEntries();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/time-entries'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should include query params when filters are provided', async () => {
      const mockBody = { time_entries: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getTimeEntries({ contact_id: 5, is_billable: true, date_from: '2024-01-01' });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('contact_id=5');
      expect(calledUrl).toContain('is_billable=true');
      expect(calledUrl).toContain('date_from=2024-01-01');
    });

    it('should skip undefined/null filter values', async () => {
      const mockBody = { time_entries: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getTimeEntries({ contact_id: 3, project_name: undefined });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('contact_id=3');
      expect(calledUrl).not.toContain('project_name');
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(getTimeEntries()).rejects.toThrow();
    });
  });

  describe('createTimeEntry', () => {
    it('should POST time entry data and return result', async () => {
      const mockBody = { success: true, id: 42 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = {
        contact_id: 1,
        entry_date: '2024-06-15',
        hours: 8,
        hourly_rate: 75,
        project_name: 'Project X',
        is_billable: true,
      };
      const result = await createTimeEntry(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/time-entries'),
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

  describe('updateTimeEntry', () => {
    it('should PUT updated data for a given time entry id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { hours: 6, description: 'Updated description' };
      const result = await updateTimeEntry(10, data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/time-entries/10'),
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

  describe('deleteTimeEntry', () => {
    it('should send DELETE request for given time entry id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await deleteTimeEntry(7);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/time-entries/7'),
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

  describe('getTimeSummary', () => {
    it('should fetch time summary without params', async () => {
      const mockBody = { summary: [], total_hours: 40, total_amount: 3000 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getTimeSummary();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/zzp/time-entries/summary');
      expect(calledUrl).not.toContain('group_by');
      expect(calledUrl).not.toContain('period');
      expect(result).toEqual(mockBody);
    });

    it('should include group_by and period params when provided', async () => {
      const mockBody = { summary: [] };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getTimeSummary('contact', '2024-06');

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('group_by=contact');
      expect(calledUrl).toContain('period=2024-06');
    });
  });
});
