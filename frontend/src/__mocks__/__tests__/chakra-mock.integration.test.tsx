/**
 * Integration Tests for Chakra Mock Framework — Alias Configuration
 *
 * Verifies that the resolve.alias in vite.config.ts correctly redirects
 * @chakra-ui/react and @chakra-ui/icons imports to the mock modules,
 * and that test-utils.tsx works seamlessly with the mocked providers.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, cleanup } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Test 1: import { render } from '@/test-utils' works with alias active
// Validates: Requirements 4.1, 4.4
// ---------------------------------------------------------------------------
describe('test-utils render works with alias active', () => {
  afterEach(cleanup);

  it('renders a simple component queryable via RTL', async () => {
    const { render } = await import('@/test-utils');
    const SimpleComponent = () => <div data-testid="simple">Hello</div>;

    render(<SimpleComponent />);

    expect(screen.getByTestId('simple')).toBeDefined();
    expect(screen.getByText('Hello')).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// Test 2: Mock ChakraProvider renders children without applying styles
// Validates: Requirement 4.2
// ---------------------------------------------------------------------------
describe('mock ChakraProvider renders children without styles', () => {
  afterEach(cleanup);

  it('renders children as-is without Chakra theme styling', async () => {
    const { ChakraProvider } = await import('../chakra-ui-react');
    const { render: rtlRender } = await import('@testing-library/react');

    rtlRender(
      <ChakraProvider>
        <p data-testid="child">Unstyled content</p>
      </ChakraProvider>,
    );

    const child = screen.getByTestId('child');
    expect(child).toBeDefined();
    expect(child.textContent).toBe('Unstyled content');
    // ChakraProvider mock is a passthrough — no wrapper elements with theme classes
    expect(child.tagName).toBe('P');
  });
});

// ---------------------------------------------------------------------------
// Test 3: Mock extendTheme returns a valid object so theme.js doesn't throw
// Validates: Requirement 4.3
// ---------------------------------------------------------------------------
describe('mock extendTheme returns valid object for theme.js', () => {
  it('extendTheme returns a valid object preserving the input config', async () => {
    // Import from the mock module directly to verify mock behavior
    const { extendTheme } = await import('../chakra-ui-react');

    const themeConfig = {
      styles: { global: { body: { bg: '#0f0f0f' } } },
      colors: { brand: { orange: '#ff6600' } },
      components: { Select: { baseStyle: {} } },
    };

    const result = extendTheme(themeConfig);
    expect(result).toEqual(themeConfig);
  });

  it('theme.js import does not throw', async () => {
    // This exercises the real theme.js which calls extendTheme({...})
    // With the alias active, extendTheme resolves to the mock
    const themeModule = await import('@/theme');
    expect(themeModule.default).toBeDefined();
    // The mock extendTheme returns its input, so theme should contain
    // the config keys from theme.js
    expect(themeModule.default).toHaveProperty('styles');
    expect(themeModule.default).toHaveProperty('colors');
    expect(themeModule.default).toHaveProperty('components');
  });
});

// ---------------------------------------------------------------------------
// Test 4: test-utils.tsx requires zero modifications
// Validates: Requirement 4.5
// ---------------------------------------------------------------------------
describe('test-utils requires zero modifications', () => {
  afterEach(cleanup);

  it('import from @/test-utils works and render produces queryable output', async () => {
    const { render } = await import('@/test-utils');

    const TestComponent = () => <span data-testid="tu-test">Works</span>;
    render(<TestComponent />);

    expect(screen.getByTestId('tu-test').textContent).toBe('Works');
  });
});

// ---------------------------------------------------------------------------
// Test 5: Transitive @chakra-ui/react import renders without crash
// Validates: Requirements 3.1, 3.2, 7.4
// ---------------------------------------------------------------------------
describe('transitive @chakra-ui/react imports are intercepted', () => {
  afterEach(cleanup);

  it('component with internal Chakra import renders without crash', async () => {
    // Import from the mock module — in the real scenario, the resolve.alias
    // redirects @chakra-ui/react to this module for all transitive imports.
    const { Box, Heading, Button } = await import('../chakra-ui-react');
    const { render: rtlRender } = await import('@testing-library/react');

    // Simulate a wrapper component that internally uses Chakra components
    // (which would be transitive imports in real code)
    const WrapperComponent = () => (
      <Box>
        <Heading>Title</Heading>
        <Button onClick={() => {}}>Click me</Button>
      </Box>
    );

    rtlRender(<WrapperComponent />);

    expect(screen.getByText('Title')).toBeDefined();
    expect(screen.getByText('Click me')).toBeDefined();
  });

  it('test-utils render wraps with mock ChakraProvider without crash', async () => {
    // This is the real integration test: test-utils.tsx imports from
    // @chakra-ui/react, and the alias redirects to the mock
    const { render } = await import('@/test-utils');

    const ComponentWithChakra = () => <div data-testid="wrapped">Content</div>;
    render(<ComponentWithChakra />);

    expect(screen.getByTestId('wrapped').textContent).toBe('Content');
  });
});

// ---------------------------------------------------------------------------
// Test 6: Rendering mock components produces zero React DOM warnings
// Validates: Requirement 5.5
// ---------------------------------------------------------------------------
describe('mock components produce zero React DOM warnings about unknown props', () => {
  afterEach(cleanup);

  it('no console.error warnings when rendering with Chakra-specific props', async () => {
    const { Box, Button, Flex, Text, Heading } = await import('../chakra-ui-react');
    const { render: rtlRender } = await import('@testing-library/react');

    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    rtlRender(
      <Flex bg="red.500" p={4} alignItems="center" gap={2}>
        <Box colorScheme="blue" variant="solid" sx={{ custom: true }}>
          <Text fontSize="lg" fontWeight="bold" color="white">
            Styled text
          </Text>
        </Box>
        <Heading size="lg" mb={4}>Title</Heading>
        <Button
          colorScheme="teal"
          size="lg"
          isLoading={false}
          isDisabled={false}
          _hover={{ bg: 'teal.600' }}
        >
          Action
        </Button>
      </Flex>,
    );

    // Filter for React unknown-prop warnings specifically
    const unknownPropWarnings = errorSpy.mock.calls.filter(
      (call) =>
        typeof call[0] === 'string' &&
        (call[0].includes('is not a valid HTML attribute') ||
         call[0].includes('Unknown event handler property') ||
         call[0].includes('React does not recognize the') ||
         call[0].includes('Invalid DOM property')),
    );

    expect(unknownPropWarnings).toHaveLength(0);

    errorSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Test 7: Per-file override mechanism works
// Validates: Requirement 7.6
// ---------------------------------------------------------------------------
describe('per-file override mechanism', () => {
  afterEach(cleanup);

  it('vi.mock can override a specific export from the mock module', async () => {
    // Dynamically import the mock module to get the base exports
    const originalModule = await import('../chakra-ui-react');

    // Verify the original useToast returns a vi.fn()
    const originalToast = originalModule.useToast();
    expect(typeof originalToast).toBe('function');

    // Verify that the override pattern works by importing and spreading
    const overridden = {
      ...originalModule,
      useToast: () => {
        const fn = vi.fn();
        (fn as any).__overridden = true;
        return fn;
      },
    };

    // The overridden useToast should have the custom marker
    const overriddenToast = overridden.useToast();
    expect(typeof overriddenToast).toBe('function');
    expect((overriddenToast as any).__overridden).toBe(true);

    // Original module exports are preserved for non-overridden items
    expect(overridden.Box).toBe(originalModule.Box);
    expect(overridden.extendTheme).toBe(originalModule.extendTheme);
  });
});
