/**
 * TypeScript type definitions for the Invoice Processing Test Tool.
 *
 * Covers pipeline data models, performance metrics, AI usage preview,
 * error diagnostics, and API response types for the SysAdmin test tool.
 */

// ─── Core Pipeline Models ────────────────────────────────────────────────────

/**
 * Result of the complete invoice processing pipeline in dry-run mode.
 */
export interface PipelineResult {
  raw_text: string;
  raw_text_truncated: boolean;
  extraction_result: ExtractionResult | null;
  formatted_transactions: Transaction[];
  prepared_transactions: PreparedTransaction[];
  parser_used: 'ai' | 'csv_rule' | 'ai_failed';
  folder_name: string;
}

/**
 * Structured extraction output from AI or CSV rule parsing.
 * All fields are always present; missing values use empty string or 0.
 */
export interface ExtractionResult {
  date: string;
  total_amount: number;
  vat_amount: number;
  description: string;
  vendor: string;
}

/**
 * Formatted transaction produced by the transaction formatting stage.
 */
export interface Transaction {
  date: string;
  amount: number;
  description: string;
  debet?: string;
  credit?: string;
  parser_used_hint?: string;
}

/**
 * Fully prepared transaction ready for import (dry-run preview only).
 */
export interface PreparedTransaction {
  ID: string;
  TransactionNumber: string;
  TransactionDate: string;
  TransactionDescription: string;
  TransactionAmount: number;
  Debet: string;
  Credit: string;
  ReferenceNumber: string;
  Ref1: string | null;
  Ref2: string | null;
  Ref3: string;
  Ref4: string;
  Administration: string;
}

// ─── Performance & Usage Models ──────────────────────────────────────────────

/**
 * Timing and model metrics for a pipeline execution.
 * AI-specific fields are null when the CSV rule engine is used.
 */
export interface PerformanceMetrics {
  total_duration_ms: number;
  ai_duration_ms: number | null;
  ai_model: string | null;
  ai_tokens: TokenUsage | null;
}

/**
 * Token consumption reported by the AI API response.
 */
export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

/**
 * Preview of what would be written to the AI usage log (dry-run, no actual write).
 */
export interface AIUsagePreview {
  administration: string;
  feature: string;
  tokens_used: number;
  cost_estimate: string;
  cost_breakdown: {
    model: string;
    rate_per_million: number;
    total_tokens: number;
    formula: string;
  };
}

// ─── Error & Diagnostic Models ───────────────────────────────────────────────

/** Pipeline stage identifiers for error reporting. */
export type PipelineStage =
  | 'file_parsing'
  | 'text_extraction'
  | 'ai_extraction'
  | 'csv_rule'
  | 'transaction_formatting'
  | 'transaction_preparation';

/**
 * Detailed error for a single pipeline stage failure.
 */
export interface PipelineError {
  stage: PipelineStage;
  error_type: string;
  message: string;
  stack_trace?: string;
  model_failures?: ModelFailure[];
  csv_rule_details?: CsvRuleDebug;
}

/**
 * Per-model failure detail when AI extraction exhausts all models.
 */
export interface ModelFailure {
  model: string;
  failure_reason: 'timeout' | 'api_error' | 'invalid_response';
  details: string;
}

/**
 * Debug information for CSV rule engine failures.
 */
export interface CsvRuleDebug {
  rules_evaluated: string[];
  pattern_matched: boolean;
  failure_reason: string;
}

// ─── API Response Types ──────────────────────────────────────────────────────

/**
 * Response from POST /api/sysadmin/test-tool/process
 */
export interface ProcessResponse {
  success: boolean;
  pipeline_result: PipelineResult;
  performance: PerformanceMetrics;
  ai_usage_preview: AIUsagePreview | null;
  execution_log: string;
  errors: PipelineError[];
}

/**
 * Response from POST /api/sysadmin/test-tool/rerun-prompt
 */
export interface RerunPromptResponse {
  success: boolean;
  extraction_result: ExtractionResult | null;
  performance: Pick<PerformanceMetrics, 'ai_duration_ms' | 'ai_model' | 'ai_tokens'>;
  ai_usage_preview: AIUsagePreview | null;
  errors: PipelineError[];
}

/**
 * Response from GET /api/sysadmin/test-tool/vendor-history
 */
export interface VendorHistoryResponse {
  success: boolean;
  vendor_name: string;
  transactions: VendorTransaction[];
  count: number;
}

/**
 * A single historical transaction entry for a vendor.
 */
export interface VendorTransaction {
  date: string;
  amount: number;
  description: string;
}
