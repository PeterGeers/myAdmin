/**
 * Invoice Test Tool Service
 *
 * API service for the Invoice Processing Test Tool (SysAdmin only).
 * Handles file processing in dry-run mode, custom prompt re-runs,
 * and vendor transaction history lookups.
 */

import {
  authenticatedGet,
  authenticatedPost,
  authenticatedFormData,
  buildEndpoint,
} from './apiService';
import type {
  ProcessResponse,
  RerunPromptResponse,
  VendorHistoryResponse,
} from '../types/invoiceTestTool';

const BASE_PATH = '/api/sysadmin/test-tool';

/**
 * Process a file through the invoice pipeline in dry-run mode.
 *
 * @param file - The file to process (PDF, JPG, JPEG, PNG, CSV, EML, MHTML)
 * @param folderName - Optional vendor/folder name (defaults to "TestVendor" on backend)
 * @param administration - Optional tenant identifier for vendor history lookup
 * @returns Full pipeline result with performance metrics, AI usage preview, and errors
 */
export async function processFile(
  file: File,
  folderName?: string,
  administration?: string
): Promise<ProcessResponse> {
  const formData = new FormData();
  formData.append('file', file);

  if (folderName) {
    formData.append('folderName', folderName);
  }
  if (administration) {
    formData.append('administration', administration);
  }

  const response = await authenticatedFormData(`${BASE_PATH}/process`, formData);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || error.message || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Re-run AI extraction with a custom prompt against already-extracted text.
 *
 * @param textContent - The raw extracted text from a previous process call
 * @param customPrompt - Modified extraction prompt (1–10,000 characters)
 * @param vendorHint - Optional vendor name for context
 * @returns Extraction result with performance metrics and AI usage preview
 */
export async function rerunPrompt(
  textContent: string,
  customPrompt: string,
  vendorHint?: string
): Promise<RerunPromptResponse> {
  const body: Record<string, string> = {
    text_content: textContent,
    custom_prompt: customPrompt,
  };

  if (vendorHint) {
    body.vendor_hint = vendorHint;
  }

  const response = await authenticatedPost(`${BASE_PATH}/rerun-prompt`, body);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || error.message || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Get previous transactions for a vendor (read-only history lookup).
 *
 * @param folderName - Vendor/folder name (required)
 * @param administration - Optional tenant filter
 * @returns Vendor transaction history with count
 */
export async function getVendorHistory(
  folderName: string,
  administration?: string
): Promise<VendorHistoryResponse> {
  const params: Record<string, string> = { folderName };

  if (administration) {
    params.administration = administration;
  }

  const endpoint = buildEndpoint(`${BASE_PATH}/vendor-history`, params);
  const response = await authenticatedGet(endpoint);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || error.message || `HTTP ${response.status}`);
  }

  return response.json();
}
