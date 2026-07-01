/**
 * API service for ZZP time tracking.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';
import { TimeEntry, TimeEntryFilters, TimeSummary } from '../types/zzp';

const BASE = '/api/zzp/time-entries';

interface ApiListResponse {
  success: boolean;
  data: TimeEntry[];
  total?: number;
}

interface ApiItemResponse {
  success: boolean;
  data: TimeEntry;
}

interface ApiDeleteResponse {
  success: boolean;
  message?: string;
}

interface ApiSummaryResponse {
  success: boolean;
  data: TimeSummary[];
}

export async function getTimeEntries(filters?: TimeEntryFilters): Promise<ApiListResponse> {
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

export async function createTimeEntry(data: Partial<TimeEntry>): Promise<ApiItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateTimeEntry(id: number, data: Partial<TimeEntry>): Promise<ApiItemResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteTimeEntry(id: number): Promise<ApiDeleteResponse> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function getTimeSummary(groupBy?: string, period?: string): Promise<ApiSummaryResponse> {
  const params = new URLSearchParams();
  if (groupBy) params.set('group_by', groupBy);
  if (period) params.set('period', period);
  const url = params.toString() ? `${BASE}/summary?${params}` : `${BASE}/summary`;
  const resp = await authenticatedGet(buildEndpoint(url));
  return resp.json();
}
