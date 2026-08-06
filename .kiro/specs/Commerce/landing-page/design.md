# Landing Page — Technical Design

## Architecture Overview

Three-layer model separating management, content authoring, and public delivery:

```
┌────────────────────────────────────────────────────────────────┐
│  Layer 1: Management (MySQL / Railway)                          │
│  ParameterService, contact submissions, audit, tenant slugs     │
├────────────────────────────────────────────────────────────────┤
│  Layer 2: CMS Content (DynamoDB)                                │
│  Draft blocks, version history, auto-save                       │
├────────────────────────────────────────────────────────────────┤
│  Layer 3: Public Delivery (S3 + CloudFront)                     │
│  Published JSON per tenant, zero backend calls for visitors     │
└────────────────────────────────────────────────────────────────┘
```

---

## DynamoDB Table Design

**Table name:** `myadmin-landing-pages`

**Single-table design with PK/SK pattern:**

| Access Pattern       | PK              | SK                              | Data                                          |
| -------------------- | --------------- | ------------------------------- | --------------------------------------------- |
| Get current draft    | `TENANT#{slug}` | `LANDING#HOME`                  | sections, status, version, modified_by        |
| Get version snapshot | `TENANT#{slug}` | `VERSION#{n}`                   | sections (frozen), published_at, published_by |
| List versions        | `TENANT#{slug}` | `VERSION#*` (begins_with query) | version list                                  |

**Draft item structure:**

```json
{
  "PK": "TENANT#acme-rentals",
  "SK": "LANDING#HOME",
  "status": "draft",
  "version": 5,
  "last_modified": "2026-08-05T14:30:00Z",
  "modified_by": "admin@acme.nl",
  "sections": [
    {
      "id": "block-001",
      "type": "hero",
      "layout": "image-right",
      "properties": {
        "title": "Welcome to Acme Rentals",
        "subtitle": "Your holiday starts here",
        "cta_text": "Check Availability",
        "cta_url": "/contact",
        "image_key": "acme-rentals/images/hero-banner.jpg"
      }
    },
    {
      "id": "block-002",
      "type": "about",
      "layout": "centered",
      "properties": {
        "content_md": "We offer luxury vacation rentals in the heart of Amsterdam...",
        "image_key": "acme-rentals/images/about-us.jpg"
      }
    },
    {
      "id": "block-003",
      "type": "embed",
      "layout": "full-width",
      "properties": {
        "url": "https://app.guesty.com/widget/acme-rentals",
        "height": "600px",
        "title": "Check Availability"
      }
    }
  ]
}
```

**Version snapshot item** (created on publish):

```json
{
  "PK": "TENANT#acme-rentals",
  "SK": "VERSION#5",
  "published_at": "2026-08-05T15:00:00Z",
  "published_by": "admin@acme.nl",
  "sections": [ ... ]  // frozen copy of sections at publish time
}
```

**IAM policy for Flask backend:**

```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:DeleteItem",
    "dynamodb:Query"
  ],
  "Resource": "arn:aws:dynamodb:eu-west-1:*:table/myadmin-landing-pages"
}
```

---

## S3 Published Content

**Bucket:** `myadmin-public-pages-${environment}` (NEW — separate from the existing private `myadmin-shared-${environment}` bucket)

**Why a separate bucket:** The existing shared bucket (`myadmin-shared-${environment}`) has all public access blocked and is designed for private document storage (invoices, branding, templates). Landing page files must be publicly readable via CloudFront. Mixing public and private content in one bucket creates security risk — a misconfigured policy could expose invoice PDFs. A dedicated public bucket with CloudFront OAC provides clean isolation.

**Bucket configuration:**

- Public access: blocked at bucket level (CloudFront OAC provides read access)
- Encryption: AES-256
- Versioning: disabled (content is regenerated on each publish)
- Lifecycle: none (small files, low cost)
- CORS: not needed (CloudFront serves the content)

**Key structure:**

```
{tenant-slug}/landing.json       # Published page data (React consumes this)
{tenant-slug}/index.html         # Static HTML shell with OG meta tags (social crawlers + entry point)
{tenant-slug}/images/hero-banner.jpg
{tenant-slug}/images/about-us.jpg
{tenant-slug}/images/og-preview.jpg
```

**Note on image uploads:** Tenant admin uploads images via the editor UI. These are written directly to the public bucket under `{tenant-slug}/images/` since they'll be served publicly. This is different from invoice/branding uploads which go to the private shared bucket via `S3SharedStorage`.

**Published JSON structure:**

```json
{
  "tenant_slug": "acme-rentals",
  "published_at": "2026-08-05T15:00:00Z",
  "version": 5,
  "branding": {
    "name": "Acme Rentals",
    "tagline": "Your holiday starts here",
    "logo_url": "https://cdn.../acme-rentals/images/logo.png",
    "color_primary": "#2D5F8A",
    "color_accent": "#F4A261"
  },
  "footer": {
    "company_name": "Acme Rentals B.V.",
    "address": "Keizersgracht 123",
    "postal_city": "1015 AA Amsterdam",
    "country": "Nederland",
    "phone": "+31 20 123 4567",
    "email": "info@acme-rentals.nl",
    "coc": "12345678",
    "vat": "NL123456789B01",
    "social_links": {
      "instagram": "https://instagram.com/acme-rentals",
      "facebook": "https://facebook.com/acme-rentals",
      "airbnb": "https://airbnb.com/rooms/12345"
    }
  },
  "seo": {
    "title": "Acme Rentals — Luxury Vacation Homes",
    "description": "Book your perfect holiday home in Amsterdam",
    "og_image": "https://cdn.../acme-rentals/images/og-preview.jpg",
    "canonical_url": "https://myadmin.app/p/acme-rentals"
  },
  "settings": {
    "show_share_buttons": true
  },
  "sections": [
    { "id": "block-001", "type": "hero", "layout": "image-right", "properties": { ... } },
    { "id": "block-002", "type": "about", "layout": "centered", "properties": { ... } },
    { "id": "block-003", "type": "embed", "layout": "full-width", "properties": { ... } }
  ]
}
```

**CloudFront distribution:**

- Origin: S3 bucket
- Cache TTL: 5 minutes (balance between freshness and performance)
- Custom error page: generic "page not found" for missing slugs

---

## Backend API Contracts

### Public Endpoints (no auth)

#### `POST /api/public/landing/{slug}/contact`

Submit contact form inquiry.

**Request:**

```json
{
  "name": "Jan de Vries",
  "email": "jan@example.nl",
  "message": "I'd like to book your property for July.",
  "honeypot": ""
}
```

**Response (200):**

```json
{ "success": true, "message": "Your message has been sent." }
```

**Response (429):**

```json
{ "success": false, "error": "Too many requests. Please try again later." }
```

**Security:**

- Rate limit: 5 per email per hour, 10 per IP per hour
- Honeypot field: reject if non-empty
- No auth required
- Validates email format

---

### Admin Endpoints (Cognito auth + tenant_required)

#### `GET /api/landing/draft`

Load current draft for editing.

**Response (200):**

```json
{
  "success": true,
  "data": {
    "version": 5,
    "last_modified": "2026-08-05T14:30:00Z",
    "sections": [ ... ]
  }
}
```

#### `PUT /api/landing/draft`

Save draft (auto-save or manual).

**Request:**

```json
{
  "sections": [ ... ]
}
```

**Response (200):**

```json
{ "success": true, "version": 5, "last_modified": "2026-08-05T14:35:00Z" }
```

#### `POST /api/landing/publish`

Publish current draft to S3.

**Response (200):**

```json
{
  "success": true,
  "version": 6,
  "published_at": "2026-08-05T15:00:00Z",
  "public_url": "/p/acme-rentals"
}
```

**Backend actions:**

1. Read draft from DynamoDB
2. Read branding from ParameterService (MySQL)
3. Resolve footer fields (landing_page → module branding fallback)
4. Enrich live data blocks (STR properties, ZZP services) if present
5. Build published JSON
6. Write `landing.json` to S3
7. Generate `index.html` with Open Graph meta tags baked in (for social crawlers)
8. Write `index.html` to S3
9. Store version snapshot in DynamoDB
10. Update `publish_status` and `published_version` in ParameterService
11. Record audit event in MySQL

#### `POST /api/landing/unpublish`

Take landing page offline (delete S3 files).

**Response (200):**

```json
{ "success": true, "message": "Landing page is now offline." }
```

**Backend actions:**

1. Delete `{slug}/landing.json` from S3
2. Delete `{slug}/index.html` from S3
3. Update `publish_status` to "offline" in ParameterService
4. Record audit event in MySQL

#### `GET /api/landing/versions`

List version history.

**Response (200):**

```json
{
  "success": true,
  "data": [
    {
      "version": 6,
      "published_at": "2026-08-05T15:00:00Z",
      "published_by": "admin@acme.nl"
    },
    {
      "version": 5,
      "published_at": "2026-08-01T10:00:00Z",
      "published_by": "admin@acme.nl"
    }
  ]
}
```

#### `POST /api/landing/rollback`

Rollback to a previous version.

**Request:**

```json
{ "version": 5 }
```

**Response (200):**

```json
{ "success": true, "version": 5, "published_at": "2026-08-05T15:05:00Z" }
```

**Backend actions:**

1. Read version snapshot from DynamoDB
2. Overwrite current draft with snapshot sections
3. Run full publish flow (same as `POST /api/landing/publish`)

---

## MySQL Schema Additions

### `landing_page_submissions` table

```sql
CREATE TABLE landing_page_submissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    visitor_name VARCHAR(200) NOT NULL,
    visitor_email VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE,
    INDEX idx_administration (administration),
    INDEX idx_created_at (created_at)
);
```

### `tenant_slugs` table

```sql
CREATE TABLE tenant_slugs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_slug (slug)
);
```

---

## Frontend Structure

```
frontend/src/
├── pages/
│   └── public/
│       ├── PublicLandingPage.tsx       # Route: /p/:tenantSlug
│       ├── PublicThemeProvider.tsx     # Applies brand colors from JSON
│       ├── PublicLayout.tsx           # SEO wrapper + footer + social meta
│       ├── SocialMetaTags.tsx         # OG + Twitter Card meta tag renderer
│       ├── ShareButtons.tsx           # Optional floating share bar
│       └── blocks/
│           ├── HeroBlock.tsx
│           ├── AboutBlock.tsx
│           ├── PropertiesBlock.tsx
│           ├── ServicesBlock.tsx
│           ├── GalleryBlock.tsx
│           ├── ContactBlock.tsx
│           ├── TestimonialsBlock.tsx
│           ├── PricingBlock.tsx
│           ├── FaqBlock.tsx
│           ├── CtaBlock.tsx
│           └── EmbedBlock.tsx
├── components/
│   └── TenantAdmin/
│       └── LandingPage/
│           ├── LandingPageEditor.tsx   # Block editor (drag-and-drop)
│           ├── BlockConfigurator.tsx   # Per-block settings panel
│           ├── BrandingSettings.tsx    # Logo, colors, tagline, social links
│           ├── SeoSettings.tsx        # Title, description, OG image preview
│           ├── PreviewPanel.tsx       # Live preview of draft
│           ├── PublishControls.tsx    # Publish/unpublish/version history
│           └── ImageUploader.tsx      # Upload to S3
```

**Public route** (`/p/:tenantSlug`):

1. CloudFront serves `{slug}/index.html` (contains OG tags for crawlers)
2. HTML shell bootstraps React SPA
3. Fetch `{slug}/landing.json` from S3/CloudFront URL
4. If 404 → show "page not found"
5. Apply brand theme via ChakraProvider color overrides
6. Render blocks in order from `sections` array
7. Render footer from `footer` object (including social profile icons)
8. Render share buttons if `settings.show_share_buttons` is true
9. Set SEO meta tags from `seo` object (react-helmet-async, for SPA navigation)

---

## Branding Resolution (Publish Time)

```python
def resolve_branding(tenant, param_service):
    """Resolve branding fields with fallback chain."""
    fields = ['company_name', 'logo_url', 'address', 'postal_city',
              'country', 'phone', 'email', 'coc', 'vat']

    result = {}
    for field in fields:
        # Priority 1: landing_page namespace
        value = param_service.get_param('landing_page', field, tenant)
        if not value:
            # Priority 2: module branding (based on primary module)
            primary = get_primary_module(tenant)  # 'zzp' or 'str'
            value = param_service.get_param(f'{primary}_branding', field, tenant)
        result[field] = value or ''

    return result
```

---

## HTML Shell Generation (Publish Time)

The publish action generates a static `index.html` per tenant. This ensures social crawlers (Facebook, LinkedIn, WhatsApp, Instagram DMs) can read OG meta tags without executing JavaScript.

```python
def generate_index_html(published_data: dict, slug: str, base_url: str) -> str:
    """Generate static HTML shell with OG tags for social crawlers."""
    seo = published_data.get('seo', {})
    branding = published_data.get('branding', {})

    title = seo.get('title', branding.get('name', ''))
    description = seo.get('description', '')
    og_image = seo.get('og_image', '')
    canonical = f"{base_url}/p/{slug}"

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_escape(title)}</title>
  <meta name="description" content="{html_escape(description)}" />

  <!-- Open Graph -->
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{html_escape(title)}" />
  <meta property="og:description" content="{html_escape(description)}" />
  <meta property="og:image" content="{html_escape(og_image)}" />
  <meta property="og:url" content="{canonical}" />
  <meta property="og:site_name" content="{html_escape(branding.get('name', ''))}" />
  <meta property="og:locale" content="nl_NL" />

  <!-- Twitter/X Card -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{html_escape(title)}" />
  <meta name="twitter:description" content="{html_escape(description)}" />
  <meta name="twitter:image" content="{html_escape(og_image)}" />

  <link rel="canonical" href="{canonical}" />
</head>
<body>
  <div id="root"></div>
  <script>
    // Bootstrap React SPA — load landing.json and render
    window.__LANDING_SLUG__ = "{slug}";
  </script>
  <script src="/assets/public-landing.js" defer></script>
  <noscript>
    <p>{html_escape(title)} — {html_escape(description)}</p>
  </noscript>
</body>
</html>"""
```

**Key decisions:**

- `index.html` is a thin shell — all rendering is still React
- `window.__LANDING_SLUG__` tells the SPA which tenant to load
- The SPA script (`public-landing.js`) is a separate bundle for the public page (no admin code)
- Crawlers get the OG tags from the static HTML; real users get the full React experience
- The `<noscript>` fallback shows basic text for accessibility

---

## Infrastructure (Terraform)

New resources needed (in addition to existing `s3.tf` shared bucket):

```hcl
# DynamoDB table for CMS content
resource "aws_dynamodb_table" "landing_pages" {
  name         = "myadmin-landing-pages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }
}

# S3 bucket for PUBLIC landing page delivery (separate from private shared bucket)
resource "aws_s3_bucket" "public_pages" {
  bucket = "myadmin-public-pages-${var.environment}"

  tags = {
    Name    = "myAdmin-Public-Pages"
    Purpose = "landing-page-delivery"
  }
}

# Block direct public access (CloudFront OAC handles read access)
resource "aws_s3_bucket_public_access_block" "public_pages" {
  bucket = aws_s3_bucket.public_pages.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudFront Origin Access Control (OAC) for secure S3 reads
resource "aws_cloudfront_origin_access_control" "public_pages" {
  name                              = "myadmin-public-pages-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront distribution for public page delivery
resource "aws_cloudfront_distribution" "public_pages" {
  origin {
    domain_name              = aws_s3_bucket.public_pages.bucket_regional_domain_name
    origin_id                = "S3-public-pages"
    origin_access_control_id = aws_cloudfront_origin_access_control.public_pages.id
  }

  enabled             = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-public-pages"

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 300   # 5 minutes
    max_ttl                = 3600  # 1 hour
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# S3 bucket policy: allow CloudFront OAC to read objects
resource "aws_s3_bucket_policy" "public_pages" {
  bucket = aws_s3_bucket.public_pages.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontOAC"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.public_pages.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.public_pages.arn
        }
      }
    }]
  })
}

# IAM policy update: backend needs write access to public bucket
# (append to existing s3_shared_access or create separate policy)
resource "aws_iam_policy" "s3_public_pages_write" {
  name = "myadmin-s3-public-pages-write-${var.environment}"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:DeleteObject"]
      Resource = "${aws_s3_bucket.public_pages.arn}/*"
    }]
  })
}
```

**Key differences from shared bucket:**
| Aspect | Shared bucket (`myadmin-shared-*`) | Public pages bucket (`myadmin-public-pages-*`) |
|--------|------------------------------------|-------------------------------------------------|
| Purpose | Private document storage | Public landing page delivery |
| Access | Backend IAM only | CloudFront OAC (public read) |
| Content | Invoices, branding, templates | `landing.json`, `index.html`, images |
| Lifecycle | 90-day transition to IA | None (small, frequently accessed) |
| Versioning | Enabled | Disabled (regenerated on publish) |
| Backend writes | `S3SharedStorage` class | `LandingPageService` (new) |

---

## Social Media Integration

Three aspects of social media support:

### 1. Social Profile Links (Footer)

Icons in the footer linking to the tenant's own social media pages. Stored as JSON in the `landing_page` ParameterService namespace:

```
Key: social_links
Value: { "instagram": "https://instagram.com/acme-rentals", "facebook": "https://facebook.com/acme-rentals", "airbnb": "https://airbnb.com/...", "booking_com": "https://booking.com/..." }
```

**Supported platforms:** instagram, facebook, airbnb, booking_com, linkedin, youtube, tiktok, twitter_x

**Frontend rendering** (in `PublicLayout.tsx` footer):

- Only render icons for platforms where URL is configured (non-empty)
- Use `react-icons/fa6` for brand icons (FaInstagram, FaFacebook, etc.)
- Open in new tab with `rel="noopener noreferrer"`
- Accessible: `aria-label` per icon

**Editor UI** (in `BrandingSettings.tsx`):

- Input field per platform with URL validation (must start with `https://`)
- Visual icon preview next to each input

### 2. Open Graph & Twitter Card Meta Tags (SEO/Sharing)

When someone shares the landing page URL on Facebook, Instagram, LinkedIn, or messaging apps, the platform fetches the page and reads Open Graph meta tags to render a preview card.

**Required meta tags** (rendered by `PublicLayout.tsx` via `react-helmet-async`):

```html
<!-- Open Graph (Facebook, LinkedIn, Instagram, WhatsApp) -->
<meta property="og:type" content="website" />
<meta property="og:title" content="{seo.title}" />
<meta property="og:description" content="{seo.description}" />
<meta property="og:image" content="{seo.og_image}" />
<meta property="og:url" content="https://myadmin.app/p/{tenant-slug}" />
<meta property="og:site_name" content="{branding.name}" />
<meta property="og:locale" content="nl_NL" />

<!-- Twitter/X Card -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{seo.title}" />
<meta name="twitter:description" content="{seo.description}" />
<meta name="twitter:image" content="{seo.og_image}" />
```

**Important considerations:**

- **`og:image` requirements**: Facebook recommends 1200×630px, minimum 200×200px. Image must be publicly accessible (S3/CloudFront URL).
- **Client-side rendering limitation**: Facebook/Instagram crawlers have limited JavaScript support. Open Graph tags MUST be present in the initial HTML response. For a client-side rendered React app, this requires either:
  - **Option A (recommended for v1):** Include a small server-rendered HTML shell per tenant with meta tags baked in. The publish action generates both `landing.json` AND an `index.html` with OG tags pre-filled.
  - **Option B (future):** CloudFront Function or Lambda@Edge that injects OG tags for crawler user-agents.

**Published `index.html` structure** (generated at publish time alongside `landing.json`):

```html
<!DOCTYPE html>
<html lang="nl">
  <head>
    <meta charset="utf-8" />
    <title>{seo.title}</title>
    <meta name="description" content="{seo.description}" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="{seo.title}" />
    <meta property="og:description" content="{seo.description}" />
    <meta property="og:image" content="{seo.og_image}" />
    <meta property="og:url" content="https://myadmin.app/p/{slug}" />
    <meta property="og:site_name" content="{branding.name}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{seo.title}" />
    <meta name="twitter:description" content="{seo.description}" />
    <meta name="twitter:image" content="{seo.og_image}" />
    <script>
      // Redirect to React SPA for full rendering
      // OR embed landing.json inline for zero-fetch rendering
    </script>
  </head>
  <body>
    <noscript>...</noscript>
  </body>
</html>
```

**S3 key structure update:**

```
{tenant-slug}/landing.json      # Data for React renderer
{tenant-slug}/index.html        # HTML shell with OG tags (for crawlers + direct URL visits)
{tenant-slug}/images/...        # Uploaded images
```

**CloudFront routing:**

- `GET /p/{slug}` → serves `{slug}/index.html` from S3
- React app boots from the HTML shell and reads `landing.json` for full rendering

### 3. Share Buttons (Optional — Visitor-Facing)

Allow visitors to share the landing page on social platforms. This is a simple UI feature using share URLs (no API keys needed):

```tsx
// Share URLs — no backend, no API keys
const shareUrls = {
  facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(pageUrl)}`,
  twitter: `https://twitter.com/intent/tweet?url=${encodeURIComponent(pageUrl)}&text=${encodeURIComponent(title)}`,
  whatsapp: `https://wa.me/?text=${encodeURIComponent(title + " " + pageUrl)}`,
  linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(pageUrl)}`,
  email: `mailto:?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(pageUrl)}`,
};
```

**Implementation:**

- Optional floating share bar or share icon in hero/CTA blocks
- Tenant can enable/disable via branding settings (`show_share_buttons: true/false`)
- Uses native share URLs — no third-party scripts or cookies

### 4. Instagram-Specific Considerations

Instagram does NOT support link sharing in the same way as Facebook:

- Instagram posts cannot contain clickable links (only in bio)
- Instagram Stories can have link stickers (but the user shares manually)
- The OG tags still matter for when URLs are shared in Instagram DMs — Instagram renders a preview card

**Recommendation for tenants:**

- Set a good `og:image` — this is what appears in Instagram DM previews
- Use the "link in bio" pattern: the landing page URL goes in the Instagram profile bio
- The `social_links.instagram` in the footer helps visitors find the tenant's Instagram

### Updated ParameterService Keys

Add to `landing_page` namespace:

```
social_links          → JSON { instagram, facebook, ... }  (existing)
show_share_buttons    → "true" / "false" (default: false)
og_image_url          → Public URL for social preview image (1200×630 recommended)
```

### Updated Published JSON Structure

```json
{
  "seo": {
    "title": "Acme Rentals — Luxury Vacation Homes",
    "description": "Book your perfect holiday home in Amsterdam",
    "og_image": "https://cdn.../acme-rentals/images/og-preview.jpg",
    "canonical_url": "https://myadmin.app/p/acme-rentals"
  },
  "footer": {
    "social_links": {
      "instagram": "https://instagram.com/acme-rentals",
      "facebook": "https://facebook.com/acme-rentals",
      "airbnb": "https://airbnb.com/rooms/12345"
    }
  },
  "settings": {
    "show_share_buttons": true
  }
}
```

---

## Security Considerations

- **Public delivery**: S3 + CloudFront, no backend involved, no data leakage path
- **Tenant isolation**: DynamoDB PK includes tenant slug, S3 keys prefixed by slug
- **Contact form**: rate-limited, honeypot, email validation, stored in tenant-scoped MySQL
- **Embed block**: HTTPS-only URLs, sandboxed iframe (`sandbox="allow-scripts allow-same-origin"`)
- **Admin APIs**: `@cognito_required` + `@tenant_required` — standard myAdmin auth pattern
- **Image uploads**: tenant-scoped S3 prefix, file type validation, size limit (5MB)
- **Share buttons**: use platform share URLs only — no third-party tracking scripts or cookies
- **OG image**: must be served from CloudFront (public), not from authenticated S3 paths

---

## New Frontend Dependencies

| Package              | Purpose                                       |
| -------------------- | --------------------------------------------- |
| `react-icons`        | Brand icons for social links (Fa6 icon set)   |
| `react-helmet-async` | SEO meta tags in SPA (client-side navigation) |

Both are well-maintained, widely used, and add minimal bundle size.
