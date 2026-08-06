# Tasks — Landing Page

## Phase 1: Infrastructure + Minimal Delivery (4-5 days)

- [x] 1.1 Create DynamoDB table `myadmin-landing-pages` (Terraform)
- [x] 1.2 Create S3 bucket `myadmin-public-pages-${env}` for published pages (Terraform)
- [x] 1.3 Create CloudFront distribution with OAC for public pages (Terraform)
- [x] 1.4 Update IAM policy for Railway backend (DynamoDB + S3 public bucket write access)
- [x] 1.5 Verify boto3 DynamoDB access from Railway (connectivity test)
- [x] 1.6 Create `tenant_slugs` table in MySQL (migration)
- [x] 1.7 Backend service: resolve slug → administration
- [x] 1.8 Admin UI: set/edit tenant slug in Tenant Admin settings
- [x] 1.9 Validate slug format (lowercase, alphanumeric + hyphens, unique)
- [x] 1.10 Service: `LandingPageService` with DynamoDB CRUD (get_draft, save_draft)
- [x] 1.11 Service: publish action (read DynamoDB → resolve branding → write S3 JSON + index.html)
- [x] 1.12 Service: unpublish action (delete S3 landing.json + index.html, update status)
- [x] 1.13 Route: `POST /api/landing/publish`
- [x] 1.14 Route: `POST /api/landing/unpublish`
- [x] 1.15 Branding resolution with fallback chain (landing_page → module branding)
- [x] 1.16 Backend: generate `index.html` per tenant at publish time (OG + Twitter Card tags pre-baked)
- [x] 1.17 CloudFront: route `/p/{slug}` → `{slug}/index.html`
- [x] 1.18 Route: `/p/:tenantSlug` in React (no auth guard)
- [x] 1.19 `PublicLandingPage.tsx` — fetch JSON from CloudFront URL
- [x] 1.20 `PublicThemeProvider.tsx` — apply brand colors from JSON
- [x] 1.21 `PublicLayout.tsx` — footer + social meta
- [x] 1.22 `SocialMetaTags.tsx` — OG + Twitter Card meta tag renderer (react-helmet-async)
- [x] 1.23 `HeroBlock.tsx` — first block renderer
- [x] 1.24 `AboutBlock.tsx` — second block renderer
- [x] 1.25 Footer component (renders from `footer` object in JSON, including social icons)
- [x] 1.26 404 handling for missing/unpublished slugs

**Exit criteria:** A hardcoded draft in DynamoDB can be published to S3 and rendered at `/p/test-tenant` with branding, footer, social icons, and OG tags readable by Facebook Sharing Debugger.

## Phase 2: CMS Block Editor (4-5 days)

- [x] 2.1 Route: `GET /api/landing/draft` (load from DynamoDB)
- [x] 2.2 Route: `PUT /api/landing/draft` (save to DynamoDB, auto-save support)
- [x] 2.3 Version increment on each save
- [x] 2.4 Auth: `@cognito_required` + `@tenant_required` on draft endpoints
- [x] 2.5 `LandingPageEditor.tsx` — main editor page in Tenant Admin
- [x] 2.6 Block list with drag-and-drop reorder
- [x] 2.7 Add block (select type from available types, filtered by active modules)
- [x] 2.8 Remove block (with confirmation)
- [x] 2.9 `BlockConfigurator.tsx` — per-block settings panel
- [x] 2.10 Layout variant selector per block
- [x] 2.11 Auto-save (debounced PUT on changes)
- [x] 2.12 `GalleryBlock.tsx` (image grid)
- [x] 2.13 `TestimonialsBlock.tsx` (quote cards)
- [x] 2.14 `FaqBlock.tsx` (accordion)
- [x] 2.15 `PricingBlock.tsx` (rate table)
- [x] 2.16 `CtaBlock.tsx` (call-to-action banner)
- [x] 2.17 `EmbedBlock.tsx` (sandboxed iframe, HTTPS-only validation)
- [x] 2.18 `ImageUploader.tsx` component
- [x] 2.19 Backend: upload to S3 public bucket (tenant-scoped prefix `{slug}/images/`)
- [x] 2.20 File type validation (jpg, png, webp, svg) + size limit (5MB)
- [x] 2.21 `PreviewPanel.tsx` — renders current draft as if published
- [x] 2.22 Toggle between edit and preview modes

**Exit criteria:** Tenant admin can add/edit/reorder blocks, upload images, preview, and publish — full round-trip working.

## Phase 3: Contact Form + Live Data + Social (3-4 days)

- [x] 3.1 `ContactBlock.tsx` — form with name, email, message fields
- [x] 3.2 Route: `POST /api/public/landing/{slug}/contact` (no auth)
- [x] 3.3 Create `landing_page_submissions` table (migration)
- [x] 3.4 Rate limiting (5 per email/hour, 10 per IP/hour)
- [x] 3.5 Honeypot field (reject if filled)
- [x] 3.6 Email validation + send notification to tenant via SES
- [x] 3.7 Store submission in MySQL + success/error feedback to visitor
- [x] 3.8 `PropertiesBlock.tsx` — render STR property cards
- [x] 3.9 `ServicesBlock.tsx` — render ZZP service listings
- [x] 3.10 Backend: `load_str_public_properties(tenant)` — data loader
- [x] 3.11 Backend: `load_zzp_public_services(tenant)` — data loader
- [x] 3.12 "Mark as public" toggle in STR property admin
- [x] 3.13 "Mark as public" toggle in ZZP service admin
- [x] 3.14 Publish enriches JSON with module data snapshots
- [x] 3.15 `BrandingSettings.tsx` — logo, colors, tagline, contact info
- [x] 3.16 Social media links section (Instagram, Facebook, Airbnb, Booking.com, LinkedIn, YouTube, TikTok, X/Twitter) with URL validation
- [x] 3.17 `SeoSettings.tsx` — title, description, OG image upload (1200×630px guidance)
- [x] 3.18 OG preview card (show how link appears when shared on Facebook/LinkedIn)
- [x] 3.19 Share buttons toggle (enable/disable visitor-facing share bar)
- [x] 3.20 `ShareButtons.tsx` — floating share bar (Facebook, X, WhatsApp, LinkedIn, Email)
- [x] 3.21 Share buttons use native share URLs (no API keys, no third-party scripts)
- [x] 3.22 Save branding/SEO/social settings to ParameterService (`landing_page` namespace)

**Exit criteria:** Contact form works end-to-end (visitor → MySQL → tenant email). Module data appears on published page. Social profile links render in footer. Share buttons functional when enabled. OG preview card shown in SEO settings.

## Phase 4: Polish + Versioning (2-3 days)

- [x] 4.1 Route: `GET /api/landing/versions` (query DynamoDB VERSION# items)
- [x] 4.2 Route: `POST /api/landing/rollback` (restore version, re-publish)
- [x] 4.3 `PublishControls.tsx` — publish button, version history list, rollback button
- [x] 4.4 Audit: record publish events in MySQL (who, when, version)
- [x] 4.5 Mobile-first responsive pass on all block renderers
- [x] 4.6 Test all layout variants on mobile/tablet/desktop
- [x] 4.7 Image lazy loading (`loading="lazy"`) + font/asset optimization
- [x] 4.8 Embed block: HTTPS-only URL enforcement
- [x] 4.9 Contact form: CAPTCHA option (reCAPTCHA v3, configurable)
- [x] 4.10 CloudFront: cache headers (5 min TTL)
- [x] 4.11 Input sanitization on contact form fields
- [x] 4.12 End-user manual: "How to set up your landing page" (NL + EN)
- [x] 4.13 Tenant Admin help text / tooltips in editor UI

**Exit criteria:** Production-ready feature with versioning, mobile support, security hardened, documented.

## Phase 5: Custom Domains (future — separate effort)

- [ ] 5.1 Subdomain routing (wildcard DNS `*.myadmin.app` + ACM cert)
- [ ] 5.2 Tenant resolution from HTTP Host header (Lambda@Edge or CloudFront Function)
- [ ] 5.3 Custom domain CNAME support (tenant registers in admin)
- [ ] 5.4 SSL provisioning per custom domain (ACM)
- [ ] 5.5 Domain verification flow (DNS TXT record)
- [ ] 5.6 Approval workflow for multi-user tenants
- [ ] 5.7 A/B testing support (serve different versions)
- [ ] 5.8 Scheduled re-publish for tenants with live data blocks

## Notes

- Phase 1 is the critical path — DynamoDB + S3 + CloudFront must be provisioned before any content work
- Phase 2 depends on Phase 1 (publish pipeline must work before editor makes sense)
- Phase 3 blocks (contact, properties, services) are independent of each other
- Phase 5 is intentionally deferred — requires DNS and cert management complexity
- `react-icons` and `react-helmet-async` are new frontend dependencies (Phase 1)
- The public S3 bucket is separate from the existing private `myadmin-shared-*` bucket

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["1.5", "1.6"] },
    { "id": 2, "tasks": ["1.7", "1.8", "1.9", "1.10"] },
    { "id": 3, "tasks": ["1.11", "1.12", "1.13", "1.14", "1.15", "1.16"] },
    {
      "id": 4,
      "tasks": [
        "1.17",
        "1.18",
        "1.19",
        "1.20",
        "1.21",
        "1.22",
        "1.23",
        "1.24",
        "1.25",
        "1.26"
      ]
    },
    { "id": 5, "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "id": 6, "tasks": ["2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11"] },
    {
      "id": 7,
      "tasks": [
        "2.12",
        "2.13",
        "2.14",
        "2.15",
        "2.16",
        "2.17",
        "2.18",
        "2.19",
        "2.20"
      ]
    },
    { "id": 8, "tasks": ["2.21", "2.22"] },
    {
      "id": 9,
      "tasks": [
        "3.1",
        "3.2",
        "3.3",
        "3.8",
        "3.9",
        "3.10",
        "3.11",
        "3.15",
        "3.16",
        "3.17"
      ]
    },
    {
      "id": 10,
      "tasks": [
        "3.4",
        "3.5",
        "3.6",
        "3.7",
        "3.12",
        "3.13",
        "3.14",
        "3.18",
        "3.19",
        "3.20",
        "3.21",
        "3.22"
      ]
    },
    { "id": 11, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"] },
    { "id": 12, "tasks": ["4.8", "4.9", "4.10", "4.11", "4.12", "4.13"] },
    {
      "id": 13,
      "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8"]
    }
  ]
}
```

## Dependencies

| Dependency                             | Required for | Status            |
| -------------------------------------- | ------------ | ----------------- |
| DynamoDB table                         | Phase 1      | New — Terraform   |
| S3 bucket (`myadmin-public-pages-*`)   | Phase 1      | New — Terraform   |
| CloudFront distribution                | Phase 1      | New — Terraform   |
| IAM policy (public bucket write)       | Phase 1      | New — Terraform   |
| `tenant_slugs` MySQL table             | Phase 1      | New — migration   |
| `landing_page_submissions` MySQL table | Phase 3      | New — migration   |
| SES (email)                            | Phase 3      | Existing          |
| ParameterService                       | Phase 1+     | Existing          |
| Cognito auth                           | Phase 2+     | Existing          |
| `react-icons` package                  | Phase 1      | New — npm install |
| `react-helmet-async` package           | Phase 1      | New — npm install |
