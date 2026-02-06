/**
 * Filter Type Definitions
 * 
 * This module provides TypeScript type definitions for the generic filter system.
 * These types enable type-safe filter configurations across the application.
 * 
 * @module filters/types
 */

/**
 * Filter type enumeration
 * Defines the available filter interaction modes
 */
export type FilterType = 'single' | 'multi' | 'range' | 'search';

/**
 * Base filter configuration interface
 * 
 * @template T - The type of data being filtered (e.g., string, object)
 * 
 * @example
 * ```typescript
 * // String filter
 * const yearFilter: FilterConfig<string> = {
 *   type: 'multi',
 *   label: 'Years',
 *   options: ['2023', '2024', '2025'],
 *   value: ['2023', '2024'],
 *   onChange: (values) => setSelectedYears(values)
 * };
 * 
 * // Object filter
 * interface Listing {
 *   id: string;
 *   name: string;
 *   address: string;
 * }
 * 
 * const listingFilter: FilterConfig<Listing> = {
 *   type: 'multi',
 *   label: 'Listings',
 *   options: listings,
 *   value: selectedListings,
 *   onChange: setSelectedListings,
 *   renderOption: (listing) => `${listing.name} - ${listing.address}`
 * };
 * ```
 */
export interface FilterConfig<T> {
  /** Filter interaction type */
  type: FilterType;
  
  /** Display label for the filter */
  label: string;
  
  /** Available options to select from */
  options: T[];
  
  /** Current selected value(s) - single value or array depending on type */
  value: T | T[];
  
  /** Callback when selection changes */
  onChange: (value: T | T[]) => void;
  
  /** Optional custom renderer for options */
  renderOption?: (option: T) => React.ReactNode;
  
  /** Optional function to extract display label from option */
  getOptionLabel?: (option: T) => string;
  
  /** Optional function to extract unique value from option */
  getOptionValue?: (option: T) => string;
  
  /** Optional placeholder text */
  placeholder?: string;
  
  /** Optional size variant */
  size?: 'sm' | 'md' | 'lg';
  
  /** Optional disabled state */
  disabled?: boolean;
  
  /** Optional loading state */
  isLoading?: boolean;
  
  /** Optional error message */
  error?: string | null;
}

/**
 * Single-select filter configuration
 * 
 * Type-safe variant that enforces single value selection.
 * Use this when only one option can be selected at a time.
 * 
 * @template T - The type of data being filtered
 * 
 * @example
 * ```typescript
 * // Single year selection (BTW report)
 * const btwYearFilter: SingleSelectFilterConfig<string> = {
 *   type: 'single',
 *   label: 'Year',
 *   options: ['2023', '2024', '2025'],
 *   value: '2024',
 *   onChange: (year) => setSelectedYear(year)
 * };
 * 
 * // Single ledger account selection
 * interface LedgerAccount {
 *   code: string;
 *   name: string;
 * }
 * 
 * const ledgerFilter: SingleSelectFilterConfig<LedgerAccount> = {
 *   type: 'single',
 *   label: 'Ledger Account',
 *   options: ledgerAccounts,
 *   value: selectedAccount,
 *   onChange: setSelectedAccount,
 *   getOptionLabel: (account) => `${account.code} - ${account.name}`
 * };
 * ```
 */
export interface SingleSelectFilterConfig<T> extends Omit<FilterConfig<T>, 'type' | 'value' | 'onChange'> {
  /** Filter type - always 'single' */
  type: 'single';
  
  /** Single selected value */
  value: T;
  
  /** Callback when selection changes - receives single value */
  onChange: (value: T) => void;
}

/**
 * Multi-select filter configuration
 * 
 * Type-safe variant that enforces array value selection.
 * Use this when multiple options can be selected simultaneously.
 * 
 * @template T - The type of data being filtered
 * 
 * @example
 * ```typescript
 * // Multi-year selection (Actuals report)
 * const actualsYearFilter: MultiSelectFilterConfig<string> = {
 *   type: 'multi',
 *   label: 'Years',
 *   options: ['2022', '2023', '2024', '2025'],
 *   value: ['2023', '2024'],
 *   onChange: (years) => setSelectedYears(years)
 * };
 * 
 * // Multi-listing selection (BNB report)
 * interface Listing {
 *   id: string;
 *   name: string;
 *   address: string;
 * }
 * 
 * const listingFilter: MultiSelectFilterConfig<Listing> = {
 *   type: 'multi',
 *   label: 'Listings',
 *   options: listings,
 *   value: selectedListings,
 *   onChange: setSelectedListings,
 *   renderOption: (listing) => (
 *     <Box>
 *       <Text fontWeight="bold">{listing.name}</Text>
 *       <Text fontSize="sm">{listing.address}</Text>
 *     </Box>
 *   )
 * };
 * ```
 */
export interface MultiSelectFilterConfig<T> extends Omit<FilterConfig<T>, 'type' | 'value' | 'onChange'> {
  /** Filter type - always 'multi' */
  type: 'multi';
  
  /** Array of selected values */
  value: T[];
  
  /** Callback when selection changes - receives array of values */
  onChange: (values: T[]) => void;
}

/**
 * Range filter configuration
 * 
 * Type-safe variant for range-based filtering (e.g., date ranges, numeric ranges).
 * 
 * @template T - The type of data being filtered (typically number or Date)
 * 
 * @example
 * ```typescript
 * // Date range filter
 * const dateRangeFilter: RangeFilterConfig<Date> = {
 *   type: 'range',
 *   label: 'Date Range',
 *   value: { min: startDate, max: endDate },
 *   onChange: ({ min, max }) => {
 *     setStartDate(min);
 *     setEndDate(max);
 *   }
 * };
 * 
 * // Amount range filter
 * const amountRangeFilter: RangeFilterConfig<number> = {
 *   type: 'range',
 *   label: 'Amount',
 *   value: { min: 0, max: 10000 },
 *   onChange: ({ min, max }) => setAmountRange({ min, max })
 * };
 * ```
 */
export interface RangeFilterConfig<T> extends Omit<FilterConfig<T>, 'type' | 'value' | 'onChange' | 'options'> {
  /** Filter type - always 'range' */
  type: 'range';
  
  /** Range value with min and max */
  value: { min: T; max: T };
  
  /** Callback when range changes */
  onChange: (value: { min: T; max: T }) => void;
  
  /** Optional minimum allowed value */
  minValue?: T;
  
  /** Optional maximum allowed value */
  maxValue?: T;
}

/**
 * Search filter configuration
 * 
 * Type-safe variant for text-based search filtering.
 * 
 * @example
 * ```typescript
 * // Reference number search
 * const referenceSearchFilter: SearchFilterConfig = {
 *   type: 'search',
 *   label: 'Reference Number',
 *   value: searchTerm,
 *   onChange: setSearchTerm,
 *   placeholder: 'Search by reference...'
 * };
 * 
 * // Description search with debounce
 * const descriptionSearchFilter: SearchFilterConfig = {
 *   type: 'search',
 *   label: 'Description',
 *   value: description,
 *   onChange: setDescription,
 *   placeholder: 'Search descriptions...',
 *   debounceMs: 300
 * };
 * ```
 */
export interface SearchFilterConfig extends Omit<FilterConfig<string>, 'type' | 'value' | 'onChange' | 'options'> {
  /** Filter type - always 'search' */
  type: 'search';
  
  /** Current search term */
  value: string;
  
  /** Callback when search term changes */
  onChange: (value: string) => void;
  
  /** Optional debounce delay in milliseconds */
  debounceMs?: number;
  
  /** Optional minimum character count before triggering search */
  minChars?: number;
}

/**
 * Filter panel layout options
 */
export type FilterPanelLayout = 'horizontal' | 'vertical' | 'grid';

/**
 * Filter panel configuration
 * 
 * Container configuration for multiple filters.
 * 
 * @example
 * ```typescript
 * const filterPanelConfig: FilterPanelConfig = {
 *   filters: [
 *     {
 *       type: 'multi',
 *       label: 'Years',
 *       options: ['2023', '2024', '2025'],
 *       value: selectedYears,
 *       onChange: setSelectedYears
 *     },
 *     {
 *       type: 'single',
 *       label: 'Quarter',
 *       options: ['Q1', 'Q2', 'Q3', 'Q4'],
 *       value: selectedQuarter,
 *       onChange: setSelectedQuarter
 *     }
 *   ],
 *   layout: 'horizontal',
 *   size: 'md'
 * };
 * ```
 */
export interface FilterPanelConfig {
  /** Array of filter configurations */
  filters: FilterConfig<any>[];
  
  /** Layout mode for the filter panel */
  layout?: FilterPanelLayout;
  
  /** Size variant for all filters */
  size?: 'sm' | 'md' | 'lg';
  
  /** Optional spacing between filters */
  spacing?: number;
  
  /** Optional disabled state for all filters */
  disabled?: boolean;
}

/**
 * Year generation mode for dynamic year options
 */
export type YearGenerationMode = 'historical' | 'future' | 'combined' | 'rolling';

/**
 * Year generation configuration
 * 
 * Configuration for generating year options dynamically.
 * 
 * @example
 * ```typescript
 * // Historical years only (from database)
 * const historicalConfig: YearGenerationConfig = {
 *   mode: 'historical',
 *   historicalYears: ['2022', '2023', '2024']
 * };
 * 
 * // Future years for planning
 * const futureConfig: YearGenerationConfig = {
 *   mode: 'future',
 *   futureCount: 3  // Current + next 3 years
 * };
 * 
 * // Combined past and future
 * const combinedConfig: YearGenerationConfig = {
 *   mode: 'combined',
 *   historicalYears: ['2022', '2023', '2024'],
 *   futureCount: 2  // + next 2 years
 * };
 * 
 * // Rolling window
 * const rollingConfig: YearGenerationConfig = {
 *   mode: 'rolling',
 *   pastCount: 3,    // Last 3 years
 *   futureCount: 2   // + current + next 2 years
 * };
 * ```
 */
export interface YearGenerationConfig {
  /** Year generation mode */
  mode: YearGenerationMode;
  
  /** Historical years from database (for 'historical' and 'combined' modes) */
  historicalYears?: string[];
  
  /** Number of future years to generate (for 'future', 'combined', and 'rolling' modes) */
  futureCount?: number;
  
  /** Number of past years to include (for 'rolling' mode) */
  pastCount?: number;
}

/**
 * Filter option with label and value
 * 
 * Generic option type for filters that need separate display and value.
 * 
 * @template T - The type of the option value
 * 
 * @example
 * ```typescript
 * const administrationOptions: FilterOption<string>[] = [
 *   { value: 'all', label: 'All Administrations' },
 *   { value: 'goodwin', label: 'Goodwin Solutions' },
 *   { value: 'peter', label: 'Peter Prive' }
 * ];
 * ```
 */
export interface FilterOption<T> {
  /** Unique value for the option */
  value: T;
  
  /** Display label for the option */
  label: string;
  
  /** Optional disabled state */
  disabled?: boolean;
  
  /** Optional description or help text */
  description?: string;
}
