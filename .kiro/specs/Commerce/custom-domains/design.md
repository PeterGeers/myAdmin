# Custom Domains — Technical Design

## Architecture Overview

```
Visitor: www.acme-rentals.nl
         ──── CNAME ────→ CloudFront (same distribution)
                          │
                          │ CloudFront Function (viewer-request)
                          │ Host header → resolve slug → rewrite URI
                          │
                          └──→ S3: /acme-rentals/index.html

Visitor: acme-rentals.jabaki.nl
         ──── *.jabaki.nl CNAME ────→ CloudFront (same distribution)
                                      │
                                      │ CloudFront Function (viewer-request)
                                      │ Host header → extract subdomain as slug → rewrite URI
                                      │
                                      └──→ S3: /acme-rentals/index.html
```

**Key principle:** The URL never changes. CloudFront serves the content directly under the requested hostname. No HTTP redirects. The visitor's address bar shows exactly what they typed.

---

## Phase 0: Domain Migration — jabaki.nl to Route 53

### Current State

- **Registration:** Squarespace (originally Google Domains, acquired by Squarespace)
- **Nameservers:** `ns-cloud-a*.googledomains.com` (Google Domains DNS)
- **A/AAAA records:** Already point to CloudFront
- **MX:** ImprovMX (email forwarding to personal inbox)
- **TXT:** SPF, Stripe verification, Google site verification
- **SES:** DKIM + domain verification records exist (may be subdomains not shown in dump)

### Migration Plan: Full Transfer to Route 53

#### Step 1: Create Route 53 Hosted Zone (before transfer)

```hcl
resource "aws_route53_zone" "jabaki" {
  name = "jabaki.nl"
}
```

#### Step 2: Recreate All Existing Records in Route 53

| Type  | Name                     | Value                                     | Notes                                  |
| ----- | ------------------------ | ----------------------------------------- | -------------------------------------- |
| A     | jabaki.nl                | Alias → CloudFront distribution           | Replace hardcoded IPs with alias       |
| AAAA  | jabaki.nl                | Alias → CloudFront distribution           | Same — use alias                       |
| MX    | jabaki.nl                | 10 mx1.improvmx.com / 20 mx2.improvmx.com | Keep for email receiving               |
| TXT   | jabaki.nl                | SPF record                                | `v=spf1 ip4:62.221.252.160 a ... ~all` |
| TXT   | jabaki.nl                | Stripe verification                       | `stripe-verification=5820...`          |
| TXT   | jabaki.nl                | Google site verification                  | `google-site-verification=Xux...`      |
| TXT   | \_amazonses.jabaki.nl    | SES domain verification token             | From `ses.tf` output                   |
| CNAME | \*.\_domainkey.jabaki.nl | SES DKIM tokens (3 records)               | From `ses.tf` output                   |
| CNAME | \*.jabaki.nl             | CloudFront distribution                   | **New** — for landing pages            |

#### Step 3: Switch Nameservers (zero-downtime)

1. Note the 4 Route 53 NS records from the new hosted zone
2. In Squarespace domain settings, change nameservers to Route 53's NS values
3. Wait for propagation (usually 1–48h, typically <2h for .nl)
4. Verify: `dig jabaki.nl NS` shows Route 53 nameservers

#### Step 4: Transfer Domain Registration to Route 53

1. **Unlock domain** at Squarespace: Domain Settings → Domain Lock → disable
2. **Get auth/transfer code** at Squarespace: Domain Settings → Transfer domain → get EPP code
3. **Initiate transfer at AWS:** Route 53 console → Registered Domains → Transfer → enter `jabaki.nl` + auth code
4. **Approve transfer:** Confirm email from current registrar (Squarespace)
5. **Wait:** SIDN (.nl registry) processes transfer (typically 5 days)
6. **Done:** Route 53 is now both registrar and DNS host

#### Step 5: Cleanup

- Remove domain from Squarespace account
- Verify all services still work: email forwarding, SES sending, CloudFront, Stripe webhooks
- Update `ses.tf` instructions to reference Route 53 instead of Squarespace

### Risk Mitigation

| Risk                          | Mitigation                                                                              |
| ----------------------------- | --------------------------------------------------------------------------------------- |
| DNS downtime during NS switch | Set low TTL on records before switch; verify all records exist in Route 53 first        |
| Email stops working           | Test MX resolution immediately after NS switch; ImprovMX has no dependency on registrar |
| SES stops sending             | DKIM/SPF records replicated in Route 53 before switch — no interruption                 |
| Transfer rejected             | Ensure domain is unlocked, not expired, and no registrar hold                           |
| Landing pages break           | A records currently use hardcoded IPs; Route 53 alias is more reliable (improvement)    |

### Cost

| Item                           | Cost                                            |
| ------------------------------ | ----------------------------------------------- |
| Route 53 hosted zone           | $0.50/month                                     |
| Route 53 DNS queries           | ~$0.01–0.10/month (minimal traffic)             |
| .nl domain registration at AWS | ~$12/year                                       |
| **Savings**                    | Cancel Squarespace domain renewal (~€5–10/year) |

### Timeline

| Step                         | Duration                 | Blocking?                    |
| ---------------------------- | ------------------------ | ---------------------------- |
| Create hosted zone + records | 30 min                   | No                           |
| Switch nameservers           | Instant + 2h propagation | Yes (brief)                  |
| Transfer registration        | 5–7 days                 | No (DNS already on Route 53) |

---

## Option Analysis: Single vs. Multiple CloudFront Distributions

### Option A: Single Distribution (Recommended)

Add custom domains as **alternate domain names (CNAMEs)** on the existing `aws_cloudfront_distribution.public_pages`.

**Pros:**

- Single point of management
- Single CloudFront Function handles all routing
- Single S3 origin — no data duplication
- Lower cost (one distribution)
- Simpler infrastructure

**Cons:**

- ACM certificate must cover ALL domains (wildcard `*.jabaki.nl` + each custom domain)
- CloudFront limits: max 100 CNAMEs per distribution (can request increase)
- Adding/removing a custom domain requires distribution update (~5 min propagation)

### Option B: Separate Distribution Per Custom Domain

Create a new CloudFront distribution for each custom domain.

**Pros:**

- Full isolation per tenant
- Independent SSL certificates

**Cons:**

- Complex management (N distributions to maintain)
- Higher cost
- Slower provisioning (new distribution per tenant)
- Overkill for landing pages (they're static content)

**Decision: Option A (single distribution).** Landing pages are static files. A single distribution with multiple CNAMEs is the standard AWS pattern. The 100-CNAME limit is fine for the foreseeable scale.

---

## SSL/TLS Certificate Strategy

### Jabaki Subdomain (`*.jabaki.nl`)

- **ACM wildcard certificate**: `*.jabaki.nl` (covers all subdomains)
- Region: `us-east-1` (required for CloudFront)
- Validation: DNS (add CNAME to `jabaki.nl` zone)
- Auto-renewable by AWS

### Custom Domains (tenant-owned)

Each custom domain requires its own ACM certificate OR a single SAN certificate that gets updated.

**Approach: Individual ACM certificates per custom domain**

- When tenant registers `www.acme-rentals.nl`:
  1. Backend creates ACM certificate request for `www.acme-rentals.nl`
  2. ACM provides DNS validation CNAME record
  3. Tenant adds the CNAME to their DNS
  4. ACM validates and issues certificate (~minutes to hours)
  5. Backend adds the domain + certificate to the CloudFront distribution
  6. Backend updates distribution CNAME aliases

**Note:** CloudFront supports multiple certificates via **Server Name Indication (SNI)** — each domain gets its own cert, no extra cost.

---

## CloudFront Function Update

The existing `public_pages_url_rewrite` function needs to handle host-based routing:

```javascript
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var host = request.headers.host ? request.headers.host.value : "";

  // --- Host-based routing (custom domains & jabaki subdomains) ---

  // Case 1: Jabaki subdomain (slug.jabaki.nl)
  if (host.endsWith(".jabaki.nl")) {
    var slug = host.replace(".jabaki.nl", "");
    if (slug && slug.length > 0 && slug !== "www") {
      // Serve landing page content; resolve file path
      if (uri === "/" || uri === "") {
        request.uri = "/" + slug + "/index.html";
      } else if (!uri.includes(".")) {
        // Non-file path → serve index.html (SPA)
        request.uri = "/" + slug + "/index.html";
      } else {
        // File request (images, json, etc.) → prefix with slug
        request.uri = "/" + slug + uri;
      }
      return request;
    }
  }

  // Case 2: Custom domain (www.acme-rentals.nl)
  // Custom domain → slug mapping is stored in a CloudFront KeyValueStore
  // The function reads the mapping to determine the slug
  if (
    host &&
    !host.endsWith(".cloudfront.net") &&
    !host.endsWith(".jabaki.nl")
  ) {
    // Look up slug from KeyValueStore
    var slug = getSlugFromKVS(host);
    if (slug) {
      if (uri === "/" || uri === "") {
        request.uri = "/" + slug + "/index.html";
      } else if (!uri.includes(".")) {
        request.uri = "/" + slug + "/index.html";
      } else {
        request.uri = "/" + slug + uri;
      }
      return request;
    }
  }

  // --- Existing path-based routing (fallback: /p/{slug}) ---
  if (uri.startsWith("/p/")) {
    var slug = uri.replace(/^\/p\//, "").replace(/\/$/, "");
    if (slug && slug.length > 0) {
      request.uri = "/" + slug + "/index.html";
    }
    return request;
  }

  if (uri.match(/^\/[a-z0-9-]+\/?$/) && !uri.includes(".")) {
    var path = uri.replace(/\/$/, "");
    request.uri = path + "/index.html";
    return request;
  }

  return request;
}
```

### CloudFront KeyValueStore (Custom Domain → Slug Mapping)

CloudFront KeyValueStore is a key-value data store that CloudFront Functions can read at the edge. It avoids needing Lambda@Edge for the custom domain lookup.

```
Key: "www.acme-rentals.nl"     → Value: "acme-rentals"
Key: "www.villa-sunflower.com" → Value: "villa-sunflower"
```

- **Max 10MB** store (plenty for thousands of domain mappings)
- **Read latency**: <1ms (runs at the edge, no network call)
- **Update**: via AWS SDK (`cloudfront-keyvaluestore` API) — backend updates when domain is verified
- **Eventual consistency**: updates propagate globally in ~seconds

---

## Database Schema

### `tenant_custom_domains` table (MySQL)

```sql
CREATE TABLE tenant_custom_domains (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    domain_type ENUM('custom', 'jabaki') NOT NULL,
    domain VARCHAR(255) NOT NULL UNIQUE,
    -- SSL/Verification
    acm_certificate_arn VARCHAR(512) NULL,
    dns_validation_name VARCHAR(255) NULL,
    dns_validation_value VARCHAR(255) NULL,
    verification_status ENUM('pending_dns', 'validating', 'issued', 'failed', 'revoked') DEFAULT 'pending_dns',
    -- Activation
    is_active BOOLEAN DEFAULT FALSE,
    activated_at TIMESTAMP NULL,
    -- Meta
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- Indexes
    INDEX idx_administration (administration),
    INDEX idx_domain (domain),
    INDEX idx_slug (slug),
    INDEX idx_verification_status (verification_status)
);
```

### Changes to `tenant_slugs` table

Add a column to track Jabaki subdomain opt-in:

```sql
ALTER TABLE tenant_slugs
ADD COLUMN jabaki_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN jabaki_enabled_at TIMESTAMP NULL;
```

---

## Backend API Contracts

### Admin Endpoints (Cognito auth + tenant_required)

#### `GET /api/landing/domains`

List domains configured for the tenant.

**Response (200):**

```json
{
  "success": true,
  "data": {
    "jabaki": {
      "enabled": true,
      "domain": "acme-rentals.jabaki.nl",
      "status": "active"
    },
    "custom": {
      "domain": "www.acme-rentals.nl",
      "status": "issued",
      "is_active": true,
      "dns_instructions": null
    }
  }
}
```

#### `POST /api/landing/domains/jabaki/enable`

Enable the Jabaki subdomain for this tenant.

**Response (200):**

```json
{
  "success": true,
  "domain": "acme-rentals.jabaki.nl",
  "message": "Jabaki subdomain is now active."
}
```

**Backend actions:**

1. Set `jabaki_enabled = true` in `tenant_slugs`
2. Add `acme-rentals.jabaki.nl` to CloudFront distribution as alternate domain (covered by wildcard cert)
3. Actually not needed per-subdomain — wildcard DNS + wildcard cert means ALL `*.jabaki.nl` subdomains route to the distribution already. Just the CloudFront Function resolves it.

**Simplification:** Since `*.jabaki.nl` wildcard DNS points to CloudFront and the wildcard cert covers everything, enabling a Jabaki subdomain is just a flag in the DB. The CloudFront Function extracts the subdomain as the slug and serves the content. No infrastructure change needed per tenant.

#### `POST /api/landing/domains/jabaki/disable`

Disable the Jabaki subdomain.

**Response (200):**

```json
{
  "success": true,
  "message": "Jabaki subdomain is now disabled."
}
```

**Backend action:** Set `jabaki_enabled = false`. The CloudFront Function should check if Jabaki is enabled for the slug (via KeyValueStore or by checking if the slug's content exists in S3). Simplest approach: if the slug folder exists in S3 (i.e., the page is published), it's servable via Jabaki. The `jabaki_enabled` flag controls whether the tenant sees it in their admin panel and whether OG tags reference this URL.

#### `POST /api/landing/domains/custom`

Register a custom domain.

**Request:**

```json
{
  "domain": "www.acme-rentals.nl"
}
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "domain": "www.acme-rentals.nl",
    "status": "pending_dns",
    "dns_instructions": {
      "type": "CNAME",
      "records": [
        {
          "purpose": "domain_verification",
          "name": "_acme-challenge.www.acme-rentals.nl",
          "value": "_abc123.acm-validations.aws."
        },
        {
          "purpose": "routing",
          "name": "www.acme-rentals.nl",
          "value": "d1234abcd.cloudfront.net"
        }
      ]
    }
  }
}
```

**Backend actions:**

1. Validate domain format (no IP addresses, no jabaki.nl subdomains)
2. Check domain is not already registered by another tenant
3. Request ACM certificate in `us-east-1` for the domain
4. Store in `tenant_custom_domains` with `status = pending_dns`
5. Return DNS instructions for the tenant

#### `POST /api/landing/domains/custom/verify`

Check if DNS validation has completed.

**Response (200) — success:**

```json
{
  "success": true,
  "data": {
    "domain": "www.acme-rentals.nl",
    "status": "issued",
    "is_active": true,
    "message": "Domain is verified and active."
  }
}
```

**Response (200) — still pending:**

```json
{
  "success": true,
  "data": {
    "domain": "www.acme-rentals.nl",
    "status": "validating",
    "is_active": false,
    "message": "DNS records detected. Certificate validation in progress (may take up to 30 minutes)."
  }
}
```

**Backend actions:**

1. Check ACM certificate status via AWS SDK
2. If `ISSUED`:
   - Add domain as alternate CNAME to CloudFront distribution
   - Associate the ACM certificate with the distribution
   - Update KeyValueStore with domain → slug mapping
   - Set `is_active = true`, `verification_status = 'issued'`
3. If still `PENDING_VALIDATION`: return current status

#### `DELETE /api/landing/domains/custom`

Remove custom domain.

**Response (200):**

```json
{
  "success": true,
  "message": "Custom domain removed."
}
```

**Backend actions:**

1. Remove domain from CloudFront distribution CNAMEs
2. Delete ACM certificate
3. Remove from KeyValueStore
4. Delete from `tenant_custom_domains`

---

## Infrastructure Changes (Terraform)

### 1. ACM Wildcard Certificate for `*.jabaki.nl`

```hcl
# Must be in us-east-1 for CloudFront
resource "aws_acm_certificate" "jabaki_wildcard" {
  provider          = aws.us_east_1
  domain_name       = "*.jabaki.nl"
  validation_method = "DNS"

  tags = {
    Name        = "jabaki-wildcard-cert"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }

  lifecycle {
    create_before_destroy = true
  }
}
```

### 2. DNS Zone for jabaki.nl (Route 53)

```hcl
resource "aws_route53_zone" "jabaki" {
  name = "jabaki.nl"

  tags = {
    Name        = "jabaki.nl-zone"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# Wildcard A record pointing to CloudFront
resource "aws_route53_record" "jabaki_wildcard" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "*.jabaki.nl"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.public_pages.domain_name
    zone_id                = aws_cloudfront_distribution.public_pages.hosted_zone_id
    evaluate_target_health = false
  }
}

# ACM DNS validation record
resource "aws_route53_record" "jabaki_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.jabaki_wildcard.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id = aws_route53_zone.jabaki.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

resource "aws_acm_certificate_validation" "jabaki_wildcard" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.jabaki_wildcard.arn
  validation_record_fqdns = [for record in aws_route53_record.jabaki_cert_validation : record.fqdn]
}
```

### 3. CloudFront Distribution Update

Update the existing distribution to include:

- `*.jabaki.nl` as alternate domain name
- The wildcard ACM certificate

```hcl
# Update the existing distribution's viewer_certificate block:
viewer_certificate {
  acm_certificate_arn      = aws_acm_certificate.jabaki_wildcard.arn
  ssl_support_method       = "sni-only"
  minimum_protocol_version = "TLSv1.2_2021"
}

# Add aliases:
aliases = ["*.jabaki.nl"]
```

**Note:** Custom tenant domains are added dynamically by the backend via AWS SDK (not Terraform-managed), because they change at runtime.

### 4. CloudFront KeyValueStore

```hcl
resource "aws_cloudfront_key_value_store" "domain_mapping" {
  name    = "myadmin-domain-slug-mapping"
  comment = "Maps custom domains to tenant slugs for landing page routing"
}
```

### 5. IAM Policy Updates

Backend needs permissions for:

- ACM certificate management (create, describe, delete)
- CloudFront distribution updates (add/remove CNAMEs)
- CloudFront KeyValueStore updates
- Route 53 (only for Jabaki zone, not for custom domains — tenants manage their own DNS)

```hcl
resource "aws_iam_policy" "custom_domains_management" {
  name        = "myadmin-custom-domains-${var.environment}"
  description = "Permissions for managing custom domain certificates and routing"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ACMCertificateManagement"
        Effect = "Allow"
        Action = [
          "acm:RequestCertificate",
          "acm:DescribeCertificate",
          "acm:DeleteCertificate",
          "acm:ListCertificates"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = "us-east-1"
          }
        }
      },
      {
        Sid    = "CloudFrontDistributionUpdate"
        Effect = "Allow"
        Action = [
          "cloudfront:GetDistribution",
          "cloudfront:GetDistributionConfig",
          "cloudfront:UpdateDistribution"
        ]
        Resource = aws_cloudfront_distribution.public_pages.arn
      },
      {
        Sid    = "CloudFrontKeyValueStore"
        Effect = "Allow"
        Action = [
          "cloudfront-keyvaluestore:GetKey",
          "cloudfront-keyvaluestore:PutKey",
          "cloudfront-keyvaluestore:DeleteKey",
          "cloudfront-keyvaluestore:ListKeys"
        ]
        Resource = aws_cloudfront_key_value_store.domain_mapping.arn
      }
    ]
  })

  tags = {
    Name        = "myAdmin-Custom-Domains"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}
```

---

## Publish Flow Update

When publishing a landing page, the `generate_index_html` function needs to determine the **canonical URL** based on domain priority:

```
Priority:
1. Custom domain (if active) → canonical = https://www.acme-rentals.nl/
2. Jabaki subdomain (if enabled) → canonical = https://acme-rentals.jabaki.nl/
3. Default CloudFront path → canonical = https://{cf-domain}/p/acme-rentals
```

The published `index.html` and `landing.json` will use the highest-priority URL as the canonical/og:url.

**Updated SEO section in `landing.json`:**

```json
{
  "seo": {
    "title": "Acme Rentals — Luxury Vacation Homes",
    "description": "Book your perfect holiday home in Amsterdam",
    "og_image": "https://cdn.../acme-rentals/images/og-preview.jpg",
    "canonical_url": "https://www.acme-rentals.nl/",
    "alternate_urls": [
      "https://acme-rentals.jabaki.nl/",
      "https://d1234abcd.cloudfront.net/p/acme-rentals"
    ]
  }
}
```

---

## Security Considerations

- **Domain squatting prevention**: Tenants can only register domains they own (verified via DNS)
- **No cross-tenant access**: KeyValueStore maps are one-to-one (domain → one slug)
- **ACM certificate isolation**: Each custom domain gets its own cert, auto-renewed by AWS
- **Jabaki subdomain isolation**: Slug must exist in S3 (page must be published) for content to serve
- **No URL manipulation**: CloudFront Function rejects unknown hosts with 404
- **Wildcard safety**: Only `*.jabaki.nl` is covered — no risk to other domains

---

## Sequence Diagram: Custom Domain Registration

```
Tenant Admin                Backend               ACM              CloudFront
    │                          │                    │                   │
    │  POST /domains/custom    │                    │                   │
    │  { domain: "www.x.nl" }  │                    │                   │
    │─────────────────────────→│                    │                   │
    │                          │  RequestCertificate│                   │
    │                          │───────────────────→│                   │
    │                          │  ← cert ARN +      │                   │
    │                          │    DNS validation   │                   │
    │                          │    records          │                   │
    │  ← DNS instructions      │                    │                   │
    │←─────────────────────────│                    │                   │
    │                          │                    │                   │
    │  [Tenant adds DNS records to their registrar] │                   │
    │                          │                    │                   │
    │  POST /domains/custom/   │                    │                   │
    │       verify             │                    │                   │
    │─────────────────────────→│                    │                   │
    │                          │  DescribeCertificate                   │
    │                          │───────────────────→│                   │
    │                          │  ← status: ISSUED  │                   │
    │                          │                    │                   │
    │                          │  UpdateDistribution│(add CNAME + cert) │
    │                          │───────────────────────────────────────→│
    │                          │                    │                   │
    │                          │  PutKey (KVS)      │                   │
    │                          │  "www.x.nl" → slug │                   │
    │                          │───────────────────────────────────────→│
    │                          │                    │                   │
    │  ← domain active!        │                    │                   │
    │←─────────────────────────│                    │                   │
```

---

## Frontend: Domain Management UI

Located in the existing LandingPage admin panel as a new "Domains" tab/section.

```
components/TenantAdmin/LandingPage/
├── DomainSettings.tsx        # Main domain management panel
├── JabakiSubdomain.tsx       # Toggle + preview for slug.jabaki.nl
├── CustomDomainForm.tsx      # Register/verify/remove custom domain
└── DnsInstructions.tsx       # Display DNS records tenant needs to add
```

**UI flow:**

1. Show current domain status (Jabaki + custom)
2. One-click enable for Jabaki subdomain
3. Form to enter custom domain → shows DNS instructions → verify button
4. Status badges: pending, validating, active, failed
