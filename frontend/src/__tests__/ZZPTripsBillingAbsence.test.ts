/**
 * Static / smoke assertions that lock in the tax-log redesign's *absences*.
 *
 * Feature: rittenregistratie-tax-log-redesign — these tests protect the redesign
 * from silently regressing by reading the real source files (not mocked modules)
 * and asserting on their textual content. They are deliberately
 * terminal-/render-free: no component is mounted, nothing is fetched, so the run
 * cannot hang.
 *
 * Coverage:
 *   - Req 5.3 — no hardcoded km_rate / 0.23 anywhere in the trip UI or trip service.
 *   - Req 5.5 — the frontend `Trip` type declares no billing-related fields and
 *               HAS the free-text `client_name` field.
 *   - Req 5.6 — the out-of-scope TimeTracking feature files (ZZPTimeTracking,
 *               ZZPInvoices, zzpInvoiceService) are left intact: their billing
 *               surface is still present (they were NOT gutted by this spec).
 *
 * Follows .kiro/steering/33-frontend-testing.md (Vitest + jsdom). Mirrors the
 * "static source check" pattern already used in ZZPTrips.test.tsx.
 */

import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

// All paths are resolved relative to this test file (frontend/src/__tests__).
const readSource = (relFromThisFile: string): string =>
  fs.readFileSync(path.resolve(__dirname, relFromThisFile), 'utf-8');

// ---------------------------------------------------------------------------
// Trip-module surface files that must stay billing-free.
// Trip UI: ZZPTrips, ZZPTripQuick, ZZPTripImport, TripModal. Trip service:
// tripService. (Paths are relative to frontend/src/__tests__.)
// ---------------------------------------------------------------------------
const TRIP_UI_AND_SERVICE_FILES: Record<string, string> = {
  'ZZPTrips.tsx': '../pages/ZZPTrips.tsx',
  'ZZPTripQuick.tsx': '../pages/ZZPTripQuick.tsx',
  'ZZPTripImport.tsx': '../pages/ZZPTripImport.tsx',
  'TripModal.tsx': '../components/zzp/TripModal.tsx',
  'tripService.ts': '../services/tripService.ts',
};

// ---------------------------------------------------------------------------
// Req 5.3 — no hardcoded km_rate (previously 0.23) anywhere in the trip UI or
// trip service. We match the identifier `km_rate` and the literal rate 0.23.
// ---------------------------------------------------------------------------
describe('Req 5.3 — no km_rate / 0.23 in trip UI or trip service', () => {
  for (const [label, rel] of Object.entries(TRIP_UI_AND_SERVICE_FILES)) {
    it(`${label} contains no km_rate identifier`, () => {
      const src = readSource(rel);
      expect(src).not.toContain('km_rate');
    });

    it(`${label} contains no hardcoded 0.23 km-rate literal`, () => {
      const src = readSource(rel);
      // Match the bare numeric literal 0.23 (not part of a longer number such as
      // 0.234 or 10.23). A hardcoded km rate would appear as `0.23`.
      expect(src).not.toMatch(/(?<![\d.])0\.23(?![\d])/);
    });
  }
});

// ---------------------------------------------------------------------------
// Req 5.5 — the frontend `Trip` type declares no billing fields and HAS
// client_name. We read the type source and inspect the `Trip` interface block
// specifically, so unrelated interfaces in the same file (e.g. TripFilters,
// RoutePreset) do not create false positives/negatives.
// ---------------------------------------------------------------------------
describe('Req 5.5 — Trip type: no billing fields, has client_name', () => {
  const typesSrc = readSource('../types/zzpTrips.ts');

  // Isolate the `export interface Trip { ... }` block.
  const tripBlockMatch = typesSrc.match(/export interface Trip\s*\{([\s\S]*?)\n\}/);

  it('has an identifiable Trip interface block', () => {
    expect(tripBlockMatch).not.toBeNull();
  });

  const tripBlock = tripBlockMatch ? tripBlockMatch[1] : '';

  it('declares client_name on the Trip type', () => {
    expect(tripBlock).toMatch(/\bclient_name\b/);
  });

  it.each([
    'contact_id',
    'contact',
    'is_billable',
    'is_billed',
    'invoice_id',
  ])('Trip type does not declare billing field %s', (field) => {
    // Field declarations look like `  <field>?: ...` or `  <field>: ...`.
    const fieldDecl = new RegExp(`^\\s*${field}\\??\\s*:`, 'm');
    expect(tripBlock).not.toMatch(fieldDecl);
  });
});

// ---------------------------------------------------------------------------
// Req 5.6 — the TimeTracking feature is out of scope and must be left with ZERO
// modifications. A static source read cannot by itself prove the git diff is
// empty, but it CAN prove the files were not gutted: their billing surface is
// still fully present. (A git-level untouched check is a stronger, separate
// verification done outside this hang-free test.) If any of these symbols
// disappeared, the files were edited by this spec — which is forbidden.
// ---------------------------------------------------------------------------
describe('Req 5.6 — TimeTracking files intact (billing surface still present)', () => {
  it('ZZPTimeTracking.tsx still wires up time-entry invoicing', () => {
    const src = readSource('../pages/ZZPTimeTracking.tsx');
    // Imports and invokes the time-entry → invoice action.
    expect(src).toContain("from '../services/zzpInvoiceService'");
    expect(src).toContain('createInvoiceFromTimeEntries');
    // Core time-tracking data wiring.
    expect(src).toContain('getTimeEntries');
    expect(src).toContain('getTimeSummary');
    // Billable concept retained in the (out-of-scope) time-tracking surface.
    expect(src).toContain('is_billable');
  });

  it('ZZPInvoices.tsx still wires up the invoices surface', () => {
    const src = readSource('../pages/ZZPInvoices.tsx');
    expect(src).toContain("from '../services/zzpInvoiceService'");
    expect(src).toContain('getInvoices');
    expect(src).toContain('copyLastInvoice');
    expect(src).toContain('InvoiceStatusBadge');
  });

  it('zzpInvoiceService.ts still exposes its full invoice/billing surface', () => {
    const src = readSource('../services/zzpInvoiceService.ts');
    // The invoice service belongs to the TimeTracking feature and is NOT edited
    // by this spec — every pre-existing export must remain, including the
    // trip-side createInvoiceFromTrips (its *trip-side callers* were removed,
    // but this out-of-scope service file itself is left untouched).
    for (const sym of [
      'getInvoices',
      'getInvoice',
      'createInvoice',
      'copyLastInvoice',
      'createInvoiceFromTimeEntries',
      'createInvoiceFromTrips',
    ]) {
      expect(src).toContain(sym);
    }
  });
});
