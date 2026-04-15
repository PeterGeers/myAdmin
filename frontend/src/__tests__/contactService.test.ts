/**
 * Tests for Contact Service API calls.
 */
import {
  getContacts, getContact, createContact, updateContact,
  deleteContact, getContactTypes,
} from '../services/contactService';

const mockGet = jest.fn();
const mockPost = jest.fn();
const mockPut = jest.fn();
const mockDelete = jest.fn();

jest.mock('../services/apiService', () => ({
  authenticatedGet: (...args: any[]) => mockGet(...args),
  authenticatedPost: (...args: any[]) => mockPost(...args),
  authenticatedPut: (...args: any[]) => mockPut(...args),
  authenticatedDelete: (...args: any[]) => mockDelete(...args),
  buildEndpoint: (endpoint: string) => endpoint,
}));

const json = (data: any) => ({ json: async () => data });

describe('Contact Service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('getContacts without filter', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    const r = await getContacts();
    expect(mockGet).toHaveBeenCalledWith('/api/contacts');
    expect(r.success).toBe(true);
  });

  it('getContacts with type filter', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    await getContacts('client');
    expect(mockGet.mock.calls[0][0]).toContain('contact_type=client');
  });

  it('getContacts with includeInactive', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    await getContacts(undefined, true);
    expect(mockGet.mock.calls[0][0]).toContain('include_inactive=true');
  });

  it('getContact by id', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: { id: 5 } }));
    const r = await getContact(5);
    expect(mockGet).toHaveBeenCalledWith('/api/contacts/5');
    expect(r.data.id).toBe(5);
  });

  it('createContact posts data', async () => {
    const data = { client_id: 'ACME', company_name: 'Acme Corp' };
    mockPost.mockResolvedValue(json({ success: true, data: { id: 1, ...data } }));
    const r = await createContact(data);
    expect(mockPost).toHaveBeenCalledWith('/api/contacts', data);
    expect(r.data.client_id).toBe('ACME');
  });

  it('updateContact puts data', async () => {
    const data = { company_name: 'Acme Updated' };
    mockPut.mockResolvedValue(json({ success: true, data: { id: 1, ...data } }));
    const r = await updateContact(1, data);
    expect(mockPut).toHaveBeenCalledWith('/api/contacts/1', data);
    expect(r.data.company_name).toBe('Acme Updated');
  });

  it('deleteContact sends delete', async () => {
    mockDelete.mockResolvedValue(json({ success: true }));
    const r = await deleteContact(1);
    expect(mockDelete).toHaveBeenCalledWith('/api/contacts/1');
    expect(r.success).toBe(true);
  });

  it('getContactTypes fetches types', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: ['client', 'supplier'] }));
    const r = await getContactTypes();
    expect(mockGet).toHaveBeenCalledWith('/api/contacts/types');
    expect(r.data).toEqual(['client', 'supplier']);
  });
});
