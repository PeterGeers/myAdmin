/**
 * Tenant Validation Hook
 * 
 * Provides standardized tenant validation utilities for components
 * that need to validate tenant selection and data ownership.
 */

import { useTenant } from '../context/TenantContext';

export interface DataOwnershipResult {
  isValid: boolean;
  reason?: string;
}

export interface LookupData {
  bank_accounts?: Array<{ rekeningNummer: string; [key: string]: any }>;
  [key: string]: any;
}

/**
 * Hook for tenant validation utilities
 */
export function useTenantValidation() {
  const { currentTenant } = useTenant();
  
  /**
   * Validates that a tenant is currently selected
   * @throws Error if no tenant is selected
   * @returns Current tenant string
   */
  const validateTenantSelection = (): string => {
    if (!currentTenant) {
      throw new Error('No tenant selected. Please select a tenant first.');
    }
    return currentTenant;
  };
  
  /**
   * Validates that banking data (IBAN) belongs to current tenant
   * @param iban - The IBAN to validate
   * @param lookupData - Lookup data containing bank accounts
   * @param fileName - Optional file name for error messages
   * @returns Validation result
   */
  const validateBankingDataOwnership = (
    iban: string, 
    lookupData: LookupData, 
    fileName?: string
  ): DataOwnershipResult => {
    if (!currentTenant) {
      return {
        isValid: false,
        reason: 'No tenant selected. Please select a tenant first.'
      };
    }
    
    if (!iban) {
      return {
        isValid: false,
        reason: 'No IBAN found in data.'
      };
    }
    
    const bankLookup = lookupData.bank_accounts?.find(
      (ba) => ba.rekeningNummer === iban
    );
    
    if (!bankLookup) {
      const fileRef = fileName ? ` in file "${fileName}"` : '';
      return {
        isValid: false,
        reason: `Access denied: The bank account ${iban}${fileRef} does not belong to your current organization.`
      };
    }
    
    return { isValid: true };
  };
  
  /**
   * Validates that administration parameter matches current tenant
   * @param administration - Administration to validate
   * @returns Validation result
   */
  const validateAdministrationAccess = (administration: string): DataOwnershipResult => {
    if (!currentTenant) {
      return {
        isValid: false,
        reason: 'No tenant selected. Please select a tenant first.'
      };
    }
    
    if (administration !== currentTenant && administration !== 'all') {
      return {
        isValid: false,
        reason: `Access denied: You do not have permission to access data for ${administration}.`
      };
    }
    
    return { isValid: true };
  };
  
  /**
   * Gets current tenant from localStorage (fallback method)
   * @returns Current tenant or null
   */
  const getCurrentTenantFromStorage = (): string | null => {
    return localStorage.getItem('selectedTenant');
  };
  
  return {
    currentTenant,
    validateTenantSelection,
    validateBankingDataOwnership,
    validateAdministrationAccess,
    getCurrentTenantFromStorage
  };
}