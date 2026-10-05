/**
 * Property-based tests for the useLazyOptions hook.
 *
 * Uses fast-check 4.4.0 with a minimum of 100 iterations and the 30000ms timeout convention
 * (`33-frontend-testing.md`, Requirement 9.5).
 *
 * These express the hook contract from design.md ("useLazyOptions" + Correctness Properties /
 * Testing Strategy) as universal invariants over arbitrary option arrays and arbitrary depKeys:
 *   - Array source passthrough: for any array, `options` equals the input and `isLoading=false`
 *     with no ensureLoaded needed (R4.1).
 *   - Async resolve: for any resolver returning array X, after ensureLoaded settles `options`
 *     equals X and `error` is null (R4.2).
 *   - Idempotence / caching: for any option set, repeated ensureLoaded calls (no depKey change)
 *     invoke the source exactly once (R4.4 cache reuse, R4.5 ensureLoaded contract).
 *   - depKey invalidation: for any depKey change, the next ensureLoaded re-resolves — the source
 *     is invoked again (R4.4).
 *
 * The async source is modelled as a plain function returning Promise.resolve over a
 * fast-check-generated option array — no real network is involved.
 *
 * renderHook resolution is async while fast-check's property callback is synchronous, so (matching
 * the existing useTableConfig.property.test.ts convention) each property runs as a loop over
 * `fc.sample(arb, 100)` inputs rather than inside `fc.assert`.
 *
 * @see .kiro/specs/Common/Frameworks/lazy-select/design.md
 * _Requirements: 4.1, 4.2, 4.4, 9.5_
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import fc from 'fast-check';
import { useLazyOptions } from '../useLazyOptions';
import type { LazyOption } from '../../components/common/lazySelect.types';

// Property-based tests with async renderHook need the extended timeout (Requirement 9.5).
vi.setConfig({ testTimeout: 30000 });

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** A single LazyOption: a required string `value` and an optional string `label`. */
const optionArbitrary: fc.Arbitrary<LazyOption> = fc.record(
  {
    value: fc.string({ minLength: 1, maxLength: 8 }),
    label: fc.option(fc.string({ minLength: 0, maxLength: 12 }), { nil: undefined }),
  },
  { requiredKeys: ['value'] },
);

/** An arbitrary options array (0-6 entries). */
const optionsArbitrary: fc.Arbitrary<LazyOption[]> = fc.array(optionArbitrary, {
  minLength: 0,
  maxLength: 6,
});

/** An arbitrary depKey. */
const depKeyArbitrary: fc.Arbitrary<string> = fc.string({ minLength: 0, maxLength: 8 });

// ---------------------------------------------------------------------------
// Property: Array source passthrough (R4.1)
// ---------------------------------------------------------------------------

describe('useLazyOptions property: array source passthrough', () => {
  /**
   * **Validates: Requirements 4.1**
   *
   * For any array source, `options` equals the input array, `isLoading` is false, and `error` is
   * null — with no `ensureLoaded` needed.
   */
  it('exposes any array unchanged with isLoading=false and error=null', () => {
    const inputs = fc.sample(optionsArbitrary, 100);

    for (const arr of inputs) {
      const { result, unmount } = renderHook(() => useLazyOptions(arr));

      expect(result.current.options).toEqual(arr);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeNull();

      unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// Property: Async resolve fidelity (R4.2)
// ---------------------------------------------------------------------------

describe('useLazyOptions property: async resolve fidelity', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * For any async source resolving to an arbitrary array X, after `ensureLoaded` settles the
   * `options` equal X, `error` is null, and `isLoading` is false.
   */
  it('resolves options to exactly the array the source returns', async () => {
    const inputs = fc.sample(optionsArbitrary, 100);

    for (const arr of inputs) {
      const fn = vi.fn(() => Promise.resolve(arr));
      const { result, unmount } = renderHook(() => useLazyOptions(fn));

      // Before ensureLoaded: empty, not loading, source untouched.
      expect(result.current.options).toEqual([]);
      expect(fn).not.toHaveBeenCalled();

      await act(async () => {
        result.current.ensureLoaded();
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.options).toEqual(arr);
      expect(result.current.error).toBeNull();

      unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// Property: Idempotence / caching (R4.4 cache reuse)
// ---------------------------------------------------------------------------

describe('useLazyOptions property: ensureLoaded idempotence / caching', () => {
  /**
   * **Validates: Requirements 4.4**
   *
   * For any option set, repeated `ensureLoaded` calls (with no depKey change) invoke the source
   * exactly once and keep the cached options.
   */
  it('invokes the source exactly once across repeated ensureLoaded calls', async () => {
    // Also vary the number of repeat calls (2-5) to widen coverage.
    const inputs = fc.sample(fc.tuple(optionsArbitrary, fc.integer({ min: 2, max: 5 })), 100);

    for (const [arr, repeats] of inputs) {
      const fn = vi.fn(() => Promise.resolve(arr));
      const { result, unmount } = renderHook(() => useLazyOptions(fn));

      for (let i = 0; i < repeats; i += 1) {
         
        await act(async () => {
          result.current.ensureLoaded();
        });
      }

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(fn).toHaveBeenCalledTimes(1);
      expect(result.current.options).toEqual(arr);

      unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// Property: depKey invalidation (R4.4)
// ---------------------------------------------------------------------------

describe('useLazyOptions property: depKey invalidation', () => {
  /**
   * **Validates: Requirements 4.4**
   *
   * For any pair of DISTINCT depKeys, resolving under the first and then re-running `ensureLoaded`
   * after the depKey changes re-invokes the source (a second call), and the options reflect the
   * second resolution.
   */
  it('re-resolves on the next ensureLoaded after the depKey changes', async () => {
    const inputs = fc.sample(
      fc
        .tuple(optionsArbitrary, optionsArbitrary, depKeyArbitrary, depKeyArbitrary)
        // Only meaningful when the two depKeys actually differ.
        .filter(([, , k1, k2]) => k1 !== k2),
      100,
    );

    for (const [arr1, arr2, key1, key2] of inputs) {
      const fn = vi.fn().mockResolvedValueOnce(arr1).mockResolvedValueOnce(arr2);
      const { result, rerender, unmount } = renderHook(
        ({ key }) => useLazyOptions(fn, key),
        { initialProps: { key: key1 } },
      );

      await act(async () => {
        result.current.ensureLoaded();
      });
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });
      expect(fn).toHaveBeenCalledTimes(1);
      expect(result.current.options).toEqual(arr1);

      // Same depKey → cache reuse, no re-invoke.
      await act(async () => {
        result.current.ensureLoaded();
      });
      expect(fn).toHaveBeenCalledTimes(1);

      // Changed depKey → next ensureLoaded re-resolves.
      rerender({ key: key2 });
      await act(async () => {
        result.current.ensureLoaded();
      });
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });
      expect(fn).toHaveBeenCalledTimes(2);
      expect(result.current.options).toEqual(arr2);

      unmount();
    }
  });
});
