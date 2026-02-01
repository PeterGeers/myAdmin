/**
 * Test Utilities
 * 
 * Custom render function with ChakraProvider wrapper for testing components.
 * Re-exports all React Testing Library utilities for convenience.
 */

import React, { ReactElement } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import theme from './theme';

/**
 * All providers wrapper for testing
 */
const AllTheProviders = ({ children }: { children: React.ReactNode }) => {
  return (
    <ChakraProvider theme={theme}>
      {children}
    </ChakraProvider>
  );
};

/**
 * Custom render function with providers
 */
const customRender = (
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) => render(ui, { wrapper: AllTheProviders, ...options });

// Re-export everything from React Testing Library
export * from '@testing-library/react';

// Override render method
export { customRender as render };
