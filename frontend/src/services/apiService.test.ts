/**
 * Integration tests for API service X-Language header functionality
 */

import { apiRequest } from './apiService';
import i18n from '../i18n';

// Mock fetch
global.fetch = jest.fn();

describe('API Service X-Language Header', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks();
    
    // Mock successful response
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: {} }),
      headers: new Headers(),
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('sends X-Language header with current language (Dutch)', async () => {
    // Set language to Dutch
    i18n.changeLanguage('nl');

    await apiRequest('/api/test', {
      method: 'GET',
    });

    // Verify fetch was called with X-Language header
    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Language': 'nl',
        }),
      })
    );
  });

  test('sends X-Language header with current language (English)', async () => {
    // Set language to English
    i18n.changeLanguage('en');

    await apiRequest('/api/test', {
      method: 'GET',
    });

    // Verify fetch was called with X-Language header
    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Language': 'en',
        }),
      })
    );
  });

  test('sends X-Language header with GET requests', async () => {
    i18n.changeLanguage('nl');

    await apiRequest('/api/test', {
      method: 'GET',
    });

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    const headers = fetchCall[1].headers;
    
    expect(headers['X-Language']).toBe('nl');
  });

  test('sends X-Language header with POST requests', async () => {
    i18n.changeLanguage('en');

    await apiRequest('/api/test', {
      method: 'POST',
      body: JSON.stringify({ test: 'data' }),
    });

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    const headers = fetchCall[1].headers;
    
    expect(headers['X-Language']).toBe('en');
  });

  test('sends X-Language header with PUT requests', async () => {
    i18n.changeLanguage('nl');

    await apiRequest('/api/test', {
      method: 'PUT',
      body: JSON.stringify({ test: 'data' }),
    });

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    const headers = fetchCall[1].headers;
    
    expect(headers['X-Language']).toBe('nl');
  });

  test('sends X-Language header with DELETE requests', async () => {
    i18n.changeLanguage('en');

    await apiRequest('/api/test', {
      method: 'DELETE',
    });

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    const headers = fetchCall[1].headers;
    
    expect(headers['X-Language']).toBe('en');
  });

  test('X-Language header persists across multiple requests', async () => {
    i18n.changeLanguage('nl');

    // Make multiple requests
    await apiRequest('/api/test1', { method: 'GET' });
    await apiRequest('/api/test2', { method: 'GET' });
    await apiRequest('/api/test3', { method: 'GET' });

    // All requests should have X-Language header
    const calls = (global.fetch as jest.Mock).mock.calls;
    
    calls.forEach(call => {
      const headers = call[1].headers;
      expect(headers['X-Language']).toBe('nl');
    });
  });

  test('X-Language header updates when language changes', async () => {
    // Start with Dutch
    i18n.changeLanguage('nl');
    await apiRequest('/api/test1', { method: 'GET' });

    // Change to English
    i18n.changeLanguage('en');
    await apiRequest('/api/test2', { method: 'GET' });

    const calls = (global.fetch as jest.Mock).mock.calls;
    
    // First call should have nl
    expect(calls[0][1].headers['X-Language']).toBe('nl');
    
    // Second call should have en
    expect(calls[1][1].headers['X-Language']).toBe('en');
  });

  test('X-Language header is included with authentication headers', async () => {
    i18n.changeLanguage('nl');

    // Mock localStorage to simulate authenticated user
    const mockToken = 'mock-jwt-token';
    Storage.prototype.getItem = jest.fn(() => mockToken);

    await apiRequest('/api/test', {
      method: 'GET',
    });

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    const headers = fetchCall[1].headers;
    
    // Should have both Authorization and X-Language headers
    expect(headers['X-Language']).toBe('nl');
    expect(headers['Authorization']).toBeDefined();
  });

  test('X-Language header defaults to nl if language not set', async () => {
    // Don't set language explicitly (should default to nl)
    
    await apiRequest('/api/test', {
      method: 'GET',
    });

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    const headers = fetchCall[1].headers;
    
    // Should default to nl
    expect(headers['X-Language']).toBeDefined();
    expect(['nl', 'en']).toContain(headers['X-Language']);
  });
});
