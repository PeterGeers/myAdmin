/**
 * Tests for Debtor Service API calls.
 */
import { vi } from 'vitest';
import {
  getReceivables, getPayables, getAging,
  sendReminder, runPaymentCheck, getPaymentCheckStatus,
} from '../services/debtorService';

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../services/apiService', () => ({
  authenticatedGet: (...args: any[]) => mockGet(...args),
  authenticatedPost: (...args: any[]) => mockPost(...args),
  buildEndpoint: (endpoint: string) => endpoint,
}));

const json = (data: any) => ({ json: async () => data });

describe('Debtor Service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getReceivables calls correct endpoint', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    const r = await getReceivables();
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/debtors/receivables');
    expect(r.success).toBe(true);
  });

  it('getPayables calls correct endpoint', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    await getPayables();
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/debtors/payables');
  });

  it('getAging calls correct endpoint', async () => {
    const aging = { total_outstanding: 5000, buckets: { current: 3000 } };
    mockGet.mockResolvedValue(json({ success: true, data: aging }));
    const r = await getAging();
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/debtors/aging');
    expect((r.data as Record<string, unknown>).total_outstanding).toBe(5000);
  });

  it('sendReminder posts to correct endpoint', async () => {
    mockPost.mockResolvedValue(json({ success: true }));
    await sendReminder(7);
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/debtors/send-reminder/7', {});
  });

  it('runPaymentCheck posts to correct endpoint', async () => {
    mockPost.mockResolvedValue(json({ success: true, data: { matched: 3 } }));
    const r = await runPaymentCheck();
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/payment-check/run', {});
    expect((r.data as Record<string, unknown>).matched).toBe(3);
  });

  it('getPaymentCheckStatus calls correct endpoint', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: { last_run: '2026-04-15' } }));
    const r = await getPaymentCheckStatus();
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/payment-check/status');
    expect((r.data as Record<string, unknown>).last_run).toBe('2026-04-15');
  });
});
