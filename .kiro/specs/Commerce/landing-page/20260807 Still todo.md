# Key gaps still to address:

1. Contact form — the standalone HTML form posts to /api/public/landing/{slug}/contact but needs the backend URL configured (currently points to relative path, won't work from CloudFront)
2. Share buttons — not rendered in the standalone HTML yet
3. Branding/SEO settings — UI exists, smoke test needed to confirm it flows through to published HTML
4. Version history / rollback — backend + frontend exist, needs verification
5. ServicesBlock — ZZP service data in standalone HTML (same pattern as the removed PropertiesBlock)
6. Block settings (themas, ...)
7. Edit mode for Accordion: Item editor coming in next phase
8. How dom we manage images. Without some management we will create massive number of files never used again

Last Future work