/**
 * Focused tests for useMemberPivotExport.ts - the result-column labels, export
 * row selection, content gates and CSV builders (network mocks where needed).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const api = vi.hoisted(() => ({ sendAdHocMail: vi.fn(), recordAnalyticsOutput: vi.fn() }));
vi.mock('../../../services/membersApiService', () => ({ sendAdHocMail: api.sendAdHocMail }));
vi.mock('../../../services/memberAnalyticsAuditService', () => ({
  recordAnalyticsOutput: api.recordAnalyticsOutput,
}));

import { useMemberPivotExport } from './useMemberPivotExport';

type Args = Parameters<typeof useMemberPivotExport>[0];

const baseArgs = (over: Partial<Args> = {}): Args => ({
  result: {
    columns: [
      { name: 'region', type: 'group' },
      { name: 'COUNT(age)', type: 'aggregate' },
    ],
    data: [{ region: 'N', 'COUNT(age)': 3 }],
  } as unknown as Args['result'],
  resultConfig: {} as unknown as Args['resultConfig'],
  selectedSet: undefined,
  fieldConfig: {
    fields: [
      { key: 'region', label: { nl: 'Regio', en: 'Region' } },
      { key: 'age', label: { nl: 'Leeftijd', en: 'Age' } },
    ],
    mail_enabled: true,
  } as unknown as Args['fieldConfig'],
  language: 'nl',
  capabilities: { canExport: true } as unknown as Args['capabilities'],
  labelTemplates: [],
  currentTenant: 't1',
  visibleRows: [],
  t: ((key: string) => key) as Args['t'],
  ...over,
});

const render = (over: Partial<Args> = {}) =>
  renderHook(() => useMemberPivotExport(baseArgs(over))).result.current;

beforeEach(() => {
  api.sendAdHocMail.mockReset();
  api.recordAnalyticsOutput.mockReset();
});

describe('useMemberPivotExport', () => {
  it('builds localized result column labels (group label + aggregate fn + inner)', () => {
    expect(render().columnLabels).toEqual({
      region: 'Regio',
      'COUNT(age)': 'analytics.pivotViews.aggregates.COUNT (Leeftijd)',
    });
  });

  it('returns {} column labels when there is no result config', () => {
    expect(render({ resultConfig: null }).columnLabels).toEqual({});
  });

  it('exports the visible rows when the table reports them, else the full result data', () => {
    const visible = [{ region: 'X' }];
    expect(render({ visibleRows: visible }).exportRows).toBe(visible);
    expect(render({ visibleRows: [] }).exportRows).toEqual([{ region: 'N', 'COUNT(age)': 3 }]);
  });

  it('gates canGenerateLabels on canExport AND at least one label template', () => {
    const template = {} as Args['labelTemplates'][number];
    expect(
      render({ capabilities: { canExport: true } as unknown as Args['capabilities'], labelTemplates: [template] })
        .canGenerateLabels,
    ).toBe(true);
    expect(
      render({ capabilities: { canExport: false } as unknown as Args['capabilities'], labelTemplates: [template] })
        .canGenerateLabels,
    ).toBe(false);
    expect(
      render({ capabilities: { canExport: true } as unknown as Args['capabilities'], labelTemplates: [] })
        .canGenerateLabels,
    ).toBe(false);
  });

  it('mailEnabled follows fieldConfig.mail_enabled === true (fail-closed)', () => {
    expect(render().mailEnabled).toBe(true);
    expect(render({ fieldConfig: { fields: [] } as unknown as Args['fieldConfig'] }).mailEnabled).toBe(false);
    expect(render({ fieldConfig: null }).mailEnabled).toBe(false);
  });

  it('buildCsvBase64 is null without a result and a non-empty string with one', () => {
    expect(render({ result: null }).buildCsvBase64()).toBeNull();
    expect(
      render({ result: { columns: [], data: [] } as unknown as Args['result'] }).buildCsvBase64(),
    ).toBeNull();
    const b64 = render().buildCsvBase64();
    expect(typeof b64).toBe('string');
    expect((b64 as string).length).toBeGreaterThan(0);
  });

  it('csvMailValid is true only for a non-empty list of valid addresses', () => {
    const at = String.fromCharCode(64);
    const { result } = renderHook(() => useMemberPivotExport(baseArgs()));
    expect(result.current.csvMailValid).toBe(false);
    act(() => result.current.setCsvMailTo(`a${at}b.com, c${at}d.com`));
    expect(result.current.csvMailValid).toBe(true);
    act(() => result.current.setCsvMailTo('nope'));
    expect(result.current.csvMailValid).toBe(false);
  });

  it('handleOpenCsvMail clears the input and opens the dialog', () => {
    const { result } = renderHook(() => useMemberPivotExport(baseArgs()));
    act(() => result.current.setCsvMailTo('x'));
    act(() => result.current.handleOpenCsvMail());
    expect(result.current.isCsvMailOpen).toBe(true);
    expect(result.current.csvMailTo).toBe('');
  });
});
