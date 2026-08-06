# Landing Page — Spec Overview

## Status: Draft

## Summary

Provide each tenant with a configurable, public-facing landing page that promotes their business. Static delivery via S3/CloudFront, CMS editing via DynamoDB, management via existing MySQL/ParameterService.

## Reading Order

1. `requirements.md` — User stories and acceptance criteria
2. `design.md` — Technical architecture, API contracts, data models
3. `TASKS.md` — Implementation phases with task checkboxes

## Related Documents

- Approach document: `.kiro/specs/myBacklog/landingpage-approach.md`
- Architecture reference: `.kiro/specs/myBacklog/Specification_ Multi-Tenant Landing Page Architecture.md`

## Key Decisions

- **Three-layer architecture**: MySQL (management) → DynamoDB (CMS content) → S3 (public delivery)
- **Block-based page builder**: tenant arranges pre-built block types, not freeform HTML
- **Publish model**: draft edits in DynamoDB, explicit publish writes static JSON to S3
- **Embed block**: external widgets (Guesty, Calendly) via sandboxed iframe — no custom integrations
- **Branding resolution**: `landing_page` namespace → module branding fallback → shared identity
- **Backend**: Flask/Railway (existing), no Lambda/SAM needed
- **New AWS services**: DynamoDB (CMS store), CloudFront (CDN for published pages)

## Change Log

| Date       | Change                                                                                  |
| ---------- | --------------------------------------------------------------------------------------- |
| 2026-08-05 | Initial spec created from approach document                                             |
| 2026-08-06 | Added social media integration (OG tags, share buttons, static HTML shell for crawlers) |
