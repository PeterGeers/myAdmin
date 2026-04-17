/**
 * Unit tests for downloadDefaultTemplate and deleteTenantTemplate API functions
 *
 * Tests that each function calls the correct endpoint, returns the response,
 * and throws an Error with the server message on non-OK responses.
 */

import { downloadDefaultTemplate, deleteTenantTemplate } from '../templateApi';

// Mock the authenticatedRequest dependency
jest.mock('../apiService', () => ({
  authenticatedRequest: jest.fn(),
}));

import { authenticatedRequest } from '../apiService';

const mockAuthRequest = authenticatedRequest as jest.MockedFunction<typeof authenticatedRequest>;

describe('templateApi - default template functions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('downloadDefaultTemplate', () => {
    const mockResponse = {
      success: true,
      template_type: 'str_invoice_nl',
      template_content: '<html><body>Default</body></html>',
      filename: 'str_invoice_nl_default.html',
      field_mappings: { company_name: 'Company' },
      message: 'Default template retrieved successfully',
    };

    it('calls GET /api/tenant-admin/templates/{type}/default', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      await downloadDefaultTemplate('str_invoice_nl' as any);

      expect(mockAuthRequest).toHaveBeenCalledWith(
        '/api/tenant-admin/templates/str_invoice_nl/default',
        { method: 'GET' }
      );
    });

    it('returns the response on success', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await downloadDefaultTemplate('str_invoice_nl' as any);

      expect(result).toEqual(mockResponse);
      expect(result.filename).toBe('str_invoice_nl_default.html');
      expect(result.template_content).toBe('<html><body>Default</body></html>');
    });

    it('throws Error with server error message on non-OK response', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: false,
        json: async () => ({ error: 'No default template available for type: unknown_type' }),
      } as Response);

      await expect(downloadDefaultTemplate('unknown_type' as any)).rejects.toThrow(
        'No default template available for type: unknown_type'
      );
    });

    it('throws Error with fallback message when server provides message field', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: false,
        json: async () => ({ message: 'Something went wrong' }),
      } as Response);

      await expect(downloadDefaultTemplate('str_invoice_nl' as any)).rejects.toThrow(
        'Something went wrong'
      );
    });

    it('throws default Error when server provides no message', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: false,
        json: async () => ({}),
      } as Response);

      await expect(downloadDefaultTemplate('str_invoice_nl' as any)).rejects.toThrow(
        'Failed to download default template'
      );
    });
  });

  describe('deleteTenantTemplate', () => {
    const mockResponse = {
      success: true,
      message: 'Template deactivated successfully. System will use default template.',
      template_type: 'btw_aangifte',
      deactivated_file_id: '1abc_xyz',
    };

    it('calls DELETE /api/tenant-admin/templates/{type}', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      await deleteTenantTemplate('btw_aangifte' as any);

      expect(mockAuthRequest).toHaveBeenCalledWith(
        '/api/tenant-admin/templates/btw_aangifte',
        { method: 'DELETE' }
      );
    });

    it('returns the response on success', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await deleteTenantTemplate('btw_aangifte' as any);

      expect(result).toEqual(mockResponse);
      expect(result.success).toBe(true);
      expect(result.deactivated_file_id).toBe('1abc_xyz');
    });

    it('throws Error with server error message on non-OK response', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: false,
        json: async () => ({ error: 'No active tenant template found for type: btw_aangifte' }),
      } as Response);

      await expect(deleteTenantTemplate('btw_aangifte' as any)).rejects.toThrow(
        'No active tenant template found for type: btw_aangifte'
      );
    });

    it('throws Error with fallback message when server provides message field', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: false,
        json: async () => ({ message: 'Tenant admin access required' }),
      } as Response);

      await expect(deleteTenantTemplate('btw_aangifte' as any)).rejects.toThrow(
        'Tenant admin access required'
      );
    });

    it('throws default Error when server provides no message', async () => {
      mockAuthRequest.mockResolvedValue({
        ok: false,
        json: async () => ({}),
      } as Response);

      await expect(deleteTenantTemplate('btw_aangifte' as any)).rejects.toThrow(
        'Failed to delete tenant template'
      );
    });
  });
});
