# Custom Domains — Tasks

## Phase 0: Domain Migration (jabaki.nl → Route 53) — ~2h active + 5-7 days transfer

- [ ] 0.1 Create Route 53 hosted zone for `jabaki.nl` — Terraform
- [ ] 0.2 Recreate all existing DNS records in Route 53 (MX, TXT, SES DKIM, A/AAAA as alias)
- [ ] 0.3 Add wildcard CNAME `*.jabaki.nl` → CloudFront distribution
- [ ] 0.4 Verify all records resolve correctly: `dig jabaki.nl MX`, `dig jabaki.nl TXT`, etc.
- [ ] 0.5 Switch nameservers at Squarespace → Route 53 NS values
- [ ] 0.6 Verify: email forwarding works, SES sending works, CloudFront still serves jabaki.nl
- [ ] 0.7 Unlock domain at Squarespace, get EPP/auth code
- [ ] 0.8 Initiate domain transfer at Route 53 console
- [ ] 0.9 Approve transfer confirmation email
- [ ] 0.10 Verify transfer complete — Route 53 is registrar + DNS host

**Dependencies:** None. Can start immediately. Steps 0.7–0.10 run in background (5–7 days) and don't block Phase 1.

---

## Phase 1: Infrastructure (Jabaki Wildcard) — ~4h

- [ ] 1.1 ~~Register `jabaki.nl` domain~~ — handled by Phase 0 transfer
- [ ] 1.2 ~~Create Route 53 hosted zone~~ — done in Phase 0
- [ ] 1.3 Create ACM wildcard certificate `*.jabaki.nl` in `us-east-1` — Terraform
- [ ] 1.4 Add DNS validation record for ACM in Route 53 — Terraform
- [ ] 1.5 Update CloudFront distribution: add `*.jabaki.nl` alias + wildcard cert — Terraform
- [ ] 1.6 Create CloudFront KeyValueStore for domain→slug mapping — Terraform
- [ ] 1.7 Test: visit `test-slug.jabaki.nl` → verify CloudFront responds (even if 404)

**Dependencies:** Phase 0 steps 0.1–0.5 complete (DNS on Route 53).

---

## Phase 2: CloudFront Function Update — ~2h

- [ ] 2.1 Update CloudFront Function to handle host-based routing for `*.jabaki.nl`
- [ ] 2.2 Add KeyValueStore association to CloudFront Function for custom domain lookups
- [ ] 2.3 Add fallback: unknown hosts return 404 (no content leak)
- [ ] 2.4 Test with published tenant: `slug.jabaki.nl` serves correct `index.html`
- [ ] 2.5 Test: file requests (images, `landing.json`) route correctly under subdomain
- [ ] 2.6 Test: existing `/p/{slug}` path routing still works unchanged

**Dependencies:** Phase 1 complete.

---

## Phase 3: Database & Backend — Jabaki Subdomain — ~3h

- [ ] 3.1 Add `jabaki_enabled` column to `tenant_slugs` table (migration)
- [ ] 3.2 Create `tenant_custom_domains` table (migration)
- [ ] 3.3 Implement `GET /api/landing/domains` endpoint
- [ ] 3.4 Implement `POST /api/landing/domains/jabaki/enable` endpoint
- [ ] 3.5 Implement `POST /api/landing/domains/jabaki/disable` endpoint
- [ ] 3.6 Update publish flow: include Jabaki URL as canonical when enabled
- [ ] 3.7 Test: enable Jabaki → visit `slug.jabaki.nl` → page loads, URL stays

**Dependencies:** Phase 2 complete for E2E testing.

---

## Phase 4: Backend — Custom Domain Registration — ~5h

- [ ] 4.1 Implement `POST /api/landing/domains/custom` — request ACM cert, store in DB
- [ ] 4.2 Implement `POST /api/landing/domains/custom/verify` — check ACM status, activate
- [ ] 4.3 Implement `DELETE /api/landing/domains/custom` — cleanup cert + CloudFront + KVS
- [ ] 4.4 Implement CloudFront distribution CNAME update logic (add/remove aliases)
- [ ] 4.5 Implement KeyValueStore update logic (put/delete domain→slug mapping)
- [ ] 4.6 Add IAM policy for ACM + CloudFront + KVS management — Terraform
- [ ] 4.7 Update publish flow: use custom domain as canonical when active
- [ ] 4.8 Add background job: periodic ACM status check for pending domains (daily)
- [ ] 4.9 Test: full flow from registration → DNS → verification → page loads on custom domain

**Dependencies:** Phase 3 complete (DB schema), Phase 1 (infrastructure).

---

## Phase 5: Frontend — Domain Management UI — ~4h

- [ ] 5.1 Create `DomainSettings.tsx` — main panel showing current domain config
- [ ] 5.2 Create `JabakiSubdomain.tsx` — toggle with preview URL
- [ ] 5.3 Create `CustomDomainForm.tsx` — input, register, verify flow (accepts both `www.x.nl` and `x.nl`)
- [ ] 5.4 Create `DnsInstructions.tsx` — context-aware instructions:
  - Subdomain (`www.x.nl`): show CNAME record
  - Root domain (`x.nl`): show ALIAS/ANAME instruction + fallback redirect guidance
  - Include "Which DNS providers support ALIAS?" help text (Route 53, Cloudflare, DNSimple, etc.)
- [ ] 5.5 Add status badges (pending, validating, active, failed)
- [ ] 5.6 Add "Domains" section to LandingPage admin panel
- [ ] 5.7 Add translations (i18n) for domain management UI
- [ ] 5.8 Test: full UI flow — enable Jabaki, register custom domain, verify

**Dependencies:** Phase 4 (backend APIs available).

---

## Phase 6: OG Tags & Canonical URL Update — ~2h

- [ ] 6.1 Update `generate_index_html` to use domain-aware canonical URL
- [ ] 6.2 Update `landing.json` SEO section with `alternate_urls`
- [ ] 6.3 Internal links in landing page use relative URLs (no hardcoded domain)
- [ ] 6.4 Test: OG tags on custom domain page show custom domain URL
- [ ] 6.5 Test: Facebook Sharing Debugger validates custom domain URL
- [ ] 6.6 Test: OG tags on Jabaki subdomain show Jabaki URL

**Dependencies:** Phase 4 (custom domains active), Phase 3 (Jabaki active).

---

## Phase 7: End-User Documentation — ~1.5h

- [ ] 7.1 Write user manual section: "Connecting your own domain"
  - Step-by-step for subdomain (CNAME)
  - Step-by-step for root domain (ALIAS/ANAME)
  - Fallback: redirect from root to www (for providers without ALIAS support)
  - List of providers that support ALIAS: Route 53, Cloudflare, DNSimple, NS1, Constellix
  - List of providers that do NOT: TransIP (basic), Hostnet, Antagonist — recommend redirect
- [ ] 7.2 Write user manual section: "Using your jabaki.nl subdomain"
- [ ] 7.3 Add troubleshooting: "My domain shows a certificate error" / "DNS not propagated yet"
- [ ] 7.4 Add to in-app `DnsInstructions.tsx`: link to full manual page

**Dependencies:** Phase 5 (UI exists to reference in screenshots).

---

## Total Estimated Effort: ~23.5h (2h active for migration + 21.5h engineering)

| Phase                  | Effort | Critical Path      |
| ---------------------- | ------ | ------------------ |
| 0. Domain Migration    | 2h     | Yes (start first)  |
| 1. Infrastructure      | 4h     | Yes (after 0.5)    |
| 2. CloudFront Function | 2h     | Yes (depends on 1) |
| 3. Backend Jabaki      | 3h     | Yes (depends on 2) |
| 4. Backend Custom      | 5h     | Yes (depends on 3) |
| 5. Frontend            | 4h     | Depends on 4       |
| 6. OG Tags             | 2h     | Depends on 3+4     |
| 7. Documentation       | 1.5h   | Depends on 5       |

**Note:** Phase 0 transfer (steps 0.7–0.10) takes 5–7 days but runs in the background. Engineering work on Phase 1+ can start as soon as nameservers are switched (step 0.5).
