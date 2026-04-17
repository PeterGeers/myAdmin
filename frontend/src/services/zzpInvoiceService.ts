/**
 * API service for ZZP invoice management.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, buildEndpoint } from './apiService';
import { InvoiceFilters, InvoiceInput } from '../types/zzp';

const BASE = '/api/zzp/invoices';

export async function getInvoices(filters?: InvoiceFilters): Promise<any> {
  const params = new URLSearchParams();
  if (filters) {
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null) params.set(k, String(v));
    });
  }
  const url = params.toString() ? `${BASE}?${params}` : BASE;
  const resp = await authenticatedGet(buildEndpoint(url));
  return resp.json();
}

export async function getInvoice(id: number): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function createInvoice(data: InvoiceInput): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateInvoice(id: number, data: InvoiceInput): Promise<any> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

/** Response from the send invoice endpoint. */
export interface SendInvoiceResponse {
  success: boolean;
  invoice_number?: string;
  error?: string;
  /** Present when the invoice was booked successfully but email sending failed. */
  warning?: string;
}

export async function sendInvoice(id: number, options?: { output_destination?: string; send_email?: boolean }): Promise<SendInvoiceResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/${id}/send`), options || {});
  return resp.json();
}

export async function createCreditNote(invoiceId: number): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/${invoiceId}/credit`), {});
  return resp.json();
}

export async function getInvoicePdf(id: number): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}/pdf`));
  return resp.json();
}

export async function copyLastInvoice(contactId: number): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/copy-last/${contactId}`), {});
  return resp.json();
}

/**
 * Fetch accounts flagged as ZZP invoice ledger for the revenue account dropdown.
 * GET /api/zzp/accounts/invoice-ledgers
 */
export async function getInvoiceLedgerAccounts(): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint('/api/zzp/accounts/invoice-ledgers'));
  return resp.json();
}

/**
 * Create an invoice from selected time entries.
 * POST /api/zzp/invoices/from-time-entries
 */
export async function createInvoiceFromTimeEntries(
  contactId: number,
  entryIds: number[],
  data?: Record<string, any>,
): Promise<any> {
  const resp = await authenticatedPost(
    buildEndpoint(`${BASE}/from-time-entries`),
    { contact_id: contactId, entry_ids: entryIds, data: data || {} },
  );
  return resp.json();
}
