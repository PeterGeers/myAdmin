/**
 * Tests for useBankingUpload hook.
 *
 * Covers record CRUD (insert/update), the two-step batch save
 * (show confirmation → confirm), inline transaction edits, and the
 * error branches for every API call. apiService is mocked.
 */

import { vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { authenticatedPost } from '../services/apiService';
import type { Transaction } from '../components/BankingProcessor.types';
import { useBankingUpload } from './useBankingUpload';
import { createMockResponse } from '@/test-utils/mockHelpers';

vi.mock('../services/apiService');
const mockPost = vi.mocked(authenticatedPost);

const tx = (over: Partial<Transaction> = {}): Transaction =>
  ({
    ID: 1,
    row_id: 10,
    TransactionNumber: 'T1',
    TransactionDate: '2025-01-01',
    TransactionDescription: 'desc',
    TransactionAmount: 100,
    Administration: 'T',
    Debet: '',
    Credit: '',
    ReferenceNumber: '',
    Ref1: '',
    Ref2: '',
    Ref3: '',
    Ref4: '',
    ...over,
  }) as Transaction;

function makeDeps(over: Partial<Parameters<typeof useBankingUpload>[0]> = {}) {
  return {
    t: (key: string) => key,
    transactions: [tx()],
    setTransactions: vi.fn(),
    testMode: false,
    setLoading: vi.fn(),
    setMessage: vi.fn(),
    setModalError: vi.fn(),
    editingRecord: tx(),
    isInsertMode: false,
    onClose: vi.fn(),
    ...over,
  };
}

describe('useBankingUpload', () => {
  beforeEach(() => vi.clearAllMocks());

  describe('handleSaveRecord — update path', () => {
    it('posts to update-mutatie, sets success message and closes modal', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: { success: true } }));
      const deps = makeDeps({ isInsertMode: false });
      const { result } = renderHook(() => useBankingUpload(deps));

      await act(async () => {
        await result.current.handleSaveRecord();
      });

      expect(mockPost).toHaveBeenCalledWith('/api/banking/update-mutatie', deps.editingRecord);
      expect(deps.setMessage).toHaveBeenCalledWith('messages.recordUpdated');
      expect(deps.onClose).toHaveBeenCalled();
      expect(deps.setLoading).toHaveBeenCalledWith(true);
      expect(deps.setLoading).toHaveBeenLastCalledWith(false);
    });

    it('surfaces backend error on unsuccessful update', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: { success: false, error: 'boom' } }));
      const deps = makeDeps({ isInsertMode: false });
      const { result } = renderHook(() => useBankingUpload(deps));

      await act(async () => {
        await result.current.handleSaveRecord();
      });

      expect(deps.setModalError).toHaveBeenCalledWith('boom');
      expect(deps.onClose).not.toHaveBeenCalled();
    });

    it('sets modal error when the request throws', async () => {
      mockPost.mockRejectedValue(new Error('offline'));
      const deps = makeDeps({ isInsertMode: false });
      const { result } = renderHook(() => useBankingUpload(deps));

      await act(async () => {
        await result.current.handleSaveRecord();
      });

      expect(deps.setModalError).toHaveBeenCalledWith(
        expect.stringContaining('messages.errorUpdating'),
      );
    });
  });

  describe('handleSaveRecord — insert path', () => {
    it('posts to insert-mutatie and reports success', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: { success: true } }));
      const deps = makeDeps({ isInsertMode: true });
      const { result } = renderHook(() => useBankingUpload(deps));

      await act(async () => {
        await result.current.handleSaveRecord();
      });

      expect(mockPost).toHaveBeenCalledWith('/api/banking/insert-mutatie', deps.editingRecord);
      expect(deps.setMessage).toHaveBeenCalledWith('messages.recordInserted');
    });

    it('is a no-op when there is no editing record', async () => {
      const deps = makeDeps({ isInsertMode: true, editingRecord: null });
      const { result } = renderHook(() => useBankingUpload(deps));

      await act(async () => {
        await result.current.handleSaveRecord();
      });

      expect(mockPost).not.toHaveBeenCalled();
    });
  });

  describe('batch save', () => {
    it('handleSaveTransactions only toggles the confirmation flag (no API call)', () => {
      const deps = makeDeps();
      const { result } = renderHook(() => useBankingUpload(deps));

      act(() => {
        result.current.handleSaveTransactions();
      });

      expect(result.current.showSaveConfirmation).toBe(true);
      expect(mockPost).not.toHaveBeenCalled();
    });

    it('confirmSaveTransactions posts the exact payload and clears transactions on success', async () => {
      mockPost.mockResolvedValue(
        createMockResponse({ body: { success: true, saved_count: 3, table: 'mutaties' } }),
      );
      const txs = [tx({ row_id: 1, TransactionAmount: 12.34 })];
      const deps = makeDeps({ transactions: txs, testMode: false });
      const { result } = renderHook(() => useBankingUpload(deps));

      await act(async () => {
        await result.current.confirmSaveTransactions();
      });

      expect(mockPost).toHaveBeenCalledWith('/api/banking/save-transactions', {
        transactions: txs,
        test_mode: false,
      });
      expect(deps.setMessage).toHaveBeenCalledWith('messages.transactionsSavedSuccess');
      expect(deps.setTransactions).toHaveBeenCalledWith([]);
      expect(result.current.showSaveConfirmation).toBe(false);
    });

    it('reports a generic error and keeps transactions when save is unsuccessful', async () => {
      mockPost.mockResolvedValue(createMockResponse({ body: { success: false, error: 'bad' } }));
      const deps = makeDeps();
      const { result } = renderHook(() => useBankingUpload(deps));

      await act(async () => {
        await result.current.confirmSaveTransactions();
      });

      expect(deps.setMessage).toHaveBeenCalledWith('messages.errorGeneric');
      expect(deps.setTransactions).not.toHaveBeenCalledWith([]);
    });

    it('reports a save error when the request rejects', async () => {
      mockPost.mockRejectedValue(new Error('timeout'));
      const deps = makeDeps();
      const { result } = renderHook(() => useBankingUpload(deps));

      await act(async () => {
        await result.current.confirmSaveTransactions();
      });

      expect(deps.setMessage).toHaveBeenCalledWith('messages.errorSaving');
    });
  });

  describe('updateTransaction', () => {
    it('updates only the matching row by row_id', () => {
      const deps = makeDeps();
      const { result } = renderHook(() => useBankingUpload(deps));

      act(() => {
        result.current.updateTransaction(10, 'TransactionAmount', 500);
      });

      // setTransactions called with an updater fn — exercise it directly
      const updater = vi.mocked(deps.setTransactions).mock.calls[0][0] as (p: Transaction[]) => Transaction[];
      const next = updater([tx({ row_id: 10, TransactionAmount: 100 }), tx({ row_id: 11 })]);
      expect(next[0].TransactionAmount).toBe(500);
      expect(next[1].TransactionAmount).toBe(100);
    });
  });
});
