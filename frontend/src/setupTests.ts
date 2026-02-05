// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

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
  global.fetch = jest.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve({
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers(),
      redirected: false,
      type: 'basic' as ResponseType,
      url: '',
      clone: jest.fn(),
      body: null,
      bodyUsed: false,
      arrayBuffer: jest.fn(),
      blob: jest.fn(),
      formData: jest.fn(),
      text: jest.fn(),
      json: () => Promise.resolve({ mode: 'Test', database: 'testfinance', folder: 'testFacturen' }),
    } as Response)
  );
}

// Global mock for AWS Amplify auth functions
// This prevents tests from trying to make real AWS calls which causes hangs
jest.mock('aws-amplify/auth', () => ({
  fetchAuthSession: jest.fn(() => Promise.resolve({ tokens: null })),
  getCurrentUser: jest.fn(() => Promise.reject(new Error('Not authenticated'))),
  signOut: jest.fn(() => Promise.resolve()),
  signInWithRedirect: jest.fn(() => Promise.resolve()),
}));
