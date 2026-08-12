 For 100+++ times you have to use linux tools in the terminal.



# Fails to scan PeterPrive

## Media Assets
Scan > Start Scan
- Works for tenant kimgeers
- Fails for tenant PeterPrive Verbinding verbroken tijdens scan. Probeer opnieuw.
## Clean. Here's the summary of what was wrong and what I fixed:

Root Cause
The scan for PeterPrive has 24 s3_asset_references of type landing_page. The reconciliation code tried to verify them by running a MySQL query against a landing_pages table — but that table doesn't exist in MySQL. Landing pages are stored in DynamoDB (myadmin-landing-pages table). This threw a DatabaseError (table not found), which crashed the generator, closed the SSE stream, and triggered the generic "Verbinding verbroken" error.

kimgeers has zero references, so the reconciliation loop never hit this code path.

Fixes
Backend media_asset_service.py — Updated ENTITY_TYPE_REGISTRY to mark landing_page as a DynamoDB-backed entity, and updated _reconcile_references to:

Use LandingPageService.get_draft(slug) for landing page existence checks
Gracefully skip if LandingPageService can't be initialized
Also added a safety net: if any other MySQL table is missing (e.g. zzp_invoices), it logs a warning and skips instead of crashing
Frontend ScanTab.tsx — The onmessage handler now checks for type === 'error' events from the backend and displays the actual error message instead of falling through to the generic "connection lost" on stream close.

Frontend mediaAsset.ts — Added type and error fields to the ScanProgress interface.

Note: The discover_landing_page_references method also queries a non-existent MySQL landing_pages table. That's a separate flow (reference discovery, not scan), but it has the same underlying problem and will need updating to use DynamoDB too.