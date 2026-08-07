# Key gaps still to address:

2. Share buttons — not rendered in the standalone HTML yet

4. Version history / rollback — backend + frontend exist, needs verification

6. Block settings (themas, ...) Backgroud colour or picture.  Block formats

8. How dom we manage images. Without some management we will create massive number of files never used again

Last Future work


## Shared Components for blocks .kiro\specs\Commerce\landing-page\block-item-editors-tasks.md

- [ ] 5.1 Extract `ItemListEditor` — reusable wrapper for add/remove/reorder pattern
  - Props: items array, renderItem function, onAdd, onRemove, onReorder
  - Provides move up/down buttons, remove with confirmation, add button
- [ ] 5.2 Use `ItemListEditor` in all 4 editors above (refactor after Phase 1)


# Phase 5: Custom Domains (future — separate effort)
How to map a private url to the slug / landing page
How to make a goodwinsolutuions.nl/slug generic for all slugs

- [ ] 5.1 Subdomain routing (wildcard DNS `*.myadmin.app` + ACM cert)
- [ ] 5.2 Tenant resolution from HTTP Host header (Lambda@Edge or CloudFront Function)
- [ ] 5.3 Custom domain CNAME support (tenant registers in admin)
- [ ] 5.4 SSL provisioning per custom domain (ACM)
- [ ] 5.5 Domain verification flow (DNS TXT record)
- [ ] 5.6 Approval workflow for multi-user tenants
- [ ] 5.7 A/B testing support (serve different versions)
- [ ] 5.8 Scheduled re-publish for tenants with live data blocks
