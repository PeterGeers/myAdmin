/**
 * Property-based tests for createMockResponse
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * Feature: frontend-test-type-safety
 * @see .kiro/specs/Common/Frameworks/frontend-test-type-safety/design.md — Properties 1, 2, 3
 */

import fc from 'fast-check';
import { createMockResponse, MockResponseOptions } from '../mockHelpers';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a valid HTTP status code (100–599). */
const statusArbitrary = fc.integer({ min: 100, max: 599 });

/** Generate a random ok boolean. */
const okArbitrary = fc.boolean();

/** Generate random status text. */
const statusTextArbitrary = fc.string({ minLength: 0, maxLength: 20 });

/** Generate random headers as key-value pairs. */
const headersArbitrary = fc
  .array(
    fc.tuple(
      fc.stringMatching(/^[a-zA-Z][a-zA-Z0-9-]{0,15}$/),
      fc.string({ minLength: 1, maxLength: 50 }),
    ),
    { minLength: 0, maxLength: 5 },
  )
  .map((pairs) => new Headers(pairs));

/** Generate a random ResponseType. */
const responseTypeArbitrary = fc.constantFrom(
  'basic',
  'cors',
  'default',
  'error',
  'opaque',
  'opaqueredirect',
) as fc.Arbitrary<ResponseType>;

/** Generate a full MockResponseOptions with all fields populated. */
const fullOptionsArbitrary: fc.Arbitrary<MockResponseOptions> = fc.record({
  status: statusArbitrary,
  ok: okArbitrary,
  statusText: statusTextArbitrary,
  headers: headersArbitrary,
  body: fc.jsonValue(),
  textBody: fc.string({ minLength: 0, maxLength: 100 }),
  redirected: fc.boolean(),
  type: responseTypeArbitrary,
  url: fc.string({ minLength: 0, maxLength: 50 }),
});

// ---------------------------------------------------------------------------
// Property 1: Response factory completeness
// ---------------------------------------------------------------------------

describe('Property 1: Response factory completeness', () => {
  /**
   * For any valid MockResponseOptions input, createMockResponse() returns an
   * object where every property required by the Response interface is defined
   * and every required method is a callable function.
   *
   * Validates: Requirements 3.1, 3.3, 3.4
   */
  it('all required Response properties are defined and methods are callable', () => {
    fc.assert(
      fc.property(fullOptionsArbitrary, (options) => {
        const response = createMockResponse(options);

        // Required properties must be defined (not undefined)
        expect(response.ok).toBeDefined();
        expect(response.status).toBeDefined();
        expect(response.statusText).toBeDefined();
        expect(response.headers).toBeDefined();
        expect(response.redirected).toBeDefined();
        expect(response.type).toBeDefined();
        expect(response.url).toBeDefined();
        expect(response.bodyUsed).toBeDefined();
        // body can be null, but the property itself must exist
        expect('body' in response).toBe(true);

        // Required methods must be functions
        expect(typeof response.json).toBe('function');
        expect(typeof response.text).toBe('function');
        expect(typeof response.blob).toBe('function');
        expect(typeof response.arrayBuffer).toBe('function');
        expect(typeof response.formData).toBe('function');
        expect(typeof response.bytes).toBe('function');
        expect(typeof response.clone).toBe('function');
      }),
      { numRuns: 100 },
    );
  });

  it('properties have correct types', () => {
    fc.assert(
      fc.property(fullOptionsArbitrary, (options) => {
        const response = createMockResponse(options);

        expect(typeof response.ok).toBe('boolean');
        expect(typeof response.status).toBe('number');
        expect(typeof response.statusText).toBe('string');
        expect(response.headers).toBeInstanceOf(Headers);
        expect(typeof response.redirected).toBe('boolean');
        expect(typeof response.type).toBe('string');
        expect(typeof response.url).toBe('string');
        expect(typeof response.bodyUsed).toBe('boolean');
      }),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: Response factory json round-trip
// ---------------------------------------------------------------------------

describe('Property 2: Response factory json round-trip', () => {
  /**
   * For any JSON-serializable value passed as the body option,
   * calling .json() on the returned Response resolves to a value
   * deeply equal to the original input.
   *
   * Validates: Requirements 3.1, 3.5
   */
  it('json() returns the exact body value passed in', async () => {
    await fc.assert(
      fc.asyncProperty(fc.jsonValue(), async (jsonBody) => {
        const response = createMockResponse({ body: jsonBody });
        const result = await response.json();
        expect(result).toEqual(jsonBody);
      }),
      { numRuns: 100 },
    );
  });

  it('json() returns empty object by default when no body provided', async () => {
    const response = createMockResponse();
    const result = await response.json();
    expect(result).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// Property 3: Response factory defaults preserve override
// ---------------------------------------------------------------------------

describe('Property 3: Response factory defaults preserve override', () => {
  /**
   * For any subset of MockResponseOptions fields provided,
   * createMockResponse() uses the provided values for those fields
   * and sensible defaults for all omitted fields, such that the
   * returned object always satisfies the Response interface.
   *
   * Validates: Requirements 3.3, 3.6
   */

  /** Documented defaults for MockResponseOptions. */
  const DEFAULTS = {
    status: 200,
    ok: true,
    statusText: 'OK',
    redirected: false,
    type: 'basic' as ResponseType,
    url: '',
    bodyUsed: false,
  };

  it('provided fields match input, omitted fields match defaults', () => {
    // Generate a random subset of options by making each field optional
    const partialOptionsArbitrary = fc.record(
      {
        status: statusArbitrary,
        ok: okArbitrary,
        statusText: statusTextArbitrary,
        redirected: fc.boolean(),
        type: responseTypeArbitrary,
        url: fc.string({ minLength: 0, maxLength: 50 }),
      },
      { requiredKeys: [] },
    );

    fc.assert(
      fc.property(partialOptionsArbitrary, (options) => {
        const response = createMockResponse(options);

        // Provided fields must match input
        if (options.status !== undefined) {
          expect(response.status).toBe(options.status);
        }
        if (options.ok !== undefined) {
          expect(response.ok).toBe(options.ok);
        }
        if (options.statusText !== undefined) {
          expect(response.statusText).toBe(options.statusText);
        }
        if (options.redirected !== undefined) {
          expect(response.redirected).toBe(options.redirected);
        }
        if (options.type !== undefined) {
          expect(response.type).toBe(options.type);
        }
        if (options.url !== undefined) {
          expect(response.url).toBe(options.url);
        }

        // Omitted fields must match defaults
        if (options.status === undefined) {
          expect(response.status).toBe(DEFAULTS.status);
        }
        if (options.ok === undefined) {
          expect(response.ok).toBe(DEFAULTS.ok);
        }
        if (options.statusText === undefined) {
          expect(response.statusText).toBe(DEFAULTS.statusText);
        }
        if (options.redirected === undefined) {
          expect(response.redirected).toBe(DEFAULTS.redirected);
        }
        if (options.type === undefined) {
          expect(response.type).toBe(DEFAULTS.type);
        }
        if (options.url === undefined) {
          expect(response.url).toBe(DEFAULTS.url);
        }

        // bodyUsed always defaults to false
        expect(response.bodyUsed).toBe(DEFAULTS.bodyUsed);

        // Result always satisfies Response interface (all methods callable)
        expect(typeof response.json).toBe('function');
        expect(typeof response.text).toBe('function');
        expect(typeof response.blob).toBe('function');
        expect(typeof response.arrayBuffer).toBe('function');
        expect(typeof response.formData).toBe('function');
        expect(typeof response.bytes).toBe('function');
        expect(typeof response.clone).toBe('function');
      }),
      { numRuns: 100 },
    );
  });

  it('headers default to empty Headers when not provided', () => {
    const response = createMockResponse();
    expect(response.headers).toBeInstanceOf(Headers);
    // Empty headers should have no entries
    const entries = [...response.headers.entries()];
    expect(entries).toHaveLength(0);
  });

  it('provided headers are preserved', () => {
    fc.assert(
      fc.property(headersArbitrary, (headers) => {
        const response = createMockResponse({ headers });
        expect(response.headers).toBe(headers);
      }),
      { numRuns: 100 },
    );
  });
});
