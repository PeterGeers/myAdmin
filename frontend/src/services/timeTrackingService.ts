/**
 * API service for ZZP time tracking.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';
import { TimeEntry, TimeEntryFilters } from '../types/zzp';

const BASE = '/api/zzp/time-entries';

export async function getTimeEntries(filters?: TimeEntryFilters): Promise<any> {
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

export async function createTimeEntry(data: Partial<TimeEntry>): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateTimeEntry(id: number, data: Partial<TimeEntry>): Promise<any> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteTimeEntry(id: number): Promise<any> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function getTimeSummary(groupBy?: string, period?: string): Promise<any> {
  const params = new URLSearchParams();
  if (groupBy) params.set('group_by', groupBy);
  if (period) params.set('period', period);
  const url = params.toString() ? `${BASE}/summary?${params}` : `${BASE}/summary`;
  const resp = await authenticatedGet(buildEndpoint(url));
  return resp.json();
}
