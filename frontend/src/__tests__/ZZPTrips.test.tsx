/**
 * Tests for the ZZPTrips (Rittenregistratie) list page after the tax-log redesign.
 *
 * Feature: rittenregistratie-tax-log-redesign - frontend trips list surface.
 *
 * Covers Requirement 2.6 (Client column sourced from client_name, empty cell when
 * null), 5.1 (no "Fact." / is_billable column), 5.2 (no invoice-from-trips button).
 *
 * RENDER-FREE BY DESIGN. The ZZPTrips page is a heavy 582-line component whose
 * Chakra Tabs mock renders every TabPanel; mounting it in jsdom repeatedly drove
 * the vitest worker into a multi-GB heap and an OOM "Worker exited unexpectedly"
 * crash. These requirements are structural facts about the page's source, so -
 * like its sibling ZZPTripsBillingAbsence.test.ts - this file asserts them by
 * reading the real source text. It mounts nothing, fetches nothing, and therefore
 * cannot hang or run out of memory.
 *
 * Follows .kiro/steering/33-frontend-testing.md (Vitest + jsdom) and mirrors the
 * static-source-check pattern of ZZPTripsBillingAbsence.test.ts.
 */

import fs from 'fs';
import path from 'path';
import { describe, it, expect } from 'vitest';

const readSource = (relFromThisFile: string): string =>
  fs.readFileSync(path.resolve(__dirname, relFromThisFile), 'utf-8');

const src = readSource('../pages/ZZPTrips.tsx');

// Req 2.6 - the Client column is sourced from the trip's free-text client_name,
// shows the value when present and an EMPTY cell when null. In source this is a
// single <Td> rendering `trip.client_name ?? ''`, under a `trips.labels.client`
// column header.
describe('Req 2.6 - Client column sourced from client_name', () => {
  it('renders a Client column header (trips.labels.client)', () => {
    expect(src).toContain('trips.labels.client');
  });

  it('renders the client cell from trip.client_name with an empty-string fallback', () => {
    expect(src).toMatch(/trip\.client_name\s*\?\?\s*''/);
  });

  it('does not source the client column from a formal contact_id / contact object', () => {
    expect(src).not.toContain('contact_id');
    expect(src).not.toMatch(/trip\.contact\b/);
  });
});

// Req 5.1 - there is NO billing column. The redesign dropped the "Fact."
// (facturabel / is_billable) column and its header/cell.
describe('Req 5.1 - no billing ("Fact.") column', () => {
  it('declares no is_billable / is_billed field usage', () => {
    expect(src).not.toContain('is_billable');
    expect(src).not.toContain('is_billed');
  });

  it('renders no "Fact." billing column header or billable label', () => {
    expect(src).not.toMatch(/Fact\.?/);
    expect(src).not.toContain('trips.labels.billable');
    expect(src).not.toContain('trips.status.billable');
  });
});

// Req 5.2 - no invoice-from-trips action anywhere in the trips page: no button,
// no handler, no import of the removed billing operations.
describe('Req 5.2 - no invoice-from-trips button or billing action', () => {
  it('references no invoice / factuur action in the trips page', () => {
    expect(src).not.toMatch(/invoice/i);
    expect(src).not.toMatch(/factuur|factureren/i);
  });

  it('neither imports nor invokes createInvoiceFromTrips / getUnbilledTrips', () => {
    expect(src).not.toContain('createInvoiceFromTrips');
    expect(src).not.toContain('getUnbilledTrips');
  });
});

// Feature: end-odometer column — the trips table exposes a sortable/filterable
// "Eind km-stand" column (trips.labels.endOdometer) so the list can be ordered by
// end odometer to reconstruct the real driven sequence. The value comes straight
// from trip.end_odometer. (Static source check — the page is render-free here.)
describe('End-odometer column (sortable "Eind km-stand")', () => {
  it('renders an end-odometer column header (trips.labels.endOdometer)', () => {
    expect(src).toContain('trips.labels.endOdometer');
  });

  it('wires the end_odometer column into the filter/sort framework', () => {
    expect(src).toMatch(/onSort=\{\(\) => handleSort\('end_odometer'\)\}/);
    expect(src).toContain("setFilter('end_odometer'");
    expect(src).toMatch(/end_odometer:\s*''/); // present in initialFilters
  });

  it('renders the end-odometer cell from trip.end_odometer', () => {
    expect(src).toMatch(/\{trip\.end_odometer\}/);
  });
});
