# Custom Domains — Requirements

## User Stories

### US-1: Tenant Uses Own Private Domain

**As a** tenant,
**I want** my private URL (e.g., `www.acme-rentals.nl`) to serve my landing page,
**so that** visitors see my brand in the address bar and the URL stays exactly as-is (no redirect).

**Acceptance Criteria:**

- [ ] Tenant can register a custom domain in the admin panel (with or without `www`)
- [ ] System provides DNS instructions depending on domain type:
  - Subdomain (`www.x.nl`): CNAME record pointing to CloudFront
  - Root domain (`x.nl`): ALIAS/ANAME record, or redirect instruction if provider doesn't support it
- [ ] System verifies domain ownership via DNS CNAME record (ACM validation)
- [ ] Once verified, visiting `www.acme-rentals.nl` serves the tenant's `index.html` + `landing.json`
- [ ] Browser URL stays `www.acme-rentals.nl` — no redirect to another domain
- [ ] SSL/TLS is provisioned automatically (ACM certificate)
- [ ] If domain verification fails or is revoked, a helpful error page is shown
- [ ] Tenant can remove a custom domain at any time
- [ ] OG meta tags use the custom domain as `og:url` / canonical

---

### US-2: Tenant Uses Jabaki Subdomain

**As the** myAdmin owner,
**I want** to offer tenants an optional `slug.jabaki.nl` subdomain that loads their landing page,
**so that** tenants without their own domain still get a clean, professional URL.

**Acceptance Criteria:**

- [ ] Wildcard DNS `*.jabaki.nl` routes all subdomains to CloudFront
- [ ] Wildcard ACM certificate covers `*.jabaki.nl`
- [ ] Visiting `acme-rentals.jabaki.nl` serves the tenant's `index.html` + `landing.json`
- [ ] Browser URL stays `acme-rentals.jabaki.nl` — no redirect
- [ ] The slug used is the tenant's existing `tenant_slugs.slug` value
- [ ] Tenants can enable/disable the Jabaki subdomain in their admin panel
- [ ] No additional cost to tenants for using the Jabaki subdomain
- [ ] OG meta tags use `slug.jabaki.nl` as `og:url` / canonical when this is the primary URL

---

### US-3: URL Stays As-Is (Both Scenarios)

**As a** visitor,
**I want** the URL to remain unchanged in my browser address bar,
**so that** I trust the site I'm on and can bookmark/share the clean URL.

**Acceptance Criteria:**

- [ ] No HTTP 301/302 redirects at any point in the flow
- [ ] CloudFront serves content directly from the requested host
- [ ] Internal links within the landing page use relative URLs (no domain hardcoded)
- [ ] Shared/bookmarked URLs continue to work identically

---

## Non-Functional Requirements

### Performance

- Custom domain resolution: no additional latency vs. CloudFront default domain
- SSL handshake: standard CloudFront TLS performance
- No extra DNS hops (CNAME directly to CloudFront distribution)

### Security

- Domain verification required before activation (prevents domain squatting)
- ACM certificates: AWS-managed, auto-renewing
- One tenant per custom domain (no sharing)
- Jabaki subdomains are system-controlled — tenants cannot impersonate other slugs

### Availability

- Same availability as existing CloudFront distribution (99.9%+)
- Domain verification status checked periodically (daily)
- Graceful degradation: if custom domain cert is pending, show info page

---

## Out of Scope

- Multi-page routing (landing pages remain single-page)
- Root domain support without `www` is supported but depends on the tenant's DNS provider (documented as customer action, not a system limitation)
- Custom domain email (MX records)
- Domain purchase/registration (tenant brings their own)
- A/B testing between domains
- Multiple custom domains per tenant (one custom domain + one Jabaki subdomain max)

---

## Relationship to Existing Design

The current architecture already supports the content delivery:

- `{slug}/index.html` and `{slug}/landing.json` are in S3
- CloudFront has a URL rewrite function (`/p/{slug}` → `{slug}/index.html`)

This feature adds **host-based routing** on top:

- Incoming `Host: acme-rentals.jabaki.nl` → resolve slug `acme-rentals` → serve `acme-rentals/index.html`
- Incoming `Host: www.acme-rentals.nl` → look up custom domain → resolve slug → serve `{slug}/index.html`

The content in S3 is unchanged. Only the routing and SSL layer changes.
