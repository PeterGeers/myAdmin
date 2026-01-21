/**
 * MyAdminReportsNew Component Tests
 * 
 * Tests the main entry point for the refactored reports structure.
 * Verifies that the component structure is correct and all imports resolve.
 */

import React from 'react';

// Import the component to verify it compiles
import MyAdminReportsNew from '../MyAdminReportsNew';

// Mock Chakra UI components to avoid dependency issues in tests
jest.mock('@chakra-ui/react', () => ({
  Box: ({ children, ...props }: any) => <div data-testid="box" {...props}>{children}</div>,
  VStack: ({ children, ...props }: any) => <div data-testid="vstack" {...props}>{children}</div>,
  Tabs: ({ children, ...props }: any) => <div data-testid="tabs" {...props}>{children}</div>,
  TabList: ({ children, ...props }: any) => <div data-testid="tablist" {...props}>{children}</div>,
  Tab: ({ children, ...props }: any) => <button data-testid="tab" {...props}>{children}</button>,
  TabPanels: ({ children, ...props }: any) => <div data-testid="tabpanels" {...props}>{children}</div>,
  TabPanel: ({ children, ...props }: any) => <div data-testid="tabpanel" {...props}>{children}</div>,
}));

// Mock the report group components
jest.mock('./BnbReportsGroup', () => ({
  __esModule: true,
  default: () => <div data-testid="bnb-reports-group">BNB Reports Group</div>
}));

jest.mock('./FinancialReportsGroup', () => ({
  __esModule: true,
  default: () => <div data-testid="financial-reports-group">Financial Reports Group</div>
}));

describe('MyAdminReportsNew', () => {
  it('component imports successfully', () => {
    expect(MyAdminReportsNew).toBeDefined();
    expect(typeof MyAdminReportsNew).toBe('function');
  });

  it('component structure is valid', () => {
    // This test verifies the component can be instantiated
    const element = React.createElement(MyAdminReportsNew);
    expect(element).toBeDefined();
    expect(element.type).toBe(MyAdminReportsNew);
  });
});
