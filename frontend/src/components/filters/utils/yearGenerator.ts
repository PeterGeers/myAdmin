/**
 * Year Generation Utility
 * 
 * Provides flexible year option generation for filter components.
 * Supports multiple modes for different use cases:
 * - Historical: Years from database only
 * - Future: Current year + N future years
 * - Combined: Historical + current + future years
 * - Rolling: Last N years + current + next M years
 * 
 * @module filters/utils/yearGenerator
 */

import { YearGenerationConfig } from '../types';

/**
 * Generate year options based on configuration
 * 
 * @param config - Year generation configuration
 * @returns Array of year strings, sorted in ascending order
 * 
 * @example
 * // Historical years only
 * const years = generateYearOptions({
 *   mode: 'historical',
 *   historicalYears: ['2022', '2023', '2024']
 * });
 * // Returns: ['2022', '2023', '2024']
 * 
 * @example
 * // Future years for planning
 * const years = generateYearOptions({
 *   mode: 'future',
 *   futureCount: 3
 * });
 * // If current year is 2024, returns: ['2024', '2025', '2026', '2027']
 * 
 * @example
 * // Combined historical and future
 * const years = generateYearOptions({
 *   mode: 'combined',
 *   historicalYears: ['2022', '2023'],
 *   futureCount: 2
 * });
 * // If current year is 2024, returns: ['2022', '2023', '2024', '2025', '2026']
 * 
 * @example
 * // Rolling window
 * const years = generateYearOptions({
 *   mode: 'rolling',
 *   pastCount: 2,
 *   futureCount: 1
 * });
 * // If current year is 2024, returns: ['2022', '2023', '2024', '2025']
 */
export function generateYearOptions(config: YearGenerationConfig): string[] {
  const currentYear = new Date().getFullYear();

  switch (config.mode) {
    case 'historical':
      return generateHistoricalYears(config.historicalYears);

    case 'future':
      return generateFutureYears(currentYear, config.futureCount);

    case 'combined':
      return generateCombinedYears(
        currentYear,
        config.historicalYears,
        config.futureCount
      );

    case 'rolling':
      return generateRollingYears(
        currentYear,
        config.pastCount,
        config.futureCount
      );

    default:
      // Exhaustive check - TypeScript will error if we miss a mode
      throw new Error(`Unknown year generation mode: ${(config as any).mode}`);
  }
}

/**
 * Generate historical years only
 * Returns years from database, sorted in ascending order
 * 
 * @param historicalYears - Array of historical year strings from database
 * @returns Sorted array of year strings
 * 
 * @example
 * generateHistoricalYears(['2023', '2021', '2022']);
 * // Returns: ['2021', '2022', '2023']
 * 
 * @example
 * generateHistoricalYears([]);
 * // Returns: []
 * 
 * @example
 * generateHistoricalYears(undefined);
 * // Returns: []
 */
function generateHistoricalYears(historicalYears?: string[]): string[] {
  if (!historicalYears || historicalYears.length === 0) {
    return [];
  }

  // Parse, deduplicate, and sort
  const yearNumbers = historicalYears
    .map((year) => parseInt(year, 10))
    .filter((year) => !isNaN(year) && year > 1900 && year < 2200);

  const uniqueYears = Array.from(new Set(yearNumbers));
  uniqueYears.sort((a, b) => a - b);

  return uniqueYears.map((year) => year.toString());
}

/**
 * Generate future years
 * Returns current year + N future years
 * 
 * @param currentYear - Current year as number
 * @param futureCount - Number of future years to generate (default: 0)
 * @returns Array of year strings including current and future years
 * 
 * @example
 * generateFutureYears(2024, 3);
 * // Returns: ['2024', '2025', '2026', '2027']
 * 
 * @example
 * generateFutureYears(2024, 0);
 * // Returns: ['2024']
 * 
 * @example
 * generateFutureYears(2024, -1);
 * // Returns: ['2024'] (negative counts treated as 0)
 */
function generateFutureYears(
  currentYear: number,
  futureCount: number = 0
): string[] {
  const count = Math.max(0, futureCount); // Ensure non-negative
  const years: string[] = [];

  for (let i = 0; i <= count; i++) {
    years.push((currentYear + i).toString());
  }

  return years;
}

/**
 * Generate combined historical and future years
 * Returns historical years + current year + N future years, deduplicated and sorted
 * 
 * @param currentYear - Current year as number
 * @param historicalYears - Array of historical year strings from database
 * @param futureCount - Number of future years to generate (default: 0)
 * @returns Sorted array of year strings
 * 
 * @example
 * generateCombinedYears(2024, ['2022', '2023'], 2);
 * // Returns: ['2022', '2023', '2024', '2025', '2026']
 * 
 * @example
 * generateCombinedYears(2024, ['2024', '2025'], 1);
 * // Returns: ['2024', '2025'] (duplicates removed)
 * 
 * @example
 * generateCombinedYears(2024, [], 2);
 * // Returns: ['2024', '2025', '2026']
 */
function generateCombinedYears(
  currentYear: number,
  historicalYears?: string[],
  futureCount: number = 0
): string[] {
  const yearSet = new Set<number>();

  // Add historical years
  if (historicalYears && historicalYears.length > 0) {
    historicalYears.forEach((year) => {
      const yearNum = parseInt(year, 10);
      if (!isNaN(yearNum) && yearNum > 1900 && yearNum < 2200) {
        yearSet.add(yearNum);
      }
    });
  }

  // Add current and future years
  const count = Math.max(0, futureCount);
  for (let i = 0; i <= count; i++) {
    yearSet.add(currentYear + i);
  }

  // Sort and convert to strings
  const sortedYears = Array.from(yearSet).sort((a, b) => a - b);
  return sortedYears.map((year) => year.toString());
}

/**
 * Generate rolling window of years
 * Returns last N years + current year + next M years
 * 
 * @param currentYear - Current year as number
 * @param pastCount - Number of past years to include (default: 0)
 * @param futureCount - Number of future years to include (default: 0)
 * @returns Array of year strings in rolling window
 * 
 * @example
 * generateRollingYears(2024, 2, 1);
 * // Returns: ['2022', '2023', '2024', '2025']
 * 
 * @example
 * generateRollingYears(2024, 0, 0);
 * // Returns: ['2024']
 * 
 * @example
 * generateRollingYears(2024, 3, 2);
 * // Returns: ['2021', '2022', '2023', '2024', '2025', '2026']
 */
function generateRollingYears(
  currentYear: number,
  pastCount: number = 0,
  futureCount: number = 0
): string[] {
  const past = Math.max(0, pastCount);
  const future = Math.max(0, futureCount);
  const years: string[] = [];

  // Add past years
  for (let i = past; i > 0; i--) {
    years.push((currentYear - i).toString());
  }

  // Add current year
  years.push(currentYear.toString());

  // Add future years
  for (let i = 1; i <= future; i++) {
    years.push((currentYear + i).toString());
  }

  return years;
}

/**
 * Get current year as string
 * Utility function for components that need the current year
 * 
 * @returns Current year as string
 * 
 * @example
 * const currentYear = getCurrentYear();
 * // Returns: '2024' (if current year is 2024)
 */
export function getCurrentYear(): string {
  return new Date().getFullYear().toString();
}

/**
 * Validate year string
 * Checks if a string represents a valid year
 * 
 * @param year - Year string to validate
 * @returns True if valid year, false otherwise
 * 
 * @example
 * isValidYear('2024'); // true
 * isValidYear('abc');  // false
 * isValidYear('1899'); // false (too old)
 * isValidYear('2201'); // false (too far in future)
 */
export function isValidYear(year: string): boolean {
  const yearNum = parseInt(year, 10);
  return !isNaN(yearNum) && yearNum > 1900 && yearNum < 2200;
}

/**
 * Parse year from various formats
 * Handles different year input formats and returns normalized string
 * 
 * @param input - Year input (string, number, or Date)
 * @returns Normalized year string, or null if invalid
 * 
 * @example
 * parseYear('2024');           // '2024'
 * parseYear(2024);             // '2024'
 * parseYear(new Date());       // '2024' (current year)
 * parseYear('invalid');        // null
 */
export function parseYear(input: string | number | Date): string | null {
  if (input instanceof Date) {
    return input.getFullYear().toString();
  }

  const yearNum = typeof input === 'number' ? input : parseInt(input, 10);
  
  if (isNaN(yearNum) || yearNum < 1900 || yearNum > 2200) {
    return null;
  }

  return yearNum.toString();
}

/**
 * Get year range description
 * Returns a human-readable description of a year range
 * 
 * @param years - Array of year strings
 * @returns Description string
 * 
 * @example
 * getYearRangeDescription(['2022', '2023', '2024']);
 * // Returns: '2022-2024'
 * 
 * @example
 * getYearRangeDescription(['2024']);
 * // Returns: '2024'
 * 
 * @example
 * getYearRangeDescription([]);
 * // Returns: 'No years'
 */
export function getYearRangeDescription(years: string[]): string {
  if (years.length === 0) {
    return 'No years';
  }

  if (years.length === 1) {
    return years[0];
  }

  const sortedYears = [...years].sort();
  return `${sortedYears[0]}-${sortedYears[sortedYears.length - 1]}`;
}
