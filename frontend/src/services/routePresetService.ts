/**
 * API service for ZZP route preset management (Rittenregistratie).
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.5
 */
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedRequest,
  buildEndpoint,
} from './apiService';
import type { RoutePreset } from '../types/zzpTrips';

/** Base API response shape. */
interface ApiResponse {
  success: boolean;
  message?: string;
  error?: string;
}

/** Response with a list of route presets. */
interface ApiListResponse {
  success: boolean;
  data: RoutePreset[];
}

/** Response with a single route preset item. */
interface ApiItemResponse {
  success: boolean;
  data: RoutePreset;
}

const BASE = '/api/zzp/route-presets';

/**
 * List route presets for the current tenant.
 * GET /api/zzp/route-presets
 * Returns top presets by usage in last 6 months + manual presets.
 */
export async function getRoutePresets(): Promise<ApiListResponse> {
  const resp = await authenticatedGet(buildEndpoint(BASE));
  return resp.json();
}

/**
 * Create a new manual route preset.
 * POST /api/zzp/route-presets
 */
export async function createRoutePreset(data: Partial<RoutePreset>): Promise<ApiItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

/**
 * Update an existing route preset's defaults.
 * PUT /api/zzp/route-presets/{id}
 */
export async function updateRoutePreset(id: number, data: Partial<RoutePreset>): Promise<ApiItemResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

/**
 * Delete a route preset.
 * DELETE /api/zzp/route-presets/{id}
 */
export async function deleteRoutePreset(id: number): Promise<ApiResponse> {
  const resp = await authenticatedRequest(buildEndpoint(`${BASE}/${id}`), {
    method: 'DELETE',
  });
  return resp.json();
}
