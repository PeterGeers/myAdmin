/**
 * Public Landing Page Service
 *
 * Fetches the published `landing.json` for a tenant's public landing page from
 * CloudFront/S3. This is a PUBLIC, UNAUTHENTICATED, cross-origin request to a
 * static asset host — it deliberately does NOT go through `apiService`:
 *
 *  - `apiService` prepends the Flask `API_BASE_URL` and attaches JWT/tenant auth
 *    headers. Both are wrong here: the target is the CloudFront public-pages
 *    origin (`VITE_CLOUDFRONT_PUBLIC_PAGES_URL`), not the API, and no visitor is
 *    authenticated. Routing this through `apiService` would hit the wrong origin
 *    and force inappropriate auth headers onto a public endpoint.
 *
 * Keeping the single `fetch(` for public pages in the service layer (instead of
 * inline in the page component) centralizes base-URL resolution and keeps the
 * frontend's "no raw fetch outside src/services/" guard clean.
 */

/** Shape of the published landing.json document served from CloudFront/S3. */
export interface LandingPageData {
  tenant_slug: string;
  published_at: string;
  version: number;
  branding: {
    name: string;
    tagline: string;
    logo_url: string;
    color_primary: string;
    color_accent: string;
  };
  footer: {
    company_name: string;
    address: string;
    postal_city: string;
    country: string;
    phone: string;
    email: string;
    coc: string;
    vat: string;
    social_links: Record<string, string>;
  };
  seo: {
    title: string;
    description: string;
    og_image: string;
    canonical_url: string;
  };
  settings: {
    show_share_buttons: boolean;
  };
  sections: Array<{
    id: string;
    type: string;
    layout: string;
    properties: Record<string, unknown>;
  }>;
}

/** Result of attempting to load a tenant's public landing page. */
export type LandingFetchResult =
  | { status: 'success'; data: LandingPageData }
  | { status: 'not_found' }
  | { status: 'error'; message: string };

/**
 * Resolve the CloudFront/S3 base URL that serves tenant public pages.
 *
 * Uses `VITE_CLOUDFRONT_PUBLIC_PAGES_URL` when configured (trailing slash
 * trimmed), falling back to the current origin for local/dev where published
 * assets are served from the same host.
 */
export function getCloudFrontBaseUrl(): string {
  const envUrl = import.meta.env.VITE_CLOUDFRONT_PUBLIC_PAGES_URL;
  if (envUrl) return envUrl.replace(/\/$/, '');
  // Fallback: use current origin (dev/local)
  return window.location.origin;
}

/**
 * Fetch the published landing.json for a tenant from CloudFront/S3.
 *
 * Public and unauthenticated by design — see the module header for why this does
 * not go through `apiService`.
 *
 * @param tenantSlug - The tenant slug segment from the `/p/:tenantSlug` route.
 * @param options - Optional overrides: a pre-resolved base URL and an
 *   AbortSignal so the caller can cancel an in-flight request on unmount.
 * @returns A discriminated result: `success` with the parsed data,
 *   `not_found` for 404/403, or `error` with a human-readable message.
 */
export async function fetchLandingData(
  tenantSlug: string,
  options: { baseUrl?: string; signal?: AbortSignal } = {},
): Promise<LandingFetchResult> {
  const baseUrl = options.baseUrl ?? getCloudFrontBaseUrl();
  const url = `${baseUrl}/${tenantSlug}/landing.json`;

  try {
    const response = await fetch(url, { signal: options.signal });

    if (response.status === 404 || response.status === 403) {
      return { status: 'not_found' };
    }

    if (!response.ok) {
      return {
        status: 'error',
        message: `Failed to load page (${response.status})`,
      };
    }

    const data: LandingPageData = await response.json();
    return { status: 'success', data };
  } catch {
    return { status: 'error', message: 'Failed to load page' };
  }
}
