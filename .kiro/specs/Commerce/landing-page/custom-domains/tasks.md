# Implementation Plan

## Overview

Implement custom domain support for landing pages. Tenants can use either a `slug.jabaki.nl` subdomain (free, one-click) or their own custom domain (`www.example.nl`). This requires migrating the `jabaki.nl` domain to Route 53, setting up wildcard infrastructure, updating the CloudFront Function for host-based routing, building backend APIs, frontend UI, and updating OG tags.

References: [requirements.md](./requirements.md) | [design.md](./design.md)

## Tasks

### Phase 0: Domain Migration (jabaki.nl → Route 53)

- [x] 0.1 Create Route 53 hosted zone for `jabaki.nl` via Terraform
  - Create `aws_route53_zone.jabaki` resource in `infrastructure/`
  - Output the NS record values for nameserver switch
  - Ref: design.md "Phase 0: Domain Migration" Step 1

- [x] 0.2 Recreate all existing DNS records in Route 53 via Terraform
  - A/AAAA records as CloudFront alias (replace hardcoded IPs)
  - MX records (mx1/mx2.improvmx.com)
  - TXT records (SPF, Stripe verification, Google site verification)
  - SES DKIM/verification CNAME records
  - Wildcard CNAME `*.jabaki.nl` → CloudFront distribution
  - Ref: design.md Step 2 table, jabaki.md for current records

- [x] 0.3 Verify all records resolve correctly after Terraform apply
  - Manual: `dig jabaki.nl MX`, `dig jabaki.nl TXT`, `dig jabaki.nl A`
  - Confirm A record alias resolves to CloudFront
  - **Type: manual verification**

- [x] 0.4 Switch nameservers at Squarespace to Route 53 NS values
  - Manual: update Squarespace domain settings
  - Wait for propagation (typically <2h for .nl)
  - Verify: `dig jabaki.nl NS` shows Route 53 nameservers
  - **Type: manual operation**

- [x] 0.5 Verify services work after NS switch
  - Manual: confirm email forwarding (ImprovMX), SES sending, CloudFront serving jabaki.nl
  - **Type: manual verification**

- [x] 0.6 Initiate domain transfer to Route 53
  - Manual: unlock domain at Squarespace, get EPP/auth code
  - Initiate transfer at Route 53 console
  - Approve transfer confirmation email
  - Wait 5-7 days for SIDN processing
  - **Type: manual operation (runs in background)**

### Phase 1: Infrastructure — Jabaki Wildcard

- [x] 1.1 Create ACM wildcard certificate `*.jabaki.nl` in us-east-1 via Terraform
  - `aws_acm_certificate.jabaki_wildcard` with DNS validation
  - `aws_route53_record.jabaki_cert_validation` for validation CNAME
  - `aws_acm_certificate_validation.jabaki_wildcard` to wait for issuance
  - Ref: design.md "ACM Wildcard Certificate" section
  - Depends on: 0.2 (Route 53 zone exists)

- [x] 1.2 Update CloudFront distribution with `*.jabaki.nl` alias and wildcard cert
  - Add `*.jabaki.nl` to `aliases` on `aws_cloudfront_distribution.public_pages`
  - Update `viewer_certificate` block with wildcard cert ARN
  - Ref: design.md "CloudFront Distribution Update" section
  - Depends on: 1.1

- [x] 1.3 Create CloudFront KeyValueStore for domain→slug mapping via Terraform
  - `aws_cloudfront_key_value_store.domain_mapping`
  - Name: `myadmin-domain-slug-mapping`
  - Ref: design.md "CloudFront KeyValueStore" section

- [x] 1.4 Create wildcard A record `*.jabaki.nl` → CloudFront in Route 53
  - `aws_route53_record.jabaki_wildcard` alias to CloudFront distribution
  - Ref: design.md Route 53 records
  - Depends on: 0.2

- [x] 1.5 Verify: visit `test-slug.jabaki.nl` → CloudFront responds
  - Manual: confirm CloudFront accepts the request (even if 404/403)
  - Validates DNS + certificate + distribution config
  - **Type: manual verification**
  - Depends on: 1.2, 1.4

### Phase 2: CloudFront Function Update

- [x] 2.1 Update CloudFront Function to handle host-based routing for `*.jabaki.nl`
  - Add Jabaki subdomain detection: `host.endsWith('.jabaki.nl')`
  - Extract slug from subdomain, rewrite URI to `/{slug}/index.html`
  - Handle file requests (images, json) with slug prefix
  - Ref: design.md "CloudFront Function Update" code
  - Depends on: 1.2

- [x] 2.2 Add KeyValueStore association and custom domain lookup to CloudFront Function
  - Associate KVS with CloudFront Function
  - Add custom domain lookup: non-jabaki, non-cloudfront hosts → KVS get slug
  - Rewrite URI same as Jabaki pattern
  - Ref: design.md Case 2 in function code
  - Depends on: 1.3, 2.1

- [x] 2.3 Add fallback: unknown hosts return 404 response
  - If host doesn't match any known pattern and KVS lookup returns null → 404
  - Prevents content leak from unknown domains
  - Ref: requirements.md US-3 acceptance criteria
  - Depends on: 2.2

- [x] 2.4 Test: published tenant slug via `slug.jabaki.nl` serves correct content
  - Manual: verify `index.html` and assets load correctly
  - Confirm no redirects occur (URL stays as-is)
  - **Type: manual verification**
  - Depends on: 2.1

- [x] 2.5 Test: existing `/p/{slug}` path routing still works unchanged
  - Manual: verify old URLs continue to function
  - Regression check
  - **Type: manual verification**
  - Depends on: 2.3

### Phase 3: Database & Backend — Jabaki Subdomain

- [x] 3.1 Add `jabaki_enabled` and `jabaki_enabled_at` columns to `tenant_slugs` table
  - Create database migration script
  - `jabaki_enabled BOOLEAN DEFAULT FALSE`
  - `jabaki_enabled_at TIMESTAMP NULL`
  - Ref: design.md "Changes to tenant_slugs table"

- [x] 3.2 Create `tenant_custom_domains` table
  - Create database migration script
  - Columns: id, administration, slug, domain_type, domain, acm_certificate_arn, dns_validation_name, dns_validation_value, verification_status, is_active, activated_at, created_at, updated_at
  - Indexes: administration, domain (UNIQUE), slug, verification_status
  - Ref: design.md "Database Schema" section

- [x] 3.3 Implement `GET /api/landing/domains` endpoint
  - Return Jabaki status + custom domain status for tenant
  - Requires: @cognito_required, @tenant_required
  - Response format per design.md API contract
  - Ref: design.md GET endpoint spec
  - Depends on: 3.1, 3.2

- [x] 3.4 Implement `POST /api/landing/domains/jabaki/enable` endpoint
  - Set `jabaki_enabled = true`, `jabaki_enabled_at = NOW()`
  - Return domain URL (`slug.jabaki.nl`)
  - Validate slug exists and is published
  - Ref: design.md POST enable spec
  - Depends on: 3.1

- [x] 3.5 Implement `POST /api/landing/domains/jabaki/disable` endpoint
  - Set `jabaki_enabled = false`
  - Ref: design.md POST disable spec
  - Depends on: 3.1

- [x] 3.6 Update publish flow: include Jabaki URL as canonical when enabled
  - Modify `generate_index_html` to check `jabaki_enabled`
  - If enabled, use `https://{slug}.jabaki.nl/` as canonical URL
  - Ref: design.md "Publish Flow Update" priority list
  - Depends on: 3.4

- [x] 3.7 Test: enable Jabaki → visit `slug.jabaki.nl` → page loads correctly
  - Integration test: API enables flag, CloudFront serves content
  - **Type: manual E2E verification**
  - Depends on: 2.4, 3.6

### Phase 4: Backend — Custom Domain Registration

- [x] 4.1 Implement `POST /api/landing/domains/custom` endpoint
  - Validate domain format (no IPs, no jabaki.nl subdomains, not already registered)
  - Request ACM certificate via boto3 in us-east-1
  - Store in `tenant_custom_domains` with status `pending_dns`
  - Return DNS instructions (validation CNAME + routing CNAME)
  - Ref: design.md POST custom endpoint spec + sequence diagram
  - Depends on: 3.2

- [x] 4.2 Implement `POST /api/landing/domains/custom/verify` endpoint
  - Check ACM certificate status via `describe_certificate`
  - If ISSUED: activate domain (update CloudFront, update KVS, set is_active)
  - If PENDING: return current status with helpful message
  - Ref: design.md POST verify spec
  - Depends on: 4.1, 4.4, 4.5

- [x] 4.3 Implement `DELETE /api/landing/domains/custom` endpoint
  - Remove domain from CloudFront distribution CNAMEs
  - Delete ACM certificate
  - Remove from KeyValueStore
  - Delete from `tenant_custom_domains`
  - Ref: design.md DELETE endpoint spec
  - Depends on: 4.1, 4.4, 4.5

- [x] 4.4 Implement CloudFront distribution CNAME update logic
  - Service function to add/remove alternate domain names on distribution
  - Uses boto3 `cloudfront` client: `get_distribution_config`, `update_distribution`
  - Handle ETag-based optimistic locking
  - Ref: design.md sequence diagram "UpdateDistribution"

- [x] 4.5 Implement KeyValueStore update logic
  - Service function to put/delete domain→slug mappings
  - Uses boto3 `cloudfront-keyvaluestore` client
  - Ref: design.md "CloudFront KeyValueStore" section

- [x] 4.6 Add IAM policy for ACM + CloudFront + KVS management via Terraform
  - `aws_iam_policy.custom_domains_management`
  - ACM: RequestCertificate, DescribeCertificate, DeleteCertificate, ListCertificates
  - CloudFront: GetDistribution, GetDistributionConfig, UpdateDistribution
  - KVS: GetKey, PutKey, DeleteKey, ListKeys
  - Attach to backend role
  - Ref: design.md "IAM Policy Updates" section

- [x] 4.7 Update publish flow: use custom domain as canonical when active
  - Extend `generate_index_html` to check custom domain status
  - Priority: custom domain > jabaki subdomain > default CloudFront URL
  - Update `landing.json` SEO section with `alternate_urls`
  - Ref: design.md "Publish Flow Update" priority list
  - Depends on: 3.6, 4.2

- [x] 4.8 Add background job: periodic ACM status check for pending domains
  - Daily check of `tenant_custom_domains` with `verification_status = 'pending_dns'` or `'validating'`
  - Auto-activate domains that become ISSUED
  - Log/notify on failures
  - Ref: requirements.md "Domain verification status checked periodically (daily)"
  - Depends on: 4.2

- [ ] 4.9 Test: full custom domain flow from registration → DNS → verification → active
  - Integration test with mocked ACM responses
  - E2E: register domain, simulate DNS, verify, confirm page loads
  - **Type: manual E2E verification**
  - Depends on: 4.2, 4.3

### Phase 5: Frontend — Domain Management UI

- [x] 5.1 Create `DomainSettings.tsx` — main domain management panel
  - Shows current Jabaki status + custom domain status
  - Entry point in LandingPage admin panel as "Domains" section
  - Uses `GET /api/landing/domains` for data
  - Ref: design.md "Frontend: Domain Management UI", requirements.md US-1/US-2
  - Depends on: 3.3

- [x] 5.2 Create `JabakiSubdomain.tsx` — toggle with preview URL
  - Toggle switch to enable/disable Jabaki subdomain
  - Shows preview: `{slug}.jabaki.nl` with link
  - Calls POST enable/disable endpoints
  - Ref: design.md UI flow item 2
  - Depends on: 3.4, 3.5

- [x] 5.3 Create `CustomDomainForm.tsx` — register, verify, remove flow
  - Input field accepting `www.x.nl` or `x.nl` format
  - Register button → shows DNS instructions
  - Verify button → polls status
  - Remove button with confirmation
  - Ref: design.md UI flow items 3-4, requirements.md US-1 AC
  - Depends on: 4.1, 4.2, 4.3

- [x] 5.4 Create `DnsInstructions.tsx` — context-aware DNS guidance
  - Subdomain (`www.x.nl`): show CNAME record instructions
  - Root domain (`x.nl`): show ALIAS/ANAME instruction + fallback redirect guidance
  - Include "Which DNS providers support ALIAS?" help text
  - List providers that support/don't support ALIAS
  - Ref: requirements.md US-1, design.md DNS instructions response format
  - Depends on: 5.3

- [x] 5.5 Add status badges for domain verification states
  - States: pending, validating, active, failed
  - Color-coded Chakra UI badges
  - Ref: design.md UI flow item 4, requirements.md US-1 AC

- [x] 5.6 Add "Domains" section to LandingPage admin panel
  - Integrate DomainSettings as tab/section in existing admin UI
  - Ref: design.md component file structure
  - Depends on: 5.1

- [x] 5.7 Add i18n translations for domain management UI
  - Dutch + English translations for all domain UI strings
  - Follow `.kiro/specs/Common/Internationalization/TRANSLATION_KEY_CONVENTIONS.md`
  - Depends on: 5.1, 5.2, 5.3, 5.4

- [ ] 5.8 Test: full UI flow — enable Jabaki, register custom domain, verify
  - Manual E2E test through UI
  - **Type: manual verification**
  - Depends on: 5.6, 5.7

### Phase 6: OG Tags & Canonical URL Update

- [x] 6.1 Update `generate_index_html` to use domain-aware canonical URL
  - Apply priority: custom domain > jabaki > default
  - Set `og:url`, `<link rel="canonical">` to highest-priority domain
  - Ref: design.md "Publish Flow Update"
  - Depends on: 4.7

- [x] 6.2 Update `landing.json` SEO section with `alternate_urls` array
  - Include all active URLs as alternates
  - Format per design.md JSON example
  - Ref: design.md "Updated SEO section in landing.json"
  - Depends on: 6.1

- [x] 6.3 Ensure internal landing page links use relative URLs
  - Audit generated HTML for hardcoded domain references
  - Replace any absolute internal URLs with relative paths
  - Ref: requirements.md US-3 "Internal links within the landing page use relative URLs"

- [x] 6.4 Test: OG tags on custom domain show correct canonical URL
  - Verify `og:url` matches the custom domain
  - **Type: manual verification**
  - Depends on: 6.1

### Phase 7: End-User Documentation

- [x] 7.1 Write user manual section: "Connecting your own domain"
  - Step-by-step for subdomain (CNAME)
  - Step-by-step for root domain (ALIAS/ANAME)
  - Fallback: redirect from root to www
  - List providers supporting ALIAS: Route 53, Cloudflare, DNSimple, NS1, Constellix
  - List providers NOT supporting ALIAS: TransIP (basic), Hostnet, Antagonist
  - Ref: requirements.md US-1, design.md DNS instructions
  - Depends on: 5.4

- [x] 7.2 Write user manual section: "Using your jabaki.nl subdomain"
  - How to enable, preview URL, when it's useful
  - Ref: requirements.md US-2
  - Depends on: 5.2

- [x] 7.3 Add troubleshooting section
  - "My domain shows a certificate error" — DNS not propagated / wrong CNAME
  - "My page doesn't load on my domain" — verification pending
  - "How long does verification take?" — typical timeframes
  - Ref: requirements.md non-functional "Graceful degradation"

- [x] 7.4 Link documentation from in-app `DnsInstructions.tsx`
  - Add link/reference to full manual page from the component
  - Depends on: 5.4, 7.1

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-0",
      "name": "Domain Migration",
      "tasks": ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6"]
    },
    {
      "id": "wave-1",
      "name": "Infrastructure",
      "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"],
      "dependsOn": ["wave-0"]
    },
    {
      "id": "wave-2",
      "name": "CloudFront Function",
      "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"],
      "dependsOn": ["wave-1"]
    },
    {
      "id": "wave-3a",
      "name": "Backend Jabaki",
      "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"],
      "dependsOn": ["wave-2"]
    },
    {
      "id": "wave-3b",
      "name": "Backend Custom Domains",
      "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9"],
      "dependsOn": ["wave-3a"]
    },
    {
      "id": "wave-4a",
      "name": "Frontend UI",
      "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8"],
      "dependsOn": ["wave-3b"]
    },
    {
      "id": "wave-4b",
      "name": "OG Tags & Canonical",
      "tasks": ["6.1", "6.2", "6.3", "6.4"],
      "dependsOn": ["wave-3b"]
    },
    {
      "id": "wave-5",
      "name": "Documentation",
      "tasks": ["7.1", "7.2", "7.3", "7.4"],
      "dependsOn": ["wave-4a"]
    }
  ]
}
```

## Notes

- **⚠️ ACTION REQUIRED: Run `terraform apply` in `infrastructure/` to complete Phase 1 deployment.** The ACM certificate validation was interrupted (waiting for DNS propagation after nameserver switch on Aug 8). Rerun apply — it will complete once DNS propagates (check cert status: `aws acm describe-certificate --certificate-arn $(terraform output -raw jabaki_wildcard_cert_arn) --region us-east-1 --query 'Certificate.Status' --output text`).
- **Phase 0 is largely manual** — DNS migration, nameserver switch, domain transfer. Steps 0.7–0.10 run in the background (5-7 days) and don't block Phase 1 once nameservers are switched.
- **Phases 1-2 require Terraform + AWS console access** — infrastructure provisioning and CloudFront Function deployment.
- **Phases 3-7 are code-implementable** — backend APIs, frontend components, OG tags, and documentation.
- **Total estimated effort:** ~23.5h (2h active for migration + 21.5h engineering)
- **Minimum calendar time:** ~6 working sessions (4h/day), domain transfer completes in background by ~Day 5.
- Tasks marked **"Type: manual verification"** or **"Type: manual operation"** cannot be automated by subagents and require human execution.
