/**
 * Shared test mock factories for type-safe test utilities.
 *
 * Provides fully-typed mock factories that satisfy TypeScript's strict
 * type checker, eliminating the need for `as Response` casts or
 * `as unknown as Response` workarounds in test files.
 *
 * @module test-utils/mockHelpers
 */

/**
 * Options for creating a mock Response object.
 * All properties are optional — sensible defaults are provided.
 *
 * @example
 * ```ts
 * import { createMockResponse } from '@/test-utils/mockHelpers';
 *
 * // Minimal usage — all defaults
 * const response = createMockResponse();
 *
 * // Custom status and body
 * const errorResponse = createMockResponse({
 *   ok: false,
 *   status: 404,
 *   statusText: 'Not Found',
 *   body: { error: 'Resource not found' },
 * });
 * ```
 */
export interface MockResponseOptions {
  /** HTTP status code. @default 200 */
  status?: number;
  /** Whether the response is ok (status 200-299). @default true */
  ok?: boolean;
  /** HTTP status text. @default "OK" */
  statusText?: string;
  /** Response headers. @default new Headers() */
  headers?: Headers;
  /** The body to return from json(). @default {} */
  body?: unknown;
  /** The text to return from text(). @default "" */
  textBody?: string;
  /** Whether the response was redirected. @default false */
  redirected?: boolean;
  /** Response type. @default "basic" */
  type?: ResponseType;
  /** Response URL. @default "" */
  url?: string;
}

/**
 * Creates a fully-typed mock `Response` object with sensible defaults.
 *
 * Eliminates partial `Response` casts (`as Response`) that cause TypeScript
 * errors when required properties are missing.
 *
 * @example
 * ```ts
 * // Simple success response with JSON body
 * vi.mocked(global.fetch).mockResolvedValue(
 *   createMockResponse({ body: { users: [] } })
 * );
 *
 * // Error response
 * vi.mocked(global.fetch).mockResolvedValue(
 *   createMockResponse({ ok: false, status: 404, body: { error: 'Not found' } })
 * );
 *
 * // Response with text body
 * vi.mocked(global.fetch).mockResolvedValue(
 *   createMockResponse({ textBody: '<html>Error</html>' })
 * );
 *
 * // Response with custom headers
 * const headers = new Headers({ 'Content-Type': 'application/json' });
 * vi.mocked(global.fetch).mockResolvedValue(
 *   createMockResponse({ headers, body: { data: 'value' } })
 * );
 * ```
 *
 * @param options - Partial response configuration. All fields optional.
 * @returns A complete `Response` object accepted by TypeScript anywhere
 *          a `Response` type is expected.
 */
export function createMockResponse(options: MockResponseOptions = {}): Response {
  const {
    status = 200,
    ok = true,
    statusText = 'OK',
    headers = new Headers(),
    body = {},
    textBody = '',
    redirected = false,
    type = 'basic',
    url = '',
  } = options;

  const response: Response = {
    ok,
    status,
    statusText,
    headers,
    redirected,
    type,
    url,
    body: null,
    bodyUsed: false,
    json: async () => body,
    text: async () => textBody,
    blob: async () => new Blob(),
    arrayBuffer: async () => new ArrayBuffer(0),
    formData: async () => new FormData(),
    bytes: async () => new Uint8Array(),
    clone(): Response {
      return createMockResponse(options);
    },
  };

  return response;
}
