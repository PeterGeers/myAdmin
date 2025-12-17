import {
    createAangifteIbFilterAdapter,
    createActualsFilterAdapter,
    createBtwFilterAdapter,
    createRefAnalysisFilterAdapter
} from './UnifiedAdminYearFilterAdapters';

// Mock fetch for API calls
global.fetch = jest.fn();

describe('UnifiedAdminYearFilter Tab Integration Tests', () => {
  beforeEach(() => {
    (fetch as jest.Mock).mockClear();
  });

  describe('Adapter Configuration Tests', () => {
    it('validates Actuals Dashboard adapter configuration', () => {
      const mockFilters = {
        years: ['2024'],
        administration: 'all',
        displayFormat: '2dec'
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createActualsFilterAdapter(mockFilters, mockSetFilters, availableYears);
      
      expect(adapter.multiSelectYears).toBe(true);
      expect(adapter.showAdministration).toBe(true);
      expect(adapter.showYears).toBe(true);
      expect(adapter.yearValues).toEqual(['2024']);
      expect(adapter.administrationValue).toBe('all');
      expect(adapter.availableYears).toEqual(availableYears);
    });

    it('validates BTW Declaration adapter configuration', () => {
      const btwFilters = { 
        administration: 'GoodwinSolutions', 
        year: '2024', 
        quarter: '1' 
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createBtwFilterAdapter(btwFilters, mockSetFilters, availableYears);
      
      expect(adapter.multiSelectYears).toBe(false); // Single select for BTW
      expect(adapter.showAdministration).toBe(true);
      expect(adapter.showYears).toBe(true);
      expect(adapter.yearValues).toEqual(['2024']);
      expect(adapter.administrationValue).toBe('GoodwinSolutions');
    });

    it('validates Reference Analysis adapter configuration', () => {
      const refFilters = {
        years: ['2024', '2023'],
        administration: 'all',
        referenceNumber: '',
        accounts: [] as string[]
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createRefAnalysisFilterAdapter(refFilters, mockSetFilters, availableYears);
      
      expect(adapter.multiSelectYears).toBe(true);
      expect(adapter.showAdministration).toBe(true);
      expect(adapter.showYears).toBe(true);
      expect(adapter.yearValues).toEqual(['2024', '2023']);
      expect(adapter.administrationValue).toBe('all');
    });

    it('validates Aangifte IB adapter configuration', () => {
      const aangifteFilters = { 
        year: '2024', 
        administration: 'all' 
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createAangifteIbFilterAdapter(aangifteFilters, mockSetFilters, availableYears);
      
      expect(adapter.multiSelectYears).toBe(false); // Single select for Aangifte IB
      expect(adapter.showAdministration).toBe(true);
      expect(adapter.showYears).toBe(true);
      expect(adapter.yearValues).toEqual(['2024']);
      expect(adapter.administrationValue).toBe('all');
    });
  });

  describe('Filter State Management Tests', () => {
    it('handles administration changes in Actuals adapter', () => {
      const mockFilters = {
        years: ['2024'],
        administration: 'all',
        displayFormat: '2dec'
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createActualsFilterAdapter(mockFilters, mockSetFilters, availableYears);
      
      // Simulate administration change
      adapter.onAdministrationChange('GoodwinSolutions');
      
      expect(mockSetFilters).toHaveBeenCalledWith(expect.any(Function));
      
      // Test the function passed to setFilters
      const updateFunction = mockSetFilters.mock.calls[0][0];
      const result = updateFunction(mockFilters);
      expect(result.administration).toBe('GoodwinSolutions');
      expect(result.years).toEqual(['2024']); // Should preserve other properties
    });

    it('handles year changes in multi-select mode (Actuals)', () => {
      const mockFilters = {
        years: ['2024'],
        administration: 'all',
        displayFormat: '2dec'
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createActualsFilterAdapter(mockFilters, mockSetFilters, availableYears);
      
      // Simulate year change (multi-select)
      adapter.onYearChange(['2024', '2023']);
      
      expect(mockSetFilters).toHaveBeenCalledWith(expect.any(Function));
      
      const updateFunction = mockSetFilters.mock.calls[0][0];
      const result = updateFunction(mockFilters);
      expect(result.years).toEqual(['2024', '2023']);
    });

    it('handles year changes in single-select mode (BTW)', () => {
      const btwFilters = { 
        administration: 'GoodwinSolutions', 
        year: '2024', 
        quarter: '1' 
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createBtwFilterAdapter(btwFilters, mockSetFilters, availableYears);
      
      // Simulate year change (single-select)
      adapter.onYearChange(['2023']);
      
      expect(mockSetFilters).toHaveBeenCalledWith(expect.any(Function));
      
      const updateFunction = mockSetFilters.mock.calls[0][0];
      const result = updateFunction(btwFilters);
      expect(result.year).toBe('2023');
      expect(result.quarter).toBe('1'); // Should preserve other properties
    });

    it('handles year changes in single-select mode (Aangifte IB)', () => {
      const aangifteFilters = { 
        year: '2024', 
        administration: 'all' 
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createAangifteIbFilterAdapter(aangifteFilters, mockSetFilters, availableYears);
      
      // Simulate year change (single-select)
      adapter.onYearChange(['2023']);
      
      expect(mockSetFilters).toHaveBeenCalledWith(expect.any(Function));
      
      const updateFunction = mockSetFilters.mock.calls[0][0];
      const result = updateFunction(aangifteFilters);
      expect(result.year).toBe('2023');
      expect(result.administration).toBe('all'); // Should preserve other properties
    });

    it('handles empty year array in single-select mode', () => {
      const aangifteFilters = { 
        year: '2024', 
        administration: 'all' 
      };
      const mockSetFilters = jest.fn();
      const availableYears = ['2022', '2023', '2024', '2025'];

      const adapter = createAangifteIbFilterAdapter(aangifteFilters, mockSetFilters, availableYears);
      
      // Simulate empty year change
      adapter.onYearChange([]);
      
      expect(mockSetFilters).toHaveBeenCalledWith(expect.any(Function));
      
      const updateFunction = mockSetFilters.mock.calls[0][0];
      const result = updateFunction(aangifteFilters);
      // Should default to current year when empty
      expect(result.year).toBe(new Date().getFullYear().toString());
    });
  });

  describe('Administration Options Tests', () => {
    it('provides standard administration options for Actuals', () => {
      const mockFilters = {
        years: ['2024'],
        administration: 'all',
        displayFormat: '2dec'
      };
      const adapter = createActualsFilterAdapter(mockFilters, jest.fn(), []);
      
      expect(adapter.administrationOptions).toEqual([
        { value: 'all', label: 'All' },
        { value: 'GoodwinSolutions', label: 'GoodwinSolutions' },
        { value: 'PeterPrive', label: 'PeterPrive' }
      ]);
    });

    it('provides BTW-specific administration options for BTW', () => {
      const btwFilters = { 
        administration: 'GoodwinSolutions', 
        year: '2024', 
        quarter: '1' 
      };
      const adapter = createBtwFilterAdapter(btwFilters, jest.fn(), []);
      
      expect(adapter.administrationOptions).toEqual([
        { value: 'GoodwinSolutions', label: 'GoodwinSolutions' },
        { value: 'PeterPrive', label: 'PeterPrive' }
      ]);
    });

    it('provides standard administration options for Aangifte IB', () => {
      const aangifteFilters = { 
        year: '2024', 
        administration: 'all' 
      };
      const adapter = createAangifteIbFilterAdapter(aangifteFilters, jest.fn(), []);
      
      expect(adapter.administrationOptions).toEqual([
        { value: 'all', label: 'All' },
        { value: 'GoodwinSolutions', label: 'GoodwinSolutions' },
        { value: 'PeterPrive', label: 'PeterPrive' }
      ]);
    });
  });

  describe('Integration Compatibility Tests', () => {
    it('maintains backward compatibility with existing filter structures', () => {
      // Test that adapters work with the exact filter structures used in myAdminReports
      
      // Actuals filters structure
      const actualsFilters = {
        years: [new Date().getFullYear().toString()],
        administration: 'all',
        displayFormat: '2dec'
      };
      
      const actualsAdapter = createActualsFilterAdapter(
        actualsFilters, 
        jest.fn(), 
        ['2022', '2023', '2024', '2025']
      );
      
      expect(actualsAdapter.yearValues).toEqual(actualsFilters.years);
      expect(actualsAdapter.administrationValue).toBe(actualsFilters.administration);

      // BTW filters structure
      const btwFilters = {
        administration: 'GoodwinSolutions',
        year: new Date().getFullYear().toString(),
        quarter: '1'
      };
      
      const btwAdapter = createBtwFilterAdapter(
        btwFilters, 
        jest.fn(), 
        ['2022', '2023', '2024', '2025']
      );
      
      expect(btwAdapter.yearValues).toEqual([btwFilters.year]);
      expect(btwAdapter.administrationValue).toBe(btwFilters.administration);

      // Aangifte IB filters structure
      const aangifteIbFilters = {
        year: new Date().getFullYear().toString(),
        administration: 'all'
      };
      
      const aangifteAdapter = createAangifteIbFilterAdapter(
        aangifteIbFilters, 
        jest.fn(), 
        ['2022', '2023', '2024', '2025']
      );
      
      expect(aangifteAdapter.yearValues).toEqual([aangifteIbFilters.year]);
      expect(aangifteAdapter.administrationValue).toBe(aangifteIbFilters.administration);
    });

    it('ensures all required adapter properties are present', () => {
      const requiredProperties = [
        'administrationValue',
        'onAdministrationChange',
        'administrationOptions',
        'yearValues',
        'onYearChange',
        'availableYears',
        'multiSelectYears',
        'showAdministration',
        'showYears'
      ];

      const mockFilters = { years: ['2024'], administration: 'all', displayFormat: '2dec' };
      const adapter = createActualsFilterAdapter(mockFilters, jest.fn(), ['2024']);

      requiredProperties.forEach(prop => {
        expect(adapter).toHaveProperty(prop);
      });
    });

    it('validates that callbacks are functions', () => {
      const mockFilters = { years: ['2024'], administration: 'all', displayFormat: '2dec' };
      const adapter = createActualsFilterAdapter(mockFilters, jest.fn(), ['2024']);

      expect(typeof adapter.onAdministrationChange).toBe('function');
      expect(typeof adapter.onYearChange).toBe('function');
    });
  });

  describe('Data Flow Integration Tests', () => {
    it('simulates complete filter change workflow for Aangifte IB', () => {
      let currentFilters = {
        year: '2024',
        administration: 'all'
      };

      const setFilters = (updater: any) => {
        if (typeof updater === 'function') {
          currentFilters = updater(currentFilters);
        } else {
          currentFilters = updater;
        }
      };

      const availableYears = ['2022', '2023', '2024', '2025'];
      
      // Create adapter
      let adapter = createAangifteIbFilterAdapter(currentFilters, setFilters, availableYears);
      
      // Simulate administration change
      adapter.onAdministrationChange('GoodwinSolutions');
      expect(currentFilters.administration).toBe('GoodwinSolutions');
      expect(currentFilters.year).toBe('2024'); // Should preserve year
      
      // Recreate adapter with updated filters (simulating re-render)
      adapter = createAangifteIbFilterAdapter(currentFilters, setFilters, availableYears);
      
      // Simulate year change
      adapter.onYearChange(['2023']);
      expect(currentFilters.year).toBe('2023');
      expect(currentFilters.administration).toBe('GoodwinSolutions'); // Should preserve administration
      
      // Final state check
      expect(currentFilters).toEqual({
        year: '2023',
        administration: 'GoodwinSolutions'
      });
    });
  });
});