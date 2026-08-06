# Landing Page — Deployment Checklist

## 1. AWS Infrastructure (Terraform)

### 1.1 DynamoDB Table

- [x] Run `terraform plan` to verify `myadmin-landing-pages` table creation
- [x] Run `terraform apply` to create the table in production
- [x] **Test mode**: DynamoDB is shared (single table). Test data uses PK prefix `TENANT#test-*`. No separate test table needed — TEST_MODE controls which MySQL database is used, not DynamoDB.
- [x] Verify table is ACTIVE: `aws dynamodb describe-table --table-name myadmin-landing-pages --region eu-west-1`

### 1.2 S3 Buckets

- [x] `terraform apply` creates `myadmin-public-pages-production`
- [x] Verify bucket exists with public access blocked
- [x] Verify AES-256 encryption is enabled
- [x] Verify bucket policy allows CloudFront OAC read

### 1.3 CloudFront Distribution

- [x] Verify distribution is deployed and enabled
- [x] Note the CloudFront domain name (e.g., `d1234abcd.cloudfront.net`)
- [x] Test URL rewrite: `GET /p/test-slug` → should serve `test-slug/index.html`
- [x] Set `CLOUDFRONT_PUBLIC_PAGES_DOMAIN` env var in Railway

### 1.4 IAM Policies

- [x] Verify `myadmin-dynamodb-landing-pages-production` policy created
- [x] Verify `myadmin-s3-public-pages-write-production` policy created
- [x] Attach both policies to the Railway backend IAM user/role:
  ```bash
  aws iam attach-user-policy --user-name <backend-iam-user> --policy-arn <dynamodb-policy-arn>
  aws iam attach-user-policy --user-name <backend-iam-user> --policy-arn <s3-write-policy-arn>
  ```

---

## 2. MySQL Tables

### 2.1 Local Docker (dev)

- [x] Run migration: `mysql -u root -p finance < backend/sql/create_tenant_slugs_table.sql`
- [x] Run migration: `mysql -u root -p finance < backend/sql/create_landing_page_submissions_table.sql`
- [x] Run migration: `mysql -u root -p finance < backend/sql/add_is_public_to_products.sql`
- [x] Verify tables exist: `SHOW TABLES LIKE '%landing%'; SHOW TABLES LIKE '%tenant_slug%';`

### 2.2 Railway Production

- [x] Run same 3 migrations against production database (via MySQL Workbench)
- [x] Verify tables exist and have correct schema

### 2.3 Test Database (testfinance)

- [x] Run same migrations against testfinance database (for TEST_MODE)

---

## 3. Backend Wiring

### 3.1 Blueprint Registration

- [x] Add to `backend/src/app.py`:
  ```python
  from routes.landing_page_routes import landing_page_bp
  app.register_blueprint(landing_page_bp)
  ```
- [x] Place it after the existing blueprint registrations (before `static_bp`)

### 3.2 Environment Variables (Railway)

Add these to the Railway backend service:

- [x] `LANDING_PAGES_BUCKET=myadmin-public-pages-production`
- [x] `CLOUDFRONT_PUBLIC_PAGES_DOMAIN=d3afn46os9e9nc.cloudfront.net`
- [x] `LANDING_PAGE_BASE_URL=https://pgeers.nl`
- [x] `ENVIRONMENT=production` (already set)

### 3.3 Verify Connectivity

- [x] Landing page routes registered and responding (tested via Docker backend)
- [x] Public endpoint `/api/public/landing/resolve/<slug>` returns proper 404 for unknown slugs
- [x] Auth-protected endpoints (`/api/landing/draft`, `/api/landing/slug/validate`) return 401 without JWT
- [ ] Test slug creation via API: `PUT /api/landing/slug` with body `{"slug": "test-tenant"}` (requires auth token)

---

## 4. Frontend Wiring

### 4.1 Environment Variables

Add to frontend `.env.production` / Vercel/GH Pages config:

- [ ] `VITE_CLOUDFRONT_PUBLIC_PAGES_URL=https://<cloudfront-domain>.cloudfront.net`
- [ ] `VITE_CLOUDFRONT_DOMAIN=<cloudfront-domain>.cloudfront.net`

### 4.2 PublicLandingPage Route (App.tsx)

- [x] Verify `/p/:tenantSlug` route is active (already coded — confirm it's not behind a feature flag)

### 4.3 TenantAdmin Landing Page Tab

- [x] Verify the `LandingPageEditor` import in `TenantAdminDashboard.tsx` works
- [x] Verify the "🌐 Landing Page" tab appears for Tenant_Admin users

### 4.4 Build Verification

- [x] `cd frontend && npm run build` — verify no errors
- [x] ~~Check bundle includes `public-landing` chunk~~ N/A — landing page is now standalone static HTML

---

## 5. Translations (i18n)

### 5.1 Verify Translation Keys

- [x] `frontend/src/locales/en/admin.json` — has `landingPage.*` section (134 keys)
- [x] `frontend/src/locales/nl/admin.json` — has `landingPage.*` section (134 keys)
- [x] Check all keys are translated (no missing keys in NL) — EN and NL in sync

### 5.2 Missing Translations Scan

- [x] Search for hardcoded English strings — only 2 minor strings found (non-critical, in public block renderers now replaced by standalone HTML)
- [x] No action needed — admin UI fully uses `t()` keys

---

## 6. Online Documentation (MkDocs)

### 6.1 End-User Manual

- [ ] Create `docs/docs/nl/landing-page/index.md` — Dutch user guide
- [ ] Create `docs/docs/en/landing-page/index.md` — English user guide
- [ ] Sections to cover:
  - Setting up your slug
  - Adding and editing blocks
  - Uploading images
  - Branding & social links
  - SEO settings & OG image
  - Publishing & unpublishing
  - Contact form submissions
  - Share buttons
- [ ] Add to `docs/mkdocs.yml` nav section

### 6.2 Build & Verify

- [ ] `cd docs && pip install mkdocs-material mkdocs-static-i18n mkdocs-print-site-plugin && mkdocs build`
- [ ] Verify landing page docs render correctly

---

## 7. Smoke Test (End-to-End)

### 7.1 Happy Path

- [ ] As Tenant_Admin: set slug "test-rental"
- [ ] Add Hero block, About block, Contact block
- [ ] Configure branding (company name, colors, social links)
- [ ] Configure SEO (title, description, OG image)
- [ ] Publish
- [ ] Visit `/p/test-rental` — verify page renders with correct branding
- [ ] Submit contact form — verify submission stored + email sent
- [ ] Verify OG tags with Facebook Sharing Debugger: `https://developers.facebook.com/tools/debug/?q=https://myadmin.app/p/test-rental`

### 7.2 Edge Cases

- [ ] Visit `/p/nonexistent` — verify 404 page
- [ ] Unpublish — verify `/p/test-rental` returns 404
- [ ] Try invalid slug formats — verify validation errors
- [ ] Test rate limiting on contact form (6 rapid submissions)
- [ ] Test honeypot field (submit with value → silently accepted, not stored)

---

## Order of Operations

1. **Terraform** (create AWS resources)
2. **IAM policy attachment** (grant Railway access)
3. **Railway env vars** (configure the backend)
4. **MySQL migrations** (create tables)
5. **Backend blueprint registration** (wire the routes)
6. **Deploy backend** (Railway redeploy)
7. **Frontend env vars** (set CloudFront domain)
8. **Deploy frontend** (GH Pages/Vercel redeploy)
9. **Smoke test** (verify everything works)
10. **Documentation** (create mkdocs pages)
