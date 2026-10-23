/**
 * Public application-form ROUTE wrapper (the missing mount that caused the preview 404).
 *
 * The public application-form components (`PublicApplicationPage` → `ApplicationFormPage` →
 * `ApplicationFormRenderer`) were all built + tested but never mounted on a route, so the
 * builder's preview iframe (pointed at `<slug>.jabaki.nl/apply`) loaded a document that had no
 * application-form route and fell through to the landing page / NotFound — a 404 for the applicant.
 *
 * This wrapper closes that gap by COMPOSING the already-tested pieces into one self-contained route
 * component (mirroring `PublicLandingPage`): it resolves the tenant slug the SAME way the landing
 * page does — from the host (`<slug>.jabaki.nl`, the deployed public-pages pattern) with a dev/path
 * fallback (`/p/:slug/apply`) — then renders the readiness/404-aware `PublicApplicationPage`,
 * supplying the submit/consent/locale `ApplicationFormPage` as its `renderForm` success slot.
 *
 * No new hosting is introduced: `<slug>.jabaki.nl/apply` already resolves to the slug's SPA
 * `index.html` via the existing CloudFront `*.jabaki.nl` rewrite (a non-file path → `/<slug>/
 * index.html`); this component is simply what that SPA now renders for the `/apply` path.
 *
 * Route: host `<slug>.jabaki.nl/apply` (prod) OR `/p/:slug/apply` (dev/path fallback).
 */

import React from 'react';
import { Box, Center, Spinner } from '@chakra-ui/react';
import { PublicApplicationPage } from '../../components/public/application/PublicApplicationPage';
import { ApplicationFormPage } from '../../components/public/application/ApplicationFormPage';
import { useIframeHeightBroadcast } from '../../components/public/application/useIframeHeightBroadcast';
import { PUBLIC_FORM_HOST_SUFFIX } from '../../components/TenantAdmin/MembersConfig/applicationShellForm';

/**
 * Resolve the tenant slug for the application form. Host-based first (`<slug>.jabaki.nl`, the
 * deployed public-pages pattern — the slug is the left-most label), then a path fallback
 * (`/p/:slug/apply`) for local dev where everything is served from one host. Returns `null` when
 * neither yields a slug so the page can render its non-probeable not-found state.
 */
export function resolveApplicationSlug(
  hostname: string = window.location.hostname,
  pathname: string = window.location.pathname,
): string | null {
  const host = (hostname || '').toLowerCase();
  const suffix = `.${PUBLIC_FORM_HOST_SUFFIX}`;
  if (host.endsWith(suffix)) {
    const label = host.slice(0, host.length - suffix.length);
    // A single left-most label that is a valid slug (no further dots, not `www`).
    if (label && label !== 'www' && /^[a-z0-9-]+$/.test(label)) return label;
  }

  const basePath = import.meta.env.BASE_URL?.replace(/\/$/, '') || '';
  const path = pathname.startsWith(basePath) ? pathname.slice(basePath.length) : pathname;
  const match = path.match(/^\/p\/([a-z0-9-]+)\/apply\/?$/);
  return match ? match[1] : null;
}

const PublicApplicationFormRoute: React.FC = () => {
  const slug = resolveApplicationSlug();

  // Responsive iframe-resize handshake (E4b / R5.2b): when this hosted form is embedded via
  // <iframe> in an external site, broadcast its content height to the parent so the embed snippet's
  // listener can grow the iframe to fit (no clipping inside a sandboxed Google Sites gadget). A
  // no-op when not framed (standalone render / in-app preview).
  useIframeHeightBroadcast();

  if (!slug) {
    // No resolvable slug → render the page with an obviously-forged slug so it shows the
    // non-probeable not-found state (never a blank screen).
    return (
      <PublicApplicationPage
        tenantSlug="__unknown__"
        renderForm={() => null}
      />
    );
  }

  return (
    <React.Suspense
      fallback={
        <Center minH="100vh" bg="white">
          <Spinner size="xl" color="orange.400" thickness="4px" />
        </Center>
      }
    >
      <Box>
        <PublicApplicationPage
          tenantSlug={slug}
          renderForm={(config) => <ApplicationFormPage tenantSlug={slug} config={config} />}
        />
      </Box>
    </React.Suspense>
  );
};

export default PublicApplicationFormRoute;
