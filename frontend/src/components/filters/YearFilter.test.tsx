/**
 * YearFilter Unit Tests
 * 
 * Test suite for the YearFilter component covering:
 * - Single-select mode (BTW, Aangifte IB)
 * - Multi-select mode (Actuals, BNB)
 * - Default labels and placeholders
 * - Year generation integration
 * - Backward compatibility
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { YearFilter } from './YearFilter';

// Mock Chakra UI icons
jest.mock('@chakra-ui/icons', () => ({
  ChevronDownIcon: () => <span>▼</span>,
}));

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => {
  const React = require('react');
  
  // Create a simple context for FormControl disabled state
  const FormControlContext = React.createContext({ isDisabled: false });
  
  return {
    Button: ({ 
      children, 
      onClick, 
      disabled, 
      isDisabled,
      isLoading,
      rightIcon, 
      ...props 
    }: any) => {
      const isActuallyDisabled = disabled || isDisabled || isLoading;
      return (
        <button 
          onClick={isActuallyDisabled ? undefined : onClick} 
          disabled={isActuallyDisabled}
          data-loading={isLoading}
          {...props}
        >
          {children}
          {rightIcon}
        </button>
      );
    },
    Checkbox: ({ isChecked, onChange, ...props }: any) => (
      <input type="checkbox" checked={isChecked} onChange={onChange} {...props} />
    ),
    FormControl: ({ children, isDisabled, ...props }: any) => {
      return (
        <FormControlContext.Provider value={{ isDisabled: isDisabled || false }}>
          <div data-disabled={isDisabled} {...props}>
            {children}
          </div>
        </FormControlContext.Provider>
      );
    },
    FormLabel: ({ children, ...props }: any) => <label {...props}>{children}</label>,
    Select: ({ children, value, onChange, placeholder, disabled, isDisabled, icon, ...props }: any) => {
      const React = require('react');
      const FormControlContext = React.createContext({ isDisabled: false });
      const context = React.useContext(FormControlContext);
      const isActuallyDisabled = disabled || isDisabled || context.isDisabled;
      return (
        <select value={value} onChange={onChange} disabled={isActuallyDisabled} {...props}>
          {placeholder && <option value="">{placeholder}</option>}
          {children}
        </select>
      );
    },
    Menu: ({ children, isOpen, onClose }: any) => {
      const [open, setOpen] = React.useState(isOpen);
      React.useEffect(() => setOpen(isOpen), [isOpen]);
      return <div data-menu-open={open}>{children}</div>;
    },
    MenuButton: React.forwardRef(({ children, onClick, ...props }: any, ref: any) => (
      <button ref={ref} onClick={onClick} {...props}>{children}</button>
    )),
    MenuList: ({ children, ...props }: any) => <div role="menu" {...props}>{children}</div>,
    MenuItem: ({ children, onClick, ...props }: any) => (
      <div role="menuitem" onClick={onClick} {...props}>{children}</div>
    ),
    Text: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    HStack: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    Spinner: () => <div data-testid="spinner">Loading...</div>,
    Alert: ({ children, ...props }: any) => <div role="alert" {...props}>{children}</div>,
    AlertIcon: () => <span>⚠️</span>,
    ChevronDownIcon: () => <span>▼</span>,
    useDisclosure: () => ({
      isOpen: false,
      onOpen: jest.fn(),
      onClose: jest.fn(),
    }),
  };
});

describe('YearFilter', () => {
  const mockYears = ['2022', '2023', '2024', '2025'];
  
  describe('Single-Select Mode', () => {
    it('renders with default label "Year"', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
        />
      );
      
      expect(screen.getByText('Year')).toBeInTheDocument();
    });
    
    it('renders with default placeholder "Select year"', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
        />
      );
      
      expect(screen.getByRole('combobox')).toHaveTextContent('Select year');
    });
    
    it('renders with custom label', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          label="Tax Year"
        />
      );
      
      expect(screen.getByText('Tax Year')).toBeInTheDocument();
    });
    
    it('renders with custom placeholder', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          placeholder="Choose a year"
        />
      );
      
      expect(screen.getByRole('combobox')).toHaveTextContent('Choose a year');
    });
    
    it('displays all available years as options', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
        />
      );
      
      const select = screen.getByRole('combobox');
      mockYears.forEach(year => {
        expect(select).toHaveTextContent(year);
      });
    });
    
    it('calls onChange with selected year', async () => {
      const user = userEvent.setup();
      const handleChange = jest.fn();
      
      render(
        <YearFilter
          values={[]}
          onChange={handleChange}
          availableOptions={mockYears}
        />
      );
      
      const select = screen.getByRole('combobox');
      await user.selectOptions(select, '2024');
      
      expect(handleChange).toHaveBeenCalledWith(['2024']);
    });
    
    it('displays selected year', () => {
      render(
        <YearFilter
          values={['2024']}
          onChange={jest.fn()}
          availableOptions={mockYears}
        />
      );
      
      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('2024');
    });
  });
  
  describe('Multi-Select Mode', () => {
    it('renders with default placeholder "Select year(s)"', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          multiSelect
        />
      );
      
      expect(screen.getByRole('button')).toHaveTextContent('Select year(s)');
    });
    
    it('displays selected year count for multiple selections', () => {
      render(
        <YearFilter
          values={['2023', '2024']}
          onChange={jest.fn()}
          availableOptions={mockYears}
          multiSelect
        />
      );
      
      expect(screen.getByRole('button')).toHaveTextContent('2 selected');
    });
    
    it('displays single year when one is selected', () => {
      render(
        <YearFilter
          values={['2024']}
          onChange={jest.fn()}
          availableOptions={mockYears}
          multiSelect
        />
      );
      
      expect(screen.getByRole('button')).toHaveTextContent('2024');
    });
  });
  
  describe('Year Generation Integration', () => {
    it('generates historical years when yearConfig is provided', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={[]}
          yearConfig={{
            mode: 'historical',
            historicalYears: ['2020', '2021', '2022']
          }}
        />
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toHaveTextContent('2020');
      expect(select).toHaveTextContent('2021');
      expect(select).toHaveTextContent('2022');
    });
    
    it('generates future years when yearConfig is provided', () => {
      const currentYear = new Date().getFullYear();
      
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={[]}
          yearConfig={{
            mode: 'future',
            futureCount: 2
          }}
        />
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toHaveTextContent(currentYear.toString());
      expect(select).toHaveTextContent((currentYear + 1).toString());
      expect(select).toHaveTextContent((currentYear + 2).toString());
    });
    
    it('prefers yearConfig over availableOptions', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={['2030', '2031']}
          yearConfig={{
            mode: 'historical',
            historicalYears: ['2020', '2021']
          }}
        />
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toHaveTextContent('2020');
      expect(select).toHaveTextContent('2021');
      expect(select).not.toHaveTextContent('2030');
    });
  });
  
  describe('Loading and Error States', () => {
    it('shows loading indicator in single-select mode', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          isLoading
        />
      );
      
      // In single-select mode, loading is shown via icon, not a separate spinner
      const select = screen.getByRole('combobox');
      expect(select.parentElement).toHaveAttribute('data-disabled', 'true');
    });
    
    it('shows loading indicator in multi-select mode', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          multiSelect
          isLoading
        />
      );
      
      // In multi-select mode, the button should be disabled when loading
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });
    
    it('shows error message', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          error="Failed to load years"
        />
      );
      
      expect(screen.getByRole('alert')).toHaveTextContent('Failed to load years');
    });
    
    it('disables filter when disabled prop is true', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          disabled
        />
      );
      
      // Check that the FormControl wrapper is disabled
      const select = screen.getByRole('combobox');
      const formControl = select.parentElement;
      expect(formControl).toHaveAttribute('data-disabled', 'true');
    });
    
    it('disables filter when isLoading is true', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          isLoading
        />
      );
      
      // When loading, the FormControl is disabled
      const select = screen.getByRole('combobox');
      expect(select.parentElement).toHaveAttribute('data-disabled', 'true');
    });
  });
  
  describe('Backward Compatibility', () => {
    it('works with BTW report pattern (single-select)', () => {
      const handleChange = jest.fn();
      const selectedYear = '2024';
      
      render(
        <YearFilter
          values={selectedYear ? [selectedYear] : []}
          onChange={(values) => handleChange(values[0] || '')}
          availableOptions={mockYears}
        />
      );
      
      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('2024');
    });
    
    it('works with Actuals report pattern (multi-select)', () => {
      const selectedYears = ['2023', '2024'];
      
      render(
        <YearFilter
          values={selectedYears}
          onChange={jest.fn()}
          availableOptions={mockYears}
          multiSelect
        />
      );
      
      expect(screen.getByRole('button')).toHaveTextContent('2 selected');
    });
  });
  
  describe('Accessibility', () => {
    it('has accessible label', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
        />
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toHaveAttribute('aria-label', 'Year');
    });
    
    it('uses custom label for aria-label', () => {
      render(
        <YearFilter
          values={[]}
          onChange={jest.fn()}
          availableOptions={mockYears}
          label="Tax Year"
        />
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toHaveAttribute('aria-label', 'Tax Year');
    });
  });
});
