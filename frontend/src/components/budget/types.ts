/**
 * Shared types for budget sub-components.
 */

import { BudgetLine, BudgetVersion, AIDraftSuggestion, PeriodMode } from '../../types/budget';
import { SortDirection } from '../../components/filters/types';

// ─── Line form shape used across modal and page ─────────────────────────────

export interface BudgetLineFormValues {
  account_code: string;
  period_mode: PeriodMode;
  amounts: number[];
  annual_amount: number;
  dimension_type: string;
  dimension_value: string;
}

// ─── Enriched line row (includes computed fields) ───────────────────────────

export interface EnrichedBudgetLine extends BudgetLine {
  dimension: string;
  total: string;
}

// ─── BudgetLineTable Props ──────────────────────────────────────────────────

export interface BudgetLineTableProps {
  /** Enriched (with computed fields) and filtered/sorted lines */
  processedData: EnrichedBudgetLine[];
  /** Whether lines are loading */
  loading: boolean;
  /** Whether there are zero lines total (before filtering) */
  isEmpty: boolean;
  /** Current filter values */
  filters: Record<string, string>;
  /** Set a filter for a specific column */
  setFilter: (key: string, value: string) => void;
  /** Currently sorted field */
  sortField: string | null;
  /** Current sort direction */
  sortDirection: SortDirection;
  /** Toggle sort on a field */
  handleSort: (field: string) => void;
  /** Callback when a row is clicked */
  onRowClick: (line: BudgetLine) => void;
}

// ─── BudgetLineToolbar Props ────────────────────────────────────────────────

export interface BudgetLineToolbarProps {
  /** Available budget versions */
  versions: BudgetVersion[];
  /** Currently selected version ID */
  selectedVersionId: number | null;
  /** Callback when version selection changes */
  onVersionChange: (versionId: number) => void;
  /** Whether the selected version is a Draft (shows AI button) */
  isDraftVersion: boolean;
  /** Action handlers */
  onAddLine: () => void;
  onGenerateDraft: () => void;
  onCopyBudget: () => void;
  onAISuggestions: () => void;
}

// ─── AISuggestionsModal Props ───────────────────────────────────────────────

export interface AISuggestionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Current suggestions list */
  suggestions: AIDraftSuggestion[];
  /** Whether suggestions are loading */
  loading: boolean;
  /** Context notes text */
  contextNotes: string;
  /** Update context notes */
  onContextNotesChange: (value: string) => void;
  /** Request suggestions from AI */
  onGetSuggestions: () => void;
  /** Accept a specific suggestion */
  onAccept: (suggestion: AIDraftSuggestion) => void;
  /** Reject a suggestion by index */
  onReject: (index: number) => void;
}
