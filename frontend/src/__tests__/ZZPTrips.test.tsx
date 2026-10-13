/**
 * Tests for the ZZPTrips (Rittenregistratie) list page after the tax-log redesign.
 *
 * Feature: rittenregistratie-tax-log-redesign — frontend trips list surface.
 *
 * Covers Requirement 2.6 (Client column sourced from client_name, empty cell when
 * null), 5.1 (no "Fact." / is_billable column), 5.2 (no invoice-from-trips button).
 *
 * NOTE (memory): this file mounts the full 582-line ZZPTrips page, which is heavy
 * in jsdom (the Chakra Tabs mock renders every TabPanel). To keep its footprint
 * small it mounts the page EXACTLY ONCE and asserts every DOM fact against that
 * single tree — do not add more render(<ZZPTrips />) calls here. The render-free
 * billing-ABSENCE invariants (Req 5.2/5.3/5.4/5.5/5.6 static source checks) live
 * in ZZPTripsBillingAbsence.test.ts, which mounts nothing.
 *
 * Follows .kiro/steering/33-frontend-testing.md: Vitest + jsdom + React Testing
 * Library, Chakra auto-mocked via vite alias, `render` from `@/test-utils`.
 */

import React from 'react';
import { vi, describe, it, expect, beforeAll, afterAll } from 'vitest';
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

// ---------------------------------------------------------------------------
// Single shared mount. The page is heavy, so we render it ONCE for the whole
// file and assert every DOM fact against that one tree (both trips are present,
// one with a client_name and one without, so a single render covers Req 2.6's
// present/empty cases plus the 5.1/5.2 absence checks).
// ---------------------------------------------------------------------------
describe('ZZPTrips — tax-log redesign list surface', () => {
  beforeAll(async () => {
    vi.clearAllMocks();
    setupMocks([TRIP_WITH_CLIENT, TRIP_WITHOUT_CLIENT]);
    render(<ZZPTrips />);
    // Wait until the table has loaded both rows before any assertion runs.
    await waitFor(() => {
      expect(screen.getByText('Amsterdam')).toBeTruthy();
      expect(screen.getByText('Rotterdam')).toBeTruthy();
    });
  });

  afterAll(() => {
    cleanup();
  });

  // Req 2.6 — Client column sourced from client_name; value shown when present.
  it('renders the client_name value in the Client column', () => {
    expect(screen.getByText('Acme BV')).toBeTruthy();
  });

  // Req 2.6 — empty Client cell (no text) when client_name is null.
  it('shows an empty Client cell when client_name is null', () => {
    // Find the null-client trip's row via a unique address cell and assert the
    // client column cell is empty. Column order: date, start, end, distance,
    // category, purpose, client, gap.
    const nullRow = screen.getByText('Den Haag').closest('tr');
    expect(nullRow).toBeTruthy();
    const cells = Array.from(nullRow!.querySelectorAll('td'));
    const clientCell = cells[6];
    expect(clientCell).toBeTruthy();
    expect(clientCell!.textContent).toBe('');
  });

  // Req 2.6 / 5.1 — the Client column header is present; no billing "Fact." column.
  it('renders a Client column header and no billing "Fact." column', () => {
    // Client header is rendered (translation key echoed by the mocked hook).
    expect(screen.getByText('trips.labels.client')).toBeTruthy();

    // Req 5.1 — no "Fact." column / no is_billable-derived header or cell.
    expect(screen.queryByText(/Fact\.?/i)).toBeNull();
    expect(screen.queryByText('trips.labels.billable')).toBeNull();
    expect(screen.queryByText('trips.status.billable')).toBeNull();
  });

  // Req 5.2 — no invoice-from-trips button anywhere in the trips UI.
  it('renders no invoice-from-trips button', () => {
    const buttons = screen.queryAllByRole('button');
    for (const btn of buttons) {
      expect(btn.textContent ?? '').not.toMatch(/invoice|factuur|factureren/i);
    }
    expect(screen.queryByText(/create invoice|invoice selected/i)).toBeNull();
  });
});
