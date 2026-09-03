/**
 * API service for shared contact registry.
 */
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete, buildEndpoint } from './apiService';
import { Contact } from '../types/zzp';

const BASE = '/api/contacts';

/** Base API response shape for contact endpoints. */
interface ApiResponse {
  success: boolean;
  error?: string;
}

/** Response with a list of contacts. */
interface ContactListResponse extends ApiResponse {
  data: Contact[];
}

/** Response with a single contact. */
interface ContactItemResponse extends ApiResponse {
  data: Contact;
}

/** Response with the list of available contact types. */
interface ContactTypesResponse extends ApiResponse {
  data: string[];
}

export async function getContacts(contactType?: string, includeInactive?: boolean): Promise<ContactListResponse> {
  const params = new URLSearchParams();
  if (contactType) params.set('contact_type', contactType);
  if (includeInactive) params.set('include_inactive', 'true');
  const url = params.toString() ? `${BASE}?${params}` : BASE;
  const resp = await authenticatedGet(buildEndpoint(url));
  return resp.json();
}

export async function getContact(id: number): Promise<ContactItemResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function createContact(data: Partial<Contact>): Promise<ContactItemResponse> {
  const resp = await authenticatedPost(buildEndpoint(BASE), data);
  return resp.json();
}

export async function updateContact(id: number, data: Partial<Contact>): Promise<ContactItemResponse> {
  const resp = await authenticatedPut(buildEndpoint(`${BASE}/${id}`), data);
  return resp.json();
}

export async function deleteContact(id: number): Promise<ApiResponse> {
  const resp = await authenticatedDelete(buildEndpoint(`${BASE}/${id}`));
  return resp.json();
}

export async function getContactTypes(): Promise<ContactTypesResponse> {
  const resp = await authenticatedGet(buildEndpoint(`${BASE}/types`));
  return resp.json();
}
