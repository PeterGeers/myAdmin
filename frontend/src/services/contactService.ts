/**
 * API service for shared contact registry.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';
import { Contact } from '../types/zzp';

const BASE = '/api/contacts';

export async function getContacts(contactType?: string, includeInactive?: boolean): Promise<any> {
  const params = new URLSearchParams();
  if (contactType) params.set('contact_type', contactType);
  if (includeInactive) params.set('include_inactive', 'true');
  const url = params.toString() ? `${BASE}?${params}` : BASE;
  const resp = await authenticatedGet(buildEndpoint(url));
  return resp.json();
}

export async function getContact(id: number): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function createContact(data: Partial<Contact>): Promise<any> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateContact(id: number, data: Partial<Contact>): Promise<any> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteContact(id: number): Promise<any> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function getContactTypes(): Promise<any> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/types`));
  return resp.json();
}
