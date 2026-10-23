// Committed unit test for the `application_form_frame_ancestors` CloudFront
// viewer-response function (spec Members/11 - application-form-builder, task 5.2/5.4,
// requirement R5.2).
//
// The function is defined inline in `infrastructure/application-form.tf` as a
// `cloudfront-js-2.0` heredoc that reads the request host's allowed embed origins from
// a KeyValueStore (KVS) and sets `Content-Security-Policy: frame-ancestors <origins>`
// on the response. Task 5.2 shipped it with only a manual `node --check` + ad-hoc
// harness ("no JS test harness exists"). This file closes that gap with a REAL,
// committed test exercising the EXACT deployed source (extracted from the .tf — no
// duplicated/drifting copy) against a mocked `cloudfront` module.
//
// Matrix (R5.2 / design §10):
//   * configured host           -> `content-security-policy: frame-ancestors <origins>`
//   * unconfigured host (no key) -> NO header (standalone / not embeddable, fail-closed)
//   * empty / whitespace value   -> NO header
//   * KVS lookup error           -> NO header (fail-closed)
//   * missing host               -> NO header
//   * KVS binding unavailable    -> NO header
//
// Run (Node >= 18 built-in test runner, no deps):
//   node --test infrastructure/functions/
//   # or a single file:
//   node --test infrastructure/functions/application-form-frame-ancestors.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { extractFunctionCode, loadHandler } from './extract-tf-function.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const TF_PATH = join(__dirname, '..', 'application-form.tf');
const RESOURCE = 'application_form_frame_ancestors';
const FORM_HOST = 'tenant-member-application.jabaki.nl';
const CSP_HEADER = 'content-security-policy';

// ── Mocks ──────────────────────────────────────────────────────────────────────────

/** A mock `cloudfront` module whose `kvs(id)` returns a store with a canned `get`. */
function mockCf({ store = {}, getThrows = false, kvsThrows = false } = {}) {
  return {
    kvs() {
      if (kvsThrows) {
        throw new Error('KVS binding unavailable');
      }
      return {
        async get(key) {
          if (getThrows) {
            throw new Error('ResourceNotFound');
          }
          if (!(key in store)) {
            // Mirror the real KVS: a missing key rejects (the function treats a
            // rejected get() as "no origins").
            throw new Error('KeyNotFound');
          }
          return store[key];
        },
      };
    },
  };
}

/** Build a viewer-response event with the given host header. */
function responseEvent(host) {
  return {
    request: { headers: host == null ? {} : { host: { value: host } } },
    response: { headers: {} },
  };
}

async function loadFreshHandler(cf) {
  const code = await extractFunctionCode(TF_PATH, RESOURCE);
  return loadHandler(code, cf);
}

// ── Configured tenant -> frame-ancestors emitted ────────────────────────────────────

test('configured host emits frame-ancestors with the single tenant origin', async () => {
  const cf = mockCf({ store: { [FORM_HOST]: 'https://www.acme.nl' } });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.ok(result.headers[CSP_HEADER], 'CSP header should be set');
  assert.equal(result.headers[CSP_HEADER].value, 'frame-ancestors https://www.acme.nl');
});

test('configured host emits frame-ancestors with multiple space-separated origins', async () => {
  const cf = mockCf({
    store: { [FORM_HOST]: 'https://www.acme.nl https://portal.acme.nl' },
  });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.equal(
    result.headers[CSP_HEADER].value,
    'frame-ancestors https://www.acme.nl https://portal.acme.nl',
  );
});

test('extra whitespace in the KVS value is collapsed in the directive', async () => {
  const cf = mockCf({
    store: { [FORM_HOST]: '  https://a.nl   https://b.nl  ' },
  });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.equal(result.headers[CSP_HEADER].value, 'frame-ancestors https://a.nl https://b.nl');
});

// ── Unconfigured tenant -> no header (standalone / fail-closed) ──────────────────────

test('unconfigured host (key not found) omits the header — not embeddable', async () => {
  // The form host has no KVS entry (standalone); get() rejects -> no header.
  const cf = mockCf({ store: {} });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.equal(result.headers[CSP_HEADER], undefined, 'no CSP header for an unconfigured host');
});

test('empty KVS value omits the header', async () => {
  const cf = mockCf({ store: { [FORM_HOST]: '' } });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.equal(result.headers[CSP_HEADER], undefined);
});

test('whitespace-only KVS value omits the header (no empty directive)', async () => {
  const cf = mockCf({ store: { [FORM_HOST]: '    ' } });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.equal(result.headers[CSP_HEADER], undefined);
});

test('a KVS lookup error fails closed (no header)', async () => {
  const cf = mockCf({ store: { [FORM_HOST]: 'https://www.acme.nl' }, getThrows: true });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.equal(result.headers[CSP_HEADER], undefined, 'lookup error must not set a header');
});

test('missing host header fails closed (no header)', async () => {
  const cf = mockCf({ store: { [FORM_HOST]: 'https://www.acme.nl' } });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(null));

  assert.equal(result.headers[CSP_HEADER], undefined);
});

test('unavailable KVS binding fails closed (no header)', async () => {
  // `cf.kvs(id)` throws at module init -> the function must still return the response
  // without a CSP header (the try/catch around the binding swallows it).
  const cf = mockCf({ kvsThrows: true });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.equal(result.headers[CSP_HEADER], undefined);
});

// ── Confirmed v1 targets (task 5.5 / R9.2): Google Sites + h-dcn portal ──────────────
//
// Task 5.5 / requirement R9.2 name the two confirmed external embed targets explicitly:
// a Google Site (`https://sites.google.com`) and the h-dcn event portal
// (`https://portal.h-dcn.nl`). These pin that a tenant configured with BOTH origins emits a
// `frame-ancestors` listing both, and that a DIFFERENT (unconfigured) form host is denied —
// the reflect-the-configured-origins / deny-others contract, stated with the real targets.

const GOOGLE_SITES = 'https://sites.google.com';
const HDCN_PORTAL = 'https://portal.h-dcn.nl';

test('configured tenant reflects the confirmed v1 targets (Google Sites + h-dcn portal)', async () => {
  const cf = mockCf({ store: { [FORM_HOST]: `${GOOGLE_SITES} ${HDCN_PORTAL}` } });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent(FORM_HOST));

  assert.equal(
    result.headers[CSP_HEADER].value,
    `frame-ancestors ${GOOGLE_SITES} ${HDCN_PORTAL}`,
  );
});

test('a different, unconfigured form host is denied (no frame-ancestors) even when another tenant lists the confirmed targets', async () => {
  // Only FORM_HOST is configured with the confirmed targets; a different host has no KVS entry
  // and must be denied framing — the deny-an-unconfigured-one half of R9.2.
  const cf = mockCf({ store: { [FORM_HOST]: `${GOOGLE_SITES} ${HDCN_PORTAL}` } });
  const handler = await loadFreshHandler(cf);

  const result = await handler(responseEvent('other-tenant-application.jabaki.nl'));

  assert.equal(result.headers[CSP_HEADER], undefined, 'an unconfigured host is not embeddable');
});

// ── Non-interference ─────────────────────────────────────────────────────────────────

test('the function returns the response object (passes other headers through)', async () => {
  const cf = mockCf({ store: {} });
  const handler = await loadFreshHandler(cf);

  const event = responseEvent(FORM_HOST);
  event.response.headers['x-existing'] = { value: 'keep-me' };

  const result = await handler(event);

  assert.equal(result.headers['x-existing'].value, 'keep-me');
});
