/**
 * Unit tests for pivotService — filterSourcesByModule
 *
 * Requirements: 11.6, 11.7
 */

import { filterSourcesByModule } from '../pivotService';
import type { PivotDataSource } from '../../types/pivot';

const SOURCES: PivotDataSource[] = [
  { name: 'vw_mutaties', label: 'Financial Transactions', module: 'FIN' },
  { name: 'vw_bnb_total', label: 'STR Revenue', module: 'STR' },
  { name: 'vw_zzp_invoices', label: 'ZZP Invoices', module: 'ZZP' },
  { name: 'vw_generic', label: 'Generic View', module: null },
];

describe('filterSourcesByModule', () => {
  it('returns only FIN sources when moduleFilter is FIN', () => {
    const result = filterSourcesByModule(SOURCES, 'FIN');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('vw_mutaties');
  });

  it('returns only STR sources when moduleFilter is STR', () => {
    const result = filterSourcesByModule(SOURCES, 'STR');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('vw_bnb_total');
  });

  it('returns only ZZP sources when moduleFilter is ZZP', () => {
    const result = filterSourcesByModule(SOURCES, 'ZZP');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('vw_zzp_invoices');
  });

  it('returns ALL sources when moduleFilter is undefined', () => {
    const result = filterSourcesByModule(SOURCES);
    expect(result).toHaveLength(4);
  });

  it('returns ALL sources when moduleFilter is null', () => {
    const result = filterSourcesByModule(SOURCES, null);
    expect(result).toHaveLength(4);
  });

  it('returns empty array when no sources match the module', () => {
    const sources: PivotDataSource[] = [
      { name: 'vw_mutaties', label: 'Financial Transactions', module: 'FIN' },
    ];
    const result = filterSourcesByModule(sources, 'STR');
    expect(result).toHaveLength(0);
  });

  it('excludes untagged sources when a module filter is active', () => {
    const result = filterSourcesByModule(SOURCES, 'FIN');
    const names = result.map((s) => s.name);
    expect(names).not.toContain('vw_generic');
  });
});
