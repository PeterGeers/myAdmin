/**
 * Stub for @zag-js/focus-visible in jsdom test environment.
 *
 * The real module monkey-patches HTMLElement.prototype.focus which is
 * getter-only in jsdom 29+, causing "Cannot set property focus" errors.
 * This stub provides no-op replacements so Chakra UI components render
 * without crashing in tests.
 */
export function trackFocusVisible(fn: (visible: boolean) => void) {
  fn(false);
  return () => {};
}
