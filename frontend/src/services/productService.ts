/**
 * API service for shared product/service registry.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';
import { Product } from '../types/zzp';

const BASE = '/api/products';

export async function getProducts(includeInactive?: boolean): Promise<any> {
  const params = includeInactive ? '?include_inactive=true' : '';
  const resp = await authenticatedGet(buildEndpoint(`${BASE}${params}`));
  return resp.json();
}

export async function getProduct(id: number): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function createProduct(data: Partial<Product>): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateProduct(id: number, data: Partial<Product>): Promise<any> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteProduct(id: number): Promise<any> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function getProductTypes(): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/types`));
  return resp.json();
}
