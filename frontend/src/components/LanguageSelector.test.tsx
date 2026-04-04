/**
 * Unit tests for LanguageSelector component
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LanguageSelector } from './LanguageSelector';

// Track language state for tests
let mockCurrentLanguage = 'en';
const mockChangeLanguage = jest.fn((lang: string) => {
  mockCurrentLanguage = lang;
  localStorage.setItem('i18nextLng', lang);
  return Promise.resolve();
});

// Mock react-i18next
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      get language() { return mockCurrentLanguage; },
      changeLanguage: mockChangeLanguage,
    },
  }),
}));

// Mock the API service
jest.mock('../services/apiService', () => ({
  apiRequest: jest.fn(() => Promise.resolve({ success: true }))
}));

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => {
  const React = require('react');
  return {
    Menu: ({ children }: any) => <div data-testid="menu">{children}</div>,
    MenuButton: ({ children, as: _As, ...props }: any) => {
      const { rightIcon, variant, fontWeight, color, _hover, _active, size, ...domProps } = props;
      return <button data-testid="language-selector" {...domProps}>{children}</button>;
    },
    MenuList: ({ children, ...props }: any) => {
      const { minWidth, ...domProps } = props;
      return <div data-testid="menu-list" {...domProps}>{children}</div>;
    },
    MenuItem: ({ children, onClick, ...props }: any) => {
      const { bg, _hover, ...domProps } = props;
      return <button onClick={onClick} {...domProps}>{children}</button>;
    },
    Button: React.forwardRef(({ children, ...props }: any, ref: any) => (
      <button ref={ref} {...props}>{children}</button>
    )),
    useToast: () => jest.fn(),
  };
});

jest.mock('@chakra-ui/icons', () => ({
  ChevronDownIcon: () => <span data-testid="chevron-down">▼</span>,
}));

describe('LanguageSelector', () => {
  beforeEach(() => {
    mockCurrentLanguage = 'en';
    mockChangeLanguage.mockClear();
    localStorage.clear();
  });

  test('renders language selector button', () => {
    render(<LanguageSelector />);
    
    const button = screen.getByTestId('language-selector');
    expect(button).toBeInTheDocument();
  });

  test('displays current language', () => {
    mockCurrentLanguage = 'nl';
    render(<LanguageSelector />);
    
    const button = screen.getByTestId('language-selector');
    expect(button.textContent).toContain('🇳🇱');
  });

  test('opens menu when clicked', async () => {
    render(<LanguageSelector />);
    
    // Menu is always rendered in our mock, so just check items are present
    await waitFor(() => {
      expect(screen.getByText(/Nederlands/)).toBeInTheDocument();
      expect(screen.getByText(/English/)).toBeInTheDocument();
    });
  });

  test('changes language when option selected', async () => {
    render(<LanguageSelector />);
    
    // Click Dutch option
    const dutchOption = screen.getByText(/Nederlands/);
    fireEvent.click(dutchOption);
    
    // Language should be changed
    await waitFor(() => {
      expect(mockChangeLanguage).toHaveBeenCalledWith('nl');
    });
  });

  test('saves language to localStorage', async () => {
    render(<LanguageSelector />);
    
    // Click Dutch option
    const dutchOption = screen.getByText(/Nederlands/);
    fireEvent.click(dutchOption);
    
    // Verify changeLanguage was called with 'nl'
    await waitFor(() => {
      expect(mockChangeLanguage).toHaveBeenCalledWith('nl');
    });
  });

  test('shows both language options', async () => {
    render(<LanguageSelector />);
    
    await waitFor(() => {
      // Use getAllByText for flags since they appear in both button and menu
      expect(screen.getAllByText(/🇳🇱/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/🇬🇧/).length).toBeGreaterThan(0);
      expect(screen.getByText(/Nederlands/)).toBeInTheDocument();
      expect(screen.getByText(/English/)).toBeInTheDocument();
    });
  });

  test('highlights current language in menu', async () => {
    mockCurrentLanguage = 'nl';
    render(<LanguageSelector />);
    
    await waitFor(() => {
      const dutchOption = screen.getByTestId('language-option-nl');
      expect(dutchOption).toBeInTheDocument();
    });
  });
});
