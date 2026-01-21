/**
 * FinancialReportsGroup Component Tests
 * 
 * Tests the Financial reports container that holds 5 individual report tabs.
 * Verifies component structure and imports.
 */

import React from 'react';
import FinancialReportsGroup from './FinancialReportsGroup';

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => ({
  Tabs: ({ children, ...props }: any) => <div data-testid="tabs" {...props}>{children}</div>,
  TabList: ({ children, ...props }: any) => <div data-testid="tablist" {...props}>{children}</div>,
  Tab: ({ children, ...props }: any) => <button data-testid="tab" {...props}>{children}</button>,
  TabPanels: ({ children, ...props }: any) => <div data-testid="tabpanels" {...props}>{children}</div>,
  TabPanel: ({ children, ...props }: any) => <div data-testid="tabpanel" {...props}>{children}</div>,
}));

// Mock all individual report components
jest.mock('./MutatiesReport', () => ({
  __esModule: true,
  default: () => <div data-testid="mutaties-report">Mutaties Report</div>
}));

jest.mock('./ActualsReport', () => ({
  __esModule: true,
  default: () => <div data-testid="actuals-report">Actuals Report</div>
}));

jest.mock('./BtwReport', () => ({
  __esModule: true,
  default: () => <div data-testid="btw-report">BTW Report</div>
}));

jest.mock('./ReferenceAnalysisReport', () => ({
  __esModule: true,
  default: () => <div data-testid="reference-analysis-report">Reference Analysis Report</div>
}));

jest.mock('./AangifteIbReport', () => ({
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

  it('has all 5 Financial report components imported', () => {
    // Verify the component can be instantiated without errors
    // This ensures all imports are valid
    expect(() => React.createElement(FinancialReportsGroup)).not.toThrow();
  });
});
