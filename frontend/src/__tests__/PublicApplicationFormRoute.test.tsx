/**
 * Tests for the public application-form ROUTE wrapper's slug resolution
 * (the mount that fixes the preview 404).
 *
 * `resolveApplicationSlug` is the one genuinely new unit of logic: it resolves the tenant slug the
 * SAME way the landing page does — host-based (`<slug>.jabaki.nl`) first, then the dev/path
 * fallback (`/p/:slug/apply`). These pin that contract so the `/apply` route reaches the right
 * tenant and a forged/odd host yields `null` (→ the page's non-probeable not-found state).
 */
import { describe, it, expect } from 'vitest';
import { resolveApplicationSlug } from '../pages/public/PublicApplicationFormRoute';

describe('resolveApplicationSlug — host-based (<slug>.jabaki.nl)', () => {
  it('resolves the left-most label as the slug on the jabaki host', () => {
    expect(resolveApplicationSlug('h-dcn.jabaki.nl', '/apply')).toBe('h-dcn');
  });

  it('resolves regardless of the path on the jabaki host (root or /apply)', () => {
    expect(resolveApplicationSlug('hdcn-application-form.jabaki.nl', '/apply')).toBe(
      'hdcn-application-form',
    );
  });

  it('ignores the `www` label (not a tenant slug)', () => {
    expect(resolveApplicationSlug('www.jabaki.nl', '/apply')).toBeNull();
  });

  it('does not treat a multi-label host as a single slug', () => {
    // `a.b.jabaki.nl` → left part is `a.b`, which is not a flat slug.
    expect(resolveApplicationSlug('a.b.jabaki.nl', '/apply')).toBeNull();
  });
});

describe('resolveApplicationSlug — path fallback (/p/:slug/apply)', () => {
  it('resolves the slug from /p/:slug/apply on a non-jabaki host (local dev)', () => {
    expect(resolveApplicationSlug('localhost', '/p/h-dcn/apply')).toBe('h-dcn');
  });

  it('tolerates a trailing slash', () => {
    expect(resolveApplicationSlug('localhost', '/p/h-dcn/apply/')).toBe('h-dcn');
  });

  it('returns null for a non-matching path on a non-jabaki host', () => {
    expect(resolveApplicationSlug('localhost', '/p/h-dcn')).toBeNull();
    expect(resolveApplicationSlug('localhost', '/apply')).toBeNull();
  });
});
