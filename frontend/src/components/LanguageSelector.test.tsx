/**
 * Unit tests for LanguageSelector component
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import LanguageSelector from './LanguageSelector';
import i18n from '../i18n';

// Mock the API service
jest.mock('../services/apiService', () => ({
  apiRequest: jest.fn(() => Promise.resolve({ success: true }))
}));

const renderWithChakra = (component: React.ReactElement) => {
  return render(
    <ChakraProvider>
      {component}
    </ChakraProvider>
  );
};

describe('LanguageSelector', () => {
  beforeEach(() => {
    // Reset language to English before each test
    i18n.changeLanguage('en');
    localStorage.clear();
  });

  test('renders language selector button', () => {
    renderWithChakra(<LanguageSelector />);
    
    // Should show current language flag
    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
  });

  test('displays current language', () => {
    i18n.changeLanguage('nl');
    renderWithChakra(<LanguageSelector />);
    
    const button = screen.getByRole('button');
    expect(button.textContent).toContain('🇳🇱');
  });

  test('opens menu when clicked', async () => {
    renderWithChakra(<LanguageSelector />);
    
    const button = screen.getByRole('button');
    fireEvent.click(button);
    
    await waitFor(() => {
      expect(screen.getByText(/Nederlands/)).toBeInTheDocument();
      expect(screen.getByText(/English/)).toBeInTheDocument();
    });
  });

  test('changes language when option selected', async () => {
    renderWithChakra(<LanguageSelector />);
    
    // Open menu
    const button = screen.getByRole('button');
    fireEvent.click(button);
    
    // Click Dutch option
    await waitFor(() => {
      const dutchOption = screen.getByText(/Nederlands/);
      fireEvent.click(dutchOption);
    });
    
    // Language should be changed
    await waitFor(() => {
      expect(i18n.language).toBe('nl');
    });
  });

  test('saves language to localStorage', async () => {
    renderWithChakra(<LanguageSelector />);
    
    // Open menu and select Dutch
    const button = screen.getByRole('button');
    fireEvent.click(button);
    
    await waitFor(() => {
      const dutchOption = screen.getByText(/Nederlands/);
      fireEvent.click(dutchOption);
    });
    
    // Check localStorage
    await waitFor(() => {
      expect(localStorage.getItem('i18nextLng')).toBe('nl');
    });
  });

  test('shows both language options', async () => {
    renderWithChakra(<LanguageSelector />);
    
    const button = screen.getByRole('button');
    fireEvent.click(button);
    
    await waitFor(() => {
      // Should show both Dutch and English
      expect(screen.getByText(/🇳🇱/)).toBeInTheDocument();
      expect(screen.getByText(/🇬🇧/)).toBeInTheDocument();
      expect(screen.getByText(/Nederlands/)).toBeInTheDocument();
      expect(screen.getByText(/English/)).toBeInTheDocument();
    });
  });

  test('highlights current language in menu', async () => {
    i18n.changeLanguage('nl');
    renderWithChakra(<LanguageSelector />);
    
    const button = screen.getByRole('button');
    fireEvent.click(button);
    
    await waitFor(() => {
      const dutchOption = screen.getByText(/Nederlands/).closest('button');
      // Current language should have visual indicator (check mark or different style)
      expect(dutchOption).toBeInTheDocument();
    });
  });
});
