/**
 * `useIframeHeightBroadcast` — the React glue that drives the hosted-form side of the iframe-resize
 * handshake (spec 11 task 5.4; R5.2b / E4b).
 *
 * Mounted by the public application-form route (`PublicApplicationFormRoute`), it posts the
 * document's content height to the embedding parent via {@link postHeightToParent}:
 *  - once on mount (so an iframe sized for the initial render grows to the real height), and
 *  - whenever the content height changes — driven by a `ResizeObserver` on the body (locale swap,
 *    a server-error summary appearing, the field list growing), with a `window` resize listener as
 *    a fallback for engines without `ResizeObserver`.
 *
 * It is a NO-OP when the form is not framed (standalone `<slug>.jabaki.nl/apply` or the in-app
 * preview) because `postHeightToParent` short-circuits there — so the hook is safe to always mount.
 */
import { useEffect } from 'react';
import { isFramed, measureDocumentHeight, postHeightToParent } from './iframeResize';

export interface UseIframeHeightBroadcastOptions {
  /** Test seam — override the window (defaults to the real `window`). */
  win?: Window;
  /** Test seam — override the document (defaults to the real `document`). */
  doc?: Document;
  /** When false the hook does nothing (e.g. an explicit standalone render). Default true. */
  enabled?: boolean;
}

/**
 * Broadcast this document's content height to the parent frame on mount + on every content-height
 * change, for as long as the component is mounted.
 */
export function useIframeHeightBroadcast(options: UseIframeHeightBroadcastOptions = {}): void {
  const { win = window, doc = document, enabled = true } = options;

  useEffect(() => {
    // Only attach observers when we are actually embedded — a standalone render never posts.
    if (!enabled || !isFramed(win)) return;

    const emit = () => postHeightToParent(measureDocumentHeight(doc), { win });

    // Initial signal — size the iframe to the first real render.
    emit();

    // Observe the body so any content-driven height change re-posts. ResizeObserver is available
    // in every browser the public form targets; the window-resize listener covers older engines /
    // viewport changes that do not resize the body node itself.
    const RO = (win as unknown as { ResizeObserver?: typeof ResizeObserver }).ResizeObserver;
    let observer: ResizeObserver | undefined;
    if (RO && doc.body) {
      observer = new RO(() => emit());
      observer.observe(doc.body);
    }

    win.addEventListener('resize', emit);
    return () => {
      observer?.disconnect();
      win.removeEventListener('resize', emit);
    };
  }, [win, doc, enabled]);
}

export default useIframeHeightBroadcast;
