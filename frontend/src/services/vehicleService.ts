/**
 * API service for ZZP vehicle management (Rittenregistratie).
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.5
 */
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedRequest,
  buildEndpoint,
} from './apiService';
import type { Vehicle } from '../types/zzpTrips';

/** Base API response shape. */
interface ApiResponse {
  success: boolean;
  message?: string;
  error?: string;
}

/** Response with a list of vehicles. */
interface ApiListResponse {
  success: boolean;
  data: Vehicle[];
}

/** Response with a single vehicle item. */
interface ApiItemResponse {
  success: boolean;
  data: Vehicle;
}

const BASE = '/api/zzp/vehicles';

/**
 * List vehicles for the current tenant.
 * GET /api/zzp/vehicles?is_active=true|false
 */
export async function getVehicles(activeOnly?: boolean): Promise<ApiListResponse> {
  const params = new URLSearchParams();
  if (activeOnly !== undefined) {
    params.set('is_active', String(activeOnly));
  }
  const url = params.toString() ? `${BASE}?${params}` : BASE;
  const resp = await authenticatedGet(buildEndpoint(url));
  return resp.json();
}

/**
 * Create a new vehicle.
 * POST /api/zzp/vehicles
 */
export async function createVehicle(data: Partial<Vehicle>): Promise<ApiItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

/**
 * Update an existing vehicle.
 * PUT /api/zzp/vehicles/{id}
 * Note: Cannot change start_odometer if trips exist for this vehicle.
 */
export async function updateVehicle(id: number, data: Partial<Vehicle>): Promise<ApiItemResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

/**
 * Deactivate (soft-delete) a vehicle.
 * DELETE /api/zzp/vehicles/{id}
 */
export async function deactivateVehicle(id: number): Promise<ApiResponse> {
  const resp = await authenticatedRequest(buildEndpoint(`${BASE}/${id}`), {
    method: 'DELETE',
  });
  return resp.json();
}
