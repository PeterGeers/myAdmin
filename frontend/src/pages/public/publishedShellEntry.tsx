/**
 * Standalone boot entry for the PUBLISHED application-form shell (spec 14 Task 5.1, R5.4).
 *
 * This is the thin client bootstrap that the server-rendered `{slug}/index.html` artifact loads.
 * It is DELIBERATELY SEPARATE from the admin SPA's `index.tsx` (which wires `App`, the router,
 * Amplify/auth, i18n, `HelmetProvider`): the published page is "self-contained" (R5.4) — it boots
 * ONLY the form renderer, so the published artifact ships the minimum, not the whole SPA.
 *
 * The outer HTML scaffold (the `<head>` SEO/OG meta + the single `<style>` + the `<body>` mount
 * point `#app-root`) is produced SERVER-SIDE by the shared `page_shell` (`sam/shared/page_shell.
 * render_page`) at publish time (spec 14 Tasks 8/9 — the live S3 write stays GATED). This entry
 * fills that `#app-root` mount point by rendering {@link PublishedApplicationShell}, which resolves
 * the slug, fetches `GET {slug}`, and renders through the one `ApplicationFormRenderer`.
 *
 * It initializes i18n (the non-form state messages — {@link ApplicationStateMessage} — are
 * bilingual) and nothing else; there is no Amplify, no auth, no app router.
 *
 * _Requirements: R5.4_
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import '../../i18n'; // the bilingual non-form state copy resolves per locale
import { PublishedApplicationShell, PUBLISHED_SHELL_MOUNT_ID } from './PublishedApplicationShell';

/**
 * Mount the published application-form shell into the `page_shell` body mount point. Returns the
 * created React root (or `null` when the mount point is absent) so a caller/test can control the
 * lifecycle; the default auto-boot below runs it against the real DOM.
 */
export function mountPublishedApplicationShell(
  mountId: string = PUBLISHED_SHELL_MOUNT_ID,
): ReactDOM.Root | null {
  const container = document.getElementById(mountId);
  if (!container) {
    // The server-rendered scaffold must carry `#app-root`; if it is missing there is nothing to
    // boot into (a blank page rather than a thrown error — never crash the published artifact).
    return null;
  }
  const root = ReactDOM.createRoot(container);
  root.render(
    <React.StrictMode>
      <PublishedApplicationShell />
    </React.StrictMode>,
  );
  return root;
}

// Auto-boot when this entry is loaded as the published artifact's script. Guarded so importing the
// module in a test (to exercise `mountPublishedApplicationShell` explicitly) does not double-mount.
if (typeof document !== 'undefined' && !import.meta.env?.VITEST) {
  mountPublishedApplicationShell();
}
