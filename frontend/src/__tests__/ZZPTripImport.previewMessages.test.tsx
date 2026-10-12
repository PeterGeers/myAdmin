/**
 * Render tests for ZZPTripImport — import preview Klant column + inline messages.
 *
 * Covers task 18.2 of the rittenregistratie-tax-log-redesign spec. Task 18.1
 * changed ZZPTripImport's Preview step to:
 *   - add a Klant column populated from each row's `client_name` (empty cell
 *     when blank/absent), and
 *   - render each per-row `_messages` entry inline and visibly (no hover) as a
 *     separate <Text> line beneath the row, while clean rows (0 messages) show
 *     no message block.
 *
 * These tests drive the real component through the Upload -> Preview step by
 * mocking `importTrips` to return a flat validation result, then assert the
 * rendered Preview DOM. The centralized Chakra mock renders Table/Td as real
 * <table>/<td>, VStack/Text as <div>/<p>, and Tooltip as a passthrough — so
 * message text is in the DOM only because it is rendered inline, not gated
 * behind any hover/focus interaction.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 10.7
 */
import React from 'react';
import { render, screen, waitFor, fireEvent, cleanup } from '../test-utils';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import ZZPTripImport from '../pages/ZZPTripImport';
import type { ImportRow, Vehicle } from '../types/zzpTrips';

/* ─── Service mocks ─── */
vi.mock('../services/tripService', () => ({
  importTrips: vi.fn(),
  commitImport: vi.fn(),
}));
vi.mock('../services/vehicleService', () => ({
  getVehicles: vi.fn(),
}));
vi.mock('../services/apiService', () => ({
  authenticatedGet: vi.fn(),
  buildEndpoint: (endpoint: string) => endpoint,
}));

/* ─── useTypedTranslation mock (identity t) ─── */
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'nl', changeLanguage: vi.fn() },
  }),
}));

import { importTrips } from '../services/tripService';
import { getVehicles } from '../services/vehicleService';

/* ─── Fixtures ─── */
const vehicle: Vehicle = {
  id: 7,
  license_plate: 'AB-123-C',
  make: 'Volkswagen',
  model: 'Golf',
  year_built: 2020,
  vin: null,
  vehicle_type: 'business',
  odometer_unit: 'km',
  owner_lease_company: null,
  start_odometer: 45000,
  start_date: '2026-01-01',
  is_active: true,
};

const row = (overrides: Partial<ImportRow> & { _row_number: number; _status: ImportRow['_status'] }): ImportRow => ({
  trip_date: '2026-05-05',
  start_address: 'Amsterdam',
  end_address: 'Utrecht',
  start_odometer: 45000,
  end_odometer: 45050,
  trip_category: 'Zakelijk',
  trip_purpose: 'klantbezoek',
  client_name: undefined,
  notes: undefined,
  _messages: [],
  ...overrides,
});

// Row with a client name + zero messages (clean row).
const cleanRow = row({ _row_number: 1, _status: 'ok', client_name: 'Acme BV', _messages: [] });
// Row with a single date-format error message, no client name.
const dateErrRow = row({
  _row_number: 2,
  _status: 'error',
  client_name: '  ', // blank -> empty Klant cell
  _messages: ['Ongeldige datum "5-mei": verwacht formaat YYYY-MM-DD of DD-MM-YYYY'],
});
// Row with MULTIPLE validation messages.
const multiMsgRow = row({
  _row_number: 3,
  _status: 'error',
  client_name: 'Globex',
  _messages: ['Categorie ontbreekt', 'Eind KM kleiner dan Begin KM'],
});

const flatResponse = {
  success: true as const,
  total_rows: 3,
  valid: 1,
  warnings: 0,
  errors: 2,
  rows: [cleanRow, dateErrRow, multiMsgRow],
  preview: [cleanRow, dateErrRow, multiMsgRow],
};

/** Drives the component from Upload -> Preview and resolves once the table is shown. */
async function renderPreview() {
  vi.mocked(getVehicles).mockResolvedValue({ success: true, data: [vehicle] });
  vi.mocked(importTrips).mockResolvedValue(flatResponse);

  const { container } = render(<ZZPTripImport />);

  // Vehicles load on mount (sets selectedVehicle). Wait for the option.
  await waitFor(() => expect(screen.getByText(/AB-123-C/)).toBeTruthy());

  // Provide a file to the hidden file input so handleNext passes validation.
  const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(['date,from,to'], 'ritten.csv', { type: 'text/csv' });
  fireEvent.change(fileInput, { target: { files: [file] } });

  // Click "Volgende" to trigger import + advance to Preview.
  fireEvent.click(screen.getByText(/Volgende/));

  // Preview renders once the summary badges appear.
  await waitFor(() => expect(screen.getByText(/Totaal: 3 rijen/)).toBeTruthy());

  return container;
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe('ZZPTripImport preview — Klant column (Req 7.5)', () => {
  it('renders a Klant column header', async () => {
    await renderPreview();
    const headers = screen.getAllByRole('columnheader').map((th) => th.textContent);
    expect(headers).toContain('Klant');
  });

  it('shows the client_name value for a row that has one', async () => {
    await renderPreview();
    expect(screen.getByText('Acme BV')).toBeTruthy();
    expect(screen.getByText('Globex')).toBeTruthy();
  });

  it('shows an empty Klant cell when client_name is blank/absent', async () => {
    const container = await renderPreview();
    // The blank-client row (dateErrRow) must not surface its whitespace value as text.
    expect(screen.queryByText('  ')).toBeNull();
    // Sanity: there is a data row whose Klant cell is empty. Find the first body
    // row (row #1 = cleanRow has a client; row #2 = dateErrRow is blank). We
    // assert at least one <td> is empty, confirming blank -> empty cell.
    const emptyCells = Array.from(container.querySelectorAll('tbody td')).filter(
      (td) => td.textContent === '',
    );
    expect(emptyCells.length).toBeGreaterThan(0);
  });
});

describe('ZZPTripImport preview — inline validation messages (Req 7.1, 7.2, 7.3, 7.4)', () => {
  it('renders a failed row\'s message inline and visible without hover (Req 7.1, 7.2)', async () => {
    await renderPreview();
    // The date-format message text is present in the rendered DOM directly —
    // no hover/focus interaction was performed to reveal it.
    expect(
      screen.getByText(/Ongeldige datum "5-mei": verwacht formaat/),
    ).toBeTruthy();
  });

  it('renders every message of a multi-message row as a distinct entry (Req 7.3)', async () => {
    await renderPreview();
    const msg1 = screen.getByText('Categorie ontbreekt');
    const msg2 = screen.getByText('Eind KM kleiner dan Begin KM');
    expect(msg1).toBeTruthy();
    expect(msg2).toBeTruthy();
    // Distinct entries: two separate elements, not one concatenated node.
    expect(msg1).not.toBe(msg2);
    expect(msg1.textContent).toBe('Categorie ontbreekt');
    expect(msg2.textContent).toBe('Eind KM kleiner dan Begin KM');
  });

  it('shows no message block for a clean row with zero messages (Req 7.4)', async () => {
    const container = await renderPreview();
    // cleanRow carries no messages. The two error-row messages render as 3
    // message <p> entries total (1 + 2). A clean row must contribute none, so
    // the total inline-message count equals exactly the error rows' messages.
    const allMessageTexts = [
      'Ongeldige datum "5-mei": verwacht formaat YYYY-MM-DD of DD-MM-YYYY',
      'Categorie ontbreekt',
      'Eind KM kleiner dan Begin KM',
    ];
    allMessageTexts.forEach((txt) => {
      expect(screen.getByText(txt)).toBeTruthy();
    });
    // No stray message rows: the clean row's client value appears, but none of
    // its (absent) messages do. Count message-row <tr> blocks: there are two
    // rows with messages, so two extra message rows beneath data rows.
    // Total <tr> = 1 header + 3 data rows + 2 message rows = 6.
    const rows = container.querySelectorAll('tr');
    expect(rows.length).toBe(6);
  });
});
