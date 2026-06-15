/**
 * Budget Management Types
 *
 * TypeScript type definitions for the Budget Management feature (fin-budget).
 * Covers budget versions, templates, lines, dashboard, and AI-powered features.
 */

// ─── Enums ───────────────────────────────────────────────────────────────────

/** Budget version status lifecycle: Draft → Approved → Revised */
export type BudgetStatus = 'Draft' | 'Approved' | 'Revised';

/** Period entry mode for budget lines and template configuration */
export type PeriodMode = 'Monthly' | 'Annual';

/** Detail dimension type for sub-account budget breakdowns */
export type DimensionType = 'platform' | 'ReferenceNumber';

/** Dashboard hierarchy drill-down level */
export type DashboardLevel = 'parent' | 'subparent' | 'account';

/** Dashboard period selection */
export type DashboardPeriod =
  | 'month-1' | 'month-2' | 'month-3' | 'month-4'
  | 'month-5' | 'month-6' | 'month-7' | 'month-8'
  | 'month-9' | 'month-10' | 'month-11' | 'month-12'
  | 'q1' | 'q2' | 'q3' | 'q4'
  | 'ytd' | 'full';

/** AI recommendation confidence level */
export type ConfidenceLevel = 'high' | 'medium' | 'low';

// ─── Budget Versions ─────────────────────────────────────────────────────────

/** A named budget instance for a specific fiscal year with status and active flag */
export interface BudgetVersion {
  /** Unique identifier */
  id: number;

  /** User-provided version name (1–100 characters) */
  name: string;

  /** 4-digit fiscal year */
  fiscal_year: number;

  /** Current lifecycle status */
  status: BudgetStatus;

  /** Whether this is the active version for dashboard comparisons */
  is_active: boolean;

  /** Timestamp of last status transition */
  status_changed_at: string | null;

  /** Creation timestamp (ISO 8601) */
  created_at: string;

  /** Last update timestamp (ISO 8601) */
  updated_at: string;
}

// ─── Budget Templates ────────────────────────────────────────────────────────

/** Template configuration specifying which accounts to budget and how */
export interface BudgetTemplate {
  /** Unique identifier */
  id: number;

  /** Template name (max 100 characters) */
  name: string;

  /** Number of configured template lines */
  line_count: number;

  /** Creation timestamp (ISO 8601) */
  created_at: string;

  /** Last update timestamp (ISO 8601) */
  updated_at: string;
}

/** Individual line configuration within a budget template */
export interface BudgetTemplateLine {
  /** Unique identifier */
  id: number;

  /** Parent template ID */
  template_id: number;

  /** Ledger account code */
  account_code: string;

  /** Entry granularity: Monthly (12 amounts) or Annual (1 amount ÷ 12) */
  period_mode: PeriodMode;

  /** Whether a detail dimension applies to this account */
  has_detail_dimension: boolean;

  /** Dimension type (required when has_detail_dimension is true) */
  dimension_type: DimensionType | null;

  /** Method for dividing annual amounts into months */
  annualization_method: string;
}

/** Full template with lines included (for detail view) */
export interface BudgetTemplateWithLines extends BudgetTemplate {
  /** Template line configurations */
  lines: BudgetTemplateLine[];
}

// ─── Budget Lines ────────────────────────────────────────────────────────────

/** A single budget entry with 12 monthly amounts for an account/dimension */
export interface BudgetLine {
  /** Unique identifier */
  id: number;

  /** Parent budget version ID */
  version_id: number;

  /** Ledger account code */
  account_code: string;

  /** Period mode used for entry */
  period_mode: PeriodMode;

  /** Detail dimension type (null if no dimension) */
  detail_dimension_type: DimensionType | null;

  /** Detail dimension value, e.g. "Airbnb" or a reference number */
  detail_dimension_value: string | null;

  /** Monthly amounts (January through December) */
  month_01: number;
  month_02: number;
  month_03: number;
  month_04: number;
  month_05: number;
  month_06: number;
  month_07: number;
  month_08: number;
  month_09: number;
  month_10: number;
  month_11: number;
  month_12: number;

  /** Creation timestamp (ISO 8601) */
  created_at: string;

  /** Last update timestamp (ISO 8601) */
  updated_at: string;
}

// ─── Dashboard ───────────────────────────────────────────────────────────────

/** Single row in the budget vs actuals dashboard */
export interface DashboardRow {
  /** Account/SubParent/Parent code */
  code: string;

  /** Account/SubParent/Parent name */
  name: string;

  /** Total budgeted amount for the selected period */
  budget: number;

  /** Total actual amount for the selected period */
  actual: number;

  /** Variance: actual - budget (positive = over-budget) */
  variance: number;
}

/** Active version summary included in dashboard response */
export interface ActiveVersionSummary {
  /** Version ID */
  id: number;

  /** Version name */
  name: string;
}

/** Dashboard API response data */
export interface DashboardData {
  /** Fiscal year */
  year: number;

  /** Hierarchy level displayed */
  level: DashboardLevel;

  /** Selected period */
  period: DashboardPeriod;

  /** Active version for this year (null if none) */
  active_version: ActiveVersionSummary | null;

  /** Budget vs actuals rows */
  rows: DashboardRow[];

  /** Optional notification (e.g. "No active budget version for 2025") */
  notification?: string;
}

// ─── API Response Wrappers ───────────────────────────────────────────────────

/** Successful API response */
export interface ApiSuccessResponse<T> {
  success: true;
  data: T;
}

/** Failed API response */
export interface ApiErrorResponse {
  success: false;
  error: string;
}

/** Union type for all API responses */
export type ApiResponse<T> = ApiSuccessResponse<T> | ApiErrorResponse;

// ─── Request Types ───────────────────────────────────────────────────────────

/** Request to create a new budget version */
export interface CreateVersionRequest {
  /** Version name (1–100 characters) */
  name: string;

  /** 4-digit fiscal year */
  fiscal_year: number;
}

/** Request to transition a budget version status */
export interface StatusTransitionRequest {
  /** Action to perform */
  action: 'approve' | 'revise';
}

/** Template line configuration for create/update requests */
export interface TemplateLineRequest {
  /** Ledger account code */
  account_code: string;

  /** Entry granularity */
  period_mode: PeriodMode;

  /** Whether a detail dimension applies */
  has_detail_dimension: boolean;

  /** Dimension type (required when has_detail_dimension is true) */
  dimension_type?: DimensionType | null;

  /** Annualization method */
  annualization_method: string;
}

/** Request to create a budget template */
export interface CreateTemplateRequest {
  /** Template name (max 100 characters) */
  name: string;

  /** Template line configurations (at least one) */
  lines: TemplateLineRequest[];
}

/** Request to create/update a monthly budget line */
export interface CreateBudgetLineMonthlyRequest {
  /** Ledger account code */
  account_code: string;

  /** Period mode */
  period_mode: 'Monthly';

  /** 12 monthly amounts */
  amounts: [number, number, number, number, number, number, number, number, number, number, number, number];

  /** Detail dimension type (null if none) */
  detail_dimension_type: DimensionType | null;

  /** Detail dimension value (null if none) */
  detail_dimension_value: string | null;

  /** Optional notes (e.g. AI reasoning) */
  notes?: string | null;
}

/** Request to create/update an annual budget line */
export interface CreateBudgetLineAnnualRequest {
  /** Ledger account code */
  account_code: string;

  /** Period mode */
  period_mode: 'Annual';

  /** Single annual amount (system divides by 12) */
  annual_amount: number;

  /** Detail dimension type (null if none) */
  detail_dimension_type: DimensionType | null;

  /** Detail dimension value (null if none) */
  detail_dimension_value: string | null;

  /** Optional notes (e.g. AI reasoning) */
  notes?: string | null;
}

/** Union type for budget line creation requests */
export type CreateBudgetLineRequest = CreateBudgetLineMonthlyRequest | CreateBudgetLineAnnualRequest;

/** Request to generate a draft from prior-year actuals */
export interface GenerateDraftRequest {
  /** Template ID to use for account selection */
  template_id: number;

  /** Target fiscal year */
  fiscal_year: number;

  /** Name for the generated draft version */
  version_name: string;
}

/** Request to copy a budget version to a new year */
export interface CopyBudgetRequest {
  /** Source version ID to copy from */
  source_version_id: number;

  /** Target fiscal year (must be later than source) */
  target_fiscal_year: number;

  /** Name for the new version */
  version_name: string;
}

// ─── Draft Generation & Copy Response Data ───────────────────────────────────

/** Response data from draft generation */
export interface GenerateDraftData {
  /** ID of the newly created version */
  version_id: number;

  /** Number of budget lines created */
  lines_created: number;

  /** Account codes with no prior-year actuals (filled with zeros) */
  accounts_with_no_actuals: string[];
}

/** Response data from budget copy */
export interface CopyBudgetData {
  /** ID of the newly created version */
  version_id: number;

  /** Number of lines copied */
  lines_copied: number;

  /** Account codes excluded (no longer in chart of accounts) */
  excluded_accounts: string[];
}

// ─── AI Feature Types ────────────────────────────────────────────────────────

/** AI narrative generation response data */
export interface AINarrativeData {
  /** Generated executive summary text (Dutch) */
  narrative: string;

  /** AI model identifier used */
  model_used: string;

  /** Number of tokens consumed */
  tokens_used: number;
}

/** AI query response — extended dashboard row with variance percentage */
export interface AIQueryResultRow extends DashboardRow {
  /** Variance as percentage (optional, included when relevant) */
  variance_pct?: number;
}

/** AI natural language query response data */
export interface AIQueryData {
  /** Dashboard parameters interpreted from the question */
  interpreted_params: {
    level?: DashboardLevel;
    period?: DashboardPeriod;
    year?: number;
    parent_code?: string;
    subparent_code?: string;
    reference_number?: string;
  };

  /** Human-readable description of the applied filter */
  filter_description: string;

  /** Filtered results */
  results: AIQueryResultRow[];

  /** AI model identifier used */
  model_used: string;

  /** Number of tokens consumed */
  tokens_used: number;
}

/** Single AI draft adjustment suggestion */
export interface AIDraftSuggestion {
  /** Ledger account code */
  account_code: string;

  /** Account name */
  account_name: string;

  /** Month numbers affected (1–12) */
  affected_months: number[];

  /** Current monthly amounts for affected months */
  current_amounts: number[];

  /** Suggested new monthly amounts */
  suggested_amounts: number[];

  /** Explanation of the suggested change */
  reasoning: string;
}

/** AI draft suggestions response data */
export interface AIDraftSuggestionsData {
  /** List of suggested adjustments */
  suggestions: AIDraftSuggestion[];

  /** AI model identifier used */
  model_used: string;

  /** Number of tokens consumed */
  tokens_used: number;
}

/** Single AI template recommendation */
export interface AITemplateRecommendation {
  /** Ledger account code */
  account_code: string;

  /** Account name */
  account_name: string;

  /** Suggested period mode */
  period_mode: PeriodMode;

  /** Whether a detail dimension is recommended */
  has_detail_dimension: boolean;

  /** Suggested dimension type (null if not recommended) */
  dimension_type: DimensionType | null;

  /** Confidence level of the recommendation */
  confidence: ConfidenceLevel;

  /** Explanation for the recommendation */
  reason: string;
}

/** AI template recommendations response data */
export interface AITemplateRecommendData {
  /** List of account recommendations */
  recommendations: AITemplateRecommendation[];

  /** AI model identifier used */
  model_used: string;

  /** Number of tokens consumed */
  tokens_used: number;
}

// ─── AI Request Types ────────────────────────────────────────────────────────

/** Request for AI narrative generation */
export interface AINarrativeRequest {
  /** Fiscal year */
  year: number;

  /** Hierarchy level */
  level: DashboardLevel;

  /** Period selection */
  period: DashboardPeriod;
}

/** Request for AI natural language query */
export interface AIQueryRequest {
  /** Natural language question */
  question: string;

  /** Fiscal year context */
  year: number;
}

/** Request for AI draft adjustment suggestions */
export interface AIDraftSuggestionsRequest {
  /** Budget version ID to analyze */
  version_id: number;

  /** User-provided context notes (e.g. "rent increases 5% in June") */
  context_notes: string;

  /** Optional scope filter */
  scope?: {
    parent_code?: string;
    subparent_code?: string;
  };
}

/** Request for AI template recommendations */
export interface AITemplateRecommendRequest {
  /** Fiscal year for analysis */
  fiscal_year: number;
}
