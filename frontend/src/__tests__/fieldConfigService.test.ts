/**
 * Tests for Field Config Service API calls.
 */
import { getFieldConfig, updateFieldConfig } from '../services/fieldConfigService';

const mockGet = jest.fn();
const mockPut = jest.fn();

jest.mock('../services/apiService', () => ({
  authenticatedGet: (...args: any[]) => mockGet(...args),
  authenticatedPut: (...args: any[]) => mockPut(...args),
  buildEndpoint: (endpoint: string) => endpoint,
}));

const json = (data: any) => ({ json: async () => data });

describe('Field Config Service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('getFieldConfig fetches config for contacts', async () => {
    const config = { client_id: 'required', company_name: 'required', vat_number: 'hidden' };
    mockGet.mockResolvedValue(json({ success: true, data: config }));
    const r = await getFieldConfig('contacts');
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/field-config/contacts');
    expect(r.data.client_id).toBe('required');
    expect(r.data.vat_number).toBe('hidden');
  });

  it('getFieldConfig fetches config for products', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: {} }));
    await getFieldConfig('products');
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/field-config/products');
  });

  it('getFieldConfig fetches config for time_entries', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: {} }));
    await getFieldConfig('time_entries');
    expect(mockGet).toHaveBeenCalledWith('/api/zzp/field-config/time_entries');
  });

  it('updateFieldConfig puts config for contacts', async () => {
    const config = { client_id: 'required', vat_number: 'optional' };
    mockPut.mockResolvedValue(json({ success: true }));
    const r = await updateFieldConfig('contacts', config as any);
    expect(mockPut).toHaveBeenCalledWith('/api/zzp/field-config/contacts', config);
    expect(r.success).toBe(true);
  });
});
