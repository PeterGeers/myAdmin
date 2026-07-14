/**
 * API service for ZZP invoice management.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, buildEndpoint } from './apiService';
import { Invoice, InvoiceFilters, InvoiceInput } from '../types/zzp';

/** Response containing a list of invoices. */
export interface InvoiceListResponse {
  success: boolean;
  data: Invoice[];
  error?: string;
}

/** Response containing a single invoice. */
export interface InvoiceItemResponse {
  success: boolean;
  data: Invoice;
  error?: string;
}

/** Response containing generic record data (e.g., ledger accounts). */
export interface GenericListResponse {
  success: boolean;
  data: Record<string, unknown>[];
  error?: string;
}

/** Response shape for the email preview endpoint. */
export interface EmailPreviewResponse {
  success: boolean;
  data?: {
    subject: string;
    html_body: string;
    recipient: string;
    bcc: string;
    attachment_filename: string;
  };
  error?: string;
}

const BASE = '/api/zzp/invoices';

export async function getInvoices(filters?: InvoiceFilters): Promise<InvoiceListResponse> {
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

export async function getInvoice(id: number): Promise<InvoiceItemResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function createInvoice(data: InvoiceInput): Promise<InvoiceItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateInvoice(id: number, data: InvoiceInput): Promise<InvoiceItemResponse> {
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

export async function createCreditNote(invoiceId: number): Promise<InvoiceItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/${invoiceId}/credit`), {});
  return resp.json();
}

export async function getInvoicePdf(id: number): Promise<InvoiceItemResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}/pdf`));
  return resp.json();
}

export async function copyLastInvoice(contactId: number): Promise<InvoiceItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/copy-last/${contactId}`), {});
  return resp.json();
}

/**
 * Fetch accounts flagged as ZZP invoice ledger for the revenue account dropdown.
 * GET /api/zzp/accounts/invoice-ledgers
 */
export async function getInvoiceLedgerAccounts(): Promise<GenericListResponse> {
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
  data?: Record<string, unknown>,
): Promise<InvoiceItemResponse> {
  const resp = await authenticatedPost(
    buildEndpoint(`${BASE}/from-time-entries`),
    { contact_id: contactId, entry_ids: entryIds, data: data || {} },
  );
  return resp.json();
}

/**
 * Generate a PDF preview for a draft invoice.
 * GET /api/zzp/invoices/{id}/preview
 *
 * Supports an optional AbortController signal for timeout/cancellation.
 * If no signal is provided, a 30-second timeout is applied automatically.
 */
export async function getInvoicePreview(
  id: number,
  options?: { signal?: AbortSignal },
): Promise<Blob> {
  let signal = options?.signal;
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  // Apply a 30s timeout if no external signal is provided
  if (!signal) {
    const controller = new AbortController();
    signal = controller.signal;
    timeoutId = setTimeout(() => controller.abort(), 30_000);
  }

  try {
    const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}/preview`), { signal });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.error || 'Preview failed');
    }
    return resp.blob();
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId);
    }
  }
}

/**
 * Fetch the email preview for a draft invoice (subject, body, recipient, BCC, attachment).
 * GET /api/zzp/invoices/{id}/email-preview
 */
export async function getEmailPreview(id: number): Promise<EmailPreviewResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}/email-preview`));
  return resp.json();
}

/** Input for creating an invoice from trips. */
export interface CreateInvoiceFromTripsInput {
  contact_id: number;
  trip_ids: number[];
  km_rate: number;
  invoice_date: string;
  payment_terms_days: number;
}

/**
 * Create an invoice from selected trips.
 * POST /api/zzp/invoices/from-trips
 */
export async function createInvoiceFromTrips(data: CreateInvoiceFromTripsInput): Promise<InvoiceItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/from-trips`), data);
  return resp.json();
}
