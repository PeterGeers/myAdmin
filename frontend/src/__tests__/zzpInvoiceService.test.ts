/**
 * Tests for ZZP Invoice Service API calls.
 */
import {
  getInvoices, getInvoice, createInvoice, updateInvoice,
  sendInvoice, createCreditNote, getInvoicePdf, copyLastInvoice,
  createInvoiceFromTimeEntries,
} from '../services/zzpInvoiceService';

const mockGet = jest.fn();
const mockPost = jest.fn();
const mockPut = jest.fn();

jest.mock('../services/apiService', () => ({
  authenticatedGet: (...args: any[]) => mockGet(...args),
  authenticatedPost: (...args: any[]) => mockPost(...args),
  authenticatedPut: (...args: any[]) => mockPut(...args),
  buildEndpoint: (endpoint: string, params?: any) => {
    if (!params) return endpoint;
    const sp = params instanceof URLSearchParams ? params : new URLSearchParams(params);
    return `${endpoint}?${sp.toString()}`;
  },
}));

const json = (data: any) => ({ json: async () => data });

describe('ZZP Invoice Service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('getInvoices without filters', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    await getInvoices();
    expect(mockGet.mock.calls[0][0]).toContain('/api/zzp/invoices');
  });

  it('getInvoices with status filter', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    await getInvoices({ status: 'draft' });
    expect(mockGet.mock.calls[0][0]).toContain('status=draft');
  });

  it('getInvoices with contact and date filters', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    await getInvoices({ contact_id: 1, date_from: '2026-01-01' });
    const url = mockGet.mock.calls[0][0];
    expect(url).toContain('contact_id=1');
    expect(url).toContain('date_from=2026-01-01');
  });

  it('getInvoice by id', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: { id: 5 } }));
    const r = await getInvoice(5);
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/invoices/5');
    expect(r.data.id).toBe(5);
  });

  it('createInvoice posts data', async () => {
    const data = { contact_id: 1, invoice_date: '2026-04-15', payment_terms_days: 30, lines: [] };
    mockPost.mockResolvedValue(json({ success: true, data: { id: 1 } }));
    const r = await createInvoice(data);
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/invoices', data);
    expect(r.success).toBe(true);
  });

  it('updateInvoice puts data', async () => {
    const data = { contact_id: 1, invoice_date: '2026-04-15', payment_terms_days: 30, lines: [] };
    mockPut.mockResolvedValue(json({ success: true, data: { id: 1 } }));
    await updateInvoice(1, data);
    expect(mockPut).toHaveBeenCalledWith('/api/zzp/invoices/1', data);
  });

  it('sendInvoice posts with options', async () => {
    mockPost.mockResolvedValue(json({ success: true }));
    await sendInvoice(1, { output_destination: 'gdrive', send_email: true });
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/invoices/1/send', { output_destination: 'gdrive', send_email: true });
  });

  it('sendInvoice posts with empty options', async () => {
    mockPost.mockResolvedValue(json({ success: true }));
    await sendInvoice(1);
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/invoices/1/send', {});
  });

  it('createCreditNote posts to credit endpoint', async () => {
    mockPost.mockResolvedValue(json({ success: true, data: { id: 2 } }));
    const r = await createCreditNote(1);
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/invoices/1/credit', {});
    expect(r.data.id).toBe(2);
  });

  it('getInvoicePdf fetches pdf endpoint', async () => {
    mockGet.mockResolvedValue(json({ success: true }));
    await getInvoicePdf(1);
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/invoices/1/pdf');
  });

  it('copyLastInvoice posts to copy-last endpoint', async () => {
    mockPost.mockResolvedValue(json({ success: true, data: { id: 42 } }));
    const r = await copyLastInvoice(1);
    expect(mockPost).toHaveBeenCalledWith('/api/zzp/invoices/copy-last/1', {});
    expect(r.data.id).toBe(42);
  });

  it('createInvoiceFromTimeEntries posts contact and entry ids', async () => {
    mockPost.mockResolvedValue(json({ success: true, data: { id: 99 } }));
    const r = await createInvoiceFromTimeEntries(1, [10, 11, 12]);
    expect(mockPost).toHaveBeenCalledWith(
      '/api/zzp/invoices/from-time-entries',
      { contact_id: 1, entry_ids: [10, 11, 12], data: {} },
    );
    expect(r.data.id).toBe(99);
  });

  it('createInvoiceFromTimeEntries passes optional data', async () => {
    mockPost.mockResolvedValue(json({ success: true, data: { id: 100 } }));
    await createInvoiceFromTimeEntries(2, [20], { notes: 'April hours' });
    expect(mockPost).toHaveBeenCalledWith(
      '/api/zzp/invoices/from-time-entries',
      { contact_id: 2, entry_ids: [20], data: { notes: 'April hours' } },
    );
  });
});
