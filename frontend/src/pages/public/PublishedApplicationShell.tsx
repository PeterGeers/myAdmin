/**
 * Published application-form SHELL — the thin, self-contained client (spec 14 Task 5.1, R5.4).
 *
 * This is the client half of the PUBLISHED `{slug}/index.html` artifact. At publish time (spec 14
 * Tasks 8/9 — the live S3 write stays GATED) the SAM plane renders the OUTER scaffold via the
 * shared, plane-neutral `page_shell` (`sam/shared/page_shell.render_page` — the `<!DOCTYPE html>` +
 * `<head>` SEO/OG meta + the single `<style>` CSS block + a `<body>` carrying ONE mount point,
 * {@link PUBLISHED_SHELL_MOUNT_ID}). THIS component is the thin body that, when the page loads at
 * `{slug}.jabaki.nl`, fills that mount point: it
 *
 *  1. resolves the slug from the host/path ({@link resolveApplicationSlug}, host-based
 *     `{slug}.jabaki.nl` with a `/p/:slug/apply` dev fallback — the SAME resolver the in-app
 *     `/apply` route uses, so the published page and the preview agree on the slug), then
 *  2. fetches `GET {slug}` — the public field-config read (spec 14 Task 3's no-auth
 *     `GET …/field-config`) — through {@link PublicApplicationPage}, which owns the loading /
 *     publication-gate (409) / non-probeable 404 / error arms ({@link ApplicationStateMessage}),
 *     and on success renders the config-driven form through the EXISTING
 *     {@link ApplicationFormRenderer} via {@link ApplicationFormPage} (submit / consent / locale).
 *
 * ## One renderer, no fork (spec 14 one-renderer discipline)
 *
 * The published shell deliberately reuses the EXACT same composition the standalone `/apply` route
 * ({@link PublicApplicationFormRoute}) and the native landing-page block
 * (`ApplicationFormBlock`) use — `PublicApplicationPage` → `ApplicationFormPage` →
 * `ApplicationFormRenderer`. There is NO second renderer: the preview, the embedded block, and the
 * published page all draw the form through the one `ApplicationFormRenderer`, so they cannot drift.
 *
 * ## Self-contained (R5.4) — no SPA bundle / router / Amplify
 *
 * "Self-contained" means the published page does NOT depend on the full admin SPA: it boots the
 * renderer standalone. So this component carries its OWN minimal `ChakraProvider` (the public
 * white-page theme) and does NOT pull in `App`, the app router, Amplify/auth, or `HelmetProvider`
 * (the `<head>` meta is already server-rendered by `page_shell`). The standalone boot entry
 * ({@link ./publishedShellEntry}) mounts this into the `page_shell` mount point — a separate entry
 * from the SPA's `index.tsx`, so the published artifact ships only what the form needs.
 *
 * _Requirements: R5.4_
 */

import React from 'react';
import { Box, ChakraProvider, extendTheme } from '@chakra-ui/react';

import { PublicApplicationPage } from '../../components/public/application/PublicApplicationPage';
import { ApplicationFormPage } from '../../components/public/application/ApplicationFormPage';
import { useIframeHeightBroadcast } from '../../components/public/application/useIframeHeightBroadcast';
import { resolveApplicationSlug } from './PublicApplicationFormRoute';

/**
 * The id of the single `<div>` the server-rendered `page_shell` body carries as the client mount
 * point. The standalone boot entry ({@link ./publishedShellEntry}) mounts {@link
 * PublishedApplicationShell} into `document.getElementById(PUBLISHED_SHELL_MOUNT_ID)`. Kept here as
 * the ONE shared constant so the SAM-rendered scaffold and the client agree on where the form
 * mounts (a mismatch would render a blank published page).
 */
export const PUBLISHED_SHELL_MOUNT_ID = 'app-root';

/**
 * The published public form's own minimal theme — a quiet white page (the public form reads on a
 * white background, spec 13 R3), independent of the admin app's saturated-orange theme. Built here
 * so the published artifact never imports the full app theme/SPA.
 */
const publishedShellTheme = extendTheme({
  styles: {
    global: {
      body: { bg: 'white', color: 'gray.800' },
    },
  },
});

export interface PublishedApplicationShellProps {
  /**
   * Optional explicit slug — bypasses host/path resolution. Primarily a test seam; in production
   * the slug is resolved from `{slug}.jabaki.nl` (or the `/p/:slug/apply` dev fallback).
   */
  slug?: string | null;
  /** Optional pre-resolved public SAM API base URL (tests inject the MSW origin). */
  apiBaseUrl?: string;
  /** Optional pre-resolved Flask-plane logo base URL (tests inject it). */
  logoBaseUrl?: string;
}

/**
 * The thin published-shell body: resolve the slug, fetch `GET {slug}`, and render the form through
 * the one `ApplicationFormRenderer`. Carries its own minimal Chakra theme so it boots standalone
 * inside the server-rendered `page_shell` scaffold, with NO dependency on the admin SPA.
 */
export const PublishedApplicationShell: React.FC<PublishedApplicationShellProps> = ({
  slug: slugProp,
  apiBaseUrl,
  logoBaseUrl,
}) => {
  // Resolve the slug from the host/path unless one is supplied explicitly (test seam). The
  // host-based `{slug}.jabaki.nl` form is the deployed published-pages pattern.
  const slug = slugProp !== undefined ? slugProp : resolveApplicationSlug();

  // Responsive iframe-resize handshake (E4b / R5.2b): when the published page is embedded via
  // <iframe> on an external host, broadcast its content height so the embed snippet's listener can
  // grow the frame to fit. A no-op when not framed (the standalone published page / the preview).
  useIframeHeightBroadcast();

  return (
    <ChakraProvider theme={publishedShellTheme}>
      <Box data-testid="published-application-shell">
        {/* No resolvable slug → render with an obviously-forged slug so PublicApplicationPage shows
            the non-probeable not-found state (never a blank page). */}
        {!slug ? (
          <PublicApplicationPage tenantSlug="__unknown__" baseUrl={apiBaseUrl} renderForm={() => null} />
        ) : (
          <PublicApplicationPage
            tenantSlug={slug}
            baseUrl={apiBaseUrl}
            renderForm={(config) => (
              <ApplicationFormPage
                tenantSlug={slug}
                config={config}
                apiBaseUrl={apiBaseUrl}
                logoBaseUrl={logoBaseUrl}
              />
            )}
          />
        )}
      </Box>
    </ChakraProvider>
  );
};

export default PublishedApplicationShell;
