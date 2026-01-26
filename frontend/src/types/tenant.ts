/**
 * Tenant-related TypeScript type definitions
 * 
 * Provides standardized types for tenant handling across the application.
 */

/**
 * Result of tenant validation operations
 */
export interface TenantValidationResult {
  isValid: boolean;
  reason?: string;
  tenant?: string;
}

/**
 * Data ownership validation result
 */
export interface DataOwnershipResult {
  isValid: boolean;
  reason?: string;
  owner?: string;
}

/**
 * Tenant-aware filter interface
 */
export interface TenantAwareFilters {
  administration: string;
  [key: string]: any;
}

/**
 * Tenant-aware API response wrapper
 */
export interface TenantAwareResponse<T = any> {
  data: T;
  tenant: string;
  timestamp: string;
}

/**
 * Lookup data structure for tenant validation
 */
export interface TenantLookupData {
  bank_accounts?: Array<{
    rekeningNummer: string;
    administration: string;
    [key: string]: any;
  }>;
  accounts?: Array<{
    id: string;
    administration: string;
    [key: string]: any;
  }>;
  [key: string]: any;
}

/**
 * Tenant module permissions
 */
export interface TenantModulePermissions {
  tenant: string;
  available_modules: string[];
  user_module_permissions: string[];
  tenant_enabled_modules: string[];
}

/**
 * Tenant context value (extends the existing interface)
 */
export interface ExtendedTenantContextValue {
  currentTenant: string | null;
  availableTenants: string[];
  setCurrentTenant: (tenant: string) => void;
  hasMultipleTenants: boolean;
  
  // Extended functionality
  validateTenant: () => TenantValidationResult;
  switchTenant: (tenant: string) => Promise<void>;
  clearTenantData: () => void;
}

/**
 * Component props that require tenant awareness
 */
export interface TenantAwareComponentProps {
  tenant?: string;
  onTenantChange?: (tenant: string) => void;
  requireTenant?: boolean;
}

/**
 * Error types for tenant operations
 */
export enum TenantErrorType {
  NO_TENANT_SELECTED = 'NO_TENANT_SELECTED',
  INVALID_TENANT = 'INVALID_TENANT',
  ACCESS_DENIED = 'ACCESS_DENIED',
  DATA_OWNERSHIP_VIOLATION = 'DATA_OWNERSHIP_VIOLATION',
  TENANT_SWITCH_FAILED = 'TENANT_SWITCH_FAILED'
}

/**
 * Tenant error class
 */
export class TenantError extends Error {
  constructor(
    public type: TenantErrorType,
    message: string,
    public tenant?: string,
    public details?: any
  ) {
    super(message);
    this.name = 'TenantError';
  }
}

/**
 * Tenant audit log entry
 */
export interface TenantAuditEntry {
  timestamp: string;
  tenant: string;
  action: string;
  resource: string;
  user: string;
  success: boolean;
  details?: any;
}