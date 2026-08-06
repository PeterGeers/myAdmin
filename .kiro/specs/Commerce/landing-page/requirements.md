# Landing Page — Requirements

## User Stories

### US-1: Tenant Admin Creates a Landing Page

**As a** tenant admin,
**I want to** configure a public landing page with my business branding and content,
**so that** potential customers can find and learn about my business online.

**Acceptance Criteria:**

- [ ] Admin can set branding (logo, colors, tagline, contact info)
- [ ] Admin can add/remove/reorder content blocks
- [ ] Admin can edit block content (text, images, links)
- [ ] Admin can preview the page before publishing
- [ ] Admin can publish the page to make it public
- [ ] Admin can unpublish the page to take it offline
- [ ] Page is accessible within 10 minutes of first configuration

---

### US-2: Visitor Views a Tenant Landing Page

**As a** visitor (no authentication),
**I want to** view a tenant's public landing page,
**so that** I can learn about their business, services, or properties.

**Acceptance Criteria:**

- [ ] Page loads without authentication
- [ ] Page loads in < 3 seconds on mobile
- [ ] Page shows tenant branding (logo, colors, name)
- [ ] Page renders configured blocks in the correct order
- [ ] Page has correct SEO meta tags (title, description)
- [ ] Page has Open Graph meta tags for social sharing (og:title, og:description, og:image, og:url)
- [ ] Page has Twitter Card meta tags (twitter:card, twitter:title, twitter:image)
- [ ] OG meta tags are present in the initial HTML (not JS-injected) so social crawlers can read them
- [ ] Page footer shows legal business details (name, address, CoC, VAT)
- [ ] Page footer shows social media profile icons (Instagram, Facebook, etc.) when configured
- [ ] No internal myAdmin data is exposed (no financials, no user info)

---

### US-3: Visitor Submits a Contact Form

**As a** visitor,
**I want to** send an inquiry via the contact form on the landing page,
**so that** I can reach the business without knowing their email.

**Acceptance Criteria:**

- [ ] Contact form collects: name, email, message (minimum)
- [ ] Submission is rate-limited (prevent spam)
- [ ] Honeypot field present (bot protection)
- [ ] Tenant receives the inquiry via email (SES)
- [ ] Submission stored in MySQL for the tenant to review
- [ ] Visitor sees a confirmation message after submission
- [ ] Form does not require authentication

---

### US-4: Tenant Admin Embeds External Widgets

**As a** tenant admin,
**I want to** embed a booking calendar or scheduling widget from an external platform,
**so that** visitors can check availability or book directly from my landing page.

**Acceptance Criteria:**

- [ ] Admin can add an `embed` block with an external URL
- [ ] Only `https://` URLs are accepted
- [ ] Widget renders in a sandboxed iframe
- [ ] No raw `<script>` tags allowed
- [ ] Multiple embed blocks can be added to one page

---

### US-5: Tenant Admin Uses Module Data

**As a** tenant admin with active STR or ZZP modules,
**I want to** include property listings or service descriptions from myAdmin on my landing page,
**so that** visitors see my current offerings without manual duplication.

**Acceptance Criteria:**

- [ ] STR tenant can add a `properties` block showing their listings
- [ ] ZZP tenant can add a `services` block showing their offerings
- [ ] Data is snapshotted at publish time (not live)
- [ ] Only items marked as "public" by the tenant appear
- [ ] Tenant can re-publish to update the snapshot

---

### US-6: Tenant Admin Manages Versions

**As a** tenant admin,
**I want to** see previous versions of my landing page and roll back if needed,
**so that** I can undo mistakes without rebuilding the page.

**Acceptance Criteria:**

- [ ] Each publish creates a version snapshot
- [ ] Admin can view a list of past versions (date, publisher)
- [ ] Admin can roll back to a previous version with one click
- [ ] Rollback re-publishes the old version to S3

### US-7: Tenant Admin Configures Social Media

**As a** tenant admin,
**I want to** add my social media profile links and configure how my page appears when shared,
**so that** visitors can find my social profiles and shared links look professional.

**Acceptance Criteria:**

- [ ] Admin can add social media URLs (Instagram, Facebook, Airbnb, Booking.com, LinkedIn, YouTube, TikTok, X/Twitter)
- [ ] Only configured (non-empty) platforms show as icons in the footer
- [ ] URLs are validated (must start with `https://`)
- [ ] Admin can upload a dedicated OG image (1200×630px recommended) for social sharing previews
- [ ] Admin can preview how the shared link will appear (OG preview card)
- [ ] Admin can enable/disable share buttons for visitors
- [ ] When enabled, share buttons allow visitors to share the page on Facebook, X/Twitter, WhatsApp, LinkedIn, and email

---

### US-8: Page Renders Correctly for Social Media Crawlers

**As a** tenant whose page is shared on social media,
**I want** Facebook, Instagram, LinkedIn, and WhatsApp to show a rich preview card (title, description, image),
**so that** shared links look professional and attract clicks.

**Acceptance Criteria:**

- [ ] Publish action generates a static `index.html` with OG meta tags pre-baked (not JS-rendered)
- [ ] Social crawlers (Facebook, LinkedIn, WhatsApp) see correct og:title, og:description, og:image
- [ ] OG image URL is publicly accessible via CloudFront
- [ ] OG image dimensions: minimum 200×200px, recommended 1200×630px
- [ ] Instagram DM link previews show the correct image and title
- [ ] Re-publishing updates the `index.html` with new meta tags
- [ ] Facebook Sharing Debugger validates the page without errors

---

## Non-Functional Requirements

### Performance

- Published JSON file size: < 500 KB per tenant
- Page load (JSON fetch + render): < 3 seconds on 3G mobile
- Publish action: < 5 seconds end-to-end
- Contact form response: < 2 seconds

### Security

- No authenticated data exposed on public endpoints
- Tenant isolation: one tenant cannot access another's draft or published content
- Contact form: rate-limited (max 5 per email per hour, max 10 per IP per hour)
- Embed blocks: sandboxed iframe, HTTPS only
- Tenant identity: server-controlled, never from query params

### Availability

- Published pages available even if Flask backend is down (S3/CloudFront serves static JSON)
- CMS editing requires backend availability (DynamoDB CRUD via Flask)

### Scalability

- One S3 file per tenant — scales to any number of tenants without DB load
- DynamoDB on-demand — no capacity planning needed
- CloudFront caching — handles traffic spikes without backend involvement

---

## Out of Scope

- Online booking/payment processing (use embed block for external tools)
- Full CMS or freeform HTML editing
- Multi-page websites (single landing page per tenant)
- User accounts for visitors
- E-commerce or checkout flows
- Real-time data (publish action required for updates)
- Blog with individual post pages / archives / RSS (use embed block for external blog)
- Custom domains (Phase 5 — separate effort)

---

## Success Metrics

| Metric                     | Target                          |
| -------------------------- | ------------------------------- |
| Time to first public page  | < 10 minutes from start         |
| Page load time (mobile 3G) | < 3 seconds                     |
| Publish latency            | < 5 seconds                     |
| Contact form delivery      | 100% delivered to tenant email  |
| Rollback time              | < 5 seconds (one click)         |
| Admin self-service rate    | 100% (no developer involvement) |
