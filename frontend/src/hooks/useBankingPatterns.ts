/**
 * useBankingPatterns Hook
 *
 * Pattern matching logic: apply patterns to uploaded transactions,
 * approve/reject suggestions, and visual styling for pattern-filled fields.
 */

import { useCallback, useState } from 'react';
import { authenticatedPost } from '../services/apiService';
import type { Transaction } from '../components/BankingProcessor.types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PatternData {
  patterns_found: number;
  predictions_made: {
    debet: number;
    credit: number;
    reference: number;
  };
  confidence_scores: number[];
  average_confidence: number;
  enhanced_results: unknown;
}

interface UseBankingPatternsDeps {
  /** Translation function */
  t: (key: string, params?: Record<string, unknown>) => string;
  /** Current transactions state */
  transactions: Transaction[];
  /** Set transactions state */
  setTransactions: React.Dispatch<React.SetStateAction<Transaction[]>>;
  /** Test mode flag */
  testMode: boolean;
  /** Set loading state */
  setLoading: (loading: boolean) => void;
  /** Set message state */
  setMessage: (msg: string) => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useBankingPatterns(deps: UseBankingPatternsDeps) {
  const { t, transactions, setTransactions, testMode, setLoading, setMessage } = deps;

  const [patternResults, setPatternResults] = useState<PatternData | null>(null);
  const [patternSuggestions, setPatternSuggestions] = useState<PatternData | null>(null);
  const [showPatternApproval, setShowPatternApproval] = useState(false);
  const [originalTransactions, setOriginalTransactions] = useState<Transaction[]>([]);

  // ---------------------------------------------------------------------------
  // Pattern application
  // ---------------------------------------------------------------------------

  const applyPatterns = useCallback(async () => {
    try {
      setLoading(true);
      setPatternResults(null);

      // Store original transactions before applying suggestions
      setOriginalTransactions([...transactions]);

      const response = await authenticatedPost('/api/banking/apply-patterns', {
        transactions: transactions,
        test_mode: testMode,
      });

      const data = await response.json();

      if (data.success) {
        setTransactions(data.transactions);

        const results = data.enhanced_results || data;

        const patternData: PatternData = {
          patterns_found: data.patterns_found || results.total_transactions || 0,
          predictions_made: results.predictions_made || { debet: 0, credit: 0, reference: 0 },
          confidence_scores: results.confidence_scores || [],
          average_confidence: results.average_confidence || 0,
          enhanced_results: data.enhanced_results,
        };

        setPatternResults(patternData);
        setPatternSuggestions(patternData);

        const totalPredictions = Object.values(patternData.predictions_made).reduce(
          (a: number, b: unknown) => a + (typeof b === 'number' ? b : 0),
          0
        );

        if (totalPredictions > 0) {
          setShowPatternApproval(true);
          setMessage(t('messages.patternSuggestionsFound', { count: totalPredictions }));
        } else {
          setMessage(t('messages.noPatternSuggestions'));
        }
      } else {
        setMessage(t('messages.errorApplyingPatterns', { error: data.error }));
        setPatternResults(null);
      }
    } catch (error) {
      setMessage(t('messages.errorApplyingPatterns', { error: String(error) }));
      setPatternResults(null);
    } finally {
      setLoading(false);
    }
  }, [transactions, testMode, t, setLoading, setMessage, setTransactions]);

  // ---------------------------------------------------------------------------
  // Approve / Reject suggestions
  // ---------------------------------------------------------------------------

  const approvePatternSuggestions = useCallback(() => {
    setShowPatternApproval(false);
    const count = Object.values(patternSuggestions?.predictions_made || {}).reduce(
      (a: number, b: unknown) => a + (typeof b === 'number' ? b : 0),
      0
    );
    setMessage(t('messages.patternSuggestionsApproved', { count }));
  }, [patternSuggestions, t, setMessage]);

  const rejectPatternSuggestions = useCallback(() => {
    setTransactions([...originalTransactions]);
    setPatternResults(null);
    setPatternSuggestions(null);
    setShowPatternApproval(false);
    setMessage(t('messages.patternSuggestionsRejected'));
  }, [originalTransactions, t, setMessage, setTransactions]);

  // ---------------------------------------------------------------------------
  // REQ-UI-008: Pattern-filled field detection & styling
  // ---------------------------------------------------------------------------

  /** Check if a field was auto-filled by patterns */
  const isPatternFilled = useCallback(
    (transaction: Transaction, field: string) => {
      const originalTx = originalTransactions.find((tx) => tx.row_id === transaction.row_id);
      if (!originalTx) return false;

      const fieldKey =
        field === 'debet' ? 'Debet' : field === 'credit' ? 'Credit' : field === 'reference' ? 'ReferenceNumber' : field;

      const originalValue = originalTx[fieldKey as keyof Transaction] || '';
      const currentValue = transaction[fieldKey as keyof Transaction] || '';

      return !originalValue && !!currentValue && !!patternSuggestions;
    },
    [originalTransactions, patternSuggestions]
  );

  /** Get Chakra styling for pattern-filled fields */
  const getPatternFieldStyle = useCallback(
    (transaction: Transaction, field: string) => {
      if (isPatternFilled(transaction, field)) {
        return {
          bg: 'blue.50',
          borderColor: 'blue.300',
          borderWidth: '2px',
          _hover: { bg: 'blue.100' },
        };
      }
      return {};
    },
    [isPatternFilled]
  );

  return {
    patternResults,
    patternSuggestions,
    showPatternApproval,
    setShowPatternApproval,
    applyPatterns,
    approvePatternSuggestions,
    rejectPatternSuggestions,
    isPatternFilled,
    getPatternFieldStyle,
  };
}
