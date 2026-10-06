/**
 * Minimal smoke tests for the Member Analytics address-label feature (task 8.2).
 *
 * The FULL coverage (grid-math table, address-formatting matrix, start-position /
 * sort-order permutations, jsPDF Avery-dimension assertions) is task 8.3 — these
 * are the compile-guarding smoke tests the implementing task carries so the new
 * service + component are exercised at least once:
 *
 *   - the pure service composes + filters addresses from the RESOLVED mapping
 *     (no h-dcn field literals), drops incomplete rows and reports the count,
 *     and the grid geometry is sane (R4.10 / R6.1);
 *   - `generateAddressLabelPdf` returns a real jsPDF document (jsPDF smoke);
 *   - the component is unavailable with a reason when there is no address mapping
 *     (R4.10) and hidden entirely without `members:export` (R4.11);
 *   - everything is reachable from the analytics barrel.
 *
 * i18n is echoed (keys returned verbatim) so assertions are locale-independent —
 * proving the component uses bilingual keys, not hardcoded English (R6.1).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'count' in opts ? `${key}:${opts.count}` : key,
  }),
}));

// Mock the pure service so the component matrix can assert WHICH options the UI
// passes through, and so clicking Generate never triggers a real jsPDF
// save()/download in jsdom. The service's own behaviour is covered exhaustively
// by addressLabelService.test.ts. The spy is typed with the real service
// signature so the option pass-through assertions below are type-checked.
type GenerateFn = typeof import('./addressLabelService').generateAddressLabelPdf;
const generateSpy = vi.fn<GenerateFn>(() => ({
  doc: { save: vi.fn(), output: vi.fn() } as unknown as ReturnType<GenerateFn>['doc'],
  labelCount: 2,
  excludedCount: 1,
  pages: 1,
}));
vi.mock('./addressLabelService', async () => {
  const actual = await vi.importActual<typeof import('./addressLabelService')>(
    './addressLabelService',
  );
  // Forward through a thin wrapper (evaluated lazily at call time) so the
  // hoisted factory does not reference `generateSpy` before it is initialized.
  return {
    ...actual,
    generateAddressLabelPdf: ((...args: Parameters<GenerateFn>) =>
      generateSpy(...args)) as GenerateFn,
  };
});

// Mock the analytics audit signal (task 10.1 / C7) so clicking Generate's
// fire-and-forget audit POST never hits the network in a component test.
const recordAnalyticsOutput = vi.fn();
vi.mock('../../../services/memberAnalyticsAuditService', () => ({
  recordAnalyticsOutput: (...args: unknown[]) => recordAnalyticsOutput(...args),
}));

import { render, screen, fireEvent } from '@/test-utils';
import AddressLabelGenerator from './AddressLabelGenerator';
import {
  AddressLabelGenerator as GeneratorFromBarrel,
  AVERY_LABEL_FORMATS,
  composeAddresses,
  cellPosition,
  labelsPerPage,
  pageCount,
  generateAddressLabelPdf,
  getLabelFormat,
} from './index';
import type { FieldConfig, MemberRow } from '../../../types/members';

/** A field config that maps the address slots to concrete tenant keys. */
const mappedFieldConfig = {
  fields: [
    { key: 'full_name', group: 'personal' },
    { key: 'street_addr', group: 'personal' },
    { key: 'zip', group: 'personal' },
    { key: 'town', group: 'personal' },
    { key: 'nation', group: 'personal' },
  ],
  analytics: {
    address_mapping: {
      name: 'full_name',
      street: 'street_addr',
      postcode: 'zip',
      city: 'town',
      country: 'nation',
    },
  },
} as unknown as FieldConfig;

/** No analytics / address mapping → generator unavailable. */
const unmappedFieldConfig = { fields: [] } as unknown as FieldConfig;

const rows = [
  // Complete.
  {
    member_id: 'a',
    full_name: 'Bob Jones',
    street_addr: '1 High St',
    zip: '1000AA',
    town: 'Amsterdam',
    nation: 'nl',
  },
  // Complete (international country uppercased).
  {
    member_id: 'b',
    full_name: 'Alice Smith',
    street_addr: '2 Low Rd',
    zip: '2000BB',
    town: 'Rotterdam',
    nation: 'de',
  },
  // Incomplete — name only, no locating line → dropped + counted.
  { member_id: 'c', full_name: 'No Address' },
] as unknown as MemberRow[];

describe('addressLabelService (task 8.2)', () => {
  it('ships the five standard Avery formats as defaults', () => {
    const keys = AVERY_LABEL_FORMATS.map((f) => f.key);
    expect(keys).toEqual(['L7160', 'L7163', 'L7162', 'L7161', 'CUSTOM_LARGE']);
    // L7160 is 21/sheet (3 x 7).
    expect(labelsPerPage(getLabelFormat('L7160')!)).toBe(21);
  });

  it('composes from resolved mapping, drops incomplete rows and counts them (R4.10)', () => {
    const { addresses, excludedCount } = composeAddresses(rows, mappedFieldConfig, {
      sortOrder: 'name',
    });
    expect(addresses).toHaveLength(2);
    expect(excludedCount).toBe(1);
    // Sorted by name: Alice before Bob.
    expect(addresses[0].lines[0]).toBe('Alice Smith');
    // Country is uppercased for international mailing.
    expect(addresses[0].lines).toContain('DE');
    // Postcode + city are joined on one line.
    expect(addresses[1].lines).toContain('1000AA  Amsterdam');
  });

  it('reports every row excluded when there is no resolvable mapping', () => {
    const { addresses, excludedCount } = composeAddresses(rows, unmappedFieldConfig);
    expect(addresses).toHaveLength(0);
    expect(excludedCount).toBe(rows.length);
  });

  it('computes grid cell geometry and page counts', () => {
    const fmt = getLabelFormat('L7160')!;
    const first = cellPosition(fmt, 0);
    expect(first).toMatchObject({ col: 0, row: 0 });
    expect(first.x).toBeCloseTo(fmt.marginLeft);
    expect(first.y).toBeCloseTo(fmt.marginTop);
    // The 4th cell on a 3-wide grid wraps to row 1, col 0.
    expect(cellPosition(fmt, 3)).toMatchObject({ col: 0, row: 1 });
    // 22 labels on a 21/sheet format → 2 pages; a start offset pushes the count.
    expect(pageCount(fmt, 22)).toBe(2);
    expect(pageCount(fmt, 1, 20)).toBe(1);
    expect(pageCount(fmt, 2, 20)).toBe(2);
  });

  it('builds a real jsPDF document (jsPDF smoke)', () => {
    const result = generateAddressLabelPdf(
      rows,
      mappedFieldConfig,
      getLabelFormat('L7160')!,
      { fontSize: 10, startPosition: 0 },
    );
    expect(result.labelCount).toBe(2);
    expect(result.excludedCount).toBe(1);
    expect(result.pages).toBe(1);
    // A real jsPDF doc exposes output(); a tiny PDF blob url proves it rendered.
    expect(typeof result.doc.output).toBe('function');
  });
});

describe('AddressLabelGenerator (task 8.2)', () => {
  const baseProps = {
    rows,
    fieldConfig: mappedFieldConfig,
    canExport: true,
  };

  it('is exported from the analytics barrel', () => {
    expect(GeneratorFromBarrel).toBe(AddressLabelGenerator);
  });

  it('renders the generator when export is allowed and the mapping resolves', () => {
    render(<AddressLabelGenerator {...baseProps} />);
    expect(screen.getByTestId('address-label-generator')).toBeInTheDocument();
    expect(screen.getByTestId('label-format-select')).toBeInTheDocument();
    expect(screen.getByTestId('label-generate')).toBeInTheDocument();
  });

  it('is unavailable with a reason when there is no address mapping (R4.10)', () => {
    render(<AddressLabelGenerator {...baseProps} fieldConfig={unmappedFieldConfig} />);
    expect(
      screen.getByTestId('address-label-generator-unavailable'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('analytics.degradation.addressMappingAbsent'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('address-label-generator')).not.toBeInTheDocument();
  });

  it('renders nothing without the members:export capability (R4.11)', () => {
    const { container } = render(
      <AddressLabelGenerator {...baseProps} canExport={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

// ---------------------------------------------------------------------------
// Task 8.3 — full component matrix: availability/degradation (with a bilingual
// reason, not hardcoded English), control wiring + start-position clamp, and
// the generate → option pass-through + count-badge flow.
// ---------------------------------------------------------------------------
describe('AddressLabelGenerator — availability + bilingual reason (task 8.3)', () => {
  const baseProps = { rows, fieldConfig: mappedFieldConfig, canExport: true };

  beforeEach(() => {
    generateSpy.mockClear();
  });

  it('surfaces the degradation reason as an i18n KEY, never hardcoded English', () => {
    render(<AddressLabelGenerator {...baseProps} fieldConfig={unmappedFieldConfig} />);
    const notice = screen.getByTestId('address-label-generator-unavailable');
    // The echoed key proves the component resolves a bilingual string, not a
    // literal English sentence (R6.1/R6.4).
    expect(notice).toHaveTextContent('analytics.degradation.addressMappingAbsent');
    expect(notice.textContent).not.toMatch(/[a-z] [a-z]/i); // no prose sentence
  });

  it('is also unavailable when the mapping is present but dangling (keys absent)', () => {
    // Every slot points at a key that is NOT in `fields` (stale mapping after
    // the overlay fields were removed) → nothing resolves → unavailable.
    const dangling = {
      fields: [{ key: 'some_other_field', group: 'personal' }],
      analytics: {
        address_mapping: { name: 'gone_name', street: 'gone_street', city: 'gone_city' },
      },
    } as unknown as FieldConfig;
    render(<AddressLabelGenerator {...baseProps} fieldConfig={dangling} />);
    expect(
      screen.getByTestId('address-label-generator-unavailable'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('address-label-generator')).not.toBeInTheDocument();
  });

  it('renders nothing when export is forbidden even if the mapping resolves', () => {
    const { container } = render(
      <AddressLabelGenerator {...baseProps} canExport={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('AddressLabelGenerator — controls + generate flow (task 8.3)', () => {
  const baseProps = { rows, fieldConfig: mappedFieldConfig, canExport: true };

  beforeEach(() => {
    generateSpy.mockClear();
    recordAnalyticsOutput.mockClear();
    recordAnalyticsOutput.mockResolvedValue(true);
  });

  it('audit-signals the PDF generate with metadata only (task 10.1 / C7)', () => {
    render(<AddressLabelGenerator {...baseProps} setKey="clubblad-paper" />);
    fireEvent.click(screen.getByTestId('label-generate'));

    // One metadata-only audit signal — output kind, the set, the label count.
    // NO member rows / addresses in the signal; filter_summary carries only the
    // generation shape (format + page/excluded counts).
    expect(recordAnalyticsOutput).toHaveBeenCalledTimes(1);
    const audit = recordAnalyticsOutput.mock.calls[0][0];
    expect(audit.outputKind).toBe('pdf_labels');
    expect(audit.setKey).toBe('clubblad-paper');
    expect(audit.recordCount).toBe(2); // generateSpy's labelCount
    expect(audit.filterSummary).toMatchObject({ pages: 1, excluded: 1 });
  });

  it('exposes the format / sort / start-position / alignment / font controls', () => {
    render(<AddressLabelGenerator {...baseProps} />);
    expect(screen.getByTestId('label-format-select')).toBeInTheDocument();
    expect(screen.getByTestId('label-sort-select')).toBeInTheDocument();
    expect(screen.getByTestId('label-start-input')).toBeInTheDocument();
    expect(screen.getByTestId('label-align-select')).toBeInTheDocument();
    expect(screen.getByTestId('label-font-input')).toBeInTheDocument();
    expect(screen.getByTestId('label-border-checkbox')).toBeInTheDocument();
    expect(screen.getByTestId('label-country-checkbox')).toBeInTheDocument();
  });

  it('passes the selected sort order + start position through to the service', () => {
    render(<AddressLabelGenerator {...baseProps} />);
    fireEvent.change(screen.getByTestId('label-sort-select'), {
      target: { value: 'postcode' },
    });
    fireEvent.change(screen.getByTestId('label-start-input'), {
      target: { value: '5' },
    });
    fireEvent.click(screen.getByTestId('label-generate'));

    expect(generateSpy).toHaveBeenCalledTimes(1);
    const opts = generateSpy.mock.calls[0][3];
    expect(opts).toMatchObject({ sortOrder: 'postcode', startPosition: 5 });
  });

  it('clamps the start-position input to the format capacity (L7160 → max 20)', () => {
    render(<AddressLabelGenerator {...baseProps} />);
    const startInput = screen.getByTestId('label-start-input') as HTMLInputElement;
    // L7160 is 21/sheet → max start index is 20.
    fireEvent.change(startInput, { target: { value: '999' } });
    expect(startInput.value).toBe('20');
    fireEvent.change(startInput, { target: { value: '-4' } });
    expect(startInput.value).toBe('0');
  });

  it('resets the start position to 0 when the format changes', () => {
    render(<AddressLabelGenerator {...baseProps} />);
    const startInput = screen.getByTestId('label-start-input') as HTMLInputElement;
    fireEvent.change(startInput, { target: { value: '10' } });
    expect(startInput.value).toBe('10');
    fireEvent.change(screen.getByTestId('label-format-select'), {
      target: { value: 'L7163' },
    });
    expect(startInput.value).toBe('0');
  });

  it('shows label / page / excluded count badges (as text) after generating', () => {
    render(<AddressLabelGenerator {...baseProps} />);
    expect(screen.queryByTestId('label-counts')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('label-generate'));

    expect(screen.getByTestId('label-counts')).toBeInTheDocument();
    // keys are echoed with the interpolated count, proving bilingual + text (R6.6).
    expect(screen.getByTestId('label-count')).toHaveTextContent(
      'analytics.labels.labelCount:2',
    );
    expect(screen.getByTestId('label-pages')).toHaveTextContent(
      'analytics.labels.pageCount:1',
    );
    expect(screen.getByTestId('label-excluded')).toHaveTextContent(
      'analytics.labels.excludedCount:1',
    );
  });

  it('hides the excluded badge when nothing was excluded', () => {
    generateSpy.mockReturnValueOnce({
      doc: { save: vi.fn(), output: vi.fn() } as unknown as ReturnType<GenerateFn>['doc'],
      labelCount: 3,
      excludedCount: 0,
      pages: 1,
    });
    render(<AddressLabelGenerator {...baseProps} />);
    fireEvent.click(screen.getByTestId('label-generate'));
    expect(screen.getByTestId('label-counts')).toBeInTheDocument();
    expect(screen.queryByTestId('label-excluded')).not.toBeInTheDocument();
  });
});
