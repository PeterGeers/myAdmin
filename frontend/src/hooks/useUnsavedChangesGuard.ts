/**
 * Unsaved-changes navigate-away guard (s5c task 2.6 / R3.6, C-EDITOR).
 *
 * The pilot uses **save-once + an unsaved-changes guard** — no draft/publish. When a
 * sub-editor has uncommitted edits (`isDirty`), leaving the page (tab close, reload,
 * back/forward, external navigation) fires the browser's native `beforeunload` prompt.
 *
 * Draft/publish (edit, stop, continue next day) is DEFERRED to the generic framework
 * and is intentionally NOT built here.
 *
 * Returns a `confirmDiscard` helper so in-app navigation (e.g. switching sub-editors or
 * closing the editor) can guard the same way with a synchronous confirm dialog.
 */
import { useEffect, useCallback } from 'react';

const DEFAULT_MESSAGE =
  'You have unsaved changes. Leave without saving?';

export interface UnsavedChangesGuard {
  /**
   * Ask the user to confirm discarding unsaved edits. Returns `true` if it is safe to
   * proceed (no unsaved edits, or the user confirmed). Use this to gate in-app actions
   * like switching sub-editors or closing the editor.
   */
  confirmDiscard: () => boolean;
}

export function useUnsavedChangesGuard(
  isDirty: boolean,
  message: string = DEFAULT_MESSAGE,
): UnsavedChangesGuard {
  useEffect(() => {
    if (!isDirty) return;

    const handler = (event: BeforeUnloadEvent) => {
      // The spec-compliant way to trigger the native prompt.
      event.preventDefault();
      event.returnValue = message;
      return message;
    };

    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty, message]);

  const confirmDiscard = useCallback((): boolean => {
    if (!isDirty) return true;
    // eslint-disable-next-line no-alert
    return window.confirm(message);
  }, [isDirty, message]);

  return { confirmDiscard };
}

export default useUnsavedChangesGuard;
