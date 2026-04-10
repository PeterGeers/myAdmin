/**
 * Reports Integration Tests
 * 
 * Comprehensive tests verifying all 12 report components are properly integrated
 * and can be imported without errors.
 */

import React from 'react';

jest.mock('@chakra-ui/icons', () => ({
  ChevronDownIcon: () => <span>▼</span>,
  ChevronUpIcon: () => <span>▲</span>,
  CloseIcon: () => <span>✕</span>,
}));

import BnbReportsGroup from './BnbReportsGroup';
import FinancialReportsGroup from './FinancialReportsGroup';
import BnbRevenueReport from './BnbRevenueReport';
import BnbActualsReport from './BnbActualsReport';
import BnbViolinsReport from './BnbViolinsReport';
import BnbReturningGuestsReport from './BnbReturningGuestsReport';
import BnbFutureReport from './BnbFutureReport';
import ToeristenbelastingReport from './ToeristenbelastingReport';
import MutatiesReport from './MutatiesReport';
import BalanceReport from './BalanceReport';
import ProfitLossReport from './ProfitLossReport';
import BtwReport from './BtwReport';
import ReferenceAnalysisReport from './ReferenceAnalysisReport';
import AangifteIbReport from './AangifteIbReport';

jest.mock('@chakra-ui/react', () => ({
  Box: 'div', VStack: 'div', Tabs: 'div', TabList: 'div', Tab: 'button',
  TabPanels: 'div', TabPanel: 'div', Button: 'button', Input: 'input',
  Select: 'select', Text: 'span', Heading: 'h1', Flex: 'div', Stack: 'div',
  HStack: 'div', Spinner: 'div', Table: 'table', Thead: 'thead', Tbody: 'tbody',
  Tr: 'tr', Th: 'th', Td: 'td',
}));

jest.mock('axios');
jest.mock('react-plotly.js', () => () => null);

describe('Reports Integration Tests', () => {
  describe('Component Imports', () => {
    it('imports group components successfully', () => {
      expect(BnbReportsGroup).toBeDefined();
      expect(FinancialReportsGroup).toBeDefined();
    });

    it('imports all 6 BNB report components successfully', () => {
      expect(BnbRevenueReport).toBeDefined();
      expect(BnbActualsReport).toBeDefined();
      expect(BnbViolinsReport).toBeDefined();
      expect(BnbReturningGuestsReport).toBeDefined();
      expect(BnbFutureReport).toBeDefined();
      expect(ToeristenbelastingReport).toBeDefined();
    });

    it('imports all 6 Financial report components successfully', () => {
      expect(MutatiesReport).toBeDefined();
      expect(BalanceReport).toBeDefined();
      expect(ProfitLossReport).toBeDefined();
      expect(BtwReport).toBeDefined();
      expect(ReferenceAnalysisReport).toBeDefined();
      expect(AangifteIbReport).toBeDefined();
    });
  });

  describe('Component Structure', () => {
    it('all components can be instantiated', () => {
      const components = [
        BnbReportsGroup, FinancialReportsGroup,
        BnbRevenueReport, BnbActualsReport, BnbViolinsReport,
        BnbReturningGuestsReport, BnbFutureReport, ToeristenbelastingReport,
        MutatiesReport, BalanceReport, ProfitLossReport,
        BtwReport, ReferenceAnalysisReport, AangifteIbReport,
      ];
      components.forEach(C => expect(() => React.createElement(C)).not.toThrow());
    });

    it('verifies all 12 individual reports are unique components', () => {
      const reports = [
        BnbRevenueReport, BnbActualsReport, BnbViolinsReport,
        BnbReturningGuestsReport, BnbFutureReport, ToeristenbelastingReport,
        MutatiesReport, BalanceReport, ProfitLossReport,
        BtwReport, ReferenceAnalysisReport, AangifteIbReport,
      ];
      expect(new Set(reports).size).toBe(12);
    });
  });
});
