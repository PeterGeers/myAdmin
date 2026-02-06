/**
 * YearFilter Component
 * 
 * A specialized filter component for year selection, built as a wrapper around GenericFilter.
 * Supports both single-select and multi-select modes for different use cases.
 * 
 * @module filters/YearFilter
 */

import React from 'react';
import { GenericFilter, GenericFilterProps } from './GenericFilter';
import { generateYearOptions } from './utils/yearGenerator';
import { YearGenerationConfig } from './types';

/**
 * Year filter props interface
 * Extends GenericFilter props with year-specific defaults and configuration
 */
export interface YearFilterProps extends Omit<GenericFilterProps<string>, 'label' | 'placeholder' | 'getOptionLabel' | 'getOptionValue'> {
  /** Custom label (default: "Year") */
  label?: string;
  
  /** Custom placeholder (default: "Select year(s)" for multi-select, "Select year" for single-select) */
  placeholder?: string;
  
  /** Optional year generation configuration for dynamic year options */
  yearConfig?: YearGenerationConfig;
}

/**
 * YearFilter - Specialized filter component for year selection
 * 
 * A wrapper around GenericFilter<string> that provides year-specific defaults
 * and optional dynamic year generation. Supports both single and multi-select modes.
 * 
 * **Single-Select Mode** (multiSelect=false):
 * - Used in BTW Report (single year + quarter selection)
 * - Used in Aangifte IB Report (single year selection)
 * - Renders as a dropdown select
 * 
 * **Multi-Select Mode** (multiSelect=true):
 * - Used in Actuals Report (multiple years for comparison)
 * - Used in BNB Reports (multiple years for analysis)
 * - Renders as a checkbox menu
 * 
 * @example
 * // Single-select year filter (BTW Report)
 * <YearFilter
 *   values={selectedYear ? [selectedYear] : []}
 *   onChange={(values) => setSelectedYear(values[0] || '')}
 *   availableOptions={['2022', '2023', '2024', '2025']}
 * />
 * 
 * @example
 * // Multi-select year filter (Actuals Report)
 * <YearFilter
 *   values={selectedYears}
 *   onChange={setSelectedYears}
 *   availableOptions={['2022', '2023', '2024', '2025']}
 *   multiSelect
 * />
 * 
 * @example
 * // With dynamic year generation (historical + future)
 * <YearFilter
 *   values={selectedYears}
 *   onChange={setSelectedYears}
 *   availableOptions={[]}
 *   multiSelect
 *   yearConfig={{
 *     mode: 'combined',
 *     historicalYears: historicalYears,
 *     futureCount: 2
 *   }}
 * />
 * 
 * @example
 * // With loading state
 * <YearFilter
 *   values={selectedYears}
 *   onChange={setSelectedYears}
 *   availableOptions={years}
 *   isLoading={isLoadingYears}
 *   multiSelect
 * />
 */
export function YearFilter({
  label,
  placeholder,
  multiSelect = false,
  availableOptions,
  yearConfig,
  ...rest
}: YearFilterProps): React.ReactElement {
  // Generate default label
  const defaultLabel = label || 'Year';
  
  // Generate default placeholder based on mode
  const defaultPlaceholder = placeholder || (multiSelect ? 'Select year(s)' : 'Select year');
  
  // Generate year options if yearConfig is provided
  const yearOptions = React.useMemo(() => {
    if (yearConfig) {
      return generateYearOptions(yearConfig);
    }
    return availableOptions;
  }, [yearConfig, availableOptions]);
  
  return (
    <GenericFilter<string>
      {...rest}
      label={defaultLabel}
      placeholder={defaultPlaceholder}
      multiSelect={multiSelect}
      availableOptions={yearOptions}
      // Year options are already strings, so we can use default label/value extractors
      getOptionLabel={(year) => year}
      getOptionValue={(year) => year}
    />
  );
}

export default YearFilter;
