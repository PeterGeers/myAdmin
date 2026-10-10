/**
 * Component tests for MemberPivotViews (analytics/MemberPivotViews.tsx).
 *
 * Verifies task 7.3 (R4.1, R4.6, R4.7, R5.2, R1.6):
 *   - the set dropdown lists the available PRESETS and the SAVED MEMBER SETS
 *     from the Members API `listAnalyticsSets` (R4.6/R5.2) — the Members Lambda
 *     returns ONLY this tenant's member sets, so no client-side data-source
 *     filter is needed (F-012 — the member saved-set store is the module's own
 *     DynamoDB plane, NOT the Flask pivotService/pivot_models);
 *   - NOTHING runs until the user explicitly clicks Execute: no result renders
 *     on mount, and selecting a set alone runs nothing (R1.6 — no auto-run);
 *   - on Execute the chosen set's config is resolved (inline for a preset,
 *     loaded via `getAnalyticsSet` for a saved set), the client adapter runs
 *     over `processedData`, and the result renders through the reused
 *     `PivotResultTable` (R4.1/R4.7);
 *   - the saved set's own definition filters travel with it, NOT the page filter
 *     (R4.4a) — the adapter is handed `processedData` as-is;
 *   - labels resolve from the `members`-namespace i18n keys (no hardcoded
 *     English);
 *   - the component is exported from the analytics barrel.
 *
 * `membersApiService` is mocked so no network is hit; `PivotResultTable` is
 * mocked with a lightweight recorder so result assertions don't depend on the
 * real (reports-namespace) table. i18n keys are echoed so assertions are
 * locale-independent and prove no hardcoded English.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import type { PivotConfig, PivotColumnMeta } from '../../../types/pivot';
import type { MemberRow } from '../../../types/members';

// --- Mock the Members API service (R4.6/R5.2 listing + loading + lifecycle). --
// The full save/save-as/update/delete lifecycle (task 7.5) routes through the
// Members module's OWN `/members/analytics-sets` DynamoDB CRUD (F-012), NOT the
// Flask pivotService — all mocked so no network is hit. The Lambda returns only
// this tenant's member sets, so there is no client-side data-source filter.
const listAnalyticsSets = vi.fn();
const getAnalyticsSet = vi.fn();
const saveAnalyticsSet = vi.fn();
const updateAnalyticsSet = vi.fn();
const deleteAnalyticsSet = vi.fn();
const getPreferredList = vi.fn();
const savePreferredList = vi.fn();
// Delivery + schedule route wrappers (R3 / R5). The Delivery/Schedule lifecycle
// actions call these from their handlers; stubbed so no network is hit.
const putAnalyticsSetDelivery = vi.fn();
const deleteAnalyticsSetDelivery = vi.fn();
const deliverAnalyticsSet = vi.fn();
const listSchedulesForSet = vi.fn();
const createSchedule = vi.fn();
const updateSchedule = vi.fn();
const deleteSchedule = vi.fn();
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
  listSchedulesForSet: (...args: unknown[]) => listSchedulesForSet(...args),
  createSchedule: (...args: unknown[]) => createSchedule(...args),
  updateSchedule: (...args: unknown[]) => updateSchedule(...args),
  deleteSchedule: (...args: unknown[]) => deleteSchedule(...args),
  // Constants the real MemberScheduleEditor imports (cadence picker + cron map).
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
    // A test can simulate the user filtering the table to a subset by clicking
    // this button, which reports a single row via onVisibleRowsChange — exactly
    // what the real table does from its post-filter `processedData`.
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

// --- Mock the reused CSV util (task 8.1 — reuse csvExport.ts, don't reimpl). --
// `generateCsvFromObjects` is captured so we can assert the produced result's
// columns + rows are handed to it; `downloadCsv` is a no-op recorder (no real
// Blob/anchor in jsdom).
const generateCsvFromObjects = vi.fn();
const downloadCsv = vi.fn();
vi.mock('../../../utils/csvExport', () => ({
  generateCsvFromObjects: (...args: unknown[]) => generateCsvFromObjects(...args),
  downloadCsv: (...args: unknown[]) => downloadCsv(...args),
}));

// --- Mock the analytics audit signal (task 10.1 / C7) so the CSV export's
// fire-and-forget audit POST never hits the network in a component test. ------
const recordAnalyticsOutput = vi.fn();
vi.mock('../../../services/memberAnalyticsAuditService', () => ({
  recordAnalyticsOutput: (...args: unknown[]) => recordAnalyticsOutput(...args),
}));

// --- Mock the reused AddressLabelGenerator (task 6.1 / R6) so the "Generate
// address labels" action in the result-actions slot can be asserted without
// driving the real jsPDF layout. The TEMPLATE-DRIVEN labels modal (labels
// sub-spec task 3.2) composes via `generateLabelTemplatePdf`; we mock ONLY that
// service export (spreading the real module so the format catalogue +
// `generateAddressLabelPdf` the mail-attach path uses stay intact), capturing
// each call's args so a test proves the modal composes the CURRENT result rows
// through the CHOSEN template's lines + the CHOSEN Avery format, and that
// `result.doc.save` fires the download. --
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

// --- Mock the member template service (labels sub-spec R-L2, task 3.1). ------
// The labels action gate loads the tenant's `kind:"label"` templates via
// `listMemberTemplates` (injectable prop, defaulting to this real service). It
// is mocked so no network is hit; the DEFAULT resolves to an ok result with NO
// label templates (so, as before, the labels action stays hidden unless a test
// opts in). Property-3 tests inject their own `listTemplates` fake directly to
// drive the ≥1-label-template branch, independent of this module default.
const listMemberTemplates = vi.fn();
vi.mock('../../../services/memberTemplateService', async (importOriginal) => {
  // Spread the real module so the OTHER exports MemberMailCompose imports
  // (getMemberTemplate, createMemberTemplate, …) stay intact; only the
  // labels-gate loader `listMemberTemplates` is replaced with a controllable fn.
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

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberPivotViews from './MemberPivotViews';
import { MemberPivotViews as FromBarrel } from './index';
import type { FieldConfig } from '../../../types/members';
import type { MemberAnalyticsAreaProps, MemberAnalyticsCapabilities } from './areas/types';

/**
 * A field config that exposes the fixed/calculated keys the always-available
 * presets need (membership_type, birth_month, years_member, joined_date,
 * country), with NO analytics config so no role-backed presets are offered —
 * keeping the preset list deterministic for the dropdown assertions.
 */
const fieldConfig = {
  fields: [
    { key: 'membership_type', origin: 'fixed', label: { en: 'Type' } },
    { key: 'birth_month', origin: 'calculated', label: { en: 'Birth month' } },
    { key: 'years_member', origin: 'calculated', label: { en: 'Years-member' } },
    { key: 'joined_date', origin: 'fixed', label: { en: 'Joined' } },
    { key: 'country', origin: 'fixed', label: { en: 'Country' } },
  ],
  // Mail-enabled by default (pivot-output-actions R0/R1 task 1.3) so the existing
  // Mail / compose tests exercise the capability (canExport) gate, not the mail
  // gate; the mail-enabled gate's hidden-when-not-enabled paths are covered in
  // their own describe block below (mail_enabled false / absent).
  mail_enabled: true,
} as unknown as FieldConfig;

const processedData = [
  { member_id: 'a', membership_type: 'Gold' },
  { member_id: 'b', membership_type: 'Gold' },
  { member_id: 'c', membership_type: 'Silver' },
] as unknown as MemberRow[];

function makeProps(
  overrides: Partial<MemberAnalyticsAreaProps> = {},
): MemberAnalyticsAreaProps {
  return {
    processedData,
    members: processedData as never,
    fieldConfig,
    hasAnalyticsConfig: false,
    language: 'en',
    // Default to a fully set-management-capable caller so the lifecycle +
    // dropdown tests see the New set / Save as / Update / Delete actions (R11
    // gates these on export|write / write|admin). Tests that assert the ABSENCE
    // of a capability-gated control pass an explicit `capabilities` override.
    capabilities: { canExport: true, canWrite: true, isAdmin: true },
    ...overrides,
  };
}

/**
 * UI REDESIGN: the preferred list + full library no longer render inline in the
 * main pane — they live inside the "All sets" library modal, opened by the
 * `member-pivot-open-library` button beside the dropdown. Any test that queries
 * the modal-only testids (member-pivot-preferred* / member-pivot-library*) must
 * open the modal first. This helper does that and waits for the modal to mount.
 */
async function openLibrary() {
  fireEvent.click(screen.getByTestId('member-pivot-open-library'));
  await screen.findByTestId('member-pivot-library-modal');
}

beforeEach(() => {
  tableCalls.length = 0;
  listAnalyticsSets.mockReset();
  getAnalyticsSet.mockReset();
  saveAnalyticsSet.mockReset();
  updateAnalyticsSet.mockReset();
  deleteAnalyticsSet.mockReset();
  // Default: no saved sets (overridden per-test).
  listAnalyticsSets.mockResolvedValue([]);
  // saveAnalyticsSet resolves to the full MemberAnalyticsSet (string set id).
  saveAnalyticsSet.mockResolvedValue({
    id: 'set-99', name: 'saved', kind: 'count', definition: {}, created_at: '', updated_at: '',
  });
  updateAnalyticsSet.mockResolvedValue({
    id: 'set-7', name: 'updated', kind: 'count', definition: {}, created_at: '', updated_at: '',
  });
  deleteAnalyticsSet.mockResolvedValue(undefined);
  getPreferredList.mockReset();
  savePreferredList.mockReset();
  // Default: the user has an empty preferred list (overridden per-test).
  getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
  // savePreferredList echoes back the refs it was given (full replace).
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
  // Default: the template generator returns a doc stub + sane counts; a test can
  // override the counts, and the doc's save/output are spies so download/print
  // never touch real jsPDF or the DOM.
  generateLabelTemplatePdf.mockReturnValue({
    doc: { save: vi.fn(), output: vi.fn().mockReturnValue('blob:labels') },
    labelCount: 3,
    excludedCount: 0,
    pages: 1,
  });
  // Default: an ok template list with NO label templates (labels sub-spec R-L2),
  // so the labels action stays hidden unless a test provides a label template.
  listMemberTemplates.mockReset();
  listMemberTemplates.mockResolvedValue({ ok: true, data: [] });
  putAnalyticsSetDelivery.mockReset();
  deleteAnalyticsSetDelivery.mockReset();
  deliverAnalyticsSet.mockReset();
  deliverAnalyticsSet.mockResolvedValue({
    runId: 'run-1',
    mode: 'to_fixed',
    enqueued: 1,
    skippedNoAddress: 0,
    jobIds: ['job-1'],
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

  it('the dropdown lists ONLY preferred sets + the jubilee/new-members selector presets (new contract)', async () => {
    // NEW CONTRACT (UI redesign): the "Select a set" dropdown is the everyday
    // launcher — it lists ONLY the user's PREFERRED sets (saved order) PLUS the
    // two always-reachable selector presets (jubilee / new-members). It no longer
    // lists every preset. Here the user has one preferred preset
    // (membership-types), so the dropdown shows exactly that + jubilee +
    // new-members, and does NOT show the non-preferred always-available presets.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
      updated_at: '',
    });
    render(<MemberPivotViews {...makeProps()} />);

    // Wait for the (empty) saved-set fetch to settle.
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    await waitFor(() => {
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('preset:membership-types');
    });
    const optionValues = Array.from(select.querySelectorAll('option')).map((o) => o.value);

    // ONLY the user's preferred set is offered in the dropdown.
    expect(optionValues).toContain('preset:membership-types');
    // Non-preferred presets — including the jubilee/new-members selector presets
    // — are NOT in the dropdown anymore; they are reachable only via the "All
    // sets" library modal (asserted below) or by adding them to the preferred
    // list first. No prefab appears unless the user explicitly added it.
    expect(optionValues).not.toContain('preset:jubilees');
    expect(optionValues).not.toContain('preset:new-members');
    expect(optionValues).not.toContain('preset:birthday-birth-month');
    // Role-backed presets are NOT offered without an analytics config.
    expect(optionValues).not.toContain('preset:cancellations');
    expect(optionValues).not.toContain('preset:clubblad-digital');
  });

  it('the FULL library (every preset + saved set) is reachable via the "All sets" modal', async () => {
    // NEW CONTRACT: non-preferred presets and all saved sets are no longer in the
    // dropdown — they live in the "All sets" library modal. Here the user has an
    // empty preferred list, so the dropdown shows only the selector presets, but
    // the library modal lists every available preset + every saved set.
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-1', name: 'Paper clubblad', kind: 'list' },
      { id: 'set-3', name: 'Active seniors', kind: 'count' },
    ]);

    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    // The dropdown does NOT list the non-preferred presets / saved sets.
    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    const dropdownValues = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(dropdownValues).not.toContain('preset:membership-types');
    expect(dropdownValues).not.toContain('model:set-1');

    // Open the "All sets" library modal — the full library lives here now.
    fireEvent.click(screen.getByTestId('member-pivot-open-library'));
    expect(await screen.findByTestId('member-pivot-library-modal')).toBeInTheDocument();

    // The library lists every available preset AND every saved set.
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    const libraryLabels = screen
      .getAllByTestId('member-pivot-library-item')
      .map((el) => el.textContent ?? '');
    // The always-available presets are in the library (including the one the
    // dropdown no longer shows).
    expect(
      libraryLabels.some((l) =>
        l.includes('analytics.pivotViews.presetNames.membershipTypes'),
      ),
    ).toBe(true);
    expect(
      libraryLabels.some((l) =>
        l.includes('analytics.pivotViews.presetNames.birthdayBirthMonth'),
      ),
    ).toBe(true);
    // The saved sets appear in the library (user-authored names, shown as-is).
    expect(libraryLabels.some((l) => l.includes('Paper clubblad'))).toBe(true);
    expect(libraryLabels.some((l) => l.includes('Active seniors'))).toBe(true);
  });

  it('runs NOTHING until Execute is clicked (R1.6 — no auto-run on selection)', async () => {
    // Seed membership-types as preferred so it is a selectable dropdown option
    // (new contract: the dropdown lists only preferred + selector presets).
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
      updated_at: '',
    });
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    // Wait for the preferred preset to appear as a dropdown option.
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('preset:membership-types');
    });

    // No result on mount.
    expect(screen.queryByTestId('mock-pivot-result-table')).not.toBeInTheDocument();
    expect(tableCalls).toHaveLength(0);

    // Selecting a set alone runs nothing (no auto-run).
    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'preset:membership-types' },
    });
    expect(screen.queryByTestId('mock-pivot-result-table')).not.toBeInTheDocument();
    expect(tableCalls).toHaveLength(0);

    // Execute is enabled now a set is chosen.
    expect(screen.getByTestId('member-pivot-execute')).not.toBeDisabled();
  });

  it('Execute runs a preset through the adapter and renders the result table (R4.1/R4.7)', async () => {
    // Seed membership-types as preferred so it is selectable in the dropdown.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
      updated_at: '',
    });
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('preset:membership-types');
    });

    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'preset:membership-types' },
    });
    fireEvent.click(screen.getByTestId('member-pivot-execute'));

    // The result table renders only after Execute.
    const table = await screen.findByTestId('mock-pivot-result-table');
    expect(table).toBeInTheDocument();
    expect(tableCalls).toHaveLength(1);

    // The membership-types preset groups by membership_type over processedData:
    // two groups (Gold, Silver) from the three rows.
    expect(table).toHaveAttribute('data-group-columns', 'membership_type');
    expect(table).toHaveAttribute('data-row-count', '2');
    // A preset carries its config inline — no saved-set load needed.
    expect(getAnalyticsSet).not.toHaveBeenCalled();
  });

  it('Execute loads a saved set definition and runs it over processedData (R4.4a)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Paper clubblad', kind: 'list' },
    ]);
    // A filtered-list set (empty groupColumns) with NO definition filter returns
    // one row per member (R4.8); the page's live filter is NOT re-baked (R4.4a).
    const savedConfig: PivotConfig = {
      dataSource: 'members',
      groupColumns: [],
      aggregateMeasures: [],
      filters: {},
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'flat',
    };
    getAnalyticsSet.mockResolvedValue({
      id: 'set-7',
      name: 'Paper clubblad',
      kind: 'list',
      definition: savedConfig,
      created_at: '',
      updated_at: '',
    });
    // Make the saved set preferred (ref set:<id>) so model:set-7 is a selectable
    // dropdown option under the new contract.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['set:set-7'],
      updated_at: '',
    });

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
    // Filtered-list mode: the adapter was handed processedData as-is (page
    // filter NOT re-baked, R4.4a) → one output row per input member.
    expect(table).toHaveAttribute('data-row-count', String(processedData.length));
    expect(tableCalls[0].config).toEqual(savedConfig);
  });

  it('applies a saved set\'s DEFINITION filter at execute (issue 3)', async () => {
    // The clubblad "paper" set: a filtered-list set carrying {clubblad:'Papier'}.
    // At execute the generic definition filter narrows processedData to members
    // whose clubblad equals 'Papier' (case-insensitive) — the adapter does not
    // itself apply config.filters, so the panel applies it.
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
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-9', name: 'Clubblad paper', kind: 'list' },
    ]);
    getAnalyticsSet.mockResolvedValue({
      id: 'set-9',
      name: 'Clubblad paper',
      kind: 'list',
      definition: paperConfig,
      created_at: '',
      updated_at: '',
    });
    // Make the saved set preferred so model:set-9 is a selectable dropdown option.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['set:set-9'],
      updated_at: '',
    });

    render(
      <MemberPivotViews
        {...makeProps({ processedData: paperRows, members: paperRows as never })}
      />,
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
    // Only the two 'Papier'/'papier' members survive the definition filter.
    expect(table).toHaveAttribute('data-row-count', '2');
  });

  it('degrades to presets-only when the saved-set fetch fails (never crashes)', async () => {
    listAnalyticsSets.mockRejectedValue(new Error('network'));
    // A preferred preset so the dropdown has a preset option to assert on (the
    // saved-set fetch failure must not take the presets down with it).
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
      updated_at: '',
    });

    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    // The dropdown still renders with the preferred preset; no saved-model
    // options survived the failed fetch.
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('preset:membership-types');
    });
    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    const optionValues = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(optionValues).toContain('preset:membership-types');
    expect(optionValues.some((v) => v.startsWith('model:'))).toBe(false);
  });

  it('uses the bilingual i18n keys for the controls (no hardcoded English)', async () => {
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    expect(screen.getByText('analytics.pivotViews.selectSet')).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-execute')).toHaveTextContent(
      'analytics.pivotViews.execute',
    );
  });

  // --- Task 7.6: the jubilee year selector. ----------------------------------
  describe('jubilee year selector (task 7.6, R4.2/R4.4)', () => {
    // Rows carrying years_member so the jubilee filter has something to narrow.
    const jubileeRows = [
      { member_id: 'a', years_member: '25' },
      { member_id: 'b', years_member: '40' },
      { member_id: 'c', years_member: '25' },
      { member_id: 'd', years_member: '26' },
    ] as unknown as MemberRow[];

    // The dropdown now lists ONLY preferred sets, so seed the jubilee +
    // new-members selector presets as preferred to make them selectable here.
    beforeEach(() => {
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['preset:jubilees', 'preset:new-members'],
        updated_at: '',
      });
    });

    it('shows the selector ONLY when the Jubilees preset is selected', async () => {
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      // Not shown before any set is picked.
      expect(screen.queryByTestId('member-pivot-jubilee-year')).not.toBeInTheDocument();

      // Not shown for a non-jubilee preset. Use new-members (also seeded as
      // preferred above) — NOT the jubilee set — so this stays a real,
      // meaningful negative selection.
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:new-members' },
      });
      expect(screen.queryByTestId('member-pivot-jubilee-year')).not.toBeInTheDocument();

      // Shown once the Jubilees preset is selected.
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:jubilees' },
      });
      expect(screen.getByTestId('member-pivot-jubilee-year')).toBeInTheDocument();
      expect(screen.getByText('analytics.pivotViews.jubileeYear')).toBeInTheDocument();
    });

    it('offers the default multiples-of-5 years when no jubilee_rule is configured', async () => {
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:jubilees' },
      });

      const yearSelect = screen.getByTestId('member-pivot-jubilee-year') as HTMLSelectElement;
      const values = Array.from(yearSelect.querySelectorAll('option'))
        .map((o) => o.value)
        .filter((v) => v !== ''); // drop the placeholder
      expect(values).toContain('5');
      expect(values).toContain('25');
      expect(values).not.toContain('7');
    });

    it('reads a configured jubilee_rule years set for the options', async () => {
      const withRule = {
        ...fieldConfig,
        analytics: { jubilee_rule: { years: [25, 40, 50] } },
      } as unknown as FieldConfig;

      render(<MemberPivotViews {...makeProps({ fieldConfig: withRule })} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:jubilees' },
      });

      const yearSelect = screen.getByTestId('member-pivot-jubilee-year') as HTMLSelectElement;
      const values = Array.from(yearSelect.querySelectorAll('option'))
        .map((o) => o.value)
        .filter((v) => v !== '');
      expect(values).toEqual(['25', '40', '50']);
    });

    it('flows the chosen year into the executed config filters and narrows rows (R4.4)', async () => {
      render(
        <MemberPivotViews {...makeProps({ processedData: jubileeRows, members: jubileeRows as never })} />,
      );
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:jubilees' },
      });
      fireEvent.change(screen.getByTestId('member-pivot-jubilee-year'), {
        target: { value: '25' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));

      const table = await screen.findByTestId('mock-pivot-result-table');
      expect(table).toBeInTheDocument();

      // The chosen year is persisted as a definition filter (so task 7.5 saves it).
      expect(tableCalls).toHaveLength(1);
      expect(tableCalls[0].config.filters).toMatchObject({ years_member: 25 });

      // Jubilees is a filtered-list preset → one row per member at that jubilee:
      // only the two members with years_member === 25 survive the filter.
      expect(table).toHaveAttribute('data-row-count', '2');
    });

    it('lists all jubilee-eligible members when no year is chosen (no filter baked in)', async () => {
      render(
        <MemberPivotViews {...makeProps({ processedData: jubileeRows, members: jubileeRows as never })} />,
      );
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:jubilees' },
      });
      // No year selected — Execute straight away.
      fireEvent.click(screen.getByTestId('member-pivot-execute'));

      const table = await screen.findByTestId('mock-pivot-result-table');
      // All four rows pass through (no jubilee filter applied).
      expect(table).toHaveAttribute('data-row-count', String(jubileeRows.length));
      expect(tableCalls[0].config.filters).not.toHaveProperty('years_member');
    });

    it('uses the bilingual placeholder for the year selector (no hardcoded English)', async () => {
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:jubilees' },
      });
      const yearSelect = screen.getByTestId('member-pivot-jubilee-year') as HTMLSelectElement;
      const placeholder = Array.from(yearSelect.querySelectorAll('option')).find(
        (o) => o.value === '',
      );
      expect(placeholder?.textContent).toBe('analytics.pivotViews.jubileeYearPlaceholder');
    });
  });

  // --- Findings F-010: the New-members "joined since <year>" selector. -------
  describe('new-members join-year selector (F-010)', () => {
    // Rows with joined_date so the joined-after filter has something to narrow.
    const joinedRows = [
      { member_id: 'a', joined_date: '2018-02-01' },
      { member_id: 'b', joined_date: '2022-06-01' },
      { member_id: 'c', joined_date: '2024-09-01' },
    ] as unknown as MemberRow[];

    // The dropdown lists ONLY preferred sets — seed the new-members + jubilees
    // selector presets as preferred so both are selectable in these tests.
    beforeEach(() => {
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['preset:new-members', 'preset:jubilees'],
        updated_at: '',
      });
    });

    it('shows the selector ONLY when the New-members preset is selected', async () => {
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      expect(screen.queryByTestId('member-pivot-joined-after')).not.toBeInTheDocument();

      // Not shown for a different preset.
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:jubilees' },
      });
      expect(screen.queryByTestId('member-pivot-joined-after')).not.toBeInTheDocument();

      // Shown for New members.
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:new-members' },
      });
      expect(screen.getByTestId('member-pivot-joined-after')).toBeInTheDocument();
      expect(screen.getByText('analytics.pivotViews.joinedAfter')).toBeInTheDocument();
    });

    it('narrows the Execute result to members who joined in or after the chosen year (R4.4)', async () => {
      render(
        <MemberPivotViews {...makeProps({ processedData: joinedRows, members: joinedRows as never })} />,
      );
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:new-members' },
      });
      fireEvent.change(screen.getByTestId('member-pivot-joined-after'), {
        target: { value: '2022' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));

      const table = await screen.findByTestId('mock-pivot-result-table');
      // Only b (2022) and c (2024) joined in or after 2022.
      expect(table).toHaveAttribute('data-row-count', '2');
      // The chosen year is persisted as a definition filter (so a save keeps it).
      expect(tableCalls[0].config.filters).toMatchObject({ joined_after_year: 2022 });
    });

    it('lists all members when no join year is chosen (no filter baked in)', async () => {
      render(
        <MemberPivotViews {...makeProps({ processedData: joinedRows, members: joinedRows as never })} />,
      );
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:new-members' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));

      const table = await screen.findByTestId('mock-pivot-result-table');
      expect(table).toHaveAttribute('data-row-count', String(joinedRows.length));
      expect(tableCalls[0].config.filters).not.toHaveProperty('joined_after_year');
    });
  });

  // --- Task 8.1: CSV export of a produced result (R4.9/R4.11). ---------------
  describe('CSV export (task 8.1, R4.9/R4.11)', () => {
    // A membership-types preset produces an AGGREGATE result (group +
    // aggregate columns); a saved filtered-LIST model (empty groupColumns)
    // produces one row per member. Both are exported through the same mapping.
    const listModel = {
      id: 'set-7',
      name: 'Paper clubblad',
      kind: 'list' as const,
    };
    const listConfig: PivotConfig = {
      dataSource: 'members',
      groupColumns: [],
      aggregateMeasures: [],
      filters: {},
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'flat',
    };

    // The everyday aggregate path selects membership-types from the dropdown,
    // which (new contract) must be in the preferred list to be a selectable
    // option. Seed it preferred for every test in this block; the one filtered-
    // LIST test that needs model:set-7 overrides getPreferredList itself.
    beforeEach(() => {
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['preset:membership-types'],
        updated_at: '',
      });
    });

    /** Select the membership-types preset and Execute → aggregate result. */
    async function executeAggregate() {
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      // Wait for the preferred preset to be a selectable dropdown option.
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('preset:membership-types');
      });
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:membership-types' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));
      await screen.findByTestId('mock-pivot-result-table');
    }

    it('does NOT render the export slot or CSV button without canExport (members:export)', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
      await executeAggregate();

      // The whole capability-gated actions slot is absent for a non-exporter.
      expect(screen.queryByTestId('pivot-result-actions')).not.toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-export-csv')).not.toBeInTheDocument();
    });

    it('renders the CSV button in the result-actions slot only when canExport', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);

      // Nothing before Execute — the slot lives inside the produced result.
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      expect(screen.queryByTestId('member-pivot-export-csv')).not.toBeInTheDocument();

      await executeAggregate();

      expect(screen.getByTestId('pivot-result-actions')).toBeInTheDocument();
      const csvButton = screen.getByTestId('member-pivot-export-csv');
      expect(csvButton).toBeInTheDocument();
      // Bilingual label from the members namespace (no hardcoded English).
      expect(csvButton).toHaveTextContent('analytics.export.csv');
    });

    it('exports an AGGREGATE result: csvExport gets the result columns + rows', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();

      // The result the table received (membership_type group + COUNT(*)).
      const produced = tableCalls[tableCalls.length - 1];

      fireEvent.click(screen.getByTestId('member-pivot-export-csv'));
      fireEvent.click(screen.getByTestId('member-pivot-export-csv-download'));

      expect(generateCsvFromObjects).toHaveBeenCalledTimes(1);
      const [columns, rows] = generateCsvFromObjects.mock.calls[0];
      // The CSV column KEY is the raw result column name (so values read from the
      // data rows); the HEADER is the LOCALIZED label — the SAME `columnLabels`
      // map handed to the result table — so the exported header matches the
      // on-screen header in the user's language (not the raw English key).
      const labels = (produced as unknown as { columnLabels?: Record<string, string> })
        .columnLabels ?? {};
      expect(columns).toEqual(
        produced.columns.map((c) => ({ key: c.name, header: labels[c.name] ?? c.name })),
      );
      // The group column's header is the field's resolved label, not the raw key.
      expect(labels['membership_type']).toBeDefined();
      expect(columns[0]).toEqual({
        key: 'membership_type',
        header: labels['membership_type'],
      });
      // The result's data rows are exported verbatim.
      expect(rows).toBe(produced.data);
      // The generated CSV is handed to downloadCsv (reuse — not reimplemented).
      expect(downloadCsv).toHaveBeenCalledTimes(1);
      expect(downloadCsv.mock.calls[0][0]).toBe('col\nval');

      // The export is audit-signalled (task 10.1 / C7): metadata only — output
      // kind, the set that produced it, and the row count. NO member rows / PII
      // in the signal; filter_summary carries only the result shape.
      expect(recordAnalyticsOutput).toHaveBeenCalledTimes(1);
      const audit = recordAnalyticsOutput.mock.calls[0][0];
      expect(audit.outputKind).toBe('csv_export');
      expect(audit.recordCount).toBe(produced.data.length);
      // The signal carries no member values — only a column-count shape.
      expect(audit.filterSummary).toEqual({ columns: produced.columns.length });
    });

    it('exports a filtered-LIST result too (R4.11): one row per member', async () => {
      listAnalyticsSets.mockResolvedValue([listModel]);
      getAnalyticsSet.mockResolvedValue({
        ...listModel,
        definition: listConfig,
        created_at: '',
        updated_at: '',
      });
      // This test selects model:set-7 (not membership-types), so make set-7
      // preferred instead so it is a selectable dropdown option.
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['set:set-7'],
        updated_at: '',
      });

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
      // Filtered-list → one row per member in processedData.
      expect(produced.data).toHaveLength(processedData.length);

      fireEvent.click(screen.getByTestId('member-pivot-export-csv'));
      fireEvent.click(screen.getByTestId('member-pivot-export-csv-download'));

      expect(generateCsvFromObjects).toHaveBeenCalledTimes(1);
      const [columns, rows] = generateCsvFromObjects.mock.calls[0];
      // Key = raw column name; header = localized label (falls back to the raw
      // name for a column with no fieldConfig label).
      const listLabels = (produced as unknown as { columnLabels?: Record<string, string> })
        .columnLabels ?? {};
      expect(columns).toEqual(
        produced.columns.map((c) => ({ key: c.name, header: listLabels[c.name] ?? c.name })),
      );
      expect(rows).toBe(produced.data);
      expect(downloadCsv).toHaveBeenCalledTimes(1);
    });

    it('exports ONLY the table-filtered subset, not the full result (findings: table filters limit the export)', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();

      const produced = tableCalls[tableCalls.length - 1];
      // The result has more than one row (membership_type: Gold ×2, Silver ×1 →
      // two aggregate rows), so a filter to one row is a real subset.
      expect(produced.data.length).toBeGreaterThan(1);

      // Simulate the user filtering the result table down to the first row (the
      // mock reports that subset through onVisibleRowsChange, exactly as the real
      // table reports its post-filter processedData).
      fireEvent.click(screen.getByTestId('mock-table-filter-to-first-row'));

      fireEvent.click(screen.getByTestId('member-pivot-export-csv'));
      fireEvent.click(screen.getByTestId('member-pivot-export-csv-download'));

      expect(generateCsvFromObjects).toHaveBeenCalledTimes(1);
      const [, rows] = generateCsvFromObjects.mock.calls[0];
      // The export reflects the FILTERED subset (one row), NOT the full result.
      expect(rows).toHaveLength(1);
      expect(rows).toEqual(produced.data.slice(0, 1));

      // The audit row count also reflects the filtered subset (not the full set).
      const audit = recordAnalyticsOutput.mock.calls[0][0];
      expect(audit.recordCount).toBe(1);
    });

    it('falls back to the full result when the table reports no filtered rows', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();
      const produced = tableCalls[tableCalls.length - 1];

      // No filter simulated → export the whole result (default behavior).
      fireEvent.click(screen.getByTestId('member-pivot-export-csv'));
      fireEvent.click(screen.getByTestId('member-pivot-export-csv-download'));
      const [, rows] = generateCsvFromObjects.mock.calls[0];
      expect(rows).toBe(produced.data);
    });
  });

  // --- Task 7.5: save / save-as / update / delete lifecycle. -----------------
  describe('save lifecycle (task 7.5, R4.4/R4.4a/R4.4b)', () => {
    /** A saved members model carrying its OWN definition filters (R4.4). */
    const savedModel = {
      id: 'set-7',
      name: 'Paper clubblad',
      kind: 'count' as const,
    };
    const savedConfig: PivotConfig = {
      dataSource: 'members',
      groupColumns: ['membership_type'],
      aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      filters: { clubblad: 'Papier' },
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'flat',
    };

    it('Update / Delete are disabled until a SAVED model is selected (not a preset)', async () => {
      // Seed membership-types as preferred so the preset is a selectable option.
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['preset:membership-types'],
        updated_at: '',
      });
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('preset:membership-types');
      });

      // New set is always available; the others require a selected saved model.
      // (Delete is no longer a main-pane button — it lives in the "All sets"
      // modal per-row trash icon.)
      expect(screen.getByTestId('member-pivot-new-set')).not.toBeDisabled();
      expect(screen.getByTestId('member-pivot-save-as')).toBeDisabled();
      expect(screen.getByTestId('member-pivot-update')).toBeDisabled();
      expect(screen.queryByTestId('member-pivot-delete')).not.toBeInTheDocument();

      // Selecting a PRESET enables Save-as but NOT Update (preset ≠ saved model).
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:membership-types' },
      });
      expect(screen.getByTestId('member-pivot-save-as')).not.toBeDisabled();
      expect(screen.getByTestId('member-pivot-update')).toBeDisabled();
    });

    it('New set opens the picker to compose + save a brand-new set (R4.4)', async () => {
      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      fireEvent.click(screen.getByTestId('member-pivot-new-set'));

      // The picker is shown, blank (no seeded-from hint).
      expect(await screen.findByTestId('member-field-picker')).toBeInTheDocument();
      expect(screen.queryByTestId('field-picker-seeded')).not.toBeInTheDocument();

      // Compose + save.
      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'My new set' },
      });
      fireEvent.click(screen.getByTestId('field-picker-group-membership_type'));
      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(saveAnalyticsSet).toHaveBeenCalledTimes(1));
      const [name, config] = saveAnalyticsSet.mock.calls[0];
      expect(name).toBe('My new set');
      expect(config.dataSource).toBe('members');
      // A new save never calls update.
      expect(updateAnalyticsSet).not.toHaveBeenCalled();
    });

    it('Update edits the selected saved set in place via updateAnalyticsSet (R4.4)', async () => {
      listAnalyticsSets.mockResolvedValue([savedModel]);
      getAnalyticsSet.mockResolvedValue({
        ...savedModel,
        definition: savedConfig,
        updated_at: '',
      });
      // Make the saved set preferred so model:set-7 is a selectable dropdown option.
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['set:set-7'],
        updated_at: '',
      });

      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('model:set-7');
      });

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'model:set-7' },
      });
      // Update is now enabled; clicking it loads the set + opens the picker.
      expect(screen.getByTestId('member-pivot-update')).not.toBeDisabled();
      fireEvent.click(screen.getByTestId('member-pivot-update'));

      await waitFor(() => expect(getAnalyticsSet).toHaveBeenCalledWith('set-7'));
      // The picker opened pre-filled from the saved set (name round-trips).
      await waitFor(() =>
        expect(screen.getByTestId('field-picker-name')).toHaveValue('Paper clubblad'),
      );

      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(updateAnalyticsSet).toHaveBeenCalledTimes(1));
      // updateAnalyticsSet(id, name, config, kind) — id is the backend set_id string.
      const [id, , config] = updateAnalyticsSet.mock.calls[0];
      expect(id).toBe('set-7');
      // The set's own definition filters travel with the update (R4.4).
      expect(config.filters).toEqual({ clubblad: 'Papier' });
      // The list is refreshed after the update so the change appears immediately.
      await waitFor(() => expect(listAnalyticsSets.mock.calls.length).toBeGreaterThanOrEqual(2));
    });

    it('Save-as saves the selected saved set as a NEW set, keeping its filters (R4.4)', async () => {
      listAnalyticsSets.mockResolvedValue([savedModel]);
      getAnalyticsSet.mockResolvedValue({
        ...savedModel,
        definition: savedConfig,
        created_at: '',
        updated_at: '',
      });
      // Make the saved set preferred so model:set-7 is a selectable dropdown option.
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['set:set-7'],
        updated_at: '',
      });

      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('model:set-7');
      });

      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'model:set-7' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-save-as'));

      // The picker opens seeded (the group column from the saved config is
      // pre-checked). The testid is on the Chakra Checkbox label; the actual
      // input is addressed by its resolved accessible name ('Type').
      await waitFor(() =>
        expect(screen.getByRole('checkbox', { name: 'Type' })).toBeChecked(),
      );
      fireEvent.change(screen.getByTestId('field-picker-name'), {
        target: { value: 'Variant' },
      });
      fireEvent.click(screen.getByTestId('field-picker-save'));

      await waitFor(() => expect(saveAnalyticsSet).toHaveBeenCalledTimes(1));
      // Save-as creates a NEW set (never updates the original).
      expect(updateAnalyticsSet).not.toHaveBeenCalled();
      const [name, config] = saveAnalyticsSet.mock.calls[0];
      expect(name).toBe('Variant');
      // The seeded set's own filters carried into the new set (R4.4).
      expect(config.filters).toEqual({ clubblad: 'Papier' });
    });

    // NOTE: permanent delete moved to the "All sets" modal (per-row trash icon);
    // its flow is covered by the modal delete tests ("offers permanent Delete
    // ONLY on custom saved sets" / "deletes a custom saved set ... confirm
    // dialog"). The old dropdown-Delete lifecycle test was removed with that
    // button.

    it('round-trips a saved set: save → appears in the list → load reproduces its config incl. filters', async () => {
      // Start with no saved sets; after the save the refreshed list returns the
      // new set so it appears in the dropdown (persisted, tenant-scoped — R4.4).
      // The new set's id MUST match the id saveAnalyticsSet resolves to (set-99,
      // from the beforeEach default) so the component reselects it after save.
      const newModelSummary = {
        id: 'set-99',
        name: 'My new set',
        kind: 'count' as const,
      };
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
        .mockResolvedValue([newModelSummary]); // after save — the new set appears
      getAnalyticsSet.mockResolvedValue({
        ...newModelSummary,
        definition: newConfig,
        created_at: '',
        updated_at: '',
      });
      // Make the new set preferred so model:set-99 is a selectable dropdown
      // option once it is persisted + the saved-set list is refreshed (the
      // controlled <select> only honors a value that exists as an option).
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['set:set-99'],
        updated_at: '',
      });

      render(<MemberPivotViews {...makeProps()} />);
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

      // Save a new set.
      fireEvent.click(screen.getByTestId('member-pivot-new-set'));
      fireEvent.change(await screen.findByTestId('field-picker-name'), {
        target: { value: 'My new set' },
      });
      fireEvent.click(screen.getByTestId('field-picker-group-membership_type'));
      fireEvent.click(screen.getByTestId('field-picker-save'));
      await waitFor(() => expect(saveAnalyticsSet).toHaveBeenCalledTimes(1));

      // It now appears in the dropdown (persisted + reselected).
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('model:set-99');
      });

      // Loading + executing it reproduces its config (incl. filters) over the data.
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'model:set-99' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));

      await screen.findByTestId('mock-pivot-result-table');
      expect(getAnalyticsSet).toHaveBeenCalledWith('set-99');
      expect(tableCalls[tableCalls.length - 1].config).toEqual(newConfig);
    });
  });

  // --- Task 9.2: the Mail button in the result-actions slot. -----------------
  describe('Mail button (task 9.2, R4.12/R8.4)', () => {
    // Seed membership-types as preferred so the aggregate path can select it
    // from the dropdown (new contract: dropdown = preferred + selector presets).
    beforeEach(() => {
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['preset:membership-types'],
        updated_at: '',
      });
    });

    /** Select the membership-types preset and Execute → a result renders. */
    async function executeAggregate() {
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      // Wait for the preferred preset to be a selectable dropdown option.
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('preset:membership-types');
      });
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:membership-types' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));
      await screen.findByTestId('mock-pivot-result-table');
    }

    it('does NOT render the Mail button without canExport (members:export)', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
      await executeAggregate();
      expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();
    });

    it('renders the Mail button in the result-actions slot only when canExport', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);

      // Nothing before Execute — the slot lives inside the produced result.
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();

      await executeAggregate();

      const mailButton = screen.getByTestId('member-pivot-mail');
      expect(mailButton).toBeInTheDocument();
      // Bilingual label from the members namespace (no hardcoded English).
      expect(mailButton).toHaveTextContent('analytics.export.mail');
    });

    it('opens the compose modal when the Mail button is clicked', async () => {
      render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
      await executeAggregate();

      // Not open until the Mail button is clicked.
      expect(screen.queryByTestId('member-mail-compose')).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId('member-pivot-mail'));
      expect(await screen.findByTestId('member-mail-compose')).toBeInTheDocument();
    });

    // --- Task 1.3 (pivot-output-actions R0/R1): the mail-enabled gate. --------
    // The Mail output action (compose / send path) is OFFERED only when the
    // tenant is mail-enabled — the R0 `config#mail` flag surfaced on the field
    // config as `mail_enabled`. When NOT enabled the action is HIDDEN and the
    // shared degradation reason explains why. Fail-closed: an ABSENT flag means
    // not enabled. These tests exercise an export-capable caller (so the slot
    // renders) and vary ONLY `fieldConfig.mail_enabled` to isolate the gate.
    describe('mail-enabled gate (task 1.3, R0/R1)', () => {
      const mailProps = (mail_enabled?: boolean) =>
        makeProps({
          capabilities: { canExport: true },
          fieldConfig: { ...fieldConfig, mail_enabled } as unknown as FieldConfig,
        });

      it('HIDES the Mail action and shows the degradation reason when NOT mail-enabled', async () => {
        render(<MemberPivotViews {...mailProps(false)} />);
        await executeAggregate();

        // The Mail button is gone; the shared degradation notice is shown in its
        // place (the surrounding export slot still renders — CSV stays available).
        expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();
        const notice = screen.getByTestId('member-pivot-mail-unavailable');
        expect(notice).toBeInTheDocument();
        expect(notice).toHaveTextContent('analytics.degradation.mailNotEnabled');
        // CSV is unaffected (the gate is a tenant gate, not a capability gate).
        expect(screen.getByTestId('member-pivot-export-csv')).toBeInTheDocument();
      });

      it('HIDES the Mail action when the mail-enabled flag is ABSENT (fail-closed)', async () => {
        render(<MemberPivotViews {...mailProps(undefined)} />);
        await executeAggregate();

        expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();
        expect(
          screen.getByTestId('member-pivot-mail-unavailable'),
        ).toBeInTheDocument();
      });

      it('OFFERS the Mail action (and no degradation notice) when mail-enabled', async () => {
        render(<MemberPivotViews {...mailProps(true)} />);
        await executeAggregate();

        expect(screen.getByTestId('member-pivot-mail')).toBeInTheDocument();
        expect(
          screen.queryByTestId('member-pivot-mail-unavailable'),
        ).not.toBeInTheDocument();
      });

      it('does NOT open the compose modal when NOT mail-enabled (the action is hidden)', async () => {
        render(<MemberPivotViews {...mailProps(false)} />);
        await executeAggregate();

        // No Mail button to click, and the modal is never mounted.
        expect(screen.queryByTestId('member-pivot-mail')).not.toBeInTheDocument();
        expect(screen.queryByTestId('member-mail-compose')).not.toBeInTheDocument();
      });
    });
  });

  // --- Task 6.1: the "Generate address labels" action in the slot (R6). ------
  describe('Generate address labels button (task 6.1, R6)', () => {
    // A field config whose `analytics.address_mapping` resolves at least one slot
    // (the `name` slot → the present `membership_type` field) so
    // `resolveAddressMapping` returns a non-empty mapping. The task 6.2
    // availability gate offers the labels action only when a mapping resolves AND
    // the caller holds members:export; these task 6.1 tests assert the mounted
    // action, so they run with a resolvable mapping. (The gate's hidden paths —
    // no mapping / no export — are covered in the task 6.2 describe below.)
    const fieldConfigWithMapping = {
      ...fieldConfig,
      analytics: { address_mapping: { name: 'membership_type' } },
    } as unknown as FieldConfig;

    /**
     * Props for the labels-action tests: a resolvable address mapping so the
     * action is OFFERED, plus whatever capability override the test needs.
     */
    const labelsProps = (capabilities: MemberAnalyticsCapabilities) =>
      makeProps({ capabilities, fieldConfig: fieldConfigWithMapping });

    // Seed membership-types as preferred so the aggregate path can select it
    // from the dropdown (new contract: dropdown = preferred + selector presets).
    // Also seed ≥1 LABEL template so the NEW labels gate (R-L2 / Property 3:
    // `canExport && hasLabelTemplate`) is satisfied — these task-6.1 tests assert
    // the MOUNTED action, so the gate must be open.
    beforeEach(() => {
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['preset:membership-types'],
        updated_at: '',
      });
      listMemberTemplates.mockResolvedValue({
        ok: true,
        data: [{ template_id: 'lbl-1', name: 'Addresses', kind: 'label', lines: [['membership_type']] }],
      });
    });

    /** Select the membership-types preset and Execute → a result renders. */
    async function executeAggregate() {
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('preset:membership-types');
      });
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:membership-types' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));
      await screen.findByTestId('mock-pivot-result-table');
    }

    it('does NOT render the labels action without canExport (members:export)', async () => {
      render(<MemberPivotViews {...labelsProps({ canExport: false })} />);
      await executeAggregate();
      // The whole capability-gated actions slot is absent for a non-exporter, so
      // the labels action is too.
      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
    });

    it('renders the labels action in the result-actions slot only when canExport, beside CSV / Mail', async () => {
      render(<MemberPivotViews {...labelsProps({ canExport: true })} />);

      // Nothing before Execute — the slot lives inside the produced result.
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();

      await executeAggregate();

      // The labels action sits in the SAME result-actions slot as CSV + Mail.
      const slot = screen.getByTestId('pivot-result-actions');
      const labelsButton = screen.getByTestId('member-pivot-labels');
      expect(slot).toContainElement(labelsButton);
      // Bilingual label from the members namespace (no hardcoded English).
      expect(labelsButton).toHaveTextContent('analytics.labels.action');
    });

    it('opens a modal hosting the template-driven labels panel when clicked', async () => {
      render(<MemberPivotViews {...labelsProps({ canExport: true })} />);
      await executeAggregate();

      // The panel is not mounted until the action is clicked (the modal is
      // closed, so its body — and the panel — is not rendered yet).
      expect(screen.queryByTestId('member-labels-panel')).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId('member-pivot-labels'));

      // The modal opens with the bilingual title and the hosted panel: a template
      // select populated from the loaded kind:"label" templates + the Avery
      // format select + the Generate button.
      expect(await screen.findByTestId('member-pivot-labels-modal')).toBeInTheDocument();
      expect(screen.getByText('analytics.labels.modalTitle')).toBeInTheDocument();
      expect(screen.getByTestId('member-labels-panel')).toBeInTheDocument();

      const templateSelect = screen.getByTestId(
        'member-pivot-labels-template',
      ) as HTMLSelectElement;
      const templateValues = Array.from(
        templateSelect.querySelectorAll('option'),
      ).map((o) => o.value);
      expect(templateValues).toEqual(['lbl-1']); // the loaded label template

      const formatSelect = screen.getByTestId(
        'member-pivot-labels-format',
      ) as HTMLSelectElement;
      const formatValues = Array.from(
        formatSelect.querySelectorAll('option'),
      ).map((o) => o.value);
      expect(formatValues).toContain('L7160'); // the default Avery format
      expect(screen.getByTestId('member-pivot-labels-generate')).toBeInTheDocument();
    });

    it('Generate composes the CURRENT rows through the chosen template lines + format and downloads', async () => {
      render(<MemberPivotViews {...labelsProps({ canExport: true })} />);
      await executeAggregate();
      const produced = tableCalls[tableCalls.length - 1];

      fireEvent.click(screen.getByTestId('member-pivot-labels'));
      await screen.findByTestId('member-labels-panel');

      // Pick the (only) label template + the L7163 format, then Generate.
      fireEvent.change(screen.getByTestId('member-pivot-labels-format'), {
        target: { value: 'L7163' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));

      await waitFor(() => expect(generateLabelTemplatePdf).toHaveBeenCalled());
      const call = generateLabelTemplatePdf.mock.calls[
        generateLabelTemplatePdf.mock.calls.length - 1
      ] as unknown[];
      // (rows, fieldConfig, { lines }, format, options)
      expect(call[0]).toEqual(produced.data); // CURRENT result rows (R2/R3)
      expect(call[2]).toEqual({ lines: [['membership_type']] }); // chosen template's lines
      expect((call[3] as { key: string }).key).toBe('L7163'); // chosen Avery format

      // The produced doc is saved → the PDF downloads (R-L4).
      const result = generateLabelTemplatePdf.mock.results[
        generateLabelTemplatePdf.mock.results.length - 1
      ].value as { doc: { save: ReturnType<typeof vi.fn> } };
      expect(result.doc.save).toHaveBeenCalledTimes(1);

      // The count badges reflect the run.
      expect(screen.getByTestId('member-pivot-labels-counts')).toBeInTheDocument();
    });

    it('labels ONLY the table-filtered subset, not the full result (findings: table filters limit the output)', async () => {
      render(<MemberPivotViews {...labelsProps({ canExport: true })} />);
      await executeAggregate();

      const produced = tableCalls[tableCalls.length - 1];
      // The aggregate result has more than one row, so a filter to one row is a
      // real subset.
      expect(produced.data.length).toBeGreaterThan(1);

      // Simulate the user filtering the result table down to the first row.
      fireEvent.click(screen.getByTestId('mock-table-filter-to-first-row'));

      fireEvent.click(screen.getByTestId('member-pivot-labels'));
      await screen.findByTestId('member-labels-panel');
      fireEvent.click(screen.getByTestId('member-pivot-labels-generate'));

      await waitFor(() => expect(generateLabelTemplatePdf).toHaveBeenCalled());
      // The generator is handed the FILTERED subset (one row), not the full set.
      const call = generateLabelTemplatePdf.mock.calls[
        generateLabelTemplatePdf.mock.calls.length - 1
      ] as unknown[];
      expect(call[0]).toEqual(produced.data.slice(0, 1));
    });
  });

  // --- Task 6.2: the "Generate address labels" availability gate (R6). -------
  // Labels sub-spec R-L2 / Property 3 (REWORKED gate): the "Generate address
  // labels" action is OFFERED only when the caller holds `members:export` AND at
  // least one LABEL template (`kind:"label"`) exists; otherwise it is HIDDEN with
  // the bilingual labels-namespace degradation reason (`analytics.labels.noTemplate`).
  // The gate depends ONLY on `canExport` + `hasLabelTemplate` — crucially NOT on
  // the address mapping / any `analytics.*` config (R6). The template loader is
  // injected via the `listTemplates` prop so these tests drive the gate with no
  // network. States: offered / hidden-no-template / hidden-no-export / and the
  // key R6 assertion that the mapping is irrelevant to the gate.
  describe('Generate address labels availability gate (labels R-L2 / Property 3)', () => {
    // A field config WITHOUT any analytics address mapping. The NEW gate must not
    // read it at all — a label template alone (plus export) opens the action.
    const fieldConfigNoMapping = fieldConfig;

    // A field config WITH a resolvable address mapping. Under the OLD gate this
    // alone opened the action; under the NEW gate it is IRRELEVANT — proving the
    // gate no longer depends on the mapping (R6 / Property 3).
    const fieldConfigWithMapping = {
      ...fieldConfig,
      analytics: { address_mapping: { name: 'membership_type' } },
    } as unknown as FieldConfig;

    /** A fake template loader resolving to the given templates (ok result). */
    const templatesLoader =
      (data: unknown[]) => vi.fn().mockResolvedValue({ ok: true, data });

    /** One label + one mail template — a kind:"label" exists ⇒ gate can open. */
    const withLabelTemplate = templatesLoader([
      { template_id: 'lbl-1', name: 'Addresses', kind: 'label', lines: [['membership_type']] },
      { template_id: 'mail-1', name: 'Newsletter', kind: 'mail', languages: {} },
    ]);
    /** Only a mail template — NO kind:"label" ⇒ gate stays closed. */
    const withoutLabelTemplate = templatesLoader([
      { template_id: 'mail-1', name: 'Newsletter', kind: 'mail', languages: {} },
    ]);

    beforeEach(() => {
      getPreferredList.mockResolvedValue({
        sub: 'u1',
        refs: ['preset:membership-types'],
        updated_at: '',
      });
    });

    /** Select the membership-types preset and Execute → a result renders. */
    async function executeAggregate() {
      await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
      await waitFor(() => {
        const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
        const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
        expect(values).toContain('preset:membership-types');
      });
      fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
        target: { value: 'preset:membership-types' },
      });
      fireEvent.click(screen.getByTestId('member-pivot-execute'));
      await screen.findByTestId('mock-pivot-result-table');
    }

    it('OFFERS the labels action when the caller may export AND ≥1 label template exists', async () => {
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={withLabelTemplate}
        />,
      );
      await executeAggregate();

      // The action is shown; the degradation notice is NOT.
      expect(screen.getByTestId('member-pivot-labels')).toBeInTheDocument();
      expect(
        screen.queryByTestId('member-pivot-labels-unavailable'),
      ).not.toBeInTheDocument();
    });

    it('HIDES the labels action with the no-template reason when ZERO label templates exist', async () => {
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={withoutLabelTemplate}
        />,
      );
      await executeAggregate();

      // Hidden; the NEW bilingual labels-namespace reason explains why ("no label
      // template"). The old address-mapping key is NOT used by this gate anymore.
      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
      const notice = screen.getByTestId('member-pivot-labels-unavailable');
      expect(notice).toBeInTheDocument();
      expect(notice).toHaveTextContent('analytics.labels.noTemplate');
      // A degradation (not an empty / error state).
      expect(notice).toHaveAttribute('data-notice-kind', 'degradation');

      // Config/capability gate — NOT a tenant gate: CSV + Mail stay available.
      expect(screen.getByTestId('member-pivot-export-csv')).toBeInTheDocument();
      expect(screen.getByTestId('member-pivot-mail')).toBeInTheDocument();
    });

    it('HIDES the labels action (and the whole slot) when the caller lacks members:export', async () => {
      // Even WITH a label template, no export → the whole result-actions slot is
      // absent, so neither the action nor its degradation notice renders.
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: false } })}
          listTemplates={withLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.queryByTestId('pivot-result-actions')).not.toBeInTheDocument();
      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
      expect(
        screen.queryByTestId('member-pivot-labels-unavailable'),
      ).not.toBeInTheDocument();
    });

    it('does NOT depend on the address mapping: a config with NO mapping but WITH a label template still SHOWS the action (R6 / Property 3)', async () => {
      // THE key Property-3/R6 assertion. The field config has NO address_mapping
      // at all, yet because a label template exists AND the caller may export,
      // the action is OFFERED — proving the gate stopped reading `analytics.*`.
      render(
        <MemberPivotViews
          {...makeProps({
            capabilities: { canExport: true },
            fieldConfig: fieldConfigNoMapping,
          })}
          listTemplates={withLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.getByTestId('member-pivot-labels')).toBeInTheDocument();
      expect(
        screen.queryByTestId('member-pivot-labels-unavailable'),
      ).not.toBeInTheDocument();
    });

    it('does NOT depend on the address mapping: a config WITH a mapping but NO label template still HIDES the action (R6 / Property 3)', async () => {
      // The converse: a resolvable address mapping is present, but there is NO
      // label template — under the OLD gate this would have shown the action;
      // under the NEW gate it is correctly HIDDEN. The mapping is irrelevant.
      render(
        <MemberPivotViews
          {...makeProps({
            capabilities: { canExport: true },
            fieldConfig: fieldConfigWithMapping,
          })}
          listTemplates={withoutLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
      expect(
        screen.getByTestId('member-pivot-labels-unavailable'),
      ).toHaveTextContent('analytics.labels.noTemplate');
    });

    it('fails closed: a non-ok template load hides the action (no crash)', async () => {
      // A failed template load (ok:false) is treated as zero label templates —
      // the action is hidden with the degradation reason, never a crash.
      const failingLoader = vi
        .fn()
        .mockResolvedValue({ ok: false, status: 500, error: 'boom' });
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={failingLoader}
        />,
      );
      await executeAggregate();

      expect(screen.queryByTestId('member-pivot-labels')).not.toBeInTheDocument();
      expect(
        screen.getByTestId('member-pivot-labels-unavailable'),
      ).toBeInTheDocument();
    });

    it('does NOT open the labels modal when the gate is closed (no template)', async () => {
      // The modal mount is gated on `canGenerateLabels`; with no label template
      // there is no action button and the modal / generator never mount.
      render(
        <MemberPivotViews
          {...makeProps({ capabilities: { canExport: true } })}
          listTemplates={withoutLabelTemplate}
        />,
      );
      await executeAggregate();

      expect(screen.queryByTestId('member-pivot-labels-modal')).not.toBeInTheDocument();
      expect(
        screen.queryByTestId('member-labels-panel'),
      ).not.toBeInTheDocument();
    });
  });
});

// ===========================================================================
// Preferred list (R11.2 layer 2) + shared-set capability gating (R11).
// ===========================================================================
describe('MemberPivotViews — preferred list (R11.2)', () => {
  // A caller who may manage sets (members:export) sees the add/remove/reorder
  // controls; the backend gates the preferred-list PUT on export|write.
  const manageProps = () => makeProps({ capabilities: { canExport: true } });

  it('loads the user preferred list on mount (keyed server-side on sub)', async () => {
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalledTimes(1));
    // No sub is passed from the client — the server resolves the principal.
    expect(getPreferredList).toHaveBeenCalledWith();
  });

  it('marks nothing preferred when the user has no preferred list (every row offers Add, none Remove)', async () => {
    // UI REDESIGN: the modal now has a SINGLE "All sets" list — it is NEVER
    // empty (it always lists every available preset), so the old "preferred
    // empty-state" no longer exists. The equivalent assertion of an empty
    // preferred list is that NO row is marked preferred: no row shows a Remove
    // button, and every manageable row shows an Add button.
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    // The single "All sets" list lives in the library modal — open it first.
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    // Nothing is preferred → no Remove / reorder controls anywhere.
    expect(screen.queryByTestId('member-pivot-library-remove')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-up')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-down')).not.toBeInTheDocument();
    // Every row offers Add instead (one Add per listed set).
    const rows = screen.getAllByTestId('member-pivot-library-item');
    const addButtons = screen.getAllByTestId('member-pivot-library-add');
    expect(addButtons).toHaveLength(rows.length);
  });

  it('the dropdown renders preferred refs in order, resolving preset:<key> and set:<id> labels', async () => {
    // UI REDESIGN: the preferred list no longer renders as its own list in the
    // modal — the modal is one "All sets" list. The ordered-ref resolution that
    // this test guarded still drives the DROPDOWN (dropdownSets lists only the
    // preferred refs, in order), so assert the dropdown's options resolve the
    // preset/set labels in the saved order.
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types', 'set:set-7'],
      updated_at: '2026-01-01T00:00:00Z',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    // Wait for both preferred refs to resolve into dropdown options.
    await waitFor(() => {
      const values = Array.from(select.querySelectorAll('option'))
        .map((o) => o.value)
        .filter((v) => v !== ''); // drop the placeholder option
      expect(values).toEqual(['preset:membership-types', 'model:set-7']);
    });
    // The resolved labels (preset i18n key / saved-set name), order preserved.
    const options = Array.from(select.querySelectorAll('option')).filter(
      (o) => o.value !== '',
    );
    expect(options[0]).toHaveTextContent('analytics.pivotViews.presetNames.membershipTypes');
    expect(options[1]).toHaveTextContent('Active seniors');
  });

  it('the dropdown SKIPS a dangling preferred ref (a set another user deleted) silently (R11.6)', async () => {
    // UI REDESIGN: dangling-ref skipping is still relevant to the DROPDOWN —
    // dropdownSets resolves the preferred refs and drops any that no longer
    // exist. set-999 is not in listAnalyticsSets → dangling → skipped, no crash.
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['set:set-999', 'preset:membership-types', 'set:set-7'],
      updated_at: '',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());

    const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
    // Only the two resolvable refs become dropdown options; the dangling one is
    // dropped, order otherwise preserved.
    await waitFor(() => {
      const values = Array.from(select.querySelectorAll('option'))
        .map((o) => o.value)
        .filter((v) => v !== '');
      expect(values).toEqual(['preset:membership-types', 'model:set-7']);
    });
    const values = Array.from(select.querySelectorAll('option'))
      .map((o) => o.value)
      .filter((v) => v !== '');
    expect(values).not.toContain('model:set-999');
  });

  it('adds the selected set to the preferred list (append, no duplicate)', async () => {
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());

    // Adding to the preferred list happens in the "All sets" modal (there is no
    // main-pane quick-add anymore — the dropdown lists only preferred sets).
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    // Add the Jubilees preset from its library row.
    const jubileeRow = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('presetNames.jubilees'))!;
    const add = jubileeRow.querySelector(
      '[data-testid="member-pivot-library-add"]',
    ) as HTMLButtonElement;
    expect(add).not.toBeDisabled();
    fireEvent.click(add);

    await waitFor(() =>
      expect(savePreferredList).toHaveBeenCalledWith(['preset:jubilees']),
    );
    // The jubilees row is now preferred: it swaps its Add for a Remove button.
    await waitFor(() => {
      const nowPreferred = screen
        .getAllByTestId('member-pivot-library-item')
        .find((el) => (el.textContent ?? '').includes('presetNames.jubilees'))!;
      expect(
        nowPreferred.querySelector('[data-testid="member-pivot-library-remove"]'),
      ).toBeTruthy();
      expect(
        nowPreferred.querySelector('[data-testid="member-pivot-library-add"]'),
      ).toBeNull();
    });
  });

  it('maps a saved-set selection (model:<id>) to a set:<id> ref on add', async () => {
    // NEW CONTRACT: a non-preferred saved set is not in the dropdown, so the
    // model:<id> → set:<id> add-mapping is exercised from the library modal's
    // per-row Add (the SAME optionValueToRef/handleAddRef path the dropdown
    // quick-add used). Intent preserved: adding a saved set stores a set:<id> ref.
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
    const addBtn = row.querySelector(
      '[data-testid="member-pivot-library-add"]',
    ) as HTMLButtonElement;
    fireEvent.click(addBtn);

    await waitFor(() => expect(savePreferredList).toHaveBeenCalledWith(['set:set-7']));
  });

  it('an already-preferred set shows Remove (not Add) in the library row', async () => {
    // UI REDESIGN: the Add button is no longer disabled-for-already-added.
    // Instead, an already-preferred row swaps its Add for a Remove button (plus
    // reorder controls) — so it can never be re-added, preserving the old
    // "does not re-add" intent.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
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
      .find((el) => (el.textContent ?? '').includes('presetNames.membershipTypes'))!;
    // No Add on an already-preferred row; it offers Remove instead.
    expect(
      row.querySelector('[data-testid="member-pivot-library-add"]'),
    ).toBeNull();
    expect(
      row.querySelector('[data-testid="member-pivot-library-remove"]'),
    ).toBeTruthy();
  });

  it('removes a ref from the preferred list via the library row Remove', async () => {
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types', 'preset:jubilees'],
      updated_at: '',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    // The single "All sets" list + its Remove controls live in the modal now.
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    // Remove the membership-types set from its library row → the preferred list
    // persists WITHOUT it (jubilees remains).
    const row = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('presetNames.membershipTypes'))!;
    const remove = row.querySelector(
      '[data-testid="member-pivot-library-remove"]',
    ) as HTMLButtonElement;
    fireEvent.click(remove);

    await waitFor(() =>
      expect(savePreferredList).toHaveBeenCalledWith(['preset:jubilees']),
    );
  });

  it('offers permanent Delete ONLY on custom saved sets (not prefab presets)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    // Delete is gated on isAdmin (page rule: Regio_All+CRUD, or Tenant_Admin).
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true, canWrite: true, isAdmin: true } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    // The custom saved set row has a Delete control …
    const savedRow = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
    expect(
      savedRow.querySelector('[data-testid="member-pivot-library-delete"]'),
    ).toBeTruthy();

    // … a prefab preset row does NOT (presets live in code, cannot be deleted).
    const presetRow = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('presetNames.membershipTypes'))!;
    expect(
      presetRow.querySelector('[data-testid="member-pivot-library-delete"]'),
    ).toBeNull();
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
    const del = savedRow.querySelector(
      '[data-testid="member-pivot-library-delete"]',
    ) as HTMLButtonElement;
    fireEvent.click(del);

    // The confirm dialog opens; confirming calls deleteAnalyticsSet with the set id.
    expect(await screen.findByTestId('member-pivot-delete-dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('member-pivot-delete-confirm'));
    await waitFor(() => expect(deleteAnalyticsSet).toHaveBeenCalledWith('set-7'));
  });

  it('hides Delete when the caller lacks write/admin (export-only cannot delete)', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    // export-only: canManageSets true (can add/remove) but canDeleteSets false.
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    // Can still add (manage), but no Delete anywhere.
    expect(screen.getAllByTestId('member-pivot-library-add').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('member-pivot-library-delete')).not.toBeInTheDocument();
  });

  it('runs a preferred set from the dropdown + Execute (modal is manage-only, no Run)', async () => {
    // UI REDESIGN (Option A + manage-only modal): the "All sets" modal no longer
    // has a Run button or reorder arrows — it is purely manage (add / remove /
    // delete). Running happens from the main-pane dropdown (which lists the
    // preferred sets) + Execute.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
      updated_at: '',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());

    // No Run anywhere in the manage modal.
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    expect(screen.queryByTestId('member-pivot-library-run')).not.toBeInTheDocument();
    // No reorder controls either (Option A: dropdown is alphabetical, no manual order).
    expect(screen.queryByTestId('member-pivot-library-up')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-down')).not.toBeInTheDocument();

    // Run the preferred set from the dropdown + Execute.
    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'preset:membership-types' },
    });
    fireEvent.click(screen.getByTestId('member-pivot-execute'));
    const table = await screen.findByTestId('mock-pivot-result-table');
    expect(table).toBeInTheDocument();
    expect(tableCalls.length).toBeGreaterThanOrEqual(1);
    expect(table).toHaveAttribute('data-group-columns', 'membership_type');
  });

  it('degrades to no-preferred when the preferred-list load fails (no crash)', async () => {
    // UI REDESIGN: there is no separate preferred empty-state anymore. A failed
    // preferred-list load degrades to an empty preferred set — the "All sets"
    // list still renders (never a crash) and simply marks nothing preferred (no
    // Remove button on any row).
    getPreferredList.mockRejectedValue(new Error('boom'));
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    // The single "All sets" list lives in the modal — open it to assert it.
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    // Nothing is preferred (the failed load degraded to an empty list).
    expect(screen.queryByTestId('member-pivot-library-remove')).not.toBeInTheDocument();
  });

  it('hides ALL manage controls in the modal for a read-only caller (no export/write)', async () => {
    // canManageSets = canExport || canWrite. A read-only caller (neither) can
    // still OPEN the manage modal and SEE the full list (names), but gets NO
    // Add / Remove / Delete controls (the modal is manage-only; there is no Run
    // in the modal anymore — running is from the dropdown + Execute, gated
    // elsewhere). The list still renders every set by name.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
      updated_at: '',
    });
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    // No mutation / manage controls anywhere for a read-only caller.
    expect(screen.queryByTestId('member-pivot-library-add')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-remove')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-delete')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-up')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-library-down')).not.toBeInTheDocument();
    // The names still render (read-only can browse the library).
    expect(screen.getAllByTestId('member-pivot-library-name').length).toBeGreaterThan(0);
  });
});

// ===========================================================================
// Full library + two-list workflow (issue 2) and localized result headers
// (issue 4).
// ===========================================================================
describe('MemberPivotViews — full library (issue 2)', () => {
  const manageProps = () => makeProps({ capabilities: { canExport: true } });

  it('lists all presets + saved sets ALPHABETICALLY by label', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-1', name: 'Zebra set', kind: 'count' },
      { id: 'set-2', name: 'Alpha set', kind: 'count' },
    ]);
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    // The full library lives in the "All sets" modal now — open it first.
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    const labels = screen
      .getAllByTestId('member-pivot-library-item')
      .map((el) => el.textContent ?? '');
    // The two saved-set names appear and 'Alpha set' sorts before 'Zebra set'.
    const alphaIdx = labels.findIndex((l) => l.includes('Alpha set'));
    const zebraIdx = labels.findIndex((l) => l.includes('Zebra set'));
    expect(alphaIdx).toBeGreaterThanOrEqual(0);
    expect(zebraIdx).toBeGreaterThanOrEqual(0);
    expect(alphaIdx).toBeLessThan(zebraIdx);
    // The whole library is sorted (case-insensitive) by label.
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
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    // The full library + its filter live in the "All sets" modal now.
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

  it('Add to my list from the library moves the item into the preferred list', async () => {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    getPreferredList.mockResolvedValue({ sub: 'u1', refs: [], updated_at: '' });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    // Both lists live in the "All sets" modal now — open it first.
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    // Find the 'Active seniors' library row and click its Add button.
    const row = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
    const addBtn = row.querySelector(
      '[data-testid="member-pivot-library-add"]',
    ) as HTMLButtonElement;
    fireEvent.click(addBtn);

    // It is persisted as a set:<id> ref and the row flips to the preferred
    // controls (Remove replaces Add on that same "Active seniors" row).
    await waitFor(() => expect(savePreferredList).toHaveBeenCalledWith(['set:set-7']));
    await waitFor(() => {
      const nowPreferred = screen
        .getAllByTestId('member-pivot-library-item')
        .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
      expect(
        nowPreferred.querySelector('[data-testid="member-pivot-library-remove"]'),
      ).toBeTruthy();
      expect(
        nowPreferred.querySelector('[data-testid="member-pivot-library-add"]'),
      ).toBeNull();
    });
  });

  it('a preferred preset runs from the dropdown + Execute and produces its result (issue 1)', async () => {
    // UI REDESIGN: running moved OUT of the modal (which is manage-only now).
    // A preferred set is listed in the dropdown; selecting it + Execute runs it.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
      updated_at: '',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    expect(tableCalls).toHaveLength(0);

    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'preset:membership-types' },
    });
    fireEvent.click(screen.getByTestId('member-pivot-execute'));

    const table = await screen.findByTestId('mock-pivot-result-table');
    expect(table).toHaveAttribute('data-group-columns', 'membership_type');
  });

  it('narrows the single "All sets" list by name, keeping preferred rows findable', async () => {
    // UI REDESIGN: there is no longer a SEPARATE preferred list with its own
    // filter — the modal is one "All sets" list filtered by
    // member-pivot-library-filter. Preferred sets live in that same list, so a
    // name filter still narrows to the matching preferred set.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types', 'preset:jubilees'],
      updated_at: '',
    });
    render(<MemberPivotViews {...manageProps()} />);
    await waitFor(() => expect(getPreferredList).toHaveBeenCalled());
    // The single "All sets" list + its filter live in the modal now.
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );

    fireEvent.change(screen.getByTestId('member-pivot-library-filter'), {
      target: { value: 'jubilee' },
    });
    const labels = screen
      .getAllByTestId('member-pivot-library-item')
      .map((el) => el.textContent ?? '');
    // Only the jubilees preset survives the filter (a preferred row), and it is
    // still marked preferred (its Remove control is present).
    expect(labels.every((l) => l.includes('analytics.pivotViews.presetNames.jubilees'))).toBe(
      true,
    );
    const jubileeRow = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('presetNames.jubilees'))!;
    expect(
      jubileeRow.querySelector('[data-testid="member-pivot-library-remove"]'),
    ).toBeTruthy();
  });
});

describe('MemberPivotViews — localized result headers (issue 4)', () => {
  it('passes a columnLabels map that localizes the result headers from fieldConfig', async () => {
    // A Dutch field config: the group column has a Dutch label.
    const nlFieldConfig = {
      fields: [
        { key: 'membership_type', origin: 'fixed', label: { nl: 'Lidtype', en: 'Type' } },
        { key: 'birth_month', origin: 'calculated', label: { en: 'Birth month' } },
        { key: 'years_member', origin: 'calculated', label: { en: 'Years-member' } },
        { key: 'joined_date', origin: 'fixed', label: { en: 'Joined' } },
        { key: 'country', origin: 'fixed', label: { en: 'Country' } },
      ],
    } as unknown as FieldConfig;

    // Seed membership-types as preferred so it is a selectable dropdown option.
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['preset:membership-types'],
      updated_at: '',
    });
    render(
      <MemberPivotViews
        {...makeProps({ fieldConfig: nlFieldConfig, language: 'nl' })}
      />,
    );
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    await waitFor(() => {
      const select = screen.getByTestId('member-pivot-set-select') as HTMLSelectElement;
      const values = Array.from(select.querySelectorAll('option')).map((o) => o.value);
      expect(values).toContain('preset:membership-types');
    });

    fireEvent.change(screen.getByTestId('member-pivot-set-select'), {
      target: { value: 'preset:membership-types' },
    });
    fireEvent.click(screen.getByTestId('member-pivot-execute'));
    await screen.findByTestId('mock-pivot-result-table');

    const produced = tableCalls[tableCalls.length - 1] as unknown as {
      columns: PivotColumnMeta[];
      columnLabels?: Record<string, string>;
    };
    // The group column 'membership_type' maps to its Dutch label; the aggregate
    // 'COUNT(*)' maps to the localized function label (echoed i18n key here).
    expect(produced.columnLabels).toBeDefined();
    expect(produced.columnLabels!['membership_type']).toBe('Lidtype');
    expect(produced.columnLabels!['COUNT(*)']).toBe(
      'analytics.pivotViews.aggregates.COUNT',
    );
  });
});

describe('MemberPivotViews — shared-set capability gating (R11)', () => {
  it('hides ALL set-mutation actions for a read-only caller (no export/write)', async () => {
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: false } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    expect(screen.queryByTestId('member-pivot-set-actions')).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-new-set')).not.toBeInTheDocument();
  });

  it('shows create/edit (New set / Save as / Update) for an export-capable caller', async () => {
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    expect(screen.getByTestId('member-pivot-set-actions')).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-new-set')).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-save-as')).toBeInTheDocument();
    expect(screen.getByTestId('member-pivot-update')).toBeInTheDocument();
  });

  it('shows create/edit for a write-capable caller who cannot export', async () => {
    render(
      <MemberPivotViews
        {...makeProps({ capabilities: { canExport: false, canWrite: true } })}
      />,
    );
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    expect(screen.getByTestId('member-pivot-new-set')).toBeInTheDocument();
  });

  it('hides Delete unless the caller holds write or admin (R11: delete = write|admin)', async () => {
    // Export-only caller: may create but NOT delete.
    render(<MemberPivotViews {...makeProps({ capabilities: { canExport: true } })} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    expect(screen.getByTestId('member-pivot-new-set')).toBeInTheDocument();
    expect(screen.queryByTestId('member-pivot-delete')).not.toBeInTheDocument();
  });

  it('a write-only caller can create/edit but gets NO delete control (modal)', async () => {
    // Delete is gated on isAdmin now (page rule: (Regio_All AND Members_CRUD) OR
    // Tenant_Admin). A plain Members_CRUD / members:write caller — isAdmin false —
    // can create/edit, but the "All sets" modal shows no Delete on any row.
    // (Delete is no longer a main-pane button at all.)
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count' },
    ]);
    render(
      <MemberPivotViews
        {...makeProps({ capabilities: { canExport: true, canWrite: true, isAdmin: false } })}
      />,
    );
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    // Create/edit actions are present in the main pane.
    expect(screen.getByTestId('member-pivot-new-set')).toBeInTheDocument();
    // No main-pane delete button exists anymore.
    expect(screen.queryByTestId('member-pivot-delete')).not.toBeInTheDocument();
    // And the modal shows no Delete control for this non-admin caller.
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
    render(
      <MemberPivotViews
        {...makeProps({ capabilities: { canExport: true, isAdmin: true } })}
      />,
    );
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    // No main-pane delete button (delete lives in the modal now).
    expect(screen.queryByTestId('member-pivot-delete')).not.toBeInTheDocument();
    // The modal's custom-set row offers the Delete control to an admin.
    await openLibrary();
    await waitFor(() =>
      expect(screen.getAllByTestId('member-pivot-library-item').length).toBeGreaterThan(0),
    );
    const savedRow = screen
      .getAllByTestId('member-pivot-library-item')
      .find((el) => (el.textContent ?? '').includes('Active seniors'))!;
    expect(
      savedRow.querySelector('[data-testid="member-pivot-library-delete"]'),
    ).toBeTruthy();
  });
});

// ===========================================================================
// Task 5.4 (R5) — the "Schedule" lifecycle action: gated on the selected set
// having a delivery block AND on the caller's scheduling capability.
// ===========================================================================
describe('MemberPivotViews — schedule action gating (task 5.4 / R5)', () => {
  /**
   * Render with a single saved set (optionally carrying a delivery block) made
   * preferred so `model:<id>` is a selectable dropdown option, then select it.
   */
  async function renderWithSavedSet(
    opts: {
      hasDelivery: boolean;
      capabilities?: MemberAnalyticsCapabilities;
    },
  ) {
    listAnalyticsSets.mockResolvedValue([
      { id: 'set-7', name: 'Active seniors', kind: 'count', hasDelivery: opts.hasDelivery },
    ]);
    getPreferredList.mockResolvedValue({
      sub: 'u1',
      refs: ['set:set-7'],
      updated_at: '',
    });
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

    const schedule = screen.getByTestId('member-pivot-schedule') as HTMLButtonElement;
    // Offered (the caller can schedule) but disabled: a schedule needs a delivery.
    expect(schedule).toBeInTheDocument();
    expect(schedule).toBeDisabled();
    // Clicking the disabled action never fetches the set / opens the editor.
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

    const schedule = screen.getByTestId('member-pivot-schedule') as HTMLButtonElement;
    expect(schedule).not.toBeDisabled();

    fireEvent.click(schedule);
    // It loads the full set + lists the set's schedules, then opens the editor.
    await waitFor(() => expect(getAnalyticsSet).toHaveBeenCalledWith('set-7'));
    await waitFor(() => expect(listSchedulesForSet).toHaveBeenCalledWith('set-7'));
    expect(await screen.findByTestId('member-schedule-editor')).toBeInTheDocument();
  });

  it('HIDES the Schedule action for a region-narrowed write caller (R5 access gate)', async () => {
    // members:write WITHOUT the all-regions grant → isAdmin false → not offered.
    await renderWithSavedSet({
      hasDelivery: true,
      capabilities: { canExport: true, canWrite: true, isAdmin: false },
    });

    expect(screen.queryByTestId('member-pivot-schedule')).not.toBeInTheDocument();
    // But the create/edit actions for a write caller are still present.
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
    listSchedulesForSet.mockResolvedValue([]); // no existing schedule → POST path
    await renderWithSavedSet({ hasDelivery: true });

    fireEvent.click(screen.getByTestId('member-pivot-schedule'));
    await screen.findByTestId('member-schedule-editor');

    fireEvent.click(screen.getByTestId('member-schedule-save'));
    await waitFor(() => expect(createSchedule).toHaveBeenCalledTimes(1));
    // Bound to the open set id, with the default cadence + enabled.
    expect(createSchedule).toHaveBeenCalledWith('set-7', 'monthly', true);
    expect(updateSchedule).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// Mail-spec task 2.4 (R3.1 / R3.2) — the "Deliver now" lifecycle action: RUN a
// saved set's STORED `to_fixed` delivery immediately via the EXISTING SAM
// deliver route (`POST /members/analytics-sets/{id}/deliver`, the frontend
// caller the gap R3.2 closes). Enabled on a selected saved set; the handler
// confirms the set has a `to_fixed` delivery (fetched — the summary carries only
// `hasDelivery`), calls `deliverAnalyticsSet`, surfaces the queued receipt
// (R3.5), and surfaces a refusal (empty recipients / not-certified, R3.4 /
// R4.2 / R5.2) or the "no fixed delivery" guard as an error — never a silent
// no-op.
// ===========================================================================
describe('MemberPivotViews — deliver-now action (mail task 2.4 / R3.1/R3.2)', () => {
  /** Render with a single preferred saved set made selectable, then select it. */
  async function renderWithSavedSet(opts: { hasDelivery: boolean } = { hasDelivery: true }) {
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
    // No selection yet → the action is present (manage caller) but disabled, and
    // a click never calls the deliver route.
    render(<MemberPivotViews {...makeProps()} />);
    await waitFor(() => expect(listAnalyticsSets).toHaveBeenCalled());
    const btn = screen.getByTestId('member-pivot-deliver-now') as HTMLButtonElement;
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    await waitFor(() => expect(deliverAnalyticsSet).not.toHaveBeenCalled());
  });

  // Validates: Requirements 3.1, 3.2, 3.5
  it('calls the EXISTING deliver route for a set with a to_fixed delivery', async () => {
    getAnalyticsSet.mockResolvedValue(toFixedSet);
    await renderWithSavedSet({ hasDelivery: true });

    fireEvent.click(screen.getByTestId('member-pivot-deliver-now'));

    // It resolves the stored delivery (summary carries no mode) then RUNS it via
    // the existing SAM deliver route — the frontend caller R3.2 adds.
    await waitFor(() => expect(getAnalyticsSet).toHaveBeenCalledWith('set-7'));
    await waitFor(() => expect(deliverAnalyticsSet).toHaveBeenCalledWith('set-7'));
  });

  // Validates: Requirements 3.4 (clear reason, not a silent no-op)
  it('does NOT call deliver and warns when the set has no to_fixed delivery', async () => {
    // A per_recipient delivery is NOT deliver-now-able here (that is the separate
    // compose path). The guard surfaces a reason and never hits the deliver route.
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
    await renderWithSavedSet({ hasDelivery: true });

    fireEvent.click(screen.getByTestId('member-pivot-deliver-now'));

    await waitFor(() => expect(getAnalyticsSet).toHaveBeenCalledWith('set-7'));
    // No stored to_fixed delivery to run → the route is NEVER called.
    await waitFor(() => expect(deliverAnalyticsSet).not.toHaveBeenCalled());
  });

  // Validates: Requirements 3.4 (empty-recipients / not-certified refusal surfaces)
  it('surfaces a deliver-route refusal (not-certified 422) without crashing', async () => {
    getAnalyticsSet.mockResolvedValue(toFixedSet);
    // The deliver route refuses BEFORE enqueue (pre-send certification gate):
    // a structured ApiError the component surfaces via applyApiError.
    const { ApiError } = await import('../../../shared/api/ApiError');
    deliverAnalyticsSet.mockRejectedValue(
      new ApiError(422, {
        error: 'The tenant mail sender is not certified',
        code: 'errors.mail.notCertified',
      }),
    );
    await renderWithSavedSet({ hasDelivery: true });

    fireEvent.click(screen.getByTestId('member-pivot-deliver-now'));

    // The run was attempted and the refusal handled (no crash); the action
    // becomes clickable again once the in-flight run settles.
    await waitFor(() => expect(deliverAnalyticsSet).toHaveBeenCalledWith('set-7'));
    await waitFor(() =>
      expect(screen.getByTestId('member-pivot-deliver-now')).not.toBeDisabled(),
    );
  });
});
