/**
 * API service for ZZP debtor/creditor management.
 */
import { authenticatedGet, authenticatedPost, buildEndpoint } from './apiService';

/** Base API response shape for debtor endpoints. */
interface DebtorApiResponse {
  success: boolean;
  data?: Record<string, unknown> | Array<Record<string, unknown>>;
  total_outstanding?: number;
  error?: string;
}

const BASE = '/api/zzp/debtors';

export async function getReceivables(): Promise<DebtorApiResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/receivables`));
  return resp.json();
}

export async function getPayables(): Promise<DebtorApiResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/payables`));
  return resp.json();
}

export async function getAging(): Promise<DebtorApiResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/aging`));
  return resp.json();
}

export async function sendReminder(invoiceId: number): Promise<DebtorApiResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/send-reminder/${invoiceId}`), {});
  return resp.json();
}

export async function markOverdue(): Promise<DebtorApiResponse> {
  const resp = await authenticatedPost(buildEndpoint('/api/zzp/invoices/mark-overdue'), {});
  return resp.json();
}

export async function runPaymentCheck(): Promise<DebtorApiResponse> {
  const resp = await authenticatedPost(buildEndpoint('/api/zzp/payment-check/run'), {});
  return resp.json();
}

export async function getPaymentCheckStatus(): Promise<DebtorApiResponse> {
  const resp = await authenticatedGet(buildEndpoint('/api/zzp/payment-check/status'));
  return resp.json();
}
