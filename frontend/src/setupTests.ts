// @testing-library/jest-dom adds custom matchers for asserting on DOM nodes.
// Works with Vitest via globals — allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { createMockResponse } from '@/test-utils/mockHelpers';

// Suppress React 19 "not wrapped in act(...)" warnings.
// React 19 aggressively warns about state updates outside act() even when
// React Testing Library's waitFor/findBy* queries handle them correctly.
// See: https://github.com/testing-library/react-testing-library/issues/1061
const originalConsoleError = console.error;
console.error = (...args: any[]) => {
  if (
    typeof args[0] === 'string' &&
    args[0].includes('was not wrapped in act')
  ) {
    return;
  }
  originalConsoleError(...args);
};

// Polyfills needed by MSW
if (typeof global.TextEncoder === 'undefined') {
  const { TextEncoder, TextDecoder } = require('util');
  global.TextEncoder = TextEncoder;
  global.TextDecoder = TextDecoder;
}

// Mock BroadcastChannel for MSW
if (typeof global.BroadcastChannel === 'undefined') {
  class MockBroadcastChannel implements BroadcastChannel {
    name: string;
    onmessage: ((this: BroadcastChannel, ev: MessageEvent) => any) | null = null;
    onmessageerror: ((this: BroadcastChannel, ev: MessageEvent) => any) | null = null;

    constructor(name: string) {
      this.name = name;
    }

    postMessage(message: any): void {}
    close(): void {}
    addEventListener(type: string, listener: EventListenerOrEventListenerObject | null, options?: boolean | AddEventListenerOptions): void {}
    removeEventListener(type: string, listener: EventListenerOrEventListenerObject | null, options?: boolean | EventListenerOptions): void {}
    dispatchEvent(event: Event): boolean { return true; }
  }

  (global as any).BroadcastChannel = MockBroadcastChannel;
}

// Mock fetch for tests
if (typeof global.fetch === 'undefined') {
  global.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(createMockResponse({
      body: { mode: 'Test', database: 'testfinance', folder: 'testFacturen' },
    }))
  );
}

// Global mock for AWS Amplify auth functions
// This prevents tests from trying to make real AWS calls which causes hangs
vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(() => Promise.resolve({ tokens: null })),
  getCurrentUser: vi.fn(() => Promise.reject(new Error('Not authenticated'))),
  signOut: vi.fn(() => Promise.resolve()),
  signInWithRedirect: vi.fn(() => Promise.resolve()),
}));
