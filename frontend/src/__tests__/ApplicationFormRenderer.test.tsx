/**
 * Tests for the PUBLIC member-application config-driven renderer (task 9.1).
 *
 * Covers the task's required behaviours:
 *  - renders from a MOCKED public field-config, SECTIONED + ordered by `functional_group`/`order`
 *    (R4.1/R4.6) via Chakra `FormControl`/`FormLabel`/`FormErrorMessage`, widget by `type`;
 *  - labels in the applicant LOCALE (`label[locale]`, nl fallback, R6b);
 *  - `show_when` conditional visibility hide/show (R6.3);
 *  - the field-config SERVICE read over MSW (R5/R1a), incl. the 409 not-available + 404 arms;
 *  - flatten ↔ un-flatten ROUND-TRIP to/from the dotted-key submit shape (R10a.4).
 *
 * Chakra is auto-mocked (vite test alias); `render` comes from `@/test-utils` (provider wrapper).
 */

import React, { useState } from 'react';
import { describe, it, expect, beforeEach, afterEach, afterAll, beforeAll, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { render, screen, within } from '@/test-utils';
import userEvent from '@testing-library/user-event';

import { ApplicationFormRenderer } from '../components/public/application/ApplicationFormRenderer';
import { buildInitialValues } from '../components/public/application/applicationForm.model';
import {
  fetchPublicFieldConfig,
  flattenFields,
  unflattenFields,
  type PublicFieldConfig,
} from '../services/applicationApi';

// ---------------------------------------------------------------------------
// A representative public field-config (design §3.1): dotted keys, bilingual labels,
// two functional groups with deliberately OUT-OF-ORDER input to prove ordering, an enum
// with options, and a show_when-gated field.
// ---------------------------------------------------------------------------
const CONFIG: PublicFieldConfig = {
  fields: [
    // Intentionally listed out of (group, order) sequence to prove the renderer orders.
    {
      key: 'personal.last_name',
      type: 'string',
      label: { nl: 'Achternaam', en: 'Last name' },
      functional_group: 'personal',
      order: 20,
      required: true,
    },
    {
      key: 'personal.first_name',
      type: 'string',
      label: { nl: 'Voornaam', en: 'First name' },
      functional_group: 'personal',
      order: 10,
      required: true,
    },
    {
      key: 'membership.membership_type',
      type: 'enum',
      label: { nl: 'Type', en: 'Type' },
      functional_group: 'membership',
      order: 10,
      required: true,
      options: [
        { value: 'gewoon', label: { nl: 'Gewoon lid', en: 'Ordinary member' } },
        { value: 'incasso', label: { nl: 'Incasso', en: 'Direct debit' } },
      ],
    },
    {
      key: 'overlay.iban',
      type: 'string',
      label: { nl: 'IBAN', en: 'IBAN' },
      functional_group: 'membership',
      order: 20,
      // Only shown when the applicant picks the direct-debit membership type.
      show_when: { 'membership.membership_type': 'incasso' },
    },
  ],
  locales: ['nl', 'en'],
  notice: { version: 'v1', text: { nl: 'Toestemming', en: 'Consent' } },
};

/** A tiny controlled harness so changing a select re-evaluates `show_when`. */
function Harness({ locale }: { locale?: string }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    buildInitialValues(CONFIG.fields),
  );
  return (
    <ApplicationFormRenderer
      config={CONFIG}
      locale={locale}
      values={values}
      onChange={(k, v) => setValues((prev) => ({ ...prev, [k]: v }))}
    />
  );
}

describe('ApplicationFormRenderer — config-driven (task 9.1)', () => {
  it('renders every field grouped by functional_group, each in its group section', () => {
    render(<Harness />);

    const personal = document.querySelector('[data-group="personal"]')!;
    const membership = document.querySelector('[data-group="membership"]')!;
    expect(personal).toBeTruthy();
    expect(membership).toBeTruthy();

    // Personal group holds the two name inputs; membership holds the type select.
    expect(within(personal as HTMLElement).getByLabelText('Voornaam')).toBeInTheDocument();
    expect(within(personal as HTMLElement).getByLabelText('Achternaam')).toBeInTheDocument();
    expect(within(membership as HTMLElement).getByLabelText('Type')).toBeInTheDocument();
  });

  it('orders fields within a group by (order, key), not input order', () => {
    render(<Harness />);
    const personal = document.querySelector('[data-group="personal"]') as HTMLElement;
    const labels = within(personal).getAllByText(/Voornaam|Achternaam/).map((n) => n.textContent);
    // first_name (order 10) precedes last_name (order 20), despite the reversed input order.
    expect(labels).toEqual(['Voornaam', 'Achternaam']);
  });

  it('renders the widget by type: string→input, enum→select from options', () => {
    render(<Harness />);
    // string → text input
    const firstName = screen.getByLabelText('Voornaam') as HTMLInputElement;
    expect(firstName.tagName).toBe('INPUT');
    // enum → select carrying its options
    const typeSelect = screen.getByLabelText('Type') as HTMLSelectElement;
    expect(typeSelect.tagName).toBe('SELECT');
    expect(within(typeSelect).getByText('Gewoon lid')).toBeInTheDocument();
    expect(within(typeSelect).getByText('Incasso')).toBeInTheDocument();
  });

  it('uses labels in the applicant locale (en), including option labels', () => {
    render(<Harness locale="en" />);
    expect(screen.getByLabelText('First name')).toBeInTheDocument();
    expect(screen.getByLabelText('Last name')).toBeInTheDocument();
    const typeSelect = screen.getByLabelText('Type') as HTMLSelectElement;
    expect(within(typeSelect).getByText('Ordinary member')).toBeInTheDocument();
  });

  it('falls back to nl for an absent/invalid locale (R6b.2)', () => {
    render(<Harness locale="fr" />);
    expect(screen.getByLabelText('Voornaam')).toBeInTheDocument();
    expect(screen.queryByLabelText('First name')).not.toBeInTheDocument();
  });

  it('honors show_when: the IBAN field is hidden until direct-debit is chosen, then shown', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // Hidden initially (membership_type is blank).
    expect(screen.queryByLabelText('IBAN')).not.toBeInTheDocument();

    // Choose the direct-debit type → the show_when condition holds → IBAN appears.
    await user.selectOptions(screen.getByLabelText('Type'), 'incasso');
    expect(screen.getByLabelText('IBAN')).toBeInTheDocument();

    // Switch back to a non-matching value → IBAN hides again.
    await user.selectOptions(screen.getByLabelText('Type'), 'gewoon');
    expect(screen.queryByLabelText('IBAN')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// flatten ↔ un-flatten round-trip (R10a.4)
// ---------------------------------------------------------------------------
describe('flatten ↔ un-flatten (R10a.4)', () => {
  it('un-flattens the flat dotted-key submit shape into the nested member shape', () => {
    const flat = {
      'personal.first_name': 'Ada',
      'personal.last_name': 'Lovelace',
      'membership.membership_type': 'incasso',
      'overlay.iban': 'NL00BANK0123456789',
    };
    expect(unflattenFields(flat)).toEqual({
      personal: { first_name: 'Ada', last_name: 'Lovelace' },
      membership: { membership_type: 'incasso' },
      overlay: { iban: 'NL00BANK0123456789' },
    });
  });

  it('round-trips nested → flat → nested unchanged', () => {
    const nested = {
      personal: { first_name: 'Ada', last_name: 'Lovelace' },
      membership: { membership_type: 'gewoon' },
    };
    expect(unflattenFields(flattenFields(nested))).toEqual(nested);
  });

  it('round-trips flat → nested → flat unchanged for the renderer form state', () => {
    const flat = buildInitialValues(CONFIG.fields);
    flat['personal.first_name'] = 'Grace';
    expect(flattenFields(unflattenFields(flat))).toEqual(flat);
  });
});

// ---------------------------------------------------------------------------
// The public field-config service read over MSW (R5 / R1a)
// ---------------------------------------------------------------------------
const BASE = 'https://public-api.test';
const FIELD_CONFIG_URL = `${BASE}/public/members/:slug/field-config`;

const server = setupServer(
  http.get(FIELD_CONFIG_URL, () => HttpResponse.json({ data: CONFIG })),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('fetchPublicFieldConfig (MSW, R5/R1a)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns success with the unwrapped field-config on 200', async () => {
    const result = await fetchPublicFieldConfig('hdcn', { baseUrl: BASE });
    expect(result.status).toBe('success');
    if (result.status === 'success') {
      expect(result.data.fields).toHaveLength(4);
      expect(result.data.locales).toEqual(['nl', 'en']);
    }
  });

  it('maps a 409 to not_available carrying the neutral code (D15/R5.4)', async () => {
    server.use(
      http.get(FIELD_CONFIG_URL, () =>
        HttpResponse.json({ code: 'errors.application.notAvailable' }, { status: 409 }),
      ),
    );
    const result = await fetchPublicFieldConfig('hdcn', { baseUrl: BASE });
    expect(result.status).toBe('not_available');
    if (result.status === 'not_available') {
      expect(result.code).toBe('errors.application.notAvailable');
    }
  });

  it('maps a 404 (unknown/forged slug) to not_found, non-probeable (R1a.4)', async () => {
    server.use(http.get(FIELD_CONFIG_URL, () => new HttpResponse(null, { status: 404 })));
    const result = await fetchPublicFieldConfig('nope', { baseUrl: BASE });
    expect(result.status).toBe('not_found');
  });
});
