/**
 * Tests for ZZP Time Tracking service layer.
 *
 * Tests API calls for time entry CRUD and summary endpoints.
 * Reference: .kiro/specs/zzp-module/tasks.md Phase 8.5
 */

import {
  getTimeEntries, createTimeEntry, updateTimeEntry,
  deleteTimeEntry, getTimeSummary,
} from '../services/timeTrackingService';

// Mock the entire apiService module — the time tracking service imports from it
const mockAuthGet = jest.fn();
const mockAuthPost = jest.fn();
const mockAuthPut = jest.fn();
const mockAuthDelete = jest.fn();

jest.mock('../services/apiService', () => ({
  authenticatedGet: (...args: any[]) => mockAuthGet(...args),
  authenticatedPost: (...args: any[]) => mockAuthPost(...args),
  authenticatedPut: (...args: any[]) => mockAuthPut(...args),
  authenticatedDelete: (...args: any[]) => mockAuthDelete(...args),
  buildEndpoint: (endpoint: string, params?: any) => {
    if (!params) return endpoint;
    const sp = params instanceof URLSearchParams ? params : new URLSearchParams(params);
    return `${endpoint}?${sp.toString()}`;
  },
}));

const jsonResp = (data: any) => ({ json: async () => data });

describe('Time Tracking Service', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  describe('getTimeEntries', () => {
    it('fetches entries without filters', async () => {
      const mock = { success: true, data: [{ id: 1, hours: 8 }] };
      mockAuthGet.mockResolvedValue(jsonResp(mock));

      const result = await getTimeEntries();

      expect(mockAuthGet).toHaveBeenCalledTimes(1);
      expect(mockAuthGet.mock.calls[0][0]).toContain('/api/zzp/time-entries');
      expect(result).toEqual(mock);
    });

    it('fetches entries with contact filter', async () => {
      mockAuthGet.mockResolvedValue(jsonResp({ success: true, data: [] }));
      await getTimeEntries({ contact_id: 5 });
      expect(mockAuthGet.mock.calls[0][0]).toContain('contact_id=5');
    });

    it('fetches entries with date range filter', async () => {
      mockAuthGet.mockResolvedValue(jsonResp({ success: true, data: [] }));
      await getTimeEntries({ date_from: '2026-01-01', date_to: '2026-01-31' });
      const url = mockAuthGet.mock.calls[0][0];
      expect(url).toContain('date_from=2026-01-01');
      expect(url).toContain('date_to=2026-01-31');
    });

    it('fetches entries with billed filter', async () => {
      mockAuthGet.mockResolvedValue(jsonResp({ success: true, data: [] }));
      await getTimeEntries({ is_billed: false });
      expect(mockAuthGet.mock.calls[0][0]).toContain('is_billed=false');
    });
  });

  describe('createTimeEntry', () => {
    it('posts new entry data', async () => {
      const entry = {
        contact_id: 1, entry_date: '2026-04-15',
        hours: 8, hourly_rate: 95, is_billable: true,
      };
      mockAuthPost.mockResolvedValue(jsonResp({ success: true, data: { id: 10, ...entry } }));

      const result = await createTimeEntry(entry);

      expect(mockAuthPost).toHaveBeenCalledTimes(1);
      expect(mockAuthPost.mock.calls[0][0]).toContain('/api/zzp/time-entries');
      expect(mockAuthPost.mock.calls[0][1]).toEqual(entry);
      expect(result.success).toBe(true);
      expect(result.data.id).toBe(10);
    });
  });

  describe('updateTimeEntry', () => {
    it('puts updated entry data', async () => {
      const update = { hours: 6 };
      mockAuthPut.mockResolvedValue(jsonResp({ success: true, data: { id: 10, hours: 6 } }));

      const result = await updateTimeEntry(10, update);

      expect(mockAuthPut.mock.calls[0][0]).toContain('/api/zzp/time-entries/10');
      expect(mockAuthPut.mock.calls[0][1]).toEqual(update);
      expect(result.data.hours).toBe(6);
    });
  });

  describe('deleteTimeEntry', () => {
    it('deletes an entry by id', async () => {
      mockAuthDelete.mockResolvedValue(jsonResp({ success: true }));

      const result = await deleteTimeEntry(10);

      expect(mockAuthDelete.mock.calls[0][0]).toContain('/api/zzp/time-entries/10');
      expect(result.success).toBe(true);
    });
  });

  describe('getTimeSummary', () => {
    it('fetches summary grouped by contact', async () => {
      const mock = { success: true, data: [{ contact_id: 1, total_hours: 40, total_amount: 3800 }] };
      mockAuthGet.mockResolvedValue(jsonResp(mock));

      const result = await getTimeSummary('contact');

      expect(mockAuthGet.mock.calls[0][0]).toContain('group_by=contact');
      expect(result.data[0].total_hours).toBe(40);
    });

    it('fetches summary grouped by period with month', async () => {
      mockAuthGet.mockResolvedValue(jsonResp({ success: true, data: [] }));
      await getTimeSummary('period', 'month');
      const url = mockAuthGet.mock.calls[0][0];
      expect(url).toContain('group_by=period');
      expect(url).toContain('period=month');
    });

    it('fetches summary without params', async () => {
      mockAuthGet.mockResolvedValue(jsonResp({ success: true, data: [] }));
      await getTimeSummary();
      expect(mockAuthGet.mock.calls[0][0]).toContain('/api/zzp/time-entries/summary');
    });
  });
});
