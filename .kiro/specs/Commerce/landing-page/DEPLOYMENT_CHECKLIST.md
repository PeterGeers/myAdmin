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
- [x] `LANDING_PAGE_BASE_URL=https://d3afn46os9e9nc.cloudfront.net`
- [x] `CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID=E28OSWC7A9O9K2`
- [x] `CONTACT_FORM_API_URL=https://invigorating-celebration-production.up.railway.app`
- [x] `ALLOWED_ORIGINS` includes CloudFront domain
- [x] `ENVIRONMENT=production` (already set)

### 3.3 Verify Connectivity

- [x] Landing page routes registered and responding (tested via Docker backend)
- [x] Public endpoint `/api/public/landing/resolve/<slug>` returns proper 404 for unknown slugs
- [x] Auth-protected endpoints (`/api/landing/draft`, `/api/landing/slug/validate`) return 401 without JWT
- [x] Test slug creation via API — verified via UI (slug "myadmin" created for PeterPrive)

---

## 4. Frontend Wiring

### 4.1 Environment Variables

Add to frontend `.env` (local dev — done) and production config:

- [x] `VITE_CLOUDFRONT_PUBLIC_PAGES_URL=https://d3afn46os9e9nc.cloudfront.net` (local .env)
- [x] `VITE_CLOUDFRONT_DOMAIN=d3afn46os9e9nc.cloudfront.net` (local .env)

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

- [x] Create `docs/docs/landing-page/index.md` — Dutch user guide
- [x] Create `docs/docs/landing-page/index.en.md` — English user guide
- [x] Sections covered: slug setup, blocks, images, branding, SEO, publishing, contact form, share buttons
- [x] Add to `docs/mkdocs.yml` nav section

### 6.2 Build & Verify

- [ ] `cd docs && pip install mkdocs-material mkdocs-static-i18n mkdocs-print-site-plugin && mkdocs build`
- [ ] Verify landing page docs render correctly

---

## 7. Smoke Test (End-to-End)

### 7.1 Happy Path

- [x] As Tenant_Admin: set slug "myadmin"
- [x] Add Hero block, About block
- [x] Configure branding (company name, logo, tagline, contact info, social links) ✓
- [x] Configure SEO (title, description, OG image) ✓
- [x] Publish
- [x] Visit `/myadmin` — page renders with correct content, images, branding, logo ✓
- [x] Submit contact form — submission stored in MySQL + email sent via SES ✓
- [x] Verify OG tags present in HTML (title, description, image, url) — verified via curl ✓

### 7.2 Edge Cases

- [x] Visit `/nonexistent` — shows 404 page ✓
- [x] Unpublish — page returns 404 immediately (CloudFront invalidation works) ✓
- [x] Slug validation — invalid/unknown slugs properly rejected ✓
- [x] Test rate limiting on contact form — blocks after 5 submissions per email/hour ✓
- [x] Test honeypot field — bot submission silently discarded, not stored ✓

---

## 8. Production Deployment

### 8.1 Push to main

- [x] Merge `feature/landing-page-deployment` branch into `main`
- [x] Railway auto-deploys backend from `main`

### 8.2 Frontend Production Env Vars

Add to your frontend production build config (wherever the React SPA is hosted):

- [x] `VITE_CLOUDFRONT_PUBLIC_PAGES_URL=https://d3afn46os9e9nc.cloudfront.net` (in deploy-frontend.yml)
- [x] `VITE_CLOUDFRONT_DOMAIN=d3afn46os9e9nc.cloudfront.net` (in deploy-frontend.yml)

### 8.3 Verify Production Backend

- [x] Backend redeploys successfully on Railway
- [x] Landing page routes respond (`/api/public/landing/resolve/myadmin`)
- [x] DynamoDB + S3 accessible from Railway

### 8.4 Verify Production Frontend

- [x] Landing Page tab visible in Tenant Admin
- [x] Image previews work in the editor
- [x] Publish/unpublish works end-to-end

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
