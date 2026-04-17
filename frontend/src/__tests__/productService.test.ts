/**
 * Tests for Product Service API calls.
 */
import {
  getProducts, getProduct, createProduct, updateProduct,
  deleteProduct, getProductTypes,
} from '../services/productService';

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

describe('Product Service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('getProducts without includeInactive', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    await getProducts();
    expect(mockGet).toHaveBeenCalledWith('/api/products');
  });

  it('getProducts with includeInactive', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: [] }));
    await getProducts(true);
    expect(mockGet.mock.calls[0][0]).toContain('include_inactive=true');
  });

  it('getProduct by id', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: { id: 3 } }));
    const r = await getProduct(3);
    expect(mockGet).toHaveBeenCalledWith('/api/products/3');
    expect(r.data.id).toBe(3);
  });

  it('createProduct posts data', async () => {
    const data = { product_code: 'DEV-HR', name: 'Development', unit_price: 95 };
    mockPost.mockResolvedValue(json({ success: true, data: { id: 1, ...data } }));
    const r = await createProduct(data);
    expect(mockPost).toHaveBeenCalledWith('/api/products', data);
    expect(r.data.product_code).toBe('DEV-HR');
  });

  it('updateProduct puts data', async () => {
    const data = { unit_price: 100 };
    mockPut.mockResolvedValue(json({ success: true, data: { id: 1, ...data } }));
    const r = await updateProduct(1, data);
    expect(mockPut).toHaveBeenCalledWith('/api/products/1', data);
    expect(r.data.unit_price).toBe(100);
  });

  it('deleteProduct sends delete', async () => {
    mockDelete.mockResolvedValue(json({ success: true }));
    const r = await deleteProduct(1);
    expect(mockDelete).toHaveBeenCalledWith('/api/products/1');
    expect(r.success).toBe(true);
  });

  it('getProductTypes fetches types', async () => {
    mockGet.mockResolvedValue(json({ success: true, data: ['service', 'product'] }));
    const r = await getProductTypes();
    expect(mockGet).toHaveBeenCalledWith('/api/products/types');
    expect(r.data).toEqual(['service', 'product']);
  });
});
