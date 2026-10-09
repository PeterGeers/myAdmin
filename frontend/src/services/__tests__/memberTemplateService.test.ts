/**
 * Unit tests for memberTemplateService (services/memberTemplateService.ts).
 *
 * Verifies task 2.5 (R2, pivot-output-actions): the authenticated client for the Members
 * mail-template routes codes against the design §3 contract + the API response & error standard
 * v1.0 (steering 37):
 *   - each function hits the right method + path (`/members/templates[/{id}]`, `.../ai-improve`);
 *   - a success envelope `{ success:true, data }` is unwrapped to `{ ok:true, data }`;
 *   - an error envelope `{ success:false, error, code }` (or a non-2xx status) becomes
 *     `{ ok:false, status, error, code }` — never a throw;
 *   - the id is URL-encoded in the path.
 *
 * The apiService verbs are mocked (no network).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { createMockResponse } from '@/test-utils/mockHelpers';

vi.mock('../apiService', () => ({
  authenticatedGet: vi.fn(),
  authenticatedPost: vi.fn(),
  authenticatedPut: vi.fn(),
  authenticatedDelete: vi.fn(),
  // Pass-through builder (identity when no params) so path assertions are simple.
  buildEndpoint: (endpoint: string) => endpoint,
}));

import {
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedDelete,
} from '../apiService';
import {
  listMemberTemplates,
  getMemberTemplate,
  createMemberTemplate,
  updateMemberTemplate,
  deleteMemberTemplate,
  aiImproveMemberTemplate,
} from '../memberTemplateService';

const mGet = vi.mocked(authenticatedGet);
const mPost = vi.mocked(authenticatedPost);
const mPut = vi.mocked(authenticatedPut);
const mDelete = vi.mocked(authenticatedDelete);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('memberTemplateService', () => {
  it('lists templates and unwraps the standard data envelope', async () => {
    const data = [{ template_id: 't1', name: 'A' }];
    mGet.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const result = await listMemberTemplates();

    expect(mGet).toHaveBeenCalledWith('/members/templates');
    expect(result).toEqual({ ok: true, data });
  });

  // Regression (white-page crash): the delivery-editor template picker calls
  // `templates.map`, so the list endpoint MUST yield an array. A malformed success
  // body (object / missing data / null) previously flowed straight through and crashed
  // the SPA — now it is coerced to an empty array so the picker degrades gracefully.
  it('coerces a non-array `data` object on a success envelope to an empty array', async () => {
    mGet.mockResolvedValue(
      createMockResponse({ body: { success: true, data: { templates: [] } } }),
    );

    const result = await listMemberTemplates();

    expect(result).toEqual({ ok: true, data: [] });
  });

  it('coerces a success envelope with NO `data` (envelope fallback) to an empty array', async () => {
    mGet.mockResolvedValue(createMockResponse({ body: { success: true } }));

    const result = await listMemberTemplates();

    expect(result).toEqual({ ok: true, data: [] });
  });

  it('coerces a null `data` on a success envelope to an empty array', async () => {
    mGet.mockResolvedValue(createMockResponse({ body: { success: true, data: null } }));

    const result = await listMemberTemplates();

    expect(result).toEqual({ ok: true, data: [] });
  });

  it('gets a template by id (URL-encoded path)', async () => {
    const data = { template_id: 'a/b', name: 'X', languages: {} };
    mGet.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const result = await getMemberTemplate('a/b');

    expect(mGet).toHaveBeenCalledWith('/members/templates/a%2Fb');
    expect(result).toEqual({ ok: true, data });
  });

  it('creates a template via POST', async () => {
    const data = { template_id: 'new', name: 'New' };
    mPost.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const input = { name: 'New', languages: { en: { subject: 'S', body_html: 'B' } } };
    const result = await createMemberTemplate(input);

    expect(mPost).toHaveBeenCalledWith('/members/templates', input);
    expect(result).toEqual({ ok: true, data });
  });

  it('updates a template via PUT', async () => {
    const data = { template_id: 't1', name: 'Edited' };
    mPut.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const input = { name: 'Edited', languages: { en: { subject: 'S', body_html: 'B' } } };
    const result = await updateMemberTemplate('t1', input);

    expect(mPut).toHaveBeenCalledWith('/members/templates/t1', input);
    expect(result).toEqual({ ok: true, data });
  });

  it('deletes a template via DELETE', async () => {
    const data = { template_id: 't1', name: 'Gone' };
    mDelete.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const result = await deleteMemberTemplate('t1');

    expect(mDelete).toHaveBeenCalledWith('/members/templates/t1');
    expect(result).toEqual({ ok: true, data });
  });

  it('improves a template via POST to the ai-improve sub-path', async () => {
    const data = { lang: 'en', subject: 'S2', body_html: 'B2', model_used: 'x:free' };
    mPost.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const result = await aiImproveMemberTemplate('t1', {
      lang: 'en',
      instruction: 'warmer',
    });

    expect(mPost).toHaveBeenCalledWith('/members/templates/t1/ai-improve', {
      lang: 'en',
      instruction: 'warmer',
    });
    expect(result).toEqual({ ok: true, data });
  });

  it('surfaces an error envelope as a typed failure (code preserved, no throw)', async () => {
    mPost.mockResolvedValue(
      createMockResponse({
        ok: false,
        status: 422,
        body: {
          success: false,
          error: 'model not allowed',
          code: 'errors.template.aiModelDisallowed',
        },
      }),
    );

    const result = await aiImproveMemberTemplate('t1', { lang: 'en', instruction: 'x' });

    expect(result).toEqual({
      ok: false,
      status: 422,
      error: 'model not allowed',
      code: 'errors.template.aiModelDisallowed',
      params: undefined,
    });
  });

  it('treats a non-2xx with no explicit success flag as a failure', async () => {
    mGet.mockResolvedValue(createMockResponse({ ok: false, status: 500, body: {} }));

    const result = await listMemberTemplates();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(500);
    }
  });
});
