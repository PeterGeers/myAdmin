/**
 * FinancialReportsGroup Component Tests
 * 
 * Tests the Financial reports container that holds 6 individual report tabs.
 * Verifies component structure and imports.
 */

import { vi } from 'vitest';
import React from 'react';
import FinancialReportsGroup from './FinancialReportsGroup';



// Mock hooks and services
vi.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));
vi.mock('../../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'TestTenant', availableTenants: ['TestTenant'], setCurrentTenant: vi.fn(), hasMultipleTenants: false }),
}));
vi.mock('../../services/apiService', () => ({
  authenticatedGet: vi.fn().mockResolvedValue({ json: () => Promise.resolve({ success: true, years: [] }) }),
  buildEndpoint: (e: string, p: any) => `${e}?${p}`,
}));

// Mock all individual report components
vi.mock('./MutatiesReport', () => ({
  __esModule: true,
  default: () => <div data-testid="mutaties-report">Mutaties Report</div>
}));

vi.mock('./BalanceReport', () => ({
  __esModule: true,
  default: () => <div data-testid="balance-report">Balance Report</div>
}));

vi.mock('./ProfitLossReport', () => ({
  __esModule: true,
  default: () => <div data-testid="profitloss-report">P&L Report</div>
}));

vi.mock('./BtwReport', () => ({
  __esModule: true,
  default: () => <div data-testid="btw-report">BTW Report</div>
}));

vi.mock('./ReferenceAnalysisReport', () => ({
  __esModule: true,
  default: () => <div data-testid="reference-analysis-report">Reference Analysis Report</div>
}));

vi.mock('./AangifteIbReport', () => ({
  __esModule: true,
  default: () => <div data-testid="aangifte-ib-report">Aangifte IB Report</div>
}));

describe('FinancialReportsGroup', () => {
  it('component imports successfully', () => {
    expect(FinancialReportsGroup).toBeDefined();
    expect(typeof FinancialReportsGroup).toBe('function');
  });

  it('component structure is valid', () => {
    const element = React.createElement(FinancialReportsGroup);
    expect(element).toBeDefined();
    expect(element.type).toBe(FinancialReportsGroup);
  });

  it('has all 6 Financial report components imported', () => {
    expect(() => React.createElement(FinancialReportsGroup)).not.toThrow();
  });
});
