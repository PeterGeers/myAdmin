/**
 * Year-End Closure Service
 * 
 * API service for year-end closure operations.
 * Handles closing fiscal years and viewing closure history.
 */

import { authenticatedGet, authenticatedPost } from './apiService';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

/**
 * Year object
 */
export interface Year {
  year: number;
}

/**
 * Validation result for year closure
 */
export interface YearValidation {
  can_close: boolean;
  errors: string[];
  warnings: string[];
  info: {
    net_result: number;
    net_result_formatted: string;
    balance_sheet_accounts: number;
  };
}

/**
 * Closed year information
 */
export interface ClosedYear {
  year: number;
  closed_date: string;
  closed_by: string;
  closure_transaction_number: string;
  opening_balance_transaction_number: string;
  notes: string;
}

/**
 * Year closure result
 */
export interface YearClosureResult {
  success: boolean;
  year: number;
  closure_transaction_number: string;
  opening_transaction_number: string;
  net_result: number;
  net_result_formatted: string;
  balance_sheet_accounts: number;
  message: string;
}

/**
 * Year status
 */
export interface YearStatus {
  year: number;
  closed?: boolean;
  closed_date?: string;
  closed_by?: string;
  closure_transaction_number?: string;
  opening_balance_transaction_number?: string;
  notes?: string;
  message?: string;
  // Additional info when year is open (from validation)
  can_close?: boolean;
  errors?: string[];
  warnings?: string[];
  info?: {
    net_result: number;
    net_result_formatted: string;
    balance_sheet_accounts: number;
    previous_year_closed?: boolean;
  };
}

/**
 * Get list of years available to close
 */
export const getAvailableYears = async (): Promise<Year[]> => {
  const response = await authenticatedGet(`${API_BASE_URL}/api/year-end/available-years`);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get available years');
  }
  
  return response.json();
};

/**
 * Validate if a year can be closed
 */
export const validateYear = async (year: number): Promise<YearValidation> => {
  const response = await authenticatedPost(
    `${API_BASE_URL}/api/year-end/validate`,
    { year }
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to validate year');
  }
  
  return response.json();
};

/**
 * Close a fiscal year
 */
export const closeYear = async (year: number, notes?: string): Promise<YearClosureResult> => {
  const response = await authenticatedPost(
    `${API_BASE_URL}/api/year-end/close`,
    { year, notes: notes || '' }
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to close year');
  }
  
  return response.json();
};

/**
 * Get list of closed years
 */
export const getClosedYears = async (): Promise<ClosedYear[]> => {
  const response = await authenticatedGet(`${API_BASE_URL}/api/year-end/closed-years`);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get closed years');
  }
  
  return response.json();
};

/**
 * Get closure status for a specific year
 */
export const getYearStatus = async (year: number): Promise<YearStatus> => {
  const response = await authenticatedGet(`${API_BASE_URL}/api/year-end/status/${year}`);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get year status');
  }
  
  return response.json();
};

/**
 * Reopen a closed fiscal year
 */
export const reopenYear = async (year: number): Promise<{ success: boolean; year: number; message: string }> => {
  const response = await authenticatedPost(
    `${API_BASE_URL}/api/year-end/reopen`,
    { year }
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to reopen year');
  }
  
  return response.json();
};
