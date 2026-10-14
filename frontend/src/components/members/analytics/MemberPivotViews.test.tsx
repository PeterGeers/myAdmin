/**
 * Component tests for MemberPivotViews (analytics/MemberPivotViews.tsx).
 *
 * Post role-removal contract: there are NO predefined presets and NO
 * jubilee / joined-after year selectors. Every runnable "set" is a tenant-saved
 * analytics set (the Members module's own `/members/analytics-sets` DynamoDB
 * CRUD, F-012). This suite verifies:
 *   - the set dropdown lists ONLY the user's preferred SAVED sets (R4.6/R5.2);
 *   - the EMPTY PIVOT VIEWS ENTRY POINT: with no saved sets, the panel renders
 *     the shared `AnalyticsStateNotice` empty-hint + the MemberFieldPicker
 *     "New set" CTA (no dead dropdown, no new component);
 *   - NOTHING runs until the user explicitly clicks Execute (R1.6 — no auto-run);
 *   - on Execute the chosen saved set's config is loaded via `getAnalyticsSet`,
 *     its own definition filters applied generically (`applyDefinitionFilters`),
 *     the client adapter runs over `processedData`, and the result renders
 *     through the reused `PivotResultTable` (R4.1/R4.7/R4.4a);
 *   - the CSV / mail / template-label export slot, the save lifecycle, the
 *     preferred-list + "All sets" library, schedule, and deliver-now flows — all
 *     the GENERIC analytics-SET surface — are unchanged, driven by saved sets.
 *
 * `membersApiService` is mocked so no network is hit; `PivotResultTable` is
 * mocked with a lightweight recorder. i18n keys are echoed so assertions are
 * locale-independent and prove no hardcoded English.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import type { PivotConfig, PivotColumnMeta } from '../../../types/pivot';
import type { MemberRow } from '../../../types/members';

// --- Mock the Members API service (R4.6/R5.2 listing + loading + lifecycle). --
const listAnalyticsSets = vi.fn();
const getAnalyticsSet = vi.fn();
const saveAnalyticsSet = vi.fn();
const updateAnalyticsSet = vi.fn();
const deleteAnalyticsSet = vi.fn();
const getPreferredList = vi.fn();
const savePreferredList = vi.fn();
const putAnalyticsSetDelivery = vi.fn();
const deleteAnalyticsSetDelivery = vi.fn();
const deliverAnalyticsSet = vi.fn();
const listSchedulesForSet = vi.fn();
const createSchedule = vi.fn();
const updateSchedule = vi.fn();
const deleteSchedule = vi.fn();
const sendAdHocMail = vi.fn();
vi.mock('../../../services/membersApiService', () => ({
  listAnalyticsSets: (...args: unknown[]) => listAnalyticsSets(...args),
  getAnalyticsSet: (...args: unknown[]) => getAnalyticsSet(...args),
  saveAnalyticsSet: (...args: unknown[]) => saveAnalyticsSet(...args),
  updateAnalyticsSet: (...args: unknown[]) => updateAnalyticsSet(...args),
  deleteAnalyticsSet: (...args: unknown[]) => deleteAnalyticsSet(...args),
  getPreferredList: (...args: unknown[]) => getPreferredList(...args),
  savePreferredList: (...args: unknown[]) => savePreferredList(...args),
  putAnalyticsSetDelivery: (...args: unknown[]) => putAnalyticsSetDelivery(...args),
  deleteAnalyticsSetDelivery: (...args: unknown[]) => deleteAnalyticsSetDelivery(...args),
  deliverAnalyticsSet: (...args: unknown[]) => deliverAnalyticsSet(...args),
  sendAdHocMail: (...args: unknown[]) => sendAdHocMail(...args),
  listSchedulesForSet: (...args: unknown[]) => listSchedulesForSet(...args),
  createSchedule: (...args: unknown[]) => createSchedule(...args),
  updateSchedule: (...args: unknown[]) => updateSchedule(...args),
  deleteSchedule: (...args: unknown[]) => deleteSchedule(...args),
  SCHEDULE_CADENCES: ['monthly', 'weekly'],
  cronToCadence: (cron: string) =>
    cron === 'cron(0 8 ? * MON *)' ? 'weekly' : 'monthly',
}));

// --- Mock the reused PivotResultTable with a lightweight recorder. ------------
const tableCalls: Array<{
  data: Record<string, unknown>[];
  columns: PivotColumnMeta[];
  config: PivotConfig;
  onVisibleRowsChange?: (rows: Record<string, unknown>[]) => void;
  columnLabels?: Record<string, string>;
}> = [];
vi.mock('../../pivot/PivotResultTable', () => ({
  default: function MockPivotResultTable(props: {
    data: Record<string, unknown>[];
    columns: PivotColumnMeta[];
    config: PivotConfig;
    onVisibleRowsChange?: (rows: Record<string, unknown>[]) => void;
    columnLabels?: Record<string, string>;
  }) {
    tableCalls.push({
      data: props.data,
      columns: props.columns,
      config: props.config,
      onVisibleRowsChange: props.onVisibleRowsChange,
      columnLabels: props.columnLabels,
    });
    return (
      <div
        data-testid="mock-pivot-result-table"
        data-row-count={props.data.length}
        data-group-columns={props.config.groupColumns.join(',')}
      >
        <button
          type="button"
          data-testid="mock-table-filter-to-first-row"
          onClick={() => props.onVisibleRowsChange?.(props.data.slice(0, 1))}
        />
      </div>
    );
  },
}));

// --- Mock the reused CSV util (reuse csvExport.ts, don't reimplement). --------
const generateCsvFromObjects = vi.fn();
const downloadCsv = vi.fn();
vi.mock('../../../utils/csvExport', () => ({
  generateCsvFromObjects: (...args: unknown[]) => generateCsvFromObjects(...args),
  downloadCsv: (...args: unknown[]) => downloadCsv(...args),
}));

// --- Mock the analytics audit signal so the CSV export's fire-and-forget audit
// POST never hits the network in a component test. --------------------------
const recordAnalyticsOutput = vi.fn();
vi.mock('../../../services/memberAnalyticsAuditService', () => ({
  recordAnalyticsOutput: (...args: unknown[]) => recordAnalyticsOutput(...args),
}));

// --- Mock ONLY the template-label generator export of addressLabelService
// (spread the real module so the Avery format catalogue stays intact), so a
// labels test proves the modal composes the CURRENT result rows through the
// CHOSEN template + Avery format and `result.doc.save` fires the download. --
const generateLabelTemplatePdf = vi.fn();
vi.mock('./addressLabelService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('./addressLabelService')>();
  return {
    ...actual,
    generateLabelTemplatePdf: (...args: unknown[]) =>
      generateLabelTemplatePdf(...args),
  };
});

// --- Mock the member template service (labels gate loader). ------------------
const listMemberTemplates = vi.fn();
vi.mock('../../../services/memberTemplateService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../../services/memberTemplateService')>();
  return {
    ...actual,
    listMemberTemplates: (...args: unknown[]) => listMemberTemplates(...args),
  };
});

// Echo i18n keys so assertions are locale-independent (no hardcoded English).
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

import { render, screen, fireEvent, waitFor, within } from '@/test-utils';
import MemberPivotViews from './MemberPivotViews';
import { MemberPivotViews as FromBarrel } from './index';
import type { FieldConfig } from '../../../types/members';
import type { MemberAnalyticsAreaProps, MemberAnalyticsCapabilities } from './areas/types';

/**
 * A field config exposing the keys the saved sets group/filter on, with NO
 * analytics role-config block (that machinery was removed). Mail-enabled by
 * default so the mail/compose tests exercise the capability gate, not the mail
 * gate (the mail-gate hidden paths are covered in their own describe block).
 */
const fieldConfig = {
  fields: [
    { key: 'membership_type', origin: 'fixed', label: { en: 'Type' } },
    { key: 'birth_month', origin: 'calculated', label: { en: 'Birth month' } },
    { key: 'years_member', origin: 'calculated', label: { en: 'Years-member' } },
    { key: 'joined_date', origin: 'fixed', label: { en: 'Joined' } },
    { key: 'country', origin: 'fixed', label: { en: 'Country' } },
  ],
  mail_enabled: true,
} as unknown as FieldConfig;

const processedData = [
  { member_id: 'a', membership_type: 'Gold' },
  { member_id: 'b', membership_type: 'Gold' },
  { member_id: 'c', membership_type: 'Silver' },
] as unknown as MemberRow[];

// ---------------------------------------------------------------------------
// Shared saved sets used as the test vehicle (there are no presets anymore).
// ---------------------------------------------------------------------------

/** A COUNT-by-membership_type AGGREGATE saved set (the everyday vehicle). */
const AGG_SET_SUMMARY = { id: 'set-agg', name: 'Members by type', kind: 'count' as const };
const AGG_SET_CONFIG: PivotConfig = {
  dataSource: 'members',
  groupColumns: ['membership_type'],
  aggregateMeasures: [{ function: 'COUNT', column: '*' }],
  filters: {},
  columnPivot: null,
  columnNestLevels: [],
  displayMode: 'flat',
};
const AGG_SET = {
  ...AGG_SET_SUMMARY,
  definition: AGG_SET_CONFIG,
  created_at: '',
  updated_at: '',
};

function makeProps(
  overrides: Partial<MemberAnalyticsAreaProps> = {},
): MemberAnalyticsAreaProps {
  return {
    processedData,
    members: processedData as never,
    fieldConfig,
    language: 'en',
    // Default to a fully set-management-capable caller so the lifecycle + manage
    // tests see the New set / Save as / Update actions (R11 gates these on
    // export|write / write|admin). Tests asserting ABSENCE pass an explicit
    // `capabilities` override.
    capabilities: { canExport: true, canWrite: true, isAdmin: true },
    ...overrides,
  };
}

/** Open the "All sets" library modal and wait for it to mount. */
async function openLibrary() {
  fireEvent.click(screen.getByTestId('member-pivot-open-library'));
  await screen.findByTestId('member-pivot-library-modal');
}

/**
 * Seed the aggregate saved set as the ONLY saved set + preferred so it is the
 * selectable dropdown option, then select it and Execute → an aggregate result.
 */
async function executeAggregate() {
  await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
  await waitFor(() => {
    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(values).toContain('model:set-agg');
  });
  fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
    target: { value: 'model:set-agg' },
  });
  fireEvent.click(screen.getByTestId('member-pivot-execute'));
  await screen.findByTestId('mock-pivot-result-table');
}

beforeEach(() => {
  tableCalls.length = 0;
  listAnalyticsSets.mockReset();
  getAnalyticsSet.mockReset();
  saveAnalyticsSet.mockReset();
  updateAnalyticsSet.mockReset();
  deleteAnalyticsSet.mockReset();
  // Default: the aggregate set is the one saved set, preferred (selectable).
  listAnalyticsSets.mockResolvedValue([AGG_SET_SUMMARY]);
  getAnalyticsSet.mockResolvedValue(AGG_SET);
  saveAnalyticsSet.mockResolvedValue({
    id: 'set-99', name: 'saved', kind: 'count', definition: {}, created_at: '', updated_at: '',
  });
  updateAnalyticsSet.mockResolvedValue({
    id: 'set-agg', name: 'updated', kind: 'count', definition: {}, created_at: '', updated_at: '',
  });
  deleteAnalyticsSet.mockResolvedValue(undefined);
  getPreferredList.mockReset();
  savePreferredList.mockReset();
  // Default: the aggregate set is preferred so it is a selectable dropdown option.
  getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-agg'], updated_at: '' });
  savePreferredList.mockImplementation(async (refs: string[]) => ({
    sub: 'u1',
    refs,
    updated_at: '2026-01-01T00:00:00Z',
  }));
  generateCsvFromObjects.mockReset();
  downloadCsv.mockReset();
  generateCsvFromObjects.mockReturnValue('col\nval');
  recordAnalyticsOutput.mockReset();
  recordAnalyticsOutput.mockResolvedValue(true);
  generateLabelTemplatePdf.mockReset();
  generateLabelTemplatePdf.mockReturnValue({
    doc: { save: vi.fn(), output: vi.fn().mockReturnValue('blob:labels') },
    labelCount: 3,
    excludedCount: 0,
    pages: 1,
  });
  listMemberTemplates.mockReset();
  listMemberTemplates.mockResolvedValue({ ok: true, data: [] });
  putAnalyticsSetDelivery.mockReset();
  deleteAnalyticsSetDelivery.mockReset();
  deliverAnalyticsSet.mockReset();
  sendAdHocMail.mockReset();
  sendAdHocMail.mockResolvedValue({ runId: 'run-1', mode: 'to_fixed', enqueued: 1, skippedNoAddress: 0, jobIds: ['job-1'] });
  deliverAnalyticsSet.mockResolvedValue({
    runId: 'run-1', mode: 'to_fixed', enqueued: 1, skippedNoAddress: 0, jobIds: ['job-1'],
  });
  listSchedulesForSet.mockReset();
  createSchedule.mockReset();
  updateSchedule.mockReset();
  deleteSchedule.mockReset();
  listSchedulesForSet.mockResolvedValue([]);
  createSchedule.mockResolvedValue(undefined);
  updateSchedule.mockResolvedValue(undefined);
  deleteSchedule.mockResolvedValue(undefined);
});

describe('MemberPivotViews', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberPivotViews);
  });

  it('the dropdown lists ONLY the user preferred SAVED sets (no presets)', async () => {
    listAnalyticsSets.mockResolvedValue([
      AGG_SET_SUMMARY,
      { id: 'set-other', name: 'Other set', kind: 'list' },
    ]);
    // Only the aggregate set is preferred → only it is in the dropdown.
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-agg'], updated_at: '' });
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    await waitFor(() => {
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('model:set-agg');
    });
    const optionValues = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    // Only the preferred saved set is offered; the non-preferred one is not.
    expect(optionValues).toContain('model:set-agg');
    expect(optionValues).not.toContain('model:set-other');
    // No predefined preset options exist at all.
    expect(optionValues.some((v) => v.startsWith('preset:'))).toBe(false);
  });

  it('the FULL library (every saved set) is reachable via the "All sets" modal', async () => {
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-1', name: 'Paper clubblad', kind: 'list' },
      { id: 'set-3', name: 'Active seniors', kind: 'count' },
    ]);

    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    // The dropdown lists none of them (none preferred).
    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    const dropdownValues = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(dropdownValues).not.toContain('model:set-1');
    expect(dropdownValues).not.toContain('model:set-3');

    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    const libraryLabels = screen
      .getAllByTestId('member-pivot-library-item')
      .map((el) => el.textContent ?? '');
    // Every saved set appears in the library (user-authored names, shown as-is).
    expect(libraryLabels.some((l) => l.includes('Paper clubblad'))).toBe(true);
    expect(libraryLabels.some((l) => l.includes('Active seniors'))).toBe(true);
    // No predefined preset names appear.
    expect(libraryLabels.some((l) => l.includes('presetNames'))).toBe(false);
  });

  it('runs NOTHING until Execute is clicked (R1.6 — no auto-run on selection)', async () => {
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('model:set-agg');
    });

    expect(screen.queryByTestId('mock-pivot-result-table')).not.toBeInTheDocument();
    expect(tableCalls).toHaveLength(0);

    // Selecting a set alone runs nothing (no auto-run).
    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'model:set-agg' },
    });
    expect(screen.queryByTestId('mock-pivot-result-table')).not.toBeInTheDocument();
    expect(tableCalls).toHaveLength(0);

    expect(screen.getByTestId('member-pivot-execute')).not.toBeDisabled();
  });

  it('Execute loads a saved set and renders the aggregate result table (R4.1/R4.7)', async () => {
    render(<MemberPivotViews {...makeProps()} />);
    await executeAggregate();

    const table = screen.getByTestId('mock-pivot-result-table');
    expect(table).toBeInTheDocument();
    expect(tableCalls).toHaveLength(1);
    // The set groups by membership_type over processedData: two groups (Gold, Silver).
    expect(table).toHaveAttribute('data-group-columns', 'membership_type');
    expect(table).toHaveAttribute('data-row-count', '2');
    // The full definition is loaded via getAnalyticsSet on Execute.
    expect(getAnalyticsSet).toHaveBeenCalledWith('set-agg');
  });

  it('Execute loads a filtered-LIST saved set and runs it over processedData (R4.4a)', async () => {
    const listSummary = { id: 'set-7', name: 'Paper clubblad', kind: 'list' as const };
    const savedConfig: PivotConfig = {
      dataSource: 'members',
      groupColumns: [],
      aggregateMeasures: [],
      filters: {},
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'flat',
    };
    listAnalyticsSets.mockResolvedValue([listSummary]);
    getAnalyticsSet.mockResolvedValue({ ...listSummary, definition: savedConfig, created_at: '', updated_at: '' });
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-7'], updated_at: '' });

    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('model:set-7');
    });

    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'model:set-7' },
    });
    fireEvent.click(screen.getByTestId('member-pivot-execute'));

    const table = await screen.findByTestId('mock-pivot-result-table');
    expect(getAnalyticsSet).toHaveBeenCalledWith('set-7');
    // Filtered-list mode: adapter handed processedData as-is (R4.4a) → one row per member.
    expect(table).toHaveAttribute('data-row-count', String(processedData.length));
    expect(tableCalls[0].config).toEqual(savedConfig);
  });

  it("applies a saved set's generic DEFINITION filter at execute (issue 3)", async () => {
    const paperRows = [
      { member_id: 'a', clubblad: 'Papier' },
      { member_id: 'b', clubblad: 'Digitaal' },
      { member_id: 'c', clubblad: 'papier' }, // case-insensitive match
    ] as unknown as MemberRow[];
    const paperConfig: PivotConfig = {
      dataSource: 'members',
      groupColumns: [],
      aggregateMeasures: [],
      filters: { clubblad: 'Papier' },
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'flat',
    };
    const listSummary = { id: 'set-9', name: 'Clubblad paper', kind: 'list' as const };
    listAnalyticsSets.mockResolvedValue([listSummary]);
    getAnalyticsSet.mockResolvedValue({ ...listSummary, definition: paperConfig, created_at: '', updated_at: '' });
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-9'], updated_at: '' });

    render(
      <MemberPivotViews {...makeProps({ processedData: paperRows, members: paperRows as never })} />,
    );
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('model:set-9');
    });

    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'model:set-9' },
    });
    fireEvent.click(screen.getByTestId('member-pivot-execute'));

    const table = await screen.findByTestId('mock-pivot-result-table');
    // Only the two 'Papier'/'papier' members survive the generic equality filter.
    expect(table).toHaveAttribute('data-row-count', '2');
  });

  it('degrades to no saved sets when the saved-set fetch fails (never crashes)', async () => {
    listAnalyticsSets.mockRejectedValue(new Error('network'));
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    // No options survive the failed fetch; the empty-state hint is shown instead.
    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    const optionValues = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(optionValues.some((v) => v.startsWith('model:'))).toBe(false);
    expect(await screen.findByTestId('member-pivot-empty-hint')).toBeInTheDocument();
  });

  it('uses the bilingual i18n keys for the controls (no hardcoded English)', async () => {
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    expect(screen.getByText('analytics.pivotViews.selectSet')).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-execute')).toHaveTextContent(
      'analytics.pivotViews.execute',
    );
  });

  // --- Empty Pivot Views entry point (bugfix §3, design Step A.1). -----------
  describe('empty-state entry point (no saved sets)', () => {
    beforeEach(() => {
      listAnalyticsSets.mockResolvedValue([]);
      getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    });

    it('renders the shared empty-hint notice when there are no saved sets', async () => {
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      const hint = await screen.findByTestId('member-pivot-empty-hint');
      expect(hint).toBeInTheDocument();
      // It reuses the shared AnalyticsStateNotice in its neutral EMPTY variant
      // (a status, not an alert/degradation) with the bilingual hint message.
      const notice = screen.getByTestId('member-pivot-empty-hint-notice');
      expect(notice).toHaveAttribute('role', 'status');
      expect(notice).toHaveAttribute('data-notice-kind', 'empty');
      expect(notice).toHaveTextContent('analytics.pivotViews.emptyHint.message');
    });

    it('offers the New set button as the single CTA (opens the field picker)', async () => {
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      const cta = await screen.findByTestId('member-pivot-empty-hint-new-set');
      expect(cta).toHaveTextContent('analytics.pivotViews.newSet');
      expect(screen.queryByTestId('member-field-picker')).not.toBeInTheDocument();
      fireEvent.click(cta);
      expect(await screen.findByTestId('member-field-picker')).toBeInTheDocument();
    });

    it('hides the New set CTA for a read-only caller (cannot create a set)', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      // The hint still shows (discoverability), but no create CTA for read-only.
      expect(await screen.findByTestId('member-pivot-empty-hint')).toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-empty-hint-new-set')).not.toBeInTheDocument();
    });

    it('shows no empty-hint once the tenant has a saved set', async () => {
      listAnalyticsSets.mockResolvedValue([AGG_SET_SUMMARY]);
      getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-agg'], updated_at: '' });
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('model:set-agg');
      });
      expect(screen.queryByTestId('member-pivot-empty-hint')).not.toBeInTheDocument();
    });
  });

  // --- CSV export of a produced result (R4.9/R4.11). -------------------------
  describe('CSV export (R4.9/R4.11)', () => {
    it('does NOT render the export slot or CSV button without canExport (members:export)', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
      await executeAggregate();

      expect(screen.queryByTestId('pivot-result-actions')).not.toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-export-csv')).not.toBeInTheDocument();
    });

    it('renders the CSV button in the result-actions slot only when canExport', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      expect(screen.queryByTestId('member-pivot-export-csv')).not.toBeInTheDocument();

      await executeAggregate();

      expect(screen.getByTestId('pivot-result-actions')).toBeInTheDocument();
      const csvButton = screen.getByTestId('member-pivot-export-csv');
      expect(csvButton).toBeInTheDocument();
      expect(csvButton).toHaveTextContent('analytics.export.csv');
    });

    it('exports an AGGREGATE result: csvExport gets the result columns + rows', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();

      const produced = tableCalls[tableCalls.length - 1];

      fireEvent.click(screen.getByTestId('member-pivot-export-csv'));
      fireEvent.click(screen.getByTestId('member-pivot-export-csv-download'));

      expect(generateCsvFromObjects).toHaveBeenCalledTimes(1);
      const [columns, rows] = generateCsvFromObjects.mock.calls[0];
      const labels = (produced as unknown as { columnLabels?: Record<string, string> })
        .columnLabels ?? {};
      // CSV column KEY = raw result column name; HEADER = localized label.
      expect(columns).toEqual(
        produced.columns.map((c) => ({ key: c.name, header: labels[c.name] ?? c.name })),
      );
      expect(labels['membership_type']).toBeDefined();
      expect(columns[0]).toEqual({ key: 'membership_type', header: labels['membership_type'] });
      expect(rows).toBe(produced.data);
      expect(downloadCsv).toHaveBeenCalledTimes(1);
      expect(downloadCsv.mock.calls[0][0]).toBe('col\nval');

      expect(recordAnalyticsOutput).toHaveBeenCalledTimes(1);
      const audit = recordAnalyticsOutput.mock.calls[0][0];
      expect(audit.outputKind).toBe('csv_export');
      expect(audit.recordCount).toBe(produced.data.length);
      expect(audit.filterSummary).toEqual({ columns: produced.columns.length });
    });

    it('exports a filtered-LIST result too (R4.11): one row per member', async () => {
      const listSummary = { id: 'set-7', name: 'Paper clubblad', kind: 'list' as const };
      const listConfig: PivotConfig = {
        dataSource: 'members',
        groupColumns: [],
        aggregateMeasures: [],
        filters: {},
        columnPivot: null,
        columnNestLevels: [],
        displayMode: 'flat',
      };
      listAnalyticsSets.mockResolvedValue([listSummary]);
      getAnalyticsSet.mockResolvedValue({ ...listSummary, definition: listConfig, created_at: '', updated_at: '' });
      getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-7'], updated_at: '' });

      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('model:set-7');
      });
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'model:set-7' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));
      await screen.findByTestId('mock-pivot-result-table');

      const produced = tableCalls[tableCalls.length - 1];
      expect(produced.data).toHaveLength(processedData.length);

      fireEvent.click(screen.getByTestId('member-pivot-export-csv'));
      fireEvent.click(screen.getByTestId('member-pivot-export-csv-download'));

      expect(generateCsvFromObjects).toHaveBeenCalledTimes(1);
      const [columns, rows] = generateCsvFromObjects.mock.calls[0];
      const listLabels = (produced as unknown as { columnLabels?: Record<string, string> })
        .columnLabels ?? {};
      expect(columns).toEqual(
        produced.columns.map((c) => ({ key: c.name, header: listLabels[c.name] ?? c.name })),
      );
      expect(rows).toBe(produced.data);
      expect(downloadCsv).toHaveBeenCalledTimes(1);
    });

    it('exports ONLY the table-filtered subset, not the full result', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();

      const produced = tableCalls[tableCalls.length - 1];
      expect(produced.data.length).toBeGreaterThan(1);

      fireEvent.click(screen.getByTestId('mock-table-filter-to-first-row'));

      fireEvent.click(screen.getByTestId('member-pivot-export-csv'));
      fireEvent.click(screen.getByTestId('member-pivot-export-csv-download'));

      expect(generateCsvFromObjects).toHaveBeenCalledTimes(1);
      const [, rows] = generateCsvFromObjects.mock.calls[0];
      expect(rows).toHaveLength(1);
      expect(rows).toEqual(produced.data.slice(0, 1));

      const audit = recordAnalyticsOutput.mock.calls[0][0];
      expect(audit.recordCount).toBe(1);
    });

    it('falls back to the full result when the table reports no filtered rows', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();
      const produced = tableCalls[tableCalls.length - 1];

      fireEvent.click(screen.getByTestId('member-pivot-export-csv'));
      fireEvent.click(screen.getByTestId('member-pivot-export-csv-download'));
      const [, rows] = generateCsvFromObjects.mock.calls[0];
      expect(rows).toBe(produced.data);
    });
  });

  // --- save / save-as / update / delete lifecycle (R4.4/R4.4a/R4.4b). --------
  describe('save lifecycle (R4.4/R4.4a/R4.4b)', () => {
    const savedModel = { id: 'set-7', name: 'Paper clubblad', kind: 'count' as const };
    const savedConfig: PivotConfig = {
      dataSource: 'members',
      groupColumns: ['membership_type'],
      aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      filters: { clubblad: 'Papier' },
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'flat',
    };

    it('Update does nothing until a SAVED model is selected', async () => {
      listAnalyticsSets.mockResolvedValue([]);
      getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      // New set is always available; Update needs a selected saved model.
      fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
      expect(screen.getByTestId('member-pivot-new-set')).toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-delete')).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId('member-pivot-update'));
      expect(screen.queryByTestId('member-field-picker')).not.toBeInTheDocument();
      expect(updateAnalyticsSet).not.toHaveBeenCalled();
    });

    it('New set opens the picker to compose + save a brand-new set (R4.4)', async () => {
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
      fireEvent.click(screen.getByTestId('member-pivot-new-set'));

      expect(await screen.findByTestId('member-field-picker')).toBeInTheDocument();
      expect(screen.queryByTestId('field-picker-seeded')).not.toBeInTheDocument();

      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'My new set' },
      });
      fireEvent.click(screen.getByTestId('field-picker-group-membership_type'));
      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(saveAnalyticsSet).toHaveBeenCalledTimes(1));
      const [name, config] = saveAnalyticsSet.mock.calls[0];
      expect(name).toBe('My new set');
      expect(config.dataSource).toBe('members');
      expect(updateAnalyticsSet).not.toHaveBeenCalled();
    });

    it('Update edits the selected saved set in place via updateAnalyticsSet (R4.4)', async () => {
      listAnalyticsSets.mockResolvedValue([savedModel]);
      getAnalyticsSet.mockResolvedValue({ ...savedModel, definition: savedConfig, updated_at: '' });
      getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-7'], updated_at: '' });

      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('model:set-7');
      });

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'model:set-7' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
      fireEvent.click(screen.getByTestId('member-pivot-update'));

      await waitFor(() => expect(getAnalyticsSet).toHaveBeenCalledWith('set-7'));
      await waitFor(() =>
        expect(screen.getByTestId('field-picker-name')).toHaveValue('Paper clubblad'),
      );

      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(updateAnalyticsSet).toHaveBeenCalledTimes(1));
      const [id, , config] = updateAnalyticsSet.mock.calls[0];
      expect(id).toBe('set-7');
      // The set's own definition filters travel with the update (R4.4).
      expect(config.filters).toEqual({ clubblad: 'Papier' });
      await waitFor(() => expect(listAnalyticsSets.mock.calls.length).toBeGreaterThanOrEqual(2));
    });

    it('Save-as saves the selected saved set as a NEW set, keeping its filters (R4.4)', async () => {
      listAnalyticsSets.mockResolvedValue([savedModel]);
      getAnalyticsSet.mockResolvedValue({ ...savedModel, definition: savedConfig, created_at: '', updated_at: '' });
      getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-7'], updated_at: '' });

      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('model:set-7');
      });

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'model:set-7' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
      fireEvent.click(screen.getByTestId('member-pivot-save-as'));

      // The picker opens seeded (the group column from the saved config is pre-checked).
      // Scope to the group-columns checklist (membership_type is labelled "Type" in both
      // the group section and the measure-column select, so scope the query to the group box).
      await waitFor(() => {
        const groupBox = screen.getByTestId('field-picker-group-fields');
        const input = within(groupBox).getByRole('checkbox', { name: 'Type' }) as HTMLInputElement;
        expect(input).toBeChecked();
      });
      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'Variant' },
      });
      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(saveAnalyticsSet).toHaveBeenCalledTimes(1));
      expect(updateAnalyticsSet).not.toHaveBeenCalled();
      const [name, config] = saveAnalyticsSet.mock.calls[0];
      expect(name).toBe('Variant');
      // The seeded set's own filters carried into the new set (R4.4).
      expect(config.filters).toEqual({ clubblad: 'Papier' });
    });

    it('round-trips a saved set: save → appears in the list → load reproduces its config incl. filters', async () => {
      const newModelSummary = { id: 'set-99', name: 'My new set', kind: 'count' as const };
      const newConfig: PivotConfig = {
        dataSource: 'members',
        groupColumns: ['membership_type'],
        aggregateMeasures: [],
        filters: {},
        columnPivot: null,
        columnNestLevels: [],
        displayMode: 'flat',
      };
      listAnalyticsSets
        .mockResolvedValueOnce([]) // initial — nothing saved yet
        .mockResolvedValue([newModelSummary]); // after save — appears
      getAnalyticsSet.mockResolvedValue({ ...newModelSummary, definition: newConfig, created_at: '', updated_at: '' });
      getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-99'], updated_at: '' });

      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
      fireEvent.click(screen.getByTestId('member-pivot-new-set'));
      fireEvent.change(await screen.findByTestId('field-picker-name'), {
        target: { value: 'My new set' },
      });
      fireEvent.click(screen.getByTestId('field-picker-group-membership_type'));
      fireEvent.click(screen.getByTestId('field-picker-save'));
      await waitFor(() => expect(saveAnalyticsSet).toHaveBeenCalledTimes(1));

      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('model:set-99');
      });

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'model:set-99' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));

      await screen.findByTestId('mock-pivot-result-table');
      expect(getAnalyticsSet).toHaveBeenCalledWith('set-99');
      expect(tableCalls[tableCalls.length - 1].config).toEqual(newConfig);
    });
  });

  // --- the Mail button in the result-actions slot (R4.12/R8.4). --------------
  describe('Mail button (R4.12/R8.4)', () => {
    it('does NOT render the Mail button without canExport (members:export)', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
      await executeAggregate();
      expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();
    });

    it('renders the Mail button in the result-actions slot only when canExport', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();

      await executeAggregate();

      const mailButton = screen.getByTestId('member-pivot-mail');
      expect(mailButton).toBeInTheDocument();
      expect(mailButton).toHaveTextContent('analytics.export.mail');
    });

    it('opens the compose modal when the Mail button is clicked', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();

      expect(screen.queryByTestId('member-mail-compose')).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId('member-pivot-mail'));
      expect(await screen.findByTestId('member-mail-compose')).toBeInTheDocument();
    });

    // --- the mail-enabled gate (R0/R1). --------------------------------------
    describe('mail-enabled gate (R0/R1)', () => {
      const mailProps = (mail_enabled?: boolean) =>
        makeProps({
          capabilities: { canExport: true },
          fieldConfig: { ...fieldConfig, mail_enabled } as unknown as FieldConfig,
        });

      it('HIDES the Mail action and shows the degradation reason when NOT mail-enabled', async () => {
        render(<MemberPivotViews {...mailProps(false)} />);
        await executeAggregate();

        expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();
        const notice = screen.getByTestId('member-pivot-mail-unavailable');
        expect(notice).toBeInTheDocument();
        expect(notice).toHaveTextContent('analytics.degradation.mailNotEnabled');
        expect(screen.getByTestId('member-pivot-export-csv')).toBeInTheDocument();
      });

      it('HIDES the Mail action when the mail-enabled flag is ABSENT (fail-closed)', async () => {
        render(<MemberPivotViews {...mailProps(undefined)} />);
        await executeAggregate();

        expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();
        expect(screen.getByTestId('member-pivot-mail-unavailable')).toBeInTheDocument();
      });

      it('OFFERS the Mail action (and no degradation notice) when mail-enabled', async () => {
        render(<MemberPivotViews {...mailProps(true)} />);
        await executeAggregate();

        expect(screen.getByTestId('member-pivot-mail')).toBeInTheDocument();
        expect(screen.queryByTestId('member-pivot-mail-unavailable')).not.toBeInTheDocument();
      });

      it('does NOT open the compose modal when NOT mail-enabled (the action is hidden)', async () => {
        render(<MemberPivotViews {...mailProps(false)} />);
        await executeAggregate();

        expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();
        expect(screen.queryByTestId('member-mail-compose')).not.toBeInTheDocument();
      });
    });
  });

  // --- the "Generate address labels" action in the slot (R6). ----------------
  describe('Generate address labels button (R6)', () => {
    beforeEach(() => {
      listMemberTemplates.mockResolvedValue({
        ok: true,
        data: [{ template_id: 'lbl-1', name: 'Addresses', kind: 'label', lines: [['membership_type']] }],
      });
    });

    it('does NOT render the labels action without canExport (members:export)', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
      await executeAggregate();
      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
    });

    it('renders the labels action in the result-actions slot beside CSV / Mail', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();

      await executeAggregate();

      const slot = screen.getByTestId('pivot-result-actions');
      const labelsButton = screen.getByTestId('member-pivot-labels');
      expect(slot).toContainElement(labelsButton);
      expect(labelsButton).toHaveTextContent('analytics.labels.action');
    });

    it('opens a modal hosting the template-driven labels panel when clicked', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();

      expect(screen.queryByTestId('member-labels-panel')).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId('member-pivot-labels'));

      expect(await screen.findByTestId('member-pivot-labels-modal')).toBeInTheDocument();
      expect(screen.getByText('analytics.labels.modalTitle')).toBeInTheDocument();
      expect(screen.getByTestId('member-labels-panel')).toBeInTheDocument();

      const templateSelect = screen.getByTestId('member-pivot-labels-template') as HTMLSelectElement;
      const templateValues = Array.from(templateSelect.querySelectorAll('option')).map((o) => o.value);
      expect(templateValues).toEqual(['lbl-1']);

      const formatSelect = screen.getByTestId('member-pivot-labels-format') as HTMLSelectElement;
      const formatValues = Array.from(formatSelect.querySelectorAll('option')).map((o) => o.value);
      expect(formatValues).toContain('L7160');
      expect(screen.getByTestId('member-pivot-labels-generate')).toBeInTheDocument();
    });

    it('Generate composes the CURRENT rows through the chosen template lines + format and downloads', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();
      const produced = tableCalls[tableCalls.length - 1];

      fireEvent.click(screen.getByTestId('member-pivot-labels'));
      await screen.findByTestId('member-labels-panel');

      fireEvent.change(screen.getByTestId('member-pivot-labels-format'), {
        target: { value: 'L7163' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));

      await waitFor(() => expect(generateLabelTemplatePdf).toHaveBeenCalled());
      const call = generateLabelTemplatePdf.mock.calls[
        generateLabelTemplatePdf.mock.calls.length - 1
      ] as unknown[];
      expect(call[0]).toEqual(produced.data); // CURRENT result rows (R2/R3)
      expect(call[2]).toEqual({ lines: [['membership_type']] }); // chosen template's lines
      expect((call[3] as { key: string }).key).toBe('L7163'); // chosen Avery format

      const result = generateLabelTemplatePdf.mock.results[
        generateLabelTemplatePdf.mock.results.length - 1
      ].value as { doc: { save: ReturnType<typeof vi.fn> } };
      expect(result.doc.save).toHaveBeenCalledTimes(1);

      expect(screen.getByTestId('member-pivot-labels-counts')).toBeInTheDocument();
    });

    it('labels ONLY the table-filtered subset, not the full result', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();

      const produced = tableCalls[tableCalls.length - 1];
      expect(produced.data.length).toBeGreaterThan(1);

      fireEvent.click(screen.getByTestId('mock-table-filter-to-first-row'));

      fireEvent.click(screen.getByTestId('member-pivot-labels'));
      await screen.findByTestId('member-labels-panel');
      fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));

      await waitFor(() => expect(generateLabelTemplatePdf).toHaveBeenCalled());
      const call = generateLabelTemplatePdf.mock.calls[
        generateLabelTemplatePdf.mock.calls.length - 1
      ] as unknown[];
      expect(call[0]).toEqual(produced.data.slice(0, 1));
    });
  });

  // --- the labels availability gate (labels R-L2 / Property 3). --------------
  // The action is OFFERED only when the caller holds `members:export` AND ≥1
  // LABEL template exists; otherwise HIDDEN with the labels-namespace reason. The
  // gate depends ONLY on `canExport` + `hasLabelTemplate` — NOT on any
  // `analytics.*` config (R6; the address-mapping path was removed).
  describe('Generate address labels availability gate (labels R-L2 / Property 3)', () => {
    const templatesLoader = (data: unknown[]) =>
      vi.fn().mockResolvedValue({ ok: true, data });
    const withLabelTemplate = templatesLoader([
      { template_id: 'lbl-1', name: 'Addresses', kind: 'label', lines: [['membership_type']] },
      { template_id: 'mail-1', name: 'Newsletter', kind: 'mail', languages: {} },
    ]);
    const withoutLabelTemplate = templatesLoader([
      { template_id: 'mail-1', name: 'Newsletter', kind: 'mail', languages: {} },
    ]);

    it('OFFERS the labels action when the caller may export AND ≥1 label template exists', async () => {
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={withLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.getByTestId('member-pivot-labels')).toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-labels-unavailable')).not.toBeInTheDocument();
    });

    it('HIDES the labels action with the no-template reason when ZERO label templates exist', async () => {
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={withoutLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
      const notice = screen.getByTestId('member-pivot-labels-unavailable');
      expect(notice).toBeInTheDocument();
      expect(notice).toHaveTextContent('analytics.labels.noTemplate');
      expect(notice).toHaveAttribute('data-notice-kind', 'degradation');
      // Config/capability gate — NOT a tenant gate: CSV + Mail stay available.
      expect(screen.getByTestId('member-pivot-export-csv')).toBeInTheDocument();
      expect(screen.getByTestId('member-pivot-mail')).toBeInTheDocument();
    });

    it('HIDES the labels action (and the whole slot) when the caller lacks members:export', async () => {
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: false } })}
          listTemplates={withLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.queryByTestId('pivot-result-actions')).not.toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-labels-unavailable')).not.toBeInTheDocument();
    });

    it('does NOT read any analytics config: a label template alone opens the action (R6 / Property 3)', async () => {
      // The field config carries NO analytics role-config; the gate reads only
      // export + label-template presence.
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={withLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.getByTestId('member-pivot-labels')).toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-labels-unavailable')).not.toBeInTheDocument();
    });

    it('fails closed: a non-ok template load hides the action (no crash)', async () => {
      const failingLoader = vi.fn().mockResolvedValue({ ok: false, status: 500, error: 'boom' });
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={failingLoader}
        />,
      );
      await executeAggregate();

      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
      expect(screen.getByTestId('member-pivot-labels-unavailable')).toBeInTheDocument();
    });

    it('does NOT open the labels modal when the gate is closed (no template)', async () => {
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={withoutLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.queryByTestId('member-pivot-labels-modal')).not.toBeInTheDocument();
      expect(screen.queryByTestId('member-labels-panel')).not.toBeInTheDocument();
    });
  });
});

// ===========================================================================
// Preferred list (R11.2 layer 2) + shared-set capability gating (R11). All
// over SAVED sets (there are no presets).
// ===========================================================================
describe('MemberPivotViews — preferred list (R11.2)', () => {
  const manageProps = () => makeProps({ capabilities: { canExport: true } });

  it('loads the user preferred list on mount (keyed server-side on sub)', async () => {
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalledTimes(1));
    expect(getPreferredList).toHaveBeenCalledWith();
  });

  it('marks nothing preferred when the user has no preferred list (every row offers Add)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-1', name: 'Paper clubblad', kind: 'list' },
      { id: 'set-2', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    expect(screen.queryByTestId('member-pivot-library-remove')).not.toBeInTheDocument();
    const rows = screen.getAllByTestId('member-pivot-library-item');
    const addButtons = screen.getAllByTestId('member-pivot-library-add');
    expect(addButtons).toHaveLength(rows.length);
  });

  it('the dropdown renders preferred set refs in order, resolving set:<id> labels', async () => {
    listAnalyticsSets.mockResolvedValue([
      AGG_SET_SUMMARY,
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['set:set-agg', 'set:set-7'],
      updated_at: '2026-01-01T00:00:00Z',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    await waitFor(() => {
      const values = Array.from(select.querySelectorAll('option'))
        .map((o) => o.value)
        .filter((v) => v !== '');
      expect(values).toEqual(['model:set-agg', 'model:set-7']);
    });
    const options = Array.from(select.querySelectorAll('option')).filter((o) => o.value !== '');
    expect(options[0]).toHaveTextContent('Members by type');
    expect(options[1]).toHaveTextContent('Active seniors');
  });

  it('the dropdown SKIPS a dangling preferred ref (a set another user deleted) silently (R11.6)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['set:set-999', 'set:set-7'],
      updated_at: '',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    await waitFor(() => {
      const values = Array.from(select.querySelectorAll('option'))
        .map((o) => o.value)
        .filter((v) => v !== '');
      expect(values).toEqual(['model:set-7']);
    });
    const values = Array.from(select.querySelectorAll('option'))
      .map((o) => o.value)
      .filter((v) => v !== '');
    expect(values).not.toContain('model:set-999');
  });

  it('a legacy preset:<key> preferred ref is skipped silently (preset subsystem removed)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types', 'set:set-7'],
      updated_at: '',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    await waitFor(() => {
      const values = Array.from(select.querySelectorAll('option'))
        .map((o) => o.value)
        .filter((v) => v !== '');
      expect(values).toEqual(['model:set-7']);
    });
    // The legacy preset ref resolves to nothing — never crashes, never an option.
    const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(values.some((v) => v.startsWith('preset:'))).toBe(false);
  });

  it('adds a saved set to the preferred list from the library (model:<id> → set:<id> ref)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());

    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    const row = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
    const addBtn = row.querySelector('[data-testid="member-pivot-library-add"]') as HTMLButtonElement;
    fireEvent.click(addBtn);

    await waitFor(() => expect(savePreferredList).toHaveBeenCalledWith(['set:set-7']));
    // The row flips to the preferred controls (Remove replaces Add).
    await waitFor(() => {
      const nowPreferred = screen
        .getAllByTestId('member-pivot-library-item')
        .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
      expect(nowPreferred.querySelector('[data-testid="member-pivot-library-remove"]')).toBeTruthy();
      expect(nowPreferred.querySelector('[data-testid="member-pivot-library-add"]')).toBeNull();
    });
  });

  it('an already-preferred set shows Remove (not Add) in the library row', async () => {
    listAnalyticsSets.mockResolvedValue([AGG_SET_SUMMARY]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-agg'], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());

    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    const row = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Members by type'))!;
    expect(row.querySelector('[data-testid="member-pivot-library-add"]')).toBeNull();
    expect(row.querySelector('[data-testid="member-pivot-library-remove"]')).toBeTruthy();
  });

  it('removes a ref from the preferred list via the library row Remove', async () => {
    listAnalyticsSets.mockResolvedValue([
      AGG_SET_SUMMARY,
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['set:set-agg', 'set:set-7'],
      updated_at: '',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    const row = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Members by type'))!;
    const remove = row.querySelector('[data-testid="member-pivot-library-remove"]') as HTMLButtonElement;
    fireEvent.click(remove);

    await waitFor(() => expect(savePreferredList).toHaveBeenCalledWith(['set:set-7']));
  });

  it('offers permanent Delete on a custom saved set (admin)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true, canWrite: true, isAdmin: true } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    const savedRow = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
    expect(savedRow.querySelector('[data-testid="member-pivot-library-delete"]')).toBeTruthy();
  });

  it('deletes a custom saved set from the library via the confirm dialog', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    deleteAnalyticsSet.mockResolvedValue(undefined);
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true, canWrite: true, isAdmin: true } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    const savedRow = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
    const del = savedRow.querySelector('[data-testid="member-pivot-library-delete"]') as HTMLButtonElement;
    fireEvent.click(del);

    expect(await screen.findByTestId('member-pivot-delete-dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('member-pivot-delete-confirm'));
    await waitFor(() => expect(deleteAnalyticsSet).toHaveBeenCalledWith('set-7'));
  });

  it('hides Delete when the caller lacks write/admin (export-only cannot delete)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    expect(screen.getAllByTestId('member-pivot-library-add').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('member-pivot-library-delete')).not.toBeInTheDocument();
  });

  it('runs a preferred set from the dropdown + Execute (modal is manage-only, no Run)', async () => {
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-agg'], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());

    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    expect(screen.queryByTestId('member-pivot-library-run')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-up')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-down')).not.toBeInTheDocument();

    // Close the modal, then run the preferred set from the dropdown + Execute.
    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'model:set-agg' },
    });
    fireEvent.click(screen.getByTestId('member-pivot-execute'));
    const table = await screen.findByTestId('mock-pivot-result-table');
    expect(table).toHaveAttribute('data-group-columns', 'membership_type');
  });

  it('degrades to no-preferred when the preferred-list load fails (no crash)', async () => {
    listAnalyticsSets.mockResolvedValue([AGG_SET_SUMMARY]);
    getPreferredList.mockRejectedValue(new Error('boom'));
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    expect(screen.queryByTestId('member-pivot-library-remove')).not.toBeInTheDocument();
  });

  it('hides ALL manage controls in the modal for a read-only caller (no export/write)', async () => {
    listAnalyticsSets.mockResolvedValue([AGG_SET_SUMMARY]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-agg'], updated_at: '' });
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    expect(screen.queryByTestId('member-pivot-library-add')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-remove')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-delete')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('member-pivot-library-name').length).toBeGreaterThan(0);
  });
});

// ===========================================================================
// Full library + localized result headers.
// ===========================================================================
describe('MemberPivotViews — full library', () => {
  const manageProps = () => makeProps({ capabilities: { canExport: true } });

  it('lists all saved sets ALPHABETICALLY by label', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-1', name: 'Zebra set', kind: 'count' },
      { id: 'set-2', name: 'Alpha set', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    const labels = screen
      .getAllByTestId('member-pivot-library-item')
      .map((el) => el.textContent ?? '');
    const alphaIdx = labels.findIndex((l) => l.includes('Alpha set'));
    const zebraIdx = labels.findIndex((l) => l.includes('Zebra set'));
    expect(alphaIdx).toBeGreaterThanOrEqual(0);
    expect(zebraIdx).toBeGreaterThanOrEqual(0);
    expect(alphaIdx).toBeLessThan(zebraIdx);
    const sorted = [...labels].sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: 'base' }),
    );
    expect(labels).toEqual(sorted);
  });

  it('narrows the library with the name filter (case-insensitive substring)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-1', name: 'Paper recipients', kind: 'count' },
      { id: 'set-2', name: 'Digital recipients', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    fireEvent.change(screen.getByTestId('member-pivot-library-filter'), {
      target: { value: 'paper' },
    });
    const labels = screen
      .getAllByTestId('member-pivot-library-item')
      .map((el) => el.textContent ?? '');
    expect(labels.some((l) => l.includes('Paper recipients'))).toBe(true);
    expect(labels.some((l) => l.includes('Digital recipients'))).toBe(false);
  });
});

describe('MemberPivotViews — localized result headers (issue 4)', () => {
  it('passes a columnLabels map that localizes the result headers from fieldConfig', async () => {
    const nlFieldConfig = {
      fields: [
        { key: 'membership_type', origin: 'fixed', label: { nl: 'Lidtype', en: 'Type' } },
        { key: 'birth_month', origin: 'calculated', label: { en: 'Birth month' } },
        { key: 'years_member', origin: 'calculated', label: { en: 'Years-member' } },
        { key: 'joined_date', origin: 'fixed', label: { en: 'Joined' } },
        { key: 'country', origin: 'fixed', label: { en: 'Country' } },
      ],
    } as unknown as FieldConfig;

    render(
      <MemberPivotViews {...makeProps({ fieldConfig: nlFieldConfig, language: 'nl' })} />,
    );
    await executeAggregate();

    const produced = tableCalls[tableCalls.length - 1] as unknown as {
      columns: PivotColumnMeta[];
      columnLabels?: Record<string, string>;
    };
    expect(produced.columnLabels).toBeDefined();
    expect(produced.columnLabels!['membership_type']).toBe('Lidtype');
    expect(produced.columnLabels!['COUNT(*)']).toBe('analytics.pivotViews.aggregates.COUNT');
  });
});

describe('MemberPivotViews — shared-set capability gating (R11)', () => {
  it('hides ALL set-mutation actions for a read-only caller (no export/write)', async () => {
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    expect(screen.queryByTestId('member-pivot-manage-set')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-new-set')).not.toBeInTheDocument();
  });

  it('shows create/edit (New set / Save as / Update) for an export-capable caller', async () => {
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    expect(screen.getByTestId('member-pivot-set-actions')).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-new-set')).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-save-as')).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-update')).toBeInTheDocument();
  });

  it('shows create/edit for a write-capable caller who cannot export', async () => {
    render(
      <MemberPivotViews {...makeProps({ capabilities: { canExport: false, canWrite: true } })} />,
    );
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    expect(screen.getByTestId('member-pivot-new-set')).toBeInTheDocument();
  });

  it('a write-only caller can create/edit but gets NO delete control (modal)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(
      <MemberPivotViews
        {...makeProps({ capabilities: { canExport: true, canWrite: true, isAdmin: false } })}
      />,
    );
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    expect(screen.getByTestId('member-pivot-new-set')).toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-delete')).not.toBeInTheDocument();
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    expect(screen.queryByTestId('member-pivot-library-delete')).not.toBeInTheDocument();
  });

  it('an admin caller gets the Delete control on a custom set in the modal', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(
      <MemberPivotViews {...makeProps({ capabilities: { canExport: true, isAdmin: true } })} />,
    );
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    const savedRow = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
    expect(savedRow.querySelector('[data-testid="member-pivot-library-delete"]')).toBeTruthy();
  });
});

// ===========================================================================
// Schedule action gating (R5): gated on the selected set having a delivery
// block AND on the caller's scheduling capability.
// ===========================================================================
describe('MemberPivotViews — schedule action gating (R5)', () => {
  async function renderWithSavedSet(opts: {
    hasDelivery: boolean;
    capabilities?: MemberAnalyticsCapabilities;
  }) {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count', hasDelivery: opts.hasDelivery },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-7'], updated_at: '' });
    render(
      <MemberPivotViews
        {...makeProps({
          capabilities: opts.capabilities ?? { canExport: true, canWrite: true, isAdmin: true },
        })}
      />,
    );
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('model:set-7');
    });
    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'model:set-7' },
    });
  }

  it('DISABLES the Schedule action for a selected set with NO delivery block (R5)', async () => {
    await renderWithSavedSet({ hasDelivery: false });

    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    const schedule = screen.getByTestId('member-pivot-schedule');
    expect(schedule).toBeInTheDocument();
    fireEvent.click(schedule);
    await waitFor(() => expect(getAnalyticsSet).not.toHaveBeenCalled());
    expect(screen.queryByTestId('member-schedule-editor')).not.toBeInTheDocument();
  });

  it('ENABLES the Schedule action + opens the editor for a set WITH a delivery block (R5)', async () => {
    getAnalyticsSet.mockResolvedValue({
      id: 'set-7',
      name: 'Active seniors',
      kind: 'count',
      definition: { groupColumns: [], aggregations: [], filters: {} },
      delivery: {
        mode: 'to_fixed',
        templateId: null,
        attachment: 'csv',
        recipients: ['agent@example.com'],
        labelOptions: null,
      },
      created_at: '',
      updated_at: '',
    });
    await renderWithSavedSet({ hasDelivery: true });

    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    const schedule = screen.getByTestId('member-pivot-schedule') as HTMLButtonElement;
    expect(schedule).not.toBeDisabled();

    fireEvent.click(schedule);
    await waitFor(() => expect(getAnalyticsSet).toHaveBeenCalledWith('set-7'));
    await waitFor(() => expect(listSchedulesForSet).toHaveBeenCalledWith('set-7'));
    expect(await screen.findByTestId('member-schedule-editor')).toBeInTheDocument();
  });

  it('HIDES the Schedule action for a region-narrowed write caller (R5 access gate)', async () => {
    await renderWithSavedSet({
      hasDelivery: true,
      capabilities: { canExport: true, canWrite: true, isAdmin: false },
    });

    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    expect(screen.queryByTestId('member-pivot-schedule')).not.toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-update')).toBeInTheDocument();
  });

  it('creating a schedule from the editor calls createSchedule (POST)', async () => {
    getAnalyticsSet.mockResolvedValue({
      id: 'set-7',
      name: 'Active seniors',
      kind: 'count',
      definition: { groupColumns: [], aggregations: [], filters: {} },
      delivery: {
        mode: 'to_fixed',
        templateId: null,
        attachment: 'csv',
        recipients: ['agent@example.com'],
        labelOptions: null,
      },
      created_at: '',
      updated_at: '',
    });
    listSchedulesForSet.mockResolvedValue([]);
    await renderWithSavedSet({ hasDelivery: true });

    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    fireEvent.click(screen.getByTestId('member-pivot-schedule'));
    await screen.findByTestId('member-schedule-editor');

    fireEvent.click(screen.getByTestId('member-schedule-save'));
    await waitFor(() => expect(createSchedule).toHaveBeenCalledTimes(1));
    expect(createSchedule).toHaveBeenCalledWith('set-7', 'monthly', true);
    expect(updateSchedule).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// Deliver-now action (R3.1 / R3.2): send a saved set's STORED to_fixed delivery
// immediately via the ad-hoc path (the on-screen result rows + stored
// recipients). Enabled on a selected saved set; confirm dialog first.
// ===========================================================================
describe('MemberPivotViews — deliver-now action (R3.1/R3.2)', () => {
  async function renderWithSavedSet(
    opts: { hasDelivery: boolean; execute?: boolean } = { hasDelivery: true },
  ) {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count', hasDelivery: opts.hasDelivery },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: ['set:set-7'], updated_at: '' });
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('model:set-7');
    });
    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'model:set-7' },
    });
    if (opts.execute) {
      fireEvent.click(screen.getByTestId('member-pivot-execute'));
      await screen.findByTestId('mock-pivot-result-table');
    }
  }

  const toFixedSet = {
    id: 'set-7',
    name: 'Active seniors',
    kind: 'count' as const,
    definition: { groupColumns: [], aggregations: [], filters: {} },
    delivery: {
      mode: 'to_fixed' as const,
      templateId: null,
      attachment: 'csv' as const,
      recipients: ['agent@example.com'],
      labelOptions: null,
    },
    created_at: '',
    updated_at: '',
  };

  it('DISABLES Deliver now until a saved set is selected', async () => {
    listAnalyticsSets.mockResolvedValue([]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    const btn = screen.getByTestId('member-pivot-deliver-now');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(screen.queryByTestId('member-pivot-deliver-now-dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(sendAdHocMail).not.toHaveBeenCalled());
    expect(deliverAnalyticsSet).not.toHaveBeenCalled();
  });

  // Validates: Requirements 3.1, 3.2, 3.5
  it('sends the on-screen result to the stored fixed recipients via the ad-hoc path', async () => {
    getAnalyticsSet.mockResolvedValue(toFixedSet);
    await renderWithSavedSet({ hasDelivery: true, execute: true });

    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    fireEvent.click(screen.getByTestId('member-pivot-deliver-now'));
    fireEvent.click(await screen.findByTestId('member-pivot-deliver-now-confirm'));

    await waitFor(() => expect(getAnalyticsSet).toHaveBeenCalledWith('set-7'));
    await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));
    const body = sendAdHocMail.mock.calls[0][0];
    expect(body.mode).toBe('to_fixed');
    expect(body.attachment).toBe('csv');
    expect(body.recipients).toEqual(['agent@example.com']);
    expect(body.result_rows).toEqual(tableCalls[0].data);
    expect(deliverAnalyticsSet).not.toHaveBeenCalled();
  });

  // Validates: Requirements 3.4 (clear reason, not a silent no-op)
  it('does NOT call deliver and warns when the set has no to_fixed delivery', async () => {
    getAnalyticsSet.mockResolvedValue({
      ...toFixedSet,
      delivery: {
        mode: 'per_recipient',
        templateId: null,
        attachment: null,
        recipients: [],
        labelOptions: null,
      },
    });
    await renderWithSavedSet({ hasDelivery: true, execute: true });

    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    fireEvent.click(screen.getByTestId('member-pivot-deliver-now'));
    fireEvent.click(await screen.findByTestId('member-pivot-deliver-now-confirm'));

    await waitFor(() => expect(getAnalyticsSet).toHaveBeenCalledWith('set-7'));
    await waitFor(() => expect(sendAdHocMail).not.toHaveBeenCalled());
    expect(deliverAnalyticsSet).not.toHaveBeenCalled();
  });

  // Validates: Requirements 3.4 (not-certified refusal surfaces, no crash)
  it('surfaces a deliver-route refusal (not-certified 422) without crashing', async () => {
    getAnalyticsSet.mockResolvedValue(toFixedSet);
    const { ApiError } = await import('../../../shared/api/ApiError');
    sendAdHocMail.mockRejectedValue(
      new ApiError(422, {
        error: 'The tenant mail sender is not certified',
        code: 'errors.mail.notCertified',
      }),
    );
    await renderWithSavedSet({ hasDelivery: true, execute: true });

    fireEvent.click(screen.getByTestId('member-pivot-manage-set'));
    fireEvent.click(screen.getByTestId('member-pivot-deliver-now'));
    fireEvent.click(await screen.findByTestId('member-pivot-deliver-now-confirm'));

    await waitFor(() => expect(sendAdHocMail).toHaveBeenCalledTimes(1));
    // The compose/result stays usable (no crash).
    expect(screen.getByTestId('mock-pivot-result-table')).toBeInTheDocument();
  });
});
