/**
 * Shared types for the Balance and P&L report components.
 * Used by BalanceReport, ProfitLossReport, and FinancialReportsGroup.
 */

export type DisplayFormat = '2dec' | '0dec' | 'k' | 'm';
export type DrillDownLevel = 'year' | 'quarter' | 'month';
export type ViewMode = 'standard' | 'pivot';

/** Shared filter state lifted to FinancialReportsGroup */
export interface SharedFilterState {
  selectedYears: string[];
  displayFormat: DisplayFormat;
  availableYears: string[];
}

/** Props passed from FinancialReportsGroup to BalanceReport */
export interface BalanceReportProps {
  selectedYears: string[];
  displayFormat: DisplayFormat;
  availableYears: string[];
  onYearsChange: (years: string[]) => void;
  onDisplayFormatChange: (format: DisplayFormat) => void;
}

/** Props passed from FinancialReportsGroup to ProfitLossReport */
export interface ProfitLossReportProps {
  selectedYears: string[];
  displayFormat: DisplayFormat;
  availableYears: string[];
  onYearsChange: (years: string[]) => void;
  onDisplayFormatChange: (format: DisplayFormat) => void;
}

/** Balance record returned by /api/reports/actuals-balance?per_year=true */
export interface BalanceYearRecord {
  Parent: string;
  Reknum: string;
  AccountName: string;
  jaar: number;
  Amount: number;
}

/** P&L record returned by /api/reports/actuals-profitloss */
export interface PLRecord {
  Parent: string;
  Reknum: string;
  AccountName: string;
  jaar: number;
  kwartaal?: number;
  maand?: number;
  Amount: number;
  ReferenceNumber?: string;
}

/** Balance API response shape when per_year=true */
export interface BalancePerYearResponse {
  success: boolean;
  data: BalanceYearRecord[];
  closedYears: number[];
}

/** P&L API response shape */
export interface ProfitLossResponse {
  success: boolean;
  data: PLRecord[];
}
