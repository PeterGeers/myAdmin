/**
 * Tests for the ZZPTrips (Rittenregistratie) list page after the tax-log redesign.
 *
 * Feature: rittenregistratie-tax-log-redesign — frontend trips list surface.
 *
 * Covers Requirement 2.6 (Client column sourced from client_name, empty cell when
 * null), 5.1 (no "Fact." / is_billable column), 5.2 (no invoice-from-trips button,
 * no createInvoiceFromTrips handler), 5.4 (trip service exposes no billing surface),
 * and the change-with-tests contract (10.7).
 *
 * Follows .kiro/steering/33-frontend-testing.md: Vitest + jsdom + React Testing
 * Library, Chakra auto-mocked via vite alias, `render` from `@/test-utils`.
 */

import React from 'react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '../test-utils';

import type { Trip, Vehicle } from '../types/zzpTrips';

// ---------------------------------------------------------------------------
// Service mocks — the page loads vehicles, trips, and a summary on mount.
// ---------------------------------------------------------------------------
const mockGetTrips = vi.fn();
const mockGetTripSummary = vi.fn();
const mockExportTrips = vi.fn();
const mockGetVehicles = vi.fn();

vi.mock('../services/tripService', () => ({
  getTrips: (...args: any[]) => mockGetTrips(...args),
  getTripSummary: (...args: any[]) => mockGetTripSummary(...args),
  exportTrips: (...args: any[]) => mockExportTrips(...args),
}));

vi.mock('../services/vehicleService', () => ({
  getVehicles: (...args: any[]) => mockGetVehicles(...args),
}));

// Translation hook echoes keys so assertions are locale-independent.
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    i18n: { language: 'en' },
  }),
}));

// Heavy / data-fetching children are stubbed so the test stays focused on the
// Ritten tab list. The Chakra Tabs mock renders every TabPanel, so the lazy
// vehicle/import panels must be stubbed too (otherwise they fetch on mount).
vi.mock('../components/zzp/TripModal', () => ({
  TripModal: () => null,
}));
vi.mock('../components/zzp/BijtellingWidget', () => ({
  BijtellingWidget: () => null,
}));
vi.mock('../components/zzp/GapFillBanner', () => ({
  GapFillBanner: () => null,
}));
vi.mock('../pages/ZZPVehicles', () => ({
  default: () => <div data-testid="stub-vehicles" />,
}));
vi.mock('../pages/ZZPTripImport', () => ({
  default: () => <div data-testid="stub-import" />,
}));

import ZZPTrips from '../pages/ZZPTrips';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const VEHICLE: Vehicle = {
  id: 1,
  license_plate: 'AB-123-C',
  make: 'Volvo',
  model: 'V60',
  year_built: 2022,
  vin: null,
  vehicle_type: 'business',
  odometer_unit: 'km',
  owner_lease_company: null,
  start_odometer: 1000,
  start_date: '2024-01-01',
  is_active: true,
};

function makeTrip(overrides: Partial<Trip>): Trip {
  return {
    id: 1,
    vehicle_id: 1,
    trip_date: '2024-06-01',
    start_time: null,
    end_time: null,
    start_address: 'Amsterdam',
    end_address: 'Utrecht',
    start_odometer: 1000,
    end_odometer: 1040,
    distance_km: 40,
    trip_category: 'Zakelijk',
    trip_purpose: 'Klantbezoek',
    route_description: null,
    client_name: null,
    project_name: null,
    notes: null,
    is_gap_fill: false,
    is_cancelled: false,
    version: 1,
    ...overrides,
  };
}

const TRIP_WITH_CLIENT = makeTrip({
  id: 1,
  trip_date: '2024-06-01',
  start_address: 'Amsterdam',
  end_address: 'Utrecht',
  client_name: 'Acme BV',
});

const TRIP_WITHOUT_CLIENT = makeTrip({
  id: 2,
  trip_date: '2024-06-02',
  start_address: 'Rotterdam',
  end_address: 'Den Haag',
  start_odometer: 1040,
  end_odometer: 1070,
  distance_km: 30,
  client_name: null,
});

function setupMocks(trips: Trip[]) {
  mockGetVehicles.mockResolvedValue({ success: true, data: [VEHICLE] });
  mockGetTrips.mockResolvedValue({ success: true, data: trips });
  mockGetTripSummary.mockResolvedValue({
    success: true,
    data: {
      year: 2024,
      vehicle_id: 1,
      total_km: 70,
      zakelijk_km: 70,
      prive_km: 0,
      woonwerk_km: 0,
      bijtelling_km: 0,
      bijtelling_limit: 500,
      bijtelling_warning: false,
      tax_deduction: 0,
    },
  });
}

describe('ZZPTrips — tax-log redesign list surface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMocks([TRIP_WITH_CLIENT, TRIP_WITHOUT_CLIENT]);
  });

  afterEach(() => {
    cleanup();
  });

  // Req 2.6 — Client column sourced from client_name; value shown when present.
  it('renders the client_name value in the Client column', async () => {
    render(<ZZPTrips />);

    // Table renders once trips have loaded.
    await waitFor(() => {
      expect(screen.getByText('Amsterdam')).toBeTruthy();
    });

    expect(screen.getByText('Acme BV')).toBeTruthy();
  });

  // Req 2.6 — empty Client cell (no text) when client_name is null.
  it('shows an empty Client cell when client_name is null', async () => {
    render(<ZZPTrips />);

    await waitFor(() => {
      expect(screen.getByText('Rotterdam')).toBeTruthy();
    });

    // The null-client trip's row renders without any client text; find its row
    // via a unique address cell and assert the client column cell is empty.
    const nullRow = screen.getByText('Den Haag').closest('tr');
    expect(nullRow).toBeTruthy();
    const cells = Array.from(nullRow!.querySelectorAll('td'));
    // Column order: date, start, end, distance, category, purpose, client, gap.
    const clientCell = cells[6];
    expect(clientCell).toBeTruthy();
    expect(clientCell!.textContent).toBe('');
  });

  // Req 2.6 — the Client column header is present and sourced from the client label.
  it('renders a Client column header and no billing "Fact." column', async () => {
    render(<ZZPTrips />);

    await waitFor(() => {
      expect(screen.getByText('Amsterdam')).toBeTruthy();
    });

    // Client header is rendered (translation key echoed by the mocked hook).
    expect(screen.getByText('trips.labels.client')).toBeTruthy();

    // Req 5.1 — no "Fact." column / no is_billable-derived header or cell.
    expect(screen.queryByText(/Fact\.?/i)).toBeNull();
    expect(screen.queryByText('trips.labels.billable')).toBeNull();
    expect(screen.queryByText('trips.status.billable')).toBeNull();
  });

  // Req 5.2 — no invoice-from-trips button anywhere in the trips UI.
  it('renders no invoice-from-trips button', async () => {
    render(<ZZPTrips />);

    await waitFor(() => {
      expect(screen.getByText('Amsterdam')).toBeTruthy();
    });

    // No button whose label references invoicing.
    const buttons = screen.queryAllByRole('button');
    for (const btn of buttons) {
      expect(btn.textContent ?? '').not.toMatch(/invoice|factuur|factureren/i);
    }
    expect(screen.queryByText(/create invoice|invoice selected/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Req 5.2 / 5.4 — the page source must not import or invoke createInvoiceFromTrips,
// and the trip service must not expose a billing operation. A static read of the
// real source files (not the mocked module) keeps this invariant from silently
// regressing.
// ---------------------------------------------------------------------------
describe('ZZPTrips — no billing imports/usage (static source check)', () => {
  const readSource = (relFromThisFile: string): string => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require('fs');
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require('path');
    return fs.readFileSync(path.resolve(__dirname, relFromThisFile), 'utf-8');
  };

  it('ZZPTrips.tsx neither imports nor references createInvoiceFromTrips', () => {
    const src = readSource('../pages/ZZPTrips.tsx');
    expect(src).not.toContain('createInvoiceFromTrips');
    expect(src).not.toContain('getUnbilledTrips');
    expect(src).not.toContain('is_billable');
    expect(src).not.toContain('is_billed');
    expect(src).not.toContain('contact_id');
    expect(src).not.toContain('km_rate');
  });

  it('tripService.ts exposes no createInvoiceFromTrips or getUnbilledTrips export', () => {
    const src = readSource('../services/tripService.ts');
    expect(src).not.toContain('createInvoiceFromTrips');
    expect(src).not.toContain('getUnbilledTrips');
    expect(src).not.toContain('km_rate');
  });
});
