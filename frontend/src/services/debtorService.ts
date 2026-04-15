/**
 * API service for ZZP debtor/creditor management.
 */
import { authenticatedGet, authenticatedPost, buildEndpoint } from './apiService';

const BASE = '/api/zzp/debtors';

export async function getReceivables(): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/receivables`));
  return resp.json();
}

export async function getPayables(): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/payables`));
  return resp.json();
}

export async function getAging(): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/aging`));
  return resp.json();
}

export async function sendReminder(invoiceId: number): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/send-reminder/${invoiceId}`), {});
  return resp.json();
}

export async function runPaymentCheck(): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint('/api/zzp/payment-check/run'), {});
  return resp.json();
}

export async function getPaymentCheckStatus(): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint('/api/zzp/payment-check/status'));
  return resp.json();
}
