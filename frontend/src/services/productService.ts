/**
 * API service for shared product/service registry.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';
import { Product } from '../types/zzp';

const BASE = '/api/products';

/** Base API response shape for product endpoints. */
interface ApiResponse {
  success: boolean;
  error?: string;
}

/** Response with a list of products. */
interface ProductListResponse extends ApiResponse {
  data: Product[];
}

/** Response with a single product. */
interface ProductItemResponse extends ApiResponse {
  data: Product;
}

/** Response with the list of available product types. */
interface ProductTypesResponse extends ApiResponse {
  data: string[];
}

export async function getProducts(includeInactive?: boolean): Promise<ProductListResponse> {
  const params = includeInactive ? '?include_inactive=true' : '';
  const resp = await authenticatedGet(buildEndpoint(`${BASE}${params}`));
  return resp.json();
}

export async function getProduct(id: number): Promise<ProductItemResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function createProduct(data: Partial<Product>): Promise<ProductItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateProduct(id: number, data: Partial<Product>): Promise<ProductItemResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteProduct(id: number): Promise<ApiResponse> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function getProductTypes(): Promise<ProductTypesResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/types`));
  return resp.json();
}
