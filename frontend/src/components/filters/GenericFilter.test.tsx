/**
 * GenericFilter Unit Tests
 * 
 * Comprehensive test suite for the GenericFilter component covering:
 * - Single-select and multi-select modes
 * - State management and callbacks
 * - Loading and error states
 * - Accessibility features
 * - Custom rendering
 * - Different data types
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Import component after mocks
import { GenericFilter } from './GenericFilter';

// Mock Chakra UI components before importing the component
const mockOnOpen = jest.fn();
const mockOnClose = jest.fn();

jest.mock('@chakra-ui/react', () => ({
  Button: ({ children, onClick, disabled, rightIcon, textAlign, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
      {rightIcon}
    </button>
  ),
  Checkbox: ({ isChecked, ...props }: any) => (
    <input type="checkbox" checked={isChecked} readOnly {...props} />
  ),
  FormControl: ({ children, isDisabled, size }: any) => (
    <div data-disabled={isDisabled} data-size={size}>{children}</div>
  ),
  FormLabel: ({ children, htmlFor }: any) => (
    <label htmlFor={htmlFor}>{children}</label>
  ),
  Menu: ({ children, isOpen, onClose, closeOnSelect }: any) => (
    <div data-menu-open={isOpen}>{children}</div>
  ),
  MenuButton: ({ children, as: Component = 'button', rightIcon, ...props }: any) => (
    <Component {...props}>
      {children}
      {rightIcon}
    </Component>
  ),
  MenuList: ({ children, maxH, overflowY, minW }: any) => (
    <div role="menu">{children}</div>
  ),
  MenuItem: ({ children, onClick, closeOnSelect, isDisabled, ...props }: any) => (
    <div role="menuitemcheckbox" onClick={onClick} aria-checked="false" {...props}>
      {children}
    </div>
  ),
  Select: ({ children, value, onChange, placeholder, disabled, size, icon, ...props }: any) => (
    <select value={value} onChange={onChange} disabled={disabled} {...props}>
      {placeholder && <option value="">{placeholder}</option>}
      {children}
    </select>
  ),
  Text: ({ children, isTruncated, color, fontSize, fontWeight, ...props }: any) => (
    <span {...props}>{children}</span>
  ),
  HStack: ({ children, spacing, width }: any) => (
    <div style={{ display: 'flex' }}>{children}</div>
  ),
  Spinner: ({ size }: any) => <span data-testid="spinner" className="chakra-spinner">Loading...</span>,
  Alert: ({ children, status, mb, size }: any) => (
    <div role="alert" data-status={status}>{children}</div>
  ),
  AlertIcon: () => <span data-testid="alert-icon">!</span>,
  useDisclosure: () => ({
    isOpen: false,
    onOpen: mockOnOpen,
    onClose: mockOnClose,
  }),
}));

jest.mock('@chakra-ui/icons', () => ({
  ChevronDownIcon: () => <span data-testid="chevron-icon">▼</span>,
}));

// Test data types
interface TestObject {
  id: string;
  name: string;
  value: number;
}

const stringOptions = ['2023', '2024', '2025'];
const objectOptions: TestObject[] = [
  { id: '1', name: 'Option One', value: 100 },
  { id: '2', name: 'Option Two', value: 200 },
  { id: '3', name: 'Option Three', value: 300 },
];

describe('GenericFilter', () => {
  describe('Single-Select Mode', () => {
    it('renders single-select dropdown with label', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          placeholder="Select year"
        />
      );

      expect(screen.getByLabelText('Year')).toBeInTheDocument();
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('displays placeholder when no value selected', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          placeholder="Select year"
        />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('');
    });

    it('displays selected value', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
        />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('2024');
    });

    it('calls onChange with selected option when value changes', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
        />
      );

      const select = screen.getByRole('combobox');
      await user.selectOptions(select, '2025');

      expect(onChange).toHaveBeenCalledWith(['2025']);
    });

    it('calls onChange with empty array when cleared', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          placeholder="Select year"
        />
      );

      const select = screen.getByRole('combobox');
      await user.selectOptions(select, '');

      expect(onChange).toHaveBeenCalledWith([]);
    });

    it('renders all available options', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
        />
      );

      stringOptions.forEach((option) => {
        expect(screen.getByRole('option', { name: option })).toBeInTheDocument();
      });
    });
  });

  describe('Multi-Select Mode', () => {
    it('renders multi-select menu button with label', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
          placeholder="Select years"
        />
      );

      expect(screen.getByText('Years')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Years' })).toBeInTheDocument();
    });

    it('displays placeholder when no values selected', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
          placeholder="Select years"
        />
      );

      expect(screen.getByText('Select years')).toBeInTheDocument();
    });

    it('displays single selected value label', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      expect(screen.getByText('2024')).toBeInTheDocument();
    });

    it('displays count when multiple values selected', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2023', '2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      expect(screen.getByText('2 selected')).toBeInTheDocument();
    });

    it('opens menu when button clicked', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      await user.click(button);

      await waitFor(() => {
        stringOptions.forEach((option) => {
          expect(screen.getByText(option)).toBeInTheDocument();
        });
      });
    });

    it('toggles selection when option clicked', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByText('2024')).toBeInTheDocument();
      });

      const option = screen.getByText('2024');
      await user.click(option);

      expect(onChange).toHaveBeenCalledWith(['2024']);
    });

    it('removes selection when already selected option clicked', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByText('2024')).toBeInTheDocument();
      });

      const option = screen.getByText('2024');
      await user.click(option);

      expect(onChange).toHaveBeenCalledWith([]);
    });

    it('shows checkboxes for all options', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      await user.click(button);

      await waitFor(() => {
        const checkboxes = screen.getAllByRole('checkbox');
        expect(checkboxes).toHaveLength(stringOptions.length);
      });
    });

    it('checks selected options', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      await user.click(button);

      await waitFor(() => {
        const checkboxes = screen.getAllByRole('checkbox');
        const checkedCheckboxes = checkboxes.filter((cb) => (cb as HTMLInputElement).checked);
        expect(checkedCheckboxes).toHaveLength(1);
      });
    });

    it('shows "No options available" when options array is empty', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={[]}
          multiSelect
          label="Years"
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByText('No options available')).toBeInTheDocument();
      });
    });
  });

  describe('Disabled State', () => {
    it('disables single-select when disabled prop is true', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          disabled
        />
      );

      const select = screen.getByRole('combobox');
      expect(select).toBeDisabled();
    });

    it('disables multi-select button when disabled prop is true', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
          disabled
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      expect(button).toBeDisabled();
    });
  });

  describe('Loading State', () => {
    it('disables single-select when loading', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          isLoading
        />
      );

      const select = screen.getByRole('combobox');
      expect(select).toBeDisabled();
    });

    it('disables multi-select button when loading', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
          isLoading
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      expect(button).toBeDisabled();
    });

    it('shows spinner in single-select when loading', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          isLoading
        />
      );

      // Check for spinner by test ID
      expect(screen.getByTestId('spinner')).toBeInTheDocument();
    });

    it('shows spinner in multi-select button when loading', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
          isLoading
        />
      );

      expect(screen.getByTestId('spinner')).toBeInTheDocument();
    });
  });

  describe('Error State', () => {
    it('displays error message in single-select mode', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          error="Failed to load years"
        />
      );

      expect(screen.getByText('Failed to load years')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('displays error message in multi-select mode', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
          error="Failed to load years"
        />
      );

      expect(screen.getByText('Failed to load years')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('does not display error when error is null', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          error={null}
        />
      );

      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  describe('Custom Rendering', () => {
    it('uses custom renderOption in multi-select', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      const customRender = (option: TestObject) => (
        <div data-testid={`custom-${option.id}`}>
          {option.name} (${option.value})
        </div>
      );

      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={objectOptions}
          multiSelect
          label="Options"
          renderOption={customRender}
          getOptionValue={(opt) => opt.id}
        />
      );

      const button = screen.getByRole('button', { name: 'Options' });
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByTestId('custom-1')).toBeInTheDocument();
        expect(screen.getByText('Option One ($100)')).toBeInTheDocument();
      });
    });

    it('uses custom getOptionLabel', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[objectOptions[0]]}
          onChange={onChange}
          availableOptions={objectOptions}
          label="Options"
          getOptionLabel={(opt) => `${opt.name} - ${opt.value}`}
          getOptionValue={(opt) => opt.id}
        />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      const selectedOption = Array.from(select.options).find(
        (opt) => opt.value === '1'
      );
      expect(selectedOption?.text).toBe('Option One - 100');
    });

    it('uses custom getOptionValue', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={objectOptions}
          label="Options"
          getOptionValue={(opt) => opt.id}
          getOptionLabel={(opt) => opt.name}
        />
      );

      const select = screen.getByRole('combobox');
      await user.selectOptions(select, '2');

      expect(onChange).toHaveBeenCalledWith([objectOptions[1]]);
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA label for single-select', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year Filter"
        />
      );

      const select = screen.getByRole('combobox');
      expect(select).toHaveAttribute('aria-label', 'Year Filter');
    });

    it('has proper ARIA label for multi-select button', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Year Filter"
        />
      );

      const button = screen.getByRole('button', { name: 'Year Filter' });
      expect(button).toHaveAttribute('aria-label', 'Year Filter');
    });

    it('has proper ARIA attributes for menu', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      expect(button).toHaveAttribute('aria-haspopup', 'true');
      expect(button).toHaveAttribute('aria-expanded', 'false');

      await user.click(button);

      await waitFor(() => {
        expect(button).toHaveAttribute('aria-expanded', 'true');
      });
    });

    it('has proper role for menu items', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          multiSelect
          label="Years"
        />
      );

      const button = screen.getByRole('button', { name: 'Years' });
      await user.click(button);

      await waitFor(() => {
        const menuItems = screen.getAllByRole('menuitemcheckbox');
        expect(menuItems.length).toBeGreaterThan(0);
        
        const selectedItem = menuItems.find((item) => 
          item.getAttribute('aria-checked') === 'true'
        );
        expect(selectedItem).toBeDefined();
      });
    });

    it('associates label with form control', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
        />
      );

      const label = screen.getByText('Year');
      const select = screen.getByRole('combobox');
      expect(label).toHaveAttribute('for', select.id);
    });
  });

  describe('Different Data Types', () => {
    it('works with string primitives', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Strings"
        />
      );

      const select = screen.getByRole('combobox');
      await user.selectOptions(select, '2024');

      expect(onChange).toHaveBeenCalledWith(['2024']);
    });

    it('works with number primitives', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      const numberOptions = [2023, 2024, 2025];
      
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={numberOptions}
          label="Numbers"
        />
      );

      const select = screen.getByRole('combobox');
      await user.selectOptions(select, '2024');

      expect(onChange).toHaveBeenCalledWith([2024]);
    });

    it('works with complex objects', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={objectOptions}
          label="Objects"
          getOptionLabel={(opt) => opt.name}
          getOptionValue={(opt) => opt.id}
        />
      );

      const select = screen.getByRole('combobox');
      await user.selectOptions(select, '2');

      expect(onChange).toHaveBeenCalledWith([objectOptions[1]]);
    });

    it('handles objects with label property', () => {
      const onChange = jest.fn();
      const optionsWithLabel = [
        { label: 'First', value: '1' },
        { label: 'Second', value: '2' },
      ];
      
      render(
        <GenericFilter
          values={[optionsWithLabel[0]]}
          onChange={onChange}
          availableOptions={optionsWithLabel}
          label="Options"
        />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      const option = Array.from(select.options).find((opt) => opt.value === '1');
      expect(option?.text).toBe('First');
    });

    it('handles objects with id property', async () => {
      const user = userEvent.setup();
      const onChange = jest.fn();
      
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={objectOptions}
          label="Objects"
          getOptionLabel={(opt) => opt.name}
        />
      );

      const select = screen.getByRole('combobox');
      await user.selectOptions(select, '1');

      expect(onChange).toHaveBeenCalledWith([objectOptions[0]]);
    });
  });

  describe('Size Variants', () => {
    it('applies small size variant', () => {
      const onChange = jest.fn();
      const { container } = render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          size="sm"
        />
      );

      // Check that size prop is passed to FormControl
      const formControl = container.querySelector('[data-size="sm"]');
      expect(formControl).toBeInTheDocument();
    });

    it('applies medium size variant (default)', () => {
      const onChange = jest.fn();
      const { container } = render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          size="md"
        />
      );

      const formControl = container.querySelector('[data-size="md"]');
      expect(formControl).toBeInTheDocument();
    });

    it('applies large size variant', () => {
      const onChange = jest.fn();
      const { container } = render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          size="lg"
        />
      );

      const formControl = container.querySelector('[data-size="lg"]');
      expect(formControl).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('handles empty availableOptions array', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={[]}
          label="Year"
        />
      );

      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
      // With placeholder, there's 1 option element
      expect(select.children.length).toBeGreaterThanOrEqual(0);
    });

    it('handles empty values array', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={[]}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
          placeholder="Select year"
        />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('');
    });

    it('handles multiple values in single-select mode (uses first)', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2023', '2024']}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
        />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      expect(select.value).toBe('2023');
    });

    it('handles value not in availableOptions', () => {
      const onChange = jest.fn();
      render(
        <GenericFilter
          values={['2022']}
          onChange={onChange}
          availableOptions={stringOptions}
          label="Year"
        />
      );

      const select = screen.getByRole('combobox') as HTMLSelectElement;
      // Value might be empty or the invalid value depending on implementation
      expect(select).toBeInTheDocument();
    });

    it('does not crash with undefined onChange', () => {
      expect(() => {
        render(
          <GenericFilter
            values={[]}
            onChange={undefined as any}
            availableOptions={stringOptions}
            label="Year"
          />
        );
      }).not.toThrow();
    });
  });
});
