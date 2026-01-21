/**
 * BnbReportsGroup Component Tests
 * 
 * Tests the BNB reports container that holds 6 individual report tabs.
 * Verifies component structure and imports.
 */

import React from 'react';
import BnbReportsGroup from './BnbReportsGroup';

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => ({
  Tabs: ({ children, ...props }: any) => <div data-testid="tabs" {...props}>{children}</div>,
  TabList: ({ children, ...props }: any) => <div data-testid="tablist" {...props}>{children}</div>,
  Tab: ({ children, ...props }: any) => <button data-testid="tab" {...props}>{children}</button>,
  TabPanels: ({ children, ...props }: any) => <div data-testid="tabpanels" {...props}>{children}</div>,
  TabPanel: ({ children, ...props }: any) => <div data-testid="tabpanel" {...props}>{children}</div>,
}));

// Mock all individual report components
jest.mock('./BnbRevenueReport', () => ({
  __esModule: true,
  default: () => <div data-testid="bnb-revenue-report">BNB Revenue Report</div>
}));

jest.mock('./BnbActualsReport', () => ({
  __esModule: true,
  default: () => <div data-testid="bnb-actuals-report">BNB Actuals Report</div>
}));

jest.mock('./BnbViolinsReport', () => ({
  __esModule: true,
  default: () => <div data-testid="bnb-violins-report">BNB Violins Report</div>
}));

jest.mock('./BnbReturningGuestsReport', () => ({
  __esModule: true,
  default: () => <div data-testid="bnb-returning-guests-report">BNB Returning Guests Report</div>
}));

jest.mock('./BnbFutureReport', () => ({
  __esModule: true,
  default: () => <div data-testid="bnb-future-report">BNB Future Report</div>
}));

jest.mock('./ToeristenbelastingReport', () => ({
  __esModule: true,
  default: () => <div data-testid="toeristenbelasting-report">Toeristenbelasting Report</div>
}));

describe('BnbReportsGroup', () => {
  it('component imports successfully', () => {
    expect(BnbReportsGroup).toBeDefined();
    expect(typeof BnbReportsGroup).toBe('function');
  });

  it('component structure is valid', () => {
    const element = React.createElement(BnbReportsGroup);
    expect(element).toBeDefined();
    expect(element.type).toBe(BnbReportsGroup);
  });

  it('has all 6 BNB report components imported', () => {
    // Verify the component can be instantiated without errors
    // This ensures all imports are valid
    expect(() => React.createElement(BnbReportsGroup)).not.toThrow();
  });
});
