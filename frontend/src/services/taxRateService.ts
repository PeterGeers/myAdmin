/**
 * API service for tax rate administration.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';
import { TaxRatesResponse, TaxRateCreateRequest, TaxRateUpdateRequest } from '../types/taxRateTypes';

const BASE = '/api/tenant-admin/tax-rates';

export async function getTaxRates(): Promise<TaxRatesResponse> {
  const resp = await authenticatedGet(buildEndpoint(BASE));
  return resp.json();
}

export async function createTaxRate(data: TaxRateCreateRequest): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateTaxRate(id: number, data: TaxRateUpdateRequest): Promise<any> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteTaxRate(id: number): Promise<any> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}
