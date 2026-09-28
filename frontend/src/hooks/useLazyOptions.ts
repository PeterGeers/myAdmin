/**
 * useLazyOptions Hook
 *
 * Normalizes a `LazyOptionsSource<V>` (an eager array OR a function returning (a Promise of) an
 * array) into a `{ options, isLoading, error, ensureLoaded, reload }` state, resolving a function
 * source on first open. It underpins the `LazySelect` building block but is usable independently.
 *
 * Behavior (design.md "useLazyOptions" + Requirement 4):
 * - Array source → `options` is the array, `isLoading=false`, `ensureLoaded` is a no-op (R4.1).
 * - Function source → the first `ensureLoaded()` invokes it; `isLoading` is true until it settles;
 *   success caches the result; rejection sets `error` and leaves `options=[]` (R4.2, R4.3).
 * - `ensureLoaded` is idempotent (resolves once); a changed `depKey` invalidates the cache so the
 *   next `ensureLoaded` re-resolves (R4.4); `reload` forces a re-resolve.
 * - Guards against setting state after unmount and against out-of-order / stale resolutions (a
 *   resolution whose request generation no longer matches is ignored).
 *
 * @module hooks/useLazyOptions
 * @see .kiro/specs/Common/Frameworks/lazy-select/design.md
 * _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { LazyOption, LazyOptionsSource, UseLazyOptionsResult } from '../components/common/lazySelect.types';

/** A source is a function (lazy) rather than an eager array. */
function isFunctionSource<V extends string>(
  source: LazyOptionsSource<V>,
): source is Exclude<LazyOptionsSource<V>, LazyOption<V>[]> {
  return typeof source === 'function';
}

export function useLazyOptions<V extends string = string>(
  source: LazyOptionsSource<V>,
  depKey?: string,
): UseLazyOptionsResult<V> {
  const isFn = isFunctionSource(source);

  // For an array source `options` is simply the array; for a function source it starts empty and is
  // populated once `ensureLoaded` resolves.
  const [resolved, setResolved] = useState<LazyOption<V>[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Keep the latest source/isFn in refs so the stable `ensureLoaded`/`reload` callbacks always read
  // the current source without needing it in their dependency lists.
  const sourceRef = useRef(source);
  sourceRef.current = source;
  const isFnRef = useRef(isFn);
  isFnRef.current = isFn;

  // Unmount guard: never set state after the component using the hook has unmounted.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Monotonic request generation. Incremented on every fresh resolve (first load, reload, depKey
  // change). A settling promise compares its captured generation against the current one and bails
  // if they differ, ignoring stale / out-of-order resolutions.
  const generationRef = useRef(0);
  // The generation whose resolution is currently cached/settled (or in flight). `-1` means nothing
  // has been requested yet for the current source.
  const requestedGenerationRef = useRef(-1);
  // The `depKey` the current cache was resolved against, so a changed key invalidates it.
  const cachedDepKeyRef = useRef<string | undefined>(undefined);

  const runResolve = useCallback((generation: number) => {
    let outcome: Promise<LazyOption<V>[]> | LazyOption<V>[];
    try {
      const fn = sourceRef.current as () => Promise<LazyOption<V>[]> | LazyOption<V>[];
      outcome = fn();
    } catch (err) {
      if (mountedRef.current && generation === generationRef.current) {
        setIsLoading(false);
        setError(err instanceof Error ? err : new Error(String(err)));
        setResolved([]);
      }
      return;
    }

    Promise.resolve(outcome).then(
      (result) => {
        // Ignore a stale resolution whose generation no longer matches.
        if (!mountedRef.current || generation !== generationRef.current) return;
        setResolved(result);
        setError(null);
        setIsLoading(false);
      },
      (err) => {
        if (!mountedRef.current || generation !== generationRef.current) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setResolved([]);
        setIsLoading(false);
      },
    );
  }, []);

  const ensureLoaded = useCallback(() => {
    // Array source → nothing to resolve (R4.1).
    if (!isFnRef.current) return;

    const alreadyRequested = requestedGenerationRef.current === generationRef.current;
    const depKeyChanged = cachedDepKeyRef.current !== depKey;

    // Idempotent: once requested for this generation and depKey, don't re-run (R4.4 cache reuse).
    if (alreadyRequested && !depKeyChanged) return;

    // A changed depKey invalidates the cache: bump the generation so any in-flight/settled result
    // for the old key is treated as stale (R4.4).
    if (depKeyChanged && alreadyRequested) {
      generationRef.current += 1;
    }

    const generation = generationRef.current;
    requestedGenerationRef.current = generation;
    cachedDepKeyRef.current = depKey;

    if (mountedRef.current) {
      setIsLoading(true);
      setError(null);
    }
    runResolve(generation);
  }, [depKey, runResolve]);

  const reload = useCallback(() => {
    // Force a re-resolve for a function source; array source has nothing to reload.
    if (!isFnRef.current) return;

    generationRef.current += 1;
    const generation = generationRef.current;
    requestedGenerationRef.current = generation;
    cachedDepKeyRef.current = depKey;

    if (mountedRef.current) {
      setIsLoading(true);
      setError(null);
    }
    runResolve(generation);
  }, [depKey, runResolve]);

  // Array source is a straight passthrough of the current array (R4.1); function source exposes the
  // cached resolution (empty until `ensureLoaded` settles).
  const options = isFn ? resolved : (source as LazyOption<V>[]);

  return {
    options,
    isLoading: isFn ? isLoading : false,
    error: isFn ? error : null,
    ensureLoaded,
    reload,
  };
}
