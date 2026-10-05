/**
 * Tests for useBankingPatterns hook.
 *
 * Covers applyPatterns (success with/without predictions + error branch),
 * approve/reject suggestion flows, and the pattern-field styling helper.
 * apiService is mocked.
 */

import { vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { authenticatedPost } from '../services/apiService';
import type { Transaction } from '../components/BankingProcessor.types';
import { useBankingPatterns } from './useBankingPatterns';
import { createMockResponse } from '@/test-utils/mockHelpers';

vi.mock('../services/apiService');
const mockPost = vi.mocked(authenticatedPost);

const tx = (over: Partial<Transaction> = {}): Transaction =>
  ({ row_id: 1, Debet: '', Credit: '', ReferenceNumber: '', ...over }) as Transaction;

function makeDeps(over: Partial<Parameters<typeof useBankingPatterns>[0]> = {}) {
  return {
    t: (key: string) => key,
    transactions: [tx()],
    setTransactions: vi.fn(),
    testMode: false,
    setLoading: vi.fn(),
    setMessage: vi.fn(),
    ...over,
  };
}

describe('useBankingPatterns', () => {
  beforeEach(() => vi.clearAllMocks());

  it('applyPatterns posts transactions, stores results and prompts approval when predictions exist', async () => {
    mockPost.mockResolvedValue(
      createMockResponse({
        body: {
          success: true,
          transactions: [tx({ Debet: '1000' })],
          patterns_found: 2,
          enhanced_results: {
            predictions_made: { debet: 1, credit: 0, reference: 1 },
            confidence_scores: [0.9, 0.8],
            average_confidence: 0.85,
          },
        },
      }),
    );
    const deps = makeDeps();
    const { result } = renderHook(() => useBankingPatterns(deps));

    await act(async () => {
      await result.current.applyPatterns();
    });

    expect(mockPost).toHaveBeenCalledWith('/api/banking/apply-patterns', {
      transactions: deps.transactions,
      test_mode: false,
    });
    expect(deps.setTransactions).toHaveBeenCalledWith([tx({ Debet: '1000' })]);
    expect(result.current.showPatternApproval).toBe(true);
    expect(result.current.patternResults?.predictions_made).toEqual({ debet: 1, credit: 0, reference: 1 });
    expect(deps.setMessage).toHaveBeenCalledWith('messages.patternSuggestionsFound');
  });

  it('applyPatterns reports "no suggestions" when total predictions is zero', async () => {
    mockPost.mockResolvedValue(
      createMockResponse({
        body: {
          success: true,
          transactions: [],
          enhanced_results: { predictions_made: { debet: 0, credit: 0, reference: 0 } },
        },
      }),
    );
    const deps = makeDeps();
    const { result } = renderHook(() => useBankingPatterns(deps));

    await act(async () => {
      await result.current.applyPatterns();
    });

    expect(result.current.showPatternApproval).toBe(false);
    expect(deps.setMessage).toHaveBeenCalledWith('messages.noPatternSuggestions');
  });

  it('applyPatterns clears results and reports error on an unsuccessful response', async () => {
    mockPost.mockResolvedValue(createMockResponse({ body: { success: false, error: 'nope' } }));
    const deps = makeDeps();
    const { result } = renderHook(() => useBankingPatterns(deps));

    await act(async () => {
      await result.current.applyPatterns();
    });

    expect(result.current.patternResults).toBeNull();
    expect(deps.setMessage).toHaveBeenCalledWith('messages.errorApplyingPatterns');
  });

  it('applyPatterns reports error when the request rejects', async () => {
    mockPost.mockRejectedValue(new Error('fail'));
    const deps = makeDeps();
    const { result } = renderHook(() => useBankingPatterns(deps));

    await act(async () => {
      await result.current.applyPatterns();
    });

    expect(result.current.patternResults).toBeNull();
    expect(deps.setMessage).toHaveBeenCalledWith('messages.errorApplyingPatterns');
    expect(deps.setLoading).toHaveBeenLastCalledWith(false);
  });

  it('rejectPatternSuggestions restores original transactions and clears state', async () => {
    mockPost.mockResolvedValue(
      createMockResponse({
        body: {
          success: true,
          transactions: [tx({ Debet: '1000' })],
          enhanced_results: { predictions_made: { debet: 1, credit: 0, reference: 0 } },
        },
      }),
    );
    const original = [tx({ row_id: 1, Debet: '' })];
    const deps = makeDeps({ transactions: original });
    const { result } = renderHook(() => useBankingPatterns(deps));

    await act(async () => {
      await result.current.applyPatterns();
    });
    vi.mocked(deps.setTransactions).mockClear();

    act(() => {
      result.current.rejectPatternSuggestions();
    });

    expect(deps.setTransactions).toHaveBeenCalledWith(original);
    expect(result.current.patternResults).toBeNull();
    expect(result.current.showPatternApproval).toBe(false);
    expect(deps.setMessage).toHaveBeenCalledWith('messages.patternSuggestionsRejected');
  });

  it('approvePatternSuggestions hides the approval UI and reports an approval message', async () => {
    mockPost.mockResolvedValue(
      createMockResponse({
        body: {
          success: true,
          transactions: [],
          enhanced_results: { predictions_made: { debet: 2, credit: 1, reference: 0 } },
        },
      }),
    );
    const deps = makeDeps();
    const { result } = renderHook(() => useBankingPatterns(deps));

    await act(async () => {
      await result.current.applyPatterns();
    });

    act(() => {
      result.current.approvePatternSuggestions();
    });

    expect(result.current.showPatternApproval).toBe(false);
    expect(deps.setMessage).toHaveBeenCalledWith('messages.patternSuggestionsApproved');
  });

  it('getPatternFieldStyle returns {} when no suggestions are active', () => {
    const deps = makeDeps();
    const { result } = renderHook(() => useBankingPatterns(deps));

    expect(result.current.getPatternFieldStyle(tx(), 'debet')).toEqual({});
  });
});
