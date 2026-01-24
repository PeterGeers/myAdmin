/**
 * Tenant Context for Multi-Tenant Support
 * 
 * Provides tenant selection state management throughout the app.
 * Manages current tenant selection with localStorage persistence.
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useAuth } from './AuthContext';

/**
 * Tenant context value
 */
interface TenantContextValue {
  // Current tenant state
  currentTenant: string | null;
  availableTenants: string[];
  
  // Tenant selection
  setCurrentTenant: (tenant: string) => void;
  
  // Utility
  hasMultipleTenants: boolean;
}

/**
 * Tenant context
 */
const TenantContext = createContext<TenantContextValue | undefined>(undefined);

/**
 * Props for TenantProvider
 */
interface TenantProviderProps {
  children: ReactNode;
}

/**
 * Tenant Provider Component
 * 
 * Wraps the application to provide tenant selection state.
 * Automatically initializes tenant from localStorage or defaults to first tenant.
 */
export function TenantProvider({ children }: TenantProviderProps) {
  const { user } = useAuth();
  const [currentTenant, setCurrentTenantState] = useState<string | null>(null);

  // Get available tenants from user
  const availableTenants = user?.tenants || [];
  const hasMultipleTenants = availableTenants.length > 1;

  /**
   * Initialize tenant selection on mount or when user changes
   */
  useEffect(() => {
    if (availableTenants.length === 0) {
      setCurrentTenantState(null);
      return;
    }

    // Try to restore from localStorage
    const savedTenant = localStorage.getItem('selectedTenant');
    
    if (savedTenant && availableTenants.includes(savedTenant)) {
      // Use saved tenant if still valid
      setCurrentTenantState(savedTenant);
    } else {
      // Default to first tenant
      setCurrentTenantState(availableTenants[0]);
      localStorage.setItem('selectedTenant', availableTenants[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]); // Only re-run when user changes

  /**
   * Set current tenant and persist to localStorage
   */
  const setCurrentTenant = (tenant: string) => {
    if (!availableTenants.includes(tenant)) {
      console.error(`Tenant ${tenant} not available for user`);
      return;
    }

    setCurrentTenantState(tenant);
    localStorage.setItem('selectedTenant', tenant);
  };

  const value: TenantContextValue = {
    currentTenant,
    availableTenants,
    setCurrentTenant,
    hasMultipleTenants,
  };

  return (
    <TenantContext.Provider value={value}>
      {children}
    </TenantContext.Provider>
  );
}

/**
 * Hook to use tenant context
 * 
 * @throws Error if used outside of TenantProvider
 * @returns Tenant context value
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { currentTenant, availableTenants, setCurrentTenant } = useTenant();
 *   
 *   return (
 *     <div>
 *       <p>Current tenant: {currentTenant}</p>
 *       <select onChange={(e) => setCurrentTenant(e.target.value)}>
 *         {availableTenants.map(t => <option key={t} value={t}>{t}</option>)}
 *       </select>
 *     </div>
 *   );
 * }
 * ```
 */
export function useTenant(): TenantContextValue {
  const context = useContext(TenantContext);
  
  if (context === undefined) {
    throw new Error('useTenant must be used within a TenantProvider');
  }
  
  return context;
}
