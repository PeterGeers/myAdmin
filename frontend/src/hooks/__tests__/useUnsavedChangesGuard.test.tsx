/**
 * Tests for the unsaved-changes navigate-away guard (s5c task 2.6 / R3.6).
 *
 * Verifies:
 *  - a `beforeunload` listener is registered only while dirty, and cleaned up otherwise;
 *  - the handler warns (sets returnValue) when the page would unload with unsaved edits;
 *  - `confirmDiscard()` prompts only when dirty and returns the user's choice.
 */
import { vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useUnsavedChangesGuard } from '../useUnsavedChangesGuard';

describe('useUnsavedChangesGuard', () => {
  let addSpy: ReturnType<typeof vi.spyOn>;
  let removeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    addSpy = vi.spyOn(window, 'addEventListener');
    removeSpy = vi.spyOn(window, 'removeEventListener');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does NOT register a beforeunload listener when clean', () => {
    renderHook(() => useUnsavedChangesGuard(false));
    const registered = addSpy.mock.calls.filter(([evt]: [string, ...unknown[]]) => evt === 'beforeunload');
    expect(registered).toHaveLength(0);
  });

  it('registers a beforeunload listener while dirty', () => {
    renderHook(() => useUnsavedChangesGuard(true));
    const registered = addSpy.mock.calls.filter(([evt]: [string, ...unknown[]]) => evt === 'beforeunload');
    expect(registered).toHaveLength(1);
  });

  it('warns (sets returnValue) on navigate-away when dirty', () => {
    renderHook(() => useUnsavedChangesGuard(true, 'unsaved!'));
    const handler = addSpy.mock.calls.find(([evt]: [string, ...unknown[]]) => evt === 'beforeunload')?.[1] as
      | ((e: BeforeUnloadEvent) => unknown)
      | undefined;
    expect(handler).toBeTruthy();

    const event = new Event('beforeunload') as BeforeUnloadEvent;
    const preventSpy = vi.spyOn(event, 'preventDefault');
    // The handler both sets returnValue and returns the message (Chrome/Firefox paths).
    const returned = handler!(event);

    expect(preventSpy).toHaveBeenCalled();
    // jsdom coerces Event.returnValue to a boolean, so assert the warning is engaged
    // via the returned message (the cross-browser way the native prompt is triggered).
    expect(returned).toBe('unsaved!');
    expect(event.returnValue).toBeTruthy();
  });

  it('removes the listener when the dirty flag clears', () => {
    const { rerender } = renderHook(({ dirty }) => useUnsavedChangesGuard(dirty), {
      initialProps: { dirty: true },
    });
    rerender({ dirty: false });
    const removed = removeSpy.mock.calls.filter(([evt]: [string, ...unknown[]]) => evt === 'beforeunload');
    expect(removed.length).toBeGreaterThanOrEqual(1);
  });

  it('confirmDiscard returns true immediately when clean (no prompt)', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { result } = renderHook(() => useUnsavedChangesGuard(false));
    let ok = false;
    act(() => {
      ok = result.current.confirmDiscard();
    });
    expect(ok).toBe(true);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('confirmDiscard prompts when dirty and returns the user choice', () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { result } = renderHook(() => useUnsavedChangesGuard(true));
    let ok = false;
    act(() => {
      ok = result.current.confirmDiscard();
    });
    expect(confirmSpy).toHaveBeenCalled();
    expect(ok).toBe(true);
  });
});
