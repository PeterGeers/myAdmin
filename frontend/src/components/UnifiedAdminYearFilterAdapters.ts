/**
 * Filter State Adapter Utilities for UnifiedAdminYearFilter
 * 
 * This module provides adapter functions to integrate the UnifiedAdminYearFilter component
 * with existing filter state structures used throughout myAdmin Reports.
 * 
 * Requirements: 3.2, 3.4
 */

import { AdministrationOption } from './UnifiedAdminYearFilter';

// ============================================================================
// Type Definitions for Existing Filter Structures
// ============================================================================

export interface ActualsFilters {
  years: string[];
  administration: string;
  displayFormat: string;
}

export interface BtwFilters {
  administration: string;
  year: string;
  quarter: string;
}

export interface RefAnalysisFilters {
  years: string[];
  administration: string;
  referenceNumber: string;
  accounts: string[];
}

export interface AangifteIbFilters {
  year: string;
  administration: string;
}

export interface BnbActualsFilters {
  years: string[];
  listings: string;
  channels: string;
  period: string;
  displayFormat: string;
  viewType: string;
  selectedAmounts: string[];
}

export interface BnbViolinFilters {
  years: string[];
  listings: string;
  channels: string;
  metric: string;
}

// ============================================================================
// Adapter Function Types
// ============================================================================

export interface FilterAdapter {
  administrationValue: string;
  onAdministrationChange: (value: string) => void;
  administrationOptions: AdministrationOption[];
  yearValues: string[];
  onYearChange: (values: string[]) => void;
  availableYears: string[];
  multiSelectYears: boolean;
  showAdministration: boolean;
  showYears: boolean;
}

export type ActualsFilterSetter = (filters: ActualsFilters | ((prev: ActualsFilters) => ActualsFilters)) => void;
export type BtwFilterSetter = (filters: BtwFilters | ((prev: BtwFilters) => BtwFilters)) => void;
export type RefAnalysisFilterSetter = (filters: RefAnalysisFilters | ((prev: RefAnalysisFilters) => RefAnalysisFilters)) => void;
export type AangifteIbFilterSetter = (filters: AangifteIbFilters | ((prev: AangifteIbFilters) => AangifteIbFilters)) => void;
export type BnbActualsFilterSetter = (filters: BnbActualsFilters | ((prev: BnbActualsFilters) => BnbActualsFilters)) => void;
export type BnbViolinFilterSetter = (filters: BnbViolinFilters | ((prev: BnbViolinFilters) => BnbViolinFilters)) => void;

// ============================================================================
// Standard Administration Options
// ============================================================================

const STANDARD_ADMINISTRATION_OPTIONS: AdministrationOption[] = [
  { value: 'all', label: 'All' },
  { value: 'GoodwinSolutions', label: 'GoodwinSolutions' },
  { value: 'PeterPrive', label: 'PeterPrive' },
];

const BTW_ADMINISTRATION_OPTIONS: AdministrationOption[] = [
  { value: 'GoodwinSolutions', label: 'GoodwinSolutions' },
  { value: 'PeterPrive', label: 'PeterPrive' },
];

// ============================================================================
// Actuals Filters Adapter
// ============================================================================

/**
 * Creates an adapter for actualsFilters integration with multi-select years
 * and full administration options including "all".
 * 
 * @param filters Current actuals filter state
 * @param setFilters Function to update actuals filter state
 * @param availableYears Array of available years for selection
 * @returns FilterAdapter configuration for UnifiedAdminYearFilter
 */
const createActualsFilterAdapter = (
  filters: ActualsFilters,
  setFilters: ActualsFilterSetter,
  availableYears: string[]
): FilterAdapter => {
  return {
    administrationValue: filters.administration,
    onAdministrationChange: (value: string) => {
      setFilters((prev) => ({ ...prev, administration: value }));
    },
    administrationOptions: STANDARD_ADMINISTRATION_OPTIONS,
    yearValues: filters.years,
    onYearChange: (values: string[]) => {
      setFilters((prev) => ({ ...prev, years: values }));
    },
    availableYears,
    multiSelectYears: true,
    showAdministration: true,
    showYears: true,
  };
};

// ============================================================================
// BTW Filters Adapter
// ============================================================================

/**
 * Creates an adapter for btwFilters integration with single-select year
 * and limited administration options (no "all" option).
 * 
 * @param filters Current BTW filter state
 * @param setFilters Function to update BTW filter state
 * @param availableYears Array of available years for selection
 * @returns FilterAdapter configuration for UnifiedAdminYearFilter
 */
const createBtwFilterAdapter = (
  filters: BtwFilters,
  setFilters: BtwFilterSetter,
  availableYears: string[]
): FilterAdapter => {
  return {
    administrationValue: filters.administration,
    onAdministrationChange: (value: string) => {
      setFilters((prev) => ({ ...prev, administration: value }));
    },
    administrationOptions: BTW_ADMINISTRATION_OPTIONS,
    yearValues: [filters.year],
    onYearChange: (values: string[]) => {
      // BTW uses single year selection, so take the first value
      const year = values.length > 0 ? values[0] : new Date().getFullYear().toString();
      setFilters((prev) => ({ ...prev, year }));
    },
    availableYears,
    multiSelectYears: false, // Single select for BTW
    showAdministration: true,
    showYears: true,
  };
};

// ============================================================================
// Reference Analysis Filters Adapter
// ============================================================================

/**
 * Creates an adapter for refAnalysisFilters integration with multi-select years
 * and full administration options including "all".
 * 
 * @param filters Current reference analysis filter state
 * @param setFilters Function to update reference analysis filter state
 * @param availableYears Array of available years for selection
 * @returns FilterAdapter configuration for UnifiedAdminYearFilter
 */
const createRefAnalysisFilterAdapter = (
  filters: RefAnalysisFilters,
  setFilters: RefAnalysisFilterSetter,
  availableYears: string[]
): FilterAdapter => {
  return {
    administrationValue: filters.administration,
    onAdministrationChange: (value: string) => {
      setFilters((prev) => ({ ...prev, administration: value }));
    },
    administrationOptions: STANDARD_ADMINISTRATION_OPTIONS,
    yearValues: filters.years,
    onYearChange: (values: string[]) => {
      setFilters((prev) => ({ ...prev, years: values }));
    },
    availableYears,
    multiSelectYears: true,
    showAdministration: true,
    showYears: true,
  };
};

// ============================================================================
// Aangifte IB Filters Adapter
// ============================================================================

/**
 * Creates an adapter for aangifteIbFilters integration with single-select year
 * and full administration options including "all".
 * 
 * @param filters Current Aangifte IB filter state
 * @param setFilters Function to update Aangifte IB filter state
 * @param availableYears Array of available years for selection
 * @returns FilterAdapter configuration for UnifiedAdminYearFilter
 */
const createAangifteIbFilterAdapter = (
  filters: AangifteIbFilters,
  setFilters: AangifteIbFilterSetter,
  availableYears: string[]
): FilterAdapter => {
  return {
    administrationValue: filters.administration,
    onAdministrationChange: (value: string) => {
      setFilters((prev) => ({ ...prev, administration: value }));
    },
    administrationOptions: STANDARD_ADMINISTRATION_OPTIONS,
    yearValues: [filters.year],
    onYearChange: (values: string[]) => {
      // Aangifte IB uses single year selection, so take the first value
      const year = values.length > 0 ? values[0] : new Date().getFullYear().toString();
      setFilters((prev) => ({ ...prev, year }));
    },
    availableYears,
    multiSelectYears: false, // Single select for Aangifte IB
    showAdministration: true,
    showYears: true,
  };
};

// ============================================================================
// BNB Filters Adapters (Years-only)
// ============================================================================

/**
 * Creates an adapter for bnbActualsFilters integration with multi-select years only.
 * Administration section is hidden as BNB filters don't use administration filtering.
 * 
 * @param filters Current BNB actuals filter state
 * @param setFilters Function to update BNB actuals filter state
 * @param availableYears Array of available years for selection
 * @returns FilterAdapter configuration for UnifiedAdminYearFilter
 */
const createBnbActualsFilterAdapter = (
  filters: BnbActualsFilters,
  setFilters: BnbActualsFilterSetter,
  availableYears: string[]
): FilterAdapter => {
  return {
    administrationValue: '', // Not used for BNB
    onAdministrationChange: () => {}, // No-op for BNB
    administrationOptions: [],
    yearValues: filters.years,
    onYearChange: (values: string[]) => {
      setFilters((prev) => ({ ...prev, years: values }));
    },
    availableYears,
    multiSelectYears: true,
    showAdministration: false, // Hide administration section for BNB
    showYears: true,
  };
};

/**
 * Creates an adapter for bnbViolinFilters integration with multi-select years only.
 * Administration section is hidden as BNB filters don't use administration filtering.
 * 
 * @param filters Current BNB violin filter state
 * @param setFilters Function to update BNB violin filter state
 * @param availableYears Array of available years for selection
 * @returns FilterAdapter configuration for UnifiedAdminYearFilter
 */
const createBnbViolinFilterAdapter = (
  filters: BnbViolinFilters,
  setFilters: BnbViolinFilterSetter,
  availableYears: string[]
): FilterAdapter => {
  return {
    administrationValue: '', // Not used for BNB
    onAdministrationChange: () => {}, // No-op for BNB
    administrationOptions: [],
    yearValues: filters.years,
    onYearChange: (values: string[]) => {
      setFilters((prev) => ({ ...prev, years: values }));
    },
    availableYears,
    multiSelectYears: true,
    showAdministration: false, // Hide administration section for BNB
    showYears: true,
  };
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Validates that a filter adapter configuration is properly set up
 * 
 * @param adapter FilterAdapter configuration to validate
 * @returns boolean indicating if the adapter is valid
 */
const validateFilterAdapter = (adapter: FilterAdapter): boolean => {
  // Check required properties exist
  if (!adapter.onAdministrationChange || !adapter.onYearChange) {
    return false;
  }

  // Check administration configuration consistency
  if (adapter.showAdministration) {
    if (!adapter.administrationOptions || adapter.administrationOptions.length === 0) {
      return false;
    }
    if (!adapter.administrationValue && adapter.administrationOptions.length > 0) {
      // Administration value should be set if options are available
      return false;
    }
  }

  // Check year configuration consistency
  if (adapter.showYears) {
    if (!adapter.availableYears || adapter.availableYears.length === 0) {
      return false;
    }
    if (!adapter.multiSelectYears && adapter.yearValues.length > 1) {
      // Single select should not have multiple values
      return false;
    }
  }

  return true;
};

/**
 * Creates a partial adapter configuration for components that only need year filtering
 * 
 * @param yearValues Current selected years
 * @param onYearChange Function to handle year changes
 * @param availableYears Array of available years
 * @param multiSelect Whether to allow multiple year selection
 * @returns Partial FilterAdapter configuration
 */
const createYearOnlyAdapter = (
  yearValues: string[],
  onYearChange: (values: string[]) => void,
  availableYears: string[],
  multiSelect: boolean = true
): Partial<FilterAdapter> => {
  return {
    administrationValue: '',
    onAdministrationChange: () => {}, // No-op
    administrationOptions: [],
    yearValues,
    onYearChange,
    availableYears,
    multiSelectYears: multiSelect,
    showAdministration: false,
    showYears: true,
  };
};

/**
 * Creates a partial adapter configuration for components that only need administration filtering
 * 
 * @param administrationValue Current selected administration
 * @param onAdministrationChange Function to handle administration changes
 * @param administrationOptions Available administration options
 * @returns Partial FilterAdapter configuration
 */
const createAdministrationOnlyAdapter = (
  administrationValue: string,
  onAdministrationChange: (value: string) => void,
  administrationOptions: AdministrationOption[] = STANDARD_ADMINISTRATION_OPTIONS
): Partial<FilterAdapter> => {
  return {
    administrationValue,
    onAdministrationChange,
    administrationOptions,
    yearValues: [],
    onYearChange: () => {}, // No-op
    availableYears: [],
    multiSelectYears: false,
    showAdministration: true,
    showYears: false,
  };
};

// ============================================================================
// Export all adapter functions and types
// ============================================================================

export {
    BTW_ADMINISTRATION_OPTIONS, STANDARD_ADMINISTRATION_OPTIONS, createAangifteIbFilterAdapter,
    createActualsFilterAdapter,
    createAdministrationOnlyAdapter,
    createBnbActualsFilterAdapter,
    createBnbViolinFilterAdapter,
    createBtwFilterAdapter,
    createRefAnalysisFilterAdapter,
    createYearOnlyAdapter,
    validateFilterAdapter
};

