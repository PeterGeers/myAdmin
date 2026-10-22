/**
 * Tests for the HOSTED (child) side of the iframe-resize handshake (spec 11 task 5.4; R5.2b / E4b).
 *
 * Covers both the pure emitter helpers (`iframeResize`) and the React glue hook
 * (`useIframeHeightBroadcast`): a framed form posts a well-formed, type-tagged height message on
 * mount and on content-height change; a NON-framed render posts nothing (the standalone /
 * in-app-preview case).
 */
import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import {
  IFRAME_RESIZE_MESSAGE_TYPE,
  IFRAME_RESIZE_SOURCE,
  buildResizeMessage,
  isFramed,
  isResizeMessage,
  measureDocumentHeight,
  postHeightToParent,
} from '../iframeResize';
import { useIframeHeightBroadcast } from '../useIframeHeightBroadcast';

describe('iframeResize — buildResizeMessage', () => {
  it('builds a type-tagged, source-namespaced structured payload with a ceil-ed integer height', () => {
    expect(buildResizeMessage(742.3)).toEqual({
      type: IFRAME_RESIZE_MESSAGE_TYPE,
      source: IFRAME_RESIZE_SOURCE,
      height: 743,
    });
  });
  it('clamps a non-finite / negative height to 0 (never emits garbage)', () => {
    expect(buildResizeMessage(-5).height).toBe(0);
    expect(buildResizeMessage(Number.NaN).height).toBe(0);
    expect(buildResizeMessage(Number.POSITIVE_INFINITY).height).toBe(0);
  });
});

describe('iframeResize — isResizeMessage (the shape guard the parent uses)', () => {
  it('accepts a well-formed message', () => {
    expect(isResizeMessage(buildResizeMessage(100))).toBe(true);
  });
  it('rejects wrong type / source / height shapes and non-objects', () => {
    expect(isResizeMessage(null)).toBe(false);
    expect(isResizeMessage({ type: 'other', source: IFRAME_RESIZE_SOURCE, height: 1 })).toBe(false);
    expect(isResizeMessage({ type: IFRAME_RESIZE_MESSAGE_TYPE, source: 'x', height: 1 })).toBe(false);
    expect(
      isResizeMessage({ type: IFRAME_RESIZE_MESSAGE_TYPE, source: IFRAME_RESIZE_SOURCE, height: 'big' }),
    ).toBe(false);
  });
});

describe('iframeResize — isFramed', () => {
  it('false when the window is its own parent (standalone render)', () => {
    const win = {} as unknown as Window;
    (win as unknown as { parent: unknown }).parent = win;
    expect(isFramed(win)).toBe(false);
  });
  it('true when a different window owns the frame (embedded)', () => {
    const parent = {} as Window;
    const win = { parent } as unknown as Window;
    expect(isFramed(win)).toBe(true);
  });
});

describe('iframeResize — measureDocumentHeight', () => {
  it('takes the largest of the body/html scroll+offset metrics', () => {
    const doc = {
      body: { scrollHeight: 500, offsetHeight: 480 },
      documentElement: { clientHeight: 400, scrollHeight: 520, offsetHeight: 510 },
    } as unknown as Document;
    expect(measureDocumentHeight(doc)).toBe(520);
  });
});

describe('iframeResize — postHeightToParent', () => {
  it('posts a structured message to the parent when framed', () => {
    const postMessage = vi.fn();
    const parent = { postMessage } as unknown as Window;
    const win = { parent } as unknown as Window;
    postHeightToParent(321, { win });
    expect(postMessage).toHaveBeenCalledWith(buildResizeMessage(321), '*');
  });
  it('targets a supplied parent origin when known', () => {
    const postMessage = vi.fn();
    const parent = { postMessage } as unknown as Window;
    const win = { parent } as unknown as Window;
    postHeightToParent(100, { win, targetOrigin: 'https://sites.google.com' });
    expect(postMessage).toHaveBeenCalledWith(buildResizeMessage(100), 'https://sites.google.com');
  });
  it('is a NO-OP when not framed (standalone)', () => {
    const postMessage = vi.fn();
    const win = {} as unknown as Window;
    (win as unknown as { parent: unknown }).parent = win;
    (win as unknown as { postMessage: typeof postMessage }).postMessage = postMessage;
    postHeightToParent(100, { win });
    expect(postMessage).not.toHaveBeenCalled();
  });
});

describe('useIframeHeightBroadcast — the React glue', () => {
  function framedWindow(postMessage = vi.fn()) {
    const parent = { postMessage } as unknown as Window;
    const win = {
      parent,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      // No ResizeObserver on this fake → the hook falls back to the resize listener only.
    } as unknown as Window;
    return { win, postMessage };
  }

  const doc = {
    body: { scrollHeight: 640, offsetHeight: 600 },
    documentElement: { clientHeight: 500, scrollHeight: 610, offsetHeight: 600 },
  } as unknown as Document;

  it('posts the initial height on mount when framed', () => {
    const { win, postMessage } = framedWindow();
    renderHook(() => useIframeHeightBroadcast({ win, doc }));
    expect(postMessage).toHaveBeenCalledWith(buildResizeMessage(640), '*');
  });

  it('registers a window resize listener and cleans it up on unmount', () => {
    const { win } = framedWindow();
    const { unmount } = renderHook(() => useIframeHeightBroadcast({ win, doc }));
    expect(win.addEventListener).toHaveBeenCalledWith('resize', expect.any(Function));
    unmount();
    expect(win.removeEventListener).toHaveBeenCalledWith('resize', expect.any(Function));
  });

  it('does NOT post when not framed (standalone render)', () => {
    const postMessage = vi.fn();
    const win = {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Window;
    (win as unknown as { parent: unknown }).parent = win;
    (win as unknown as { postMessage: typeof postMessage }).postMessage = postMessage;
    renderHook(() => useIframeHeightBroadcast({ win, doc }));
    expect(postMessage).not.toHaveBeenCalled();
  });

  it('does nothing when disabled', () => {
    const { win, postMessage } = framedWindow();
    renderHook(() => useIframeHeightBroadcast({ win, doc, enabled: false }));
    expect(postMessage).not.toHaveBeenCalled();
  });
});
