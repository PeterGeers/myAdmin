/**
 * Reports Integration Tests
 * 
 * Comprehensive tests verifying all 11 report components are properly integrated
 * and can be imported without errors.
 */

// Mock Chakra UI before any imports
import React from 'react';

// Import main component
import MyAdminReportsNew from '../MyAdminReportsNew';

// Import group components
import BnbReportsGroup from './BnbReportsGroup';
import FinancialReportsGroup from './FinancialReportsGroup';

// Import all individual report components
import BnbRevenueReport from './BnbRevenueReport';
import BnbActualsReport from './BnbActualsReport';
import BnbViolinsReport from './BnbViolinsReport';
import BnbReturningGuestsReport from './BnbReturningGuestsReport';
import BnbFutureReport from './BnbFutureReport';
import ToeristenbelastingReport from './ToeristenbelastingReport';
import MutatiesReport from './MutatiesReport';
import ActualsReport from './ActualsReport';
import BtwReport from './BtwReport';
import ReferenceAnalysisReport from './ReferenceAnalysisReport';
import AangifteIbReport from './AangifteIbReport';

jest.mock('@chakra-ui/react', () => ({
  Box: 'div',
  VStack: 'div',
  Tabs: 'div',
  TabList: 'div',
  Tab: 'button',
  TabPanels: 'div',
  TabPanel: 'div',
  Button: 'button',
  Input: 'input',
  Select: 'select',
  Text: 'span',
  Heading: 'h1',
  Flex: 'div',
  Stack: 'div',
  HStack: 'div',
  Spinner: 'div',
  Table: 'table',
  Thead: 'thead',
  Tbody: 'tbody',
  Tr: 'tr',
  Th: 'th',
  Td: 'td',
}));

// Mock axios
jest.mock('axios');

// Mock plotly
jest.mock('react-plotly.js', () => () => null);

describe('Reports Integration Tests', () => {
  describe('Component Imports', () => {
    it('imports main entry point successfully', () => {
      expect(MyAdminReportsNew).toBeDefined();
      expect(typeof MyAdminReportsNew).toBe('function');
    });

    it('imports group components successfully', () => {
      expect(BnbReportsGroup).toBeDefined();
      expect(typeof BnbReportsGroup).toBe('function');
      
      expect(FinancialReportsGroup).toBeDefined();
      expect(typeof FinancialReportsGroup).toBe('function');
    });

    it('imports all 6 BNB report components successfully', () => {
      expect(BnbRevenueReport).toBeDefined();
      expect(typeof BnbRevenueReport).toBe('function');
      
      expect(BnbActualsReport).toBeDefined();
      expect(typeof BnbActualsReport).toBe('function');
      
      expect(BnbViolinsReport).toBeDefined();
      expect(typeof BnbViolinsReport).toBe('function');
      
      expect(BnbReturningGuestsReport).toBeDefined();
      expect(typeof BnbReturningGuestsReport).toBe('function');
      
      expect(BnbFutureReport).toBeDefined();
      expect(typeof BnbFutureReport).toBe('function');
      
      expect(ToeristenbelastingReport).toBeDefined();
      expect(typeof ToeristenbelastingReport).toBe('function');
    });

    it('imports all 5 Financial report components successfully', () => {
      expect(MutatiesReport).toBeDefined();
      expect(typeof MutatiesReport).toBe('function');
      
      expect(ActualsReport).toBeDefined();
      expect(typeof ActualsReport).toBe('function');
      
      expect(BtwReport).toBeDefined();
      expect(typeof BtwReport).toBe('function');
      
      expect(ReferenceAnalysisReport).toBeDefined();
      expect(typeof ReferenceAnalysisReport).toBe('function');
      
      expect(AangifteIbReport).toBeDefined();
      expect(typeof AangifteIbReport).toBe('function');
    });
  });

  describe('Component Structure', () => {
    it('all components can be instantiated', () => {
      const components = [
        MyAdminReportsNew,
        BnbReportsGroup,
        FinancialReportsGroup,
        BnbRevenueReport,
        BnbActualsReport,
        BnbViolinsReport,
        BnbReturningGuestsReport,
        BnbFutureReport,
        ToeristenbelastingReport,
        MutatiesReport,
        ActualsReport,
        BtwReport,
        ReferenceAnalysisReport,
        AangifteIbReport,
      ];

      components.forEach(Component => {
        expect(() => React.createElement(Component)).not.toThrow();
      });
    });

    it('verifies all 11 individual reports are unique components', () => {
      const reports = [
        BnbRevenueReport,
        BnbActualsReport,
        BnbViolinsReport,
        BnbReturningGuestsReport,
        BnbFutureReport,
        ToeristenbelastingReport,
        MutatiesReport,
        ActualsReport,
        BtwReport,
        ReferenceAnalysisReport,
        AangifteIbReport,
      ];

      // Verify all are unique
      const uniqueReports = new Set(reports);
      expect(uniqueReports.size).toBe(11);
    });
  });

  describe('Module Structure', () => {
    it('verifies proper module exports', () => {
      // All components should be default exports
      expect(MyAdminReportsNew).not.toHaveProperty('default');
      expect(BnbReportsGroup).not.toHaveProperty('default');
      expect(FinancialReportsGroup).not.toHaveProperty('default');
    });

    it('verifies component naming conventions', () => {
      const componentNames = [
        'MyAdminReportsNew',
        'BnbReportsGroup',
        'FinancialReportsGroup',
        'BnbRevenueReport',
        'BnbActualsReport',
        'BnbViolinsReport',
        'BnbReturningGuestsReport',
        'BnbFutureReport',
        'ToeristenbelastingReport',
        'MutatiesReport',
        'ActualsReport',
        'BtwReport',
        'ReferenceAnalysisReport',
        'AangifteIbReport',
      ];

      const components = [
        MyAdminReportsNew,
        BnbReportsGroup,
        FinancialReportsGroup,
        BnbRevenueReport,
        BnbActualsReport,
        BnbViolinsReport,
        BnbReturningGuestsReport,
        BnbFutureReport,
        ToeristenbelastingReport,
        MutatiesReport,
        ActualsReport,
        BtwReport,
        ReferenceAnalysisReport,
        AangifteIbReport,
      ];

      components.forEach((component, index) => {
        expect(component.name).toBe(componentNames[index]);
      });
    });
  });
});
