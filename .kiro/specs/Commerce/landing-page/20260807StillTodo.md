# Key gaps still to address:

2. .kiro\specs\Commerce\landing-page\improve-landing-page-look-and-feel.md Block settings (themas, ...) Backgroud colour or picture. Block formats

3. How dom we manage images. Without some management we will create massive number of files never used again See .kiro\specs\image-asset-management

Last Future work

# Phase 5: Custom Domains (future — separate effort)

**→ Full spec: `.kiro/specs/Commerce/landing-page/custom-domains/`**

Req 1: As a tenant i want my private url to become the url used for the tenants landing page (slug) and that the url stays as is (no overwrite)
Req 2: As the myAdmin owner I want to offer my tenants the option to use slug.jabaki.nl that loads the tenants landing page and that the url stays as is (no overwrite)

- [ ] 5.1 Subdomain routing (wildcard DNS `*.jabaki.nl` + ACM cert)
- [ ] 5.2 Tenant resolution from HTTP Host header (CloudFront Function + KeyValueStore)
- [ ] 5.3 Custom domain CNAME support (tenant registers in admin)
- [ ] 5.4 SSL provisioning per custom domain (ACM per domain, SNI)
- [ ] 5.5 Domain verification flow (DNS CNAME record via ACM)
- [ ] 5.6 Approval workflow for multi-user tenants
- [ ] 5.7 A/B testing support (serve different versions)
- [ ] 5.8 Scheduled re-publish for tenants with live data blocks
