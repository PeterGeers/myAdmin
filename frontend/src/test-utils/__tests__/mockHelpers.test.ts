/**
 * Unit tests for createMockResponse
 *
 * Example-based tests covering specific scenarios for the Response mock factory.
 *
 * Feature: frontend-test-type-safety
 * @see .kiro/specs/Common/Frameworks/frontend-test-type-safety/design.md
 */

import { createMockResponse } from '../mockHelpers';

describe('createMockResponse', () => {
  describe('default response (no arguments)', () => {
    it('returns ok: true, status: 200, statusText: "OK"', () => {
      const response = createMockResponse();

      expect(response.ok).toBe(true);
      expect(response.status).toBe(200);
      expect(response.statusText).toBe('OK');
    });

    it('returns empty headers', () => {
      const response = createMockResponse();

      expect(response.headers).toBeInstanceOf(Headers);
      expect([...response.headers.entries()]).toHaveLength(0);
    });

    it('returns default values for all other properties', () => {
      const response = createMockResponse();

      expect(response.redirected).toBe(false);
      expect(response.type).toBe('basic');
      expect(response.url).toBe('');
      expect(response.body).toBeNull();
      expect(response.bodyUsed).toBe(false);
    });

    it('json() resolves to empty object', async () => {
      const response = createMockResponse();
      const result = await response.json();
      expect(result).toEqual({});
    });

    it('text() resolves to empty string', async () => {
      const response = createMockResponse();
      const result = await response.text();
      expect(result).toBe('');
    });
  });

  describe('error response', () => {
    it('returns ok: false with status 404', () => {
      const response = createMockResponse({ ok: false, status: 404 });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(404);
    });

    it('returns ok: false with status 500 and custom statusText', () => {
      const response = createMockResponse({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(500);
      expect(response.statusText).toBe('Internal Server Error');
    });

    it('returns error body via json()', async () => {
      const errorBody = { error: 'Not found', code: 'RESOURCE_NOT_FOUND' };
      const response = createMockResponse({ ok: false, status: 404, body: errorBody });

      const result = await response.json();
      expect(result).toEqual(errorBody);
    });
  });

  describe('custom headers', () => {
    it('preserves provided headers', () => {
      const headers = new Headers({
        'Content-Type': 'application/json',
        'X-Request-Id': 'abc-123',
      });
      const response = createMockResponse({ headers });

      expect(response.headers.get('Content-Type')).toBe('application/json');
      expect(response.headers.get('X-Request-Id')).toBe('abc-123');
    });

    it('uses the exact Headers instance provided', () => {
      const headers = new Headers({ Authorization: 'Bearer token' });
      const response = createMockResponse({ headers });

      expect(response.headers).toBe(headers);
    });
  });

  describe('textBody', () => {
    it('maps to .text() return value', async () => {
      const response = createMockResponse({ textBody: '<html>Error page</html>' });
      const result = await response.text();
      expect(result).toBe('<html>Error page</html>');
    });

    it('returns empty string by default', async () => {
      const response = createMockResponse({ body: { data: 'value' } });
      const result = await response.text();
      expect(result).toBe('');
    });
  });

  describe('clone()', () => {
    it('returns a distinct object', () => {
      const response = createMockResponse({ status: 201, body: { id: 1 } });
      const cloned = response.clone();

      expect(cloned).not.toBe(response);
    });

    it('returns an object with same properties', () => {
      const response = createMockResponse({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        redirected: true,
        type: 'cors',
        url: 'https://example.com/api',
      });
      const cloned = response.clone();

      expect(cloned.ok).toBe(response.ok);
      expect(cloned.status).toBe(response.status);
      expect(cloned.statusText).toBe(response.statusText);
      expect(cloned.redirected).toBe(response.redirected);
      expect(cloned.type).toBe(response.type);
      expect(cloned.url).toBe(response.url);
    });

    it('cloned json() returns same body', async () => {
      const body = { users: [{ id: 1, name: 'Alice' }] };
      const response = createMockResponse({ body });
      const cloned = response.clone();

      const result = await cloned.json();
      expect(result).toEqual(body);
    });
  });

  describe('body methods', () => {
    it('blob() returns a Blob', async () => {
      const response = createMockResponse();
      const result = await response.blob();
      expect(result).toBeInstanceOf(Blob);
    });

    it('arrayBuffer() returns an ArrayBuffer', async () => {
      const response = createMockResponse();
      const result = await response.arrayBuffer();
      expect(result).toBeInstanceOf(ArrayBuffer);
    });

    it('formData() returns a FormData', async () => {
      const response = createMockResponse();
      const result = await response.formData();
      expect(result).toBeInstanceOf(FormData);
    });

    it('bytes() returns a Uint8Array', async () => {
      const response = createMockResponse();
      const result = await response.bytes();
      expect(result).toBeInstanceOf(Uint8Array);
    });
  });
});
