/**
 * API service for ZZP trip/mileage registration (Rittenregistratie).
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md §5.5
 */
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedRequest,
  authenticatedFormData,
  buildEndpoint,
} from './apiService';
import type { Trip, TripFilters, TripSummary, TripAuditEntry, GapFillData } from '../types/zzpTrips';

/** Base API response shape. */
interface ApiResponse {
  success: boolean;
  message?: string;
  error?: string;
}

/** Response with a list of trips + total count. */
interface ApiListResponse {
  success: boolean;
  data: Trip[];
  total?: number;
}

/** Response with a single trip (may include warnings for gap detection). */
interface ApiTripResponse {
  success: boolean;
  data: Trip;
  warnings?: Array<{
    type: string;
    message: string;
    gap_km?: number;
    previous_end_odometer?: number;
    current_start_odometer?: number;
  }>;
  gap_fill_offer?: {
    start_odometer: number;
    end_odometer: number;
    suggested_category: string;
    suggested_purpose: string;
  };
}

/** Response with audit/history entries. */
interface ApiAuditResponse {
  success: boolean;
  data: TripAuditEntry[];
}

/** Response with trip summary data. */
interface ApiSummaryResponse {
  success: boolean;
  data: TripSummary & {
    monthly_breakdown?: Array<{
      month: string;
      zakelijk: number;
      prive: number;
      woonwerk: number;
    }>;
  };
}

/** Column mapping for CSV/Excel import commit. */
export interface ColumnMapping {
  date?: string;
  start_address?: string;
  end_address?: string;
  start_km?: string;
  end_km?: string;
  purpose?: string;
  category?: string;
  [key: string]: string | undefined;
}

/** Response from import preview/validation. */
interface ApiImportResponse {
  success: boolean;
  data: {
    total_rows: number;
    valid: number;
    warnings: number;
    errors: number;
    preview: Array<Record<string, unknown>>;
  };
}

const BASE = '/api/zzp/trips';

/**
 * List trips with optional filtering.
 * GET /api/zzp/trips
 */
export async function getTrips(filters?: TripFilters): Promise<ApiListResponse> {
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

/**
 * Create a new trip.
 * POST /api/zzp/trips
 */
export async function createTrip(data: Partial<Trip>): Promise<ApiTripResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

/**
 * Update/correct a trip (requires correction_reason in data).
 * PUT /api/zzp/trips/{id}
 */
export async function updateTrip(id: number, data: Partial<Trip>): Promise<ApiTripResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

/**
 * Cancel (soft-delete) a trip with a reason.
 * DELETE /api/zzp/trips/{id}
 */
export async function cancelTrip(id: number, reason: string): Promise<ApiResponse> {
  const resp = await authenticatedRequest(buildEndpoint(`${BASE}/${id}`), {
    method: 'DELETE',
    body: JSON.stringify({ cancel_reason: reason }),
  });
  return resp.json();
}

/**
 * Get correction/audit history for a trip.
 * GET /api/zzp/trips/{id}/history
 */
export async function getTripHistory(id: number): Promise<ApiAuditResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}/history`));
  return resp.json();
}

/**
 * Get unbilled billable trips for a specific contact.
 * GET /api/zzp/trips/unbilled?contact_id={id}
 */
export async function getUnbilledTrips(contactId: number): Promise<ApiListResponse> {
  const params = new URLSearchParams({ contact_id: String(contactId) });
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/unbilled`, params));
  return resp.json();
}

/**
 * Get trip summary (yearly totals per category, bijtelling status).
 * GET /api/zzp/trips/summary?vehicle_id=&year=
 */
export async function getTripSummary(vehicleId: number, year: number): Promise<ApiSummaryResponse> {
  const params = new URLSearchParams({
    vehicle_id: String(vehicleId),
    year: String(year),
  });
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/summary`, params));
  return resp.json();
}

/**
 * Export trips as a downloadable file (PDF/CSV/XLSX).
 * GET /api/zzp/trips/export?vehicle_id=&year=&format=
 * Returns a Blob for file download.
 */
export async function exportTrips(vehicleId: number, year: number, format: string): Promise<Blob> {
  const params = new URLSearchParams({
    vehicle_id: String(vehicleId),
    year: String(year),
    format,
  });
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/export`, params));
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.error || 'Export failed');
  }
  return resp.blob();
}

/**
 * Accept a gap-fill suggestion (creates a gap-fill trip).
 * POST /api/zzp/trips/gap-fill
 */
export async function createGapFill(data: GapFillData): Promise<ApiTripResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/gap-fill`), data);
  return resp.json();
}

/**
 * Upload and validate a CSV/Excel file for import.
 * POST /api/zzp/trips/import (multipart/form-data)
 */
export async function importTrips(file: File, vehicleId: number): Promise<ApiImportResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('vehicle_id', String(vehicleId));
  const resp = await authenticatedFormData(buildEndpoint(`${BASE}/import`), formData);
  return resp.json();
}

/**
 * Commit a validated import with column mapping.
 * POST /api/zzp/trips/import/commit
 */
export async function commitImport(vehicleId: number, mapping: ColumnMapping): Promise<ApiResponse> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/import/commit`), {
    vehicle_id: vehicleId,
    column_mapping: mapping,
  });
  return resp.json();
}

/**
 * Get unresolved gap-fill entries.
 * GET /api/zzp/trips/gaps
 */
export async function getGaps(): Promise<ApiListResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/gaps`));
  return resp.json();
}
