/**
 * Unit tests for the useLazyOptions hook.
 *
 * Covers the hook contract from the LazySelect design ("useLazyOptions" + Testing Strategy):
 *   - array source passthrough (isLoading=false, ensureLoaded is a no-op);
 *   - resolve-on-ensureLoaded (isLoading true until settle, then options cached);
 *   - error path (rejection sets error, options stays []);
 *   - cache reuse (a second ensureLoaded does not re-invoke the source fn);
 *   - reload forces a re-resolve;
 *   - depKey invalidation (a changed depKey re-resolves on the next ensureLoaded);
 *   - idempotence of ensureLoaded.
 *
 * The hook takes a plain (possibly async) function as its source, so tests pass a `vi.fn()`
 * returning a resolved/rejected Promise — no real network is involved.
 *
 * @see .kiro/specs/Common/Frameworks/lazy-select/design.md
 * _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useLazyOptions } from '../useLazyOptions';
import type { LazyOption } from '../../components/common/lazySelect.types';

const optA: LazyOption[] = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta' },
];
const optB: LazyOption[] = [
  { value: 'c', label: 'Gamma' },
  { value: 'd', label: 'Delta' },
];

describe('useLazyOptions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── R4.1: array passthrough ────────────────────────────────────────────────
  describe('array source passthrough', () => {
    it('exposes the array directly with isLoading=false and no error', () => {
      const { result } = renderHook(() => useLazyOptions(optA));

      expect(result.current.options).toEqual(optA);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('ensureLoaded is a no-op for an array source (no loading, options unchanged)', () => {
      const { result } = renderHook(() => useLazyOptions(optA));

      act(() => {
        result.current.ensureLoaded();
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.options).toEqual(optA);
      expect(result.current.error).toBeNull();
    });

    it('reflects a new array when the source array changes on re-render', () => {
      const { result, rerender } = renderHook(({ src }) => useLazyOptions(src), {
        initialProps: { src: optA },
      });

      expect(result.current.options).toEqual(optA);

      rerender({ src: optB });

      expect(result.current.options).toEqual(optB);
    });
  });

  // ── R4.2: resolve on first ensureLoaded ─────────────────────────────────────
  describe('resolve-on-ensureLoaded (function source)', () => {
    it('starts empty and not loading before ensureLoaded is called', () => {
      const fn = vi.fn().mockResolvedValue(optA);
      const { result } = renderHook(() => useLazyOptions(fn));

      expect(result.current.options).toEqual([]);
      expect(result.current.isLoading).toBe(false);
      expect(fn).not.toHaveBeenCalled();
    });

    it('sets isLoading true until the promise settles, then caches options', async () => {
      let resolveFn: (v: LazyOption[]) => void = () => {};
      const fn = vi.fn(
        () =>
          new Promise<LazyOption[]>((resolve) => {
            resolveFn = resolve;
          }),
      );

      const { result } = renderHook(() => useLazyOptions(fn));

      act(() => {
        result.current.ensureLoaded();
      });

      // In flight: loading true, options still empty.
      expect(result.current.isLoading).toBe(true);
      expect(result.current.options).toEqual([]);
      expect(fn).toHaveBeenCalledTimes(1);

      await act(async () => {
        resolveFn(optA);
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.options).toEqual(optA);
      expect(result.current.error).toBeNull();
    });

    it('supports a synchronous (non-Promise) function source', async () => {
      const fn = vi.fn(() => optA);
      const { result } = renderHook(() => useLazyOptions(fn));

      await act(async () => {
        result.current.ensureLoaded();
      });

      expect(result.current.options).toEqual(optA);
      expect(result.current.isLoading).toBe(false);
      expect(fn).toHaveBeenCalledTimes(1);
    });
  });

  // ── R4.3: error path ────────────────────────────────────────────────────────
  describe('error path (rejection)', () => {
    it('sets error and leaves options empty when the source rejects', async () => {
      const boom = new Error('feed unavailable');
      const fn = vi.fn().mockRejectedValue(boom);
      const { result } = renderHook(() => useLazyOptions(fn));

      await act(async () => {
        result.current.ensureLoaded();
      });

      await waitFor(() => {
        expect(result.current.error).toBe(boom);
      });
      expect(result.current.options).toEqual([]);
      expect(result.current.isLoading).toBe(false);
    });

    it('wraps a non-Error rejection into an Error', async () => {
      const fn = vi.fn().mockRejectedValue('string failure');
      const { result } = renderHook(() => useLazyOptions(fn));

      await act(async () => {
        result.current.ensureLoaded();
      });

      await waitFor(() => {
        expect(result.current.error).toBeInstanceOf(Error);
      });
      expect(result.current.error?.message).toBe('string failure');
      expect(result.current.options).toEqual([]);
    });

    it('sets error when a synchronous source throws', async () => {
      const fn = vi.fn(() => {
        throw new Error('sync boom');
      });
      const { result } = renderHook(() => useLazyOptions(fn));

      await act(async () => {
        result.current.ensureLoaded();
      });

      await waitFor(() => {
        expect(result.current.error).toBeInstanceOf(Error);
      });
      expect(result.current.error?.message).toBe('sync boom');
      expect(result.current.options).toEqual([]);
      expect(result.current.isLoading).toBe(false);
    });
  });

  // ── R4.4: cache reuse + idempotence ─────────────────────────────────────────
  describe('cache reuse / idempotence of ensureLoaded', () => {
    it('does not re-invoke the source on a second ensureLoaded', async () => {
      const fn = vi.fn().mockResolvedValue(optA);
      const { result } = renderHook(() => useLazyOptions(fn));

      await act(async () => {
        result.current.ensureLoaded();
      });
      expect(result.current.options).toEqual(optA);
      expect(fn).toHaveBeenCalledTimes(1);

      // Second call: idempotent, no re-invoke, options stay cached.
      await act(async () => {
        result.current.ensureLoaded();
      });
      expect(fn).toHaveBeenCalledTimes(1);
      expect(result.current.options).toEqual(optA);
    });

    it('is idempotent even while a resolve is still in flight', () => {
      const fn = vi.fn(() => new Promise<LazyOption[]>(() => {}));
      const { result } = renderHook(() => useLazyOptions(fn));

      act(() => {
        result.current.ensureLoaded();
        result.current.ensureLoaded();
        result.current.ensureLoaded();
      });

      expect(fn).toHaveBeenCalledTimes(1);
    });
  });

  // ── R4.5: reload forces re-resolve ──────────────────────────────────────────
  describe('reload', () => {
    it('forces a re-resolve of a function source', async () => {
      const fn = vi.fn().mockResolvedValueOnce(optA).mockResolvedValueOnce(optB);
      const { result } = renderHook(() => useLazyOptions(fn));

      await act(async () => {
        result.current.ensureLoaded();
      });
      expect(result.current.options).toEqual(optA);
      expect(fn).toHaveBeenCalledTimes(1);

      await act(async () => {
        result.current.reload();
      });
      expect(fn).toHaveBeenCalledTimes(2);
      expect(result.current.options).toEqual(optB);
    });

    it('is a no-op for an array source', () => {
      const { result } = renderHook(() => useLazyOptions(optA));

      act(() => {
        result.current.reload();
      });

      expect(result.current.options).toEqual(optA);
      expect(result.current.isLoading).toBe(false);
    });
  });

  // ── R4.4: depKey invalidation ───────────────────────────────────────────────
  describe('depKey invalidation', () => {
    it('re-resolves on the next ensureLoaded after depKey changes', async () => {
      const fn = vi.fn().mockResolvedValueOnce(optA).mockResolvedValueOnce(optB);
      const { result, rerender } = renderHook(
        ({ key }) => useLazyOptions(fn, key),
        { initialProps: { key: 'k1' } },
      );

      await act(async () => {
        result.current.ensureLoaded();
      });
      expect(result.current.options).toEqual(optA);
      expect(fn).toHaveBeenCalledTimes(1);

      // Same depKey → cache reuse, no re-invoke.
      await act(async () => {
        result.current.ensureLoaded();
      });
      expect(fn).toHaveBeenCalledTimes(1);

      // Changed depKey → next ensureLoaded re-resolves.
      rerender({ key: 'k2' });
      await act(async () => {
        result.current.ensureLoaded();
      });
      expect(fn).toHaveBeenCalledTimes(2);
      expect(result.current.options).toEqual(optB);
    });
  });
});
