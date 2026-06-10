/**
 * ZZP Invoice Service - Unit Tests
 *
 * Tests for all zzpInvoiceService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getInvoices,
  getInvoice,
  createInvoice,
  updateInvoice,
  sendInvoice,
  createCreditNote,
  getInvoicePdf,
  copyLastInvoice,
  getInvoiceLedgerAccounts,
  createInvoiceFromTimeEntries,
  getInvoicePreview,
  getEmailPreview,
} from './zzpInvoiceService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('zzpInvoiceService', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'TestTenant';

  beforeEach(() => {
    vi.clearAllMocks();

    // Mock localStorage
    Storage.prototype.getItem = vi.fn((key) => {
      if (key === 'selectedTenant') return mockTenant;
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

  describe('getInvoices', () => {
    it('should fetch invoices without filters', async () => {
      const mockBody = { invoices: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getInvoices();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices'),
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
      const mockBody = { invoices: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getInvoices({ status: 'sent' as any, contact_id: 5 });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('status=sent');
      expect(calledUrl).toContain('contact_id=5');
    });

    it('should omit undefined/null filter values', async () => {
      const mockBody = { invoices: [] };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getInvoices({ status: undefined, contact_id: 3 });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).not.toContain('status');
      expect(calledUrl).toContain('contact_id=3');
    });
  });

  describe('getInvoice', () => {
    it('should fetch a single invoice by id', async () => {
      const mockBody = { invoice: { id: 1, invoice_number: 'INV-001' } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getInvoice(1);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/zzp/invoices/1');
      expect(result).toEqual(mockBody);
    });
  });

  describe('createInvoice', () => {
    it('should POST invoice data', async () => {
      const mockBody = { success: true, id: 42 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = {
        contact_id: 1,
        invoice_date: '2024-06-01',
        payment_terms_days: 30,
        lines: [{ description: 'Consulting', quantity: 10, unit_price: 100, vat_rate: 21 }],
      } as any;
      const result = await createInvoice(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices'),
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

  describe('updateInvoice', () => {
    it('should PUT updated invoice data', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = {
        contact_id: 1,
        invoice_date: '2024-06-15',
        payment_terms_days: 14,
        lines: [{ description: 'Updated service', quantity: 5, unit_price: 150, vat_rate: 21 }],
      } as any;
      const result = await updateInvoice(10, data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices/10'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('sendInvoice', () => {
    it('should POST send request without options', async () => {
      const mockBody = { success: true, invoice_number: 'INV-001' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await sendInvoice(5);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices/5/send'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({}),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should POST send request with options', async () => {
      const mockBody = { success: true, invoice_number: 'INV-002' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const options = { output_destination: 'email', send_email: true };
      const result = await sendInvoice(7, options);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices/7/send'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(options),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('createCreditNote', () => {
    it('should POST credit note creation', async () => {
      const mockBody = { success: true, credit_note_id: 99 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await createCreditNote(12);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices/12/credit'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({}),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('getInvoicePdf', () => {
    it('should GET the PDF for an invoice', async () => {
      const mockBody = { pdf_url: 'https://example.com/invoice.pdf' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getInvoicePdf(3);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/zzp/invoices/3/pdf');
      expect(result).toEqual(mockBody);
    });
  });

  describe('copyLastInvoice', () => {
    it('should POST copy request for a contact', async () => {
      const mockBody = { success: true, invoice_id: 55 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await copyLastInvoice(8);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices/copy-last/8'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({}),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('getInvoiceLedgerAccounts', () => {
    it('should fetch invoice ledger accounts', async () => {
      const mockBody = { accounts: [{ code: '8000', name: 'Revenue' }] };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getInvoiceLedgerAccounts();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/zzp/accounts/invoice-ledgers');
      expect(result).toEqual(mockBody);
    });
  });

  describe('createInvoiceFromTimeEntries', () => {
    it('should POST invoice creation from time entries', async () => {
      const mockBody = { success: true, invoice_id: 77 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await createInvoiceFromTimeEntries(4, [1, 2, 3]);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices/from-time-entries'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ contact_id: 4, entry_ids: [1, 2, 3], data: {} }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should include optional data when provided', async () => {
      const mockBody = { success: true, invoice_id: 78 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const extraData = { notes: 'Custom note' };
      await createInvoiceFromTimeEntries(4, [1, 2], extraData);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices/from-time-entries'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ contact_id: 4, entry_ids: [1, 2], data: extraData }),
        })
      );
    });
  });

  describe('getInvoicePreview', () => {
    it('should GET preview and return a blob', async () => {
      const mockBlob = new Blob(['pdf-content'], { type: 'application/pdf' });
      const mockResponse: Response = {
        ok: true,
        status: 200,
        statusText: 'OK',
        headers: new Headers(),
        redirected: false,
        type: 'basic',
        url: '',
        body: null,
        bodyUsed: false,
        json: async () => ({}),
        text: async () => '',
        blob: async () => mockBlob,
        arrayBuffer: async () => new ArrayBuffer(0),
        formData: async () => new FormData(),
        bytes: async () => new Uint8Array(),
        clone() { return this; },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      const result = await getInvoicePreview(9);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/zzp/invoices/9/preview');
      expect(result).toBe(mockBlob);
    });

    it('should throw when preview response is not ok', async () => {
      const mockResponse: Response = {
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers(),
        redirected: false,
        type: 'basic',
        url: '',
        body: null,
        bodyUsed: false,
        json: async () => ({ error: 'Preview generation failed' }),
        text: async () => '',
        blob: async () => new Blob(),
        arrayBuffer: async () => new ArrayBuffer(0),
        formData: async () => new FormData(),
        bytes: async () => new Uint8Array(),
        clone() { return this; },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await expect(getInvoicePreview(9)).rejects.toThrow('Preview generation failed');
    });
  });

  describe('getEmailPreview', () => {
    it('should GET email preview data', async () => {
      const mockBody = {
        success: true,
        data: {
          subject: 'Invoice INV-001',
          html_body: '<p>Hello</p>',
          recipient: 'client@example.com',
          bcc: 'admin@example.com',
          attachment_filename: 'INV-001.pdf',
        },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getEmailPreview(15);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/zzp/invoices/15/email-preview');
      expect(result).toEqual(mockBody);
    });
  });
});
