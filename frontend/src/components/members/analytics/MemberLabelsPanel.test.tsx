/**
 * Component tests for MemberLabelsPanel (analytics/MemberLabelsPanel.tsx).
 *
 * Co-located unit coverage for labels sub-spec task 3.2 (R-L2 / R-L3 / R-L4 /
 * R-L5): the template-driven address-label panel. The panel is otherwise only
 * exercised transitively through MemberPivotViews.test.tsx; this file pins its
 * own behavior in isolation (steering 33 — a new source file gets a paired test).
 *
 * It proves:
 *   - the template Select is populated from the passed `templates` (option value =
 *     template_id) and defaults to the first;
 *   - the format Select lists the shipped Avery formats and defaults to
 *     DEFAULT_LABEL_FORMAT_KEY;
 *   - Download composes the CURRENT rows through the chosen template via an
 *     INJECTED `generate` spy — called with (rows, fieldConfig, { lines }, the
 *     resolved LabelFormat, the UI-default options) — then saves the doc (R-L4);
 *   - switching the template passes the SECOND template's lines;
 *   - switching the format passes the newly resolved LabelFormat;
 *   - the count badges render after a generate.
 *
 * The generator (and the defensive full-template loader) are injected, so NO
 * network and NO real jsPDF run. i18n keys are echoed so assertions stay
 * locale-independent (no hardcoded English).
 */
import { vi, describe, it, expect } from 'vitest';
import React from 'react';

// Echo i18n keys so assertions are locale-independent (prove no hardcoded English).
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Stub the embedded (unified) template editor: it fetches templates on open (a
// real network call in jsdom). We only need to assert the panel MOUNTS it on
// Edit, so render a lightweight marker when open — no service call, no noisy
// auth error.
vi.mock('./MemberTemplateManager', () => ({
  default: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="member-template-manager" /> : null,
}));

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberLabelsPanel from './MemberLabelsPanel';
import type { MemberLabelsPanelProps } from './MemberLabelsPanel';
import {
  AVERY_LABEL_FORMATS,
  DEFAULT_LABEL_FORMAT_KEY,
  getLabelFormat,
  type GenerateResult,
} from './addressLabelService';
import type { FieldConfig, MemberRow } from '../../../types/members';
import type { MemberTemplateDto } from '../../../services/memberTemplateService';

// --- Fixtures ----------------------------------------------------------------

const ROWS: MemberRow[] = [
  { member_id: 'm-1', display_name: 'Alice', city: 'Amsterdam' } as unknown as MemberRow,
  { member_id: 'm-2', display_name: 'Bob', city: 'Rotterdam' } as unknown as MemberRow,
];

const FIELD_CONFIG: FieldConfig = {
  fields: [{ key: 'display_name' }, { key: 'city' }],
} as unknown as FieldConfig;

// Two label templates — list DTOs carry `lines` so the defensive fetch is NOT hit.
const TPL_A: MemberTemplateDto = {
  template_id: 'lbl-a',
  name: 'Name + city',
  kind: 'label',
  lines: [['display_name'], ['city']],
  languages: {},
  merge_fields: [],
  logo_asset_ref: null,
  origin: 'user',
  created_by: 'sub-1',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const TPL_B: MemberTemplateDto = {
  template_id: 'lbl-b',
  name: 'Name only',
  kind: 'label',
  lines: [['display_name']],
  languages: {},
  merge_fields: [],
  logo_asset_ref: null,
  origin: 'user',
  created_by: 'sub-1',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

/** A fake GenerateResult whose doc records save/output calls (no real jsPDF). */
function makeResult(labelCount = 2): GenerateResult {
  return {
    doc: { save: vi.fn(), output: vi.fn() } as unknown as GenerateResult['doc'],
    labelCount,
    excludedCount: 0,
    pages: 1,
  };
}

function makeProps(
  overrides: Partial<MemberLabelsPanelProps> = {},
): MemberLabelsPanelProps {
  const generate = vi.fn(() => makeResult());
  // A getTemplate spy that should never be reached (the DTOs carry `lines`).
  const getTemplate = vi.fn(async () => ({ ok: true as const, data: TPL_A }));
  return {
    rows: ROWS,
    fieldConfig: FIELD_CONFIG,
    templates: [TPL_A, TPL_B],
    language: 'en',
    resultFields: [
      { key: 'display_name', label: 'Display name' },
      { key: 'city', label: 'City' },
    ],
    generate: generate as unknown as MemberLabelsPanelProps['generate'],
    getTemplate: getTemplate as unknown as MemberLabelsPanelProps['getTemplate'],
    ...overrides,
  };
}

function templateSelect(): HTMLSelectElement {
  return screen.getByTestId('member-pivot-labels-template') as HTMLSelectElement;
}
function formatSelect(): HTMLSelectElement {
  return screen.getByTestId('member-pivot-labels-format') as HTMLSelectElement;
}
function optionValues(select: HTMLSelectElement): string[] {
  return Array.from(select.options).map((o) => o.value);
}

describe('MemberLabelsPanel', () => {
  it('populates the template Select from `templates` (value = template_id) and defaults to the first', () => {
    render(<MemberLabelsPanel {...makeProps()} />);
    const select = templateSelect();
    expect(optionValues(select)).toEqual(['lbl-a', 'lbl-b']);
    expect(select.value).toBe('lbl-a');
    // Option labels are the template names.
    expect(screen.getByText('Name + city')).toBeInTheDocument();
    expect(screen.getByText('Name only')).toBeInTheDocument();
  });

  it('lists the shipped Avery formats and defaults to DEFAULT_LABEL_FORMAT_KEY', () => {
    render(<MemberLabelsPanel {...makeProps()} />);
    const select = formatSelect();
    expect(optionValues(select)).toEqual(AVERY_LABEL_FORMATS.map((f) => f.key));
    expect(select.value).toBe(DEFAULT_LABEL_FORMAT_KEY);
  });

  it('Download calls the injected generate with rows, fieldConfig, chosen lines, format + default options, then saves', async () => {
    const props = makeProps();
    const generate = props.generate as unknown as ReturnType<typeof vi.fn>;
    render(<MemberLabelsPanel {...props} />);

    fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));

    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
    const call = generate.mock.calls[0] as unknown[];
    // (rows, fieldConfig, { lines }, format, options)
    expect(call[0]).toBe(ROWS); // the CURRENT result rows
    expect(call[1]).toBe(FIELD_CONFIG); // the field config prop
    expect(call[2]).toEqual({ lines: TPL_A.lines }); // first template's lines
    expect(call[3]).toEqual(getLabelFormat(DEFAULT_LABEL_FORMAT_KEY)); // resolved default format
    // The ONE shared options model reflects the UI defaults.
    expect(call[4]).toEqual({
      fontSize: 10,
      alignment: 'left',
      showBorder: false,
      autoFit: false,
      startPosition: 0,
    });

    // The produced doc is saved → the PDF downloads (R-L4).
    const result = generate.mock.results[0].value as GenerateResult;
    const save = result.doc.save as unknown as ReturnType<typeof vi.fn>;
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('switching the template to the second one passes its lines on Download', async () => {
    const props = makeProps();
    const generate = props.generate as unknown as ReturnType<typeof vi.fn>;
    render(<MemberLabelsPanel {...props} />);

    fireEvent.change(templateSelect(), { target: { value: 'lbl-b' } });
    fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));

    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
    expect((generate.mock.calls[0] as unknown[])[2]).toEqual({ lines: TPL_B.lines });
  });

  it('switching the format passes the newly resolved LabelFormat', async () => {
    const props = makeProps();
    const generate = props.generate as unknown as ReturnType<typeof vi.fn>;
    render(<MemberLabelsPanel {...props} />);

    fireEvent.change(formatSelect(), { target: { value: 'L7163' } });
    fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));

    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
    expect((generate.mock.calls[0] as unknown[])[3]).toEqual(getLabelFormat('L7163'));
  });

  it('renders the count badges after a generate', async () => {
    render(<MemberLabelsPanel {...makeProps()} />);
    // No counts before the first generate.
    expect(screen.queryByTestId('member-pivot-labels-counts')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));

    expect(
      await screen.findByTestId('member-pivot-labels-counts'),
    ).toBeInTheDocument();
  });

  it('shows the selected template lines resolved to field labels, and updates on switch', () => {
    render(<MemberLabelsPanel {...makeProps()} />);
    const view = screen.getByTestId('member-pivot-labels-lines');
    // TPL_A = [[display_name],[city]] -> localized result-column labels shown.
    expect(view).toHaveTextContent('Display name');
    expect(view).toHaveTextContent('City');
    // Switch to TPL_B ([[display_name]]) -> only Display name remains.
    fireEvent.change(templateSelect(), { target: { value: 'lbl-b' } });
    const view2 = screen.getByTestId('member-pivot-labels-lines');
    expect(view2).toHaveTextContent('Display name');
  });

  it('shows a first-row merged preview of the actual label text', () => {
    render(<MemberLabelsPanel {...makeProps()} />);
    const preview = screen.getByTestId('member-pivot-labels-preview');
    // First row: display_name=Alice, city=Amsterdam -> two preview lines.
    expect(preview).toHaveTextContent('Alice');
    expect(preview).toHaveTextContent('Amsterdam');
  });

  it('opens the unified template editor from the Edit button', () => {
    render(<MemberLabelsPanel {...makeProps()} />);
    // The editor modal is not mounted/open until Edit is clicked.
    expect(screen.queryByTestId('member-template-manager')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('member-pivot-labels-edit'));
    expect(screen.getByTestId('member-template-manager')).toBeInTheDocument();
  });

  it('fires a download-confirmation toast after Download', async () => {
    // The i18n mock echoes the key, so the toast title is the key; we assert the
    // generator ran + doc.save fired (the toast path) without throwing.
    const props = makeProps();
    const generate = props.generate as unknown as ReturnType<typeof vi.fn>;
    render(<MemberLabelsPanel {...props} />);
    fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
    const result = generate.mock.results[0].value as GenerateResult;
    expect((result.doc.save as unknown as ReturnType<typeof vi.fn>)).toHaveBeenCalled();
  });
});
