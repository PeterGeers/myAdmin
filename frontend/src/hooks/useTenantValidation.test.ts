/**
 * Tests for useTenantValidation hook
 */

import { renderHook } from '@testing-library/react';
import { useTenantValidation } from './useTenantValidation';

// Mock the tenant context
const mockUseTenant = jest.fn();
jest.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant()
}));

describe('useTenantValidation', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  describe('validateTenantSelection', () => {
    it('should return current tenant when tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      const { result } = renderHook(() => useTenantValidation());
      const tenant = result.current.validateTenantSelection();
      
      expect(tenant).toBe('GoodwinSolutions');
    });

    it('should throw error when no tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null
      });

      const { result } = renderHook(() => useTenantValidation());
      
      expect(() => result.current.validateTenantSelection()).toThrow(
        'No tenant selected. Please select a tenant first.'
      );
    });
  });

  describe('validateBankingDataOwnership', () => {
    const mockLookupData = {
      bank_accounts: [
        { rekeningNummer: 'NL91ABNA0417164300', administration: 'GoodwinSolutions' },
        { rekeningNummer: 'NL08REVO7549383472', administration: 'GoodwinSolutions' }
      ]
    };

    it('should validate successfully when IBAN belongs to current tenant', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      const { result } = renderHook(() => useTenantValidation());
      const validation = result.current.validateBankingDataOwnership(
        'NL91ABNA0417164300',
        mockLookupData
      );
      
      expect(validation.isValid).toBe(true);
      expect(validation.reason).toBeUndefined();
    });

    it('should fail validation when IBAN does not belong to current tenant', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      const { result } = renderHook(() => useTenantValidation());
      const validation = result.current.validateBankingDataOwnership(
        'NL00UNKNOWN0000000000',
        mockLookupData,
        'test.csv'
      );
      
      expect(validation.isValid).toBe(false);
      expect(validation.reason).toContain('Access denied');
      expect(validation.reason).toContain('NL00UNKNOWN0000000000');
      expect(validation.reason).toContain('test.csv');
    });

    it('should fail validation when no tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null
      });

      const { result } = renderHook(() => useTenantValidation());
      const validation = result.current.validateBankingDataOwnership(
        'NL91ABNA0417164300',
        mockLookupData
      );
      
      expect(validation.isValid).toBe(false);
      expect(validation.reason).toBe('No tenant selected. Please select a tenant first.');
    });

    it('should fail validation when no IBAN is provided', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      const { result } = renderHook(() => useTenantValidation());
      const validation = result.current.validateBankingDataOwnership(
        '',
        mockLookupData
      );
      
      expect(validation.isValid).toBe(false);
      expect(validation.reason).toBe('No IBAN found in data.');
    });
  });

  describe('validateAdministrationAccess', () => {
    it('should validate successfully when administration matches current tenant', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      const { result } = renderHook(() => useTenantValidation());
      const validation = result.current.validateAdministrationAccess('GoodwinSolutions');
      
      expect(validation.isValid).toBe(true);
    });

    it('should validate successfully when administration is "all"', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      const { result } = renderHook(() => useTenantValidation());
      const validation = result.current.validateAdministrationAccess('all');
      
      expect(validation.isValid).toBe(true);
    });

    it('should fail validation when administration does not match current tenant', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      const { result } = renderHook(() => useTenantValidation());
      const validation = result.current.validateAdministrationAccess('PeterPrive');
      
      expect(validation.isValid).toBe(false);
      expect(validation.reason).toContain('Access denied');
      expect(validation.reason).toContain('PeterPrive');
    });

    it('should fail validation when no tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null
      });

      const { result } = renderHook(() => useTenantValidation());
      const validation = result.current.validateAdministrationAccess('GoodwinSolutions');
      
      expect(validation.isValid).toBe(false);
      expect(validation.reason).toBe('No tenant selected. Please select a tenant first.');
    });
  });

  describe('getCurrentTenantFromStorage', () => {
    it('should return tenant from localStorage', () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      const { result } = renderHook(() => useTenantValidation());
      const tenant = result.current.getCurrentTenantFromStorage();
      
      expect(tenant).toBe('GoodwinSolutions');
    });

    it('should return null when no tenant in localStorage', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null
      });

      const { result } = renderHook(() => useTenantValidation());
      const tenant = result.current.getCurrentTenantFromStorage();
      
      expect(tenant).toBeNull();
    });
  });
});