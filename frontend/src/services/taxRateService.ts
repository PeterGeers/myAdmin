/**
 * API service for tax rate administration.
 */
import { TaxRate, TaxRatesResponse, TaxRateCreateRequest, TaxRateUpdateRequest } from '../types/taxRateTypes';
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';

const BASE = '/api/tenant-admin/tax-rates';

/** Base API response shape for tax rate mutations. */
interface TaxRateMutationResponse {
  success: boolean;
  error?: string;
  data?: TaxRate;
}

export async function getTaxRates(): Promise<TaxRatesResponse> {
  const resp = await authenticatedGet(buildEndpoint(BASE));
  return resp.json();
}

export async function createTaxRate(data: TaxRateCreateRequest): Promise<TaxRateMutationResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateTaxRate(id: number, data: TaxRateUpdateRequest): Promise<TaxRateMutationResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteTaxRate(id: number): Promise<TaxRateMutationResponse> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}
