/**
 * ZZPTripQuick Unit Tests
 *
 * Covers the tax-log redesign changes to the quick trip entry page:
 * - Free-text Klant input bound to `client_name`; empty input → null in payload (Req 2.3, 2.5)
 * - Client-side >255-char Klant guard: value retained, error shown, submission blocked (Req 2.4)
 * - Required-one validation for category and purpose preserved (Req 10.3, 10.4)
 * - Odometer pre-fill from the vehicle's last trip preserved (Req 10.1)
 *
 * Feature: rittenregistratie-tax-log-redesign
 * Follows .kiro/steering/33-frontend-testing.md (Vitest + jsdom + RTL, Chakra auto-mock,
 * `render` from @/test-utils, mocked services).
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';

// --- Service mocks (declared before component import) ---------------------
vi.mock('../services/tripService', () => ({
  createTrip: vi.fn(),
  getTrips: vi.fn(),
}));
vi.mock('../services/vehicleService', () => ({
  getVehicles: vi.fn(),
}));
vi.mock('../services/routePresetService', () => ({
  getRoutePresets: vi.fn(),
}));

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@/test-utils';
import ZZPTripQuick from '../pages/ZZPTripQuick';
import { createTrip, getTrips } from '../services/tripService';
import { getVehicles } from '../services/vehicleService';
import { getRoutePresets } from '../services/routePresetService';
import type { Vehicle, Trip } from '../types/zzpTrips';

const mockCreateTrip = vi.mocked(createTrip);
const mockGetTrips = vi.mocked(getTrips);
const mockGetVehicles = vi.mocked(getVehicles);
const mockGetRoutePresets = vi.mocked(getRoutePresets);

const vehicle: Vehicle = {
  id: 1,
  license_plate: 'AB-12-CD',
  make: 'Volkswagen',
  model: 'Transporter',
  year_built: 2020,
  vin: null,
  vehicle_type: 'business',
  odometer_unit: 'km',
  owner_lease_company: null,
  start_odometer: 10000,
  start_date: '2024-01-01',
  is_active: true,
};

const lastTrip: Trip = {
  id: 42,
  vehicle_id: 1,
  trip_date: '2024-06-01',
  start_time: null,
  end_time: null,
  start_address: 'Amsterdam',
  end_address: 'Utrecht',
  start_odometer: 10000,
  end_odometer: 10050,
  distance_km: 50,
  trip_category: 'Zakelijk',
  trip_purpose: 'Klantbezoek',
  route_description: null,
  client_name: null,
  project_name: null,
  notes: null,
  is_gap_fill: false,
  is_cancelled: false,
  version: 1,
};

/** Render the page and wait for initial data load (spinner → form). */
async function renderPage() {
  await act(async () => {
    render(<ZZPTripQuick />);
  });
  // Wait until the loading spinner is replaced by the form.
  await waitFor(() => {
    expect(screen.getByLabelText('Eind km-stand')).toBeInTheDocument();
  });
}

/** Select a trip purpose (the purpose select is the last <select> on the page). */
function selectPurpose(value = 'Klantbezoek') {
  const selects = document.querySelectorAll('select');
  const purposeSelect = selects[selects.length - 1] as HTMLSelectElement;
  fireEvent.change(purposeSelect, { target: { value } });
}

/**
 * Fill the fields the component requires to pass validation up to the Klant guard:
 * route addresses, end odometer, and (by default) a trip purpose. Category defaults
 * to "Zakelijk" in the component, so it needs no explicit selection.
 * Pass `withPurpose = false` to leave purpose unset (to exercise the purpose guard).
 */
function fillRouteAndOdometer(endKm = '10100', withPurpose = true) {
  fireEvent.change(screen.getByPlaceholderText('Van'), { target: { value: 'Amsterdam' } });
  fireEvent.change(screen.getByPlaceholderText('Naar'), { target: { value: 'Utrecht' } });
  fireEvent.change(screen.getByLabelText('Eind km-stand'), { target: { value: endKm } });
  if (withPurpose) selectPurpose();
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetVehicles.mockResolvedValue({ success: true, data: [vehicle] });
  mockGetRoutePresets.mockResolvedValue({ success: true, data: [] });
  mockGetTrips.mockResolvedValue({ success: true, data: [lastTrip] });
  mockCreateTrip.mockResolvedValue({ success: true, data: { ...lastTrip } });
});

describe('ZZPTripQuick — Klant field (Req 2.3, 2.5)', () => {
  it('renders a Klant input and writes trimmed client_name to the create payload', async () => {
    await renderPage();

    const klant = screen.getByLabelText('Klant');
    expect(klant).toBeInTheDocument();

    fillRouteAndOdometer();
    fireEvent.change(klant, { target: { value: '  Acme BV  ' } });

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });

    await waitFor(() => expect(mockCreateTrip).toHaveBeenCalledTimes(1));
    const payload = mockCreateTrip.mock.calls[0][0];
    expect(payload.client_name).toBe('Acme BV');
  });

  it('sends client_name = null when the Klant input is left empty (Req 2.5)', async () => {
    await renderPage();

    fillRouteAndOdometer();
    // Klant intentionally left blank.

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });

    await waitFor(() => expect(mockCreateTrip).toHaveBeenCalledTimes(1));
    const payload = mockCreateTrip.mock.calls[0][0];
    expect(payload.client_name).toBeNull();
  });
});

describe('ZZPTripQuick — Klant length guard (Req 2.4)', () => {
  it('blocks submission when Klant exceeds 255 chars, retains the value, and shows an error', async () => {
    await renderPage();

    fillRouteAndOdometer();

    const klant = screen.getByLabelText('Klant') as HTMLInputElement;
    const tooLong = 'x'.repeat(256);
    fireEvent.change(klant, { target: { value: tooLong } });

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });

    // Submission blocked.
    expect(mockCreateTrip).not.toHaveBeenCalled();
    // Entered value retained.
    expect(klant.value).toBe(tooLong);
    // Inline error shown.
    await waitFor(() => {
      expect(screen.getByText(/maximaal 255 tekens/i)).toBeInTheDocument();
    });
  });

  it('clears the Klant error once the value is edited back under the limit', async () => {
    await renderPage();
    fillRouteAndOdometer();

    const klant = screen.getByLabelText('Klant') as HTMLInputElement;
    fireEvent.change(klant, { target: { value: 'y'.repeat(256) } });

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });
    await waitFor(() => expect(screen.getByText(/maximaal 255 tekens/i)).toBeInTheDocument());

    // Editing the field clears the error.
    fireEvent.change(klant, { target: { value: 'Acme BV' } });
    expect(screen.queryByText(/maximaal 255 tekens/i)).not.toBeInTheDocument();
  });
});

describe('ZZPTripQuick — required-one category/purpose (Req 10.3, 10.4)', () => {
  it('renders category and purpose selects with a default category and no default purpose', async () => {
    await renderPage();

    // Category defaults to "Zakelijk"; purpose starts empty (placeholder "Ritdoel").
    expect(screen.getByRole('option', { name: 'Zakelijk' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Klantbezoek' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Ritdoel' })).toBeInTheDocument();
  });

  it('blocks submission when purpose is not selected and retains entered values (Req 10.4)', async () => {
    await renderPage();

    fillRouteAndOdometer('10100', false);
    // Purpose left unselected (empty); category stays at default "Zakelijk".

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });

    expect(mockCreateTrip).not.toHaveBeenCalled();
    // Entered route/odometer values retained.
    expect((screen.getByPlaceholderText('Van') as HTMLInputElement).value).toBe('Amsterdam');
    expect((screen.getByPlaceholderText('Naar') as HTMLInputElement).value).toBe('Utrecht');
    expect((screen.getByLabelText('Eind km-stand') as HTMLInputElement).value).toBe('10100');
  });

  it('submits once both category and purpose are set (Req 10.3, 10.4)', async () => {
    await renderPage();

    // fillRouteAndOdometer selects purpose "Klantbezoek"; category stays "Zakelijk".
    fillRouteAndOdometer();

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });

    await waitFor(() => expect(mockCreateTrip).toHaveBeenCalledTimes(1));
    const payload = mockCreateTrip.mock.calls[0][0];
    expect(payload.trip_category).toBe('Zakelijk');
    expect(payload.trip_purpose).toBe('Klantbezoek');
  });
});

describe('ZZPTripQuick — odometer pre-fill (Req 10.1)', () => {
  it('pre-fills the start odometer from the vehicle last trip end odometer', async () => {
    await renderPage();

    await waitFor(() => {
      expect((screen.getByLabelText('Start km-stand') as HTMLInputElement).value).toBe('10050');
    });
    // getTrips was queried for the selected vehicle with a limit.
    expect(mockGetTrips).toHaveBeenCalledWith({ vehicle_id: 1, limit: 1 });
  });

  it('falls back to the vehicle start_odometer when there are no prior trips', async () => {
    mockGetTrips.mockResolvedValue({ success: true, data: [] });

    await renderPage();

    await waitFor(() => {
      expect((screen.getByLabelText('Start km-stand') as HTMLInputElement).value).toBe('10000');
    });
  });
});

/**
 * Bugfix: zzp-quick-trip-silent-save-failure
 *
 * The quick-entry page silently loses a trip when the backend REJECTS the create
 * with a resolved `{success:false}` body (HTTP 400/500 — the HTTP layer does not
 * throw on these, only on 401, so `createTrip` resolves rather than rejecting and
 * the component's `catch` never fires). The classic repro is the RETURN leg: after
 * saving the outbound leg the user reverses the route and submits again; the backend
 * rejects (e.g. `end_odometer must be greater than start_odometer`) but the UI shows
 * success and resets the form, discarding the entry.
 *
 * The Chakra auto-mock's `useToast` returns a bare vi.fn() and does not render toast
 * content, so the reliable observable signal is the FORM-RESET side effect: on a
 * rejected create the entered end km-stand + Van/Naar addresses must be PRESERVED
 * (not cleared) so the user can retry.
 */
describe('ZZPTripQuick — silent save failure on rejected create (bug condition)', () => {
  it('does NOT reset the form when createTrip resolves {success:false} (return-leg data loss)', async () => {
    // Backend rejects the (return) leg but resolves — does not throw.
    mockCreateTrip.mockResolvedValue({
      success: false,
      error: 'end_odometer must be greater than start_odometer',
    } as never);

    await renderPage();
    fillRouteAndOdometer('10100');

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });

    // The submit reached the service with the entered payload.
    await waitFor(() => expect(mockCreateTrip).toHaveBeenCalledTimes(1));

    // BUG CONDITION: a rejected create must NOT clear the form — the entered values
    // must survive so the trip can be retried. On the unfixed component the success
    // path runs and these fields are wiped (end km-stand → '', addresses → '').
    expect((screen.getByLabelText('Eind km-stand') as HTMLInputElement).value).toBe('10100');
    expect((screen.getByPlaceholderText('Van') as HTMLInputElement).value).toBe('Amsterdam');
    expect((screen.getByPlaceholderText('Naar') as HTMLInputElement).value).toBe('Utrecht');
  });

  it('shows a generic fallback behavior path when {success:false} has no error message', async () => {
    mockCreateTrip.mockResolvedValue({ success: false } as never);

    await renderPage();
    fillRouteAndOdometer('10100');

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });

    await waitFor(() => expect(mockCreateTrip).toHaveBeenCalledTimes(1));
    // Form preserved even when the backend omits an error message.
    expect((screen.getByLabelText('Eind km-stand') as HTMLInputElement).value).toBe('10100');
  });
});

describe('ZZPTripQuick — successful create resets the form (preservation)', () => {
  it('clears the form and advances the start odometer when createTrip resolves {success:true}', async () => {
    mockCreateTrip.mockResolvedValue({ success: true, data: { ...lastTrip } });

    await renderPage();
    fillRouteAndOdometer('10100');

    await act(async () => {
      fireEvent.click(screen.getByText('REGISTREER RIT'));
    });

    await waitFor(() => expect(mockCreateTrip).toHaveBeenCalledTimes(1));

    // Happy path: addresses + end km-stand cleared, start km-stand advanced to entered end.
    await waitFor(() => {
      expect((screen.getByLabelText('Eind km-stand') as HTMLInputElement).value).toBe('');
    });
    expect((screen.getByPlaceholderText('Van') as HTMLInputElement).value).toBe('');
    expect((screen.getByPlaceholderText('Naar') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('Start km-stand') as HTMLInputElement).value).toBe('10100');
  });
});
